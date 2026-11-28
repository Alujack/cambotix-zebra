#!/usr/bin/env python3
"""Chart-only Binance spot feed: closed M1 candles every minute and the live best bid/ask, for the website's chart and
watchlist. Nothing is scanned or published. Public market-data endpoints only: no account, no API key, no MT5.

    py -3.13 scripts/binance_feeder.py --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT
    py -3.13 scripts/binance_feeder.py --symbols BTCUSDT,ETHUSDT --backfill-days 180     # one-time history, then exits
Unattended: scripts\\install_autostart.ps1 -Script binance_feeder.py -Symbol BTCUSDT,... (see that script).

api.binance.com is unreachable from some networks; BINANCE_API in .env (or the environment) picks another host.
The default, data-api.binance.vision, is Binance's own public market-data mirror. Binance candles carry no spread,
so they are stored with spread 0: these symbols are for charts, not for grading plans.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mt5_feeder import CANDLE_CHUNK, env, post  # noqa: E402  (mt5_feeder imports MetaTrader5; fine on the Windows PC)

DEFAULT_API = 'https://data-api.binance.vision'
TICK_PASS = 1.0             # one bookTicker request for every symbol per pass (weight 4; the limit is 6000 a minute)
KLINE_LIMIT = 1000          # Binance's maximum per klines request
CHUNKS_PER_MINUTE = 20      # catching up after downtime: 40 days per symbol per minute, the rest the next minute


def get(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'zebra-chart-feed'}), timeout=15) as r:
        return json.loads(r.read())


def klines(api: str, symbol: str, start: int, stop: int) -> list[list]:
    """Closed M1 candles with open time in [start, stop - 60] as [t, o, h, l, c, spread=0]."""
    rows, cursor = [], start
    while cursor < stop:
        query = urllib.parse.urlencode({'symbol': symbol, 'interval': '1m', 'startTime': cursor * 1000,
                                        'endTime': (stop - 60) * 1000, 'limit': KLINE_LIMIT})
        batch = get(f'{api}/api/v3/klines?{query}')
        for k in batch:
            t = int(k[0]) // 1000
            if start <= t <= stop - 60:
                rows.append([t, float(k[1]), float(k[2]), float(k[3]), float(k[4]), 0.0])
        if len(batch) < KLINE_LIMIT:
            break
        cursor = int(batch[-1][0]) // 1000 + 60
    return rows


def send_chunk(cfg: dict, symbol: str, start: int, stop: int) -> dict | None:
    rows = klines(cfg['api'], symbol, start, stop)
    status, text = post({'symbol': symbol, 'start': start, 'end': stop, 'candles': rows},
                        cfg['candles_url'], cfg['token'], limit=2000, timeout=120)
    if status != 200:
        print(f'  {symbol} candles: HTTP {status} {text}')
        return None
    return {**json.loads(text), 'rows': len(rows)}


def push_candles(cfg: dict, symbol: str, state: dict) -> None:
    """Forward from the analyzer's need_from to the last closed minute, as scripts/mt5_feeder.py does."""
    end = int(time.time()) // 60 * 60
    start = state.get('need_from') or end - cfg['first_candles']
    for _ in range(CHUNKS_PER_MINUTE):
        start = min(start, end - 60)
        try:
            reply = send_chunk(cfg, symbol, start, min(end, start + CANDLE_CHUNK))
        except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
            print(f'  {symbol} candles: Binance {type(exc).__name__}: {exc}; retrying next minute')
            return
        if reply is None:
            return
        state['need_from'] = reply['need_from']
        if reply['need_from'] >= end:
            return
        start = reply['need_from']
    print(f'  {symbol} candles: catch-up continues next minute')


def backfill(cfg: dict, symbol: str, days: float) -> None:
    """Backward from now, so each older chunk touches the stored window and extends it (see backfill_candles.py)."""
    stop = int(time.time()) // 60 * 60
    floor, total = stop - int(days * 86400), 0
    while stop > floor:
        start = max(floor, stop - CANDLE_CHUNK)
        reply = send_chunk(cfg, symbol, start, stop)
        if reply is None:
            raise SystemExit(1)
        total += reply['rows']
        print(f'{symbol} {dt.datetime.fromtimestamp(start, dt.timezone.utc):%Y-%m-%d %H:%M}  {reply["rows"]:5d} candles')
        if reply['rows'] == 0 and total > 0:
            print(f'{symbol}: no older history on Binance; stopping')
            break
        stop = start
    print(f'{symbol}: {total} candles sent')


def push_ticks(cfg: dict, symbols: list[str], states: dict) -> None:
    query = urllib.parse.quote(json.dumps(symbols, separators=(',', ':')))
    try:
        book = get(f'{cfg["api"]}/api/v3/ticker/bookTicker?symbols={query}')
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as exc:
        log_once(states, f'  ticks: Binance {type(exc).__name__}: {exc}')
        return
    now_ms = int(time.time() * 1000)
    for row in book:
        symbol, quote = row['symbol'], (float(row['bidPrice']), float(row['askPrice']))
        state = states[symbol]
        if quote == state.get('quote') or quote[0] <= 0 or quote[1] < quote[0]:
            continue
        status, text = post({'symbol': symbol, 'ticks': [[now_ms, *quote]]}, cfg['ticks_url'], cfg['token'], timeout=3)
        if status == 200:
            state['quote'] = quote
        else:
            log_once(states, f'  {symbol} ticks: HTTP {status} {text}')


def log_once(states: dict, message: str) -> None:
    """Failures while ticking are logged at most once a minute."""
    if time.time() - states['_logged'] >= 60:
        states['_logged'] = time.time()
        print(message)


def main() -> None:
    parser = argparse.ArgumentParser(description='Chart-only Binance candles and live prices.')
    parser.add_argument('--symbols', required=True, help='comma list of Binance spot symbols, e.g. BTCUSDT,ETHUSDT')
    parser.add_argument('--history-hours', type=float, default=48,
                        help='M1 history sent on start, so a restart after downtime closes the gap (default 48)')
    parser.add_argument('--backfill-days', type=float, help='send this much history for every symbol, then exit')
    args = parser.parse_args()

    settings = env()
    analyzer = os.getenv('ZEBRA_ANALYZER_URL', f'http://127.0.0.1:{settings.get("ANALYZER_PORT", "8010")}').rstrip('/')
    cfg = {'api': (os.getenv('BINANCE_API') or settings.get('BINANCE_API') or DEFAULT_API).rstrip('/'),
           'token': os.getenv('ZEBRA_ANALYZER_TOKEN') or settings.get('ANALYZER_TOKEN', ''),
           'candles_url': analyzer + '/candles', 'ticks_url': analyzer + '/ticks',
           'first_candles': int(args.history_hours * 3600)}
    if not cfg['token']:
        raise SystemExit('ANALYZER_TOKEN missing from .env')
    symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    if not symbols:
        raise SystemExit('--symbols is empty')
    if args.backfill_days:
        for symbol in symbols:
            backfill(cfg, symbol, args.backfill_days)
        return

    states: dict = {symbol: {} for symbol in symbols} | {'_logged': 0.0}
    print(f'binance chart feed: {",".join(symbols)} from {cfg["api"]} -> {analyzer}')
    print(f'watching; ticks every {TICK_PASS}s, candles every minute. Ctrl+C to stop.')
    next_job = 0.0
    try:
        while True:
            started = time.time()
            push_ticks(cfg, symbols, states)
            if time.time() >= next_job:
                for symbol in symbols:
                    push_candles(cfg, symbol, states[symbol])
                next_job = (int(time.time()) // 60 + 1) * 60 + 10
            time.sleep(max(0.0, TICK_PASS - (time.time() - started)))
    except KeyboardInterrupt:
        print('stopped')


if __name__ == '__main__':
    main()
