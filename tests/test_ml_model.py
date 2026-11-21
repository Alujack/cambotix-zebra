"""ml/train.py (plan v2), ml/predict.py, ml/backtest.py and ml/monitor.py: the expected-profit model finds a real
signal and not a fake one, the pieces of the model, promotion, the predictor's locks and its live/full-history
feature match, and the monitor's checks."""
import json
import math

import pytest

np = pytest.importorskip('numpy')
pd = pytest.importorskip('pandas')
lgb = pytest.importorskip('lightgbm')
pytest.importorskip('sklearn')

from ml import backtest, lockbox, monitor, predict, train  # noqa: E402
from ml.data import from_dicts  # noqa: E402
from ml.ict_features import FEATURES, CandidateConfig, detect  # noqa: E402
from tests.synthetic_ml import START, candidates  # noqa: E402
from tests.test_ict_features import walk  # noqa: E402


@pytest.fixture(scope='module')
def data():
    return train.prepare(candidates())


@pytest.fixture(scope='module')
def small_bundle(data):
    filled = data[data['filled']].head(1500)
    return train.fit_bundle(filled, {'cls': 8, 'timeout': 8}, seeds=(7, 11))


def meta_for(bundle, passed, day='2026-01-01', threshold=-99.0):
    return {'trained_to': day, 'gates_passed': passed, 'threshold': threshold, 'features': list(FEATURES),
            'gates': [{'gate': 1, 'passed': passed}], 'rr': 2.0, 'means': bundle['means'], 'rounds': bundle['rounds']}


# -- the model ---------------------------------------------------------------------------------------------
def test_prepare_keeps_tradable_resolved_rows_and_charges_slippage_on_stops_and_timeouts():
    raw = candidates(400, seed=3)
    raw.loc[0, 'tradable'] = False
    raw.loc[1, 'outcome'] = 'unresolved'
    df = train.prepare(raw)
    assert len(df) == 398 and df['filled'].sum() == (df['outcome'] == 'closed').sum()
    stopped = df[df['exit'] == 'sl'].iloc[0]
    won = df[df['exit'] == 'final_target'].iloc[0]
    assert stopped['r_net'] == pytest.approx(stopped['r'] - 0.5 * stopped['spread_risk'])
    assert won['r_net'] == won['r'] and set(df['cls'].dropna()) == {0.0, 1.0, 2.0}


def test_weights_halve_every_four_years():
    df = pd.DataFrame({'bar_time': [0, 4 * 365.25 * 86400, 8 * 365.25 * 86400]})
    assert list(train.weights(df)) == pytest.approx([0.25, 0.5, 1.0])


def test_expected_r_is_the_three_outcomes_weighted_by_their_probabilities(data, small_bundle):
    part = data.head(300)
    s = train.score(small_bundle, part)
    assert np.allclose(s[['p_target', 'p_stop', 'p_timeout']].sum(axis=1), 1.0)
    means = small_bundle['means']
    want = s['p_target'] * means['target'] + s['p_stop'] * means['stop'] + s['p_timeout'] * s['timeout_r']
    assert s['expected_r'].to_numpy() == pytest.approx(want.to_numpy())
    assert means['target'] > 1.5 and means['stop'] < -1.0 and len(small_bundle['cls']) == 2


def test_timeout_model_never_rises_with_spread_over_risk(data):
    filled = data[data['filled']]
    bundle = train.fit_bundle(filled, {'cls': 5, 'timeout': 60}, seeds=(7,))
    row = filled.iloc[[0]]
    sweep = pd.concat([row.assign(spread_risk=x) for x in np.linspace(0.01, 0.5, 40)], ignore_index=True)
    out = bundle['timeout'][0].predict(sweep[list(FEATURES)])
    assert (np.diff(out) <= 1e-12).all()


def test_walk_forward_learns_a_real_signal_and_the_control_does_not(data):
    scored, _ = train.walk_forward(data, '2013-01-01', 6, 150, START)
    control, _ = train.walk_forward(data, '2013-01-01', 6, 150, START, shuffle=11)
    assert scored['fold'].nunique() >= 6
    # A quarter of setups reach the target 55% of the time against 15%: the best possible AUC is about 0.66.
    assert train.auc(scored) > 0.62 and abs(train.auc(control) - 0.5) < 0.05
    pol = train.policies(scored)
    model = train.stats(pol['model'])
    assert model['expectancy_r'] > 0.3 > train.stats(train.policies(control)['model'])['expectancy_r']
    assert model['expectancy_r'] > train.stats(pol['all tradable candidates'])['expectancy_r'] + 0.5
    tenth = train.by_tenth(scored)
    assert tenth['realised'].iloc[-1] > tenth['realised'].iloc[0] + 0.5        # predicted profit sorts realised
    assert tenth['target'].iloc[-1] > 2 * tenth['target'].iloc[0]              # by reaching the target
    assert scored.groupby('fold')['rank_check'].first().mean() > 0.5
    for _, part in scored.groupby('fold'):            # nothing after a fold start was used to train for it
        assert part['train_rows'].iloc[0] <= (data['filled'] & (data['end_time'] < part['bar_time'].min())).sum()
    gates = {g['gate']: g['passed'] for g in train.gates(pol, train.policies(control), scored, control, None)}
    assert gates[1] and gates[3] and not gates[5]                              # no broker dataset: gate 5 fails


def test_no_signal_gives_no_skill_out_of_sample():
    df = train.prepare(candidates(signal=False, seed=4))
    scored, _ = train.walk_forward(df, '2013-01-01', 6, 150, START)
    assert abs(train.auc(scored) - 0.5) < 0.05
    model = train.stats(train.policies(scored)['model'])
    assert model['expectancy_r'] is None or model['expectancy_r'] < train.GATES['expectancy_r']


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


def test_half_spread_line_regrades_the_models_own_choices():
    scored = pd.DataFrame({'symbol': 'XAUUSD', 'side': ['BUY', 'SELL', 'BUY'], 'bar_time': [10, 20, 30],
                           'expected_r': [0.5, -0.5, 0.4], 'threshold': 0.0})
    half = pd.DataFrame({'side': ['BUY', 'SELL', 'BUY'], 'bar_time': [10, 20, 30], 'end_time': [15.0, 25, 35],
                         'filled': [True, True, True], 'r': [2.0, 2.0, -1.0], 'r_net': [2.0, 2.0, -1.05]})
    out = train.half_spread(scored, half)
    assert out['trades'] == 2 and out['total_r'] == pytest.approx(0.95)       # the skipped SELL is not counted
    assert train.half_spread(scored, None) is None


# -- saving, promotion, prediction ---------------------------------------------------------------------------
def test_saved_model_scores_the_same_and_a_failed_model_never_replaces_a_passing_one(tmp_path, data, small_bundle):
    first = train.save_model(small_bundle, meta_for(small_bundle, False, '2026-01-01'), tmp_path, 'XAUUSD')
    assert first['promoted']                                         # nothing better in place
    loaded, meta = train.load_model('XAUUSD', tmp_path)
    part = data.head(50)
    assert train.score(loaded, part)['expected_r'].to_numpy() == pytest.approx(
        train.score(small_bundle, part)['expected_r'].to_numpy())
    good = train.save_model(small_bundle, meta_for(small_bundle, True, '2026-02-01'), tmp_path, 'XAUUSD')
    bad = train.save_model(small_bundle, meta_for(small_bundle, False, '2026-03-01'), tmp_path, 'XAUUSD')
    assert good['promoted'] and not bad['promoted'] and bad['kept'] == good['version']
    assert json.loads((tmp_path / 'xauusd_ict_v2.json').read_text())['version'] == good['version']
    assert (tmp_path / f"{bad['version']}.models.json").exists()    # still saved, for the record


def test_predict_needs_passed_gates_a_cut_and_a_passed_final_test(tmp_path, small_bundle):
    failed = tmp_path / 'failed'
    train.save_model(small_bundle, meta_for(small_bundle, False), failed, 'XAUUSD')
    with pytest.raises(predict.ModelRefused, match='development gates'):
        predict.load_model('XAUUSD', failed)
    assert predict.load_model('XAUUSD', failed, research=True)[1]['gates_passed'] is False

    no_cut = tmp_path / 'no_cut'
    train.save_model(small_bundle, meta_for(small_bundle, True, threshold=None), no_cut, 'XAUUSD')
    with pytest.raises(predict.ModelRefused, match='no profitable cut'):
        predict.load_model('XAUUSD', no_cut)

    ok = tmp_path / 'ok'
    saved = train.save_model(small_bundle, meta_for(small_bundle, True), ok, 'XAUUSD')
    with pytest.raises(predict.ModelRefused, match='has not run'):
        predict.load_model('XAUUSD', ok)
    lockbox.seal('XAUUSD', ok, {'passed': False, 'model': saved['version']})
    with pytest.raises(predict.ModelRefused, match='did not pass'):
        predict.load_model('XAUUSD', ok)
    lockbox.record_file('XAUUSD', ok).unlink()
    lockbox.seal('XAUUSD', ok, {'passed': True, 'model': saved['version']})
    assert predict.load_model('XAUUSD', ok)[1]['version'] == saved['version']


def test_live_scoring_sees_the_same_features_as_the_full_history(monkeypatch, small_bundle):
    bars = from_dicts(walk(24000, seed=5))
    full = [r for r in detect('XAUUSD', bars, CandidateConfig()) if r['bar_index'] > 16000]
    assert full
    row = full[0]
    m5 = bars.slice(0, row['bar_index'] + 1)
    meta = meta_for(small_bundle, True)
    live = [r for r in predict.score('XAUUSD', m5, small_bundle, meta) if r['side'] == row['side']]
    assert len(live) == 1 and live[0]['take'] and live[0]['tradable']
    for name in FEATURES:                              # the 50 v1 inputs and the 11 v2 ones
        assert live[0][name] == pytest.approx(row[name], rel=1e-4, abs=1e-6, nan_ok=True), name
    short = [r for r in predict.score('XAUUSD', m5, small_bundle, meta, lookback=3000) if r['side'] == row['side']]
    assert short and short[0]['ema_h4_50_atr'] != pytest.approx(row['ema_h4_50_atr'], rel=1e-3)
    body = predict.signals(live)[0]
    assert body['ml_probability'] == round(live[0]['p_target'], 4) and 'ml_expected_r' in body
    monkeypatch.setattr(predict, 'ACCOUNT_RISK_USD', 0.01)           # a stop the account cannot size
    blocked = predict.score('XAUUSD', m5, small_bundle, meta)
    assert blocked and not any(r['take'] or r['tradable'] for r in blocked) and predict.signals(blocked) == []


# -- backtest ------------------------------------------------------------------------------------------------
def test_backtest_trains_only_before_the_period_and_explains_its_cut(data):
    start = START + 4 * 365 * 86400
    fold = backtest.fit_before(data, start, START, 150)
    assert fold['train_rows'] == int((data['filled'] & (data['end_time'] < start - train.EMBARGO)).sum())
    assert fold['val']['bar_time'].max() < start
    s = backtest.scan(fold['val'], 150)
    assert len(s) == len(backtest.QUANTILES) and s['trades'].is_monotonic_decreasing
    assert s['qualifies'].any() == (not math.isinf(fold['threshold']))      # the scan explains the decision
    assert s['target'].iloc[-2] > s['target'].iloc[0]                       # stricter cuts reach the target more
    period = backtest.score(data[data['bar_time'] >= start], fold)
    model = train.stats(backtest.trades_at(period, fold['threshold']))
    assert model['expectancy_r'] > train.stats(backtest.trades_at(period, -99.0))['expectancy_r']
    text = backtest.report('XAUUSD', start, int(data['bar_time'].max()) + 1, fold, period, None)
    assert '## Why: every cut the model tried on validation' in text and '## Model net R by month' in text


# -- monitor -------------------------------------------------------------------------------------------------
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
