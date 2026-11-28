#!/usr/bin/env python3
"""Chart-only MT5 feed for several symbols in one process: closed M1 candles every minute and live ticks, for the
website's chart and watchlist. Nothing is scanned or published (the models lost on these symbols; see
scripts/mt5_feeder.py for the signal feeders). Same candle and tick code as mt5_feeder.py, so the data is identical.

Run on Windows with the terminal open and logged in (reading prices places no orders):
    py -3.13 scripts/chart_feeder.py --symbols GBPUSDc,USDJPYc,AUDUSDc,USDCADc,USDCHFc,NZDUSDc
Unattended: scripts\\install_autostart.ps1 -Script chart_feeder.py -Symbol GBPUSDc,... (see that script).
History older than --history-hours comes from scripts/backfill_candles.py.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

import MetaTrader5 as mt5

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mt5_feeder import env, push_candles, push_ticks  # noqa: E402

TICK_PASS = 1.0             # seconds between tick passes over all symbols (the signal feeders use 0.5 s for one symbol)


def main() -> None:
    parser = argparse.ArgumentParser(description='Chart-only MT5 candles and ticks for several symbols.')
    parser.add_argument('--symbols', required=True, help='comma list of broker symbols as named in MT5')
    parser.add_argument('--history-hours', type=float, default=48,
                        help='M1 history sent on start, so a restart after downtime closes the gap (default 48)')
    args = parser.parse_args()

    settings = env()
    analyzer = os.getenv('ZEBRA_ANALYZER_URL', f'http://127.0.0.1:{settings.get("ANALYZER_PORT", "8010")}').rstrip('/')
    token = os.getenv('ZEBRA_ANALYZER_TOKEN') or settings.get('ANALYZER_TOKEN', '')
    if not token:
        raise SystemExit('ANALYZER_TOKEN missing from .env')
    feeds = [({'mt5_symbol': s, 'symbol': re.sub(r'[a-z.]+$', '', s).upper(), 'token': token,
               'candles_url': analyzer + '/candles', 'ticks_url': analyzer + '/ticks',
               'first_candles': int(args.history_hours * 3600)}, {})
             for s in (item.strip() for item in args.symbols.split(',')) if s]
    if not feeds:
        raise SystemExit('--symbols is empty')
    if not mt5.initialize():
        raise SystemExit(f'MT5 initialize failed: {mt5.last_error()}')
    for cfg, _ in feeds:
        if not mt5.symbol_select(cfg['mt5_symbol'], True):
            raise SystemExit(f'unknown MT5 symbol {cfg["mt5_symbol"]}')
    print(f'chart feed: {", ".join(cfg["mt5_symbol"] + " -> " + cfg["symbol"] for cfg, _ in feeds)}  {analyzer}')
    print(f'watching; ticks every {TICK_PASS}s, candles every minute. Ctrl+C to stop.')

    next_job = 0.0                  # candles right away: the start-up history closes any gap left by downtime
    try:
        while True:
            started = time.time()
            for cfg, state in feeds:
                push_ticks(cfg, state, dry_run=False)
            if time.time() >= next_job:
                for cfg, state in feeds:
                    push_candles(cfg, state)
                next_job = (int(time.time()) // 60 + 1) * 60 + 10
            time.sleep(max(0.0, TICK_PASS - (time.time() - started)))
    except KeyboardInterrupt:
        print('stopped')


if __name__ == '__main__':
    main()
