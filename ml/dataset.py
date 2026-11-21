#!/usr/bin/env python3
"""Build the labelled ICT dataset: one row per candidate, ICT features + the graded outcome (ML plan section 5).

    python -m ml.dataset                                   # XAUUSD, full Dukascopy history, 2008 on
    python -m ml.dataset --from 2011-01-01                 # skip the coarse-spread years entirely

Steps, all on one M1 file (default .local/history_dukascopy_full/XAUUSD_m1.csv, which ml/check_history.py must have
passed):

1. Repair the spread (ml.data.repair_spread): zero spreads get the hour's median; years before --coarse-until get
   at least their 99th-percentile spread, because their recorded spread has no news spikes.
2. Rebuild M5 from that M1 and run ml.ict_features.detect over the whole history, so 2003-2007 serve as indicator
   and pool warm-up, then keep candidates from --from on. Before 2008 Dukascopy's gold bars are about twice as wide
   relative to price and candidates run at a fraction of the later rate (ml/reports/xauusd_ict_candidates.md).
3. Grade each candidate with ml.labels.label (app.grader.simulate on M1 with spread, the live grader).

Output: a parquet file (default ml/data/xauusd_ict.parquet, gitignored) with the candidate identity, every name in
ml.ict_features.FEATURES, `year`, `spread_coarse` (1 when the bar's year had its spread raised) and the label
(outcome, r, win, exit, ambiguous, fill_time, end_time), plus <out>.meta.json describing how it was built.
`r` is the R the live grader gives the trade (0 when the limit never filled); `win` is 1/0 for filled trades only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.data import CRYPTO, load_m1, m1_path, repair_spread, resample  # noqa: E402
from ml.ict_features import FEATURES, CandidateConfig, detect  # noqa: E402
from ml.labels import ENTRY_EXPIRY_MINUTES, MAX_HOLD_MINUTES, label  # noqa: E402

DEFAULT_FOLDER = ROOT / '.local' / 'history_dukascopy_full'
DEFAULT_START = '2008-01-01'
DEFAULT_COARSE_UNTIL = 2011


def epoch(day: str) -> int:
    return int(datetime.combine(date.fromisoformat(day), datetime.min.time(), timezone.utc).timestamp())


def build(symbol: str, folder: Path, start: str = DEFAULT_START, coarse_until: int | None = DEFAULT_COARSE_UNTIL,
          rr: float = 2.0, expiry: int = ENTRY_EXPIRY_MINUTES, hold: int = MAX_HOLD_MINUTES, entry: str = 'edge',
          log=print) -> tuple[pd.DataFrame, dict]:
    """The labelled candidates of one symbol from `start` on, and a description of the build."""
    started = time.time()
    m1, spread_report = repair_spread(load_m1(symbol, folder), coarse_until)
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
    meta = {
        'symbol': symbol, 'm1_file': str(m1_path(symbol, folder)), 'from': start, 'coarse_spread_until': coarse_until,
        'spread_repair': spread_report, 'rr': rr, 'entry': entry, 'entry_expiry_minutes': expiry,
        'max_hold_minutes': hold,
        'config': cfg.__dict__, 'features': list(FEATURES), 'm1_bars': int(len(m1)), 'm5_bars': int(len(m5)),
        'candidates': int(len(df)), 'built_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M'),
        'seconds': round(time.time() - started, 1), 'git_commit': git_commit(),
    }
    history_meta = Path(folder) / f'{symbol}_meta.json'
    if history_meta.exists():
        meta['history_check'] = json.loads(history_meta.read_text()).get('checks')
    return df, meta


def by_year(df: pd.DataFrame) -> pd.DataFrame:
    """Candidates, fills and the raw (unfiltered) result per year: the baseline any model has to beat."""
    if not len(df):
        return pd.DataFrame()
    closed = df[df['outcome'] == 'closed']
    g = closed.groupby('year')
    out = pd.DataFrame({
        'candidates': df.groupby('year').size(),
        'filled': g.size(),
        'unresolved': df[df['outcome'] == 'unresolved'].groupby('year').size(),
        'win_rate': g['win'].mean(),
        'expectancy_r': g['r'].mean(),
        'total_r': g['r'].sum(),
        'ambiguous': g['ambiguous'].mean(),
    }).fillna({'filled': 0, 'unresolved': 0, 'total_r': 0.0})
    return out.astype({'filled': int, 'unresolved': int})


def git_commit() -> str | None:
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def summary(df: pd.DataFrame, meta: dict) -> str:
    closed = df[df['outcome'] == 'closed'] if len(df) else df
    table = by_year(df)
    lines = [f"# {meta['symbol']} ICT dataset", '',
             f"{meta['candidates']:,} candidates from {meta['from']}, {len(closed):,} filled. Built {meta['built_at']} "
             f"UTC from `{meta['m1_file']}` at commit {meta['git_commit']}; target {meta['rr']:g}R, entry expiry "
             f"{meta['entry_expiry_minutes']} min, hold {meta['max_hold_minutes']} min.", '']
    if len(closed):
        lines += [f"All candidates, no filter: win rate {closed['win'].mean():.1%}, expectancy "
                  f"{closed['r'].mean():+.3f}R per filled trade, total {closed['r'].sum():+.1f}R. This is the "
                  'baseline a model has to beat; it is not a strategy (overlapping trades are all counted).', '']
    lines += ['| Year | Candidates | Filled | Unresolved | Win rate | Exp. R | Total R | Ambiguous |',
              '|---|---|---|---|---|---|---|---|']
    for year, row in table.iterrows():
        lines.append(f"| {year} | {int(row['candidates'])} | {int(row['filled'])} | {int(row['unresolved'])} | "
                     f"{row['win_rate']:.1%} | {row['expectancy_r']:+.3f} | {row['total_r']:+.1f} | "
                     f"{row['ambiguous']:.1%} |")
    if len(df):
        lines += ['', 'Outcomes:', ''] + [f'- {k}: {v:,}' for k, v in df['outcome'].value_counts().items()]
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
    parser.add_argument('--folder', type=Path, default=DEFAULT_FOLDER, help='history folder with <SYMBOL>_m1.csv')
    parser.add_argument('--from', dest='start', default=DEFAULT_START, help='first candidate date (UTC)')
    parser.add_argument('--coarse-until', type=int, default=DEFAULT_COARSE_UNTIL,
                        help='years before this get a p99 spread floor (0 = no floor)')
    parser.add_argument('--rr', type=float, default=2.0)
    parser.add_argument('--expiry', type=int, default=ENTRY_EXPIRY_MINUTES, help='limit expiry, minutes')
    parser.add_argument('--hold', type=int, default=MAX_HOLD_MINUTES, help='maximum hold after the fill, minutes')
    parser.add_argument('--entry', choices=('edge', 'mid', 'market'), default='edge',
                        help='limit at the FVG edge (default), at its midpoint, or market on the next candle')
    parser.add_argument('--out', type=Path, default=None, help='parquet path (default ml/data/<symbol>_ict.parquet)')
    parser.add_argument('--report', type=Path, default=None,
                        help='Markdown report path (default ml/reports/<symbol>_ict_dataset.md)')
    parser.add_argument('--allow-unchecked', action='store_true',
                        help='build even if ml/check_history.py has not passed on this folder')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    folder = args.folder if args.folder.is_absolute() else ROOT / args.folder
    checks = json.loads((folder / f'{symbol}_meta.json').read_text()).get('checks') \
        if (folder / f'{symbol}_meta.json').exists() else None
    if not (checks and checks.get('passed')) and not args.allow_unchecked:
        raise SystemExit(f'{folder} has no passed history check; run ml/check_history.py first '
                         '(or pass --allow-unchecked)')
    df, meta = build(symbol, folder, args.start, args.coarse_until or None, args.rr, args.expiry, args.hold,
                     args.entry)
    out = args.out or ROOT / 'ml' / 'data' / f'{symbol.lower()}_ict.parquet'
    out = out if out.is_absolute() else ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    meta['file'] = str(out)
    out.with_suffix('.meta.json').write_text(json.dumps(meta, indent=2, default=str))
    text = summary(df, meta)
    report = args.report or ROOT / 'ml' / 'reports' / f'{symbol.lower()}_ict_dataset.md'
    report = report if report.is_absolute() else ROOT / report
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text, encoding='utf-8')
    print(text)
    print(f'dataset -> {out}\nreport  -> {report}')
    if not len(df) or df['r'].isna().all():
        raise SystemExit('no graded candidates')


if __name__ == '__main__':
    main()
