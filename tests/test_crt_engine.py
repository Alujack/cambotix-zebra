import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from crt_engine import CrtConfig, detect, htf_candles  # noqa: E402

NY = dt.timezone(dt.timedelta(hours=-4))          # EDT, for building test timestamps


def bars_for(candles, start):
    """Each (o, h, l, c) becomes 16 M15 bars (one H4 candle) that open at o, touch h and l, close at c."""
    out, t = [], start
    for o, h, l, c in candles:
        for k in range(16):
            first, last = k == 0, k == 15
            out.append({'t': t, 'o': o if first else c, 'h': h if k == 5 else max(o, c), 'l': l if k == 10 else min(o, c),
                        'c': c if last else (o if not first else o)})
            t += 900
    return out


START = int(dt.datetime(2026, 9, 8, 1, 0, tzinfo=NY).timestamp())          # Tuesday 01:00 New York


def test_h4_candles_open_on_new_york_slots():
    candles = htf_candles(bars_for([(100, 101, 99, 100)] * 3, START), 4)
    assert [c.ny_hour for c in candles] == [1, 5, 9]


def test_bearish_crt_sweeps_high_and_closes_inside():
    # C1 range 100-110; C2 takes 112 (above C1 high), stays above 100, closes back inside at 106.
    m15 = bars_for([(105, 110, 100, 105), (107, 112, 104, 106)], START)
    setups = detect('XAUUSD', m15, CrtConfig(min_rr=0.1, min_risk_atr=0))
    assert len(setups) == 1
    s = setups[0]
    assert s['direction'] == 'SELL' and s['swept'] == 'C1 high'
    assert s['stop'] > 112 and s['targets'][-1][1] == 100
    assert s['session'] == 'C2 05:00 NY'


def test_no_crt_when_close_stays_outside_or_both_sides_swept():
    outside = bars_for([(105, 110, 100, 105), (108, 113, 104, 112)], START)       # closes above C1 high
    both = bars_for([(105, 110, 100, 105), (105, 112, 98, 104)], START)           # takes both sides
    assert detect('XAUUSD', outside, CrtConfig(min_rr=0.1, min_risk_atr=0)) == []
    assert detect('XAUUSD', both, CrtConfig(min_rr=0.1, min_risk_atr=0)) == []


def test_key_times_filter():
    m15 = bars_for([(105, 110, 100, 105), (107, 112, 104, 106)], START)
    assert detect('XAUUSD', m15, CrtConfig(min_rr=0.1, min_risk_atr=0, key_times=(9,))) == []
