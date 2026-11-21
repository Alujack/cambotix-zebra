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


def repair_spread(m1: Bars, coarse_before_year: int | None = None) -> tuple[Bars, dict]:
    """Make the recorded spread safe to grade with (docs/ml-plan.md section 3, data check findings).

    - A spread of zero or less (Dukascopy 2012 has a few thousand) becomes the median positive spread of the same
      UTC hour in the same year, or that year's median when the hour has none.
    - Years before `coarse_before_year` have a coarse spread with no news spikes (Dukascopy gold before 2011 never
      exceeds 0.706), so every bar there is raised to at least that year's 99th-percentile spread. That makes those
      years more expensive to trade, never cheaper.

    Returns the repaired bars (prices untouched) and a report of what changed per year."""
    spread = m1.spread.astype(float).copy()
    year = m1.t.astype('datetime64[s]').astype('datetime64[Y]').astype(np.int64) + 1970
    hour = (m1.t % 86400) // 3600
    report: dict[str, dict] = {}
    df = pd.DataFrame({'year': year, 'hour': hour, 's': spread})
    positive = df[df['s'] > 0]
    hour_median = positive.groupby(['year', 'hour'])['s'].median()
    year_median = positive.groupby('year')['s'].median()
    bad = df['s'] <= 0
    if bad.any():
        keys = list(zip(df.loc[bad, 'year'], df.loc[bad, 'hour']))
        fill = np.array([hour_median.get(k, year_median.get(k[0], 0.0)) for k in keys], dtype=float)
        spread[bad.to_numpy()] = fill
        for y, count in df.loc[bad, 'year'].value_counts().items():
            report.setdefault(str(int(y)), {})['zero_replaced'] = int(count)
    if coarse_before_year is not None:
        for y in np.unique(year[year < coarse_before_year]):
            mask = year == y
            floor = float(np.quantile(spread[mask], 0.99))
            raised = int((spread[mask] < floor).sum())
            spread[mask] = np.maximum(spread[mask], floor)
            report.setdefault(str(int(y)), {}).update({'coarse_floor': round(floor, 6), 'raised': raised})
    return Bars(m1.t, m1.o, m1.h, m1.l, m1.c, spread), report


def resample(m1: Bars, seconds: int = 300) -> Bars:
    """Aggregate M1 into `seconds` bars on UTC boundaries (as scripts/backtest.m5_from_m1). Spread = the mean."""
    key = m1.t - m1.t % seconds
    df = pd.DataFrame({'k': key, 'o': m1.o, 'h': m1.h, 'l': m1.l, 'c': m1.c, 's': m1.spread})
    g = df.groupby('k', sort=True)
    out = pd.DataFrame({'t': g['k'].first(), 'o': g['o'].first(), 'h': g['h'].max(), 'l': g['l'].min(),
                        'c': g['c'].last(), 'spread': g['s'].mean()})
    return from_frame(out.reset_index(drop=True))
