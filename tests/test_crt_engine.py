import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from crt_engine import CrtConfig, detect, htf_candles, slot_closes  # noqa: E402
from app.domain import Signal, crt_rules  # noqa: E402

NY = dt.timezone(dt.timedelta(hours=-4))          # EDT, for building test timestamps
LOOSE = dict(min_rr=0.1, min_risk_atr=0)


def bars_for(candles, start):
    """Each (o, h, l, c) becomes 16 M15 bars (one H4 candle) that open at o, touch h and l, and close at c."""
    out, t = [], start
    for o, h, l, c in candles:
        for k in range(16):
            out.append({'t': t, 'o': o if k == 0 else c, 'h': h if k == 5 else max(o, c),
                        'l': l if k == 10 else min(o, c), 'c': c})
            t += 900
    return out


START = int(dt.datetime(2026, 9, 8, 1, 0, tzinfo=NY).timestamp())          # Tuesday 01:00 New York


def test_h4_candles_open_on_new_york_slots():
    candles = htf_candles(bars_for([(100, 101, 99, 100)] * 3, START), 4)
    assert [c.ny_hour for c in candles] == [1, 5, 9]
    assert slot_closes(START + 15 * 900, 4) and not slot_closes(START + 14 * 900, 4)


def test_bearish_crt_payload_passes_the_analyzer(monkeypatch):
    monkeypatch.setenv('CRT_MIN_RR', '0.1')
    # C1 range 100-110; C2 takes 112 (above C1 high), stays above 100, closes back inside at 106.
    m15 = bars_for([(105, 110, 100, 105), (107, 112, 104, 106)], START)
    setups = detect('XAUUSD', m15, CrtConfig(**LOOSE))
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'SELL_SETUP' and body['model'] == 'crt' and body['timeframe'] == '4h'
    assert body['sweep_level'] == 112 and body['stop'] > 112 and body['target_liquidity'] == 100
    assert body['bar_time'] == START + 2 * 4 * 3600                      # C2 closes 09:00 New York
    assert crt_rules(Signal.model_validate(body)) == []


def test_no_crt_when_close_stays_outside_or_both_sides_swept():
    outside = bars_for([(105, 110, 100, 105), (108, 113, 104, 112)], START)       # closes above C1 high
    both = bars_for([(105, 110, 100, 105), (105, 112, 98, 104)], START)           # takes both sides
    assert detect('XAUUSD', outside, CrtConfig(**LOOSE)) == []
    assert detect('XAUUSD', both, CrtConfig(**LOOSE)) == []


def test_forming_candle_never_signals():
    m15 = bars_for([(105, 110, 100, 105), (107, 112, 104, 106)], START)[:-1]     # C2's last bar not closed yet
    assert detect('XAUUSD', m15, CrtConfig(**LOOSE)) == []


def test_sunday_open_is_not_a_range_candle():
    sunday = int(dt.datetime(2026, 9, 6, 17, 0, tzinfo=NY).timestamp())     # C1 Sunday 17-21, C2 21-01 New York
    m15 = bars_for([(105, 110, 100, 105), (107, 112, 104, 106)], sunday)
    assert detect('XAUUSD', m15, CrtConfig(**LOOSE)) == []
    assert len(detect('BTCUSD', m15, CrtConfig(**LOOSE, crypto=True))) == 1


def test_key_times_and_min_rr_filters():
    m15 = bars_for([(105, 110, 100, 105), (107, 112, 104, 106)], START)
    assert detect('XAUUSD', m15, CrtConfig(**LOOSE, key_times=(9,))) == []      # C2 opens 05:00, not 09:00
    assert detect('XAUUSD', m15, CrtConfig(min_rr=5.0, min_risk_atr=0)) == []    # 6 to target vs ~6 risk: < 5R
