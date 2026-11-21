#!/usr/bin/env python3
"""Out-of-sample backtest of the v2 ICT model over one development period (default: its last 12 months).

    python -m ml.backtest                                  # the last 12 months before the lockbox
    python -m ml.backtest --from 2022-01-01 --to 2023-01-01

Development data only: the lockbox (2024-11-20 on) is read once, by ml/final_test.py, never here.

The model is trained exactly as one walk-forward fold of ml/train.py: on tradable filled trades from --train-from
that finished a day before the period starts. The last 20% of that window is validation: rounds by early stopping
and the cut on expected net R are chosen there. Nothing from the period itself is used to fit or tune anything.

How the cut is chosen (ml.train.choose_threshold): the model gives every validation trade an expected net R; cuts
are tried at the 0%, 5%, ..., 95% quantiles; a cut counts only if it keeps at least --min-val-trades trades whose
mean net R is above zero; the best by mean R x sqrt(trades) wins. If no cut qualifies, the model takes no trades in
the period. The report lists every cut with its validation result, so a "no trades" outcome shows exactly why.

Trading in the period is as live: one open plan per side, unfilled limits score 0R and block their slot until they
expire, net R after spread and 0.5 x spread slippage on stop and time exits. The same model also trades the
broker-price candidates of the period when ml/data/xauusd_ict_exness_dev.parquet covers it.

Writes ml/reports/<symbol>_v2_backtest_<from>_<to>.md.
"""
from __future__ import annotations

import argparse
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml import train  # noqa: E402

QUANTILES = np.arange(0.0, 0.96, 0.05)


def fit_before(df: pd.DataFrame, start: int, train_from: int, min_val: int) -> dict:
    """One walk-forward fold's model for a period starting at `start`, with its validation slice scored."""
    filled = df[df['filled'] & (df['bar_time'] >= train_from) & (df['end_time'] < start - train.EMBARGO)]
    window = train.fit_window(filled, min_val)
    return {**window, 'min_val': min_val, 'trained_from': train.day(filled['bar_time'].min()),
            'trained_to': train.day(filled['end_time'].max()), 'val_from': train.day(window['val']['bar_time'].min())}


def scan(val: pd.DataFrame, min_val: int) -> pd.DataFrame:
    """Every cut choose_threshold tried on validation: trades kept, predicted and realised net R, how the trades
    ended, and whether the cut qualified (enough trades and realised net R above zero)."""
    rows = []
    for q in QUANTILES:
        cut = float(np.quantile(val['expected_r'], q))
        kept = val[val['expected_r'] >= cut]
        net = kept['r_net'].mean()
        rows.append({'top': 1 - q, 'cut': cut, 'trades': len(kept), 'predicted_r': kept['expected_r'].mean(),
                     'net_r': net, 'target': (kept['cls'] == train.TARGET).mean(),
                     'stop': (kept['cls'] == train.STOP).mean(), 'timeout': (kept['cls'] == train.TIMEOUT).mean(),
                     'qualifies': len(kept) >= min_val and net > 0})
    return pd.DataFrame(rows)


def score(period: pd.DataFrame, fold: dict) -> pd.DataFrame:
    return period.join(train.score(fold['bundle'], period))


def trades_at(period: pd.DataFrame, cut: float) -> pd.DataFrame:
    return train.take_non_overlapping(period[period['expected_r'] >= cut]) if len(period) else period


def monthly(trades: pd.DataFrame) -> pd.Series:
    filled = trades[trades['filled']] if len(trades) else trades
    if not len(filled):
        return pd.Series(dtype=float)
    return filled.groupby(pd.to_datetime(filled['end_time'], unit='s').dt.strftime('%Y-%m'))['r_net'].sum()


def report(symbol, start, end, fold, period, broker) -> str:
    thr, val, info = fold['threshold'], fold['val'], fold['validation']
    none = math.isinf(thr)
    model = trades_at(period, thr)
    lines = [f'# {symbol} ICT ML model v2: backtest {train.day(start)} .. {train.day(end)}', '',
             f"Out of sample, development data. Trained on {fold['train_rows']:,} tradable filled trades "
             f"{fold['trained_from']} .. {fold['trained_to']} (rounds {fold['rounds']}). Cut chosen on the validation "
             f"slice {fold['val_from']} .. {fold['trained_to']} ({len(val):,} trades). Nothing from the test period "
             'was used to fit or tune.', '',
             '## Result', '', train.HEAD, '| model (Dukascopy prices) ' + train.fmt(train.stats(model))]
    if broker is not None and len(broker):
        lines.append("| model (broker prices, Dukascopy's spread) " + train.fmt(train.stats(trades_at(broker, thr))))
    if none:
        lines += ['', f"**The model took no trades.** It has no cut: on validation, no level of expected profit kept "
                  f"at least {fold['min_val']} trades with a net result above zero, so the rule is to stay out."]
    else:
        lines += ['', f"Cut {thr:+.3f}R expected: on validation it kept {info['n']} trades at {info['mean_r']:+.3f}R "
                  'net each.']

    s = scan(val, fold['min_val'])
    best = s.loc[s['net_r'].idxmax()]
    lines += ['', '## Why: every cut the model tried on validation', '',
              'The model gives each validation trade an expected net R (after spread and slippage). A cut keeps the '
              'trades at or above it. "Predicted" is what the model expected of the kept trades, "Realised" is what '
              'they made.', '',
              '| Keep top | Cut | Trades | Predicted R | Realised net R | Hit target | Stopped | Timed out | '
              'Qualifies |', '|---|---|---|---|---|---|---|---|---|']
    for r in s.itertuples():
        lines.append(f"| {r.top:.0%} | {r.cut:+.3f} | {r.trades} | {r.predicted_r:+.3f} | {r.net_r:+.3f} | "
                     f"{r.target:.1%} | {r.stop:.1%} | {r.timeout:.1%} | {'yes' if r.qualifies else 'no'} |")
    lines += ['', 'What this shows:', '',
              f"- Target rate: {s['target'].iloc[0]:.1%} of all {len(val):,} validation trades reach the target; in the "
              f"model's top 10% it is {s['target'].iloc[-2]:.1%}."
              + (' The model now selects for reaching the target, which version 1 did not.'
                 if s['target'].iloc[-2] > s['target'].iloc[0] else ' The model does not raise it.'),
              f"- Profit: the best cut is the top {best['top']:.0%} at {best['net_r']:+.3f}R per trade "
              f"({int(best['trades'])} trades)" + ('; it qualifies.' if best['qualifies'] else
                                                    '; no cut is above zero with enough trades.'),
              '', '## Hindsight check: the same cuts in the test period', '',
              'Not used for any decision. It shows whether trading anyway would have paid.', '',
              '| Keep top (validation cut) | Trades | Win | Net R per trade | Total net R | Max DD R |',
              '|---|---|---|---|---|---|']
    for r in s.itertuples():
        st = train.stats(trades_at(period, r.cut))
        if st['trades']:
            lines.append(f"| {r.top:.0%} ({r.cut:+.3f}) | {st['trades']} | {st['win_rate']:.1%} | "
                         f"{st['expectancy_r']:+.3f} | {st['total_r']:+.1f} | {st['max_drawdown_r']:.1f} |")
    if not none and len(model):
        months = monthly(model)
        lines += ['', '## Model net R by month', '', '| Month | Net R |', '|---|---|']
        lines += [f'| {m} | {v:+.1f} |' for m, v in months.items()]
        lines.append(f'| **Total** | **{months.sum():+.1f}** |')
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--data', type=Path, default=train.DATA)
    parser.add_argument('--exness', type=Path, default=train.EXNESS)
    parser.add_argument('--from', dest='start', help='first day of the period (default: 12 months before --to)')
    parser.add_argument('--to', dest='end', help='day after the period (default: the end of the development data)')
    parser.add_argument('--train-from', default='2011-01-01')
    parser.add_argument('--min-val-trades', type=int, default=150)
    args = parser.parse_args()

    df = train.load(args.data)
    end = train.epoch(args.end) if args.end else int(df['bar_time'].max()) + 1
    start = train.epoch(args.start) if args.start else \
        int((datetime.fromtimestamp(end, timezone.utc) - timedelta(days=365)).replace(
            hour=0, minute=0, second=0).timestamp())
    fold = fit_before(df, start, train.epoch(args.train_from), args.min_val_trades)
    inside = lambda frame: frame[(frame['bar_time'] >= start) & (frame['bar_time'] < end)]
    period = score(inside(df), fold)
    broker = score(inside(train.load(args.exness)), fold) if args.exness.exists() else None
    text = report(args.symbol.upper(), start, end, fold, period, broker)
    tag = f"{train.day(start)}_{train.day(end)}".replace('-', '')
    path = ROOT / 'ml' / 'reports' / f'{args.symbol.lower()}_v2_backtest_{tag}.md'
    path.write_text(text, encoding='utf-8')
    print(text)
    print(f'report -> {path}')


if __name__ == '__main__':
    main()
