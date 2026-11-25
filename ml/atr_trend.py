"""ATR Trend Confluence System (web/trend.py, tradingview/atr_trend_confluence.pine) through the idea screen.

    python -m ml.atr_trend             # run the filter ladder on development gold, write ml/reports/xauusd_atr_trend_screen.md
    python -m ml.atr_trend --check     # prove no rule reads a later candle, and that this file agrees with web/trend.py

The indicator marks the bar on which a Supertrend stop (ATR 14 x 2.8) flips, and keeps the label only when its
filters agree. It has no exits of its own, so the trade is defined here, before the first run:

  entry   the M1 open right after the signal bar closes, in the direction of the flip
  stop    the stop line on the signal bar (the indicator's own invalidation), at least 1 ATR away
  exits   "2R target": target at 2 x the stop distance, held at most 4 h (M1), 24 h (M5) or 48 h (M15)
          "trail":     no target; out at the close of the bar on which the stop flips back, at most 8 h / 48 h / 120 h

The ladder adds one filter at a time, as the write-up's section 9 asks, from every flip (the plain Buy/Sell labels of
this indicator family) to everything at once. Each filter is also tried alone on top of every flip, so a filter that
helps shows up even if the ladder reaches it with too few trades left. Inputs are the script's defaults; nothing is
tuned. The pass rule is ml.screen.RULE, unchanged. Only development data is loaded (the lockbox stays shut).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml import lockbox, screen
from ml.data import ROOT, Bars, resample
from ml.ideas import Frame, build, fmt
from web import trend as site
from web.trend import HTF, SESSIONS, TrendConfig

REPORT = ROOT / 'ml' / 'reports' / 'xauusd_atr_trend_screen.md'
INF = float('inf')
TIMEFRAMES = (('M1', 60, 240, 480), ('M5', 300, 1440, 2880), ('M15', 900, 2880, 7200))   # name, seconds, hold with a target, cap of the trail (minutes)
EXITS = ('2R target', 'trail')
TARGET_R = 2.0
MIN_STOP_ATR = 1.0
LADDER = (
    ('0', 'Every stop flip (the plain Buy/Sell labels)', ()),
    ('A0', '0 + price on the right side of a sloping EMA50', ('base',)),
    ('A', 'A0 + within 1 ATR of the EMA50 (the script with every toggle off)', ('base', 'near')),
    ('B', 'A + 1h EMA50/200 trend', ('base', 'near', 'htf')),
    ('C', 'B + Choppiness below 55', ('base', 'near', 'htf', 'chop')),
    ('D', 'C + ADX at least 20 with DI on side', ('base', 'near', 'htf', 'chop', 'adx')),
    ('E', 'D + break of structure in the last 8 bars', ('base', 'near', 'htf', 'chop', 'adx', 'bos')),
    ('F', 'E + London / New York morning', ('base', 'near', 'htf', 'chop', 'adx', 'bos', 'session')),
    ('site', 'As on the website: F without the structure filter', ('base', 'near', 'htf', 'chop', 'adx', 'session')),
)
SOLO = (('htf', '0 + 1h EMA50/200 trend only'), ('chop', '0 + Choppiness below 55 only'), ('adx', '0 + ADX and DI only'),
        ('bos', '0 + break of structure only'), ('session', '0 + London / New York morning only'),
        ('near', '0 + within 1 ATR of the EMA50 only'))
BLOCKS = {'base': 'baseline_not_aligned', 'htf': 'htf_not_aligned', 'adx': 'adx_weak_or_against', 'chop': 'choppy',
          'session': 'outside_session', 'bos': 'no_recent_bos', 'near': 'extended_from_baseline'}
TWO_SIDED = ('base', 'htf', 'adx', 'bos')


def rma(x, n: int) -> np.ndarray:
    return pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()


def ema(x, n: int) -> np.ndarray:
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def supertrend(h: np.ndarray, l: np.ndarray, c: np.ndarray, atr: np.ndarray, mult: float) -> tuple[np.ndarray, np.ndarray]:
    """web.trend.supertrend on arrays: the line and its direction (-1 = uptrend). The band logic is sequential."""
    mid = (h + l) / 2
    ups, lows, closes = (mid + mult * atr).tolist(), (mid - mult * atr).tolist(), c.tolist()
    n = len(closes)
    line, direction = [0.0] * n, [1] * n
    upper, lower, state = ups[0], lows[0], 1
    line[0] = upper
    for i in range(1, n):
        previous = closes[i - 1]
        if lows[i] > lower or previous < lower:
            lower = lows[i]
        if ups[i] < upper or previous > upper:
            upper = ups[i]
        if state == 1:
            state = -1 if closes[i] > upper else 1
        else:
            state = 1 if closes[i] < lower else -1
        direction[i] = state
        line[i] = lower if state == -1 else upper
    return np.array(line), np.array(direction, dtype=np.int8)


def features(m1: Bars, f: Frame, cfg: TrendConfig = TrendConfig()) -> pd.DataFrame:
    """One row per bar: the stop line, the flip (+1 buy, -1 sell, 0 none) and every filter, as web.trend.evaluate."""
    b = f.bars
    t, h, l, c = b.t, b.h, b.l, b.c
    n = len(b)
    previous = np.concatenate([[c[0]], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - previous), np.abs(l - previous)))
    base = ema(c, cfg.base_len)
    base_before = np.concatenate([[np.nan], base[:-1]])
    atr = rma(tr, cfg.st_len)
    line, direction = supertrend(h, l, c, atr, cfg.st_mult)
    flip = np.zeros(n, dtype=np.int8)
    flip[1:] = np.where(direction[1:] != direction[:-1], -direction[1:], 0)

    up, down = np.diff(h, prepend=h[0]), -np.diff(l, prepend=l[0])
    plus, minus = np.where((up > down) & (up > 0), up, 0.0), np.where((down > up) & (down > 0), down, 0.0)
    smooth = rma(tr, cfg.di_len)
    with np.errstate(divide='ignore', invalid='ignore'):
        plus_di = np.where(smooth > 0, 100 * rma(plus, cfg.di_len) / smooth, 0.0)
        minus_di = np.where(smooth > 0, 100 * rma(minus, cfg.di_len) / smooth, 0.0)
        total = plus_di + minus_di
        adx = rma(np.where(total > 0, 100 * np.abs(plus_di - minus_di) / total, 0.0), cfg.di_len)
        span = (pd.Series(h).rolling(cfg.chop_len).max() - pd.Series(l).rolling(cfg.chop_len).min()).to_numpy()
        tr_sum = pd.Series(tr).rolling(cfg.chop_len).sum().to_numpy()
        chop = np.where((span > 0) & (tr_sum > 0), 100 * np.log10(tr_sum / span) / np.log10(cfg.chop_len), np.nan)

    stamp = pd.to_datetime(t, unit='s', utc=True)
    session = np.zeros(n, dtype=bool)
    for _, zone, start, end in SESSIONS:
        local = stamp.tz_convert(zone)
        session |= (np.asarray(local.weekday) < 5) & (np.asarray(local.hour) >= start) & (np.asarray(local.hour) < end)

    if f.seconds < HTF:
        hour = resample(m1, HTF)
        fast, slow = ema(hour.c, cfg.htf_fast), ema(hour.c, cfg.htf_slow)
        k = np.searchsorted(hour.t, t - t % HTF) - 1          # the 1h candle that had closed when this bar opened
        seen, k = k >= 0, np.maximum(k, 0)
        htf_buy = seen & (hour.c[k] > fast[k]) & (fast[k] > slow[k])
        htf_sell = seen & (hour.c[k] < fast[k]) & (fast[k] < slow[k])
    else:
        htf_buy = htf_sell = np.ones(n, dtype=bool)

    p, where = cfg.pivot_len, np.arange(n)
    highs, lows, close = pd.Series(h), pd.Series(l), pd.Series(c)

    def breaks(series: pd.Series, top: bool) -> np.ndarray:
        left = series.shift(1).rolling(p)
        right = series[::-1].shift(1).rolling(p)
        pivot = ((series > left.max()) & (series >= right.max()[::-1])) if top else ((series < left.min()) & (series <= right.min()[::-1]))
        value = series.where(pivot).shift(p)                  # known p bars after the swing formed
        level = value.ffill()
        since = pd.Series(np.where(value.notna(), where, np.nan)).ffill()
        crossed = (close > level) & (close.shift(1) <= level.shift(1)) if top else (close < level) & (close.shift(1) >= level.shift(1))
        hit = (crossed & (where > since)).astype(float)
        return (hit.rolling(cfg.bos_lookback + 1, min_periods=1).max() > 0).to_numpy()

    return pd.DataFrame({
        't': t, 'c': c, 'atr': atr, 'line': line, 'flip': flip, 'entry': f.entry,
        'base_buy': (c > base) & (base > base_before), 'base_sell': (c < base) & (base < base_before),
        'htf_buy': htf_buy, 'htf_sell': htf_sell,
        'adx_buy': (adx >= cfg.adx_min) & (plus_di > minus_di), 'adx_sell': (adx >= cfg.adx_min) & (minus_di > plus_di),
        'bos_buy': breaks(highs, True), 'bos_sell': breaks(lows, False),
        'chop': chop < cfg.max_chop, 'session': session, 'near': np.abs(c - base) <= atr * cfg.max_extension})


def signals(d: pd.DataFrame, filters: tuple[str, ...], exit_kind: str, seconds: int, hold: int, cap: int) -> pd.DataFrame:
    """Screen entries for the flips that pass `filters`."""
    buy, sell = (d['flip'] > 0).to_numpy(), (d['flip'] < 0).to_numpy()
    for name in filters:
        if name in TWO_SIDED:
            buy, sell = buy & d[f'{name}_buy'].to_numpy(), sell & d[f'{name}_sell'].to_numpy()
        else:
            buy, sell = buy & d[name].to_numpy(), sell & d[name].to_numpy()
    mask = (buy | sell) & (d['entry'].to_numpy() >= 0)
    stop = np.maximum(np.abs(d['c'] - d['line']), MIN_STOP_ATR * d['atr']).to_numpy()
    if exit_kind == 'trail':
        # Out when the stop flips back: the next flip of any kind, since flips alternate.
        t, n = d['t'].to_numpy(), len(d)
        nxt = np.where(d['flip'].to_numpy() != 0, np.arange(n), n)
        nxt = np.minimum.accumulate(nxt[::-1])[::-1]
        nxt = np.concatenate([nxt[1:], [n]])
        minutes = np.where(nxt < n, (t[np.minimum(nxt, n - 1)] - t) // 60, cap)
        held, target = np.clip(minutes, seconds // 60, cap), np.full(n, INF)
    else:
        held, target = np.full(len(d), hold), TARGET_R * stop
    out = pd.DataFrame({'i': d['entry'].to_numpy()[mask], 'side': np.where(buy, 1.0, -1.0)[mask], 'stop': stop[mask],
                        'target': target[mask], 'hold': held[mask].astype(np.int64)})
    return out[(out['stop'] > 0) & np.isfinite(out['stop'])].reset_index(drop=True)


def run(m1: Bars, sig: pd.DataFrame, cost: float) -> pd.DataFrame:
    """screen.run with the chunk sized to the longest hold, so day-long trails fit in memory."""
    if len(sig) == 0:
        return pd.DataFrame({'entry_t': [], 'exit_t': [], 'side': [], 'r': [], 'kind': [], 'resolved': [], 'stop': []})
    sig = sig.sort_values('i', kind='stable')
    out = screen.simulate(m1, sig['i'].to_numpy(), sig['side'].to_numpy(), sig['stop'].to_numpy(), sig['target'].to_numpy(),
                          sig['hold'].to_numpy(), cost, chunk=max(100, 4_000_000 // int(sig['hold'].max())))
    out['stop'] = sig['stop'].to_numpy()
    out = out[out['resolved']].reset_index(drop=True)
    return out[screen.non_overlapping(out['entry_t'].to_numpy(), out['exit_t'].to_numpy())].reset_index(drop=True)


def evaluate(m1: Bars, sig: pd.DataFrame) -> tuple[dict, dict]:
    result, extra = {}, {'hours': np.nan, 'stop': np.nan, 'spread': np.nan}
    for cost in screen.COSTS:
        trades = run(m1, sig, cost)
        result[cost] = {'discovery': screen.stats(screen.window(trades, screen.DISCOVERY)),
                        'confirm': screen.stats(screen.window(trades, screen.CONFIRM))}
        if cost == 1.0 and len(trades):
            extra['hours'] = float(((trades['exit_t'] - trades['entry_t']) / 3600).median())
            extra['stop'] = float(trades['stop'].median())
    result['verdict'] = screen.verdict(result)
    return result, extra


def variants() -> list[tuple[str, str, tuple[str, ...]]]:
    return list(LADDER) + [(f'0+{name}', label, (name,)) for name, label in SOLO]


def all_runs(m1: Bars, log=print) -> list[dict]:
    out = []
    for name, seconds, hold, cap in TIMEFRAMES:
        d = features(m1, build(m1, seconds))
        log(f'{name}: {len(d):,} bars, {int((d["flip"] != 0).sum()):,} stop flips')
        for exit_kind in EXITS:
            for key, label, filters in variants():
                out.append({'tf': name, 'exit': exit_kind, 'key': key, 'label': label, 'filters': filters,
                            'signals': signals(d, filters, exit_kind, seconds, hold, cap)})
    return out


def check(m1: Bars, log=print) -> bool:
    """Two proofs. (1) Entries built from history cut at a random minute equal those built with the future present.
    (2) On real candles this file marks the same flips and filter states as web/trend.py, the engine on the website."""
    ok = True
    frames = {name: (seconds, hold, cap) for name, seconds, hold, cap in TIMEFRAMES}
    rng = np.random.default_rng(11)
    for name in ('M5', 'M15'):
        seconds, hold, cap = frames[name]
        full = features(m1, build(m1, seconds))
        for k in sorted(rng.integers(len(m1) // 2, len(m1) - 1, 3)):
            part_m1 = m1.slice(0, int(k))
            part = features(part_m1, build(part_m1, seconds))
            for key, _, filters in variants():
                want = signals(full, filters, '2R target', seconds, hold, cap)
                want = want[want['i'] < k].reset_index(drop=True)
                got = signals(part, filters, '2R target', seconds, hold, cap)
                if len(want) != len(got) or not np.allclose(want.to_numpy(float), got.to_numpy(float)):
                    ok = False
                    log(f'LOOKAHEAD {name} rung {key} at cut {k}: {len(want)} entries with the future, {len(got)} without')
            log(f'{name}: cut at M1 bar {k:,}, {len(variants())} rungs agree')
    lo = len(m1) - 60 * 1440
    window = m1.slice(lo, len(m1))
    mine = features(window, build(window, 300)).set_index('t')
    rows = site.evaluate(window.dicts(0, len(window)), 300, TrendConfig(use_bos=True))
    flips = differ = states = 0
    for row in rows[len(rows) // 4:]:                         # past both engines' warmup
        m = mine.loc[row['t']]
        flips += row['flip'] is not None
        if {1: 'BUY', -1: 'SELL', 0: None}[int(m['flip'])] != row['flip']:
            differ += 1
        for name, reason in BLOCKS.items():
            for side, blocked in (('buy', row['buy_blocked']), ('sell', row['sell_blocked'])):
                passes = bool(m[f'{name}_{side}'] if name in TWO_SIDED else m[name])
                states += 1
                differ += passes == (reason in blocked)
    log(f'website engine, last 60 days of M5: {flips} flips, {states:,} filter states compared, {differ} differences')
    return ok and differ == 0


def table(rows: list[dict], tf: str, exit_kind: str) -> list[str]:
    lines = [f'### {tf}, {exit_kind}', '',
             '| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |',
             '|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        if r['tf'] != tf or r['exit'] != exit_kind:
            continue
        zero, real = r['result'][0.0], r['result'][1.0]
        lines.append(f"| {r['key']} | {r['label']} | {real['confirm']['per_year']:.0f} | {fmt(zero['discovery']['mean'])} "
                     f"(t {fmt(zero['discovery']['t'], '+.1f')}) | {fmt(zero['confirm']['mean'])} | {fmt(real['discovery']['mean'])} | "
                     f"{fmt(real['confirm']['mean'])} | {fmt(real['confirm']['pf'], '.2f')} | {r['result']['verdict']} |")
    sample = next((r for r in rows if r['tf'] == tf and r['exit'] == exit_kind and r['key'] == '0'), None)
    if sample:
        lines += ['', f"Median stop ${sample['extra']['stop']:.2f} per oz, median hold {sample['extra']['hours']:.1f} h (rung 0)."]
    return lines + ['']


def report(rows: list[dict], m1: Bars) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    first = datetime.fromtimestamp(int(m1.t[0]), timezone.utc).date()
    last = datetime.fromtimestamp(int(m1.t[-1]), timezone.utc).date()
    rule = screen.RULE
    passed = [r for r in rows if r['result']['verdict'] == 'PASSED']
    counts = pd.Series([r['result']['verdict'] for r in rows]).value_counts()
    lines = [f'# XAUUSD ATR Trend Confluence screen ({stamp})', '',
             'The indicator on the website (web/trend.py, tradingview/atr_trend_confluence.pine): EMA50 baseline, Supertrend '
             'stop ATR 14 x 2.8, a label where the stop flips, filtered. Script defaults, nothing tuned.', '',
             f'Development gold only (Dukascopy M1 {first} .. {last}; nothing from {lockbox.LOCK_START} on is loaded). '
             f'Discovery {screen.DISCOVERY[0]} to {screen.DISCOVERY[1]}, confirmation {screen.CONFIRM[0]} to {screen.CONFIRM[1]}. '
             'One position at a time. R = result divided by the stop distance. Numbers are mean R per trade.', '',
             'Trade, fixed before the run: enter at the M1 open after the signal bar closes; stop at the stop line (at least '
             '1 ATR away); exit either at a 2R target (held at most 4 h on M1, 24 h on M5, 48 h on M15) or, for "trail", '
             'when the stop flips back (at most 8 h / 48 h / 120 h).', '',
             f'Pass rule (ml.screen.RULE, unchanged): at zero cost in discovery mean R >= {rule["zero_cost_discovery_r"]:+.2f} with '
             f't >= {rule["zero_cost_discovery_t"]:g} and at least 100 trades; at the recorded spread in discovery mean R > 0; then '
             f'in confirmation at the recorded spread mean R >= {rule["confirm_r"]:+.2f}, profit factor >= {rule["confirm_pf"]:g}, '
             f'{rule["confirm_years_positive"]:.0%} of years positive and at least {rule["confirm_trades_per_year"]} trades a year.', '',
             f'**{len(rows)} tests, {len(passed)} passed.**', '',
             '| Verdict | Tests |', '|---|---|'] + [f'| {k} | {v} |' for k, v in counts.items()] + ['']
    for name, *_ in TIMEFRAMES:
        for exit_kind in EXITS:
            lines += table(rows, name, exit_kind)
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--report', type=Path, default=REPORT)
    parser.add_argument('--check', action='store_true', help='only run the lookahead and website-parity proofs')
    args = parser.parse_args()
    m1 = screen.load()
    print(f'gold M1: {len(m1):,} bars')
    if args.check:
        ok = check(m1)
        print('no rule reads a later candle, and the screen matches the website engine' if ok else 'FAILED: see the lines above')
        sys.exit(0 if ok else 1)
    rows = all_runs(m1)
    for row in rows:
        row['result'], row['extra'] = evaluate(m1, row.pop('signals'))
        zero, real = row['result'][0.0], row['result'][1.0]
        print(f"{row['tf']:<3} {row['exit']:<9} {row['key']:<10} n/yr {real['confirm']['per_year']:6.0f}  zero {fmt(zero['discovery']['mean'])} / "
              f"{fmt(zero['confirm']['mean'])}  real {fmt(real['discovery']['mean'])} / {fmt(real['confirm']['mean'])}  {row['result']['verdict']}")
        sys.stdout.flush()
    args.report.write_text(report(rows, m1), encoding='utf-8', newline='\n')
    print(f'report -> {args.report}')


if __name__ == '__main__':
    main()
