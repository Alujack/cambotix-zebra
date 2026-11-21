#!/usr/bin/env python3
"""Build the labelled ICT dataset: one row per candidate, ICT features + the graded outcome.

    python -m ml.dataset                                  # all symbols with saved history
    python -m ml.dataset --symbols XAUUSD,EURUSD --out ml/data/ict_dataset.csv.gz

Output columns: candidate identity (symbol, bar_time, side, entry, stop, target, ...), every name in
ml.ict_features.FEATURES, and the label (outcome, r, win, exit, ambiguous, fill_time, end_time). `r` is the R
multiple the live grader gives the trade (0 when the limit never filled); `win` is 1/0 for filled trades only.
"""
from __future__ import annotations

import argparse
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

from ml.data import ALL_SYMBOLS, CRYPTO, ROOT, load_m1, m1_path, resample
from ml.ict_features import CandidateConfig, detect
from ml.labels import ENTRY_EXPIRY_MINUTES, MAX_HOLD_MINUTES, label

DEFAULT_OUT = ROOT / 'ml' / 'data' / 'ict_dataset.csv.gz'


def build_symbol(symbol: str, rr: float = 2.0, expiry: int = ENTRY_EXPIRY_MINUTES,
                 hold: int = MAX_HOLD_MINUTES) -> pd.DataFrame:
    started = time.time()
    m1 = load_m1(symbol)
    m5 = resample(m1, 300)
    cfg = CandidateConfig(rr=rr, crypto=symbol in CRYPTO)
    rows = detect(symbol, m5, cfg)
    labels = label(rows, m1, rr=rr, expiry=expiry, hold=hold)
    df = pd.DataFrame([{**r, **lab} for r, lab in zip(rows, labels)])
    print(f'{symbol:<7} {len(m5):>8} M5 bars  {len(df):>6} candidates  '
          f'{(df["outcome"] == "closed").sum() if len(df) else 0:>6} filled  {time.time() - started:5.0f}s', flush=True)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbols', default=','.join(ALL_SYMBOLS))
    parser.add_argument('--out', default=str(DEFAULT_OUT))
    parser.add_argument('--rr', type=float, default=2.0)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    symbols = [s for s in symbols if m1_path(s).exists() or print(f'{s:<7} skipped: no {m1_path(s)}')]
    frames = []
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as pool:
        for df in pool.map(build_symbol, symbols, [args.rr] * len(symbols)):
            frames.append(df)
    data = pd.concat([f for f in frames if len(f)], ignore_index=True).sort_values(['bar_time', 'symbol'])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(out, index=False)
    closed = data[data['outcome'] == 'closed']
    print(f'\n{len(data)} candidates, {len(closed)} filled, raw expectancy {closed["r"].mean():+.3f}R, '
          f'win rate {closed["win"].mean():.1%} -> {out}')
    print(data['outcome'].value_counts().to_string())


if __name__ == '__main__':
    main()
