"""Test of the smart-money-concepts library (github.com/joshyattridge/smart-money-concepts, v0.0.27) on gold.

    pip install smartmoneyconcepts --no-deps        # or put a clone of the repository on PYTHONPATH
    python -m ml.smc_test --replay                  # slow: the library is called once per bar (about 50 minutes)
    python -m ml.smc_test                           # trades and report: ml/reports/xauusd_smc_library_test.md

The library draws swings, break of structure (BOS), change of character (CHoCH), order blocks, liquidity and fair
value gaps on a finished chart. Three of those need candles that come after the signal bar (a swing needs
`swing_length` later candles, a BOS is only kept once a later swing confirms it, the liquidity range uses the
whole chart). So the test is done twice:

    live      the library only ever sees candles up to "now" (a window ending at the current closed bar), and a
              signal is whatever it reports for that last bar. This is what a bot running the library would trade.
    hindsight the library is run once over a finished chart of 2,000 candles and every signal is traded at the bar
              it is drawn on. This is how the indicators look on a chart and how they are usually backtested.

Trades go through ml/screen.py (zero, half and recorded spread; discovery and confirmation years; development
data only). Every rule below was fixed before the first run.
"""
from __future__ import annotations

import argparse
import multiprocessing as mp
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from ml import lockbox, screen
from ml.data import LOCAL, ROOT
from ml.ideas import build, fmt

EVENTS = LOCAL / 'smc_events'
REPORT = ROOT / 'ml' / 'reports' / 'xauusd_smc_library_test.md'
# (timeframe seconds, swing_length, window of candles the library sees live)
CONFIGS = ((300, 5, 200), (300, 20, 400), (900, 20, 400), (900, 50, 600))
REPLAY_FROM = '2010-12-15'
CHUNK = 4000
HINDSIGHT_CHART = 2000
STOP_ATR, TARGET_R, HOLD_BARS = 2.0, 2.0, 48
STRUCTURE_MEMORY = 48            # bars a BOS/CHoCH stays "the current structure" for the combined entries
FVG_TAIL = 1000                  # a fair value gap is followed for at most this many bars
G = None                         # the candles of one timeframe, set in each worker


def frame_of(seconds: int):
    m1 = screen.load()
    f = build(m1, seconds)
    b = f.bars
    return m1, f, pd.DataFrame({'open': b.o, 'high': b.h, 'low': b.l, 'close': b.c, 'volume': 1.0})


def _init(seconds: int) -> None:
    global G
    G = frame_of(seconds)[2]


def _replay(task: tuple[int, int, int, int]) -> list[tuple]:
    """Live replay of bars lo..hi-1: at each bar the library sees the last `window` candles and nothing later."""
    from smartmoneyconcepts import smc
    lo, hi, swing, window = task
    high, low, close = G['high'].to_numpy(), G['low'].to_numpy(), G['close'].to_numpy()
    events, known, fired = [], set(), set()
    for g in range(max(lo - window, window - 1), hi):
        start = g - window + 1
        w = G.iloc[start:g + 1].reset_index(drop=True)
        live = g >= lo
        try:
            swings = smc.swing_highs_lows(w, swing_length=swing)
            blocks = smc.ob(w, swings)
            if live:
                structure = smc.bos_choch(w, swings)
                pools = smc.liquidity(w, swings)
        except Exception:                                   # the library fails on a few degenerate windows
            if live:
                events.append((g, 'error', 0))
            continue
        # Order blocks: one that was already on the chart before this bar, touched now without closing through.
        for row in np.flatnonzero(blocks['OB'].notna().to_numpy()):
            side = int(blocks['OB'].iat[row])
            key = (start + int(row), side)
            top, bottom = float(blocks['Top'].iat[row]), float(blocks['Bottom'].iat[row])
            upper, lower = max(top, bottom), min(top, bottom)
            if key in known and key not in fired:
                touched = (low[g] <= upper and close[g] >= lower) if side > 0 else (high[g] >= lower and close[g] <= upper)
                if touched:
                    fired.add(key)
                    if live:
                        events.append((g, 'ob_retest', side))
            known.add(key)
        if not live:
            continue
        now = structure[structure['BrokenIndex'] == window - 1]
        for row in now.itertuples():
            if np.isfinite(row.BOS):
                events.append((g, 'bos', int(row.BOS)))
            if np.isfinite(row.CHOCH):
                events.append((g, 'choch', int(row.CHOCH)))
        for row in pools[pools['Swept'] == window - 1].itertuples():
            events.append((g, 'liq_sweep', int(row.Liquidity)))
    return events


def replay(seconds: int, swing: int, window: int, processes: int, log=print) -> Path:
    m1, f, df = frame_of(seconds)
    first = int(np.searchsorted(f.bars.t, screen.epoch(REPLAY_FROM)))
    tasks = [(lo, min(lo + CHUNK, len(df)), swing, window) for lo in range(first, len(df), CHUNK)]
    started, rows = time.time(), []
    with mp.Pool(processes, initializer=_init, initargs=(seconds,)) as pool:
        for done, part in enumerate(pool.imap_unordered(_replay, tasks), 1):
            rows += part
            if done % 20 == 0 or done == len(tasks):
                log(f'  {seconds // 60}m swing {swing}: {done}/{len(tasks)} chunks, {len(rows):,} events, '
                    f'{(time.time() - started) / 60:.1f} min')
                sys.stdout.flush()
    out = pd.DataFrame(rows, columns=['g', 'kind', 'side']).sort_values(['g', 'kind']).reset_index(drop=True)
    EVENTS.mkdir(parents=True, exist_ok=True)
    path = EVENTS / f'XAUUSD_{seconds}_{swing}_{window}.parquet'
    out.to_parquet(path, index=False)
    return path


def hindsight(df: pd.DataFrame, swing: int, first: int) -> pd.DataFrame:
    """The library run once per finished chart of HINDSIGHT_CHART candles; signals at the bar they are drawn on."""
    from smartmoneyconcepts import smc
    rows = []
    for lo in range(first, len(df) - HINDSIGHT_CHART, HINDSIGHT_CHART):
        w = df.iloc[lo:lo + HINDSIGHT_CHART].reset_index(drop=True)
        try:
            swings = smc.swing_highs_lows(w, swing_length=swing)
            structure = smc.bos_choch(w, swings).dropna(subset=['BrokenIndex'])
            pools = smc.liquidity(w, swings)
        except Exception:
            continue
        for row in structure.itertuples():
            if np.isfinite(row.BOS):
                rows.append((lo + int(row.BrokenIndex), 'bos', int(row.BOS)))
            if np.isfinite(row.CHOCH):
                rows.append((lo + int(row.BrokenIndex), 'choch', int(row.CHOCH)))
        for row in pools[pools['Swept'] > 0].itertuples():
            rows.append((lo + int(row.Swept), 'liq_sweep', int(row.Liquidity)))
    return pd.DataFrame(rows, columns=['g', 'kind', 'side'])


def fvg_events(df: pd.DataFrame, first: int) -> pd.DataFrame:
    """Fair value gaps need no later candle beyond the third one, so they are computed in overlapping pieces: a
    gap at candle i is known when candle i+1 closes, and its first retest is the library's MitigatedIndex."""
    from smartmoneyconcepts import smc
    rows = []
    for lo in range(max(first - 1, 1), len(df), CHUNK):
        w = df.iloc[lo - 1:lo + CHUNK + FVG_TAIL].reset_index(drop=True)
        gaps = smc.fvg(w)
        hit = gaps[gaps['FVG'].notna()]
        hit = hit[(hit.index >= 1) & (hit.index <= CHUNK)]
        for i, row in hit.iterrows():
            g = lo - 1 + int(i)
            if g + 1 < len(df):
                rows.append((g + 1, 'fvg_formed', int(row.FVG)))
            if row.MitigatedIndex > 0:
                rows.append((lo - 1 + int(row.MitigatedIndex), 'fvg_retest', int(row.FVG)))
    return pd.DataFrame(rows, columns=['g', 'kind', 'side']).drop_duplicates()


def signals(f, events: pd.DataFrame, side_sign: float = 1.0) -> pd.DataFrame:
    """Enter at the open after the signal bar. Stop 2 ATR, target 2R, hold 48 bars of the timeframe."""
    g = events['g'].to_numpy()
    entry = f.entry[g]
    atr = f.atr[g]
    out = pd.DataFrame({'i': entry, 'side': events['side'].to_numpy() * side_sign, 'stop': STOP_ATR * atr,
                        'target': STOP_ATR * TARGET_R * atr, 'hold': HOLD_BARS * f.seconds // 60})
    return out[(out['i'] >= 0) & (out['stop'] > 0)].sort_values('i').reset_index(drop=True)


def with_structure(events: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Retests that agree with the latest BOS or CHoCH, when that happened within STRUCTURE_MEMORY bars."""
    structure = events[events['kind'].isin(('bos', 'choch'))].sort_values('g')
    retests = events[events['kind'] == kind].sort_values('g')
    if structure.empty or retests.empty:
        return retests.iloc[:0]
    merged = pd.merge_asof(retests, structure.rename(columns={'side': 'trend', 'g': 'g_structure'})[['g_structure', 'trend']],
                           left_on='g', right_on='g_structure', allow_exact_matches=False)
    ok = (merged['trend'] == merged['side']) & (merged['g'] - merged['g_structure'] <= STRUCTURE_MEMORY)
    return merged.loc[ok, ['g', 'kind', 'side']]


# What the concept says to do with each signal (+1 = trade the signal's own side, -1 = the other side).
CONCEPT = {'bos': 1.0, 'choch': 1.0, 'ob_retest': 1.0, 'liq_sweep': -1.0, 'fvg_formed': 1.0, 'fvg_retest': 1.0}
LABEL = {'bos': 'Break of structure', 'choch': 'Change of character', 'ob_retest': 'Order block retest',
         'liq_sweep': 'Liquidity sweep, then reverse', 'fvg_formed': 'Fair value gap forms',
         'fvg_retest': 'Fair value gap retest'}


def evaluate_all(log=print) -> tuple[list[dict], list[dict]]:
    live, drawn = [], []
    for seconds in sorted({c[0] for c in CONFIGS}):
        m1, f, df = frame_of(seconds)
        first = int(np.searchsorted(f.bars.t, screen.epoch(REPLAY_FROM)))
        tf = f'M{seconds // 60}'
        gaps = fvg_events(df, first)
        for kind in ('fvg_formed', 'fvg_retest'):
            for way, sign in (('as the concept says', 1.0), ('opposite', -1.0)):
                result = screen.evaluate(m1, signals(f, gaps[gaps['kind'] == kind], CONCEPT[kind] * sign))
                live.append({'tf': tf, 'swing': '-', 'name': LABEL[kind], 'way': way, 'result': result})
                log(f"{tf} {LABEL[kind]} ({way}): {result['verdict']}")
        for _, swing, window in (c for c in CONFIGS if c[0] == seconds):
            path = EVENTS / f'XAUUSD_{seconds}_{swing}_{window}.parquet'
            if not path.exists():
                log(f'missing {path}: run with --replay first')
                continue
            events = pd.read_parquet(path)
            errors = int((events['kind'] == 'error').sum())
            for kind in ('bos', 'choch', 'ob_retest', 'liq_sweep'):
                for way, sign in (('as the concept says', 1.0), ('opposite', -1.0)):
                    result = screen.evaluate(m1, signals(f, events[events['kind'] == kind], CONCEPT[kind] * sign))
                    live.append({'tf': tf, 'swing': swing, 'name': LABEL[kind], 'way': way, 'result': result,
                                 'errors': errors})
                    log(f"{tf} swing {swing} {LABEL[kind]} ({way}): {result['verdict']}")
            both = pd.concat([events, gaps], ignore_index=True)
            for kind, label in (('fvg_retest', 'Fair value gap retest with the structure'),
                                ('ob_retest', 'Order block retest with the structure')):
                result = screen.evaluate(m1, signals(f, with_structure(both, kind)))
                live.append({'tf': tf, 'swing': swing, 'name': label, 'way': 'as the concept says', 'result': result})
                log(f"{tf} swing {swing} {label}: {result['verdict']}")
            chart = hindsight(df, swing, first)
            for kind in ('bos', 'choch', 'liq_sweep'):
                result = screen.evaluate(m1, signals(f, chart[chart['kind'] == kind], CONCEPT[kind]))
                same = screen.evaluate(m1, signals(f, events[events['kind'] == kind], CONCEPT[kind]))
                drawn.append({'tf': tf, 'swing': swing, 'name': LABEL[kind], 'hindsight': result, 'live': same})
                log(f"{tf} swing {swing} {LABEL[kind]} hindsight zero-cost R "
                    f"{fmt(result[0.0]['confirm']['mean'])} vs live {fmt(same[0.0]['confirm']['mean'])}")
    return live, drawn


def report(live: list[dict], drawn: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    rule = screen.RULE
    passed = [r for r in live if r['result']['verdict'] == 'PASSED']
    lines = [f'# smart-money-concepts library on XAUUSD ({stamp})', '',
             'Library: github.com/joshyattridge/smart-money-concepts v0.0.27, its own code, unchanged. '
             f'Development gold only (Dukascopy; nothing from {lockbox.LOCK_START} on is loaded). Discovery '
             f'{screen.DISCOVERY[0]} to {screen.DISCOVERY[1]}, confirmation {screen.CONFIRM[0]} to {screen.CONFIRM[1]}.', '',
             f'Every trade: enter at the open after the signal bar, stop {STOP_ATR:g} ATR, target {TARGET_R:g}R, hold at '
             f'most {HOLD_BARS} bars, one position at a time. "Swing" is the library\'s `swing_length`.', '',
             f'Pass rule (the same as the idea screen, fixed before the run): at zero cost in discovery mean R >= '
             f'{rule["zero_cost_discovery_r"]:+.2f} with t >= {rule["zero_cost_discovery_t"]:g}; at the recorded spread '
             f'in discovery mean R > 0; in confirmation at the recorded spread mean R >= {rule["confirm_r"]:+.2f}, '
             f'profit factor >= {rule["confirm_pf"]:g}, {rule["confirm_years_positive"]:.0%} of years positive, at '
             f'least {rule["confirm_trades_per_year"]} trades a year.', '',
             f'**{len(live)} live tests, {len(passed)} passed.**', '']
    counts = pd.Series([r['result']['verdict'] for r in live]).value_counts()
    lines += ['| Verdict | Tests |', '|---|---|'] + [f'| {k} | {v} |' for k, v in counts.items()] + ['']
    lines += ['## Live: the library sees only candles up to now', '',
              '| Timeframe | Swing | Signal | Traded | Trades a year | Zero cost: discovery R (t) | '
              'Zero cost: confirmation R | Half spread: confirmation R | Real spread: discovery R | '
              'Real spread: confirmation R | Confirmation PF | Years positive | Verdict |',
              '|---|---|---|---|---|---|---|---|---|---|---|---|---|']
    for r in live:
        z, h, f = r['result'][0.0], r['result'][0.5], r['result'][1.0]
        c = f['confirm']
        lines.append(f"| {r['tf']} | {r['swing']} | {r['name']} | {r['way']} | {fmt(c['per_year'], '.0f')} | "
                     f"{fmt(z['discovery']['mean'])} ({fmt(z['discovery']['t'], '+.1f')}) | {fmt(z['confirm']['mean'])} | "
                     f"{fmt(h['confirm']['mean'])} | {fmt(f['discovery']['mean'])} | {fmt(c['mean'])} | "
                     f"{fmt(c['pf'], '.2f')} | {c['years_positive']} of {c['years']} | {r['result']['verdict']} |")
    lines += ['', '## Hindsight against live', '',
              f'Hindsight: the library is run once on a finished chart of {HINDSIGHT_CHART:,} candles and every signal '
              'is traded at the bar where it is drawn. Live: the same signal, taken only when the library reports '
              'it for the last closed bar. Same stop, target and hold. Mean R per trade at zero cost.', '',
              '| Timeframe | Swing | Signal | Hindsight: trades a year | Hindsight: discovery R | '
              'Hindsight: confirmation R | Hindsight: win rate | Live: trades a year | Live: discovery R | '
              'Live: confirmation R | Live: win rate |', '|---|---|---|---|---|---|---|---|---|---|---|']
    for r in drawn:
        a, b = r['hindsight'][0.0], r['live'][0.0]
        lines.append(f"| {r['tf']} | {r['swing']} | {r['name']} | {fmt(a['confirm']['per_year'], '.0f')} | "
                     f"{fmt(a['discovery']['mean'])} | {fmt(a['confirm']['mean'])} | {fmt(a['confirm']['win'], '.0%')} | "
                     f"{fmt(b['confirm']['per_year'], '.0f')} | {fmt(b['discovery']['mean'])} | "
                     f"{fmt(b['confirm']['mean'])} | {fmt(b['confirm']['win'], '.0%')} |")
    lines.append('')
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--replay', action='store_true', help='run the slow bar-by-bar replay first')
    parser.add_argument('--processes', type=int, default=10)
    parser.add_argument('--report', type=Path, default=REPORT)
    args = parser.parse_args()
    if args.replay:
        for seconds, swing, window in CONFIGS:
            path = EVENTS / f'XAUUSD_{seconds}_{swing}_{window}.parquet'
            if path.exists():
                print(f'{path.name} exists, skipped')
                continue
            print(f'replay {seconds // 60}m swing {swing} window {window} -> {replay(seconds, swing, window, args.processes)}')
            sys.stdout.flush()
    live, drawn = evaluate_all()
    args.report.write_text(report(live, drawn), encoding='utf-8', newline='\n')
    print(f'report -> {args.report}')


if __name__ == '__main__':
    main()
