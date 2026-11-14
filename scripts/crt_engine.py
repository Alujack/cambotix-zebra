"""Candle Range Theory (CRT) detector: a higher-timeframe candle's range, a sweep of one side that closes back inside.

    C1  range candle: its high and low are the range.
    C2  next candle: trades beyond ONE extreme of C1, leaves the other untouched, and closes back inside C1.
        Bearish CRT = C2 swept C1's high; bullish CRT = C2 swept C1's low.
    C3  distribution: price is expected to travel to C1's 50% and then its opposite extreme.

Higher-timeframe candles are built from closed M15 bars in New York time with the 17:00 roll (forex convention), so
H4 candles open at 17, 21, 1, 5, 9 and 13 New York - the "1am / 5am / 9am" candles CRT traders refer to. Broker H4
bars (UTC on Exness) do not line up with those times, which is why they are rebuilt here.

Entries (CrtConfig.entry):
    close   market order at C2's close (the signal bar).
    level   limit order back at the swept C1 extreme, valid for one HTF candle.
Stop beyond C2's wick plus stop_buffer_atr x M15 ATR. Targets (CrtConfig.target):
    opposite  TP1 = C1's opposite extreme.
    mid       TP1 = C1's 50% (when still ahead of entry), TP2 = the opposite extreme.

Standard library only; bars are dicts t,o,h,l,c with t = open time in UTC seconds.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
M15 = 900


@dataclass
class CrtConfig:
    htf_hours: int = 4                  # 4 = H4, 24 = D1, 1 = H1 (New York 17:00 roll)
    key_times: tuple[int, ...] = ()     # allowed New York open hours of C2, e.g. (1, 5, 9); empty = every candle
    entry: str = 'close'                # 'close' or 'level'
    target: str = 'opposite'            # 'opposite' or 'mid'
    min_rr: float = 1.0                 # reward:risk to TP1
    stop_buffer_atr: float = 0.1
    min_risk_atr: float = 0.3           # skip stops tighter than spread noise
    max_hold_candles: int = 3           # exit after this many HTF candles from the signal
    crypto: bool = False                # trade weekends


@dataclass
class Candle:
    start: int                          # UTC seconds of the first M15 bar
    end: int                            # UTC close time of the last M15 bar
    ny_hour: int                        # New York hour the candle opens at (by its slot, not its first bar)
    o: float
    h: float
    l: float
    c: float


def slot(stamp: int, hours: int) -> tuple[dt.date, int]:
    """(trading day, slot index) of a bar in New York time with the 17:00 roll."""
    shifted = dt.datetime.fromtimestamp(stamp, dt.timezone.utc).astimezone(NY) + dt.timedelta(hours=7)
    return shifted.date(), shifted.hour // hours


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
    """Every CRT setup in the history, as plain dicts ready for a plan (one per C2 close)."""
    candles = htf_candles(m15, cfg.htf_hours)
    atr = atr_series(m15)
    period = cfg.htf_hours * 3600
    setups = []
    for c1, c2 in zip(candles, candles[1:]):
        if cfg.key_times and c2.ny_hour not in cfg.key_times:
            continue
        if not cfg.crypto and dt.datetime.fromtimestamp(c2.start, dt.timezone.utc).astimezone(NY).weekday() >= 5:
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
        sign = -1 if sell else 1
        stop = (c2.h + cfg.stop_buffer_atr * a) if sell else (c2.l - cfg.stop_buffer_atr * a)
        entry = c2.c if cfg.entry == 'close' else (c1.h if sell else c1.l)
        risk = abs(entry - stop)
        if risk < cfg.min_risk_atr * a:
            continue
        mid, far = (c1.h + c1.l) / 2, (c1.l if sell else c1.h)
        targets = []
        if cfg.target == 'mid' and sign * (mid - entry) > 0:
            targets.append((mid, 'C1 50%'))
        targets.append((far, 'C1 low' if sell else 'C1 high'))
        tp1_r = sign * (targets[0][0] - entry) / risk
        if tp1_r < cfg.min_rr:
            continue
        setups.append({
            'symbol': symbol, 'model': 'crt', 'direction': 'SELL' if sell else 'BUY', 'bar_time': c2.end,
            'published_at': c2.end, 'entry_type': 'market' if cfg.entry == 'close' else 'limit',
            'entry': round(entry, 8), 'stop': round(stop, 8),
            'targets': [[round(sign * (price - entry) / risk, 2), round(price, 8), note] for price, note in targets],
            'entry_expiry_minutes': cfg.htf_hours * 60, 'max_hold_minutes': cfg.max_hold_candles * cfg.htf_hours * 60,
            'session': f'C2 {c2.ny_hour:02d}:00 NY', 'atr': a, 'price': c2.c,
            'c1_high': c1.h, 'c1_low': c1.l, 'c2_high': c2.h, 'c2_low': c2.l, 'swept': 'C1 high' if sell else 'C1 low',
            'htf': f'H{cfg.htf_hours}' if cfg.htf_hours < 24 else 'D1', 'c2_start': c2.start, 'period': period,
        })
    return setups
