"""The lockbox: the final two years of candidates, kept away from all development code (plan v2, V2.0).

    development file   ml/data/<name>_dev.parquet               trade window ends before LOCK_START
    lockbox file       ml/data/lockbox/<name>_lockbox.parquet   candidates from LOCK_START on

Rules, enforced here:
  - `split` puts every candidate in exactly one of the two files, or in neither if its trade window straddles
    LOCK_START.
  - `guard` raises LockboxError for a frame holding any row of the lockbox period; ml.train.load calls it on
    everything it reads, so development code cannot train on or score a wrong file by accident.
  - `open_once` is the only reader of the lockbox file. It is called by ml/final_test.py only, requires that the
    final test has not run before, and `seal` then records the result; a second call raises LockboxError.
    tests/test_lockbox.py checks that no other module under ml/ mentions the reader or the lockbox folder.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'ml' / 'data'
LOCK_START = '2024-11-20'
LOCK_EPOCH = int(datetime.strptime(LOCK_START, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())


class LockboxError(Exception):
    """Development code touched lockbox data, or the final test was asked to run twice."""


def split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    """(development rows, lockbox rows, number of straddling rows dropped)."""
    if not len(df):
        return df, df, 0
    dev = df[df['end_time'] < LOCK_EPOCH]
    locked = df[df['bar_time'] >= LOCK_EPOCH]
    return dev, locked, len(df) - len(dev) - len(locked)


def guard(df: pd.DataFrame, what: str = 'data') -> pd.DataFrame:
    """Return df unchanged, or raise if it holds anything from the lockbox period."""
    if len(df) and (df['bar_time'].max() >= LOCK_EPOCH or df['end_time'].max() >= LOCK_EPOCH):
        raise LockboxError(f'{what} contains rows from {LOCK_START} on: that is lockbox data, which only '
                           'ml/final_test.py may read, once')
    return df


def dev_file(name: str, folder: Path = DATA) -> Path:
    return Path(folder) / f'{name}_dev.parquet'


def locked_file(name: str, folder: Path = DATA) -> Path:
    return Path(folder) / 'lockbox' / f'{name}_lockbox.parquet'


def record_file(symbol: str, models: Path) -> Path:
    return Path(models) / f'{symbol.lower()}_final_test.json'


def write(df: pd.DataFrame, name: str, folder: Path = DATA) -> tuple[Path, Path, dict]:
    """Split df and write both files. Returns their paths and the row counts."""
    dev, locked, dropped = split(df)
    dev_path, locked_path = dev_file(name, folder), locked_file(name, folder)
    locked_path.parent.mkdir(parents=True, exist_ok=True)
    dev.to_parquet(dev_path, index=False)
    locked.to_parquet(locked_path, index=False)
    return dev_path, locked_path, {'development': int(len(dev)), 'lockbox': int(len(locked)),
                                   'straddling_dropped': int(dropped)}


def record(symbol: str, models: Path) -> dict | None:
    """The saved result of the final test, or None if it has not run."""
    path = record_file(symbol, models)
    return json.loads(path.read_text()) if path.exists() else None


def open_once(name: str, symbol: str, models: Path, folder: Path = DATA) -> pd.DataFrame:
    """The lockbox candidates. Raises if the final test already ran for this symbol."""
    done = record(symbol, models)
    if done is not None:
        raise LockboxError(f"the final test already ran on {done.get('ran_at')} (result: "
                           f"{'passed' if done.get('passed') else 'failed'}); the lockbox is not opened twice")
    path = locked_file(name, folder)
    if not path.exists():
        raise FileNotFoundError(f'no lockbox file {path}: build it with python -m ml.dataset')
    return pd.read_parquet(path)


def seal(symbol: str, models: Path, result: dict) -> Path:
    """Record the final test's result. From now on `open_once` refuses."""
    path = record_file(symbol, models)
    if path.exists():
        raise LockboxError(f'{path} already exists; the final test result is never overwritten')
    Path(models).mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**result, 'ran_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')},
                               indent=1, default=str))
    return path
