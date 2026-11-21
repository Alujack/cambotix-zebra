#!/usr/bin/env python3
"""Monthly retrain of the gold ICT model (plan section 10): refresh history, check it, rebuild, retrain, promote.

    python -m ml.retrain                  # full cycle
    python -m ml.retrain --skip-pull      # history is already current

Steps, each stopping the cycle if it fails:
  1. scripts/pull_dukascopy.py --from 2003-05-01 --out .local/history_dukascopy_full (resumable: only the current
     year is fetched again)
  2. ml/check_history.py on that folder (must pass)
  3. python -m ml.dataset (Dukascopy) and, when .local/history has the broker M1, the Exness dataset for gate 5
  4. python -m ml.train: walk-forward, gates, final model. ml/train.py promotes the new version only if it passes
     the gates (or nothing that passed is in place), so a failed retrain never replaces a passing model.
  5. python -m ml.monitor: drift of the last 90 days against the new training data

Schedule it monthly (Windows Task Scheduler, or cron) once a model is in use; until then run it by hand.
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
        raise SystemExit(f'{label} failed (exit {code}); retrain stopped')
    return code


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--skip-pull', action='store_true')
    parser.add_argument('--workers', type=int, default=4, help='Dukascopy download workers (more get throttled)')
    args = parser.parse_args()
    symbol = args.symbol.upper()
    full = '.local/history_dukascopy_full'

    if not args.skip_pull:
        run('pull', ['scripts/pull_dukascopy.py', '--symbol', symbol, '--from', '2003-05-01', '--out', full,
                     '--workers', str(args.workers)])
    run('check history', ['ml/check_history.py', '--symbol', symbol, '--folder', full])
    run('dataset', ['-m', 'ml.dataset', '--symbol', symbol, '--folder', full])
    broker = ROOT / '.local' / 'history' / f'{symbol}_m1.csv'
    if broker.exists():
        # The broker file starts with a partial M15/H4 bar MT5 built from minutes before the M1, which the
        # history check rejects; the dataset uses M1 only, whose checks pass.
        run('broker dataset', ['-m', 'ml.dataset', '--symbol', symbol, '--folder', '.local/history',
                               '--from', '2023-11-24', '--coarse-until', '0', '--allow-unchecked',
                               '--out', f'ml/data/{symbol.lower()}_ict_exness.parquet',
                               '--report', f'ml/reports/{symbol.lower()}_ict_dataset_exness.md'])
    run('train', ['-m', 'ml.train', '--symbol', symbol])
    pointer = json.loads((ROOT / 'ml' / 'models' / f'{symbol.lower()}_ict_lgbm.json').read_text())
    run('monitor', ['-m', 'ml.monitor', '--symbol', symbol], allow_fail=True)
    print(f"\nIn use: {pointer['version']} (gates {'passed' if pointer.get('gates_passed') else 'FAILED'}); "
          f"report ml/reports/{symbol.lower()}_walkforward.md")


if __name__ == '__main__':
    main()
