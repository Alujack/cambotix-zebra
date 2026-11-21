#!/usr/bin/env python3
"""Train the ICT setup model with an honest walk-forward, check the go / no-go gates, save the final model.

    python -m ml.train                         # gold: walk-forward report, gates, final model
    python -m ml.train --no-final              # report only

Data: ml/data/xauusd_ict.parquet (python -m ml.dataset), plus ml/data/xauusd_ict_exness.parquet for gate 5 when it
exists (python -m ml.dataset --folder .local/history --from 2023-11-24 --coarse-until 0
--out ml/data/xauusd_ict_exness.parquet --allow-unchecked).

Walk-forward (docs/ml-plan.md section 6), per test fold of --fold-months from --test-start:
  1. Train on filled trades from --train-from that *finished* a day (the embargo) before the fold starts.
  2. The last 20% of that window is validation: LightGBM early-stops on it and the probability threshold is chosen
     on it (best mean net R x sqrt(trades), at least --min-val-trades). No profitable threshold there means the
     model takes no trades in the fold.
  3. Refit on the whole window and score every candidate in the fold, filled or not. Unfilled limits score 0R and
     block their slot until they expire; one open plan per side (MAX_OPEN_SAME_DIRECTION=1) for every policy.
  4. Net R: stop-outs and time exits lose a further 0.5 x spread (as a share of risk) for slippage. Limit fills and
     targets fill at their price. Gates use net R.

Baselines, all on the same folds: (a) every candidate, (b) the ict_engine-style subset (killzone sweep of a
session or day pool), (c) the same model trained on shuffled labels, (d) a spread/risk cut-off chosen on the same
validation slice. Also reported: 2008-2010 scored by the final model as a stress test (never trained on; those
years carry a p99 spread floor), and every fold's model applied to the Exness candidates of the same period.

The gates (section 8) are computed, not judged: the model JSON records them and ml/predict.py refuses a model that
did not pass, unless told otherwise for research.
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

from ml.ict_features import CATEGORICAL, FEATURES, SESSIONS  # noqa: E402

DATA = ROOT / 'ml' / 'data' / 'xauusd_ict.parquet'
EXNESS = ROOT / 'ml' / 'data' / 'xauusd_ict_exness.parquet'
MODELS = ROOT / 'ml' / 'models'
REPORTS = ROOT / 'ml' / 'reports'
EMBARGO = 86_400
SLIP_EXITS = ('sl', 'timeout')
SLIP_SPREADS = 0.5

PARAMS = {
    'objective': 'binary', 'learning_rate': 0.03, 'num_leaves': 15, 'min_data_in_leaf': 150,
    'feature_fraction': 0.8, 'bagging_fraction': 0.8, 'bagging_freq': 1, 'lambda_l2': 5.0,
    'max_depth': 5, 'verbose': -1, 'seed': 7, 'num_threads': 8,
}

GATES = {
    'expectancy_r': 0.10, 'profit_factor': 1.2,          # 1
    'margin_r': 0.05, 'auc_margin': 0.02,                # 2: beat every baseline by this much per trade
    'positive_fold_share': 0.60, 'recent_years': 2,      # 3
    'max_drawdown_r': 15.0, 'trades_per_year': 100,      # 4
}


# -- data ---------------------------------------------------------------------------------------------
def load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    df = df[df['outcome'] != 'unresolved'].copy()
    for col in CATEGORICAL:
        df[col] = df[col].astype(int)
    df['filled'] = df['outcome'] == 'closed'
    df['r'] = df['r'].fillna(0.0)
    slip = np.where(df['filled'] & df['exit'].isin(SLIP_EXITS), SLIP_SPREADS * df['spread_risk'], 0.0)
    df['r_net'] = df['r'] - slip
    if 'symbol' not in df:
        df['symbol'] = 'XAUUSD'
    return df.sort_values(['bar_time', 'side']).reset_index(drop=True)


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
    if not len(df):
        return np.zeros(0)
    return model.predict(df[list(FEATURES)], num_iteration=model.best_iteration or None)


def choose_threshold(score: np.ndarray, r: np.ndarray, min_trades: int) -> tuple[float, dict]:
    """The cut on `score` (higher = take) that maximised mean R x sqrt(n) on validation; +inf when no cut with
    at least min_trades trades made money."""
    best = (0.0, math.inf, {'n': 0, 'mean_r': 0.0, 'top_fraction': 0.0})
    if not len(score):
        return best[1], best[2]
    for q in np.arange(0.0, 0.96, 0.05):
        cut = float(np.quantile(score, q))
        sel = r[score >= cut]
        if len(sel) < min_trades:
            continue
        value = sel.mean() * math.sqrt(len(sel))
        if value > best[0]:
            best = (value, cut, {'n': int(len(sel)), 'mean_r': float(sel.mean()), 'top_fraction': float(1 - q)})
    return best[1], best[2]


def split_window(train: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit on the first 80% of the window, validate on the last 20%; fit trades end a day before validation."""
    cut = train['bar_time'].quantile(0.8)
    return train[train['end_time'] < cut - EMBARGO], train[train['bar_time'] >= cut]


# -- walk-forward ---------------------------------------------------------------------------------------
def walk_forward(df: pd.DataFrame, start: str, months: int, min_val: int, train_from: int,
                 shuffle: int | None = None, extra: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Scored test candidates of all folds (prob, threshold, spread_cut, fold, ...), and `extra` scored by the
    same fold models over the same periods."""
    filled = df[df['filled'] & (df['bar_time'] >= train_from)]
    scored, scored_extra = [], []
    for a, b in folds(df, start, months):
        train = filled[filled['end_time'] < a - EMBARGO]
        if len(train) < 2000:
            continue
        fit_part, val_part = split_window(train)
        model = fit(fit_part, val_part, shuffle=shuffle)
        rounds = max(model.best_iteration or 0, 20)
        threshold, info = choose_threshold(predict(model, val_part), val_part['r_net'].to_numpy(), min_val)
        spread_cut, _ = choose_threshold(-val_part['spread_risk'].to_numpy(), val_part['r_net'].to_numpy(), min_val)
        final = fit(train, None, rounds=rounds, shuffle=shuffle)
        for source, out in ((df, scored), (extra, scored_extra)):
            if source is None:
                continue
            test = source[(source['bar_time'] >= a) & (source['bar_time'] < b)].copy()
            if not len(test):
                continue
            test['prob'] = final.predict(test[list(FEATURES)])
            test['threshold'] = threshold
            test['spread_cut'] = -spread_cut
            test['fold'] = day(a)
            test['val_trades'] = info['n']
            test['rounds'] = rounds
            test['train_rows'] = len(train)
            out.append(test)
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
    filled = trades[trades['filled']] if len(trades) else trades
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
        'all candidates': take_non_overlapping(scored),
        'ict_engine-style (killzone, session/day pools)': take_non_overlapping(scored[engine]),
        'spread/risk cut-off': take_non_overlapping(scored[scored['spread_risk'] <= scored['spread_cut']]),
        'model': take_non_overlapping(scored[scored['prob'] >= scored['threshold']]),
    }


def auc(scored: pd.DataFrame) -> float:
    filled = scored[scored['filled']] if len(scored) else scored
    if len(filled) < 20 or filled['win'].nunique() < 2:
        return math.nan
    return float(roc_auc_score(filled['win'], filled['prob']))


def years_covered(scored: pd.DataFrame) -> float:
    return (scored['bar_time'].max() - scored['bar_time'].min()) / (365.25 * 86400) if len(scored) else 0.0


def gates(pol: dict, control_pol: dict, scored: pd.DataFrame, control: pd.DataFrame,
          exness_pol: dict | None) -> list[dict]:
    """Section 8 of the plan, one entry per gate: what was required, what was measured, passed or not."""
    model = pol['model']
    m = stats(model)
    out = []
    exp, pf = m['expectancy_r'], m['profit_factor']
    out.append({'gate': 1, 'name': 'expectancy and profit factor after spread and slippage',
                'required': f"> {GATES['expectancy_r']:+.2f}R per trade and PF > {GATES['profit_factor']}",
                'measured': f"{exp:+.3f}R, PF {pf:.2f}" if exp is not None and pf is not None else 'no trades',
                'passed': bool(exp is not None and pf is not None and exp > GATES['expectancy_r']
                               and pf > GATES['profit_factor'])})
    others = {name: stats(p) for name, p in pol.items() if name != 'model'}
    others['shuffled-label control'] = stats(control_pol.get('model', control.iloc[:0]))
    beaten = all(exp is not None and (o['expectancy_r'] is None or exp >= o['expectancy_r'] + GATES['margin_r'])
                 for o in others.values())
    a, ca = auc(scored), auc(control)
    worst = max((o['expectancy_r'] for o in others.values() if o['expectancy_r'] is not None), default=None)
    out.append({'gate': 2, 'name': 'beats every baseline and the shuffled control',
                'required': f"+{GATES['margin_r']:.2f}R per trade over each, AUC {GATES['auc_margin']:+.2f} over control",
                'measured': (f"best other {worst:+.3f}R vs model {exp:+.3f}R; AUC {a:.3f} vs control {ca:.3f}"
                             if exp is not None and worst is not None else 'no trades'),
                'passed': bool(beaten and not math.isnan(a) and not math.isnan(ca) and a >= ca + GATES['auc_margin'])})
    by_fold = [stats(part)['total_r'] for _, part in model.groupby('fold')] if len(model) else []
    folds_with_trades = [x for x, (_, part) in zip(by_fold, model.groupby('fold')) if part['filled'].any()] \
        if len(model) else []
    share = (sum(x > 0 for x in folds_with_trades) / len(folds_with_trades)) if folds_with_trades else 0.0
    recent_from = scored['bar_time'].max() - GATES['recent_years'] * 365.25 * 86400 if len(scored) else 0
    recent = stats(model[model['bar_time'] >= recent_from]) if len(model) else stats(model)
    all_folds = scored['fold'].nunique() if len(scored) else 0
    out.append({'gate': 3, 'name': 'consistent across folds and recent',
                'required': f">= {GATES['positive_fold_share']:.0%} of folds positive, last {GATES['recent_years']} years positive",
                'measured': f"{sum(x > 0 for x in folds_with_trades)} of {len(folds_with_trades)} traded folds positive "
                            f"({all_folds} folds in all); last {GATES['recent_years']} years {recent['total_r']:+.1f}R",
                'passed': bool(share >= GATES['positive_fold_share'] and recent['total_r'] > 0)})
    per_year = m['trades'] / years_covered(scored) if years_covered(scored) else 0.0
    out.append({'gate': 4, 'name': 'drawdown and enough trades',
                'required': f"max drawdown <= {GATES['max_drawdown_r']:g}R, >= {GATES['trades_per_year']} trades a year",
                'measured': f"max drawdown {m['max_drawdown_r']:.1f}R, {per_year:.0f} trades a year",
                'passed': bool(m['trades'] and m['max_drawdown_r'] <= GATES['max_drawdown_r']
                               and per_year >= GATES['trades_per_year'])})
    if exness_pol:
        e = stats(exness_pol['model'])
        out.append({'gate': 5, 'name': 'holds on Exness prices and spreads (same fold models)',
                    'required': f"> {GATES['expectancy_r']:+.2f}R per trade and PF > {GATES['profit_factor']}",
                    'measured': (f"{e['trades']} trades, {e['expectancy_r']:+.3f}R, PF "
                                 f"{e['profit_factor']:.2f}" if e['trades'] and e['profit_factor'] else
                                 f"{e['trades']} trades"),
                    'passed': bool(e['trades'] and e['profit_factor'] and e['expectancy_r'] > GATES['expectancy_r']
                                   and e['profit_factor'] > GATES['profit_factor'])})
    else:
        out.append({'gate': 5, 'name': 'holds on Exness prices and spreads', 'required': 'Exness dataset',
                    'measured': f'missing {EXNESS.relative_to(ROOT)}', 'passed': False})
    return out


# -- final model --------------------------------------------------------------------------------------
def train_final(df: pd.DataFrame, min_val: int, train_from: int) -> tuple[object, dict, pd.Series]:
    filled = df[df['filled'] & (df['bar_time'] >= train_from)]
    fit_part, val_part = split_window(filled)
    model = fit(fit_part, val_part)
    rounds = max(model.best_iteration or 0, 20)
    threshold, info = choose_threshold(predict(model, val_part), val_part['r_net'].to_numpy(), min_val)
    final = fit(filled, None, rounds=rounds)
    meta = {
        'features': list(FEATURES), 'categorical': list(CATEGORICAL),
        'threshold': None if math.isinf(threshold) else threshold, 'validation': info, 'rounds': rounds,
        'trained_rows': int(len(filled)), 'trained_from': day(filled['bar_time'].min()),
        'trained_to': day(filled['end_time'].max()), 'symbols': sorted(filled['symbol'].unique()),
        'rr': round(float(((filled['target'] - filled['entry']).abs() / filled['risk']).median()), 3),
        'entry_expiry_minutes': 120, 'max_hold_minutes': 360,
        'params': PARAMS,
        'created': datetime.now(timezone.utc).isoformat(timespec='seconds'),
    }
    importance = pd.Series(final.feature_importance('gain'), index=final.feature_name()).sort_values(ascending=False)
    meta['importance'] = list(importance.index)        # ml/monitor.py judges drift on the top features
    return final, meta, importance


def save_model(final, meta: dict, out: Path, symbol: str) -> dict:
    """Write <symbol>_ict_lgbm_<trained_to>.txt/.json (versioned by training end), then promote it: the pointer
    <symbol>_ict_lgbm.json moves to this version only if it passed the gates, or if the version it points to did
    not pass either (section 10: a new model replaces the old one only if it passes the same gates)."""
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{symbol.lower()}_ict_lgbm_{meta['trained_to'].replace('-', '')}"
    final.save_model(str(out / f'{stem}.txt'))
    meta = {**meta, 'model_file': f'{stem}.txt', 'version': stem}
    (out / f'{stem}.json').write_text(json.dumps(meta, indent=1, default=str))
    pointer = out / f'{symbol.lower()}_ict_lgbm.json'
    current = json.loads(pointer.read_text()) if pointer.exists() else None
    promote = meta['gates_passed'] or not (current and current.get('gates_passed'))
    if promote:
        pointer.write_text(json.dumps(meta, indent=1, default=str))
    meta['promoted'] = promote
    meta['kept'] = None if promote else current.get('version')
    return meta


# -- report -------------------------------------------------------------------------------------------
HEAD = '| | signals | filled | win | exp R | total R | PF | max DD R |\n|---|---|---|---|---|---|---|---|'


def fmt(s: dict) -> str:
    if not s['trades']:
        return f"| {s['signals']} | 0 | - | - | 0.0 | - | 0.0 |"
    pf = '-' if s['profit_factor'] is None else f"{s['profit_factor']:.2f}"
    return (f"| {s['signals']} | {s['trades']} | {s['win_rate']:.1%} | {s['expectancy_r']:+.3f} | "
            f"{s['total_r']:+.1f} | {pf} | {s['max_drawdown_r']:.1f} |")


def calibration(scored: pd.DataFrame) -> pd.DataFrame:
    filled = scored[scored['filled']]
    if len(filled) < 100:
        return pd.DataFrame()
    bins = pd.qcut(filled['prob'], 10, duplicates='drop')
    return filled.groupby(bins, observed=True).agg(trades=('win', 'size'), predicted=('prob', 'mean'),
                                                   actual=('win', 'mean'), exp_r=('r_net', 'mean'))


def report(df, scored, control, exness_scored, stress, gate_rows, final_meta, importance, args) -> str:
    pol, cpol = policies(scored), policies(control)
    lines = [f'# XAUUSD ICT model walk-forward ({datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC)', '',
             f"Dataset `{Path(args.data).name}`{' (session/day pools only)' if args.pools == 'session' else ''}: {len(df):,} resolved candidates ({int(df['filled'].sum()):,} filled), "
             f"{day(df['bar_time'].min())} .. {day(df['bar_time'].max())}. Training from {args.train_from}; test folds of "
             f"{args.fold_months} months from {args.test_start} ({scored['fold'].nunique() if len(scored) else 0} folds); "
             'one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread '
             f'(in the grade) and {SLIP_SPREADS:g} x spread slippage on stop and time exits.', '']
    passed = all(g['passed'] for g in gate_rows)
    lines += [f"## Gates: **{'PASSED' if passed else 'FAILED'}**", '',
              '| # | Gate | Required | Measured | Pass |', '|---|---|---|---|---|']
    lines += [f"| {g['gate']} | {g['name']} | {g['required']} | {g['measured']} | {'yes' if g['passed'] else 'no'} |"
              for g in gate_rows]
    if not passed:
        lines += ['', 'The model does not go to a forward test. ml/predict.py refuses this model unless run with '
                  '--allow-failed-gates (research only).']
    lines += ['', f"Out-of-sample AUC on filled trades: **{auc(scored):.3f}** (shuffled-label control "
              f"{auc(control):.3f}; 0.5 = no skill).", '', '## Out-of-sample result, net R (all folds)', '', HEAD]
    for name, trades in pol.items():
        lines.append(f'| {name} ' + fmt(stats(trades)))
    if cpol:
        lines.append('| model, shuffled-label control ' + fmt(stats(cpol['model'])))
    lines += ['', 'Gross R (spread only, no slippage):', '', HEAD]
    for name, trades in pol.items():
        lines.append(f'| {name} ' + fmt(stats(trades, 'r')))
    if len(exness_scored):
        epol = policies(exness_scored)
        lines += ['', f"## Same fold models on Exness prices ({day(exness_scored['bar_time'].min())} .. "
                  f"{day(exness_scored['bar_time'].max())}), net R", '', HEAD]
        for name, trades in epol.items():
            lines.append(f'| {name} ' + fmt(stats(trades)))
    if stress is not None and len(stress):
        lines += ['', '## Stress test: final model on 2008-2010 (never trained on; p99 spread floor), net R', '', HEAD]
        for name, trades in policies(stress).items():
            if name != 'spread/risk cut-off':
                lines.append(f'| {name} ' + fmt(stats(trades)))
    model_trades = pol.get('model', scored.iloc[:0])
    lines += ['', '## Model by fold', '',
              '| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |',
              '|---|---|---|---|---|---|---|---|---|---|---|']
    for fold, part in scored.groupby('fold'):
        thr = part['threshold'].iloc[0]
        base = stats(pol['all candidates'][pol['all candidates']['fold'] == fold])
        lines.append(f"| {fold} | {'none' if math.isinf(thr) else f'{thr:.3f}'} | {part['val_trades'].iloc[0]} "
                     + fmt(stats(model_trades[model_trades['fold'] == fold])) + f" {base['total_r']:+.1f} |")
    frame = model_trades.assign(
        year=pd.to_datetime(model_trades['bar_time'], unit='s').dt.year,
        session=[SESSIONS[int(s)] for s in model_trades['session_now']],
        era=np.where(model_trades['bar_time'] < epoch('2020-01-01'), 'before 2020', '2020 on'))
    for key in ('year', 'session', 'side', 'era'):
        lines += ['', f'## Model by {key}', '', HEAD]
        for value, part in frame.groupby(key):
            lines.append(f'| {value} ' + fmt(stats(part)))
    cal = calibration(scored)
    if len(cal):
        lines += ['', '## Calibration (filled test trades, probability deciles)', '',
                  '| predicted | actual win | trades | exp R |', '|---|---|---|---|']
        lines += [f"| {row.predicted:.3f} | {row.actual:.3f} | {row.trades} | {row.exp_r:+.3f} |"
                  for row in cal.itertuples()]
    if importance is not None:
        lines += ['', '## Feature importance (final model, gain)', '', '| feature | share |', '|---|---|']
        total = importance.sum() or 1
        lines += [f'| {name} | {value / total:.1%} |' for name, value in importance.head(15).items()]
    if final_meta:
        thr = final_meta['threshold']
        lines += ['', '## Saved model', '',
                  f"`ml/models/{final_meta['model_file']}`: {final_meta['trained_rows']:,} filled trades "
                  f"{final_meta['trained_from']} .. {final_meta['trained_to']}, {final_meta['rounds']} trees, threshold "
                  f"{'none (no profitable cut on validation: do not trade)' if thr is None else round(thr, 4)}, "
                  f"gates {'passed' if final_meta['gates_passed'] else 'FAILED'}."]
    return '\n'.join(lines) + '\n'


def expected(pol: dict, scored: pd.DataFrame) -> dict:
    """What the walk-forward says the model policy should do live, for ml/monitor.py to compare against."""
    s = stats(pol['model']) if pol else stats(scored.iloc[:0])
    filled = pol['model'][pol['model']['filled']] if pol else scored.iloc[:0]
    years = years_covered(scored)
    return {'win_rate': s['win_rate'], 'expectancy_r': s['expectancy_r'], 'profit_factor': s['profit_factor'],
            'trades_per_week': s['trades'] / (years * 52.18) if years else None,
            'r_std': float(filled['r_net'].std()) if len(filled) > 1 else None,
            'mean_probability': float(filled['prob'].mean()) if len(filled) else None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data', default=str(DATA))
    parser.add_argument('--exness', default=str(EXNESS), help='Exness dataset for gate 5 (skipped if missing)')
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--train-from', default='2011-01-01')
    parser.add_argument('--test-start', default='2014-01-01')
    parser.add_argument('--fold-months', type=int, default=6)
    parser.add_argument('--min-val-trades', type=int, default=150)
    parser.add_argument('--out', default=str(MODELS))
    parser.add_argument('--reports', default=str(REPORTS))
    parser.add_argument('--pools', choices=('all', 'session'), default='all',
                        help="'session' keeps only sweeps of day/session pools (no M5 swing pools)")
    parser.add_argument('--tag', default='', help='suffix for the report and scored file (variants)')
    parser.add_argument('--no-final', action='store_true', help='skip fitting and saving the final model')
    args = parser.parse_args()

    df = load(Path(args.data))
    train_from = epoch(args.train_from)
    exness = load(Path(args.exness)) if Path(args.exness).exists() else None
    if args.pools == 'session':
        df = df[df['pool_kind'] < 4]
        exness = exness[exness['pool_kind'] < 4] if exness is not None else None
    print(f"{len(df):,} candidates, {int(df['filled'].sum()):,} filled; training from {args.train_from}", flush=True)
    scored, exness_scored = walk_forward(df, args.test_start, args.fold_months, args.min_val_trades, train_from,
                                         extra=exness)
    control, _ = walk_forward(df, args.test_start, args.fold_months, args.min_val_trades, train_from, shuffle=11)
    pol = policies(scored)
    epol = policies(exness_scored) if len(exness_scored) else None
    gate_rows = gates(pol, policies(control), scored, control, epol)
    passed = all(g['passed'] for g in gate_rows)

    final_meta, importance, stress = None, None, None
    if not args.no_final:
        final, meta, importance = train_final(df, args.min_val_trades, train_from)
        stress = df[df['bar_time'] < train_from].copy()
        if len(stress):
            stress['prob'] = final.predict(stress[list(FEATURES)])
            stress['threshold'] = meta['threshold'] if meta['threshold'] is not None else math.inf
            stress['spread_cut'] = math.inf
            stress['fold'] = 'stress'
        meta.update({'gates': gate_rows, 'gates_passed': passed, 'expected': expected(pol, scored),
                     'walk_forward': {'train_from': args.train_from, 'test_start': args.test_start,
                                      'fold_months': args.fold_months, 'auc': auc(scored),
                                      'control_auc': auc(control)}})
        final_meta = save_model(final, meta, Path(args.out), args.symbol)
    text = report(df, scored, control, exness_scored, stress, gate_rows, final_meta, importance, args)
    folder = Path(args.reports)
    folder.mkdir(parents=True, exist_ok=True)
    suffix = f'_{args.tag}' if args.tag else ''
    path = folder / f'{args.symbol.lower()}_walkforward{suffix}.md'
    path.write_text(text, encoding='utf-8')
    scored.to_parquet(ROOT / 'ml' / 'data' / f'{args.symbol.lower()}_walkforward{suffix}_scored.parquet', index=False)
    summary = {'tag': args.tag or 'baseline', 'data': Path(args.data).name, 'pools': args.pools,
               'gates_passed': passed, 'gates': gate_rows, 'auc': auc(scored), 'control_auc': auc(control),
               'policies': {name: stats(p) for name, p in pol.items()}}
    (ROOT / 'ml' / 'data' / f'{args.symbol.lower()}_walkforward{suffix}.json').write_text(
        json.dumps(summary, indent=1, default=str))
    print(text)
    print(f'report -> {path}')


if __name__ == '__main__':
    main()
