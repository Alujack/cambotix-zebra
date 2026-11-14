"""Candle Range Theory (CRT) detector: a higher-timeframe candle's range, a sweep of one side that closes back inside.

    C1  range candle: its high and low are the range.
    C2  next candle: trades beyond ONE extreme of C1, leaves the other untouched, and closes back inside C1.
        Bearish CRT = C2 swept C1's high; bullish CRT = C2 swept C1's low.
    C3  distribution: price is expected to travel to C1's opposite extreme.

Higher-timeframe candles are built from closed M15 bars in New York time with the 17:00 roll (forex convention), so
H4 candles open at 17, 21, 1, 5, 9 and 13 New York - the "1am / 5am / 9am" candles CRT traders refer to. Broker H4
bars (UTC on Exness) do not line up with those times, which is why they are rebuilt here.

The plan is the one that held up in scripts/backtest.py (see README): market entry at C2's close, stop beyond C2's
wick plus stop_buffer_atr x 15m ATR, single target at C1's opposite extreme, minimum reward:risk min_rr.

detect() returns analyzer payloads (app.domain.Signal, model 'crt'), so the live feeder and the backtest post exactly
what the analyzer validates with crt_rules. Standard library only; bars are dicts t,o,h,l,c, t = open time UTC seconds.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
M15 = 900
TIMEFRAMES = {1: '1h', 4: '4h', 24: '1d'}


@dataclass
class CrtConfig:
    htf_hours: int = 4                  # 4 = H4, 24 = D1, 1 = H1 (New York 17:00 roll)
    key_times: tuple[int, ...] = ()     # allowed New York open hours of C2, e.g. (1, 5, 9); empty = every candle
    min_rr: float = 2.0                 # reward:risk to the target (the analyzer re-checks CRT_MIN_RR)
    stop_buffer_atr: float = 0.1
    min_risk_atr: float = 0.3           # skip stops tighter than spread noise (the analyzer re-checks)
    crypto: bool = False                # trade weekends


@dataclass
class Candle:
    start: int                          # UTC seconds of the slot's first M15 bar
    end: int                            # UTC close time of the slot's last M15 bar
    ny_hour: int                        # New York hour the slot opens at (by its slot, not its first bar)
    o: float
    h: float
    l: float
    c: float


def slot(stamp: int, hours: int) -> tuple[dt.date, int]:
    """(trading day, slot index) of a bar in New York time with the 17:00 roll."""
    shifted = dt.datetime.fromtimestamp(stamp, dt.timezone.utc).astimezone(NY) + dt.timedelta(hours=7)
    return shifted.date(), shifted.hour // hours


def slot_closes(stamp: int, hours: int) -> bool:
    """True when the M15 bar opening at `stamp` is the last bar of its HTF slot (its close ends the candle)."""
    return slot(stamp, hours) != slot(stamp + M15, hours)


def htf_candles(m15: list[dict], hours: int) -> list[Candle]:
    out: list[Candle] = []
    key = None
    for bar in m15:
        k = slot(bar['t'], hours)
        if k != key:
            key = k
            out.append(Candle(bar['t'], bar['t'] + M15, (k[1] * hours - 7) % 24, bar['o'], bar['h'], bar['l'], bar['c']))
        else:
            cur = out[-1]
            cur.h, cur.l, cur.c, cur.end = max(cur.h, bar['h']), min(cur.l, bar['l']), bar['c'], bar['t'] + M15
    return out


def atr_series(m15: list[dict], n: int = 14) -> dict[int, float]:
    """Wilder ATR keyed by bar close time."""
    out, prev_close, value = {}, None, None
    for bar in m15:
        tr = bar['h'] - bar['l'] if prev_close is None else max(bar['h'] - bar['l'], abs(bar['h'] - prev_close),
                                                                abs(bar['l'] - prev_close))
        value = tr if value is None else (value * (n - 1) + tr) / n
        out[bar['t'] + M15] = value
        prev_close = bar['c']
    return out


def detect(symbol: str, m15: list[dict], cfg: CrtConfig) -> list[dict]:
    """Every CRT setup in closed M15 history, one analyzer payload per sweep candle (C2) close.
    The last candle counts only when its final M15 bar is present, so a still-forming candle never signals."""
    candles = htf_candles(m15, cfg.htf_hours)
    if m15 and not slot_closes(m15[-1]['t'], cfg.htf_hours):
        candles = candles[:-1]
    atr = atr_series(m15)
    timeframe = TIMEFRAMES[cfg.htf_hours]
    setups = []
    for c1, c2 in zip(candles, candles[1:]):
        if cfg.key_times and c2.ny_hour not in cfg.key_times:
            continue
        # Both candles must be weekday sessions, judged by each one's last minute (a Monday D1 candle opens Sunday
        # 17:00 New York). This also drops the thin Sunday-evening open as a range candle.
        if not cfg.crypto and any(dt.datetime.fromtimestamp(c.end - 1, dt.timezone.utc).astimezone(NY).weekday() >= 5
                                  for c in (c1, c2)):
            continue
        swept_high, swept_low = c2.h > c1.h, c2.l < c1.l
        if swept_high == swept_low:                      # inside bar, or both sides taken
            continue
        if not c1.l < c2.c < c1.h:                       # must close back inside the range
            continue
        sell = swept_high
        a = atr.get(c2.end)
        if not a:
            continue
        stop = (c2.h + cfg.stop_buffer_atr * a) if sell else (c2.l - cfg.stop_buffer_atr * a)
        entry, target = c2.c, (c1.l if sell else c1.h)
        risk = abs(entry - stop)
        if risk < cfg.min_risk_atr * a or abs(target - entry) / risk < cfg.min_rr:
            continue
        direction = 'SELL_SETUP' if sell else 'BUY_SETUP'
        number = lambda value: round(float(value), 8)
        setups.append({
            'event_id': f'{symbol}-{timeframe}-crt-{c2.end}-{direction}', 'symbol': symbol, 'timeframe': timeframe,
            'bar_time': c2.end, 'signal': direction, 'model': 'crt', 'price': number(c2.c), 'atr': number(a),
            'range_high': number(c1.h), 'range_low': number(c1.l), 'sweep_level': number(c2.h if sell else c2.l),
            'entry': number(entry), 'stop': number(stop), 'target_liquidity': number(target),
            'swept_name': 'range high' if sell else 'range low', 'target_name': 'range low' if sell else 'range high',
        })
    return setups
