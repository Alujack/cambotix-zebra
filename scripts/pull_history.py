#!/usr/bin/env python3
"""Save broker history from MetaTrader 5 to .local/history/ for scripts/backtest.py.

Run on Windows with the Python that has the MetaTrader5 package (here: `py -3.13 scripts/pull_history.py`),
with the terminal open and logged in. Writes M1 (with spread, used for grading), M15 (signals), and H4/D1/W1
(SMC context). The backtest itself runs anywhere and never touches MT5.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import MetaTrader5 as mt5

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '.local' / 'history'
FRAMES = {'m1': mt5.TIMEFRAME_M1, 'm15': mt5.TIMEFRAME_M15, 'h4': mt5.TIMEFRAME_H4,
          'd1': mt5.TIMEFRAME_D1, 'w1': mt5.TIMEFRAME_W1}
CHUNK_DAYS = 20                   # M1 requests stay small; the terminal can refuse very large ranges


def fetch(symbol: str, frame: int, start: datetime, end: datetime) -> list:
    rows, cursor, step = [], start, timedelta(days=CHUNK_DAYS)
    while cursor < end:
        upper = min(cursor + step, end)
        for _ in range(5):
            rates = mt5.copy_rates_range(symbol, frame, cursor, upper)
            if rates is not None:
                break
            time.sleep(1)
        else:
            raise SystemExit(f'MT5 refused {symbol} {cursor:%Y-%m-%d}..{upper:%Y-%m-%d}: {mt5.last_error()}')
        rows.extend(rates)
        cursor = upper
    seen, unique = set(), []
    for r in rows:
        if int(r['time']) not in seen:
            seen.add(int(r['time']))
            unique.append(r)
    return sorted(unique, key=lambda r: int(r['time']))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSDm', help='MT5 symbol, e.g. XAUUSDm or XAUUSDc')
    parser.add_argument('--days', type=int, default=365, help='how far back to pull (default 365)')
    args = parser.parse_args()

    if not mt5.initialize():
        raise SystemExit(f'MT5 initialize failed: {mt5.last_error()} - open the terminal and log in first')
    if not mt5.symbol_select(args.symbol, True):
        raise SystemExit(f'Symbol {args.symbol} not available on this account')
    info = mt5.symbol_info(args.symbol)
    clean = re.sub(r'[a-z]+$', '', args.symbol)
    end = datetime.now(timezone.utc) + timedelta(days=1)
    start = end - timedelta(days=args.days + 1)
    OUT.mkdir(parents=True, exist_ok=True)

    for name, frame in FRAMES.items():
        # Context frames need extra warm-up before the first signal bar.
        since = start - timedelta(days={'m1': 0, 'm15': 5, 'h4': 120, 'd1': 400, 'w1': 900}[name])
        rates = fetch(args.symbol, frame, since, end)
        path = OUT / f'{clean}_{name}.csv'
        with path.open('w', newline='') as handle:
            out = csv.writer(handle)
            out.writerow(['t', 'o', 'h', 'l', 'c', 'spread'])
            for r in rates:
                out.writerow([int(r['time']), float(r['open']), float(r['high']), float(r['low']), float(r['close']),
                              round(int(r['spread']) * info.point, 8)])
        first = datetime.fromtimestamp(int(rates[0]['time']), timezone.utc) if rates else None
        print(f'{name:>4}: {len(rates):>7} bars from {first:%Y-%m-%d} -> {path.relative_to(ROOT)}' if rates
              else f'{name:>4}: no bars')
    (OUT / f'{clean}_meta.json').write_text(json.dumps(
        {'mt5_symbol': args.symbol, 'symbol': clean, 'point': info.point, 'digits': info.digits,
         'pulled_at': int(time.time()), 'days': args.days}, indent=2))
    mt5.shutdown()


if __name__ == '__main__':
    main()
