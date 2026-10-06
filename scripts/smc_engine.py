"""ICT / Smart Money Concepts detection on broker candles: a bar-for-bar port of tradingview/smc_setups.pine.

Pure Python, no MetaTrader import, so the same code runs in tests. The engine replays closed 15m bars in order
with Daily, 4H and Weekly context and returns the confirmed-entry payloads exactly as the Pine webhook sends them
(`entry_mode: confirmed_close`). The feeder re-runs the replay every bar and posts only a payload whose
`bar_time` is the bar that just closed, so emission is edge-triggered and a restart never re-sends history.

Order of evaluation inside `step()` follows the Pine script top to bottom; where Pine semantics are not fully
specified (pivot ties) the stricter reading is used and noted.
"""
from __future__ import annotations

import datetime as dt
import math
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
M15 = 900
POOL_NAMES = ('PDH', 'PDL', 'PWH', 'PWL', 'Asia high', 'Asia low', 'EQH', 'EQL', 'Swing high', 'Swing low')
KILLZONES = {'London': (2 * 60, 5 * 60), 'NY AM': (8 * 60 + 30, 11 * 60), 'NY PM': (13 * 60 + 30, 16 * 60)}


@dataclass
class Config:
    pivot_len: int = 3
    asia_start: int = 20 * 60          # New York minutes of day
    asia_end: int = 24 * 60
    eq_tol_atr: float = 0.1
    range_bars: int = 96
    min_rr: float = 1.5
    disp_atr: float = 1.0
    min_fvg_atr: float = 0.1
    wait_bars: int = 12
    require_htf: bool = True
    require_discount: bool = True
    require_ob: bool = False
    ob_lookback: int = 20
    track_bars: int = 48
    outcome_bars: int = 192
    killzones: tuple[str, ...] = ('London', 'NY AM')
    crypto: bool = False
    stop_buffer: float = 0.1
    min_risk_atr: float = 0.3
    max_risk_atr: float = 3.0
    min_atr_pct: float = 0.02
    max_atr_pct: float = 0.5
    weights: dict = field(default_factory=lambda: {'htf': 20, 'sweep': 20, 'mss': 20, 'fvg': 15, 'zone': 10, 'kz': 10, 'ob': 5})
    min_score: int = 70
    tick: float = 0.01


@dataclass
class Plan:
    direction: int
    state: int                 # 1 wait for retest, 2 entered, 3 finished
    created: int
    formation_time: int
    midpoint: float
    stop: float
    target: float
    top: float
    bottom: float
    range_high: float
    range_low: float
    sweep: float
    mss: float
    ob_top: float | None
    ob_bottom: float | None
    score: int
    target_name: str
    swept_name: str
    entered: int | None = None
    entry: float | None = None
    message: str = 'WAIT - retest, then a confirming close'


def ny(stamp: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).astimezone(NY)


def structure_bias(bars: list[dict], pivot_len: int) -> list[int]:
    """Pine structureBias(): direction after each bar, from the last confirmed swing broken by a close."""
    out, swing_high, swing_low, direction = [], None, None, 0
    for i, bar in enumerate(bars):
        ph, pl = pivot(bars, i, pivot_len)
        if ph is not None:
            swing_high = ph
        if pl is not None:
            swing_low = pl
        if swing_high is not None and bar['c'] > swing_high:
            direction = 1
        if swing_low is not None and bar['c'] < swing_low:
            direction = -1
        out.append(direction)
    return out


def pivot(bars: list[dict], i: int, n: int) -> tuple[float | None, float | None]:
    """ta.pivothigh/pivotlow(n, n) as known on bar i: the bar n candles back, strictly beyond its 2n neighbours
    (ties are not pivots; Pine's exact tie handling is undocumented, so the stricter reading is used)."""
    centre = i - n
    if centre - n < 0:
        return None, None
    window = bars[centre - n:i + 1]
    high, low = bars[centre]['h'], bars[centre]['l']
    ph = high if all(b['h'] < high for k, b in enumerate(window) if k != n) else None
    pl = low if all(b['l'] > low for k, b in enumerate(window) if k != n) else None
    return ph, pl


def round_tick(value: float, tick: float, mode: str = 'round') -> float:
    """Pine math.round_to_mintick / floor / ceil to the symbol's tick; the epsilon absorbs float noise."""
    units = value / tick
    if mode == 'floor':
        units = math.floor(units + 1e-9)
    elif mode == 'ceil':
        units = math.ceil(units - 1e-9)
    else:
        units = round(units)
    return round(units * tick, 8)


class Engine:
    def __init__(self, symbol: str, cfg: Config):
        self.symbol, self.cfg = symbol, cfg
        self.wins = self.losses = 0
        self.plan: Plan | None = None
        self.emitted: list[dict] = []

    # -- higher timeframe context ----------------------------------------------------------------
    def _context(self, d1: list[dict], h4: list[dict], w1: list[dict]):
        n = self.cfg.pivot_len
        self._d1, self._h4, self._w1 = d1, h4, w1
        self._d1_bias, self._h4_bias = structure_bias(d1, n), structure_bias(h4, n)

    @staticmethod
    def _last_closed(bars: list[dict], period: int, stamp: int) -> int | None:
        """Index of the last higher-timeframe bar completed at or before a 15m bar's open (Pine `[1]` + lookahead)."""
        index = None
        for k, bar in enumerate(bars):
            if bar['t'] + period <= stamp:
                index = k
            else:
                break
        return index

    @staticmethod
    def _containing(bars: list[dict], stamp: int) -> int | None:
        index = None
        for k, bar in enumerate(bars):
            if bar['t'] <= stamp:
                index = k
            else:
                break
        return index

    # -- replay --------------------------------------------------------------------------------------
    def run(self, m15: list[dict], d1: list[dict], h4: list[dict], w1: list[dict]) -> list[dict]:
        """Replay closed 15m bars (dicts t,o,h,l,c; t = open time, UTC seconds). Returns emitted payloads."""
        self._context(d1, h4, w1)
        c = self.cfg
        self.bars = m15
        self.atr: list[float] = []
        self.disp_bull: list[bool] = []
        self.disp_bear: list[bool] = []
        self.last_high = self.last_low = self.eqh = self.eql = None
        self.asia_hi = self.asia_lo = self.asia_high = self.asia_low = None
        self.prev_in_asia = False
        self.prev_day = self.prev_week = None
        self.pool_values: list[float | None] = [None] * 10
        self.pool_fresh = [False] * 10
        self.long_state = self.short_state = 0
        self.long_sweep = self.short_sweep = self.long_mss = self.short_mss = None
        self.long_sweep_bar = self.short_sweep_bar = self.long_shift_bar = self.short_shift_bar = None
        self.long_swept = self.short_swept = ''
        self.status = 'warming up'
        tr_prev = None
        for i, bar in enumerate(m15):
            prev_close = m15[i - 1]['c'] if i else None
            tr = bar['h'] - bar['l'] if prev_close is None else max(bar['h'] - bar['l'], abs(bar['h'] - prev_close), abs(bar['l'] - prev_close))
            tr_prev = tr if tr_prev is None else (tr_prev * 13 + tr) / 14
            self.atr.append(tr_prev)
            self.step(i)
        return self.emitted

    # -- one confirmed bar -------------------------------------------------------------------------
    def step(self, i: int) -> None:
        c, bars = self.cfg, self.bars
        bar = bars[i]
        atr = self.atr[i]
        stamp, close_time = bar['t'], bar['t'] + M15
        local = ny(stamp)
        minute = local.hour * 60 + local.minute
        weekday_ok = c.crypto or local.weekday() < 5
        kz_name = next((name for name in ('London', 'NY AM', 'NY PM') if name in c.killzones and weekday_ok
                        and KILLZONES[name][0] <= minute < KILLZONES[name][1]), 'none')
        in_kz = kz_name != 'none'
        atr_pct = atr / bar['c'] * 100
        volatility_ok = c.min_atr_pct <= atr_pct <= c.max_atr_pct

        d_idx, h_idx, w_idx = (self._last_closed(self._d1, 86400, stamp), self._last_closed(self._h4, 14400, stamp),
                               self._last_closed(self._w1, 7 * 86400, stamp))
        daily_bias = self._d1_bias[d_idx] if d_idx is not None else 0
        h4_bias = self._h4_bias[h_idx] if h_idx is not None else 0
        htf_bias = daily_bias if daily_bias == h4_bias else 0
        pdh, pdl = (self._d1[d_idx]['h'], self._d1[d_idx]['l']) if d_idx is not None else (None, None)
        pwh, pwl = (self._w1[w_idx]['h'], self._w1[w_idx]['l']) if w_idx is not None else (None, None)
        day, week = self._containing(self._d1, stamp), self._containing(self._w1, stamp)
        new_day, new_week = day != self.prev_day and self.prev_day is not None, week != self.prev_week and self.prev_week is not None
        self.prev_day, self.prev_week = day, week

        in_asia = c.asia_start <= minute < c.asia_end
        asia_complete = not in_asia and self.prev_in_asia
        if in_asia and not self.prev_in_asia:
            self.asia_hi, self.asia_lo = bar['h'], bar['l']
        elif in_asia:
            self.asia_hi = bar['h'] if self.asia_hi is None else max(self.asia_hi, bar['h'])
            self.asia_lo = bar['l'] if self.asia_lo is None else min(self.asia_lo, bar['l'])
        if asia_complete:
            self.asia_high, self.asia_low = self.asia_hi, self.asia_lo
        self.prev_in_asia = in_asia

        ph, pl = pivot(bars, i, c.pivot_len)
        new_eq_high = new_eq_low = False
        atr_at_pivot = self.atr[i - c.pivot_len] if i >= c.pivot_len else atr
        if ph is not None:
            new_eq_high = self.last_high is not None and abs(ph - self.last_high) <= c.eq_tol_atr * atr_at_pivot
            if new_eq_high:
                self.eqh = max(ph, self.last_high)
            self.last_high = ph
        if pl is not None:
            new_eq_low = self.last_low is not None and abs(pl - self.last_low) <= c.eq_tol_atr * atr_at_pivot
            if new_eq_low:
                self.eql = min(pl, self.last_low)
            self.last_low = pl

        window = bars[max(0, i - c.range_bars + 1):i + 1]
        range_high_ext, range_low_ext = max(b['h'] for b in window), min(b['l'] for b in window)

        # Each named pool can be used once until that day/week/session/swing is replaced.
        current = [pdh, pdl, pwh, pwl, self.asia_high, self.asia_low, self.eqh, self.eql, self.last_high, self.last_low]
        resets = [new_day, new_day, new_week, new_week, asia_complete, asia_complete, new_eq_high, new_eq_low,
                  ph is not None, pl is not None]
        swept_low = swept_high = ''
        for k in range(10):
            level, previous = current[k], self.pool_values[k]
            if level is not None and (previous is None or level != previous or resets[k]):
                self.pool_values[k], self.pool_fresh[k] = level, True
            upper = k % 2 == 0
            touched = level is not None and (bar['h'] >= level if upper else bar['l'] <= level)
            if self.pool_fresh[k] and touched:
                if upper and bar['h'] > level and bar['c'] < level and not swept_high:
                    swept_high = POOL_NAMES[k]
                if not upper and bar['l'] < level and bar['c'] > level and not swept_low:
                    swept_low = POOL_NAMES[k]
                self.pool_fresh[k] = False

        body = abs(bar['c'] - bar['o'])
        bull_disp, bear_disp = bar['c'] > bar['o'] and body >= c.disp_atr * atr, bar['c'] < bar['o'] and body >= c.disp_atr * atr
        self.disp_bull.append(bull_disp)
        self.disp_bear.append(bear_disp)
        two_back = bars[i - 2] if i >= 2 else None
        bull_fvg = (two_back is not None and bar['l'] > two_back['h'] and bar['l'] - two_back['h'] >= c.min_fvg_atr * atr
                    and self.disp_bull[i - 1])
        bear_fvg = (two_back is not None and bar['h'] < two_back['l'] and two_back['l'] - bar['h'] >= c.min_fvg_atr * atr
                    and self.disp_bear[i - 1])

        data_ready = i >= c.range_bars
        if data_ready:
            if self.long_state and (i - self.long_sweep_bar > c.wait_bars + (1 if self.long_state == 2 else 0) or bar['l'] < self.long_sweep):
                self.long_state = 0
            if self.short_state and (i - self.short_sweep_bar > c.wait_bars + (1 if self.short_state == 2 else 0) or bar['h'] > self.short_sweep):
                self.short_state = 0
            if swept_low and swept_high:
                self.long_state = self.short_state = 0
            else:
                if swept_low and self.last_high is not None and bar['c'] <= self.last_high and self.long_state == 0:
                    self.long_state, self.long_sweep, self.long_mss = 1, bar['l'], self.last_high
                    self.long_sweep_bar, self.long_swept = i, swept_low
                if swept_high and self.last_low is not None and bar['c'] >= self.last_low and self.short_state == 0:
                    self.short_state, self.short_sweep, self.short_mss = 1, bar['h'], self.last_low
                    self.short_sweep_bar, self.short_swept = i, swept_high
            prev_close = bars[i - 1]['c']
            if self.long_state == 1 and i > self.long_sweep_bar and prev_close <= self.long_mss and bar['c'] > self.long_mss and bull_disp:
                self.long_state, self.long_shift_bar = 2, i
            if self.short_state == 1 and i > self.short_sweep_bar and prev_close >= self.short_mss and bar['c'] < self.short_mss and bear_disp:
                self.short_state, self.short_shift_bar = 2, i

        ob_long = self._last_opposing(i, True, self.long_sweep_bar)
        ob_short = self._last_opposing(i, False, self.short_sweep_bar)
        ce_long = round_tick((bar['l'] + two_back['h']) / 2, c.tick) if two_back else None
        ce_short = round_tick((bar['h'] + two_back['l']) / 2, c.tick) if two_back else None
        candidate_long = self.long_state == 2 and self.long_shift_bar == i - 1 and bull_fvg and bar['c'] > self.long_mss
        candidate_short = self.short_state == 2 and self.short_shift_bar == i - 1 and bear_fvg and bar['c'] < self.short_mss

        def score(is_buy: bool, shifted: bool, armed: bool, location_ok: bool, ob_ok: bool) -> int:
            w = c.weights
            total = (w['htf'] if c.require_htf else 0) + w['sweep'] + w['mss'] + w['fvg'] + (w['zone'] if c.require_discount else 0) + w['kz'] + w['ob']
            points = (w['htf'] if c.require_htf and htf_bias == (1 if is_buy else -1) else 0)
            points += (w['sweep'] if armed else 0) + (w['mss'] + w['fvg'] if shifted else 0)
            points += (w['zone'] if c.require_discount and location_ok else 0) + (w['kz'] if in_kz else 0)
            points += w['ob'] if ob_ok and shifted else 0
            return int(round(100.0 * points / total)) if total else 0

        def valid_risk(is_buy: bool, entry: float, stop: float, target: float | None) -> bool:
            if target is None or entry <= 0 or stop <= 0 or target <= 0:
                return False
            risk = entry - stop if is_buy else stop - entry
            reward = target - entry if is_buy else entry - target
            return c.min_risk_atr * atr <= risk <= c.max_risk_atr * atr and reward >= c.min_rr * risk

        busy_at_open = self.plan is not None and self.plan.state in (1, 2)
        entry_event = None

        # Pending plan: expiry before retest, invalidation before entry.
        plan = self.plan
        if plan and plan.state == 1 and i > plan.created:
            bullish = plan.direction == 1
            bias_lost = c.require_htf and htf_bias != plan.direction
            stop_touched = bar['l'] <= plan.stop if bullish else bar['h'] >= plan.stop
            target_touched = bar['h'] >= plan.target if bullish else bar['l'] <= plan.target
            gap_broken = bar['c'] < plan.bottom if bullish else bar['c'] > plan.top
            too_old = i - plan.created > c.track_bars
            if too_old or bias_lost or stop_touched or target_touched or gap_broken:
                plan.state = 3
                plan.message = ('EXPIRED - no confirmed entry' if too_old else 'CANCELLED - direction changed' if bias_lost
                                else 'CANCELLED - stop reached before entry' if stop_touched
                                else 'MISSED - target reached before entry' if target_touched else 'CANCELLED - FVG closed through')
            else:
                retested = bar['l'] <= plan.midpoint <= bar['h']
                rejection = (bar['c'] > bar['o'] and bar['c'] > plan.top) if bullish else (bar['c'] < bar['o'] and bar['c'] < plan.bottom)
                equilibrium = (plan.range_high + plan.range_low) / 2
                inside = plan.range_low <= bar['c'] <= plan.range_high
                location_ok = inside and (not c.require_discount or (bar['c'] < equilibrium if bullish else bar['c'] > equilibrium))
                if in_kz and volatility_ok and retested and rejection and location_ok and valid_risk(bullish, bar['c'], plan.stop, plan.target):
                    plan.state, plan.entry, plan.entered = 2, bar['c'], i
                    plan.message = ('BUY' if bullish else 'SELL') + ' confirmed - reference entry at close'
                    entry_event = 'BUY_SETUP' if bullish else 'SELL_SETUP'
        elif plan and plan.state == 2 and i > plan.entered:
            bullish = plan.direction == 1
            hit_stop = bar['l'] <= plan.stop if bullish else bar['h'] >= plan.stop
            hit_target = bar['h'] >= plan.target if bullish else bar['l'] <= plan.target
            gapped = (bar['o'] < plan.stop or bar['o'] > plan.target) if bullish else (bar['o'] > plan.stop or bar['o'] < plan.target)
            timed_out = i - plan.entered > c.outcome_bars
            if timed_out or gapped or (hit_stop and hit_target):
                plan.state, plan.message = 3, 'UNRESOLVED - tracking time ended' if timed_out else 'UNCERTAIN - gap / both stop and TP1'
            elif hit_stop or hit_target:
                self.wins += 1 if hit_target else 0
                self.losses += 1 if hit_stop else 0
                plan.state, plan.message = 3, 'TP1 REACHED - example finished' if hit_target else 'STOP REACHED - example finished'

        samples = self.wins + self.losses
        if entry_event:
            self.emitted.append(self._payload(entry_event, plan, bar, close_time, atr, htf_bias, daily_bias, h4_bias,
                                              pdh, pdl, pwh, pwl, kz_name, samples))

        # A new plan only when none is being followed and every filter passes on the FVG candle.
        if data_ready and not busy_at_open and in_kz and volatility_ok:
            if candidate_long:
                stop = round_tick(self.long_sweep - c.stop_buffer * atr, c.tick, 'floor')
                target, target_name = self._pick_target(True, ce_long, ce_long - stop, bar['h'])
                eq = (range_high_ext + self.long_sweep) / 2
                location_ok = ce_long < eq
                sc = score(True, True, True, location_ok, ob_long is not None)
                if ((not c.require_htf or htf_bias == 1) and (not c.require_discount or location_ok)
                        and (not c.require_ob or ob_long is not None) and self.long_sweep < ce_long <= range_high_ext
                        and valid_risk(True, ce_long, stop, target) and sc >= c.min_score):
                    self.plan = Plan(1, 1, i, close_time, ce_long, stop, target, bar['l'], two_back['h'], range_high_ext,
                                     self.long_sweep, self.long_sweep, self.long_mss, *(ob_long or (None, None)), sc,
                                     target_name, self.long_swept)
            elif candidate_short:
                stop = round_tick(self.short_sweep + c.stop_buffer * atr, c.tick, 'ceil')
                target, target_name = self._pick_target(False, ce_short, stop - ce_short, bar['l'])
                eq = (self.short_sweep + range_low_ext) / 2
                location_ok = ce_short > eq
                sc = score(False, True, True, location_ok, ob_short is not None)
                if ((not c.require_htf or htf_bias == -1) and (not c.require_discount or location_ok)
                        and (not c.require_ob or ob_short is not None) and range_low_ext <= ce_short < self.short_sweep
                        and valid_risk(False, ce_short, stop, target) and sc >= c.min_score):
                    self.plan = Plan(-1, 1, i, close_time, ce_short, stop, target, two_back['l'], bar['h'], self.short_sweep,
                                     range_low_ext, self.short_sweep, self.short_mss, *(ob_short or (None, None)), sc,
                                     target_name, self.short_swept)

        # A gap must belong to the actual MSS candle, not an unrelated later displacement.
        if self.long_state == 2 and i > self.long_shift_bar:
            self.long_state = 0
        if self.short_state == 2 and i > self.short_shift_bar:
            self.short_state = 0
        self.status = (f'bias D{daily_bias:+d}/4H{h4_bias:+d} kz={kz_name} long={self.long_state} short={self.short_state} '
                       f'plan={self.plan.message if self.plan else "none"} atr%={atr_pct:.3f}')

    def _last_opposing(self, i: int, bullish: bool, sweep_bar: int | None) -> tuple[float, float] | None:
        if sweep_bar is None:
            return None
        for k in range(2, self.cfg.ob_lookback + 1):
            j = i - k
            if j < sweep_bar or j < 0:
                break
            b = self.bars[j]
            if (b['c'] < b['o']) if bullish else (b['c'] > b['o']):
                return b['h'], b['l']
        return None

    def _pick_target(self, is_buy: bool, entry: float, risk: float, beyond: float) -> tuple[float | None, str]:
        best, name = None, 'none'
        for k in range(10):
            level = self.pool_values[k]
            if not self.pool_fresh[k] or level is None or (k % 2 == 0) != is_buy:
                continue
            reward = level - entry if is_buy else entry - level
            ahead = level > beyond if is_buy else level < beyond
            if ahead and reward > 0 and reward >= self.cfg.min_rr * risk and (best is None or (level < best if is_buy else level > best)):
                best, name = level, POOL_NAMES[k]
        return best, name

    def _payload(self, direction, plan, bar, close_time, atr, htf_bias, daily_bias, h4_bias, pdh, pdl, pwh, pwl, kz_name, samples):
        def num(value):
            return None if value is None else round(float(value), 8)
        return {'event_id': f'{self.symbol}-15m-smc-{close_time}-{direction}', 'symbol': self.symbol, 'timeframe': '15m',
                'bar_time': close_time, 'signal': direction, 'model': 'smc', 'price': num(bar['c']), 'atr': num(atr),
                'entry_mode': 'confirmed_close', 'setup_entry': num(plan.midpoint), 'setup_bar_time': plan.formation_time,
                'htf_bias': htf_bias, 'daily_bias': daily_bias, 'h4_bias': h4_bias, 'sweep_level': num(plan.sweep),
                'swept_name': plan.swept_name, 'mss_level': num(plan.mss), 'fvg_top': num(plan.top), 'fvg_bottom': num(plan.bottom),
                'ob_top': num(plan.ob_top), 'ob_bottom': num(plan.ob_bottom), 'range_high': num(plan.range_high),
                'range_low': num(plan.range_low), 'pdh': num(pdh), 'pdl': num(pdl), 'pwh': num(pwh), 'pwl': num(pwl),
                'asia_high': num(self.asia_high), 'asia_low': num(self.asia_low), 'entry': num(plan.entry), 'stop': num(plan.stop),
                'target_liquidity': num(plan.target), 'target_name': plan.target_name, 'killzone': kz_name, 'score': plan.score,
                'hit_rate': round(self.wins / samples, 3) if samples else None, 'samples': samples}
