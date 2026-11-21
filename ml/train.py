#!/usr/bin/env python3
"""Plan v2 trainer: expected-profit model for ICT gold setups, walk-forward on development data, gates, final model.

    python -m ml.train                 # development walk-forward, gates, report, final development model
    python -m ml.train --no-final      # report only

Data (python -m ml.dataset; development rows only, ml/lockbox.py refuses anything from the lockbox period):
    ml/data/xauusd_ict_dev.parquet              Dukascopy prices and spread: training and all gates
    ml/data/xauusd_ict_exness_dev.parquet       broker prices with Dukascopy's spread: gate 5
    ml/data/xauusd_ict_halfspread_dev.parquet   the same setups graded with half the spread: a sensitivity line

Model (docs/ml-plan.md, Plan v2). For a filled trade there are three outcomes: target, stop, timeout.
    1. one LightGBM three-class model, five seeds averaged: P(target), P(stop), P(timeout)
    2. one LightGBM regression of net R on timeout trades (decreasing in spread/risk), five seeds averaged
    expected net R = P(target) x mean net R of target exits in the training window
                   + P(stop)   x mean net R of stop exits in the training window
                   + P(timeout) x the timeout model's prediction
Training trades are weighted 0.5 ^ (age in years / 4). Settings are version 1's, untuned.

Walk-forward, per test fold of --fold-months from --test-start:
    train on tradable filled trades from --train-from that finished a day before the fold; the last 20% of that
    window is validation: rounds by early stopping, then the cut on expected net R (best mean net R x sqrt(trades),
    at least --min-val-trades, mean above zero; otherwise the model takes no trades in the fold). Refit on the whole
    window, score every candidate of the fold, trade one open plan per side; unfilled limits score 0R and block
    their slot. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

Baselines on the same folds: every tradable candidate, the ict_engine-style subset, a spread/risk cut-off chosen on
the same validation slice, and the same model trained on shuffled outcomes. The five gates are computed in code;
the final model is promoted only if they pass, and only a promoted, passing model may be taken to the lockbox by
ml/final_test.py.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import lightgbm as lgb  # noqa: E402
from sklearn.metrics import roc_auc_score  # noqa: E402

from ml import lockbox  # noqa: E402
from ml.ict_features import CATEGORICAL, FEATURES, SESSIONS, V1_FEATURES  # noqa: E402

DATA = lockbox.dev_file('xauusd_ict')
EXNESS = lockbox.dev_file('xauusd_ict_exness')
HALF = lockbox.dev_file('xauusd_ict_halfspread')
MODELS = ROOT / 'ml' / 'models'
REPORTS = ROOT / 'ml' / 'reports'
EMBARGO = 86_400
SLIP_EXITS = ('sl', 'timeout')
SLIP_SPREADS = 0.5
SEEDS = (7, 11, 13, 17, 19)
HALF_LIFE_YEARS = 4.0
MIN_TIMEOUT_ROWS = 50
TARGET, STOP, TIMEOUT = 0, 1, 2

BASE = {'learning_rate': 0.03, 'num_leaves': 15, 'min_data_in_leaf': 150, 'feature_fraction': 0.8,
        'bagging_fraction': 0.8, 'bagging_freq': 1, 'lambda_l2': 5.0, 'max_depth': 5, 'verbose': -1,
        'num_threads': 8}
MONOTONE = [-1 if name == 'spread_risk' else 0 for name in FEATURES]
PARAMS_CLASS = {**BASE, 'objective': 'multiclass', 'num_class': 3}
PARAMS_TIMEOUT = {**BASE, 'objective': 'regression', 'monotone_constraints': MONOTONE}
PARAMS_CHECK = {**BASE, 'objective': 'huber', 'monotone_constraints': MONOTONE}

GATES = {
    'expectancy_r': 0.10, 'profit_factor': 1.2,          # 1
    'margin_r': 0.05, 'auc_margin': 0.02,                # 2: beat every baseline by this much per trade
    'positive_fold_share': 0.60, 'recent_years': 2,      # 3
    'max_drawdown_r': 15.0, 'trades_per_year': 100,      # 4
    'broker_expectancy_r': 0.0,                          # 5: broker prices, Dukascopy spread
}


# -- data ---------------------------------------------------------------------------------------------
def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Resolved, account-tradable candidates with the columns the trainer uses: filled, cls, r, r_net."""
    df = df[df['outcome'] != 'unresolved']
    if 'tradable' in df:
        df = df[df['tradable'].astype(bool)]
    df = df.copy()
    for col in CATEGORICAL:
        df[col] = df[col].astype(int)
    df['filled'] = df['outcome'] == 'closed'
    df['r'] = df['r'].fillna(0.0)
    slip = np.where(df['filled'] & df['exit'].isin(SLIP_EXITS), SLIP_SPREADS * df['spread_risk'], 0.0)
    df['r_net'] = df['r'] - slip
    df['cls'] = df['outcome_class'] if 'outcome_class' in df else np.nan
    if 'symbol' not in df:
        df['symbol'] = 'XAUUSD'
    return df.sort_values(['bar_time', 'side']).reset_index(drop=True)


def load(path: Path) -> pd.DataFrame:
    """A development dataset, prepared. Raises LockboxError if the file holds lockbox-period rows."""
    return prepare(lockbox.guard(pd.read_parquet(path), Path(path).name))


def filter_counts(path: Path) -> pd.DataFrame:
    """Per year: resolved candidates and how many the account filter removed."""
    df = lockbox.guard(pd.read_parquet(path), Path(path).name)
    df = df[df['outcome'] != 'unresolved']
    return pd.DataFrame({'candidates': df.groupby('year').size(),
                         'untradable': (~df['tradable'].astype(bool)).groupby(df['year']).sum()})


def epoch(day_text: str) -> int:
    return int(datetime.strptime(day_text, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())


def day(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d')


def folds(df: pd.DataFrame, start: str, months: int) -> list[tuple[int, int]]:
    last = int(df['bar_time'].max())
    edges = pd.date_range(start, datetime.fromtimestamp(last, timezone.utc).strftime('%Y-%m-%d'),
                          freq=f'{months}MS', tz='UTC')
    edges = [int(e.timestamp()) for e in edges] + [last + 1]
    return [(a, b) for a, b in zip(edges, edges[1:]) if b > a]


def split_window(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit on the first 80% of the window, validate on the last 20%; fit trades end a day before validation."""
    cut = train['bar_time'].quantile(0.8)
    return train[train['end_time'] < cut - EMBARGO], train[train['bar_time'] >= cut]


# -- model --------------------------------------------------------------------------------------------
def weights(df: pd.DataFrame) -> np.ndarray:
    """0.5 ^ (age in years / HALF_LIFE_YEARS), age measured back from the newest trade in the frame."""
    age = (df['bar_time'].max() - df['bar_time'].to_numpy()) / (365.25 * 86400)
    return 0.5 ** (age / HALF_LIFE_YEARS)


def outcomes(df: pd.DataFrame, shuffle: int | None) -> tuple[np.ndarray, np.ndarray]:
    """(class, net R) of filled trades; with `shuffle`, permuted together so features carry no information."""
    y, r = df['cls'].to_numpy().astype(int), df['r_net'].to_numpy().astype(float)
    if shuffle is not None:
        order = np.random.default_rng(shuffle).permutation(len(y))
        y, r = y[order], r[order]
    return y, r


def dataset(df: pd.DataFrame, y: np.ndarray, weight: np.ndarray | None = None, reference=None):
    return lgb.Dataset(df[list(FEATURES)], y, weight=weight, categorical_feature=list(CATEGORICAL),
                       reference=reference, free_raw_data=False)


def find_rounds(fit_part: pd.DataFrame, val_part: pd.DataFrame, shuffle: int | None = None) -> dict:
    """Boosting rounds for both models by early stopping on the validation slice (first seed only)."""
    y, r = outcomes(fit_part, shuffle)
    yv, rv = outcomes(val_part, None if shuffle is None else shuffle + 1)
    stop = [lgb.early_stopping(50, verbose=False)]
    w = weights(fit_part)
    train_set = dataset(fit_part, y, w)
    model = lgb.train({**PARAMS_CLASS, 'seed': SEEDS[0]}, train_set, 1000,
                      valid_sets=[dataset(val_part, yv, reference=train_set)], callbacks=stop)
    rounds = {'cls': max(model.best_iteration or 0, 20), 'timeout': 50}
    mine, theirs = y == TIMEOUT, yv == TIMEOUT
    if mine.sum() >= MIN_TIMEOUT_ROWS and theirs.sum() >= 30:
        train_set = dataset(fit_part[mine], r[mine], w[mine])
        model = lgb.train({**PARAMS_TIMEOUT, 'seed': SEEDS[0]}, train_set, 1000,
                          valid_sets=[dataset(val_part[theirs], rv[theirs], reference=train_set)], callbacks=stop)
        rounds['timeout'] = max(model.best_iteration or 0, 20)
    return rounds


def fit_bundle(train: pd.DataFrame, rounds: dict, shuffle: int | None = None, seeds=SEEDS) -> dict:
    """The models of plan v2 fitted on `train` (filled trades): class models and timeout models per seed, and the
    mean net R of each outcome in the window."""
    y, r = outcomes(train, shuffle)
    w = weights(train)
    mine = y == TIMEOUT
    bundle = {'cls': [], 'timeout': [], 'rounds': dict(rounds),
              'means': {name: float(r[y == k].mean()) if (y == k).any() else 0.0
                        for k, name in ((TARGET, 'target'), (STOP, 'stop'), (TIMEOUT, 'timeout'))}}
    for seed in seeds:
        bundle['cls'].append(lgb.train({**PARAMS_CLASS, 'seed': seed}, dataset(train, y, w), rounds['cls']))
        if mine.sum() >= MIN_TIMEOUT_ROWS:
            bundle['timeout'].append(lgb.train({**PARAMS_TIMEOUT, 'seed': seed},
                                               dataset(train[mine], r[mine], w[mine]), rounds['timeout']))
    return bundle


def score(bundle: dict, df: pd.DataFrame) -> pd.DataFrame:
    """p_target, p_stop, p_timeout, timeout_r and expected_r for every row of df (same index)."""
    if not len(df):
        return pd.DataFrame(columns=['p_target', 'p_stop', 'p_timeout', 'timeout_r', 'expected_r'], index=df.index,
                            dtype=float)
    x = df[list(FEATURES)]
    p = np.mean([m.predict(x) for m in bundle['cls']], axis=0)
    means = bundle['means']
    timeout_r = np.mean([m.predict(x) for m in bundle['timeout']], axis=0) if bundle['timeout'] else \
        np.full(len(df), means['timeout'])
    expected = p[:, TARGET] * means['target'] + p[:, STOP] * means['stop'] + p[:, TIMEOUT] * timeout_r
    return pd.DataFrame({'p_target': p[:, TARGET], 'p_stop': p[:, STOP], 'p_timeout': p[:, TIMEOUT],
                         'timeout_r': timeout_r, 'expected_r': expected}, index=df.index)


def choose_threshold(score_values: np.ndarray, r: np.ndarray, min_trades: int) -> tuple[float, dict]:
    """The cut on a score (higher = take) that maximised mean R x sqrt(n) on validation; +inf when no cut with
    at least min_trades trades made money."""
    best = (0.0, math.inf, {'n': 0, 'mean_r': 0.0, 'top_fraction': 0.0})
    if not len(score_values):
        return best[1], best[2]
    for q in np.arange(0.0, 0.96, 0.05):
        cut = float(np.quantile(score_values, q))
        sel = r[score_values >= cut]
        if len(sel) < min_trades:
            continue
        value = sel.mean() * math.sqrt(len(sel))
        if value > best[0]:
            best = (value, cut, {'n': int(len(sel)), 'mean_r': float(sel.mean()), 'top_fraction': float(1 - q)})
    return best[1], best[2]


def rank_check(fit_part: pd.DataFrame, val_part: pd.DataFrame, val_expected: np.ndarray, rounds: int) -> float:
    """Spearman correlation on validation between the expected-R score and a direct regression of net R.
    Reported only (plan v2, V2.2): under 0.5 means the two ways of estimating profit disagree."""
    _, r = outcomes(fit_part, None)
    model = lgb.train({**PARAMS_CHECK, 'seed': SEEDS[0]}, dataset(fit_part, r, weights(fit_part)), rounds)
    direct = model.predict(val_part[list(FEATURES)])
    return float(pd.Series(direct).corr(pd.Series(np.asarray(val_expected, dtype=float)), method='spearman'))


def fit_window(train: pd.DataFrame, min_val: int, shuffle: int | None = None, check: bool = False) -> dict:
    """Everything one training window yields: the bundle fitted on all of it, the cut chosen on its validation
    slice, the spread/risk cut-off for the baseline, and the validation slice with its scores."""
    fit_part, val_part = split_window(train)
    rounds = find_rounds(fit_part, val_part, shuffle)
    val = val_part.join(score(fit_bundle(fit_part, rounds, shuffle), val_part))
    threshold, info = choose_threshold(val['expected_r'].to_numpy(), val['r_net'].to_numpy(), min_val)
    spread_cut, _ = choose_threshold(-val['spread_risk'].to_numpy(), val['r_net'].to_numpy(), min_val)
    return {'bundle': fit_bundle(train, rounds, shuffle), 'threshold': threshold, 'validation': info,
            'spread_cut': -spread_cut, 'val': val, 'rounds': rounds, 'train_rows': len(train),
            'rank_check': rank_check(fit_part, val_part, val['expected_r'].to_numpy(), rounds['cls']) if check
            else math.nan}


# -- walk-forward ---------------------------------------------------------------------------------------
def walk_forward(df: pd.DataFrame, start: str, months: int, min_val: int, train_from: int,
                 shuffle: int | None = None, extra: pd.DataFrame | None = None,
                 log=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scored test candidates of all folds, and `extra` scored by the same fold models over the same periods."""
    filled = df[df['filled'] & (df['bar_time'] >= train_from)]
    scored, scored_extra = [], []
    for a, b in folds(df, start, months):
        train = filled[filled['end_time'] < a - EMBARGO]
        if len(train) < 2000:
            continue
        window = fit_window(train, min_val, shuffle, check=shuffle is None)
        for source, out in ((df, scored), (extra, scored_extra)):
            if source is None:
                continue
            test = source[(source['bar_time'] >= a) & (source['bar_time'] < b)]
            if not len(test):
                continue
            test = test.join(score(window['bundle'], test))
            test['threshold'] = window['threshold']
            test['spread_cut'] = window['spread_cut']
            test['fold'] = day(a)
            test['val_trades'] = window['validation']['n']
            test['train_rows'] = window['train_rows']
            test['rank_check'] = window['rank_check']
            out.append(test)
        if log:
            thr = window['threshold']
            log(f"  fold {day(a)}: {window['train_rows']:,} training trades, rounds {window['rounds']}, cut "
                + ('none' if math.isinf(thr) else f'{thr:+.3f}R'))
    return (pd.concat(scored) if scored else pd.DataFrame(),
            pd.concat(scored_extra) if scored_extra else pd.DataFrame())


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


def stats(trades: pd.DataFrame, col: str = 'r_net') -> dict:
    filled = trades[trades['filled'].astype(bool)] if len(trades) else trades
    if not len(filled):
        return {'signals': int(len(trades)), 'trades': 0, 'win_rate': None, 'expectancy_r': None, 'total_r': 0.0,
                'profit_factor': None, 'max_drawdown_r': 0.0}
    r = filled[col].to_numpy()
    equity = np.cumsum(filled.sort_values('end_time')[col].to_numpy())
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0.0], equity]))[1:] - equity))
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {'signals': int(len(trades)), 'trades': int(len(r)), 'win_rate': float((filled['r'] > 0).mean()),
            'expectancy_r': float(r.mean()), 'total_r': float(r.sum()),
            'profit_factor': float(gains / losses) if losses else None, 'max_drawdown_r': max(dd, 0.0)}


def policies(scored: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if not len(scored):
        return {}
    engine = (scored['in_killzone'] == 1) & (scored['pool_kind'] < 4)
    return {
        'all tradable candidates': take_non_overlapping(scored),
        'ict_engine-style (killzone, session/day pools)': take_non_overlapping(scored[engine]),
        'spread/risk cut-off': take_non_overlapping(scored[scored['spread_risk'] <= scored['spread_cut']]),
        'model': take_non_overlapping(scored[scored['expected_r'] >= scored['threshold']]),
    }


def auc(scored: pd.DataFrame) -> float:
    """P(target) against 'reached the target' on filled trades."""
    filled = scored[scored['filled']] if len(scored) else scored
    if len(filled) < 20 or (filled['cls'] == TARGET).nunique() < 2:
        return math.nan
    return float(roc_auc_score(filled['cls'] == TARGET, filled['p_target']))


def years_covered(scored: pd.DataFrame) -> float:
    return (scored['bar_time'].max() - scored['bar_time'].min()) / (365.25 * 86400) if len(scored) else 0.0


def half_spread(scored: pd.DataFrame, half: pd.DataFrame | None) -> dict | None:
    """What the model's chosen setups made when the same candidates are graded with half the spread."""
    if half is None or not len(scored):
        return None
    chosen = scored[scored['expected_r'] >= scored['threshold']][['symbol', 'side', 'bar_time']]
    cheap = chosen.merge(half[['side', 'bar_time', 'end_time', 'filled', 'r', 'r_net']], on=['side', 'bar_time'])
    return stats(take_non_overlapping(cheap.sort_values(['bar_time', 'side']).reset_index(drop=True)))


def gates(pol: dict, control_pol: dict, scored: pd.DataFrame, control: pd.DataFrame,
          broker_pol: dict | None) -> list[dict]:
    """Section 8 of the plan as amended by V2.6, one entry per gate: required, measured, passed."""
    model = pol['model'] if pol else scored
    m = stats(model) if len(model) else {'signals': 0, 'trades': 0, 'win_rate': None, 'expectancy_r': None,
                                         'total_r': 0.0, 'profit_factor': None, 'max_drawdown_r': 0.0}
    out = []
    exp, pf = m['expectancy_r'], m['profit_factor']
    out.append({'gate': 1, 'name': 'expectancy and profit factor after spread and slippage',
                'required': f"> {GATES['expectancy_r']:+.2f}R per trade and PF > {GATES['profit_factor']}",
                'measured': f"{exp:+.3f}R, PF {pf:.2f}" if exp is not None and pf is not None else 'no trades',
                'passed': bool(exp is not None and pf is not None and exp > GATES['expectancy_r']
                               and pf > GATES['profit_factor'])})
    others = {name: stats(p) for name, p in pol.items() if name != 'model'}
    if control_pol:
        others['shuffled-outcome control'] = stats(control_pol['model'])
    beaten = all(exp is not None and (o['expectancy_r'] is None or exp >= o['expectancy_r'] + GATES['margin_r'])
                 for o in others.values())
    a, ca = auc(scored), auc(control)
    best_other = max((o['expectancy_r'] for o in others.values() if o['expectancy_r'] is not None), default=None)
    out.append({'gate': 2, 'name': 'beats every baseline and the shuffled control',
                'required': f"+{GATES['margin_r']:.2f}R per trade over each, AUC {GATES['auc_margin']:+.2f} over control",
                'measured': (f"best other {best_other:+.3f}R vs model {exp:+.3f}R; AUC {a:.3f} vs control {ca:.3f}"
                             if exp is not None and best_other is not None
                             else f'no model trades; AUC {a:.3f} vs control {ca:.3f}'),
                'passed': bool(beaten and not math.isnan(a) and not math.isnan(ca) and a >= ca + GATES['auc_margin'])})
    traded = [stats(part)['total_r'] for _, part in model.groupby('fold') if part['filled'].any()] if len(model) else []
    share = (sum(x > 0 for x in traded) / len(traded)) if traded else 0.0
    recent_from = scored['bar_time'].max() - GATES['recent_years'] * 365.25 * 86400 if len(scored) else 0
    recent_total = stats(model[model['bar_time'] >= recent_from])['total_r'] if len(model) else 0.0
    all_folds = scored['fold'].nunique() if len(scored) else 0
    out.append({'gate': 3, 'name': 'consistent across folds and recent',
                'required': f">= {GATES['positive_fold_share']:.0%} of folds positive, last {GATES['recent_years']} "
                            'development years positive',
                'measured': f"{sum(x > 0 for x in traded)} of {len(traded)} traded folds positive ({all_folds} folds "
                            f"in all); last {GATES['recent_years']} years {recent_total:+.1f}R",
                'passed': bool(share >= GATES['positive_fold_share'] and recent_total > 0)})
    per_year = m['trades'] / years_covered(scored) if years_covered(scored) else 0.0
    out.append({'gate': 4, 'name': 'drawdown and enough trades',
                'required': f"max drawdown <= {GATES['max_drawdown_r']:g}R, >= {GATES['trades_per_year']} trades a year",
                'measured': f"max drawdown {m['max_drawdown_r']:.1f}R, {per_year:.0f} trades a year",
                'passed': bool(m['trades'] and m['max_drawdown_r'] <= GATES['max_drawdown_r']
                               and per_year >= GATES['trades_per_year'])})
    if broker_pol:
        e = stats(broker_pol['model'])
        out.append({'gate': 5, 'name': "holds on broker prices with Dukascopy's spread (same fold models)",
                    'required': f"expectancy > {GATES['broker_expectancy_r']:+.2f}R",
                    'measured': f"{e['trades']} trades, {e['expectancy_r']:+.3f}R" if e['trades'] else '0 trades',
                    'passed': bool(e['trades'] and e['expectancy_r'] > GATES['broker_expectancy_r'])})
    else:
        out.append({'gate': 5, 'name': "holds on broker prices with Dukascopy's spread", 'required': 'broker dataset',
                    'measured': 'missing', 'passed': False})
    return out


# -- final model --------------------------------------------------------------------------------------
def importance(bundle: dict) -> pd.Series:
    gain = np.sum([m.feature_importance('gain') for m in bundle['cls']], axis=0)
    return pd.Series(gain, index=list(FEATURES)).sort_values(ascending=False)


def train_final(df: pd.DataFrame, min_val: int, train_from: int) -> tuple[dict, dict]:
    """The development model: fitted on every tradable filled development trade from train_from."""
    filled = df[df['filled'] & (df['bar_time'] >= train_from)]
    window = fit_window(filled, min_val)
    threshold = window['threshold']
    meta = {
        'model': 'ict_v2', 'features': list(FEATURES), 'categorical': list(CATEGORICAL),
        'threshold': None if math.isinf(threshold) else threshold, 'validation': window['validation'],
        'rounds': window['rounds'], 'means': window['bundle']['means'], 'seeds': list(SEEDS),
        'trained_rows': int(len(filled)), 'trained_from': day(filled['bar_time'].min()),
        'trained_to': day(filled['end_time'].max()), 'symbols': sorted(filled['symbol'].unique()),
        'rr': round(float(((filled['target'] - filled['entry']).abs() / filled['risk']).median()), 3),
        'entry_expiry_minutes': 120, 'max_hold_minutes': 360, 'lock_start': lockbox.LOCK_START,
        'half_life_years': HALF_LIFE_YEARS, 'params': BASE,
        'importance': list(importance(window['bundle']).index),
        'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    return window['bundle'], meta


def save_model(bundle: dict, meta: dict, out: Path, symbol: str) -> dict:
    """Write <symbol>_ict_v2_<trained_to>.json (meta) and .models.json (the boosters), then promote: the pointer
    <symbol>_ict_v2.json moves to this version only if it passed the gates, or if the version it points to did not
    pass either. A failed retrain never replaces a passing model."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol.lower()}_ict_v2_{meta['trained_to'].replace('-', '')}"
    (out / f'{stem}.models.json').write_text(json.dumps({
        'cls': [m.model_to_string() for m in bundle['cls']],
        'timeout': [m.model_to_string() for m in bundle['timeout']]}))
    meta = {**meta, 'model_file': f'{stem}.models.json', 'version': stem}
    (out / f'{stem}.json').write_text(json.dumps(meta, indent=1, default=str))
    pointer = out / f'{symbol.lower()}_ict_v2.json'
    current = json.loads(pointer.read_text()) if pointer.exists() else None
    promote = bool(meta['gates_passed']) or not (current and current.get('gates_passed'))
    if promote:
        pointer.write_text(json.dumps(meta, indent=1, default=str))
    meta['promoted'] = promote
    meta['kept'] = None if promote else current.get('version')
    return meta


def load_model(symbol: str, folder: Path = MODELS) -> tuple[dict, dict]:
    """(bundle, meta) of the promoted v2 model. FileNotFoundError when none has been trained."""
    pointer = Path(folder) / f'{symbol.lower()}_ict_v2.json'
    if not pointer.exists():
        raise FileNotFoundError(f'no model: {pointer} (train one with python -m ml.train)')
    meta = json.loads(pointer.read_text())
    saved = json.loads((Path(folder) / meta['model_file']).read_text())
    bundle = {'cls': [lgb.Booster(model_str=s) for s in saved['cls']],
              'timeout': [lgb.Booster(model_str=s) for s in saved['timeout']], 'means': meta['means'],
              'rounds': meta['rounds']}
    return bundle, meta


# -- report -------------------------------------------------------------------------------------------
HEAD = '| | signals | filled | win | exp R | total R | PF | max DD R |\n|---|---|---|---|---|---|---|---|'


def fmt(s: dict) -> str:
    if not s['trades']:
        return f"| {s['signals']} | 0 | - | - | 0.0 | - | 0.0 |"
    pf = '-' if s['profit_factor'] is None else f"{s['profit_factor']:.2f}"
    return (f"| {s['signals']} | {s['trades']} | {s['win_rate']:.1%} | {s['expectancy_r']:+.3f} | "
            f"{s['total_r']:+.1f} | {pf} | {s['max_drawdown_r']:.1f} |")


def by_tenth(scored: pd.DataFrame) -> pd.DataFrame:
    """Filled test trades in tenths of predicted expected R: predicted against realised, and how each ends."""
    filled = scored[scored['filled']] if len(scored) else scored
    if len(filled) < 100:
        return pd.DataFrame()
    bins = pd.qcut(filled['expected_r'], 10, duplicates='drop')
    g = filled.groupby(bins, observed=True)
    return pd.DataFrame({'trades': g.size(), 'predicted': g['expected_r'].mean(), 'realised': g['r_net'].mean(),
                         'target': g['cls'].apply(lambda s: (s == TARGET).mean()),
                         'stop': g['cls'].apply(lambda s: (s == STOP).mean()),
                         'timeout': g['cls'].apply(lambda s: (s == TIMEOUT).mean())})


def report(df, scored, control, broker_scored, half_stats, counts, gate_rows, final_meta, gain, args) -> str:
    pol, cpol = policies(scored), policies(control)
    passed = all(g['passed'] for g in gate_rows)
    lines = [f'# XAUUSD ICT model v2: development walk-forward ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)', '',
             f"Development data only (`{Path(args.data).name}`, ends before {lockbox.LOCK_START}; the lockbox is "
             f"unread). {len(df):,} tradable resolved candidates ({int(df['filled'].sum()):,} filled), "
             f"{day(df['bar_time'].min())} .. {day(df['bar_time'].max())}. Training from {args.train_from}; test folds "
             f"of {args.fold_months} months from {args.test_start} ({scored['fold'].nunique() if len(scored) else 0} "
             'folds); one-day embargo; cut chosen on the last 20% of each training window. Net R = after spread '
             f'and {SLIP_SPREADS:g} x spread slippage on stop and time exits.', '',
             f"## Gates: **{'PASSED' if passed else 'FAILED'}**", '',
             '| # | Gate | Required | Measured | Pass |', '|---|---|---|---|---|']
    lines += [f"| {g['gate']} | {g['name']} | {g['required']} | {g['measured']} | {'yes' if g['passed'] else 'no'} |"
              for g in gate_rows]
    lines += ['', 'All gates passed: the configuration is frozen and `python -m ml.final_test` may run once.' if passed
              else 'The development gates failed, so by plan v2 the work stops here: the lockbox stays closed, there '
                   'is no forward test and no further v2 variant.']
    lines += ['', f"AUC of P(target) on filled test trades: **{auc(scored):.3f}** (shuffled-outcome control "
              f"{auc(control):.3f}; 0.5 = no skill).", '', '## Out-of-sample result, net R (all development folds)',
              '', HEAD]
    for name, trades in pol.items():
        lines.append(f'| {name} ' + fmt(stats(trades)))
    if cpol:
        lines.append('| model, shuffled-outcome control ' + fmt(stats(cpol['model'])))
    if half_stats is not None:
        lines += ['', "Sensitivity only (decides nothing): the model's chosen setups graded with half the spread:", '',
                  HEAD, '| model, spread halved ' + fmt(half_stats)]
    if len(broker_scored):
        lines += ['', f"## Same fold models on broker prices with Dukascopy's spread "
                  f"({day(broker_scored['bar_time'].min())} .. {day(broker_scored['bar_time'].max())}), net R", '', HEAD]
        for name, trades in policies(broker_scored).items():
            lines.append(f'| {name} ' + fmt(stats(trades)))
    tenth = by_tenth(scored)
    if len(tenth):
        lines += ['', '## Predicted against realised (filled test trades, tenths of expected R)', '',
                  '| Predicted R | Realised net R | Trades | Target | Stop | Timeout |', '|---|---|---|---|---|---|']
        lines += [f"| {r.predicted:+.3f} | {r.realised:+.3f} | {r.trades} | {r.target:.1%} | {r.stop:.1%} | "
                  f"{r.timeout:.1%} |" for r in tenth.itertuples()]
    checks = scored.groupby('fold')['rank_check'].first() if len(scored) else pd.Series(dtype=float)
    if len(checks):
        low = int((checks < 0.5).sum())
        lines += ['', 'Cross-check: rank correlation between the expected-R score and a direct regression of net R, '
                  f'on validation, averages {checks.mean():.2f} over {len(checks)} folds'
                  + (f' and is under 0.5 in {low} of them: the two estimates of profit disagree there.'
                     if low else '; never under 0.5.')]
    model_trades = pol['model'] if pol else scored
    lines += ['', '## Model by fold', '',
              '| fold | cut (expected R) | val trades | signals | filled | win | exp R | total R | PF | max DD R | '
              'all tradable R |', '|---|---|---|---|---|---|---|---|---|---|---|']
    if len(scored):
        everything = pol['all tradable candidates']
        for fold, part in scored.groupby('fold'):
            thr = part['threshold'].iloc[0]
            base = stats(everything[everything['fold'] == fold])
            lines.append(f"| {fold} | {'none' if math.isinf(thr) else f'{thr:+.3f}'} | {part['val_trades'].iloc[0]} "
                         + fmt(stats(model_trades[model_trades['fold'] == fold])) + f" {base['total_r']:+.1f} |")
    if len(model_trades):
        frame = model_trades.assign(
            year=pd.to_datetime(model_trades['bar_time'], unit='s').dt.year,
            session=[SESSIONS[int(s)] for s in model_trades['session_now']])
        for key in ('year', 'session', 'side'):
            lines += ['', f'## Model by {key}', '', HEAD]
            for value, part in frame.groupby(key):
                lines.append(f'| {value} ' + fmt(stats(part)))
    if counts is not None and len(counts):
        lines += ['', '## Account filter (stop at most $10 at the minimum position)', '',
                  '| Year | Resolved candidates | Removed as untradable |', '|---|---|---|']
        lines += [f"| {y} | {int(r['candidates'])} | {int(r['untradable'])} |" for y, r in counts.iterrows()
                  if y >= int(args.train_from[:4])]
    if gain is not None:
        total = gain.sum() or 1
        new = set(FEATURES[V1_FEATURES:])
        lines += ['', '## Feature importance (development model, gain; * = new in v2)', '', '| feature | share |',
                  '|---|---|']
        lines += [f"| {name}{' *' if name in new else ''} | {value / total:.1%} |"
                  for name, value in gain.head(15).items()]
    if final_meta:
        thr = final_meta['threshold']
        lines += ['', '## Saved development model', '',
                  f"`ml/models/{final_meta['model_file']}`: {final_meta['trained_rows']:,} filled trades "
                  f"{final_meta['trained_from']} .. {final_meta['trained_to']}, rounds {final_meta['rounds']}, cut "
                  + ('none (no profitable cut on validation: do not trade)' if thr is None else f'{thr:+.3f}R')
                  + f", gates {'passed' if final_meta['gates_passed'] else 'FAILED'}."]
    return '\n'.join(lines) + '\n'


def expected(pol: dict, scored: pd.DataFrame) -> dict:
    """What the walk-forward says the model policy should do live, for ml/monitor.py to compare against."""
    model = pol['model'] if pol else scored.iloc[:0]
    filled = model[model['filled']] if len(model) else model
    s = stats(model) if len(model) else {'win_rate': None, 'expectancy_r': None, 'profit_factor': None, 'trades': 0}
    years = years_covered(scored)
    return {'win_rate': s['win_rate'], 'expectancy_r': s['expectancy_r'], 'profit_factor': s['profit_factor'],
            'trades_per_week': s['trades'] / (years * 52.18) if years else None,
            'r_std': float(filled['r_net'].std()) if len(filled) > 1 else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data', default=str(DATA))
    parser.add_argument('--exness', default=str(EXNESS), help='broker-price development dataset for gate 5')
    parser.add_argument('--half', default=str(HALF), help='half-spread development dataset (sensitivity line)')
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--train-from', default='2011-01-01')
    parser.add_argument('--test-start', default='2014-01-01')
    parser.add_argument('--fold-months', type=int, default=6)
    parser.add_argument('--min-val-trades', type=int, default=150)
    parser.add_argument('--out', default=str(MODELS))
    parser.add_argument('--reports', default=str(REPORTS))
    parser.add_argument('--no-final', action='store_true', help='skip fitting and saving the development model')
    args = parser.parse_args()

    df = load(Path(args.data))
    train_from = epoch(args.train_from)
    broker = load(Path(args.exness)) if Path(args.exness).exists() else None
    half = load(Path(args.half)) if Path(args.half).exists() else None
    print(f"{len(df):,} tradable candidates, {int(df['filled'].sum()):,} filled; training from {args.train_from}",
          flush=True)
    scored, broker_scored = walk_forward(df, args.test_start, args.fold_months, args.min_val_trades, train_from,
                                         extra=broker, log=lambda text: print(text, flush=True))
    print('shuffled-outcome control...', flush=True)
    control, _ = walk_forward(df, args.test_start, args.fold_months, args.min_val_trades, train_from, shuffle=11)
    pol = policies(scored)
    broker_pol = policies(broker_scored) if len(broker_scored) else None
    gate_rows = gates(pol, policies(control), scored, control, broker_pol)
    passed = all(g['passed'] for g in gate_rows)

    final_meta, gain = None, None
    if not args.no_final:
        bundle, meta = train_final(df, args.min_val_trades, train_from)
        gain = importance(bundle)
        meta.update({'gates': gate_rows, 'gates_passed': passed, 'expected': expected(pol, scored),
                     'walk_forward': {'train_from': args.train_from, 'test_start': args.test_start,
                                      'fold_months': args.fold_months, 'auc': auc(scored),
                                      'control_auc': auc(control)}})
        final_meta = save_model(bundle, meta, Path(args.out), args.symbol)
    text = report(df, scored, control, broker_scored, half_spread(scored, half), filter_counts(Path(args.data)),
                  gate_rows, final_meta, gain, args)
    folder = Path(args.reports)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f'{args.symbol.lower()}_v2_walkforward.md'
    path.write_text(text, encoding='utf-8')
    scored.to_parquet(ROOT / 'ml' / 'data' / f'{args.symbol.lower()}_v2_scored_dev.parquet', index=False)
    (ROOT / 'ml' / 'data' / f'{args.symbol.lower()}_v2_walkforward.json').write_text(json.dumps(
        {'gates_passed': passed, 'gates': gate_rows, 'auc': auc(scored), 'control_auc': auc(control),
         'policies': {name: stats(p) for name, p in pol.items()}}, indent=1, default=str))
    print(text)
    print(f'report -> {path}')


if __name__ == '__main__':
    main()
