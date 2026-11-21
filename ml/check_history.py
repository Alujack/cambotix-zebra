#!/usr/bin/env python3
"""Validate a saved M1 history before it is used for datasets (ML plan, Phase 0 / roadmap phase 1).

    python ml/check_history.py --symbol XAUUSD --folder .local/history_dukascopy_full --compare .local/history

Checks, on <folder>/<SYMBOL>_m1.csv (t,o,h,l,c,spread; t = bar open, UTC seconds):

    reject   duplicate or out-of-order timestamps, bars not on a minute boundary, prices <= 0, high < low,
             open/close outside [low, high], bars on Saturday, and holes longer than --max-hole trading days
    report   missing trading hours by date (holidays are expected; a few hours a year are normal),
             spread per year (median, 99th percentile, zeros, outliers above 20x the median),
             the resampled frames (m5, m15, h1, h4, d1) agree with pandas resampling of the M1 file,
             overlap with another folder's M1 (e.g. the Exness pull): price and spread difference by year

Writes <folder>/<SYMBOL>_check.json, adds a "checks" key to <folder>/<SYMBOL>_meta.json and a Markdown report to
ml/reports/<symbol>_history_check.md. Exit code 1 when anything in the reject list is found.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / 'ml' / 'reports'
PERIOD = {'m5': 300, 'm15': 900, 'h1': 3600, 'h4': 14400, 'd1': 86400}
OPEN_HOURS = range(0, 21)          # UTC hours every Mon-Fri with trading; 21-23 depend on DST, Sunday evening too
SPREAD_OUTLIER = 20.0              # x median


def load_m1(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={'t': np.int64, 'o': float, 'h': float, 'l': float, 'c': float, 'spread': float})
    if 'spread' not in df:
        df['spread'] = 0.0
    return df


def stamp(t) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime('%Y-%m-%d %H:%M')


def day(t) -> str:
    return datetime.fromtimestamp(int(t), timezone.utc).strftime('%Y-%m-%d')


def check_timestamps(df: pd.DataFrame) -> dict:
    t = df['t'].to_numpy()
    diff = np.diff(t)
    return {
        'bars': int(len(df)),
        'first': stamp(t[0]) if len(t) else None,
        'last': stamp(t[-1]) if len(t) else None,
        'duplicates': int((diff == 0).sum()),
        'out_of_order': int((diff < 0).sum()),
        'off_minute': int((t % 60 != 0).sum()),
    }


def check_prices(df: pd.DataFrame) -> dict:
    bad_sign = (df[['o', 'h', 'l', 'c']] <= 0).any(axis=1)
    inverted = df['h'] < df['l']
    outside = (df['o'] > df['h']) | (df['o'] < df['l']) | (df['c'] > df['h']) | (df['c'] < df['l'])
    bad = bad_sign | inverted | outside
    return {
        'non_positive': int(bad_sign.sum()),
        'high_below_low': int(inverted.sum()),
        'open_close_outside_range': int(outside.sum()),
        'examples': [stamp(t) for t in df.loc[bad, 't'].head(5)],
    }


def check_weekend(df: pd.DataFrame) -> dict:
    t = df['t'].to_numpy()
    weekday = (t // 86400 + 3) % 7                          # Monday = 0 (1970-01-01 was a Thursday)
    hour = (t % 86400) // 3600
    saturday = weekday == 5
    sunday_early = (weekday == 6) & (hour < 21)
    return {
        'saturday_bars': int(saturday.sum()),
        'sunday_before_21utc_bars': int(sunday_early.sum()),
        'examples': [stamp(x) for x in t[saturday | sunday_early][:5]],
    }


def check_gaps(df: pd.DataFrame, max_hole_days: int) -> dict:
    """Trading hours (Mon-Fri 00:00-20:59 UTC) with no bars, grouped by date, plus runs of fully missing days."""
    t = df['t'].to_numpy()
    if len(t) == 0:
        return {'missing_hours': 0, 'missing_days': 0, 'holes': [], 'by_year': {}, 'days': []}
    present = np.unique(t // 3600)
    hours = np.arange(present[0] - present[0] % 24, present[-1] - present[-1] % 24 + 24)   # whole first/last days
    weekday = (hours // 24 + 3) % 7
    expected = hours[(weekday <= 4) & (hours % 24 < OPEN_HOURS.stop)]
    missing = np.setdiff1d(expected, present, assume_unique=True)
    missing_days = pd.Series(missing // 24).value_counts().sort_index()
    full = missing_days[missing_days >= len(OPEN_HOURS)]
    full_days = full.index.to_numpy()

    holes, run = [], []
    trading_days = np.unique(expected // 24)
    full_set = set(full_days.tolist())
    for d in trading_days:
        if d in full_set:
            run.append(d)
        elif run:
            holes.append(run)
            run = []
    if run:
        holes.append(run)
    long_holes = [{'from': day(r[0] * 86400), 'to': day(r[-1] * 86400), 'trading_days': len(r)}
                  for r in holes if len(r) > max_hole_days]

    by_year: dict[str, dict] = {}
    for d, n in missing_days.items():
        y = datetime.fromtimestamp(int(d) * 86400, timezone.utc).strftime('%Y')
        entry = by_year.setdefault(y, {'missing_hours': 0, 'full_days': 0, 'partial_days': 0})
        entry['missing_hours'] += int(n)
        entry['full_days' if n >= len(OPEN_HOURS) else 'partial_days'] += 1

    partial = [(d, n) for d, n in missing_days.items() if n < len(OPEN_HOURS)]
    return {
        'missing_hours': int(len(missing)),
        'missing_days': int(len(full_days)),
        'partial_days': int(len(partial)),
        'holes': long_holes,
        'by_year': by_year,
        'days': [day(int(d) * 86400) for d in full_days],
        'partial': [{'day': day(int(d) * 86400), 'hours': int(n)} for d, n in partial],
    }


def check_spread(df: pd.DataFrame) -> dict:
    years = pd.to_datetime(df['t'], unit='s').dt.year
    out = {}
    for y, s in df['spread'].groupby(years):
        med = float(s.median())
        out[str(int(y))] = {
            'bars': int(len(s)),
            'median': round(med, 6),
            'p99': round(float(s.quantile(0.99)), 6),
            'max': round(float(s.max()), 6),
            'zero': int((s <= 0).sum()),
            'outliers': int((s > SPREAD_OUTLIER * med).sum()) if med > 0 else 0,
        }
    return out


def resample(m1: pd.DataFrame, seconds: int) -> pd.DataFrame:
    key = m1['t'] - m1['t'] % seconds
    g = m1.groupby(key, sort=True)
    return pd.DataFrame({'t': g['t'].first().index, 'o': g['o'].first().to_numpy(), 'h': g['h'].max().to_numpy(),
                         'l': g['l'].min().to_numpy(), 'c': g['c'].last().to_numpy()})


def check_frames(m1: pd.DataFrame, folder: Path, symbol: str) -> dict:
    """Each saved frame: aligned, sorted, unique, and (within the M1 range) equal to pandas resampling of M1."""
    out = {}
    m1_start = int(m1['t'].iloc[0]) if len(m1) else 0
    for name, seconds in PERIOD.items():
        path = folder / f'{symbol}_{name}.csv'
        if not path.exists():
            out[name] = {'present': False}
            continue
        f = pd.read_csv(path, dtype={'t': np.int64})
        t = f['t'].to_numpy()
        entry = {'present': True, 'bars': int(len(f)), 'misaligned': int((t % seconds != 0).sum()),
                 'duplicates': int(pd.Series(t).duplicated().sum()), 'out_of_order': int((np.diff(t) < 0).sum())}
        inside = f[f['t'] >= m1_start - m1_start % seconds].reset_index(drop=True)
        want = resample(m1, seconds)
        if seconds == 86400 or seconds == 14400:
            inside = inside[inside['t'] >= want['t'].iloc[0]].reset_index(drop=True) if len(want) else inside
        if len(inside) != len(want):
            entry['matches_m1'] = False
            entry['mismatch'] = f'{len(inside)} saved bars vs {len(want)} resampled from M1'
        else:
            close = np.isclose(inside[['o', 'h', 'l', 'c']].to_numpy(), want[['o', 'h', 'l', 'c']].to_numpy(),
                               rtol=0, atol=1e-6).all(axis=1) & (inside['t'].to_numpy() == want['t'].to_numpy())
            entry['matches_m1'] = bool(close.all())
            if not close.all():
                entry['mismatch'] = f'{int((~close).sum())} bars differ, first {stamp(inside["t"][~close].iloc[0])}'
        out[name] = entry
    return out


def check_overlap(m1: pd.DataFrame, other_path: Path) -> dict:
    """Compare with another M1 file (e.g. the Exness MT5 pull) on the minutes both have."""
    other = load_m1(other_path).drop_duplicates('t')
    lo, hi = max(m1['t'].iloc[0], other['t'].iloc[0]), min(m1['t'].iloc[-1], other['t'].iloc[-1])
    a = m1[(m1['t'] >= lo) & (m1['t'] <= hi)]
    b = other[(other['t'] >= lo) & (other['t'] <= hi)]
    if len(a) == 0 or len(b) == 0:
        return {'file': str(other_path), 'overlap': None}
    j = a.merge(b, on='t', suffixes=('', '_other'))
    years = pd.to_datetime(j['t'], unit='s').dt.year
    by_year = {}
    for y, g in j.groupby(years):
        d = (g['c'] - g['c_other']).abs()
        by_year[str(int(y))] = {
            'minutes': int(len(g)),
            'close_diff_median': round(float(d.median()), 4),
            'close_diff_p99': round(float(d.quantile(0.99)), 4),
            'spread_median': round(float(g['spread'].median()), 4),
            'spread_median_other': round(float(g['spread_other'].median()), 4),
        }
    return {
        'file': str(other_path),
        'overlap': {'from': stamp(lo), 'to': stamp(hi)},
        'minutes_here': int(len(a)), 'minutes_other': int(len(b)), 'minutes_both': int(len(j)),
        'only_other': int(len(b) - len(j)), 'only_here': int(len(a) - len(j)),
        'close_diff_median': round(float((j['c'] - j['c_other']).abs().median()), 4),
        'close_diff_p99': round(float((j['c'] - j['c_other']).abs().quantile(0.99)), 4),
        'spread_median': round(float(j['spread'].median()), 4),
        'spread_median_other': round(float(j['spread_other'].median()), 4),
        'by_year': by_year,
    }


def run_checks(folder: Path, symbol: str, compare: Path | None, max_hole_days: int) -> dict:
    m1 = load_m1(folder / f'{symbol}_m1.csv')
    result = {
        'symbol': symbol, 'folder': str(folder), 'checked_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'),
        'timestamps': check_timestamps(m1),
        'prices': check_prices(m1),
        'weekend': check_weekend(m1),
        'gaps': check_gaps(m1, max_hole_days),
        'spread': check_spread(m1),
        'frames': check_frames(m1, folder, symbol),
    }
    if compare is not None:
        other = compare / f'{symbol}_m1.csv'
        result['overlap'] = check_overlap(m1, other) if other.exists() else {'file': str(other), 'overlap': None}
    ts, pr, wk, gp = result['timestamps'], result['prices'], result['weekend'], result['gaps']
    rejects = []
    for key in ('duplicates', 'out_of_order', 'off_minute'):
        if ts[key]:
            rejects.append(f'{ts[key]} {key} timestamps')
    for key in ('non_positive', 'high_below_low', 'open_close_outside_range'):
        if pr[key]:
            rejects.append(f'{pr[key]} bars with {key}')
    if wk['saturday_bars']:
        rejects.append(f'{wk["saturday_bars"]} Saturday bars')
    for hole in gp['holes']:
        rejects.append(f'hole {hole["from"]} .. {hole["to"]} ({hole["trading_days"]} trading days)')
    for name, f in result['frames'].items():
        if f.get('present') and (f['misaligned'] or f['duplicates'] or f['out_of_order'] or not f.get('matches_m1', True)):
            rejects.append(f'{name}: ' + (f.get('mismatch') or 'misaligned, duplicate or unsorted bars'))
    result['rejects'] = rejects
    result['passed'] = not rejects
    return result


def markdown(r: dict) -> str:
    ts, gp = r['timestamps'], r['gaps']
    lines = [f'# {r["symbol"]} history check', '',
             f'Folder: `{r["folder"]}` - checked {r["checked_at"]} UTC - **{"PASSED" if r["passed"] else "FAILED"}**', '']
    if r['rejects']:
        lines += ['Rejects:', ''] + [f'- {x}' for x in r['rejects']] + ['']
    lines += ['## M1', '', '| Item | Value |', '|---|---|',
              f'| Bars | {ts["bars"]:,} |', f'| First | {ts["first"]} |', f'| Last | {ts["last"]} |',
              f'| Duplicate / out-of-order / off-minute | {ts["duplicates"]} / {ts["out_of_order"]} / {ts["off_minute"]} |',
              f'| Bad prices (<=0, h<l, o/c outside) | {r["prices"]["non_positive"]} / {r["prices"]["high_below_low"]} / {r["prices"]["open_close_outside_range"]} |',
              f'| Saturday bars / Sunday before 21:00 UTC | {r["weekend"]["saturday_bars"]} / {r["weekend"]["sunday_before_21utc_bars"]} |',
              f'| Missing trading hours (Mon-Fri 00-20 UTC) | {gp["missing_hours"]:,} in {gp["missing_days"]} full days + {gp["partial_days"]} partial days |', '']
    lines += ['## Gaps by year', '', '| Year | Missing hours | Full days | Partial days |', '|---|---|---|---|']
    lines += [f'| {y} | {v["missing_hours"]} | {v["full_days"]} | {v["partial_days"]} |' for y, v in gp['by_year'].items()]
    if gp['holes']:
        lines += ['', 'Holes longer than the limit:', ''] + [f'- {h["from"]} .. {h["to"]} ({h["trading_days"]} trading days)' for h in gp['holes']]
    lines += ['', 'Full missing weekdays (holidays expected: Christmas, New Year, Good Friday):', '',
              ', '.join(gp['days']) or 'none', '']
    lines += ['## Spread by year', '', '| Year | Bars | Median | p99 | Max | Zero | > 20x median |', '|---|---|---|---|---|---|---|']
    lines += [f'| {y} | {v["bars"]:,} | {v["median"]} | {v["p99"]} | {v["max"]} | {v["zero"]} | {v["outliers"]} |'
              for y, v in r['spread'].items()]
    lines += ['', '## Frames vs M1', '', '| Frame | Bars | Misaligned | Dups | Unsorted | Matches M1 |', '|---|---|---|---|---|---|']
    for name, f in r['frames'].items():
        if f.get('present'):
            lines.append(f'| {name} | {f["bars"]:,} | {f["misaligned"]} | {f["duplicates"]} | {f["out_of_order"]} | '
                         f'{"yes" if f.get("matches_m1") else f.get("mismatch", "no")} |')
        else:
            lines.append(f'| {name} | missing | | | | |')
    ov = r.get('overlap')
    if ov:
        lines += ['', '## Overlap with ' + ov['file'], '']
        if ov.get('overlap'):
            lines += [f'{ov["overlap"]["from"]} .. {ov["overlap"]["to"]}: {ov["minutes_both"]:,} minutes in both, '
                      f'{ov["only_other"]:,} only in the other file, {ov["only_here"]:,} only here.',
                      f'Median |close difference| {ov["close_diff_median"]} (p99 {ov["close_diff_p99"]}); '
                      f'median spread here {ov["spread_median"]} vs {ov["spread_median_other"]} there.', '',
                      '| Year | Minutes | Close diff median | p99 | Spread here | Spread there |', '|---|---|---|---|---|---|']
            lines += [f'| {y} | {v["minutes"]:,} | {v["close_diff_median"]} | {v["close_diff_p99"]} | {v["spread_median"]} | {v["spread_median_other"]} |'
                      for y, v in ov['by_year'].items()]
        else:
            lines.append('No overlapping range.')
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--folder', type=Path, default=ROOT / '.local' / 'history_dukascopy_full')
    parser.add_argument('--compare', type=Path, default=None, help='another history folder to compare on the overlap')
    parser.add_argument('--max-hole', type=int, default=5, help='reject holes longer than this many trading days')
    parser.add_argument('--report', type=Path, default=None, help='Markdown report path (default ml/reports/)')
    args = parser.parse_args()
    symbol = args.symbol.upper()
    folder = args.folder if args.folder.is_absolute() else ROOT / args.folder
    compare = None if args.compare is None else (args.compare if args.compare.is_absolute() else ROOT / args.compare)

    result = run_checks(folder, symbol, compare, args.max_hole)
    (folder / f'{symbol}_check.json').write_text(json.dumps(result, indent=2))
    meta_path = folder / f'{symbol}_meta.json'
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        meta['checks'] = {'checked_at': result['checked_at'], 'passed': result['passed'], 'rejects': result['rejects'],
                          'bars': result['timestamps']['bars'], 'first': result['timestamps']['first'],
                          'last': result['timestamps']['last'], 'missing_hours': result['gaps']['missing_hours']}
        meta_path.write_text(json.dumps(meta, indent=2))
    report = args.report or REPORTS / f'{symbol.lower()}_history_check.md'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(markdown(result), encoding='utf-8')
    print(markdown(result))
    print(f'report -> {report}')
    sys.exit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
