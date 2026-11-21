#!/usr/bin/env python3
"""The one final test of plan v2: trade the lockbox (2024-11-20 on) with the frozen development model. Runs once.

    python -m ml.final_test

Preconditions, each a hard stop:
  - a promoted model exists (python -m ml.train) and it passed all five development gates
  - it has a cut (a model with no profitable cut on validation takes no trades; there is nothing to test)
  - the final test has not run before: its result file ml/models/<symbol>_final_test.json does not exist

Then, exactly once: read ml/data/lockbox/<name>_lockbox.parquet, apply the account filter, score every candidate
with the frozen model and cut, trade one open plan per side with net R as in ml/train.py, and seal the result.

Lockbox pass (docs/ml-plan.md V2.7.9): expectancy above +0.10R and profit factor above 1.2, max drawdown at most
15R, at least 100 trades a year, and at least +0.05R per trade better than taking every tradable setup. A pass is
weak evidence (a model with no edge passes by luck roughly 6-13% of the time at this sample size) and earns a demo
forward test judged at 400 trades, nothing more.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml import lockbox, train  # noqa: E402

REPORTS = ROOT / 'ml' / 'reports'


class NotAllowed(Exception):
    """A precondition of the final test is not met; the lockbox was not opened."""


def criteria(model: dict, everything: dict, years: float) -> list[dict]:
    exp, pf = model['expectancy_r'], model['profit_factor']
    per_year = model['trades'] / years if years else 0.0
    base = everything['expectancy_r']
    g = train.GATES
    return [
        {'name': 'expectancy and profit factor', 'required': f"> {g['expectancy_r']:+.2f}R and PF > {g['profit_factor']}",
         'measured': f'{exp:+.3f}R, PF {pf:.2f}' if exp is not None and pf is not None else 'no trades',
         'passed': bool(exp is not None and pf is not None and exp > g['expectancy_r'] and pf > g['profit_factor'])},
        {'name': 'drawdown and enough trades',
         'required': f"max drawdown <= {g['max_drawdown_r']:g}R, >= {g['trades_per_year']} trades a year",
         'measured': f"max drawdown {model['max_drawdown_r']:.1f}R, {per_year:.0f} trades a year",
         'passed': bool(model['trades'] and model['max_drawdown_r'] <= g['max_drawdown_r']
                        and per_year >= g['trades_per_year'])},
        {'name': 'better than every tradable setup', 'required': f"+{g['margin_r']:.2f}R per trade over it",
         'measured': f'{exp:+.3f}R vs {base:+.3f}R' if exp is not None and base is not None else 'no trades',
         'passed': bool(exp is not None and base is not None and exp >= base + g['margin_r'])},
    ]


def run(symbol: str = 'XAUUSD', name: str | None = None, models: Path = train.MODELS,
        data: Path = lockbox.DATA) -> dict:
    """Run the final test and seal its result. Raises NotAllowed or lockbox.LockboxError without opening the
    lockbox when a precondition fails."""
    name = name or f'{symbol.lower()}_ict'
    bundle, meta = train.load_model(symbol, models)
    if not meta.get('gates_passed'):
        failed = [g['gate'] for g in meta.get('gates', []) if not g.get('passed')]
        raise NotAllowed(f"{meta['version']} failed development gates {failed}; the lockbox stays closed")
    if meta.get('threshold') is None:
        raise NotAllowed(f"{meta['version']} has no cut (no profitable one on validation); nothing to test")
    df = train.prepare(lockbox.open_once(name, symbol, models, data))
    df = df.join(train.score(bundle, df))
    model = train.take_non_overlapping(df[df['expected_r'] >= meta['threshold']])
    everything = train.take_non_overlapping(df)
    m, e = train.stats(model), train.stats(everything)
    rows = criteria(m, e, train.years_covered(df))
    result = {'symbol': symbol, 'model': meta['version'], 'threshold': meta['threshold'],
              'period': [train.day(df['bar_time'].min()), train.day(df['bar_time'].max())] if len(df) else None,
              'tradable_candidates': int(len(df)), 'model_stats': m, 'all_tradable_stats': e, 'criteria': rows,
              'passed': all(r['passed'] for r in rows)}
    lockbox.seal(symbol, models, result)
    return result


def markdown(result: dict) -> str:
    lines = [f"# {result['symbol']} ICT model v2: final test on the lockbox", '',
             f"Model `{result['model']}`, cut {result['threshold']:+.3f}R expected, on {result['tradable_candidates']:,} "
             f"tradable candidates {result['period'][0]} .. {result['period'][1]}. Run once; the result is sealed in "
             f"`ml/models/{result['symbol'].lower()}_final_test.json`.", '',
             f"## Result: **{'PASSED' if result['passed'] else 'FAILED'}**", '',
             '| Criterion | Required | Measured | Pass |', '|---|---|---|---|']
    lines += [f"| {r['name']} | {r['required']} | {r['measured']} | {'yes' if r['passed'] else 'no'} |"
              for r in result['criteria']]
    lines += ['', train.HEAD, '| model ' + train.fmt(result['model_stats']),
              '| all tradable candidates ' + train.fmt(result['all_tradable_stats']), '',
              'A pass earns a demo forward test judged at 400 graded trades; it is weak evidence on its own.'
              if result['passed'] else 'The model does not go to a forward test.']
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    args = parser.parse_args()
    symbol = args.symbol.upper()
    try:
        result = run(symbol)
    except (NotAllowed, lockbox.LockboxError, FileNotFoundError) as error:
        raise SystemExit(f'final test not run: {error}')
    text = markdown(result)
    path = REPORTS / f'{symbol.lower()}_v2_final_test.md'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    print(text)
    print(f'report -> {path}')


if __name__ == '__main__':
    main()
