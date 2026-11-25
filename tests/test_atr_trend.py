"""ml/atr_trend.py: the screen's array version of the indicator must mark exactly what web/trend.py marks."""
import pytest

np = pytest.importorskip('numpy')          # the ML layer is optional: requirements-ml.txt
pytest.importorskip('pandas')

from ml import atr_trend  # noqa: E402
from ml.data import Bars  # noqa: E402
from ml.ideas import build  # noqa: E402
from web import trend  # noqa: E402


def market(count=9000, seed=5, start=1_790_000_100 // 3600 * 3600) -> Bars:
    rng = np.random.default_rng(seed)
    drift = np.where((np.arange(count) // 700) % 2 == 0, 0.03, -0.03)
    close = 3000 + np.cumsum(drift + rng.normal(0, 0.3, count))
    opened = np.concatenate([[3000.0], close[:-1]])
    wick = np.abs(rng.normal(0, 0.1, (2, count)))
    return Bars(start + 60 * np.arange(count), opened, np.maximum(opened, close) + wick[0], np.minimum(opened, close) - wick[1],
                close, np.full(count, 0.2))


def test_the_screen_marks_the_same_flips_and_filters_as_the_website_engine():
    m1 = market()
    mine = atr_trend.features(m1, build(m1, 300)).set_index('t')
    rows = trend.evaluate(m1.dicts(0, len(m1)), 300, trend.TrendConfig(use_bos=True))
    assert len(rows) > 1500 and sum(row['flip'] is not None for row in rows) > 20
    for row in rows:
        m = mine.loc[row['t']]
        assert {1: 'BUY', -1: 'SELL', 0: None}[int(m['flip'])] == row['flip']
        assert m['line'] == pytest.approx(row['trail'])
        for name, reason in atr_trend.BLOCKS.items():
            for side in ('buy', 'sell'):
                passes = bool(m[f'{name}_{side}'] if name in atr_trend.TWO_SIDED else m[name])
                assert passes == (reason not in row[f'{side}_blocked']), (row['t'], name, side)


def test_entries_follow_the_flip_with_the_stop_line_as_the_stop_and_never_change_with_later_candles():
    m1 = market()
    d = atr_trend.features(m1, build(m1, 300))
    fixed = atr_trend.signals(d, (), '2R target', 300, 1440, 2880)
    trail = atr_trend.signals(d, (), 'trail', 300, 1440, 2880)
    flips = d[(d['flip'] != 0) & (d['entry'] >= 0)]
    assert len(fixed) == len(trail) == len(flips) and (fixed['side'].to_numpy() == np.sign(flips['flip'].to_numpy())).all()
    # The stop is the line on the signal bar, never closer than 1 ATR; a 2R target; the trail waits for the next flip.
    wanted = np.maximum((flips['c'] - flips['line']).abs(), flips['atr']).to_numpy()
    assert np.allclose(fixed['stop'], wanted) and np.allclose(fixed['target'], 2 * wanted) and (fixed['hold'] == 1440).all()
    assert np.isinf(trail['target']).all()
    gaps = np.diff(flips['t'].to_numpy()) // 60
    assert (trail['hold'].to_numpy()[:-1] == np.clip(gaps, 5, 2880)).all()
    strict = atr_trend.signals(d, ('base', 'near', 'htf'), '2R target', 300, 1440, 2880)
    assert 0 < len(strict) < len(fixed) and set(strict['i']) <= set(fixed['i'])
    cut = m1.slice(0, 6000)
    early = atr_trend.signals(atr_trend.features(cut, build(cut, 300)), (), '2R target', 300, 1440, 2880)
    assert early.equals(fixed[fixed['i'] < 6000].reset_index(drop=True))
