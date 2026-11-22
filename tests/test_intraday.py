"""ml/intraday.py: the trading-day clock, the signal rows and the proof that no idea reads a later candle."""
import numpy as np
import pandas as pd

from ml import intraday
from ml.data import Bars
from ml.ideas import build


def random_walk(days=60, seed=3, start='2021-03-01 00:00'):
    """M1 gold-like bars for whole weekdays in UTC, with the 21:00 to 22:00 UTC daily break left out."""
    t = pd.date_range(start, periods=days * 1440, freq='min', tz='UTC')
    t = t[(t.dayofweek < 5) & (t.hour != 21)]
    rng = np.random.default_rng(seed)
    close = 1800 + np.cumsum(rng.normal(0, 0.35, len(t)))
    open_ = np.concatenate([[1800.0], close[:-1]])
    high = np.maximum(open_, close) + rng.uniform(0, 0.3, len(t))
    low = np.minimum(open_, close) - rng.uniform(0, 0.3, len(t))
    seconds = (t - pd.Timestamp('1970-01-01', tz='UTC')) // pd.Timedelta(seconds=1)
    return Bars(np.asarray(seconds, dtype=np.int64), open_, high, low, close, np.full(len(t), 0.3))


def test_clock_counts_from_the_17_00_start_of_the_trading_day():
    assert intraday.clock('17:00') == 0
    assert intraday.clock('19:00') == 120
    assert intraday.clock('03:00') == 600
    assert intraday.clock('16:00') == 1380
    assert intraday.ASIA < intraday.LONDON < intraday.NEW_YORK < intraday.NOON < intraday.FLAT


def test_signals_drop_rows_without_entry_side_stop_or_time_left():
    d = pd.DataFrame({'entry': [5, -1, 7, 8, 9, 10]})
    out = intraday.signals(d, [True] * 6, [1, 1, 0, -1, 1, np.nan], [2.0, 2.0, 2.0, 0.0, 2.0, 2.0], np.inf,
                           [600, 600, 600, 600, 20, 600])
    assert out['i'].tolist() == [5]
    assert out['hold'].dtype == np.int64 and out['hold'].tolist() == [600]


def test_day_trades_enter_at_19_00_and_are_flat_by_16_00():
    m1 = random_walk()
    sig = intraday.day_trade(build(m1, 3600), 'long')
    assert len(sig) > 20
    local = pd.to_datetime(m1.t[sig['i'].to_numpy()], unit='s', utc=True).tz_convert('America/New_York')
    assert set(local.hour) == {19} and set(local.minute) == {0}
    assert set(sig['hold']) == {21 * 60}


def test_every_idea_makes_signals_and_none_reads_a_later_candle():
    m1 = random_walk()
    ideas, _ = intraday.all_ideas(m1, with_map=False)
    assert len(ideas) == 46
    assert sum(len(idea['signals']) > 0 for idea in ideas) >= 40
    assert intraday.check(m1, cuts=3, log=lambda *_: None)
