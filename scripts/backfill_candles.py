#!/usr/bin/env python3
"""One-time backfill of broker M1 candles into the analyzer, so the website chart has history before the feeder started.

The live feeder only sends a few hours on its first push and then keeps up minute by minute. This walks backward from
now in 2-day chunks through the same /candles endpoint, which never replaces a stored candle and extends the coverage
window as each older chunk touches it. Safe to run while the feeder is running, and safe to run again.

Run on Windows with the terminal open and logged in (reading history places no orders):
    py -3.13 scripts/backfill_candles.py --symbol XAUUSDc --days 180
It stops early when MT5 has no older M1 history (raise "Max bars in chart" in MT5 Options > Charts for more).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mt5_feeder import CANDLE_CHUNK, env, post  # noqa: E402

EMPTY_STOP = 4      # consecutive empty 2-day chunks (8 days, longer than any weekend or holiday) = history exhausted


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill broker M1 candles into the analyzer.')
    parser.add_argument('--symbol', required=True, help='broker symbol as named in MT5, e.g. XAUUSDc')
    parser.add_argument('--days', type=float, default=180, help='how far back to go (default 180)')
    args = parser.parse_args()

    settings = env()
    analyzer = os.getenv('ZEBRA_ANALYZER_URL', f'http://127.0.0.1:{settings.get("ANALYZER_PORT", "8010")}').rstrip('/')
    token = os.getenv('ZEBRA_ANALYZER_TOKEN') or settings.get('ANALYZER_TOKEN', '')
    if not token:
        raise SystemExit('ANALYZER_TOKEN missing from .env')
    symbol = re.sub(r'[a-z.]+$', '', args.symbol).upper()
    if not mt5.initialize():
        raise SystemExit(f'MT5 initialize failed: {mt5.last_error()}')
    if not mt5.symbol_select(args.symbol, True) or (info := mt5.symbol_info(args.symbol)) is None:
        raise SystemExit(f'unknown MT5 symbol {args.symbol}')

    end = int(time.time()) // 60 * 60
    floor = end - int(args.days * 86400)
    stop, stored, empty, oldest = end, 0, 0, None
    while stop > floor:
        start = max(floor, stop - CANDLE_CHUNK)
        window = (dt.datetime.fromtimestamp(start, dt.timezone.utc), dt.datetime.fromtimestamp(stop, dt.timezone.utc))
        rates = mt5.copy_rates_range(args.symbol, mt5.TIMEFRAME_M1, *window)
        if rates is not None and len(rates) == 0:
            time.sleep(1)                       # the terminal may still be downloading this range from the server
            rates = mt5.copy_rates_range(args.symbol, mt5.TIMEFRAME_M1, *window)
        if rates is None:
            raise SystemExit(f'MT5 returned no result for {window[0]:%Y-%m-%d}: {mt5.last_error()}')
        rows = [[int(r['time']), float(r['open']), float(r['high']), float(r['low']), float(r['close']),
                 round(float(r['spread']) * info.point, 8)]
                for r in rates if start <= int(r['time']) and int(r['time']) + 60 <= stop]
        status, text = post({'symbol': symbol, 'start': start, 'end': stop, 'candles': rows},
                            analyzer + '/candles', token, limit=2000, timeout=120)
        if status != 200:
            raise SystemExit(f'HTTP {status} {text}')
        reply = json.loads(text)
        stored += len(rows)
        if rows:
            oldest, empty = rows[0][0], 0
        else:
            empty += 1
        print(f'{symbol} {window[0]:%Y-%m-%d %H:%M} -> {window[1]:%Y-%m-%d %H:%M}  {len(rows):5d} candles  '
              f'coverage since {dt.datetime.fromtimestamp(reply["since"], dt.timezone.utc):%Y-%m-%d %H:%M}')
        if empty >= EMPTY_STOP:
            print('MT5 has no older M1 history; stopping')
            break
        stop = start
    first = f'{dt.datetime.fromtimestamp(oldest, dt.timezone.utc):%Y-%m-%d %H:%M} UTC' if oldest else 'none'
    print(f'done: {stored} candles sent (already stored ones are skipped by the analyzer), oldest {first}')


if __name__ == '__main__':
    main()
