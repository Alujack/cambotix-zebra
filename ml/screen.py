"""Idea screen: the cheap test that comes before any model (docs/ml-plan.md V2.10, lesson 1).

A trading idea is a list of entries (M1 bar, side, stop distance, target distance, hold). The screen walks every
entry through M1 at three costs (zero spread, half spread, the recorded spread), keeps one position at a time, and
reports the result separately for a discovery period and a confirmation period. An idea that makes nothing at
zero cost is dropped there; nothing here trains a model.

Only development data is ever loaded: bars from the lockbox period (ml.lockbox.LOCK_EPOCH on) are cut off at load.

Price convention (bid candles plus spread, as the saved history): a buy enters at the ask (open + spread) and exits
at the bid; a sell enters at the bid and exits at the ask (bid + spread). Stop and target levels are measured from
the bid open of the entry bar. If one M1 bar reaches both, the stop counts. A stop that the bar opens beyond is
filled at that open.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ml import lockbox
from ml.data import LOCAL, Bars, load_m1, repair_spread

FOLDER = LOCAL / 'history_dukascopy_full'
CACHE = LOCAL / 'screen_cache'
WARMUP_START = '2010-06-01'
DISCOVERY = ('2011-01-01', '2019-01-01')
CONFIRM = ('2019-01-01', lockbox.LOCK_START)
COSTS = (0.0, 0.5, 1.0)
TARGET, STOP, TIMEOUT = 0, 1, 2

# The pass rule, fixed before the first run.
RULE = {
    'zero_cost_discovery_r': 0.03,     # mean R at zero spread, discovery
    'zero_cost_discovery_t': 2.0,
    'real_cost_discovery_r': 0.0,      # mean R at the recorded spread, discovery
    'confirm_r': 0.05,                 # mean R at the recorded spread, confirmation
    'confirm_pf': 1.15,
    'confirm_years_positive': 0.6,
    'confirm_trades_per_year': 50,
}


def epoch(day: str) -> int:
    return int(pd.Timestamp(day, tz='UTC').timestamp())


def load(symbol: str = 'XAUUSD', folder: Path = FOLDER, start: str = WARMUP_START, end: int = lockbox.LOCK_EPOCH,
         coarse_until: int | None = 2011, cache: bool = True) -> Bars:
    """Development M1 with the repaired spread; cached as .npz because the CSV takes a while to parse."""
    path = CACHE / f'{symbol}_{Path(folder).name}_{start}_{end}.npz'
    if cache and path.exists():
        z = np.load(path)
        return Bars(z['t'], z['o'], z['h'], z['l'], z['c'], z['spread'])
    m1 = load_m1(symbol, folder, epoch(start), end)
    m1, _ = repair_spread(m1, coarse_until)
    if cache:
        CACHE.mkdir(parents=True, exist_ok=True)
        np.savez(path, t=m1.t, o=m1.o, h=m1.h, l=m1.l, c=m1.c, spread=m1.spread)
    return m1


def simulate(m1: Bars, entry, side, stop, target, hold, cost: float = 1.0, chunk: int = 3000) -> pd.DataFrame:
    """Walk each entry through M1. entry = index of the M1 bar whose open is the fill; side = +1 buy / -1 sell;
    stop and target = distances in price (target may be inf for a time exit); hold = minutes.
    Returns r (in units of the stop distance), kind (TARGET/STOP/TIMEOUT), entry_t, exit_t and resolved."""
    entry = np.asarray(entry, dtype=np.int64)
    n = len(entry)
    side = np.broadcast_to(np.asarray(side, dtype=float), (n,))
    stop = np.broadcast_to(np.asarray(stop, dtype=float), (n,))
    target = np.broadcast_to(np.asarray(target, dtype=float), (n,))
    hold = np.broadcast_to(np.asarray(hold, dtype=np.int64), (n,))
    spread = m1.spread * cost
    total = len(m1)
    r = np.full(n, np.nan)
    kind = np.full(n, -1, dtype=np.int8)
    exit_t = np.zeros(n, dtype=np.int64)
    for a in range(0, n, chunk):
        e, s, sd, td, hd = entry[a:a + chunk], side[a:a + chunk], stop[a:a + chunk], target[a:a + chunk], hold[a:a + chunk]
        width = int(hd.max())
        idx = e[:, None] + np.arange(width)[None, :]
        inside = idx < total
        idx = np.minimum(idx, total - 1)
        t0 = m1.t[e]
        live = inside & (m1.t[idx] < (t0 + hd * 60)[:, None])
        o0 = m1.o[e]
        buy = (s > 0)[:, None]
        stop_level = (o0 - s * sd)[:, None]
        target_level = (o0 + s * td)[:, None]
        H, L, S = m1.h[idx], m1.l[idx], spread[idx]
        hit_stop = np.where(buy, L <= stop_level, H + S >= stop_level) & live
        hit_target = np.where(buy, H >= target_level, L + S <= target_level) & live
        first_stop = np.where(hit_stop.any(1), hit_stop.argmax(1), width)
        first_target = np.where(hit_target.any(1), hit_target.argmax(1), width)
        last = np.maximum(live.sum(1) - 1, 0)
        k = np.where(first_stop <= first_target, first_stop, first_target)
        what = np.where((first_stop <= first_target) & (first_stop < width), STOP,
                        np.where(first_target < width, TARGET, TIMEOUT))
        k = np.where(what == TIMEOUT, last, k)
        rows = np.arange(len(e))
        bar = idx[rows, k]
        open_k, close_k, spread_k = m1.o[bar], m1.c[bar], spread[bar]
        is_buy = s > 0
        stop_fill = np.where(is_buy, np.minimum(stop_level[:, 0], open_k), np.maximum(stop_level[:, 0], open_k + spread_k))
        time_fill = np.where(is_buy, close_k, close_k + spread_k)
        price = np.where(what == STOP, stop_fill, np.where(what == TARGET, target_level[:, 0], time_fill))
        entry_price = np.where(is_buy, o0 + spread[e], o0)
        r[a:a + chunk] = s * (price - entry_price) / sd
        kind[a:a + chunk] = what
        exit_t[a:a + chunk] = m1.t[bar] + 60
    resolved = m1.t[entry] + hold * 60 <= m1.t[-1]
    return pd.DataFrame({'entry_t': m1.t[entry], 'exit_t': exit_t, 'side': side, 'r': r, 'kind': kind,
                         'resolved': resolved})


def non_overlapping(entry_t: np.ndarray, exit_t: np.ndarray) -> np.ndarray:
    """Mask of the trades taken when only one position may be open (rows must be sorted by entry time)."""
    keep = np.zeros(len(entry_t), dtype=bool)
    free = -1
    for k in range(len(entry_t)):
        if entry_t[k] >= free:
            keep[k] = True
            free = exit_t[k]
    return keep


def stats(trades: pd.DataFrame) -> dict:
    r = trades['r'].to_numpy()
    n = len(r)
    if n == 0:
        return {'n': 0, 'win': np.nan, 'mean': np.nan, 'total': 0.0, 'pf': np.nan, 't': np.nan, 'dd': 0.0,
                'per_year': 0.0, 'years': 0, 'years_positive': 0}
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    curve = np.cumsum(r)
    year = pd.to_datetime(trades['entry_t'], unit='s').dt.year
    by_year = trades.groupby(year.to_numpy())['r'].sum()
    span = (trades['entry_t'].max() - trades['entry_t'].min()) / (365.25 * 86400)
    sd = r.std(ddof=1) if n > 1 else np.nan
    return {'n': n, 'win': float((r > 0).mean()), 'mean': float(r.mean()), 'total': float(r.sum()),
            'pf': float(gains / losses) if losses > 0 else np.nan,
            't': float(r.mean() / (sd / np.sqrt(n))) if sd and sd > 0 else np.nan,
            'dd': float((np.maximum.accumulate(np.maximum(curve, 0)) - curve).max()),
            'per_year': float(n / span) if span > 0 else float(n), 'years': int(len(by_year)),
            'years_positive': int((by_year > 0).sum())}


def run(m1: Bars, signals: pd.DataFrame, cost: float) -> pd.DataFrame:
    """Simulate, drop the unresolved, keep one position at a time."""
    if len(signals) == 0:
        return pd.DataFrame({'entry_t': [], 'exit_t': [], 'side': [], 'r': [], 'kind': [], 'resolved': [],
                             'stop': []})
    signals = signals.sort_values('i', kind='stable')
    out = simulate(m1, signals['i'].to_numpy(), signals['side'].to_numpy(), signals['stop'].to_numpy(),
                   signals['target'].to_numpy(), signals['hold'].to_numpy(), cost)
    out['stop'] = signals['stop'].to_numpy()
    out = out[out['resolved']].reset_index(drop=True)
    return out[non_overlapping(out['entry_t'].to_numpy(), out['exit_t'].to_numpy())].reset_index(drop=True)


def window(trades: pd.DataFrame, period: tuple[str, str]) -> pd.DataFrame:
    return trades[(trades['entry_t'] >= epoch(period[0])) & (trades['entry_t'] < epoch(period[1]))]


def evaluate(m1: Bars, signals: pd.DataFrame, discovery=DISCOVERY, confirm=CONFIRM, costs=COSTS) -> dict:
    """Discovery and confirmation statistics at each cost, and the verdict by RULE."""
    result = {}
    for cost in costs:
        trades = run(m1, signals, cost)
        result[cost] = {'discovery': stats(window(trades, discovery)), 'confirm': stats(window(trades, confirm))}
    result['verdict'] = verdict(result)
    return result


def verdict(result: dict) -> str:
    zero, real = result[0.0], result[1.0]
    d0, d1, c1 = zero['discovery'], real['discovery'], real['confirm']
    if d0['n'] < 100:
        return 'too few trades'
    if not (d0['mean'] >= RULE['zero_cost_discovery_r'] and d0['t'] >= RULE['zero_cost_discovery_t']):
        return 'no edge before costs'
    if not d1['mean'] > RULE['real_cost_discovery_r']:
        return 'edge smaller than the spread'
    ok = (c1['n'] > 0 and c1['mean'] >= RULE['confirm_r'] and c1['pf'] >= RULE['confirm_pf']
          and c1['years_positive'] >= RULE['confirm_years_positive'] * c1['years']
          and c1['per_year'] >= RULE['confirm_trades_per_year'])
    return 'PASSED' if ok else 'failed confirmation'
