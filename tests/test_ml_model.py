"""ml/train.py, ml/predict.py and ml/monitor.py: the walk-forward finds a real signal and not a fake one, the gates,
model promotion, the predictor's gate lock and live/full-history feature match, and the monitor's checks."""
import json
import math
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
pd = pytest.importorskip('pandas')
lgb = pytest.importorskip('lightgbm')
pytest.importorskip('sklearn')

from ml import monitor, predict, train  # noqa: E402
from ml.data import from_dicts  # noqa: E402
from ml.ict_features import CATEGORICAL, FEATURES, CandidateConfig, detect  # noqa: E402
from tests.test_ict_features import walk  # noqa: E402

START = 1293840000           # 2011-01-01 UTC


def synthetic(n=9000, seed=1, signal=True):
    """Candidates over ~5 years. With `signal`, filled trades with a low spread_risk win far more often."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({name: rng.normal(size=n) for name in FEATURES})
    for name in CATEGORICAL:
        df[name] = rng.integers(0, 4, n)
    df['in_killzone'] = rng.integers(0, 2, n).astype(float)
    df['spread_risk'] = rng.uniform(0.02, 0.4, n)
    df['bar_time'] = np.sort(rng.integers(START, START + 5 * 365 * 86400, n))
    df['end_time'] = df['bar_time'] + 8 * 3600
    df['side'] = np.where(rng.random(n) < 0.5, 'BUY', 'SELL')
    df['symbol'] = 'XAUUSD'
    df['filled'] = rng.random(n) < 0.65
    p = np.where(df['spread_risk'] < 0.1, 0.6, 0.25) if signal else np.full(n, 0.33)
    win = rng.random(n) < p
    df['win'] = np.where(df['filled'], win.astype(float), np.nan)
    df['r'] = np.where(df['filled'], np.where(win, 2.0, -1.0), 0.0)
    df['r_net'] = df['r'] - np.where(df['filled'] & ~win, 0.5 * df['spread_risk'], 0.0)
    df['exit'] = np.where(df['filled'], np.where(win, 'final_target', 'sl'), '')
    return df


def test_walk_forward_learns_a_real_signal_and_the_control_does_not():
    df = synthetic()
    scored, _ = train.walk_forward(df, '2013-01-01', 6, 150, START)
    control, _ = train.walk_forward(df, '2013-01-01', 6, 150, START, shuffle=11)
    assert scored['fold'].nunique() >= 6
    # About a fifth of trades have a low spread and win 60% vs 25%: the best possible AUC is about 0.63.
    assert train.auc(scored) > 0.6 and abs(train.auc(control) - 0.5) < 0.05
    model = train.stats(train.policies(scored)['model'])
    assert model['expectancy_r'] > 0.3
    for _, part in scored.groupby('fold'):            # nothing after a fold start was used to train for it
        assert part['train_rows'].iloc[0] <= (df['filled'] & (df['end_time'] < part['bar_time'].min())).sum()


def test_no_signal_gives_no_skill_out_of_sample():
    """On noise the validation slice still finds cuts that look profitable (that is why the shuffled control and
    the out-of-sample gates exist), but out of sample there is no skill and no edge."""
    df = synthetic(signal=False, seed=4)
    scored, _ = train.walk_forward(df, '2013-01-01', 6, 150, START)
    assert abs(train.auc(scored) - 0.5) < 0.05
    assert train.stats(train.policies(scored)['model'])['expectancy_r'] < train.GATES['expectancy_r']


def test_choose_threshold_and_one_open_plan_per_side():
    prob = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95])
    r = np.array([-1, -1, -1, -1, -1, 2, 2, -1, 2, 2], dtype=float)
    cut, info = train.choose_threshold(prob, r, min_trades=3)
    assert 0.5 < cut <= 0.6 and info['n'] == 5           # ties keep the first (lowest) cut that selects them
    assert math.isinf(train.choose_threshold(prob, -np.ones(10), 3)[0])
    df = pd.DataFrame({'symbol': 'X', 'side': ['BUY', 'BUY', 'SELL', 'BUY'], 'bar_time': [0, 10, 12, 30],
                       'end_time': [20, 25, 40, 50]})
    assert list(train.take_non_overlapping(df).index) == [0, 2, 3]


def test_stats_drawdown_is_on_net_r_in_exit_order():
    t = pd.DataFrame({'filled': True, 'r': [2, -1, -1, 2, -1.0], 'r_net': [2, -1.1, -1.1, 2, -1.1],
                      'end_time': [1, 2, 3, 4, 5]})
    s = train.stats(t)
    assert s['trades'] == 5 and s['max_drawdown_r'] == pytest.approx(2.2)
    assert s['profit_factor'] == pytest.approx(4 / 3.3) and s['win_rate'] == pytest.approx(0.4)


def booster(seed=0):
    rng = np.random.default_rng(seed)
    x = pd.DataFrame(rng.normal(size=(400, len(FEATURES))), columns=list(FEATURES))
    return lgb.train({'objective': 'binary', 'verbose': -1, 'min_data_in_leaf': 20},
                     lgb.Dataset(x, rng.integers(0, 2, 400)), num_boost_round=5)


def meta(passed, day='2026-01-01', threshold=0.0):
    return {'trained_to': day, 'gates_passed': passed, 'threshold': threshold, 'features': list(FEATURES),
            'gates': [{'gate': 1, 'passed': passed}], 'rr': 2.0}


def test_a_failed_model_never_replaces_a_passing_one(tmp_path):
    b = booster()
    first = train.save_model(b, meta(False, '2026-01-01'), tmp_path, 'XAUUSD')
    assert first['promoted']                                         # nothing better in place
    good = train.save_model(b, meta(True, '2026-02-01'), tmp_path, 'XAUUSD')
    bad = train.save_model(b, meta(False, '2026-03-01'), tmp_path, 'XAUUSD')
    assert good['promoted'] and not bad['promoted'] and bad['kept'] == good['version']
    assert json.loads((tmp_path / 'xauusd_ict_lgbm.json').read_text())['version'] == good['version']
    assert (tmp_path / f"{bad['version']}.txt").exists()            # still saved, for the record


def test_predict_refuses_failed_or_thresholdless_models(tmp_path):
    train.save_model(booster(), meta(False), tmp_path, 'XAUUSD')
    with pytest.raises(predict.ModelRefused):
        predict.load_model('XAUUSD', tmp_path)
    assert predict.load_model('XAUUSD', tmp_path, allow_failed=True)[1]['gates_passed'] is False
    other = tmp_path / 'b'
    train.save_model(booster(), meta(True, threshold=None), other, 'XAUUSD')
    with pytest.raises(predict.ModelRefused):
        predict.load_model('XAUUSD', other)


def test_live_scoring_sees_the_same_features_as_the_full_history():
    bars = from_dicts(walk(24000, seed=5))
    full = [r for r in detect('XAUUSD', bars, CandidateConfig()) if r['bar_index'] > 16000]
    assert full
    row = full[0]
    m5 = bars.slice(0, row['bar_index'] + 1)
    b, m = booster(), meta(True, threshold=0.0)
    live = [r for r in predict.score('XAUUSD', m5, b, m) if r['side'] == row['side']]
    assert len(live) == 1 and live[0]['take']
    for name in FEATURES:
        assert live[0][name] == pytest.approx(row[name], rel=1e-4, abs=1e-6, nan_ok=True), name
    short = [r for r in predict.score('XAUUSD', m5, b, m, lookback=3000) if r['side'] == row['side']]
    assert short and short[0]['ema_h4_50_atr'] != pytest.approx(row['ema_h4_50_atr'], rel=1e-3)
    assert predict.signals(live)[0]['ml_probability'] == round(live[0]['probability'], 4)


def test_psi_is_zero_for_the_same_distribution_and_large_for_a_shift():
    rng = np.random.default_rng(3)
    base = rng.normal(size=5000)
    assert monitor.psi(base, rng.normal(size=5000)) < 0.02
    assert monitor.psi(base, rng.normal(1.0, 1.0, 5000)) > monitor.PSI_ALERT
    assert monitor.categorical_psi(np.array([0, 1] * 500), np.array([0] * 900 + [1] * 100)) > monitor.PSI_ALERT


def test_performance_alerts_only_with_enough_trades_far_below_expectation():
    expected = {'expectancy_r': 0.15, 'win_rate': 0.4, 'r_std': 1.4}
    bad = pd.DataFrame({'r': [-1.0] * 40 + [2.0] * 10})
    out = monitor.performance(bad, expected, min_trades=50)
    assert out['judged'] and len(out['alerts']) == 2
    assert not monitor.performance(bad.head(30), expected, 50)['alerts']
    fine = pd.DataFrame({'r': [2.0] * 20 + [-1.0] * 30})
    assert not monitor.performance(fine, expected, 50)['alerts']
