import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from mss_engine import MssConfig, detect, h1_from_m15  # noqa: E402
from app.domain import Signal, mss_rules, trade_plan  # noqa: E402

UTC = dt.timezone.utc
# Sunday 00:00 UTC: the 125 hourly bars below end on Thursday 04:00 UTC, a weekday decision bar.
START = int(dt.datetime(2026, 9, 6, 0, 0, tzinfo=UTC).timestamp())
TROUGH = 120                                                # the swing low that gets swept


def centre(k: int) -> float:
    """A triangle wave: 98 at k = 0, 10, 20, ... and 102 at k = 5, 15, ...; every peak and trough is a 2/2 swing."""
    phase = k % 10
    return 98 + 0.8 * phase if phase <= 5 else 102 - 0.8 * (phase - 5)


def hours(sweep: bool = True, shift: bool = True, spike: bool = False) -> list[tuple[float, float, float, float]]:
    """Small one-point candles following the triangle (ATR about 1), a trough at bar 120 confirmed by bars 121-122,
    a bar that wicks below it and closes back (the sweep) and a wide bullish bar closing above the last peak (the
    shift). `spike` plants a lone swing high at 125 thirty bars earlier: the next liquidity pool above the entry."""
    shapes = [(centre(k) - 0.2, centre(k) + 0.5, centre(k) - 0.5, centre(k) + 0.2) for k in range(TROUGH + 3)]
    if spike:
        o, _, l, c = shapes[90]
        shapes[90] = (o, 125.0, l, c)
    shapes.append((99.6, 100.1, 97.3 if sweep else 97.6, 99.9))                 # bar 123: the sweep of 97.5
    shapes.append((99.9, 103.6, 99.8, 103.5) if shift else (99.9, 100.4, 99.8, 100.2))   # bar 124: the shift
    return shapes


def m15(shapes, start: int = START) -> list[dict]:
    """Each hour as four M15 bars: the first carries the hour's range, the other three sit flat at its close."""
    bars = []
    for k, (o, h, l, c) in enumerate(shapes):
        t = start + 3600 * k
        bars.append({'t': t, 'o': o, 'h': h, 'l': l, 'c': c})
        bars += [{'t': t + 900 * q, 'o': c, 'h': c, 'l': c, 'c': c} for q in (1, 2, 3)]
    return bars


def mirror(bars):
    """The same bars upside down around 100, for the SELL side."""
    return [{'t': b['t'], 'o': 200 - b['o'], 'h': 200 - b['l'], 'l': 200 - b['h'], 'c': 200 - b['c']} for b in bars]


@pytest.fixture(autouse=True)
def gold(monkeypatch):
    monkeypatch.setenv('SYMBOLS', 'XAUUSD,EURUSD')
    monkeypatch.setenv('MSS_SYMBOLS', 'XAUUSD')
    monkeypatch.delenv('MSS_MIN_RR', raising=False)


def test_hourly_candles_are_built_on_the_hour_and_a_forming_hour_is_dropped():
    bars = m15([(1, 3, 0.5, 2), (2, 2.5, 1, 1.5)])
    bars[1]['h'], bars[6]['l'] = 4, 0.2                                     # a later quarter extends the hour
    candles = h1_from_m15(bars)
    assert candles == [{'t': START, 'o': 1, 'h': 4, 'l': 0.5, 'c': 2}, {'t': START + 3600, 'o': 2, 'h': 2.5, 'l': 0.2, 'c': 1.5}]
    assert h1_from_m15(bars[:-1]) == candles[:1]                           # the second hour has no :45 bar yet


def test_buy_setup_after_a_sweep_and_a_displacement_shift_passes_the_analyzer():
    bars = m15(hours())
    setups = detect('XAUUSD', bars, MssConfig())
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'BUY_SETUP' and body['model'] == 'mss' and body['timeframe'] == '1h'
    assert body['bar_time'] == START + 3600 * 125                          # the shift candle's close
    assert body['swing_low'] == 97.5 and body['sweep_level'] == 97.3 and body['mss_level'] == 102.5
    assert body['entry'] == body['price'] == 103.5
    risk = body['entry'] - body['stop']
    assert body['stop'] == pytest.approx(97.3 - 0.5 * body['atr'])
    assert body['target_liquidity'] == pytest.approx(body['entry'] + 2 * risk) and body['target_name'] == '2R'
    signal = Signal.model_validate(body)
    assert mss_rules(signal) == []
    plan = trade_plan(signal)
    assert plan['entry'] == 103.5 and plan['targets'][0][0] == 2.0 and plan['targets'] [0][1] == body['target_liquidity']


def test_sell_setup_is_the_mirror_image():
    setups = detect('XAUUSD', mirror(m15(hours())), MssConfig())
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'SELL_SETUP'
    assert body['swing_high'] == 102.5 and body['sweep_level'] == 102.7 and body['mss_level'] == 97.5
    assert body['stop'] > body['sweep_level'] > body['entry'] > body['target_liquidity']
    assert mss_rules(Signal.model_validate(body)) == []


def test_target_is_the_next_swing_when_it_clears_the_minimum_rr():
    body = detect('XAUUSD', m15(hours(spike=True)), MssConfig())[0]
    assert body['target_liquidity'] == 125.0 and body['target_name'] == 'swing high'
    assert (125.0 - body['entry']) / (body['entry'] - body['stop']) >= 2
    assert mss_rules(Signal.model_validate(body)) == []
    body = detect('XAUUSD', m15(hours(spike=True)), MssConfig(min_rr=4.0))[0]
    assert body['target_name'] == '4R'                                    # 125 is under 4R away: project instead


def test_no_setup_without_a_sweep_or_without_displacement():
    assert detect('XAUUSD', m15(hours(sweep=False)), MssConfig()) == []
    assert detect('XAUUSD', m15(hours(shift=False)), MssConfig()) == []


def test_weekend_candles_never_signal_and_the_analyzer_agrees():
    tuesday = int(dt.datetime(2026, 9, 8, 0, 0, tzinfo=UTC).timestamp())  # bar 124 opens on Sunday
    assert detect('XAUUSD', m15(hours(), start=tuesday), MssConfig()) == []
    body = detect('XAUUSD', m15(hours(), start=tuesday), MssConfig(crypto=True))[0]
    assert mss_rules(Signal.model_validate(body)) == ['weekend_candle']


def test_analyzer_rejects_a_disabled_symbol_a_short_target_and_a_broken_payload():
    body = detect('XAUUSD', m15(hours()), MssConfig())[0]
    assert mss_rules(Signal.model_validate({**body, 'symbol': 'EURUSD'})) == ['mss_not_enabled_for_symbol']
    short = {**body, 'target_liquidity': body['entry'] + 1.5 * (body['entry'] - body['stop'])}
    assert mss_rules(Signal.model_validate(short)) == ['target_too_close']
    assert mss_rules(Signal.model_validate({**body, 'stop': body['sweep_level'] + 0.1})) == ['stop_not_beyond_sweep']
    with pytest.raises(ValueError):
        Signal.model_validate({**body, 'timeframe': '4h'})
    with pytest.raises(ValueError):
        Signal.model_validate({k: v for k, v in body.items() if k != 'swing_low'})
