#!/usr/bin/env python3
"""Save Dukascopy history to .local/history/ for scripts/backtest.py - no MetaTrader needed (runs on the Mac).

Writes the same files as scripts/pull_history.py: <SYMBOL>_{m1,m15,h4,d1,w1}.csv and <SYMBOL>_meta.json.
M1 bars are Dukascopy BID minute candles with spread = ask open - bid open; M15/H4/D1/W1 are built from them
(and from Dukascopy hourly candles for the warm-up before the M1 range). Times are UTC, D1 starts at 00:00 UTC
and W1 on Sunday, like a GMT+0 MT5 server (Exness). Prices and spreads are Dukascopy's, not your broker's, so
results come close to an MT5 pull but are not identical.

Downloads are cached in .local/dukascopy/, so a rerun (or a run with more --days) only fetches what is missing.
Standard library only:  python3 scripts/pull_dukascopy.py --symbol XAUUSD --days 365
"""
from __future__ import annotations

import argparse
import csv
import json
import lzma
import struct
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '.local' / 'history'
CACHE = ROOT / '.local' / 'dukascopy'
URL = 'https://datafeed.dukascopy.com/datafeed'
RECORD = struct.Struct('>IIIIIf')          # seconds from file start, open, close, low, high, volume
SCALE = {'XAUUSD': 1000, 'XAGUSD': 1000, 'BTCUSD': 10, 'ETHUSD': 10}   # integer price -> price; FX default below
WARMUP_DAYS = {'m15': 5, 'h4': 120, 'd1': 400, 'w1': 900}            # same as pull_history.py
PERIOD = {'m15': 900, 'h4': 14400, 'd1': 86400}
WEEK, SUNDAY = 604800, 3 * 86400            # 1970-01-04 (epoch + 3 days) was a Sunday


def fetch(path: str, retries: int = 10) -> bytes:
    """Return the decompressed file at datafeed/<path>, cached on disk; b'' when Dukascopy has no data."""
    cached = CACHE / path
    if cached.exists():
        raw = cached.read_bytes()
    else:
        request = urllib.request.Request(f'{URL}/{path}', headers={'User-Agent': 'Mozilla/5.0'})
        for attempt in range(retries):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    raw = b''
                    break
                if attempt == retries - 1:
                    raise SystemExit(f'Dukascopy keeps refusing {path} (HTTP {error.code}); rerun later - '
                                     'finished files are cached')
            except (urllib.error.URLError, TimeoutError) as error:
                if attempt == retries - 1:
                    raise SystemExit(f'cannot reach Dukascopy for {path}: {error}')
            time.sleep(min(30, 1.5 ** attempt))
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(raw)
    return lzma.decompress(raw) if raw else b''


def candles(path: str, base: int, scale: float) -> list[dict]:
    """Decode one candle file; drop the flat zero-volume bars Dukascopy fills closed-market minutes with."""
    data = fetch(path)
    out = []
    for offset, o, c, lo, hi, volume in RECORD.iter_unpack(data):
        if volume > 0:
            out.append({'t': base + offset, 'o': o / scale, 'h': hi / scale, 'l': lo / scale, 'c': c / scale})
    return out


def day_path(instrument: str, day: date, side: str) -> str:
    return f'{instrument}/{day.year}/{day.month - 1:02d}/{day.day:02d}/{side}_candles_min_1.bi5'   # month is 0-based


def epoch(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def minute_bars(instrument: str, day: date, scale: float) -> list[dict]:
    bid = candles(day_path(instrument, day, 'BID'), epoch(day), scale)
    ask = {b['t']: b['o'] for b in candles(day_path(instrument, day, 'ASK'), epoch(day), scale)}
    for b in bid:
        b['spread'] = round(max(0.0, ask.get(b['t'], b['o']) - b['o']), 8)
    return bid


def hour_bars(instrument: str, month: date, scale: float) -> list[dict]:
    bars = candles(f'{instrument}/{month.year}/{month.month - 1:02d}/BID_candles_hour_1.bi5', epoch(month), scale)
    for b in bars:
        b['spread'] = 0.0
    return bars


def aggregate(bars: list[dict], bucket) -> list[dict]:
    out: list[dict] = []
    for b in bars:
        t = bucket(b['t'])
        if out and out[-1]['t'] == t:
            last = out[-1]
            last['h'], last['l'], last['c'] = max(last['h'], b['h']), min(last['l'], b['l']), b['c']
        else:
            out.append({'t': t, 'o': b['o'], 'h': b['h'], 'l': b['l'], 'c': b['c'], 'spread': b['spread']})
    return out


def write(path: Path, bars: list[dict]) -> None:
    with path.open('w', newline='') as handle:
        out = csv.writer(handle)
        out.writerow(['t', 'o', 'h', 'l', 'c', 'spread'])
        for b in bars:
            out.writerow([b['t'], b['o'], b['h'], b['l'], b['c'], b['spread']])


def months(first: date, last: date) -> list[date]:
    out, cursor = [], first.replace(day=1)
    while cursor <= last:
        out.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD', help='Dukascopy instrument, e.g. XAUUSD, EURUSD, BTCUSD')
    parser.add_argument('--days', type=int, default=365, help='how far back to pull (default 365)')
    parser.add_argument('--workers', type=int, default=4, help='parallel downloads (Dukascopy throttles above ~6)')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    scale = SCALE.get(symbol, 1000 if symbol.endswith('JPY') else 100000)
    end = datetime.now(timezone.utc).date()                     # today is incomplete: stop at yesterday
    start = end - timedelta(days=args.days)
    m1_days = [start - timedelta(days=WARMUP_DAYS['m15']) + timedelta(days=i)
               for i in range(args.days + WARMUP_DAYS['m15'])]
    context_months = [m for m in months(start - timedelta(days=WARMUP_DAYS['w1']), end)
                      if epoch(m) < epoch(m1_days[0])]

    jobs = [(minute_bars, d) for d in m1_days] + [(hour_bars, m) for m in context_months]
    done = 0

    def run(job):
        nonlocal done
        result = job[0](symbol, job[1], scale)
        done += 1
        if done % 25 == 0 or done == len(jobs):
            print(f'\r  {done}/{len(jobs)} files', end='', file=sys.stderr, flush=True)
        return result

    print(f'{symbol}: {len(m1_days)} days of M1 + {len(context_months)} months of H1 from Dukascopy', file=sys.stderr)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(run, jobs))
    print(file=sys.stderr)

    minute = [b for r in results[:len(m1_days)] for b in r]
    if not minute:
        raise SystemExit(f'Dukascopy returned no data for {symbol} - check the instrument name')
    m1_start = minute[0]['t'] - minute[0]['t'] % 3600
    hours = [b for r in results[len(m1_days):] for b in r if b['t'] < m1_start]
    hours += aggregate(minute, lambda t: t - t % 3600)

    frames = {'m1': [b for b in minute if b['t'] >= epoch(start)],
              'm15': aggregate(minute, lambda t: t - t % PERIOD['m15'])}
    for name in ('h4', 'd1'):
        frames[name] = aggregate(hours, lambda t, p=PERIOD[name]: t - t % p)
    frames['w1'] = aggregate(hours, lambda t: t - (t - SUNDAY) % WEEK)

    OUT.mkdir(parents=True, exist_ok=True)
    for name, bars in frames.items():
        since = epoch(start - timedelta(days=WARMUP_DAYS.get(name, 0)))
        bars = [b for b in bars if b['t'] >= since]
        path = OUT / f'{symbol}_{name}.csv'
        write(path, bars)
        first = datetime.fromtimestamp(bars[0]['t'], timezone.utc) if bars else None
        print(f'{name:>4}: {len(bars):>7} bars from {first:%Y-%m-%d} -> {path.relative_to(ROOT)}' if bars
              else f'{name:>4}: no bars')
    (OUT / f'{symbol}_meta.json').write_text(json.dumps(
        {'source': 'dukascopy', 'symbol': symbol, 'point': 1 / scale, 'digits': len(str(scale)) - 1,
         'pulled_at': int(time.time()), 'days': args.days}, indent=2))


if __name__ == '__main__':
    main()
