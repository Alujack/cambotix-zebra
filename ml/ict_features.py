"""Broad ICT candidates on M5 and the features the model learns from.

A candidate is the ICT 2022 sequence, detected the same way as scripts/ict_engine.py but at any hour of the day and
from more liquidity pools, so the model sees thousands of setups instead of a few hundred:

    pools     previous day high/low (New York 17:00 roll), Asia high/low (20:00-24:00 NY), London high/low
              (02:00-05:00), NY AM high/low (08:30-11:00), and M5 swing highs/lows (a 6/6 fractal, known six bars
              after its pivot, fresh for `swing_life_bars`). A pool is spent once price trades through it.
    sweep     price trades beyond a fresh pool: a high swept arms a SELL, a low swept arms a BUY. Deeper wicks move
              the sweep extreme. The most significant pool taken names the sweep (day, London, Asia, NY AM, swing),
              within one candle and across the run. Weekend bars never arm (crypto excepted).
    MSS       within `mss_wait_bars` of the extreme, the first M5 close back beyond the last 2/2 pivot that formed
              before the extreme (at most `pivot_age_bars` earlier).
    FVG       the latest 3-candle fair value gap (>= min_fvg_atr x ATR) in the leg, found by the candle after the MSS.
    plan      limit at the FVG's near edge, stop beyond the extreme + stop_buffer_atr x ATR(14), one target at rr x
              risk. Identical geometry to the ICT engine, so labels from the grader are directly comparable.

The killzone, the pool type, the session and everything else that ict_engine uses as a hard filter become features
here, and the model decides which combinations matter. Every feature at bar i uses bars 0..i only (tests check that
truncating or rewriting the future never changes a candidate).

Each ICT concept is a small function that tests/test_ict_features.py exercises on its own:

    session_of, in_killzone      New York session clock
    trading_days                 the 17:00 New York day roll
    pivots                       swing highs/lows (strict w/w fractals)
    SessionRange                 a forming session range that becomes two pools when its window ends
    find_fvg, count_fvgs         fair value gaps in a leg
    order_block                  the last opposite candle before the displacement
    retracement                  where the entry sits in the leg (OTE is 62-79%)
    detect                       the sweep -> MSS -> FVG state machine that ties them together

Check the candidates of a saved history year by year with ml/check_candidates.py.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ml.data import Bars, CRYPTO, asset_class

M5 = 300
ASIA = (20 * 60, 24 * 60)
LONDON = (2 * 60, 5 * 60)
NY_AM = (8 * 60 + 30, 11 * 60)
KILLZONES = (LONDON, NY_AM)

# Pool kinds, most significant first: on a tie (one candle sweeping several pools) the first one names the sweep.
POOL_KINDS = ('day', 'london', 'asia', 'nyam', 'swing')
SESSIONS = ('asia', 'london_kz', 'london_mid', 'ny_am_kz', 'ny_mid', 'ny_pm', 'close')
ASSETS = ('fx', 'metal', 'index', 'crypto')

FEATURES = (
    # setup identity
    'direction', 'pool_kind', 'n_pools_swept', 'pool_age_bars', 'in_killzone', 'session_sweep', 'session_now',
    'ny_hour', 'weekday', 'asset',
    # sweep
    'sweep_depth_atr', 'sweep_wick_ratio', 'bars_sweep_to_mss', 'bars_extreme_to_now',
    # displacement and structure shift
    'mss_body_atr', 'mss_range_atr', 'mss_body_ratio', 'mss_close_beyond_atr', 'leg_atr', 'leg_max_body_atr',
    'leg_bars',
    # fair value gap, order block, breaker, OTE
    'fvg_size_atr', 'fvg_count_leg', 'fvg_age_bars', 'ob_overlap', 'ob_dist_atr', 'breaker_overlap', 'ote_fib',
    'in_ote',
    # plan geometry and costs
    'risk_atr', 'spread_risk', 'spread_atr', 'entry_dist_atr', 'opp_pool_r', 'target_before_pool',
    # volatility regime
    'atr_pct', 'atr_ratio_day', 'atr_ratio_week',
    # higher-timeframe bias (M5 EMAs spanning about H1 EMA20 / H1 EMA50 / H4 EMA50)
    'ema_h1_20_atr', 'ema_h1_50_atr', 'ema_h4_50_atr', 'ema_h1_50_slope_atr',
    # premium / discount and daily context
    'pd_prev_day', 'pd_week', 'day_move_atr', 'day_range_atr', 'asia_range_atr',
    # momentum into the setup
    'ret_1h_atr', 'ret_4h_atr', 'ret_1d_atr',
)
CATEGORICAL = ('pool_kind', 'session_sweep', 'session_now', 'weekday', 'asset')
# Features that are NaN when what they measure does not exist: no candle against the trade in the leg, no pool
# ahead of the entry, no finished Asia session yet today, a zero-range candle, or (only inside the warm-up) not
# enough history. Every other feature is always a finite number.
MAY_BE_MISSING = frozenset({
    'ob_dist_atr', 'opp_pool_r', 'target_before_pool', 'asia_range_atr', 'sweep_wick_ratio', 'mss_body_ratio',
    'pd_prev_day', 'pd_week', 'atr_ratio_day', 'atr_ratio_week', 'ema_h1_50_slope_atr', 'ret_1h_atr', 'ret_4h_atr',
    'ret_1d_atr',
})


@dataclass
class CandidateConfig:
    rr: float = 2.0                  # the single target in R (as ICT_MIN_RR)
    stop_buffer_atr: float = 0.1
    min_risk_atr: float = 0.3        # skip stops tighter than spread noise (as the analyzer)
    min_fvg_atr: float = 0.1
    mss_wait_bars: int = 36          # 3 hours of M5 from the sweep extreme to the structure shift
    pivot_age_bars: int = 48         # the pivot that must break formed at most 4 hours before the extreme
    swing_window: int = 6            # an M5 swing pool is a 6/6 fractal
    swing_life_bars: int = 288       # and stays a pool for one day
    warmup_bars: int = 2400          # the H4 EMA50 proxy needs about eight trading days
    crypto: bool = False             # trade weekends


def session_of(minute: int) -> int:
    if minute >= ASIA[0] or minute < LONDON[0]:
        return 0
    if minute < LONDON[1]:
        return 1
    if minute < NY_AM[0]:
        return 2
    if minute < NY_AM[1]:
        return 3
    if minute < 13 * 60 + 30:
        return 4
    if minute < 16 * 60:
        return 5
    return 6


def in_killzone(minute: int, weekday: int) -> bool:
    """London or NY AM killzone on a weekday (New York minute of the day and weekday), as scripts/ict_engine.py."""
    return weekday < 5 and any(start <= minute < end for start, end in KILLZONES)


def trading_days(t: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For bar open times in UTC seconds: New York minute of the day, New York weekday and a trading-day number
    that changes at 17:00 New York (so Sunday evening already belongs to Monday)."""
    local = pd.to_datetime(np.asarray(t, dtype=np.int64), unit='s', utc=True).tz_convert('America/New_York')
    minute = (local.hour * 60 + local.minute).to_numpy()
    # Whole days since 1970 of the local calendar date. Going through datetime64[D] keeps this independent of
    # the index resolution: pandas 2 stores nanoseconds, pandas 3 seconds, and dividing asi8 by a fixed number
    # of nanoseconds silently gave every bar the same day on pandas 3.
    wall_clock = local.tz_localize(None).to_numpy().astype('datetime64[s]')
    day = (wall_clock + np.timedelta64(7, 'h')).astype('datetime64[D]').astype(np.int64)
    return minute, local.day_of_week.to_numpy(), day


def pivots(high: np.ndarray, low: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """Strict w/w fractals at their centre index (known w bars later). Equal highs or lows make no pivot."""
    n = len(high)
    ph, pl = np.zeros(n, bool), np.zeros(n, bool)
    if n < 2 * w + 1:
        return ph, pl
    ph[w:n - w] = True
    pl[w:n - w] = True
    for k in range(1, w + 1):
        ph[w:n - w] &= (high[w:n - w] > high[w - k:n - w - k]) & (high[w:n - w] > high[w + k:n - w + k])
        pl[w:n - w] &= (low[w:n - w] < low[w - k:n - w - k]) & (low[w:n - w] < low[w + k:n - w + k])
    return ph, pl


def find_fvg(h: np.ndarray, l: np.ndarray, atr: np.ndarray, direction: int, first: int, last: int,
             min_atr: float = 0.0) -> tuple[int, float, float] | None:
    """The latest fair value gap whose three candles all lie in first..last, as (index of its third candle, low,
    high). Bullish (direction 1): the third candle's low is above the first candle's high. Bearish (-1): the third
    candle's high is below the first candle's low. Gaps smaller than min_atr x ATR at the third candle are ignored."""
    for k in range(last, first + 1, -1):
        if direction == 1 and l[k] > h[k - 2] and l[k] - h[k - 2] >= min_atr * atr[k]:
            return k, float(h[k - 2]), float(l[k])
        if direction == -1 and h[k] < l[k - 2] and l[k - 2] - h[k] >= min_atr * atr[k]:
            return k, float(h[k]), float(l[k - 2])
    return None


def count_fvgs(h: np.ndarray, l: np.ndarray, direction: int, first: int, last: int) -> int:
    """Fair value gaps of any size in the trade's direction whose three candles lie in first..last."""
    if last - first < 2:
        return 0
    third, one = slice(first + 2, last + 1), slice(first, last - 1)
    return int(np.sum(l[third] > h[one]) if direction == 1 else np.sum(h[third] < l[one]))


def order_block(o: np.ndarray, h: np.ndarray, l: np.ndarray, c: np.ndarray, direction: int, first: int,
                last: int) -> tuple[int, float, float] | None:
    """The last candle in first..last that closed against the trade (a down candle for a BUY), as (index, low,
    high): the order block the displacement left behind. None when every candle closed with the trade."""
    for k in range(last, first - 1, -1):
        if (direction == 1 and c[k] < o[k]) or (direction == -1 and c[k] > o[k]):
            return k, float(l[k]), float(h[k])
    return None


def retracement(entry: float, extreme: float, leg_end: float) -> float:
    """How far back into the leg the entry sits: 0 at the leg's end, 1 at the sweep extreme it started from.
    ICT's optimal trade entry is 0.62-0.79. NaN for a leg with no length."""
    span = abs(leg_end - extreme)
    return abs(leg_end - entry) / span if span else math.nan


class SessionRange:
    """High and low of one New York session window while it forms. `update` returns (high, low) once, on the
    first bar after the window; the caller publishes those as liquidity pools. A session that began on an
    earlier trading day (a data gap, a holiday) is dropped instead of being published late."""

    def __init__(self, window: tuple[int, int]):
        self.start, self.end = window
        self.high = self.low = math.nan
        self.day = None
        self.open = False

    def update(self, minute: int, day: int, high: float, low: float) -> tuple[float, float] | None:
        inside = self.start <= minute < self.end
        done = None
        if self.open and (not inside or day != self.day):
            if day == self.day:
                done = (self.high, self.low)
            self.open = False
        if inside:
            if not self.open:
                self.open, self.day, self.high, self.low = True, day, high, low
            else:
                self.high, self.low = max(self.high, high), min(self.low, low)
        return done


def _context(bars: Bars) -> dict:
    """Trailing indicator arrays (each value at i uses bars <= i)."""
    h, l, c = bars.h, bars.l, bars.c
    prev = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    tr[0] = h[0] - l[0]
    s = pd.Series(tr)
    atr = s.ewm(alpha=1 / 14, adjust=False).mean().to_numpy()   # the ict_engine recursion
    a = pd.Series(atr)
    close = pd.Series(c)
    minute, weekday, day_id = trading_days(bars.t)
    ph2, pl2 = pivots(h, l, 2)
    return {
        'atr': atr,
        'atr_day': a.rolling(288, min_periods=50).mean().to_numpy(),
        'atr_week': a.rolling(1440, min_periods=200).mean().to_numpy(),
        'ema240': close.ewm(span=240, adjust=False).mean().to_numpy(),
        'ema600': close.ewm(span=600, adjust=False).mean().to_numpy(),
        'ema2400': close.ewm(span=2400, adjust=False).mean().to_numpy(),
        'week_hi': pd.Series(h).rolling(1440, min_periods=200).max().to_numpy(),
        'week_lo': pd.Series(l).rolling(1440, min_periods=200).min().to_numpy(),
        'minute': minute,
        'weekday': weekday,
        'day_id': day_id,
        'ph2': ph2, 'pl2': pl2,
    }


def detect(symbol: str, bars: Bars, cfg: CandidateConfig | None = None, start_index: int = 0) -> list[dict]:
    """Every candidate in closed M5 history, oldest first. Candidates before `start_index` are not emitted
    (the state is still replayed from bar 0, so live scoring can ask for only the newest bars)."""
    cfg = cfg or CandidateConfig(crypto=symbol.upper() in CRYPTO)
    n = len(bars)
    if n < 10:
        return []
    ctx = _context(bars)
    ph6, pl6 = pivots(bars.h, bars.l, cfg.swing_window)
    t, o, h, l, c, spread = bars.t, bars.o, bars.h, bars.l, bars.c, bars.spread
    atr, minute, weekday, day_id = ctx['atr'], ctx['minute'], ctx['weekday'], ctx['day_id']
    asset = ASSETS.index(asset_class(symbol))

    pools: dict[str, list] = {}       # name -> [level, side (+1 high / -1 low), kind index, created index]
    day = None
    day_open = day_high = day_low = math.nan
    prev_day_high = prev_day_low = math.nan
    sessions = (('Asia', 2, SessionRange(ASIA)), ('London', 1, SessionRange(LONDON)), ('NYAM', 3, SessionRange(NY_AM)))
    asia_range = math.nan
    piv_hi_idx: list[int] = []
    piv_hi_lvl: list[float] = []
    piv_lo_idx: list[int] = []
    piv_lo_lvl: list[float] = []
    armed: dict[int, dict | None] = {1: None, -1: None}
    out: list[dict] = []

    for i in range(n):
        m = int(minute[i])
        tradable = cfg.crypto or weekday[i] < 5
        if day_id[i] != day:
            if day is not None:
                prev_day_high, prev_day_low = day_high, day_low
                pools['PDH'] = [day_high, 1, 0, i]
                pools['PDL'] = [day_low, -1, 0, i]
            for name in ('Asia high', 'Asia low', 'London high', 'London low', 'NYAM high', 'NYAM low'):
                pools.pop(name, None)
            day, day_open, day_high, day_low = day_id[i], o[i], h[i], l[i]
            asia_range = math.nan
        for label, kind, tracker in sessions:
            finished = tracker.update(m, day, h[i], l[i])
            if finished:
                pools[f'{label} high'] = [finished[0], 1, kind, i]
                pools[f'{label} low'] = [finished[1], -1, kind, i]
                if label == 'Asia':
                    asia_range = finished[0] - finished[1]

        j = i - 2
        if j >= 2:
            if ctx['ph2'][j]:
                piv_hi_idx.append(j)
                piv_hi_lvl.append(h[j])
            if ctx['pl2'][j]:
                piv_lo_idx.append(j)
                piv_lo_lvl.append(l[j])
        j = i - cfg.swing_window
        if j >= cfg.swing_window:
            if ph6[j]:
                pools[f'swing high {j}'] = [h[j], 1, 4, i]
            if pl6[j]:
                pools[f'swing low {j}'] = [l[j], -1, 4, i]

        # Sweeps: the most significant pool names the sweep; every pool traded through is spent.
        swept: dict[int, list] = {}
        dead = []
        for name, pool in pools.items():
            level, side, kind, created = pool
            if kind == 4 and i - created > cfg.swing_life_bars:
                dead.append(name)
                continue
            if (side == 1 and h[i] > level) or (side == -1 and l[i] < level):
                dead.append(name)
                if not tradable:
                    continue
                best = swept.get(-side)
                if best is None:
                    swept[-side] = [name, level, kind, created, 1]
                else:
                    best[4] += 1
                    if kind < best[2]:
                        best[:4] = [name, level, kind, created]
        for name in dead:
            pools.pop(name, None)
        for direction, (name, level, kind, created, count) in swept.items():
            extreme = l[i] if direction == 1 else h[i]
            current = armed[direction]
            if current is None or (direction == 1 and extreme < current['extreme']) or \
                    (direction == -1 and extreme > current['extreme']):
                state = {'extreme': extreme, 'extreme_i': i, 'sweep_i': i, 'name': name, 'level': level,
                         'kind': kind, 'created': created, 'count': count, 'mss': None, 'mss_i': None,
                         'pivot_i': None, 'session': session_of(m)}
                if current is not None and current['kind'] < kind:
                    # One run can take several pools on its way: a minor pool taken deeper moves the extreme,
                    # but the most significant pool taken so far still names the sweep.
                    for key in ('sweep_i', 'name', 'level', 'kind', 'created', 'count', 'session'):
                        state[key] = current[key]
                armed[direction] = state

        if i >= start_index and i >= cfg.warmup_bars and tradable:
            for direction in (1, -1):
                setup = _advance(armed, direction, i, bars, atr, piv_hi_idx, piv_hi_lvl, piv_lo_idx, piv_lo_lvl, cfg)
                if setup:
                    row = _candidate(symbol, setup, i, bars, ctx, pools, cfg, asset, day_open, day_high, day_low,
                                     prev_day_high, prev_day_low, asia_range)
                    if row:
                        out.append(row)
        else:
            for direction in (1, -1):
                _advance(armed, direction, i, bars, atr, piv_hi_idx, piv_hi_lvl, piv_lo_idx, piv_lo_lvl, cfg)
        day_high, day_low = max(day_high, h[i]), min(day_low, l[i])
    return out


def _advance(armed, direction, i, bars, atr, phi, phl, pli, pll, cfg) -> dict | None:
    """Move one armed sweep forward by bar i; returns the finished setup when its FVG appears."""
    state = armed[direction]
    if state is None:
        return None
    h, l, c = bars.h, bars.l, bars.c
    if state['mss_i'] is None:
        if i > state['sweep_i'] and ((direction == 1 and l[i] < state['extreme'])
                                     or (direction == -1 and h[i] > state['extreme'])):
            state['extreme'], state['extreme_i'] = (l[i] if direction == 1 else h[i]), i
        if i - state['extreme_i'] > cfg.mss_wait_bars:
            armed[direction] = None
            return None
        idx, lvl = (phi, phl) if direction == 1 else (pli, pll)
        k = bisect.bisect_left(idx, state['extreme_i']) - 1
        if k < 0 or state['extreme_i'] - idx[k] > cfg.pivot_age_bars or i == 0:
            return None
        level, previous_close = lvl[k], c[i - 1]
        if not ((direction == 1 and c[i] > level >= previous_close)
                or (direction == -1 and c[i] < level <= previous_close)):
            return None
        state['mss'], state['mss_i'], state['pivot_i'] = level, i, idx[k]
    if i > state['mss_i'] + 1:          # the FVG must exist by the candle after the shift
        armed[direction] = None
        return None
    gap = find_fvg(h, l, atr, direction, state['extreme_i'], i, cfg.min_fvg_atr)
    if gap is None:
        return None
    armed[direction] = None
    return {**state, 'direction': direction, 'fvg_i': gap[0], 'fvg_low': gap[1], 'fvg_high': gap[2]}


def _ratio(a: float, b: float) -> float:
    return a / b if b and not math.isnan(b) else math.nan


def _candidate(symbol, s, i, bars, ctx, pools, cfg, asset, day_open, day_high, day_low, pdh, pdl, asia_range):
    t, o, h, l, c, spread = bars.t, bars.o, bars.h, bars.l, bars.c, bars.spread
    d = s['direction']
    buy = d == 1
    A = float(ctx['atr'][i])
    if not A:
        return None
    entry = float(s['fvg_high'] if buy else s['fvg_low'])
    stop = float(s['extreme'] - cfg.stop_buffer_atr * A if buy else s['extreme'] + cfg.stop_buffer_atr * A)
    risk = abs(entry - stop)
    if risk < cfg.min_risk_atr * A or d * (c[i] - entry) < 0:
        return None                     # too tight, or price already through the limit (it would fill at market)
    target = entry + d * cfg.rr * risk
    ei, mi, fi = s['extreme_i'], s['mss_i'], s['fvg_i']

    # Displacement and leg.
    mbody, mrange = abs(c[mi] - o[mi]), h[mi] - l[mi]
    leg = slice(ei, i + 1)
    bodies = np.abs(c[leg] - o[leg])
    fvg_count = count_fvgs(h, l, d, ei, i)
    ote = retracement(entry, s['extreme'], float(np.max(h[leg]) if buy else np.min(l[leg])))

    # Order block: the last opposite candle from the extreme to the shift.
    ob = order_block(o, h, l, c, d, ei, mi)
    fl, fh = s['fvg_low'], s['fvg_high']
    ob_overlap = float(ob is not None and fl <= ob[2] and fh >= ob[1])
    ob_dist = (d * (entry - (ob[2] if buy else ob[1])) / A) if ob else math.nan
    # Breaker (unicorn): the gap overlaps the candle of the swing that the shift broke.
    p = s['pivot_i']
    breaker = float(fl <= h[p] and fh >= l[p]) if p is not None else math.nan

    # Draw on liquidity: the nearest fresh opposing pool beyond the entry, in R.
    opp = [lvl for lvl, side, _, _ in pools.values() if side == d and d * (lvl - entry) > 0]
    opp_r = (min(abs(lvl - entry) for lvl in opp) / risk) if opp else math.nan

    # Sweep candle anatomy.
    si = s['sweep_i']
    srange = h[si] - l[si]
    wick = (min(o[si], c[si]) - l[si]) if buy else (h[si] - max(o[si], c[si]))

    def pd_pos(lo, hi):
        if math.isnan(lo) or math.isnan(hi) or hi <= lo:
            return math.nan
        pos = (c[i] - lo) / (hi - lo)
        return pos if buy else 1 - pos

    def ret(k):
        return d * (c[i] - c[i - k]) / A if i >= k else math.nan

    m = int(ctx['minute'][i])
    zone = in_killzone(m, int(ctx['weekday'][i]))
    close_time = int(t[i]) + M5
    feats = {
        'direction': d, 'pool_kind': s['kind'], 'n_pools_swept': s['count'], 'pool_age_bars': si - s['created'],
        'in_killzone': float(zone), 'session_sweep': s['session'], 'session_now': session_of(m),
        'ny_hour': m / 60, 'weekday': int(ctx['weekday'][i]), 'asset': asset,
        'sweep_depth_atr': abs(s['extreme'] - s['level']) / A, 'sweep_wick_ratio': _ratio(wick, srange),
        'bars_sweep_to_mss': mi - ei, 'bars_extreme_to_now': i - ei,
        'mss_body_atr': mbody / A, 'mss_range_atr': mrange / A, 'mss_body_ratio': _ratio(mbody, mrange),
        'mss_close_beyond_atr': d * (c[mi] - s['mss']) / A, 'leg_atr': d * (c[i] - s['extreme']) / A,
        'leg_max_body_atr': float(bodies.max()) / A, 'leg_bars': i - ei,
        'fvg_size_atr': (fh - fl) / A, 'fvg_count_leg': fvg_count, 'fvg_age_bars': i - fi,
        'ob_overlap': ob_overlap, 'ob_dist_atr': ob_dist, 'breaker_overlap': breaker,
        'ote_fib': ote, 'in_ote': float(0.62 <= ote <= 0.79) if not math.isnan(ote) else math.nan,
        'risk_atr': risk / A, 'spread_risk': spread[i] / risk, 'spread_atr': spread[i] / A,
        'entry_dist_atr': d * (c[i] - entry) / A, 'opp_pool_r': opp_r,
        'target_before_pool': float(opp_r >= cfg.rr) if not math.isnan(opp_r) else math.nan,
        'atr_pct': A / c[i] * 100, 'atr_ratio_day': _ratio(A, ctx['atr_day'][i]),
        'atr_ratio_week': _ratio(A, ctx['atr_week'][i]),
        'ema_h1_20_atr': d * (c[i] - ctx['ema240'][i]) / A, 'ema_h1_50_atr': d * (c[i] - ctx['ema600'][i]) / A,
        'ema_h4_50_atr': d * (c[i] - ctx['ema2400'][i]) / A,
        'ema_h1_50_slope_atr': d * (ctx['ema600'][i] - ctx['ema600'][i - 48]) / A if i >= 48 else math.nan,
        'pd_prev_day': pd_pos(pdl, pdh), 'pd_week': pd_pos(ctx['week_lo'][i], ctx['week_hi'][i]),
        'day_move_atr': d * (c[i] - day_open) / A, 'day_range_atr': (max(day_high, h[i]) - min(day_low, l[i])) / A,
        'asia_range_atr': asia_range / A,
        'ret_1h_atr': ret(12), 'ret_4h_atr': ret(48), 'ret_1d_atr': ret(288),
    }
    return {
        'symbol': symbol.upper(), 'bar_index': i, 'bar_time': close_time, 'side': 'BUY' if buy else 'SELL',
        'entry': entry, 'stop': stop, 'target': target, 'risk': risk, 'atr': A,
        'fvg_high': float(fh), 'fvg_low': float(fl), 'sweep_level': float(s['extreme']), 'mss_level': float(s['mss']),
        'swept_name': s['name'], **{k: float(v) for k, v in feats.items()},
    }


def payload(row: dict, probability: float | None = None) -> dict:
    """A candidate as an analyzer-style ICT payload (same fields as scripts/ict_engine.py)."""
    direction = 'BUY_SETUP' if row['side'] == 'BUY' else 'SELL_SETUP'
    body = {
        'event_id': f"{row['symbol']}-5m-ictml-{row['bar_time']}-{direction}", 'symbol': row['symbol'],
        'timeframe': '5m', 'bar_time': row['bar_time'], 'signal': direction, 'model': 'ict',
        'atr': round(row['atr'], 8), 'sweep_level': round(row['sweep_level'], 8),
        'mss_level': round(row['mss_level'], 8), 'fvg_high': round(row['fvg_high'], 8),
        'fvg_low': round(row['fvg_low'], 8), 'entry': round(row['entry'], 8), 'stop': round(row['stop'], 8),
        'target_liquidity': round(row['target'], 8), 'swept_name': row['swept_name'],
    }
    if probability is not None:
        body['ml_probability'] = round(float(probability), 4)
    return body
