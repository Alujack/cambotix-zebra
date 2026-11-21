"""Scalping and intraday ideas for the screen (ml/screen.py). Every rule and parameter here was written before the
first run; the screen decides, nothing is tuned afterwards.

    python -m ml.ideas                 # run every idea on development gold, write ml/reports/xauusd_idea_screen.md

Each idea returns entries: i (M1 bar whose open is the fill, always after the signal bar closed), side, stop and
target distances in price, hold in minutes. ATR is Wilder 14 on the signal timeframe. Times are New York.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml import lockbox, screen
from ml.data import LOCAL, ROOT, Bars, load_m1, resample
from ml.ict_features import trading_days

REPORT = ROOT / 'ml' / 'reports' / 'xauusd_idea_screen.md'
INF = float('inf')
EURUSD_FOLDER = LOCAL / 'history_dukascopy6y'
LEAD_DISCOVERY = ('2020-12-01', '2023-01-01')
LEAD_CONFIRM = ('2023-01-01', lockbox.LOCK_START)
HOUR_T = 2.5                    # an hour is traded only if its discovery drift has |t| >= this


@dataclass
class Frame:
    """One timeframe built from M1, with the M1 bar that opens right after each bar closes."""
    bars: Bars
    atr: np.ndarray
    minute: np.ndarray          # New York minute of the day at the bar open
    weekday: np.ndarray
    day: np.ndarray             # trading day, changes at 17:00 New York
    entry: np.ndarray           # M1 index of the next open, -1 when the market is closed then
    seconds: int

    def frame(self) -> pd.DataFrame:
        b = self.bars
        return pd.DataFrame({'t': b.t, 'o': b.o, 'h': b.h, 'l': b.l, 'c': b.c, 'atr': self.atr, 'minute': self.minute,
                             'weekday': self.weekday, 'day': self.day, 'entry': self.entry})


def wilder_atr(bars: Bars, n: int = 14) -> np.ndarray:
    prev = np.concatenate([[bars.c[0]], bars.c[:-1]])
    tr = np.maximum(bars.h - bars.l, np.maximum(np.abs(bars.h - prev), np.abs(bars.l - prev)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def build(m1: Bars, seconds: int) -> Frame:
    bars = resample(m1, seconds)
    close_time = bars.t + seconds
    entry = np.searchsorted(m1.t, close_time)
    ok = entry < len(m1)
    ok[ok] &= (m1.t[entry[ok]] - close_time[ok]) < 300
    minute, weekday, day = trading_days(bars.t)
    return Frame(bars, wilder_atr(bars), minute, weekday, day, np.where(ok, entry, -1), seconds)


def entries(frame: pd.DataFrame, mask, side, stop, target, hold) -> pd.DataFrame:
    """Rows of `frame` where mask holds and an entry exists, as screen signals."""
    mask = np.asarray(mask, dtype=bool) & (frame['entry'].to_numpy() >= 0)
    stop = np.broadcast_to(np.asarray(stop, dtype=float), mask.shape)[mask]
    side = np.broadcast_to(np.asarray(side, dtype=float), mask.shape)[mask]
    target = np.broadcast_to(np.asarray(target, dtype=float), mask.shape)[mask]
    out = pd.DataFrame({'i': frame['entry'].to_numpy()[mask], 'side': side, 'stop': stop, 'target': target,
                        'hold': hold})
    good = (out['stop'] > 0) & np.isfinite(out['stop']) & np.isfinite(out['side']) & (out['side'] != 0)
    return out[good].reset_index(drop=True)


# -- 1. momentum or reversal after a move of L minutes --------------------------------------------------------
def move(f: Frame, minutes: int, z_min: float, follow: bool) -> pd.DataFrame:
    """M5: the last `minutes` moved at least z_min x (ATR x sqrt(bars)); enter with the move (follow) or against
    it. Stop 1.5 x that scale, target 1.5R, hold = the same number of minutes (at least 30)."""
    d = f.frame()
    k = minutes // 5
    scale = d['atr'] * np.sqrt(k)
    z = (d['c'] - d['c'].shift(k)) / scale
    fresh = (z.abs() >= z_min) & (z.shift(1).abs() < z_min)
    side = np.sign(z) * (1 if follow else -1)
    return entries(d, fresh.fillna(False), side.fillna(0), 1.5 * scale, 1.5 * 1.5 * scale, max(30, minutes))


# -- 2. Donchian channel break on M15 -------------------------------------------------------------------------
def channel(f: Frame, bars: int, follow: bool) -> pd.DataFrame:
    """M15: the first close beyond the highest high / lowest low of the previous `bars`. Stop 2 ATR, target 2R,
    hold 8 hours."""
    d = f.frame()
    hi, lo = d['h'].rolling(bars).max().shift(1), d['l'].rolling(bars).min().shift(1)
    up = (d['c'] > hi) & ~(d['c'].shift(1) > hi.shift(1))
    down = (d['c'] < lo) & ~(d['c'].shift(1) < lo.shift(1))
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    return entries(d, up | down, side, 2 * d['atr'], 4 * d['atr'], 480)


# -- 3. volatility squeeze, then a band break on M5 -----------------------------------------------------------
def squeeze(f: Frame, follow: bool) -> pd.DataFrame:
    """M5: Bollinger (20, 2) width in the lowest tenth of the last two days, then a close outside the band.
    Stop 1.5 ATR, target 2R, hold 2 hours."""
    d = f.frame()
    mid, sd = d['c'].rolling(20).mean(), d['c'].rolling(20).std()
    width = 4 * sd / mid
    tight = width.rolling(576).rank(pct=True).shift(1) <= 0.10
    up = tight & (d['c'] > mid + 2 * sd) & (d['c'].shift(1) <= (mid + 2 * sd).shift(1))
    down = tight & (d['c'] < mid - 2 * sd) & (d['c'].shift(1) >= (mid - 2 * sd).shift(1))
    side = (up.astype(float) - down.astype(float)) * (1 if follow else -1)
    return entries(d, up | down, side, 1.5 * d['atr'], 3 * d['atr'], 120)


# -- 4. round numbers -----------------------------------------------------------------------------------------
def round_number(f: Frame, step: float, breakout: bool) -> pd.DataFrame:
    """M5: a round level ($10 or $50) not touched in the previous hour. Breakout: close at least 0.2 ATR beyond
    it, enter with the break. Rejection: the bar trades through it and closes at least 0.2 ATR back, enter
    against. Stop 1.5 ATR, target 1.5R, hold 90 minutes."""
    d = f.frame()
    prev = d['c'].shift(1)
    above = np.floor(prev / step) * step + step          # nearest level above the previous close
    below = np.ceil(prev / step) * step - step           # nearest level below it
    quiet_up = d['h'].rolling(12).max().shift(1) < above
    quiet_down = d['l'].rolling(12).min().shift(1) > below
    edge = 0.2 * d['atr']
    if breakout:
        up = quiet_up & (d['c'] >= above + edge)
        down = quiet_down & (d['c'] <= below - edge)
        side = up.astype(float) - down.astype(float)
    else:
        up = quiet_up & (d['h'] >= above) & (d['c'] <= above - edge)
        down = quiet_down & (d['l'] <= below) & (d['c'] >= below + edge)
        side = down.astype(float) - up.astype(float)
    return entries(d, (up | down).fillna(False), side, 1.5 * d['atr'], 2.25 * d['atr'], 90)


# -- 5. previous day's high or low ----------------------------------------------------------------------------
def previous_day(f: Frame, follow: bool) -> pd.DataFrame:
    """M5: the first close of the trading day beyond the previous day's high or low. Stop 2 ATR, target 2R,
    hold 4 hours."""
    d = f.frame()
    daily = d.groupby('day').agg(high=('h', 'max'), low=('l', 'min')).shift(1)
    pdh, pdl = d['day'].map(daily['high']), d['day'].map(daily['low'])
    above, below = d['c'] > pdh, d['c'] < pdl
    first_up = above & (above.groupby(d['day']).cumsum() == 1)
    first_down = below & (below.groupby(d['day']).cumsum() == 1)
    side = (first_up.astype(float) - first_down.astype(float)) * (1 if follow else -1)
    return entries(d, first_up | first_down, side, 2 * d['atr'], 4 * d['atr'], 240)


# -- 6. the news clock ----------------------------------------------------------------------------------------
def news_clock(m1: Bars, f5: Frame, minute_of_day: int) -> pd.DataFrame:
    """M1: at 08:30 or 10:00 New York, take the high and low of the 15 minutes before. The first M1 close beyond
    that range in the next 15 minutes is followed. Stop at the other side of the range (at least 1 ATR of M5),
    target 1.5R, hold 60 minutes."""
    minute, weekday, _ = trading_days(m1.t)
    atr5 = pd.Series(f5.atr, index=f5.bars.t + 300)             # known from the bar's close on
    starts = np.flatnonzero((minute == minute_of_day) & (weekday < 5))
    rows = []
    for s in starts:
        if s < 15 or s + 16 >= len(m1) or m1.t[s] - m1.t[s - 15] != 900 or m1.t[s + 15] - m1.t[s] != 900:
            continue
        hi, lo = m1.h[s - 15:s].max(), m1.l[s - 15:s].min()
        closes = m1.c[s:s + 15]
        out = np.flatnonzero((closes > hi) | (closes < lo))
        if len(out) == 0:
            continue
        k = s + out[0]
        side = 1.0 if m1.c[k] > hi else -1.0
        a = atr5.asof(m1.t[k])
        if not np.isfinite(a):
            continue
        stop = max(a, (m1.c[k] - lo) if side > 0 else (hi - m1.c[k]))
        rows.append((k + 1, side, stop, 1.5 * stop, 60))
    return pd.DataFrame(rows, columns=['i', 'side', 'stop', 'target', 'hold'])


# -- 7. one session predicts the next -------------------------------------------------------------------------
def at_minute(d: pd.DataFrame, minute: int) -> pd.DataFrame:
    """Per trading day: the M5 bar that opens at this New York minute."""
    return d[d['minute'] == minute].drop_duplicates('day').set_index('day')


def session_follow(f: Frame, measure_from: int, measure_to: int, enter: int, hold: int, follow: bool,
                   next_day: bool = False) -> pd.DataFrame:
    """M5: the price change between two New York times of the trading day gives the side; enter at a third time
    (of the next trading day when next_day) and hold. Stop 3 x hourly ATR (ATR of M5 x sqrt(12)), no target."""
    d = f.frame()
    a, b = at_minute(d, measure_from), at_minute(d, measure_to)
    # The bar that closes at `enter` opens five minutes before; after the daily break the first bar is taken.
    e = at_minute(d, (enter - 5) % 1440)
    change = (b['o'] - a['o']).dropna()
    if next_day:
        days = pd.Series(sorted(d['day'].unique()))
        following = dict(zip(days[:-1], days[1:]))
        change.index = change.index.map(following)
        change = change[change.index.notna()]
        change.index = change.index.astype(np.int64)
    joined = e.join(change.rename('change'), how='inner')
    side = np.sign(joined['change']) * (1 if follow else -1)
    return entries(joined.reset_index(), np.ones(len(joined), dtype=bool), side.to_numpy(),
                   3 * joined['atr'].to_numpy() * np.sqrt(12), INF, hold)


# -- 8. pullback in the daily trend ---------------------------------------------------------------------------
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down)


def trend_pullback(f: Frame) -> pd.DataFrame:
    """M15: the daily trend is the previous day's close against the 50-day average of closes. In an uptrend buy
    when RSI(14) crosses under 30; in a downtrend sell when it crosses over 70. Stop 3 ATR, target 2R, hold 24h."""
    d = f.frame()
    daily = d.groupby('day')['c'].last()
    trend = np.sign(daily - daily.rolling(50).mean()).shift(1)
    side_day = d['day'].map(trend)
    value = rsi(d['c'])
    buy = (value < 30) & (value.shift(1) >= 30) & (side_day > 0)
    sell = (value > 70) & (value.shift(1) <= 70) & (side_day < 0)
    return entries(d, buy | sell, buy.astype(float) - sell.astype(float), 3 * d['atr'], 6 * d['atr'], 1440)


# -- 9. drift by hour of the day ------------------------------------------------------------------------------
def hour_trade(f: Frame, hour: int, side: float) -> pd.DataFrame:
    """Enter at the start of one New York hour every weekday, hold 60 minutes. Stop 3 x hourly ATR, no target."""
    d = f.frame()
    mask = (d['minute'] == (hour * 60 - 5) % 1440) & (d['weekday'] < 5)
    return entries(d, mask, side, 3 * d['atr'] * np.sqrt(12), INF, 60)


def hour_map(m1: Bars, f: Frame) -> pd.DataFrame:
    """Zero-cost hourly drift of buying each New York hour: discovery and confirmation, in R and in dollars."""
    rows = []
    for hour in range(24):
        sig = hour_trade(f, hour, 1.0)
        if len(sig) < 200:
            continue
        trades = screen.run(m1, sig, 0.0)
        trades['usd'] = trades['r'] * trades['stop']
        d, c = screen.window(trades, screen.DISCOVERY), screen.window(trades, screen.CONFIRM)
        sd, sc = screen.stats(d), screen.stats(c)
        rows.append({'hour': hour, 'n_d': sd['n'], 'r_d': sd['mean'], 't_d': sd['t'], 'usd_d': d['usd'].mean(),
                     'n_c': sc['n'], 'r_c': sc['mean'], 't_c': sc['t'], 'usd_c': c['usd'].mean()})
    return pd.DataFrame(rows)


# -- 10. EURUSD leads gold ------------------------------------------------------------------------------------
def lead_lag(gold: Frame, m1_eur: Bars, minutes: int, follow: bool) -> pd.DataFrame:
    """M5: EURUSD moved at least 2 x its own scale over `minutes` while gold moved less than 0.5 x its own. Buy
    gold when EURUSD rose (a weaker dollar), sell when it fell; `follow` False trades the opposite. Stop 1.5 ATR
    of gold M5, target 1.5R, hold 30 minutes."""
    eur = build(m1_eur, 300)
    k = minutes // 5
    e = pd.DataFrame({'t': eur.bars.t, 'c': eur.bars.c, 'atr': eur.atr})
    e['z_eur'] = (e['c'] - e['c'].shift(k)) / (e['atr'] * np.sqrt(k))
    d = gold.frame()
    d['z_gold'] = (d['c'] - d['c'].shift(k)) / (d['atr'] * np.sqrt(k))
    d = d.merge(e[['t', 'z_eur']], on='t', how='inner')
    mask = (d['z_eur'].abs() >= 2) & (d['z_gold'].abs() < 0.5)
    side = np.sign(d['z_eur']) * (1 if follow else -1)
    return entries(d, mask.fillna(False), side.fillna(0), 1.5 * d['atr'], 2.25 * d['atr'], 30)


# -- the list -------------------------------------------------------------------------------------------------
def all_ideas(m1: Bars, m1_eur: Bars | None = None, log=print) -> tuple[list[dict], pd.DataFrame]:
    m5, m15 = build(m1, 300), build(m1, 900)
    ideas: list[dict] = []

    def add(family, name, signals, periods=None):
        ideas.append({'family': family, 'name': name, 'signals': signals, 'periods': periods})

    for minutes in (5, 15, 60, 240):
        for z in (1.0, 2.0):
            add('Move, then follow it', f'{minutes} min move >= {z:g}, follow', move(m5, minutes, z, True))
            add('Move, then fade it', f'{minutes} min move >= {z:g}, fade', move(m5, minutes, z, False))
    for bars, label in ((20, '5 hour'), (96, '24 hour')):
        add('Channel break (M15)', f'{label} channel, follow', channel(m15, bars, True))
        add('Channel break (M15)', f'{label} channel, fade', channel(m15, bars, False))
    add('Squeeze break (M5)', 'squeeze, follow', squeeze(m5, True))
    add('Squeeze break (M5)', 'squeeze, fade', squeeze(m5, False))
    for step in (10.0, 50.0):
        add('Round numbers', f'${step:g} level, breakout', round_number(m5, step, True))
        add('Round numbers', f'${step:g} level, rejection', round_number(m5, step, False))
    add('Previous day high/low', 'first close beyond, follow', previous_day(m5, True))
    add('Previous day high/low', 'first close beyond, fade', previous_day(m5, False))
    add('News clock', '08:30 range break', news_clock(m1, m5, 8 * 60 + 30))
    add('News clock', '10:00 range break', news_clock(m1, m5, 10 * 60))
    sessions = (('Asia -> London', 18 * 60, 3 * 60, 3 * 60, 300, False),
                ('overnight -> New York', 18 * 60, 8 * 60 + 30, 8 * 60 + 30, 300, False),
                ('COMEX first 30 min -> last hour', 8 * 60 + 20, 8 * 60 + 50, 12 * 60 + 30, 60, False),
                ('New York day -> next Asia', 8 * 60, 16 * 60 + 55, 18 * 60 + 5, 480, True))
    for label, a, b, enter, hold, next_day in sessions:
        add('One session predicts the next', f'{label}, follow', session_follow(m5, a, b, enter, hold, True, next_day))
        add('One session predicts the next', f'{label}, fade', session_follow(m5, a, b, enter, hold, False, next_day))
    add('Daily trend pullback (M15)', 'RSI 30/70 with the daily trend', trend_pullback(m15))

    log('hourly drift map ...')
    hours = hour_map(m1, m5)
    for row in hours.itertuples():
        if abs(row.t_d) >= HOUR_T:
            side = 1.0 if row.t_d > 0 else -1.0
            add('Hour of the day', f"{'buy' if side > 0 else 'sell'} the {row.hour:02d}:00 hour",
                hour_trade(m5, row.hour, side))

    if m1_eur is not None:
        for minutes in (5, 15):
            add('EURUSD leads gold (2020-12 on)', f'EURUSD {minutes} min move, gold follows',
                lead_lag(m5, m1_eur, minutes, True), (LEAD_DISCOVERY, LEAD_CONFIRM))
            add('EURUSD leads gold (2020-12 on)', f'EURUSD {minutes} min move, gold opposite',
                lead_lag(m5, m1_eur, minutes, False), (LEAD_DISCOVERY, LEAD_CONFIRM))
    return ideas, hours


def fmt(x, spec='+.3f') -> str:
    return '-' if x is None or not np.isfinite(x) else format(x, spec)


def report(results: list[dict], hours: pd.DataFrame, m1: Bars) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    first = datetime.fromtimestamp(int(m1.t[0]), timezone.utc).date()
    last = datetime.fromtimestamp(int(m1.t[-1]), timezone.utc).date()
    rule = screen.RULE
    passed = [r for r in results if r['result']['verdict'] == 'PASSED']
    lines = [f'# XAUUSD idea screen ({stamp})', '',
             f'Development gold only (Dukascopy M1 {first} .. {last}; nothing from {lockbox.LOCK_START} on is loaded). '
             f'Discovery {screen.DISCOVERY[0]} to {screen.DISCOVERY[1]}, confirmation {screen.CONFIRM[0]} to '
             f'{screen.CONFIRM[1]}. One position at a time per idea. R = result divided by the stop distance. '
             'Costs: zero spread, half the recorded spread, the recorded spread.', '',
             f'Pass rule, fixed before the run: at zero cost in discovery mean R >= {rule["zero_cost_discovery_r"]:+.2f} '
             f'with t >= {rule["zero_cost_discovery_t"]:g}; at the recorded spread in discovery mean R > 0; then in '
             f'confirmation at the recorded spread mean R >= {rule["confirm_r"]:+.2f}, profit factor >= '
             f'{rule["confirm_pf"]:g}, {rule["confirm_years_positive"]:.0%} of years positive and at least '
             f'{rule["confirm_trades_per_year"]} trades a year.', '',
             f'**{len(results)} ideas tested, {len(passed)} passed.**', '']
    counts = pd.Series([r['result']['verdict'] for r in results]).value_counts()
    lines += ['| Verdict | Ideas |', '|---|---|'] + [f'| {k} | {v} |' for k, v in counts.items()] + ['']
    lines += ['## Every idea', '',
              '| Family | Idea | Trades a year | Zero cost: discovery R (t) | Zero cost: confirmation R | '
              'Half spread: confirmation R | Real spread: discovery R | Real spread: confirmation R | '
              'Confirmation PF | Years positive | Verdict |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in results:
        z, h, f = r['result'][0.0], r['result'][0.5], r['result'][1.0]
        c = f['confirm']
        lines.append(f"| {r['family']} | {r['name']} | {fmt(c['per_year'], '.0f')} | "
                     f"{fmt(z['discovery']['mean'])} ({fmt(z['discovery']['t'], '+.1f')}) | {fmt(z['confirm']['mean'])} | "
                     f"{fmt(h['confirm']['mean'])} | {fmt(f['discovery']['mean'])} | {fmt(c['mean'])} | "
                     f"{fmt(c['pf'], '.2f')} | {c['years_positive']} of {c['years']} | {r['result']['verdict']} |")
    lines += ['', '## Drift by New York hour, zero cost (buy at the start of the hour, hold 60 minutes)', '',
              f'An hour is traded as an idea only if its discovery t is at least {HOUR_T:g} in size.', '',
              '| Hour | Discovery R (t) | Discovery $ per oz | Confirmation R (t) | Confirmation $ per oz |',
              '|---|---|---|---|---|']
    for row in hours.itertuples():
        lines.append(f'| {row.hour:02d}:00 | {fmt(row.r_d)} ({fmt(row.t_d, "+.1f")}) | {fmt(row.usd_d, "+.3f")} | '
                     f'{fmt(row.r_c)} ({fmt(row.t_c, "+.1f")}) | {fmt(row.usd_c, "+.3f")} |')
    spread = pd.Series(m1.spread, index=pd.to_datetime(m1.t, unit='s'))
    recent = spread[spread.index >= pd.Timestamp(screen.CONFIRM[0])]
    lines += ['', f'For scale: the median recorded spread in the confirmation years is ${recent.median():.2f} per oz.', '']
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--no-eurusd', action='store_true')
    args = parser.parse_args()
    m1 = screen.load()
    print(f'gold M1: {len(m1):,} bars')
    m1_eur = None
    if not args.no_eurusd and (EURUSD_FOLDER / 'EURUSD_m1.csv').exists():
        m1_eur = load_m1('EURUSD', EURUSD_FOLDER, None, lockbox.LOCK_EPOCH)
        print(f'EURUSD M1: {len(m1_eur):,} bars')
    ideas, hours = all_ideas(m1, m1_eur)
    results = []
    for idea in ideas:
        periods = idea['periods'] or (screen.DISCOVERY, screen.CONFIRM)
        result = screen.evaluate(m1, idea['signals'], *periods)
        results.append({'family': idea['family'], 'name': idea['name'], 'result': result})
        z, f = result[0.0], result[1.0]
        print(f"{idea['name']:<48} n/yr {f['confirm']['per_year']:6.0f}  zero {fmt(z['discovery']['mean'])} / "
              f"{fmt(z['confirm']['mean'])}  real {fmt(f['discovery']['mean'])} / {fmt(f['confirm']['mean'])}  "
              f"{result['verdict']}")
        sys.stdout.flush()
    args.report.write_text(report(results, hours, m1), encoding='utf-8', newline='\n')
    print(f'report -> {args.report}')


if __name__ == '__main__':
    main()
