"""Can any model forecast gold's next 30 or 60 minutes well enough to pay the spread?

    python -m ml.forecast_check        # writes ml/reports/xauusd_forecast_check.md
    python -m ml.forecast_check --horizons 48 96 --report ml/reports/xauusd_forecast_check_intraday.md
                                       # the same for the next 4 and 8 hours

The model version of the idea screen (ml/screen.py): instead of one hand-written rule at a time, a LightGBM
regression gets about 40 generic inputs from closed M5 bars and learns the move of the mid price over the next
30 and 60 minutes. It is trained on the discovery years and judged on the confirmation years (development data
only). The question is only how large its best forecasts turn out, set against the spread a trade must pay.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from ml import lockbox, screen
from ml.data import ROOT
from ml.ideas import build, rsi

REPORT = ROOT / 'ml' / 'reports' / 'xauusd_forecast_check.md'
HORIZONS = (6, 12)                       # M5 bars: 30 and 60 minutes
VALIDATION_FROM = '2018-01-01'           # the last discovery year stops the training early
PARAMS = {'objective': 'huber', 'learning_rate': 0.03, 'num_leaves': 31, 'min_data_in_leaf': 2000,
          'feature_fraction': 0.7, 'bagging_fraction': 0.7, 'bagging_freq': 1, 'lambda_l2': 10.0, 'verbose': -1,
          'seed': 7}


def features(m1, horizons=HORIZONS) -> tuple[pd.DataFrame, list[str]]:
    f = build(m1, 300)
    d = f.frame()
    spread = pd.Series(f.bars.spread)
    atr, c = d['atr'], d['c']
    x = pd.DataFrame(index=d.index)
    for k in (1, 3, 6, 12, 48, 288):
        x[f'ret_{k}'] = (c - c.shift(k)) / (atr * np.sqrt(k))
    for k in (20, 100):
        x[f'z_sma_{k}'] = (c - c.rolling(k).mean()) / atr
    x['rsi_14'] = rsi(c)
    x['body'] = (c - d['o']) / atr
    x['range'] = (d['h'] - d['l']) / atr
    x['upper_wick'] = (d['h'] - np.maximum(c, d['o'])) / atr
    x['lower_wick'] = (np.minimum(c, d['o']) - d['l']) / atr
    for k in (12, 48, 288):
        hi, lo = d['h'].rolling(k).max(), d['l'].rolling(k).min()
        x[f'pos_{k}'] = (c - lo) / (hi - lo).replace(0, np.nan)
        x[f'to_high_{k}'] = (hi - c) / atr
        x[f'to_low_{k}'] = (c - lo) / atr
    day = d.groupby('day').agg(high=('h', 'max'), low=('l', 'min'), close=('c', 'last'))
    for name in ('high', 'low', 'close'):
        x[f'prev_day_{name}'] = (c - d['day'].map(day[name].shift(1))) / atr
    x['day_open'] = (c - d.groupby('day')['o'].transform('first')) / atr
    x['day_high'] = (d.groupby('day')['h'].cummax() - c) / atr
    x['day_low'] = (c - d.groupby('day')['l'].cummin()) / atr
    for step in (10.0, 50.0):
        x[f'round_{step:g}'] = (c - np.round(c / step) * step) / atr
    x['atr_ratio_day'] = atr / atr.rolling(288).mean()
    x['atr_ratio_week'] = atr / atr.rolling(1440).mean()
    x['vol_trend'] = d['h'].sub(d['l']).rolling(6).mean() / d['h'].sub(d['l']).rolling(48).mean()
    x['spread_atr'] = spread / atr
    x['hour'] = d['minute'] // 60
    x['minute_in_hour'] = d['minute'] % 60
    x['weekday'] = d['weekday']
    names = list(x.columns)
    # Targets on the mid price, from the next bar's open, so the widening spread at the daily close is not a "move".
    mid_open = d['o'] + spread / 2
    mid_close = c + spread / 2
    for k in horizons:
        x[f'y_{k}'] = (mid_close.shift(-k) - mid_open.shift(-1)) / atr
        gap = d['t'].shift(-k) - d['t']
        x.loc[gap != 300 * k, f'y_{k}'] = np.nan         # no targets across a weekend or a break
    x['t'], x['atr'], x['spread'] = d['t'], atr, spread
    return x, names


def tenths(score: np.ndarray, y: np.ndarray, atr: np.ndarray) -> pd.DataFrame:
    order = pd.qcut(pd.Series(score).rank(method='first'), 10, labels=False)
    out = pd.DataFrame({'tenth': order, 'forecast': score, 'move': y, 'usd': y * atr}).groupby('tenth').mean()
    return out


def run(horizons=HORIZONS, log=print) -> str:
    m1 = screen.load()
    x, names = features(m1, horizons)
    start, mid, end = (screen.epoch(day) for day in (screen.DISCOVERY[0], VALIDATION_FROM, screen.CONFIRM[0]))
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    lines = [f'# XAUUSD forecast check ({stamp})', '',
             f'Development gold only (nothing from {lockbox.LOCK_START} on is loaded). LightGBM regression on '
             f'{len(names)} inputs from closed M5 bars. Trained {screen.DISCOVERY[0]} to {VALIDATION_FROM}, stopped '
             f'early on {VALIDATION_FROM} to {screen.CONFIRM[0]}, judged on {screen.CONFIRM[0]} to {screen.CONFIRM[1]}. '
             'The target is the move of the mid price from the next bar to '
             + ' or '.join(str(k * 5) for k in horizons) + ' minutes later, in ATR of M5. A target never '
             'crosses the daily break or a weekend.', '']
    for k in horizons:
        col = f'y_{k}'
        data = x[np.isfinite(x[col]) & np.isfinite(x['atr']) & (x['t'] >= start)]
        train, valid, test = data[data['t'] < mid], data[(data['t'] >= mid) & (data['t'] < end)], data[data['t'] >= end]
        booster = lgb.train(PARAMS, lgb.Dataset(train[names], train[col]), num_boost_round=600,
                            valid_sets=[lgb.Dataset(valid[names], valid[col])],
                            callbacks=[lgb.early_stopping(50, verbose=False)])
        score = booster.predict(test[names], num_iteration=booster.best_iteration)
        y, atr, spread = test[col].to_numpy(), test['atr'].to_numpy(), test['spread'].to_numpy()
        ic = float(pd.Series(score).corr(pd.Series(y), method='spearman'))
        table = tenths(score, y, atr)
        cost_atr, cost_usd = float(np.median(spread / atr)), float(np.median(spread))
        top, bottom = table.iloc[-1], table.iloc[0]
        log(f'{k * 5} min: rounds {booster.best_iteration}, rank corr {ic:+.4f}, top tenth {top.move:+.4f} ATR '
            f'(${top.usd:+.3f}), bottom {bottom.move:+.4f} ATR (${bottom.usd:+.3f}), spread {cost_atr:.3f} ATR')
        gain = pd.Series(booster.feature_importance('gain'), index=names).sort_values(ascending=False)
        lines += [f'## Next {k * 5} minutes', '',
                  f'{len(train):,} training bars, {len(test):,} test bars, {booster.best_iteration} rounds. Rank '
                  f'correlation between forecast and outcome on the test years: **{ic:+.4f}** (0 = no skill).', '',
                  f'Median spread on the test years: {cost_atr:.3f} ATR (${cost_usd:.2f} per oz). A trade has to '
                  'beat that.', '',
                  '| Forecast tenth | Mean forecast (ATR) | Mean real move (ATR) | Mean real move ($ per oz) |',
                  '|---|---|---|---|']
        for tenth, row in table.iterrows():
            label = 'lowest' if tenth == 0 else 'highest' if tenth == 9 else str(int(tenth) + 1)
            lines.append(f'| {label} | {row.forecast:+.4f} | {row.move:+.4f} | {row.usd:+.3f} |')
        best = max(abs(top.usd), abs(bottom.usd))
        lines += ['', f'Best tenth: ${best:.3f} per oz before costs, against a spread of ${cost_usd:.2f}: '
                      f'**{best / cost_usd:.0%} of the cost.**', '',
                  'Most used inputs: ' + ', '.join(f'{name} {share:.0%}' for name, share in
                                                    (gain / gain.sum()).head(6).items()) + '.', '']
    return '\n'.join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--horizons', type=int, nargs='+', default=list(HORIZONS), help='in M5 bars')
    parser.add_argument('--report', type=Path, default=REPORT)
    args = parser.parse_args()
    args.report.write_text(run(tuple(args.horizons)), encoding='utf-8', newline='\n')
    print(f'report -> {args.report}')


if __name__ == '__main__':
    main()
