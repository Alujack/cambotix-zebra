#!/usr/bin/env python3
"""Watch the saved ICT model: live results against the walk-forward, and feature drift (plan section 10, phase 7).

    python -m ml.monitor                                   # drift of the last 90 days vs the training data
    python -m ml.monitor --trades graded.csv               # plus live (or forward-test) results vs expectation

1. Performance. --trades is a CSV or parquet of graded trades of this model with a column `r` (R per filled
   trade, as the grader reports it) and optionally `probability`. With at least --min-trades of them, the mean R
   is compared with the walk-forward expectation saved in the model JSON (`expected`): an ALERT when it is more than
   two standard errors below it, or when the win rate falls outside the 95% binomial band around the expected
   win rate. With `probability`, the report also compares the mean predicted and the actual win rate (calibration).
2. Drift. Candidates of the last --days of the history folder are detected again and compared with the training
   candidates (the dataset rows inside the model's training range) feature by feature with the population
   stability index (PSI, ten training-quantile bins): above 0.25 is an ALERT, above 0.10 a warning. Only the
   features the model uses most (gain) are judged; all are listed.

Writes ml/reports/<symbol>_monitor.md and exits 1 on any ALERT, so a scheduled task can notice.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.data import CRYPTO, load_m1, resample  # noqa: E402
from ml.ict_features import CATEGORICAL, FEATURES, CandidateConfig, detect  # noqa: E402

MODELS = ROOT / 'ml' / 'models'
DATA = ROOT / 'ml' / 'data' / 'xauusd_ict.parquet'
PSI_WARN, PSI_ALERT = 0.10, 0.25
TOP_FEATURES = 10


def psi(expected: np.ndarray, actual: np.ndarray, bins: int = 10) -> float:
    """Population stability index of `actual` against `expected`, on the expected sample's quantile bins (NaN is
    its own bin). 0 = same distribution; 0.1 = moderate shift; 0.25 = large shift."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    if not len(expected) or not len(actual):
        return math.nan
    finite = expected[np.isfinite(expected)]
    edges = np.unique(np.quantile(finite, np.linspace(0, 1, bins + 1))) if len(finite) else np.array([])

    def shares(x):
        nan = ~np.isfinite(x)
        counts = np.histogram(np.clip(x[~nan], edges[0], edges[-1]), edges)[0] if len(edges) > 1 else \
            np.array([(~nan).sum()])
        return np.append(counts, nan.sum()) / len(x)

    e, a = shares(expected), shares(actual)
    e, a = np.maximum(e, 1e-4), np.maximum(a, 1e-4)
    return float(np.sum((a - e) * np.log(a / e)))


def categorical_psi(expected: np.ndarray, actual: np.ndarray) -> float:
    levels = np.union1d(np.unique(expected), np.unique(actual))
    e = np.array([(expected == v).mean() for v in levels])
    a = np.array([(actual == v).mean() for v in levels])
    e, a = np.maximum(e, 1e-4), np.maximum(a, 1e-4)
    return float(np.sum((a - e) * np.log(a / e)))


def drift(train: pd.DataFrame, recent: pd.DataFrame, top: list[str]) -> pd.DataFrame:
    rows = []
    for name in FEATURES:
        value = categorical_psi(train[name].to_numpy(), recent[name].to_numpy()) if name in CATEGORICAL else \
            psi(train[name].to_numpy(), recent[name].to_numpy())
        judged = name in top
        level = 'ALERT' if judged and value > PSI_ALERT else 'warn' if judged and value > PSI_WARN else ''
        rows.append({'feature': name, 'psi': value, 'top': judged, 'level': level,
                     'train_median': float(np.nanmedian(train[name])), 'recent_median': float(np.nanmedian(recent[name]))})
    return pd.DataFrame(rows).sort_values(['top', 'psi'], ascending=[False, False])


def performance(trades: pd.DataFrame, expected: dict, min_trades: int) -> dict:
    """Live R against the walk-forward expectation. `alert` only once there are min_trades trades."""
    r = trades['r'].astype(float).to_numpy()
    n = len(r)
    out = {'trades': n, 'mean_r': float(r.mean()) if n else None, 'win_rate': float((r > 0).mean()) if n else None,
           'expected_r': expected.get('expectancy_r'), 'expected_win': expected.get('win_rate'), 'alerts': []}
    if 'probability' in trades and n:
        out['mean_probability'] = float(trades['probability'].mean())
    if n < min_trades or out['expected_r'] is None:
        out['judged'] = False
        return out
    out['judged'] = True
    sd = expected.get('r_std') or float(np.std(r, ddof=1))
    se = sd / math.sqrt(n)
    out['z'] = (out['mean_r'] - out['expected_r']) / se if se else 0.0
    if out['z'] < -2:
        out['alerts'].append(f"mean {out['mean_r']:+.3f}R over {n} trades is {out['z']:.1f} standard errors below "
                             f"the walk-forward's {out['expected_r']:+.3f}R")
    p = out['expected_win']
    if p is not None:
        band = 1.96 * math.sqrt(p * (1 - p) / n)
        out['win_band'] = (p - band, p + band)
        if not p - band <= out['win_rate'] <= p + band:
            out['alerts'].append(f"win rate {out['win_rate']:.1%} is outside the expected {p - band:.1%}-{p + band:.1%}")
    return out


def recent_candidates(symbol: str, folder: Path, days: int, rr: float) -> pd.DataFrame:
    """Candidates of the last `days` of the history, detected with enough warm-up for every feature."""
    m1 = load_m1(symbol, folder)
    m5 = resample(m1, 300)
    since = int(m5.t[-1]) - days * 86400
    first = int(np.searchsorted(m5.t, since))
    lo = max(0, first - 15_000)                       # the slowest feature needs ~15,000 bars (ml/predict.py)
    rows = detect(symbol, m5.slice(lo, len(m5)), CandidateConfig(rr=rr, crypto=symbol in CRYPTO),
                  start_index=first - lo)
    return pd.DataFrame(rows)


def report(symbol: str, meta: dict, perf: dict | None, table: pd.DataFrame, recent_n: int, train_n: int,
           days: int) -> tuple[str, bool]:
    alerts = list(perf['alerts']) if perf else []
    alerts += [f"{r.feature}: PSI {r.psi:.2f}" for r in table.itertuples() if r.level == 'ALERT']
    lines = [f'# {symbol} ICT model monitor ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)', '',
             f"Model `{meta['version']}`, trained {meta['trained_from']} .. {meta['trained_to']}, gates "
             f"{'passed' if meta.get('gates_passed') else 'FAILED (not used for signals)'}. "
             f"Result: **{'ALERT' if alerts else 'ok'}**.", '']
    if alerts:
        lines += ['Alerts:', ''] + [f'- {a}' for a in alerts] + ['']
    lines += ['## Performance against the walk-forward', '']
    if perf is None:
        lines += ['No graded trades given (--trades).']
    else:
        exp_r, exp_win = perf['expected_r'], perf['expected_win']
        exp_r_text = '-' if exp_r is None else f'{exp_r:+.3f}R'
        exp_win_text = '-' if exp_win is None else f'{exp_win:.1%}'
        lines += [f"{perf['trades']} trades, mean {perf['mean_r']:+.3f}R, win rate {perf['win_rate']:.1%}; "
                  f"walk-forward expectation {exp_r_text}, win rate {exp_win_text}."
                  if perf['trades'] else 'No trades yet.']
        if not perf['judged']:
            lines.append('Not judged yet: fewer trades than --min-trades.')
        if 'mean_probability' in perf:
            lines.append(f"Calibration: mean predicted win {perf['mean_probability']:.1%} vs actual {perf['win_rate']:.1%}.")
    lines += ['', f'## Feature drift: last {days} days ({recent_n} candidates) vs training ({train_n} candidates)', '',
              f'PSI above {PSI_WARN} is a warning and above {PSI_ALERT} an alert, judged on the model\'s '
              f'{TOP_FEATURES} most important features.', '',
              '| Feature | Top | PSI | Level | Training median | Recent median |', '|---|---|---|---|---|---|']
    lines += [f"| {r.feature} | {'yes' if r.top else ''} | {r.psi:.3f} | {r.level} | {r.train_median:.3f} | "
              f"{r.recent_median:.3f} |" for r in table.itertuples()]
    return '\n'.join(lines) + '\n', bool(alerts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--models', type=Path, default=MODELS)
    parser.add_argument('--data', type=Path, default=DATA, help='the dataset the model was trained on')
    parser.add_argument('--folder', type=Path, default=ROOT / '.local' / 'history_dukascopy_full')
    parser.add_argument('--days', type=int, default=90, help='recent window for drift')
    parser.add_argument('--trades', type=Path, help='graded trades (CSV or parquet with r, optional probability)')
    parser.add_argument('--min-trades', type=int, default=50)
    args = parser.parse_args()

    symbol = args.symbol.upper()
    started = time.time()
    meta = json.loads((args.models / f'{symbol.lower()}_ict_lgbm.json').read_text())
    importance = meta.get('importance') or []
    top = importance[:TOP_FEATURES] if importance else list(FEATURES[:TOP_FEATURES])
    data = pd.read_parquet(args.data)
    lo = datetime.fromisoformat(meta['trained_from']).replace(tzinfo=timezone.utc).timestamp()
    hi = datetime.fromisoformat(meta['trained_to']).replace(tzinfo=timezone.utc).timestamp() + 86400
    train = data[(data['bar_time'] >= lo) & (data['bar_time'] < hi)]
    recent = recent_candidates(symbol, args.folder, args.days, float(meta.get('rr', 2.0)))
    table = drift(train, recent, top) if len(recent) else pd.DataFrame(columns=['feature', 'psi', 'top', 'level'])
    perf = None
    if args.trades:
        trades = pd.read_parquet(args.trades) if args.trades.suffix == '.parquet' else pd.read_csv(args.trades)
        perf = performance(trades, meta.get('expected') or {}, args.min_trades)
    text, alert = report(symbol, meta, perf, table, len(recent), len(train), args.days)
    path = ROOT / 'ml' / 'reports' / f'{symbol.lower()}_monitor.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    print(text)
    print(f'report -> {path} ({time.time() - started:.0f}s)')
    sys.exit(1 if alert else 0)


if __name__ == '__main__':
    main()
