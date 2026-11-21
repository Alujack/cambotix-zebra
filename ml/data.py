"""Saved broker history as numpy arrays.

CSV files are the ones scripts/pull_history.py (MT5) and scripts/pull_dukascopy.py write: columns t,o,h,l,c,spread
with t = bar open time in UTC seconds and spread in price units. M5 is always rebuilt from M1 so the features and
the grader see exactly the same prices.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / '.local'

# Longest clean M1 history per symbol. EURUSD uses six years of Dukascopy; the rest are Exness MT5 pulls.
SOURCES = {
    'EURUSD': LOCAL / 'history_dukascopy6y',
}
DEFAULT_SOURCE = LOCAL / 'history'

ASSET_CLASS = {
    'XAUUSD': 'metal', 'XAGUSD': 'metal',
    'US30': 'index', 'USTEC': 'index',
    'BTCUSD': 'crypto',
}
CRYPTO = {'BTCUSD', 'BTCUSDT'}

ALL_SYMBOLS = ('XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURJPY', 'GBPJPY',
               'XAGUSD', 'US30', 'USTEC', 'BTCUSD')


def asset_class(symbol: str) -> str:
    return ASSET_CLASS.get(symbol.upper(), 'fx')


@dataclass
class Bars:
    """Column arrays of one timeframe; t is the open time in UTC seconds."""
    t: np.ndarray
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    spread: np.ndarray

    def __len__(self) -> int:
        return len(self.t)

    def slice(self, lo: int, hi: int) -> 'Bars':
        return Bars(*(getattr(self, k)[lo:hi] for k in ('t', 'o', 'h', 'l', 'c', 'spread')))

    def dicts(self, lo: int, hi: int) -> list[dict]:
        """Rows lo..hi as the dicts app.grader expects."""
        return [{'t': int(self.t[k]), 'o': float(self.o[k]), 'h': float(self.h[k]), 'l': float(self.l[k]),
                 'c': float(self.c[k]), 'spread': float(self.spread[k])} for k in range(lo, hi)]


def from_frame(df: pd.DataFrame) -> Bars:
    spread = df['spread'] if 'spread' in df else pd.Series(0.0, index=df.index)
    return Bars(df['t'].to_numpy(np.int64), df['o'].to_numpy(float), df['h'].to_numpy(float),
                df['l'].to_numpy(float), df['c'].to_numpy(float), spread.fillna(0.0).to_numpy(float))


def from_dicts(rows: list[dict]) -> Bars:
    return from_frame(pd.DataFrame(rows))


def m1_path(symbol: str, folder: Path | None = None) -> Path:
    base = folder or SOURCES.get(symbol.upper(), DEFAULT_SOURCE)
    return Path(base) / f'{symbol.upper()}_m1.csv'


def load_m1(symbol: str, folder: Path | None = None, start: int | None = None, end: int | None = None) -> Bars:
    path = m1_path(symbol, folder)
    if not path.exists():
        raise FileNotFoundError(f'missing {path}: pull it with scripts/pull_history.py or scripts/pull_dukascopy.py')
    df = pd.read_csv(path, dtype={'t': np.int64})
    df = df.drop_duplicates('t').sort_values('t')
    if start is not None:
        df = df[df['t'] >= start]
    if end is not None:
        df = df[df['t'] < end]
    return from_frame(df.reset_index(drop=True))


def resample(m1: Bars, seconds: int = 300) -> Bars:
    """Aggregate M1 into `seconds` bars on UTC boundaries (as scripts/backtest.m5_from_m1). Spread = the mean."""
    key = m1.t - m1.t % seconds
    df = pd.DataFrame({'k': key, 'o': m1.o, 'h': m1.h, 'l': m1.l, 'c': m1.c, 's': m1.spread})
    g = df.groupby('k', sort=True)
    out = pd.DataFrame({'t': g['k'].first(), 'o': g['o'].first(), 'h': g['h'].max(), 'l': g['l'].min(),
                        'c': g['c'].last(), 'spread': g['s'].mean()})
    return from_frame(out.reset_index(drop=True))
