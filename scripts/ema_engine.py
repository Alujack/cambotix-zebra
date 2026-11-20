"""EMA pullback scalper on M1: the EMA 20/50/200 stack gives the trend, a pullback into EMA20 gives the entry.

    trend      close > EMA20 > EMA50 > EMA200 on the trigger candle (reversed for a sell).
    pullback   within the last pullback_bars candles at least one low touched or crossed EMA20, and the pullback
               low (the lowest low of those candles and the trigger) stayed above EMA200: a dip in a trend, not a
               trend change.
    trigger    a bullish M1 close (c > o) above EMA20 that also breaks the previous candle's high: the first candle
               that resumes the trend after the dip.
    plan       market entry at the trigger close, stop below the pullback low minus stop_buffer_atr x ATR(14, M1),
               one target at min_rr x risk. The stop must be between min_risk_atr and max_risk_atr: tighter is spread
               noise on a 1-minute chart, wider is no longer a scalp.
    session    London or New York hours (08:00-17:00 local, weekdays), the hours the classic model also trades.
    cooldown   after a setup, no further setup in the same direction for cooldown_bars candles.

detect() replays closed M1 bars and returns analyzer payloads (app.domain.Signal, model 'ema'), one per setup, keyed
by the close time of the trigger candle; the feeder posts only the one that just closed. Standard library only; bars
are dicts t,o,h,l,c with t = open time in UTC seconds. EMAs use the pandas ewm(adjust=False) recursion, as the
classic model does, and the first warmup_bars candles never signal so a 1500-bar live window and a multi-year
backtest see the same EMA values.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

M1 = 60
SESSIONS = (('Europe/London', 8, 17), ('America/New_York', 8, 17))


@dataclass
class EmaConfig:
    fast: int = 20
    mid: int = 50
    slow: int = 200
    pullback_bars: int = 5            # candles before the trigger in which EMA20 must have been touched
    min_rr: float = 1.5               # the single target, in R (the analyzer re-checks EMA_MIN_RR)
    stop_buffer_atr: float = 0.2
    min_risk_atr: float = 1.0         # the analyzer re-checks a 0.5 ATR floor
    max_risk_atr: float = 4.0
    cooldown_bars: int = 10
    warmup_bars: int = 600            # 3 x EMA200: the initial value's weight is below 1e-5 by then
    crypto: bool = False              # trade around the clock


def in_session(stamp: int, cfg: EmaConfig) -> bool:
    """True when the M1 bar opening at `stamp` falls in London or New York hours on a weekday."""
    if cfg.crypto:
        return True
    moment = dt.datetime.fromtimestamp(stamp, dt.timezone.utc)
    for zone, start, end in SESSIONS:
        local = moment.astimezone(ZoneInfo(zone))
        if local.weekday() < 5 and start <= local.hour < end:
            return True
    return False


def ema_series(values: list[float], n: int) -> list[float]:
    alpha, out, state = 2 / (n + 1), [], None
    for value in values:
        state = value if state is None else alpha * value + (1 - alpha) * state
        out.append(state)
    return out


def atr_series(bars: list[dict], n: int = 14) -> list[float]:
    out, prev_close, value = [], None, None
    for bar in bars:
        tr = bar['h'] - bar['l'] if prev_close is None else max(bar['h'] - bar['l'], abs(bar['h'] - prev_close),
                                                                abs(bar['l'] - prev_close))
        value = tr if value is None else (value * (n - 1) + tr) / n
        out.append(value)
        prev_close = bar['c']
    return out


def detect(symbol: str, m1: list[dict], cfg: EmaConfig) -> list[dict]:
    """Every EMA pullback setup in closed M1 history, as analyzer payloads in time order."""
    close = [bar['c'] for bar in m1]
    fast, mid, slow = ema_series(close, cfg.fast), ema_series(close, cfg.mid), ema_series(close, cfg.slow)
    atr = atr_series(m1)
    setups: list[dict] = []
    last: dict[int, int] = {1: -10 ** 9, -1: -10 ** 9}     # direction -> index of the last setup
    for i in range(max(cfg.warmup_bars, cfg.pullback_bars + 1), len(m1)):
        bar, prev = m1[i], m1[i - 1]
        if not atr[i] or not in_session(bar['t'], cfg):
            continue
        window = m1[i - cfg.pullback_bars:i]
        for direction in (1, -1):
            if i - last[direction] <= cfg.cooldown_bars:
                continue
            if direction == 1:
                stacked = bar['c'] > fast[i] > mid[i] > slow[i] and bar['c'] > bar['o'] and bar['c'] > prev['h']
                touched = any(m1[k]['l'] <= fast[k] for k in range(i - cfg.pullback_bars, i))
                extreme = min(b['l'] for b in window + [bar])
                intact = extreme > slow[i]
            else:
                stacked = bar['c'] < fast[i] < mid[i] < slow[i] and bar['c'] < bar['o'] and bar['c'] < prev['l']
                touched = any(m1[k]['h'] >= fast[k] for k in range(i - cfg.pullback_bars, i))
                extreme = max(b['h'] for b in window + [bar])
                intact = extreme < slow[i]
            if not (stacked and touched and intact):
                continue
            stop = extreme - direction * cfg.stop_buffer_atr * atr[i]
            risk = direction * (bar['c'] - stop)
            if not cfg.min_risk_atr * atr[i] <= risk <= cfg.max_risk_atr * atr[i]:
                continue
            last[direction] = i
            setups.append(_payload(symbol, direction, bar, window, fast[i], mid[i], slow[i], atr[i], stop, cfg))
    return setups


def _payload(symbol, direction, bar, window, fast, mid, slow, atr, stop, cfg) -> dict:
    buy = direction == 1
    entry = bar['c']
    target = entry + direction * cfg.min_rr * abs(entry - stop)
    close_time = bar['t'] + M1
    signal = 'BUY_SETUP' if buy else 'SELL_SETUP'
    number = lambda value: round(float(value), 8)
    candles = window + [bar]
    return {
        'event_id': f'{symbol}-1m-ema-{close_time}-{signal}', 'symbol': symbol, 'timeframe': '1m',
        'bar_time': close_time, 'signal': signal, 'model': 'ema', 'price': number(entry), 'atr': number(atr),
        'ema20': number(fast), 'ema50': number(mid), 'ema200': number(slow),
        'swing_high': number(max(b['h'] for b in candles)), 'swing_low': number(min(b['l'] for b in candles)),
        'entry': number(entry), 'stop': number(stop), 'target_liquidity': number(target),
        'swept_name': 'EMA20 pullback', 'target_name': f'{cfg.min_rr:g}R',
    }
