#!/usr/bin/env python3
"""One-time backfill of broker M1 candles into the analyzer, so the website chart has history before the feeder started.

The live feeder only sends a few hours on its first push and then keeps up minute by minute. This walks backward from
now in 2-day chunks through the same /candles endpoint, which never replaces a stored candle and extends the coverage
window as each older chunk touches it. Safe to run while the feeder is running, and safe to run again.

Run on Windows with the terminal open and logged in (reading history places no orders):
    py -3.13 scripts/backfill_candles.py --symbol XAUUSDc --days 1100 --skip-days 175
It stops early when MT5 has no older M1 history (raise "Max bars in chart" in MT5 Options > Charts for more), or, with
--csv, carries on from that file (Dukascopy M1 from scripts/pull_dukascopy.py) for the older part. Exness keeps forex
M1 only from early 2024, so three years of EURUSD and the other majors need Dukascopy before that. Those candles are a
different feed (a few points off the broker's), used for the chart's history only: plans are published, and graded,
long after them.
"""
from __future__ import annotations

import argparse
import bisect
import csv
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
STUB = 10           # fewer rows than this in a 2-day chunk counts as empty: MT5 returns a lone bar before its history


def load_csv(path: Path, floor: int, end: int) -> tuple[list[int], list[list]]:
    """Rows of a t,o,h,l,c,spread M1 file inside [floor, end) that the analyzer would accept, sorted by time."""
    rows = []
    with path.open(newline='') as handle:
        for line in csv.DictReader(handle):
            t = int(line['t'])
            if floor <= t < end and t % 60 == 0:
                o, h, l, c, spread = (float(line[k]) for k in ('o', 'h', 'l', 'c', 'spread'))
                if min(o, h, l, c) > 0 and spread >= 0 and h >= max(o, c) and l <= min(o, c):
                    rows.append([t, o, h, l, c, spread])
    rows.sort()
    return [row[0] for row in rows], rows


def main() -> None:
    parser = argparse.ArgumentParser(description='Backfill broker M1 candles into the analyzer.')
    parser.add_argument('--symbol', required=True, help='broker symbol as named in MT5, e.g. XAUUSDc')
    parser.add_argument('--days', type=float, default=180, help='how far back to go (default 180)')
    parser.add_argument('--skip-days', type=float, default=0,
                        help='start this many days back instead of now (history already stored; keep a little overlap)')
    parser.add_argument('--csv', type=Path, help='M1 file (t,o,h,l,c,spread) for the range older than MT5 has')
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

    now = int(time.time()) // 60 * 60
    end = now - int(args.skip_days * 86400)
    floor = now - int(args.days * 86400)
    times, older = load_csv(args.csv, floor, end) if args.csv else ([], [])
    if args.csv:
        print(f'{args.csv}: {len(older)} usable candles in range')
    source, stop, stored, empty, oldest, first_empty = 'mt5', end, 0, 0, None, None
    while stop > floor:
        start = max(floor, stop - CANDLE_CHUNK)
        window = (dt.datetime.fromtimestamp(start, dt.timezone.utc), dt.datetime.fromtimestamp(stop, dt.timezone.utc))
        if source == 'mt5':
            rates = mt5.copy_rates_range(args.symbol, mt5.TIMEFRAME_M1, *window)
            if rates is not None and len(rates) == 0:
                time.sleep(1)                       # the terminal may still be downloading this range from the server
                rates = mt5.copy_rates_range(args.symbol, mt5.TIMEFRAME_M1, *window)
            if rates is None:
                raise SystemExit(f'MT5 returned no result for {window[0]:%Y-%m-%d}: {mt5.last_error()}')
            rows = [[int(r['time']), float(r['open']), float(r['high']), float(r['low']), float(r['close']),
                     round(float(r['spread']) * info.point, 8)]
                    for r in rates if start <= int(r['time']) and int(r['time']) + 60 <= stop]
        else:
            rows = older[bisect.bisect_left(times, start):bisect.bisect_left(times, stop - 59)]
        status, text = post({'symbol': symbol, 'start': start, 'end': stop, 'candles': rows},
                            analyzer + '/candles', token, limit=2000, timeout=120)
        if status != 200:
            raise SystemExit(f'HTTP {status} {text}')
        reply = json.loads(text)
        stored += len(rows)
        if len(rows) >= STUB:
            oldest, empty, first_empty = rows[0][0], 0, None
        else:
            empty += 1
            first_empty = first_empty or stop
        print(f'{symbol} {source} {window[0]:%Y-%m-%d %H:%M} -> {window[1]:%Y-%m-%d %H:%M}  {len(rows):5d} candles  '
              f'coverage since {dt.datetime.fromtimestamp(reply["since"], dt.timezone.utc):%Y-%m-%d %H:%M}')
        if empty >= EMPTY_STOP:
            if source == 'mt5' and args.csv:
                print(f'MT5 has no older M1 history; continuing from {args.csv.name}')
                source, empty, stop, first_empty = 'csv', 0, first_empty, None
                continue
            print(f'{"MT5" if source == "mt5" else args.csv.name} has no older M1 history; stopping')
            break
        stop = start
    first = f'{dt.datetime.fromtimestamp(oldest, dt.timezone.utc):%Y-%m-%d %H:%M} UTC' if oldest else 'none'
    print(f'done: {stored} candles sent (already stored ones are skipped by the analyzer), oldest {first}')


if __name__ == '__main__':
    main()
