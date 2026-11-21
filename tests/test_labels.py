"""ml/labels.py and ml/dataset.py: labels equal what scripts/backtest.py grades, the spread repair, and a dataset
built end to end from a small saved history."""
import json
import math
import sys
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')          # the ML layer is optional: requirements-ml.txt
pd = pytest.importorskip('pandas')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import backtest  # noqa: E402
from ml import dataset  # noqa: E402
from ml.data import Bars, from_dicts, repair_spread, resample  # noqa: E402
from ml.ict_features import CandidateConfig, detect  # noqa: E402
from ml.labels import label  # noqa: E402

SUNDAY = 1788732000          # 2026-09-06 22:00 UTC


def m1_walk(minutes, seed=5, start=SUNDAY, spread=0.2):
    """A fat-tailed random walk in M1 bars (weekends included, so no gaps) with a fixed spread."""
    rng = np.random.default_rng(seed)
    path = 2000 + np.cumsum(rng.standard_t(3, size=minutes * 4) * 0.12).reshape(minutes, 4)
    opens = np.concatenate([[2000.0], path[:-1, -1]])
    return [{'t': start + 60 * k, 'o': float(opens[k]), 'h': float(max(opens[k], path[k].max())),
             'l': float(min(opens[k], path[k].min())), 'c': float(path[k, -1]), 'spread': spread}
            for k in range(minutes)]


def test_labels_equal_the_backtest_grade_of_every_killzone_engine_setup(monkeypatch):
    """The plans scripts/backtest.py publishes and grades (analyzer rules, ledger.plan_record, the grader) must get
    exactly the R that ml.labels gives the same candidate. The open-plan limit is off: the dataset keeps every
    candidate and the walk-forward applies the limit later."""
    monkeypatch.setenv('ICT_SYMBOLS', 'XAUUSD')
    monkeypatch.setenv('MAX_OPEN_SAME_DIRECTION', '0')
    m1_rows = m1_walk(60 * 24 * 150)
    m1 = from_dicts(m1_rows)
    m5 = resample(m1, 300)
    payloads = backtest.ict_payloads('XAUUSD', {'m1': m1_rows})
    trades, rejected = backtest.grade(payloads, m1_rows)
    assert len(trades) >= 10, (len(trades), rejected)
    assert not [k for k in rejected if not k.startswith('not_filled')]      # every setup passed the rules

    rows = detect('XAUUSD', m5, CandidateConfig(warmup_bars=0))
    by_key = {(r['bar_time'], r['side']): (r, lab) for r, lab in zip(rows, label(rows, m1))}
    for trade in trades:
        row, lab = by_key[(trade['published_at'], trade['direction'])]
        assert lab['outcome'] == 'closed'
        assert lab['r'] == pytest.approx(trade['r_tp1'], abs=1e-6)
        assert lab['exit'] == trade['exit'] and lab['end_time'] == trade['time']
    filled = sum(1 for _, lab in by_key.values() if lab['outcome'] == 'closed')
    assert filled >= len(trades)               # the broad engine finds more than the killzone engine


def test_unfilled_limit_scores_zero_and_history_end_is_unresolved():
    m1_rows = m1_walk(60 * 24 * 20, seed=9)
    m1 = from_dicts(m1_rows)
    rows = detect('XAUUSD', resample(m1, 300), CandidateConfig(warmup_bars=0))
    labels = label(rows, m1)
    kinds = {lab['outcome'].split(':')[0] for lab in labels}
    assert {'closed', 'not_filled'} <= kinds
    for lab in labels:
        if lab['outcome'].startswith('not_filled'):
            assert lab['r'] == 0 and math.isnan(lab['win'])
        if lab['outcome'] == 'closed':
            assert lab['win'] == float(lab['r'] > 0) and lab['fill_time'] <= lab['end_time']
    late = dict(rows[-1], bar_time=int(m1.t[-1]) - 600)
    assert label([late], m1)[0]['outcome'] == 'unresolved'


def bars(t, spread):
    t = np.asarray(t, dtype=np.int64)
    one = np.ones(len(t))
    return Bars(t, one, one * 2, one * 0.5, one, np.asarray(spread, dtype=float))


def test_repair_spread_replaces_zeros_with_the_hour_median():
    jan_2012 = 1325376000
    t = [jan_2012 + 3600 * 5 + 60 * k for k in range(4)] + [jan_2012 + 3600 * 6]
    fixed, report = repair_spread(bars(t, [0.3, 0.5, 0.0, -1.0, 0.9]))
    assert list(fixed.spread) == [0.3, 0.5, 0.4, 0.4, 0.9]
    assert report == {'2012': {'zero_replaced': 2}}
    assert list(fixed.h) == [2.0] * 5                                        # prices untouched


def test_repair_spread_raises_coarse_years_to_their_p99_only():
    jan_2010, jan_2011 = 1262304000, 1293840000
    t = [jan_2010 + 60 * k for k in range(100)] + [jan_2011 + 60 * k for k in range(3)]
    spread = [0.4] * 99 + [0.7] + [0.1, 0.2, 0.3]
    fixed, report = repair_spread(bars(t, spread), coarse_before_year=2011)
    floor = float(np.quantile(spread[:100], 0.99))
    assert fixed.spread[:100].min() == pytest.approx(floor) and fixed.spread[99] == 0.7
    assert list(fixed.spread[100:]) == [0.1, 0.2, 0.3]                       # 2011 keeps its real spread
    assert report['2010']['raised'] == 99 and '2011' not in report


def test_build_keeps_warmup_out_and_marks_coarse_years(tmp_path):
    """A small history in a folder, built the way the CLI does: candidates only from --from on, every one labelled,
    the coarse-spread flag set by year, and a parquet that round-trips."""
    pytest.importorskip('pyarrow')
    rows = m1_walk(60 * 24 * 30, seed=3, start=1293919200)                  # 2011-01-01 22:00 UTC, Saturday
    for r in rows:
        r['spread'] = 0.0 if r['t'] % 7 == 0 else r['spread']
    pd.DataFrame(rows).to_csv(tmp_path / 'XAUUSD_m1.csv', index=False)
    (tmp_path / 'XAUUSD_meta.json').write_text(json.dumps({'checks': {'passed': True}}))
    df, meta = dataset.build('XAUUSD', tmp_path, start='2011-01-10', coarse_until=2012)
    assert len(df) > 20 and df['bar_time'].min() >= dataset.epoch('2011-01-10')
    assert set(df['spread_coarse']) == {1.0} and set(df['year']) == {2011}
    assert df['outcome'].notna().all() and meta['candidates'] == len(df)
    assert meta['history_check'] == {'passed': True} and meta['spread_repair']['2011']['coarse_floor'] > 0
    df.to_parquet(tmp_path / 'd.parquet', index=False)
    assert pd.read_parquet(tmp_path / 'd.parquet').shape == df.shape
    text = dataset.summary(df, meta)
    assert '| 2011 |' in text and 'baseline a model has to beat' in text
