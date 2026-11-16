"""ICT 2022-style detector on M5: a killzone liquidity sweep, a market structure shift, then a limit order at the FVG.

    pools     previous day high/low (New York 17:00 roll), Asia high/low (20:00-24:00 New York), London high/low
              (02:00-05:00 New York). Each pool counts once; one traded through outside a killzone is spent.
    sweep     inside a killzone (London 02:00-05:00, NY AM 08:30-11:00 New York, weekdays) price trades beyond a fresh
              pool: a high swept arms a SELL, a low swept arms a BUY. Deeper wicks move the sweep extreme.
    MSS       within 3 hours of the extreme, the first M5 close back beyond the last 2/2 pivot formed before it.
    FVG       the latest 3-candle fair value gap (>= 0.1 ATR) in the leg from the extreme to the MSS candle (+1 candle).
    plan      limit at the FVG's near edge, stop beyond the sweep extreme + stop_buffer_atr x ATR(14, M5), one target
              at min_rr x risk. The analyzer cancels an unfilled limit after ICT_ENTRY_EXPIRY_MINUTES.

These rules are the ones fixed before the research backtest (README "ICT model"): EURUSD over Nov 2023 - Nov 2026,
+22.8R on 192 trades, PF 1.22, years +17.9 / -5.3 / +11.2R. Gold lost money with the same rules, so the analyzer only
accepts ICT on the symbols in ICT_SYMBOLS.

detect() replays closed M5 bars and returns analyzer payloads (app.domain.Signal, model 'ict'), one per setup, keyed
by the close time of the candle that completed it; the feeder posts only the one that just closed. Standard library
only; bars are dicts t,o,h,l,c with t = open time in UTC seconds.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
M5 = 300
KILLZONES = {'London': (2 * 60, 5 * 60), 'NY AM': (8 * 60 + 30, 11 * 60)}   # New York minutes of the day
ASIA_START, LONDON = 20 * 60, (2 * 60, 5 * 60)


@dataclass
class IctConfig:
    killzones: tuple[str, ...] = ('London', 'NY AM')
    min_rr: float = 2.0               # the single target, in R (the analyzer re-checks ICT_MIN_RR)
    stop_buffer_atr: float = 0.1
    min_risk_atr: float = 0.3         # skip stops tighter than spread noise (the analyzer re-checks)
    min_fvg_atr: float = 0.1
    mss_wait_bars: int = 36           # 3 hours of M5 from the sweep extreme to the structure shift
    pivot_age_bars: int = 48          # the pivot that must break formed at most 4 hours before the extreme
    crypto: bool = False              # trade weekends


def killzone(stamp: int, cfg: IctConfig) -> str | None:
    """Killzone the M5 bar opening at `stamp` belongs to, or None."""
    local = dt.datetime.fromtimestamp(stamp, dt.timezone.utc).astimezone(NY)
    if not cfg.crypto and local.weekday() >= 5:
        return None
    minute = local.hour * 60 + local.minute
    return next((name for name in cfg.killzones if KILLZONES[name][0] <= minute < KILLZONES[name][1]), None)


def atr_series(bars: list[dict], n: int = 14) -> list[float]:
    out, prev_close, value = [], None, None
    for bar in bars:
        tr = bar['h'] - bar['l'] if prev_close is None else max(bar['h'] - bar['l'], abs(bar['h'] - prev_close),
                                                                abs(bar['l'] - prev_close))
        value = tr if value is None else (value * (n - 1) + tr) / n
        out.append(value)
        prev_close = bar['c']
    return out


def detect(symbol: str, m5: list[dict], cfg: IctConfig) -> list[dict]:
    """Every ICT setup in closed M5 history, as analyzer payloads in time order."""
    atr = atr_series(m5)
    setups: list[dict] = []
    pools: dict[str, list] = {}       # name -> [level, side (+1 high / -1 low), fresh]
    day = day_high = day_low = None
    asia = london = None              # [high, low] while the session is forming
    prev_minute = None
    pivot_highs: list[tuple[int, float]] = []
    pivot_lows: list[tuple[int, float]] = []
    armed: dict[int, dict | None] = {1: None, -1: None}
    for i, bar in enumerate(m5):
        t, h, l, c = bar['t'], bar['h'], bar['l'], bar['c']
        local = dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(NY)
        minute = local.hour * 60 + local.minute
        trading_day = (local + dt.timedelta(hours=7)).date()
        if trading_day != day:
            if day is not None:
                pools['PDH'], pools['PDL'] = [day_high, 1, True], [day_low, -1, True]
            for name in ('Asia high', 'Asia low', 'London high', 'London low'):
                pools.pop(name, None)
            day, day_high, day_low = trading_day, h, l
        if minute >= ASIA_START:
            fresh_session = asia is None or prev_minute is None or prev_minute < ASIA_START
            asia = [h, l] if fresh_session else [max(asia[0], h), min(asia[1], l)]
        elif asia is not None and prev_minute is not None and prev_minute >= ASIA_START:
            pools['Asia high'], pools['Asia low'] = [asia[0], 1, True], [asia[1], -1, True]
            asia = None
        if LONDON[0] <= minute < LONDON[1]:
            london = [h, l] if london is None else [max(london[0], h), min(london[1], l)]
        elif london is not None and minute >= LONDON[1]:
            pools['London high'], pools['London low'] = [london[0], 1, True], [london[1], -1, True]
            london = None
        prev_minute = minute

        # A 2/2 pivot is known two bars after its centre.
        j = i - 2
        if j >= 2:
            if all(m5[j]['h'] > m5[k]['h'] for k in range(j - 2, i + 1) if k != j):
                pivot_highs.append((j, m5[j]['h']))
            if all(m5[j]['l'] < m5[k]['l'] for k in range(j - 2, i + 1) if k != j):
                pivot_lows.append((j, m5[j]['l']))

        zone = killzone(t, cfg)
        for name, pool in pools.items():
            level, side, fresh = pool
            if fresh and ((side == 1 and h > level) or (side == -1 and l < level)):
                pool[2] = False
                if zone:
                    direction, extreme = -side, (h if side == 1 else l)
                    current = armed[direction]
                    if (current is None or (direction == 1 and extreme < current['extreme'])
                            or (direction == -1 and extreme > current['extreme'])):
                        armed[direction] = {'extreme': extreme, 'extreme_i': i, 'name': name, 'mss': None, 'mss_i': None}
        if not zone:
            armed = {1: None, -1: None}
        else:
            for direction in (1, -1):
                setup = _advance(armed, direction, i, m5, atr, pivot_highs, pivot_lows, cfg)
                body = _payload(symbol, setup, bar, atr[i], zone, cfg) if setup else None
                if body:
                    setups.append(body)
        day_high, day_low = max(day_high, h), min(day_low, l)
    return setups


def _advance(armed, direction, i, m5, atr, pivot_highs, pivot_lows, cfg) -> dict | None:
    """Move one armed sweep forward by bar i; returns the finished setup when its FVG appears."""
    state = armed[direction]
    if state is None:
        return None
    bar = m5[i]
    if state['mss_i'] is None:
        if (direction == 1 and bar['l'] < state['extreme']) or (direction == -1 and bar['h'] > state['extreme']):
            state['extreme'], state['extreme_i'] = (bar['l'] if direction == 1 else bar['h']), i
        if i - state['extreme_i'] > cfg.mss_wait_bars:
            armed[direction] = None
            return None
        pivots = pivot_highs if direction == 1 else pivot_lows
        prior = [p for p in pivots if p[0] < state['extreme_i'] and state['extreme_i'] - p[0] <= cfg.pivot_age_bars]
        if not prior:
            return None
        level, previous_close = prior[-1][1], m5[i - 1]['c']
        if not ((direction == 1 and bar['c'] > level >= previous_close)
                or (direction == -1 and bar['c'] < level <= previous_close)):
            return None
        state['mss'], state['mss_i'] = level, i
    if i > state['mss_i'] + 1:            # the FVG must exist by the candle after the shift
        armed[direction] = None
        return None
    for k in range(i, state['extreme_i'] + 1, -1):
        first, third = m5[k - 2], m5[k]
        if direction == 1 and third['l'] > first['h'] and third['l'] - first['h'] >= cfg.min_fvg_atr * atr[k]:
            armed[direction] = None
            return {**state, 'direction': 1, 'fvg_high': third['l'], 'fvg_low': first['h']}
        if direction == -1 and third['h'] < first['l'] and first['l'] - third['h'] >= cfg.min_fvg_atr * atr[k]:
            armed[direction] = None
            return {**state, 'direction': -1, 'fvg_high': first['l'], 'fvg_low': third['h']}
    return None


def _payload(symbol: str, setup: dict, bar: dict, atr: float, zone: str, cfg: IctConfig) -> dict | None:
    buy = setup['direction'] == 1
    entry = setup['fvg_high'] if buy else setup['fvg_low']          # the near edge: first price a retrace reaches
    stop = setup['extreme'] - cfg.stop_buffer_atr * atr if buy else setup['extreme'] + cfg.stop_buffer_atr * atr
    risk = abs(entry - stop)
    if risk < cfg.min_risk_atr * atr:
        return None
    target = entry + (1 if buy else -1) * cfg.min_rr * risk
    close_time = bar['t'] + M5
    direction = 'BUY_SETUP' if buy else 'SELL_SETUP'
    number = lambda value: round(float(value), 8)
    return {
        'event_id': f'{symbol}-5m-ict-{close_time}-{direction}', 'symbol': symbol, 'timeframe': '5m',
        'bar_time': close_time, 'signal': direction, 'model': 'ict', 'price': number(bar['c']), 'atr': number(atr),
        'sweep_level': number(setup['extreme']), 'mss_level': number(setup['mss']),
        'fvg_high': number(setup['fvg_high']), 'fvg_low': number(setup['fvg_low']),
        'entry': number(entry), 'stop': number(stop), 'target_liquidity': number(target),
        'swept_name': setup['name'], 'target_name': f'{cfg.min_rr:g}R',
    }
