#!/usr/bin/env python3
"""Train the ICT setup model with an honest walk-forward, then fit and save the final model.

    python -m ml.train                                   # walk-forward report + final model
    python -m ml.train --test-start 2025-01-01 --fold-months 2
    python -m ml.train --no-final                        # report only

What it does, per test fold (default: quarters from 2024-07-01 to the end of the data):
  1. Train only on trades that were *finished* before the fold starts, minus a one-day embargo (no overlap leaks).
  2. Hold out the last 20% of that training period: LightGBM early-stops on it and the probability threshold is
     chosen on it (best mean R x sqrt(trades), at least --min-val-trades). If no threshold made money there, the
     model takes no trades in that fold: "don't trade" is a valid answer.
  3. Refit on the whole training period and score every candidate in the fold, filled or not. Unfilled limits
     score 0R and still block the slot until they expire, exactly as live.
  4. One open plan per symbol and side (the analyzer's MAX_OPEN_SAME_DIRECTION=1), applied to every policy.

The same folds are run with shuffled training labels as a control: any "edge" the control also shows is noise.
Baselines: every candidate, and the ict_engine-style subset (killzone sweep of a session/day pool).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from ml.data import ROOT
from ml.ict_features import CATEGORICAL, FEATURES

DATA = ROOT / 'ml' / 'data' / 'ict_dataset.csv.gz'
MODELS = ROOT / 'ml' / 'models'
REPORTS = ROOT / 'ml' / 'reports'
EMBARGO = 86_400

PARAMS = {
    'objective': 'binary', 'learning_rate': 0.03, 'num_leaves': 15, 'min_data_in_leaf': 150,
    'feature_fraction': 0.8, 'bagging_fraction': 0.8, 'bagging_freq': 1, 'lambda_l2': 5.0,
    'max_depth': 5, 'verbose': -1, 'seed': 7, 'num_threads': 2,
}


# -- data ---------------------------------------------------------------------------------------------
def load(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df = df[df['outcome'] != 'unresolved'].copy()
    for col in CATEGORICAL:
        df[col] = df[col].astype(int)
    df['filled'] = df['outcome'] == 'closed'
    return df.sort_values(['bar_time', 'symbol']).reset_index(drop=True)


def epoch(day: str) -> int:
    return int(datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())


def day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d')


def folds(df: pd.DataFrame, start: str, months: int) -> list[tuple[int, int]]:
    edges = pd.date_range(start, datetime.fromtimestamp(df['bar_time'].max(), timezone.utc).strftime('%Y-%m-%d'),
                          freq=f'{months}MS', tz='UTC')
    edges = [int(e.timestamp()) for e in edges] + [int(df['bar_time'].max()) + 1]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b > a]


# -- model --------------------------------------------------------------------------------------------
def fit(train: pd.DataFrame, valid: pd.DataFrame | None, rounds: int | None = None, shuffle: int | None = None):
    y = train['win'].to_numpy()
    if shuffle is not None:
        y = np.random.default_rng(shuffle).permutation(y)
    dtrain = lgb.Dataset(train[list(FEATURES)], y, categorical_feature=list(CATEGORICAL), free_raw_data=False)
    if valid is None:
        return lgb.train(PARAMS, dtrain, num_boost_round=rounds or 200)
    yv = valid['win'].to_numpy()
    if shuffle is not None:
        yv = np.random.default_rng(shuffle + 1).permutation(yv)
    dvalid = lgb.Dataset(valid[list(FEATURES)], yv, categorical_feature=list(CATEGORICAL), reference=dtrain)
    return lgb.train(PARAMS, dtrain, num_boost_round=1000, valid_sets=[dvalid],
                     callbacks=[lgb.early_stopping(50, verbose=False)])


def predict(model, df: pd.DataFrame) -> np.ndarray:
    return model.predict(df[list(FEATURES)], num_iteration=model.best_iteration or None)


def choose_threshold(prob: np.ndarray, r: np.ndarray, min_trades: int) -> tuple[float, dict]:
    """Probability cut that maximised mean R x sqrt(n) on validation; +inf when nothing was profitable."""
    best = (0.0, math.inf, {'n': 0, 'mean_r': 0.0})
    for q in np.arange(0.0, 0.96, 0.05):
        cut = float(np.quantile(prob, q))
        sel = r[prob >= cut]
        if len(sel) < min_trades:
            continue
        score = sel.mean() * math.sqrt(len(sel))
        if score > best[0]:
            best = (score, cut, {'n': int(len(sel)), 'mean_r': float(sel.mean()), 'top_fraction': float(1 - q)})
    return best[1], best[2]


# -- evaluation ---------------------------------------------------------------------------------------
def take_non_overlapping(df: pd.DataFrame) -> pd.DataFrame:
    """One open plan per symbol and side; a plan blocks its slot until it closes or its limit expires."""
    busy: dict[tuple[str, str], float] = {}
    keep = []
    for idx, row in zip(df.index, df[['symbol', 'side', 'bar_time', 'end_time']].itertuples(index=False)):
        key = (row.symbol, row.side)
        if row.bar_time >= busy.get(key, -1):
            keep.append(idx)
            busy[key] = row.end_time
    return df.loc[keep]


def stats(trades: pd.DataFrame) -> dict:
    filled = trades[trades['filled']]
    r = filled['r'].to_numpy()
    if not len(r):
        return {'signals': int(len(trades)), 'trades': 0, 'win_rate': None, 'expectancy_r': None, 'total_r': 0.0,
                'profit_factor': None, 'max_drawdown_r': 0.0}
    order = filled.sort_values('end_time')['r'].to_numpy()
    equity = np.cumsum(order)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], equity]))[1:] - equity)) if len(equity) else 0.0
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {'signals': int(len(trades)), 'trades': int(len(r)), 'win_rate': float((r > 0).mean()),
            'expectancy_r': float(r.mean()), 'total_r': float(r.sum()),
            'profit_factor': float(gains / losses) if losses else None, 'max_drawdown_r': max(dd, 0.0)}


def walk_forward(df: pd.DataFrame, start: str, months: int, min_val: int, shuffle: int | None = None) -> pd.DataFrame:
    """Scored test candidates (all folds) with columns prob, threshold, fold."""
    filled = df[df['filled']]
    scored = []
    for a, b in folds(df, start, months):
        train = filled[filled['end_time'] < a - EMBARGO]
        if len(train) < 2000:
            continue
        cut = train['bar_time'].quantile(0.8)
        fit_part, val_part = train[train['bar_time'] < cut], train[train['bar_time'] >= cut]
        val_part = val_part[val_part['bar_time'] >= fit_part['end_time'].max() + 0] if False else val_part
        model = fit(fit_part, val_part, shuffle=shuffle)
        rounds = max(model.best_iteration or 0, 20)
        threshold, info = choose_threshold(predict(model, val_part), val_part['r'].to_numpy(), min_val)
        final = fit(train, None, rounds=rounds, shuffle=shuffle)
        test = df[(df['bar_time'] >= a) & (df['bar_time'] < b)].copy()
        if not len(test):
            continue
        test['prob'] = final.predict(test[list(FEATURES)])
        test['threshold'] = threshold
        test['fold'] = day(a)
        test['val_trades'] = info['n']
        test['rounds'] = rounds
        scored.append(test)
    return pd.concat(scored) if scored else pd.DataFrame()


def policies(scored: pd.DataFrame) -> dict[str, pd.DataFrame]:
    engine = (scored['in_killzone'] == 1) & (scored['pool_kind'] < 4)
    return {
        'all candidates': take_non_overlapping(scored),
        'ict_engine-style (killzone, session pools)': take_non_overlapping(scored[engine]),
        'model': take_non_overlapping(scored[scored['prob'] >= scored['threshold']]),
    }


def fmt(s: dict) -> str:
    if not s['trades']:
        return f"| {s['signals']} | 0 | - | - | 0.0 | - | 0.0 |"
    pf = '-' if s['profit_factor'] is None else f"{s['profit_factor']:.2f}"
    return (f"| {s['signals']} | {s['trades']} | {s['win_rate']:.1%} | {s['expectancy_r']:+.3f} | "
            f"{s['total_r']:+.1f} | {pf} | {s['max_drawdown_r']:.1f} |")


HEAD = '| | signals | filled trades | win | exp R | total R | PF | max DD R |\n|---|---|---|---|---|---|---|---|'


def report(df: pd.DataFrame, scored: pd.DataFrame, control: pd.DataFrame, final_meta: dict | None,
           importance: pd.Series | None, args) -> str:
    lines = [f'# ICT model walk-forward ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)', '',
             f'Dataset: {len(df)} resolved candidates ({int(df["filled"].sum())} filled) on '
             f'{df["symbol"].nunique()} symbols, {day(df["bar_time"].min())} .. {day(df["bar_time"].max())}. '
             f'Test folds: {args.fold_months}-month steps from {args.test_start}; one-day embargo; '
             'thresholds chosen on the last 20% of each training window only.', '']
    filled_test = scored[scored['filled']]
    if len(filled_test) and filled_test['win'].nunique() == 2:
        auc = roc_auc_score(filled_test['win'], filled_test['prob'])
        cauc = roc_auc_score(control[control['filled']]['win'], control[control['filled']]['prob'])
        lines += [f'Out-of-sample AUC on filled trades: **{auc:.3f}** (shuffled-label control {cauc:.3f}; 0.5 = no skill).', '']
    lines += ['## Out-of-sample result (all folds)', '', HEAD]
    pol = policies(scored)
    for name, trades in pol.items():
        lines.append(f'| {name} ' + fmt(stats(trades)))
    lines.append('| model, shuffled-label control ' + fmt(stats(policies(control)['model'])))
    lines += ['', '## Model by fold', '', '| fold | threshold | val trades ' + HEAD.split('\n')[0][1:],
              '|---|---|---|---|---|---|---|---|---|---|']
    model_trades = pol['model']
    for fold, part in scored.groupby('fold'):
        thr = part['threshold'].iloc[0]
        s = stats(model_trades[model_trades['fold'] == fold])
        base = stats(pol['all candidates'][pol['all candidates']['fold'] == fold])
        lines.append(f"| {fold} | {'none' if math.isinf(thr) else f'{thr:.3f}'} | {part['val_trades'].iloc[0]} "
                     + fmt(s) + f" all: {base['total_r']:+.1f}R")
    for key, title in (('symbol', 'symbol'), ('side', 'side'), ('year', 'year')):
        lines += ['', f'## Model by {title}', '', HEAD]
        frame = model_trades.assign(year=pd.to_datetime(model_trades['bar_time'], unit='s').dt.year)
        for value, part in frame.groupby(key):
            lines.append(f'| {value} ' + fmt(stats(part)))
    if importance is not None:
        lines += ['', '## Feature importance (final model, gain)', '', '| feature | share |', '|---|---|']
        total = importance.sum() or 1
        for name, value in importance.head(20).items():
            lines.append(f'| {name} | {value / total:.1%} |')
    if final_meta:
        lines += ['', '## Saved model', '', f"`{final_meta['model_file']}`: trained on {final_meta['trained_rows']} "
                  f"filled trades {final_meta['trained_from']} .. {final_meta['trained_to']}, "
                  f"{final_meta['rounds']} trees, threshold "
                  f"{'none (no profitable cut on validation: do not trade)' if final_meta['threshold'] is None else round(final_meta['threshold'], 4)}."]
    lines += ['', 'Rules of thumb: trust only results that beat *both* baselines and the shuffled control, that hold '
              'in most folds and on more than one symbol, and that survive a forward test on a demo account.']
    return '\n'.join(lines) + '\n'


def train_final(df: pd.DataFrame, min_val: int, out: Path) -> tuple[dict, pd.Series]:
    filled = df[df['filled']]
    cut = filled['bar_time'].quantile(0.8)
    fit_part, val_part = filled[filled['bar_time'] < cut], filled[filled['bar_time'] >= cut]
    model = fit(fit_part, val_part)
    rounds = max(model.best_iteration or 0, 20)
    threshold, info = choose_threshold(predict(model, val_part), val_part['r'].to_numpy(), min_val)
    final = fit(filled, None, rounds=rounds)
    out.mkdir(parents=True, exist_ok=True)
    model_file = out / 'ict_lgbm.txt'
    final.save_model(str(model_file))
    meta = {
        'model_file': str(model_file.relative_to(ROOT)).replace('\\', '/'), 'features': list(FEATURES),
        'categorical': list(CATEGORICAL), 'threshold': None if math.isinf(threshold) else threshold,
        'validation': info, 'rounds': rounds, 'trained_rows': int(len(filled)),
        'trained_from': day(filled['bar_time'].min()), 'trained_to': day(filled['bar_time'].max()),
        'symbols': sorted(filled['symbol'].unique()), 'rr': 2.0, 'entry_expiry_minutes': 120,
        'max_hold_minutes': 360, 'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    (out / 'ict_lgbm.json').write_text(json.dumps(meta, indent=1))
    importance = pd.Series(final.feature_importance('gain'), index=final.feature_name()).sort_values(ascending=False)
    return meta, importance


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data', default=str(DATA))
    parser.add_argument('--symbols', help='comma list to restrict training and testing (default: all)')
    parser.add_argument('--test-start', default='2024-07-01')
    parser.add_argument('--fold-months', type=int, default=3)
    parser.add_argument('--min-val-trades', type=int, default=150)
    parser.add_argument('--out', default=str(MODELS))
    parser.add_argument('--reports', default=str(REPORTS))
    parser.add_argument('--no-final', action='store_true', help='skip fitting and saving the final model')
    args = parser.parse_args()

    df = load(Path(args.data))
    if args.symbols:
        df = df[df['symbol'].isin({s.strip().upper() for s in args.symbols.split(',')})]
    print(f'{len(df)} candidates, {int(df["filled"].sum())} filled, {df["symbol"].nunique()} symbols')
    scored = walk_forward(df, args.test_start, args.fold_months, args.min_val_trades)
    control = walk_forward(df, args.test_start, args.fold_months, args.min_val_trades, shuffle=11)
    meta, importance = (None, None) if args.no_final else train_final(df, args.min_val_trades, Path(args.out))
    text = report(df, scored, control, meta, importance, args)
    folder = Path(args.reports)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'walkforward.md'
    path.write_text(text)
    scored.to_csv(folder / 'walkforward_scored.csv.gz', index=False)
    print(text)
    print(f'report -> {path}')


if __name__ == '__main__':
    main()
