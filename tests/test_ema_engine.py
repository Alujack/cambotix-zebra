import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from ema_engine import EmaConfig, detect, in_session  # noqa: E402
from app.domain import Signal, ema_rules, trade_plan  # noqa: E402

UTC = dt.timezone.utc
# Wednesday 08:00 UTC = 09:00 London: 700 one-minute bars run to 19:40 UTC, inside New York hours.
START = int(dt.datetime(2026, 9, 9, 8, 0, tzinfo=UTC).timestamp())
STEP = 0.01                                                 # the trend climbs one cent per minute


def ramp(k: int) -> tuple[float, float, float, float]:
    base = 100 + STEP * k
    return base, base + 0.03, base - 0.02, base + 0.01     # o, h, l, c: a small bullish candle


def session(start: int = START, pullback: bool = True, trigger: bool = True) -> list[dict]:
    """A steady uptrend (EMA20 > EMA50 > EMA200), a four-candle dip through EMA20, then a candle resuming through
    the previous high. Without `pullback` the dip is left out; without `trigger` the last candle stays small."""
    shapes = [ramp(k) for k in range(680)]
    base = 100 + STEP * 680
    if pullback:
        for n in range(1, 5):                               # closes fall 4 cents a minute: 0.16 below the trend line
            o = base - 0.04 * (n - 1)
            shapes.append((o, o + 0.01, o - 0.06, o - 0.04))
    last_close = shapes[-1][3]
    if trigger:
        shapes.append((last_close, last_close + 0.22, last_close - 0.01, last_close + 0.20))
    else:
        shapes.append((last_close, last_close + 0.01, last_close - 0.01, last_close + 0.005))
    return [{'t': start + 60 * k, 'o': o, 'h': h, 'l': l, 'c': c} for k, (o, h, l, c) in enumerate(shapes)]


def mirror(bars):
    """The same bars upside down around 100, for the SELL side."""
    return [{'t': b['t'], 'o': 200 - b['o'], 'h': 200 - b['l'], 'l': 200 - b['h'], 'c': 200 - b['c']} for b in bars]


@pytest.fixture(autouse=True)
def gold(monkeypatch):
    monkeypatch.setenv('SYMBOLS', 'XAUUSD,EURUSD')
    monkeypatch.setenv('EMA_SYMBOLS', 'XAUUSD')
    monkeypatch.delenv('EMA_MIN_RR', raising=False)


def test_sessions_follow_london_and_new_york_hours():
    cfg = EmaConfig()
    assert in_session(int(dt.datetime(2026, 9, 9, 8, 0, tzinfo=UTC).timestamp()), cfg)         # 09:00 London
    assert in_session(int(dt.datetime(2026, 9, 9, 20, 30, tzinfo=UTC).timestamp()), cfg)       # 16:30 New York
    assert not in_session(int(dt.datetime(2026, 9, 9, 23, 0, tzinfo=UTC).timestamp()), cfg)    # 19:00 New York
    assert not in_session(int(dt.datetime(2026, 9, 12, 10, 0, tzinfo=UTC).timestamp()), cfg)   # Saturday
    assert in_session(int(dt.datetime(2026, 9, 12, 10, 0, tzinfo=UTC).timestamp()), EmaConfig(crypto=True))


def test_buy_setup_after_a_dip_into_ema20_passes_the_analyzer():
    bars = session()
    setups = detect('XAUUSD', bars, EmaConfig())
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'BUY_SETUP' and body['model'] == 'ema' and body['timeframe'] == '1m'
    assert body['bar_time'] == bars[-1]['t'] + 60                           # the trigger candle's close
    assert body['entry'] == body['price'] == pytest.approx(bars[-1]['c'])
    assert body['ema20'] > body['ema50'] > body['ema200']
    assert body['swing_low'] == pytest.approx(min(b['l'] for b in bars[-6:]))
    risk = body['entry'] - body['stop']
    assert body['stop'] < body['swing_low']
    assert 1.0 * body['atr'] <= risk <= 4.0 * body['atr']
    assert body['target_liquidity'] == pytest.approx(body['entry'] + 1.5 * risk)
    signal = Signal.model_validate(body)
    assert ema_rules(signal) == []
    plan = trade_plan(signal)
    assert plan['entry'] == body['price'] and plan['targets'][0][0] == 1.5


def test_sell_setup_is_the_mirror_image():
    setups = detect('XAUUSD', mirror(session()), EmaConfig())
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'SELL_SETUP'
    assert body['ema20'] < body['ema50'] < body['ema200']
    assert body['stop'] > body['swing_high'] > body['entry'] > body['target_liquidity']
    assert ema_rules(Signal.model_validate(body)) == []


def test_no_setup_without_a_pullback_or_a_resuming_candle():
    assert detect('XAUUSD', session(pullback=False), EmaConfig()) == []
    assert detect('XAUUSD', session(trigger=False), EmaConfig()) == []


def test_no_setup_outside_sessions_and_the_analyzer_agrees():
    saturday = int(dt.datetime(2026, 9, 12, 8, 0, tzinfo=UTC).timestamp())
    assert detect('XAUUSD', session(start=saturday), EmaConfig()) == []
    body = detect('XAUUSD', session(start=saturday), EmaConfig(crypto=True))[0]
    assert 'outside_london_or_new_york_session' in ema_rules(Signal.model_validate(body))


def test_analyzer_rejects_a_disabled_symbol_and_a_short_target():
    body = detect('XAUUSD', session(), EmaConfig())[0]
    assert ema_rules(Signal.model_validate({**body, 'symbol': 'EURUSD'})) == ['ema_not_enabled_for_symbol']
    short = {**body, 'target_liquidity': body['entry'] + 0.5 * (body['entry'] - body['stop'])}
    assert ema_rules(Signal.model_validate(short)) == ['target_too_close']
    with pytest.raises(ValueError):
        Signal.model_validate({**body, 'timeframe': '5m'})
