"""Intraday ideas for the screen (ml/screen.py): trades that last hours, not minutes. No scalping.

    python -m ml.intraday              # run every idea on development gold, write ml/reports/xauusd_intraday_screen.md
    python -m ml.intraday --check      # prove that no idea reads a candle from the future

Signals come from closed M15 or H1 bars. Stops are 2 to 3 ATR of H1 or half a session's range, so the spread is a
few percent of the risk instead of the 20 to 30 percent it was in the scalping screen (ml/ideas.py). A trade is
held for hours: either up to 12 or 24 hours, or until 16:00 New York the same trading day. Every rule and
parameter here was written before the first run; the screen decides, nothing is tuned afterwards.

Times are New York. The trading day starts at 17:00. Day trades enter from 19:00 and are flat by 16:00, so they
stay clear of the hour around the daily break, when the spread is wide and the bid candles bend.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml import lockbox, screen
from ml.data import ROOT, Bars
from ml.ideas import INF, Frame, build, fmt, rsi

REPORT = ROOT / 'ml' / 'reports' / 'xauusd_intraday_screen.md'
DAY_START = 17 * 60             # New York minute at which the trading day changes
MAP_T = 2.5                     # a session or weekday is traded only if its discovery drift has |t| >= this
WEEKDAYS = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday')


def clock(hhmm: str) -> int:
    """Minutes into the trading day (which starts at 17:00 New York) for a New York time 'HH:MM'."""
    hour, minute = map(int, hhmm.split(':'))
    return (hour * 60 + minute - DAY_START) % 1440


REOPEN, ASIA, LONDON, NEW_YORK, NOON, FLAT = (clock(x) for x in ('18:00', '19:00', '03:00', '08:00', '12:00', '16:00'))


def table(f: Frame) -> pd.DataFrame:
    """The frame with s = minutes into the trading day at the bar open, and close_s at the bar close."""
    d = f.frame()
    d['s'] = (d['minute'] - DAY_START) % 1440
    d['close_s'] = d['s'] + f.seconds // 60
    return d


def signals(d: pd.DataFrame, mask, side, stop, target, hold) -> pd.DataFrame:
    """Rows of d where mask holds and an entry exists, as screen signals. Unlike ideas.entries, hold (minutes) may
    differ per row; a trade with less than 30 minutes left is not taken."""
    n = len(d)
    mask = np.asarray(mask, dtype=bool) & (d['entry'].to_numpy() >= 0)
    out = pd.DataFrame({'i': d['entry'].to_numpy()[mask]})
    for name, value in (('side', side), ('stop', stop), ('target', target), ('hold', hold)):
        out[name] = np.broadcast_to(np.asarray(value, dtype=float), (n,))[mask]
    good = ((out['stop'] > 0) & np.isfinite(out['stop']) & np.isfinite(out['side']) & (out['side'] != 0)
            & np.isfinite(out['hold']) & (out['hold'] >= 30))
    out = out[good].reset_index(drop=True)
    out['hold'] = out['hold'].astype(np.int64)
    return out


def daily(d: pd.DataFrame) -> pd.DataFrame:
    """One row per trading day. Only ever used shifted by one day, so a signal sees finished days only."""
    out = d.groupby('day').agg(open=('o', 'first'), high=('h', 'max'), low=('l', 'min'), close=('c', 'last'))
    out['range'] = out['high'] - out['low']
    out['avg_range'] = out['range'].rolling(14).mean()
    return out


def first_of_day(mask: pd.Series, day: pd.Series) -> pd.Series:
    return mask & (mask.groupby(day).cumsum() == 1)


# -- 1. a session's range, then the break ---------------------------------------------------------------------
def range_break(f: Frame, start: int, end: int, until: int, exit_s: int, follow: bool) -> pd.DataFrame:
    """M15: the high and low between two times of the trading day. The first close beyond that range before
    `until` is followed (or faded). Stop = half the range (at least 2 ATR), no target, flat at `exit_s`."""
    d = table(f)
    inside = (d['s'] >= start) & (d['close_s'] <= end)
    high = d['h'].where(inside).groupby(d['day']).transform('max')
    low = d['l'].where(inside).groupby(d['day']).transform('min')
    complete = inside.groupby(d['day']).transform('sum') >= 0.8 * (end - start) / (f.seconds // 60)
    window = (d['s'] >= end) & (d['close_s'] <= until) & complete
    up, down = window & (d['c'] > high), window & (d['c'] < low)
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    stop = np.maximum((high - low) / 2, 2 * d['atr'])
    return signals(d, first_of_day(up | down, d['day']), side, stop, INF, exit_s - d['close_s'])


# -- 2. volatility breakout from the day's open ---------------------------------------------------------------
def volatility_breakout(f: Frame, k: float, follow: bool) -> pd.DataFrame:
    """M15, 19:00 to 12:00: the first close at least k x yesterday's range away from today's open is followed (or
    faded). Stop = k x yesterday's range (back at the open; at least 2 ATR), no target, flat at 16:00."""
    d = table(f)
    day = daily(d)
    reach = k * d['day'].map(day['range'].shift(1))
    day_open = d['day'].map(day['open'])
    window = (d['s'] >= ASIA) & (d['close_s'] <= NOON)
    up, down = window & (d['c'] >= day_open + reach), window & (d['c'] <= day_open - reach)
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    return signals(d, first_of_day(up | down, d['day']), side, np.maximum(reach, 2 * d['atr']), INF,
                   FLAT - d['close_s'])


# -- 3. a narrow day, then the break of its high or low -------------------------------------------------------
def narrow_day(f: Frame, kind: str, follow: bool) -> pd.DataFrame:
    """M15, 19:00 to 12:00: yesterday was an inside day (inside the day before) or the narrowest of seven days
    (NR7). The first close beyond yesterday's high or low is followed (or faded). Stop = half of yesterday's
    range (at least 2 ATR), no target, flat at 16:00."""
    d = table(f)
    day = daily(d)
    if kind == 'inside':
        flag = (day['high'] < day['high'].shift(1)) & (day['low'] > day['low'].shift(1))
    else:
        flag = day['range'] <= day['range'].rolling(7).min()
    yesterday = d['day'].map(flag.shift(1, fill_value=False)).fillna(False).astype(bool)
    high, low = d['day'].map(day['high'].shift(1)), d['day'].map(day['low'].shift(1))
    window = (d['s'] >= ASIA) & (d['close_s'] <= NOON) & yesterday
    up, down = window & (d['c'] > high), window & (d['c'] < low)
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    stop = np.maximum((high - low) / 2, 2 * d['atr'])
    return signals(d, first_of_day(up | down, d['day']), side, stop, INF, FLAT - d['close_s'])


# -- 4. channel break on H1 -----------------------------------------------------------------------------------
def channel(f: Frame, bars: int, follow: bool) -> pd.DataFrame:
    """H1: the first close beyond the highest high / lowest low of the previous `bars` hours. Stop 2 ATR, target
    2R, hold 24 hours."""
    d = table(f)
    hi, lo = d['h'].rolling(bars).max().shift(1), d['l'].rolling(bars).min().shift(1)
    up = (d['c'] > hi) & ~(d['c'].shift(1) > hi.shift(1))
    down = (d['c'] < lo) & ~(d['c'].shift(1) < lo.shift(1))
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    return signals(d, up | down, side, 2 * d['atr'], 4 * d['atr'], 1440)


# -- 5. moving averages on H1 ---------------------------------------------------------------------------------
def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def ema_cross(f: Frame, follow: bool) -> pd.DataFrame:
    """H1: EMA 20 crosses EMA 50; trade with the cross (or against it). Stop 3 ATR, no target, hold 24 hours."""
    d = table(f)
    gap = ema(d['c'], 20) - ema(d['c'], 50)
    ready = np.arange(len(d)) >= 200
    up, down = (gap > 0) & (gap.shift(1) <= 0) & ready, (gap < 0) & (gap.shift(1) >= 0) & ready
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    return signals(d, up | down, side, 3 * d['atr'], INF, 1440)


def ema_pullback(f: Frame) -> pd.DataFrame:
    """H1: in an uptrend (EMA 50 above EMA 200) the bar dips to EMA 20 and closes back above it, after a close
    above it; buy. Mirrored for a downtrend. Stop 2 ATR, target 2R, hold 24 hours."""
    d = table(f)
    e20, e50, e200 = ema(d['c'], 20), ema(d['c'], 50), ema(d['c'], 200)
    ready = np.arange(len(d)) >= 800
    buy = (e50 > e200) & (d['l'] <= e20) & (d['c'] > e20) & (d['c'].shift(1) > e20.shift(1)) & ready
    sell = (e50 < e200) & (d['h'] >= e20) & (d['c'] < e20) & (d['c'].shift(1) < e20.shift(1)) & ready
    return signals(d, buy | sell, buy.astype(float) - sell.astype(float), 2 * d['atr'], 4 * d['atr'], 1440)


# -- 6. stretched on H1: RSI and Bollinger bands --------------------------------------------------------------
def rsi_extreme(f: Frame, follow: bool) -> pd.DataFrame:
    """H1: RSI(14) crosses under 30 or over 70. Fade: buy the low, sell the high. Follow: the opposite. Stop 2
    ATR, target 1R, hold 12 hours."""
    d = table(f)
    value = rsi(d['c'])
    low, high = (value < 30) & (value.shift(1) >= 30), (value > 70) & (value.shift(1) <= 70)
    side = (high.astype(float) - low.astype(float)) * (1 if follow else -1)
    return signals(d, low | high, side, 2 * d['atr'], 2 * d['atr'], 720)


def band(f: Frame, follow: bool) -> pd.DataFrame:
    """H1: the first close outside the Bollinger band (20, 2). Fade it, or follow it. Stop 2 ATR, target 1R, hold
    12 hours."""
    d = table(f)
    mid, sd = d['c'].rolling(20).mean(), d['c'].rolling(20).std()
    upper, lower = mid + 2 * sd, mid - 2 * sd
    up = (d['c'] > upper) & (d['c'].shift(1) <= upper.shift(1))
    down = (d['c'] < lower) & (d['c'].shift(1) >= lower.shift(1))
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    return signals(d, up | down, side, 2 * d['atr'], 2 * d['atr'], 720)


# -- 7. round numbers on H1 -----------------------------------------------------------------------------------
def level(f: Frame, step: float, follow: bool) -> pd.DataFrame:
    """H1: the close crosses a multiple of $50 or $100. Trade with the cross (or against it). Stop 2 ATR, target
    2R, hold 24 hours."""
    d = table(f)
    crossed = np.floor(d['c'] / step) != np.floor(d['c'].shift(1) / step)
    side = np.sign(d['c'] - d['c'].shift(1)) * (1 if follow else -1)
    return signals(d, crossed & d['c'].shift(1).notna(), side.fillna(0), 2 * d['atr'], 4 * d['atr'], 1440)


# -- 8. the last 24 hours, at a session open ------------------------------------------------------------------
def clock_momentum(f: Frame, enter_s: int, follow: bool) -> pd.DataFrame:
    """H1: at the London (03:00) or New York (08:00) open, the change over the last 24 hourly bars gives the side;
    trade with it (or against it). Stop 3 ATR, no target, flat at 16:00."""
    d = table(f)
    side = np.sign(d['c'] - d['c'].shift(24)) * (1 if follow else -1)
    return signals(d, d['close_s'] == enter_s, side.fillna(0), 3 * d['atr'], INF, FLAT - enter_s)


# -- 9. day trades from a daily rule: in at 19:00, flat at 16:00 ----------------------------------------------
def day_trade(f: Frame, rule: str, follow: bool = True) -> pd.DataFrame:
    """H1: one trade per trading day, in at 19:00 and flat at 16:00, stop = the average daily range of the last 14
    finished days, no target. The side comes from finished days only:
      'yesterday'      yesterday's open-to-close direction
      'big_yesterday'  the same, only after a day that moved at least 0.7 x the average range
      'sma20', 'sma50' yesterday's close above or below the 20 or 50 day average of closes
      'long'           always buy (the benchmark: what gold's own drift pays)"""
    d = table(f)
    day = daily(d)
    change = day['close'] - day['open']
    if rule == 'yesterday':
        side_day = np.sign(change)
    elif rule == 'big_yesterday':
        side_day = np.sign(change).where(change.abs() >= 0.7 * day['avg_range'], 0.0)
    elif rule in ('sma20', 'sma50'):
        side_day = np.sign(day['close'] - day['close'].rolling(int(rule[3:])).mean())
    else:
        side_day = pd.Series(1.0, index=day.index)
    side = d['day'].map(side_day.shift(1)).fillna(0) * (1 if follow else -1)
    stop = d['day'].map(day['avg_range'].shift(1))
    return signals(d, d['close_s'] == ASIA, side, stop, INF, FLAT - ASIA)


# -- 10. drift by session and by weekday ----------------------------------------------------------------------
SESSIONS = (('Asia 19:00 to 03:00', ASIA, LONDON), ('London 03:00 to 08:00', LONDON, NEW_YORK),
            ('New York morning 08:00 to 12:00', NEW_YORK, NOON), ('New York afternoon 12:00 to 16:00', NOON, FLAT))


def session_trade(f: Frame, enter_s: int, exit_s: int, side: float, weekday: int | None = None) -> pd.DataFrame:
    """H1: enter at one time of every trading day (or of one weekday), flat at another. Stop 3 ATR, no target."""
    d = table(f)
    mask = d['close_s'] == enter_s
    if weekday is not None:
        mask &= (d['day'] + 3) % 7 == weekday               # day 0 (1970-01-01) was a Thursday
    return signals(d, mask, side, 3 * d['atr'], INF, exit_s - enter_s)


def drift_map(m1: Bars, f: Frame) -> pd.DataFrame:
    """Zero-cost result of buying each session, and each weekday's 19:00 to 16:00, in both periods."""
    rows = []
    cases = [(name, a, b, None) for name, a, b in SESSIONS]
    cases += [(f'{name} 19:00 to 16:00', ASIA, FLAT, k) for k, name in enumerate(WEEKDAYS)]
    for name, a, b, weekday in cases:
        trades = screen.run(m1, session_trade(f, a, b, 1.0, weekday), 0.0)
        trades['usd'] = trades['r'] * trades['stop']
        d, c = screen.window(trades, screen.DISCOVERY), screen.window(trades, screen.CONFIRM)
        sd, sc = screen.stats(d), screen.stats(c)
        rows.append({'name': name, 'enter': a, 'exit': b, 'weekday': weekday, 'r_d': sd['mean'], 't_d': sd['t'],
                     'usd_d': d['usd'].mean(), 'r_c': sc['mean'], 't_c': sc['t'], 'usd_c': c['usd'].mean()})
    return pd.DataFrame(rows)


# -- the list -------------------------------------------------------------------------------------------------
def all_ideas(m1: Bars, with_map: bool = True, log=print) -> tuple[list[dict], pd.DataFrame]:
    m15, h1 = build(m1, 900), build(m1, 3600)
    ideas: list[dict] = []

    def add(family, name, sig):
        ideas.append({'family': family, 'name': name, 'signals': sig})

    def both(family, name, make):
        add(family, f'{name}, follow', make(True))
        add(family, f'{name}, fade', make(False))

    ranges = (('Asia range, break in London', REOPEN, LONDON, NEW_YORK, NOON),
              ('London range, break in New York', LONDON, NEW_YORK, NOON, FLAT),
              ('Asia + London range, break in New York', REOPEN, NEW_YORK, NOON, FLAT),
              ('New York 08:00 to 09:30 range, break by 13:00', NEW_YORK, clock('09:30'), clock('13:00'), FLAT))
    for name, a, b, until, exit_s in ranges:
        both('Session range break (M15)', name, lambda follow: range_break(m15, a, b, until, exit_s, follow))
    for k in (0.5, 1.0):
        both('Volatility breakout (M15)', f"open +/- {k:g} x yesterday's range",
             lambda follow: volatility_breakout(m15, k, follow))
    for kind, label in (('inside', 'inside day'), ('nr7', 'narrowest day of 7')):
        both('Narrow day, then the break (M15)', f'{label}, break of its high/low',
             lambda follow: narrow_day(m15, kind, follow))
    for bars, label in ((24, '24 hour'), (72, '3 day'), (120, '5 day')):
        both('Channel break (H1)', f'{label} channel', lambda follow: channel(h1, bars, follow))
    both('Moving averages (H1)', 'EMA 20 crosses EMA 50', lambda follow: ema_cross(h1, follow))
    add('Moving averages (H1)', 'pullback to EMA 20 in the EMA 50/200 trend', ema_pullback(h1))
    both('Stretched (H1)', 'RSI 30/70', lambda follow: rsi_extreme(h1, follow))
    both('Stretched (H1)', 'close outside the Bollinger band', lambda follow: band(h1, follow))
    for step in (50.0, 100.0):
        both('Round numbers (H1)', f'close crosses a ${step:g} level', lambda follow: level(h1, step, follow))
    for label, enter_s in (('London open', LONDON), ('New York open', NEW_YORK)):
        both('Last 24 hours at a session open (H1)', f'{label}, last 24 hours',
             lambda follow: clock_momentum(h1, enter_s, follow))
    both('Day trade from a daily rule', "yesterday's direction", lambda follow: day_trade(h1, 'yesterday', follow))
    both('Day trade from a daily rule', "yesterday's direction after a big day",
         lambda follow: day_trade(h1, 'big_yesterday', follow))
    both('Day trade from a daily rule', 'side of the 20 day average', lambda follow: day_trade(h1, 'sma20', follow))
    both('Day trade from a daily rule', 'side of the 50 day average', lambda follow: day_trade(h1, 'sma50', follow))
    add('Day trade from a daily rule', 'always buy (benchmark)', day_trade(h1, 'long'))

    drift = pd.DataFrame()
    if with_map:
        log('session and weekday drift map ...')
        drift = drift_map(m1, h1)
        for row in drift.itertuples():
            if np.isfinite(row.t_d) and abs(row.t_d) >= MAP_T:
                side = 1.0 if row.t_d > 0 else -1.0
                weekday = None if pd.isna(row.weekday) else int(row.weekday)
                add('Session or weekday drift', f"{'buy' if side > 0 else 'sell'} {row.name}",
                    session_trade(h1, int(row.enter), int(row.exit), side, weekday))
    return ideas, drift


def evaluate(m1: Bars, sig: pd.DataFrame) -> tuple[dict, dict]:
    """screen.evaluate, plus the median hold and stop of the confirmation trades at the recorded spread."""
    result, extra = {}, {'hours': np.nan, 'stop': np.nan, 'cost_r': np.nan}
    for cost in screen.COSTS:
        trades = screen.run(m1, sig, cost)
        result[cost] = {'discovery': screen.stats(screen.window(trades, screen.DISCOVERY)),
                        'confirm': screen.stats(screen.window(trades, screen.CONFIRM))}
        if cost == 1.0:
            c = screen.window(trades, screen.CONFIRM)
            if len(c):
                extra['hours'] = float(((c['exit_t'] - c['entry_t']) / 3600).median())
                extra['stop'] = float(c['stop'].median())
    result['verdict'] = screen.verdict(result)
    zero, real = result[0.0]['confirm']['mean'], result[1.0]['confirm']['mean']
    extra['cost_r'] = zero - real if np.isfinite(zero) and np.isfinite(real) else np.nan
    return result, extra


def check(m1: Bars, cuts: int = 6, log=print) -> bool:
    """No idea may read a later candle: the signals built from history cut at a random minute must equal the
    signals built from the full history up to that minute."""
    full, _ = all_ideas(m1, with_map=False)
    rng = np.random.default_rng(11)
    ok = True
    for k in sorted(rng.integers(len(m1) // 2, len(m1) - 1, cuts)):
        part, _ = all_ideas(m1.slice(0, int(k)), with_map=False)
        for a, b in zip(full, part):
            want = a['signals'][a['signals']['i'] < k].reset_index(drop=True)
            got = b['signals'].reset_index(drop=True)
            same = len(want) == len(got) and np.allclose(want.to_numpy(float), got.to_numpy(float), equal_nan=True)
            if not same:
                ok = False
                log(f"LOOKAHEAD at cut {k}: {a['name']} ({len(want)} signals with the future, {len(got)} without)")
        log(f'cut at M1 bar {k:,}: checked {len(full)} ideas')
    return ok


def report(results: list[dict], drift: pd.DataFrame, m1: Bars) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    first = datetime.fromtimestamp(int(m1.t[0]), timezone.utc).date()
    last = datetime.fromtimestamp(int(m1.t[-1]), timezone.utc).date()
    rule = screen.RULE
    passed = [r for r in results if r['result']['verdict'] == 'PASSED']
    lines = [f'# XAUUSD intraday screen ({stamp})', '',
             f'Development gold only (Dukascopy M1 {first} .. {last}; nothing from {lockbox.LOCK_START} on is loaded). '
             f'Discovery {screen.DISCOVERY[0]} to {screen.DISCOVERY[1]}, confirmation {screen.CONFIRM[0]} to '
             f'{screen.CONFIRM[1]}. Signals from closed M15 or H1 bars, trades held for hours, one position at a '
             'time per idea. R = result divided by the stop distance. Costs: zero spread, half the recorded '
             'spread, the recorded spread. Times are New York.', '',
             f'Pass rule, fixed before the run: at zero cost in discovery mean R >= {rule["zero_cost_discovery_r"]:+.2f} '
             f'with t >= {rule["zero_cost_discovery_t"]:g}; at the recorded spread in discovery mean R > 0; then in '
             f'confirmation at the recorded spread mean R >= {rule["confirm_r"]:+.2f}, profit factor >= '
             f'{rule["confirm_pf"]:g}, {rule["confirm_years_positive"]:.0%} of years positive and at least '
             f'{rule["confirm_trades_per_year"]} trades a year.', '',
             f'**{len(results)} ideas tested, {len(passed)} passed.**', '']
    counts = pd.Series([r['result']['verdict'] for r in results]).value_counts()
    lines += ['| Verdict | Ideas |', '|---|---|'] + [f'| {k} | {v} |' for k, v in counts.items()] + ['']
    lines += ['| Family | Idea | Trades a year | Median hold (hours) | Median stop ($) | Spread cost (R) | '
              'Zero cost: discovery R (t) | Zero cost: confirmation R | Real spread: discovery R | '
              'Real spread: confirmation R (t) | Confirmation PF | Confirmation total R | Years positive | Verdict |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in results:
        z, f, x = r['result'][0.0], r['result'][1.0], r['extra']
        c = f['confirm']
        lines.append(f"| {r['family']} | {r['name']} | {fmt(c['per_year'], '.0f')} | {fmt(x['hours'], '.1f')} | "
                     f"{fmt(x['stop'], '.2f')} | {fmt(x['cost_r'], '.3f')} | {fmt(z['discovery']['mean'])} "
                     f"({fmt(z['discovery']['t'], '+.1f')}) | {fmt(z['confirm']['mean'])} | "
                     f"{fmt(f['discovery']['mean'])} | {fmt(c['mean'])} ({fmt(c['t'], '+.1f')}) | "
                     f"{fmt(c['pf'], '.2f')} | {fmt(c['total'], '+.1f')} | {c['years_positive']} of {c['years']} | "
                     f"{r['result']['verdict']} |")
    if len(drift):
        lines += ['', '## Drift by session and by weekday, zero cost (buy at the start, flat at the end)', '',
                  f'A row is traded as an idea only if its discovery t is at least {MAP_T:g} in size.', '',
                  '| Window | Discovery R (t) | Discovery $ per oz | Confirmation R (t) | Confirmation $ per oz |',
                  '|---|---|---|---|---|']
        for row in drift.itertuples():
            lines.append(f'| {row.name} | {fmt(row.r_d)} ({fmt(row.t_d, "+.1f")}) | {fmt(row.usd_d, "+.3f")} | '
                         f'{fmt(row.r_c)} ({fmt(row.t_c, "+.1f")}) | {fmt(row.usd_c, "+.3f")} |')
    spread = pd.Series(m1.spread, index=pd.to_datetime(m1.t, unit='s'))
    recent = spread[spread.index >= pd.Timestamp(screen.CONFIRM[0])]
    lines += ['', f'For scale: the median recorded spread in the confirmation years is ${recent.median():.2f} per oz. '
                  '"Spread cost (R)" is the zero-cost result minus the real-spread result in confirmation.', '',
              'Gold rose from about $1,280 to about $2,630 in the confirmation years and fell in the discovery '
              'years. A rule that is mostly long looks good in confirmation for that reason alone; the "always buy" '
              'row shows how much of a result is that drift.', '']
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--check', action='store_true', help='only prove that no idea reads a later candle')
    args = parser.parse_args()
    m1 = screen.load()
    print(f'gold M1: {len(m1):,} bars')
    if args.check:
        ok = check(m1)
        print('no idea reads a later candle' if ok else 'FAILED: see the lines above')
        sys.exit(0 if ok else 1)
    ideas, drift = all_ideas(m1)
    results = []
    for idea in ideas:
        result, extra = evaluate(m1, idea['signals'])
        results.append({'family': idea['family'], 'name': idea['name'], 'result': result, 'extra': extra})
        z, f = result[0.0], result[1.0]
        print(f"{idea['name']:<58} n/yr {f['confirm']['per_year']:5.0f}  zero {fmt(z['discovery']['mean'])} / "
              f"{fmt(z['confirm']['mean'])}  real {fmt(f['discovery']['mean'])} / {fmt(f['confirm']['mean'])}  "
              f"{result['verdict']}")
        sys.stdout.flush()
    args.report.write_text(report(results, drift, m1), encoding='utf-8', newline='\n')
    print(f'report -> {args.report}')


if __name__ == '__main__':
    main()
