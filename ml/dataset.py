#!/usr/bin/env python3
"""Build the labelled ICT dataset: one row per candidate, ICT features + the graded outcome (plan v2, V2.0-V2.2).

    python -m ml.dataset                                   # XAUUSD, full Dukascopy history, 2008 on
    python -m ml.dataset --name xauusd_ict_halfspread --spread-scale 0.5
    python -m ml.dataset --name xauusd_ict_exness --folder .local/history --from 2023-11-24 --coarse-until 0 \\
        --spread-from .local/history_dukascopy_full --allow-unchecked

Steps, all on one M1 file (default .local/history_dukascopy_full/XAUUSD_m1.csv, which ml/check_history.py must have
passed):

1. Spread. --spread-from takes the spread of another folder's M1 for the same minute (the spread recorded in the
   broker file is a floor, so the broker's prices are graded with Dukascopy's spread). Then ml.data.repair_spread:
   zero spreads get the hour's median; years before --coarse-until get at least their 99th-percentile spread.
   --spread-scale multiplies the result (0.5 for the "spread halved" sensitivity line).
2. Rebuild M5 from that M1 and run ml.ict_features.detect over the whole history, so the early years serve as
   indicator and pool warm-up, then keep candidates from --from on.
3. Grade each candidate with ml.labels.label (app.grader.simulate on M1 with spread, the live grader).
4. Mark the account filter and the three-outcome label, then split (ml/lockbox.py):
       ml/data/<name>_dev.parquet               trade window ends before 2024-11-20: all development work
       ml/data/lockbox/<name>_lockbox.parquet   2024-11-20 on: read once, by ml/final_test.py only

Columns: the candidate identity, every name in ml.ict_features.FEATURES, `year`, `spread_coarse`, the label
(outcome, r, win, exit, ambiguous, fill_time, end_time), `outcome_class` (0 target, 1 stop, 2 timeout or
break-even exit; missing when the limit never filled) and `tradable` (the stop distance fits the account: at most
ACCOUNT_RISK_USD at the minimum position). The report and everything printed describe the development rows only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml import lockbox  # noqa: E402
from ml.data import CRYPTO, Bars, load_m1, m1_path, repair_spread, resample  # noqa: E402
from ml.ict_features import FEATURES, CandidateConfig, detect  # noqa: E402
from ml.labels import ENTRY_EXPIRY_MINUTES, MAX_HOLD_MINUTES, label  # noqa: E402

DEFAULT_FOLDER = ROOT / '.local' / 'history_dukascopy_full'
DEFAULT_START = '2008-01-01'
DEFAULT_COARSE_UNTIL = 2011
ACCOUNT_RISK_USD = 10.0              # $1,000 account, 1% a trade (plan v2, V2.1)
MIN_POSITION_UNITS = 1.0             # 0.01 lot of gold = 1 oz: one dollar per dollar of price
CLASSES = ('target', 'stop', 'timeout')
EXIT_CLASS = {'final_target': 0, 'sl': 1, 'timeout': 2, 'be': 2}


def epoch(day: str) -> int:
    return int(datetime.combine(date.fromisoformat(day), datetime.min.time(), timezone.utc).timestamp())


def borrow_spread(m1: Bars, other: Bars) -> Bars:
    """m1's prices with `other`'s spread for the same minute (its latest earlier one where it has no bar)."""
    idx = np.clip(np.searchsorted(other.t, m1.t, side='right') - 1, 0, len(other) - 1)
    return Bars(m1.t, m1.o, m1.h, m1.l, m1.c, other.spread[idx].astype(float))


def build(symbol: str, folder: Path, start: str = DEFAULT_START, coarse_until: int | None = DEFAULT_COARSE_UNTIL,
          rr: float = 2.0, expiry: int = ENTRY_EXPIRY_MINUTES, hold: int = MAX_HOLD_MINUTES, entry: str = 'edge',
          spread_from: Path | None = None, spread_scale: float = 1.0, log=print) -> tuple[pd.DataFrame, dict]:
    """The labelled candidates of one symbol from `start` on (development and lockbox rows together; the caller
    splits them), and a description of the build."""
    started = time.time()
    m1 = load_m1(symbol, folder)
    if spread_from is not None:
        m1 = borrow_spread(m1, load_m1(symbol, spread_from, start=int(m1.t[0]) - 86400))
    m1, spread_report = repair_spread(m1, coarse_until)
    if spread_scale != 1.0:
        m1 = Bars(m1.t, m1.o, m1.h, m1.l, m1.c, m1.spread * spread_scale)
    m5 = resample(m1, 300)
    cfg = CandidateConfig(rr=rr, crypto=symbol in CRYPTO, entry=entry)
    rows = detect(symbol, m5, cfg)
    since = epoch(start)
    rows = [r for r in rows if r['bar_time'] >= since]
    log(f'{symbol}: {len(m1):,} M1 bars, {len(m5):,} M5 bars, {len(rows):,} candidates from {start} '
        f'({time.time() - started:.0f}s); grading...')
    labels = label(rows, m1, rr=rr, expiry=expiry, hold=hold)
    df = pd.DataFrame([{**r, **lab} for r, lab in zip(rows, labels)])
    if len(df):
        df['year'] = pd.to_datetime(df['bar_time'], unit='s').dt.year.astype(int)
        df['spread_coarse'] = (df['year'] < coarse_until).astype(float) if coarse_until else 0.0
        df['outcome_class'] = df['exit'].map(EXIT_CLASS).astype(float)
        df['tradable'] = df['risk'] * MIN_POSITION_UNITS <= ACCOUNT_RISK_USD
    meta = {
        'symbol': symbol, 'm1_file': str(m1_path(symbol, folder)), 'from': start, 'coarse_spread_until': coarse_until,
        'spread_from': str(spread_from) if spread_from else None, 'spread_scale': spread_scale,
        'spread_repair': spread_report, 'rr': rr, 'entry': entry, 'entry_expiry_minutes': expiry,
        'max_hold_minutes': hold, 'account_risk_usd': ACCOUNT_RISK_USD, 'lock_start': lockbox.LOCK_START,
        'config': cfg.__dict__, 'features': list(FEATURES), 'm1_bars': int(len(m1)), 'm5_bars': int(len(m5)),
        'candidates': int(len(df)), 'built_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'),
        'seconds': round(time.time() - started, 1), 'git_commit': git_commit(),
    }
    history_meta = Path(folder) / f'{symbol}_meta.json'
    if history_meta.exists():
        meta['history_check'] = json.loads(history_meta.read_text()).get('checks')
    return df, meta


def by_year(df: pd.DataFrame) -> pd.DataFrame:
    """Per year: candidates, how many the account can trade, fills among those, and their raw result."""
    if not len(df):
        return pd.DataFrame()
    ok = df[df['tradable']]
    closed = ok[ok['outcome'] == 'closed']
    g = closed.groupby('year')
    out = pd.DataFrame({
        'candidates': df.groupby('year').size(),
        'tradable': ok.groupby('year').size(),
        'filled': g.size(),
        'target': g['outcome_class'].apply(lambda s: (s == 0).mean()),
        'stop': g['outcome_class'].apply(lambda s: (s == 1).mean()),
        'timeout': g['outcome_class'].apply(lambda s: (s == 2).mean()),
        'expectancy_r': g['r'].mean(),
        'total_r': g['r'].sum(),
    }).fillna({'tradable': 0, 'filled': 0, 'total_r': 0.0})
    return out.astype({'tradable': int, 'filled': int})


def git_commit() -> str | None:
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def summary(dev: pd.DataFrame, meta: dict) -> str:
    """Markdown about the development rows only: nothing here may describe lockbox outcomes."""
    lockbox.guard(dev, 'the dataset summary')
    ok = dev[dev['tradable']] if len(dev) else dev
    closed = ok[ok['outcome'] == 'closed'] if len(ok) else ok
    counts = meta.get('rows', {})
    lines = [f"# {meta['symbol']} ICT dataset `{meta.get('name', '')}` (development rows)", '',
             f"{len(dev):,} development candidates from {meta['from']} to {lockbox.LOCK_START}; {len(ok):,} fit the "
             f"account (stop at most ${meta['account_risk_usd']:g} at the minimum position); {len(closed):,} of those "
             f"filled. Lockbox: {counts.get('lockbox', 0):,} candidates from {lockbox.LOCK_START} on, written "
             f"unread; {counts.get('straddling_dropped', 0)} straddling candidates dropped.", '',
             f"Built {meta['built_at']} UTC from `{meta['m1_file']}` at commit {meta['git_commit']}; target "
             f"{meta['rr']:g}R, entry expiry {meta['entry_expiry_minutes']} min, hold {meta['max_hold_minutes']} min"
             + (f"; spread from `{meta['spread_from']}`" if meta.get('spread_from') else '')
             + (f"; spread x {meta['spread_scale']:g}" if meta.get('spread_scale', 1.0) != 1.0 else '') + '.', '']
    if len(closed):
        lines += [f"Every tradable setup, no model: {closed['r'].mean():+.3f}R per filled trade before slippage, total "
                  f"{closed['r'].sum():+.1f}R (overlapping trades all counted).", '']
    lines += ['| Year | Candidates | Tradable | Filled | Target | Stop | Timeout | Exp. R | Total R |',
              '|---|---|---|---|---|---|---|---|---|']
    for year, row in by_year(dev).iterrows():
        lines.append(f"| {year} | {int(row['candidates'])} | {row['tradable']} | {row['filled']} | "
                     f"{row['target']:.1%} | {row['stop']:.1%} | {row['timeout']:.1%} | {row['expectancy_r']:+.3f} | "
                     f"{row['total_r']:+.1f} |")
    if len(dev):
        lines += ['', 'Outcomes:', ''] + [f'- {k}: {v:,}' for k, v in dev['outcome'].value_counts().items()]
    repaired = meta['spread_repair']
    if repaired:
        lines += ['', 'Spread repair (ml.data.repair_spread):', '']
        for year, info in sorted(repaired.items()):
            parts = []
            if 'zero_replaced' in info:
                parts.append(f"{info['zero_replaced']:,} zero spreads replaced")
            if 'coarse_floor' in info:
                parts.append(f"floor {info['coarse_floor']:g} raised {info['raised']:,} bars")
            lines.append(f"- {year}: " + ', '.join(parts))
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--name', help='dataset name (default <symbol>_ict): files <name>_dev / <name>_lockbox')
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER, help='history folder with <SYMBOL>_m1.csv')
    parser.add_argument('--from', dest='start', default=DEFAULT_START, help='first candidate date (UTC)')
    parser.add_argument('--coarse-until', type=int, default=DEFAULT_COARSE_UNTIL,
                        help='years before this get a p99 spread floor (0 = no floor)')
    parser.add_argument('--spread-from', type=Path, help='take the spread from this history folder, minute by minute')
    parser.add_argument('--spread-scale', type=float, default=1.0, help='multiply the spread (sensitivity only)')
    parser.add_argument('--rr', type=float, default=2.0)
    parser.add_argument('--expiry', type=int, default=ENTRY_EXPIRY_MINUTES, help='limit expiry, minutes')
    parser.add_argument('--hold', type=int, default=MAX_HOLD_MINUTES, help='maximum hold after the fill, minutes')
    parser.add_argument('--entry', choices=('edge', 'mid', 'market'), default='edge',
                        help='limit at the FVG edge (default), at its midpoint, or market on the next candle')
    parser.add_argument('--report', type=Path, default=None, help='Markdown report (default ml/reports/<name>_dataset.md)')
    parser.add_argument('--allow-unchecked', action='store_true',
                        help='build even if ml/check_history.py has not passed on this folder')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    name = args.name or f'{symbol.lower()}_ict'
    folder = args.folder if args.folder.is_absolute() else ROOT / args.folder
    spread_from = None if args.spread_from is None else \
        (args.spread_from if args.spread_from.is_absolute() else ROOT / args.spread_from)
    checks = json.loads((folder / f'{symbol}_meta.json').read_text()).get('checks') \
        if (folder / f'{symbol}_meta.json').exists() else None
    if not (checks and checks.get('passed')) and not args.allow_unchecked:
        raise SystemExit(f'{folder} has no passed history check; run ml/check_history.py first '
                         '(or pass --allow-unchecked)')
    df, meta = build(symbol, folder, args.start, args.coarse_until or None, args.rr, args.expiry, args.hold,
                     args.entry, spread_from, args.spread_scale)
    if not len(df):
        raise SystemExit('no candidates')
    dev_path, locked_path, counts = lockbox.write(df, name)
    meta.update({'name': name, 'rows': counts, 'file': str(dev_path), 'lockbox_file': str(locked_path)})
    dev_path.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2, default=str))
    dev, _, _ = lockbox.split(df)
    text = summary(dev, meta)
    report = args.report or ROOT / 'ml' / 'reports' / f'{name}_dataset.md'
    report = report if report.is_absolute() else ROOT / report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text, encoding='utf-8')
    print(text)
    print(f'development -> {dev_path}\nlockbox     -> {locked_path} ({counts["lockbox"]:,} rows, unread)\n'
          f'report      -> {report}')


if __name__ == '__main__':
    main()
