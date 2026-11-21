#!/usr/bin/env python3
"""Rebuild cycle of the gold ICT model (plan section 10 and Plan v2): refresh history, check it, rebuild the
datasets, run the development walk-forward with its gates.

    python -m ml.retrain                  # full cycle
    python -m ml.retrain --skip-pull      # history is already current

Steps, each stopping the cycle if it fails:
  1. scripts/pull_dukascopy.py --from 2003-05-01 --out .local/history_dukascopy_full (resumable: only the current
     year is fetched again)
  2. ml/check_history.py on that folder (must pass)
  3. python -m ml.dataset three times: Dukascopy (training and gates), half spread (sensitivity line) and, when
     .local/history has the broker M1, broker prices with Dukascopy's spread (gate 5). Each build writes a
     development file and an unread lockbox file (ml/lockbox.py).
  4. python -m ml.train: walk-forward on development data, gates, development model. A model is promoted only if
     it passes the gates (or nothing that passed is in place), so a failed run never replaces a passing model.
  5. python -m ml.monitor, only once the final test has run: before that the recent months are the lockbox.

This never runs ml/final_test.py: opening the lockbox is a decision made once, by hand, after the gates pass.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(label: str, args: list[str], allow_fail: bool = False) -> int:
    print(f'\n=== {label}: {" ".join(args)}', flush=True)
    code = subprocess.run([PY, *args], cwd=ROOT).returncode
    if code and not allow_fail:
        raise SystemExit(f'{label} failed (exit {code}); cycle stopped')
    return code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--skip-pull', action='store_true')
    parser.add_argument('--workers', type=int, default=4, help='Dukascopy download workers (more get throttled)')
    args = parser.parse_args()
    symbol = args.symbol.upper()
    name = f'{symbol.lower()}_ict'
    full = '.local/history_dukascopy_full'

    if not args.skip_pull:
        run('pull', ['scripts/pull_dukascopy.py', '--symbol', symbol, '--from', '2003-05-01', '--out', full,
                     '--workers', str(args.workers)])
    run('check history', ['ml/check_history.py', '--symbol', symbol, '--folder', full])
    run('dataset', ['-m', 'ml.dataset', '--symbol', symbol, '--folder', full])
    run('half-spread dataset', ['-m', 'ml.dataset', '--symbol', symbol, '--folder', full,
                                '--name', f'{name}_halfspread', '--spread-scale', '0.5'])
    if (ROOT / '.local' / 'history' / f'{symbol}_m1.csv').exists():
        # The broker file starts with a partial M15/H4 bar MT5 built from minutes before the M1, which the
        # history check rejects; the dataset uses M1 only, whose checks pass. Its recorded spread is a floor, so
        # the broker's prices are graded with Dukascopy's spread.
        run('broker dataset', ['-m', 'ml.dataset', '--symbol', symbol, '--name', f'{name}_exness',
                               '--folder', '.local/history', '--from', '2023-11-24', '--coarse-until', '0',
                               '--spread-from', full, '--allow-unchecked'])
    run('train', ['-m', 'ml.train', '--symbol', symbol])
    models = ROOT / 'ml' / 'models'
    pointer = json.loads((models / f'{symbol.lower()}_ict_v2.json').read_text())
    if (models / f'{symbol.lower()}_final_test.json').exists():
        run('monitor', ['-m', 'ml.monitor', '--symbol', symbol], allow_fail=True)
    print(f"\nPromoted model: {pointer['version']} (development gates "
          f"{'passed' if pointer.get('gates_passed') else 'FAILED'}); report "
          f"ml/reports/{symbol.lower()}_v2_walkforward.md")


if __name__ == '__main__':
    main()
