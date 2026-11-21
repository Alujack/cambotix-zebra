#!/usr/bin/env python3
"""Save Dukascopy history for scripts/backtest.py and ml/ - no MetaTrader needed (runs on the Mac).

Writes <SYMBOL>_{m1,m5,m15,h1,h4,d1,w1}.csv and <SYMBOL>_meta.json (the m1/m15/h4/d1/w1 files are the same shape
scripts/pull_history.py writes). M1 bars are Dukascopy BID minute candles with spread = ask open - bid open; the
other frames are built from them (plus Dukascopy hourly candles for the warm-up before the M1 range). Times are
UTC, D1 starts at 00:00 UTC and W1 on Sunday, like a GMT+0 MT5 server (Exness). Prices and spreads are
Dukascopy's, not your broker's, so results come close to an MT5 pull but are not identical.

Two ways to pick the range:
    --days 365                    the last year (default), written to .local/history/ like pull_history.py
    --from 2004-01-01 --out DIR   everything from that date, written year by year to DIR/years/ and merged;
                                  a rerun skips finished years and only fetches missing days

Downloads are cached in .local/dukascopy/, so a rerun only fetches what is missing. If Dukascopy refuses files
(it throttles with 503s) the affected year is not written and the merge is skipped; rerun the same command.
Standard library only:
    python3 scripts/pull_dukascopy.py --symbol XAUUSD --from 2004-01-01 --out .local/history_dukascopy_full
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import lzma
import struct
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / '.local' / 'history'
CACHE = ROOT / '.local' / 'dukascopy'
HOST = 'datafeed.dukascopy.com'          # files live at https://HOST/datafeed/<instrument>/<year>/<month-1>/...
RECORD = struct.Struct('>IIIIIf')          # seconds from file start, open, close, low, high, volume
SCALE = {'XAUUSD': 1000, 'XAGUSD': 1000, 'BTCUSD': 10, 'ETHUSD': 10}   # integer price -> price; FX default below
WARMUP_DAYS = {'m15': 5, 'h4': 120, 'd1': 400, 'w1': 900}            # same as pull_history.py
PERIOD = {'m5': 300, 'm15': 900, 'h1': 3600, 'h4': 14400, 'd1': 86400}
FRAMES = ('m1', 'm5', 'm15', 'h1', 'h4', 'd1', 'w1')
WEEK, SUNDAY = 604800, 3 * 86400            # 1970-01-04 (epoch + 3 days) was a Sunday
COLUMNS = ['t', 'o', 'h', 'l', 'c', 'spread']


class Refused(Exception):
    """Dukascopy did not serve a file after all retries (it throttles with 503s); a rerun picks it up."""


_local = threading.local()


def connection(fresh: bool = False) -> http.client.HTTPSConnection:
    """One keep-alive HTTPS connection per worker thread: a new TLS handshake per file is most of the latency."""
    if fresh or getattr(_local, 'conn', None) is None:
        if getattr(_local, 'conn', None) is not None:
            _local.conn.close()
        _local.conn = http.client.HTTPSConnection(HOST, timeout=60)
    return _local.conn


def fetch(path: str, retries: int = 40) -> bytes:
    """Return the decompressed file at datafeed/<path>, cached on disk; b'' when Dukascopy has no data.

    Dukascopy answers 503 from its load balancer when busy and drops connections when throttling; both are
    transient, so a file is retried many times with a short pause before it counts as refused."""
    cached = CACHE / path
    if cached.exists():
        raw = cached.read_bytes()
    else:
        fresh = False
        for attempt in range(retries):
            try:
                conn = connection(fresh)
                conn.request('GET', f'/datafeed/{path}', headers={'User-Agent': 'Mozilla/5.0'})
                response = conn.getresponse()
                raw = response.read()
                if response.status == 200:
                    break
                if response.status == 404:
                    raw = b''
                    break
                problem, fresh = f'HTTP {response.status}', response.status != 503
            except (http.client.HTTPException, TimeoutError, ConnectionError, OSError) as error:
                problem, fresh = f'{type(error).__name__}: {error}', True
            if attempt == retries - 1:
                raise Refused(f'{path}: {problem}')
            time.sleep(min(20.0, 1.0 + attempt * 0.5))
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


def minute_bars(instrument: str, day: date, scale: float, spread: float | None) -> list[dict]:
    bid = candles(day_path(instrument, day, 'BID'), epoch(day), scale)
    if spread is not None:                                  # fixed spread: no ASK download
        for b in bid:
            b['spread'] = spread
        return bid
    ask = {b['t']: b['o'] for b in candles(day_path(instrument, day, 'ASK'), epoch(day), scale)}
    for b in bid:
        b['spread'] = round(max(0.0, ask.get(b['t'], b['o']) - b['o']), 8)
    return bid


def hour_bars(instrument: str, month: date, scale: float, _spread=None) -> list[dict]:
    bars = candles(f'{instrument}/{month.year}/{month.month - 1:02d}/BID_candles_hour_1.bi5', epoch(month), scale)
    for b in bars:
        b['spread'] = 0.0
    return bars


def bucket_of(frame: str):
    if frame == 'w1':
        return lambda t: t - (t - SUNDAY) % WEEK
    return lambda t, p=PERIOD[frame]: t - t % p


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


def frames_from(minute: list[dict], context_hours: list[dict]) -> dict[str, list[dict]]:
    """All frames of one stretch of M1 (plus hourly candles from before it, for h4/d1/w1 warm-up)."""
    hours = context_hours + aggregate(minute, bucket_of('h1'))
    frames = {'m1': minute}
    for name in ('m5', 'm15', 'h1'):
        frames[name] = aggregate(minute, bucket_of(name))
    for name in ('h4', 'd1', 'w1'):
        frames[name] = aggregate(hours, bucket_of(name))
    return frames


def write(path: Path, bars: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        out = csv.writer(handle)
        out.writerow(COLUMNS)
        for b in bars:
            out.writerow([b['t'], b['o'], b['h'], b['l'], b['c'], b['spread']])


def read(path: Path):
    """Yield the rows of a CSV this script wrote, typed."""
    with path.open(newline='') as handle:
        for row in csv.DictReader(handle):
            yield {'t': int(row['t']), 'o': float(row['o']), 'h': float(row['h']), 'l': float(row['l']),
                   'c': float(row['c']), 'spread': float(row['spread'])}


def merge(parts: list[Path], out: Path) -> tuple[int, int | None, int | None]:
    """Concatenate yearly frame files in order; a bar split across two files (a W1 week over New Year) is joined.
    Returns (bars, first t, last t)."""
    out.parent.mkdir(parents=True, exist_ok=True)
    pending, count, first = None, 0, None
    with out.open('w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for part in parts:
            for row in read(part):
                if pending and row['t'] == pending['t']:
                    pending['h'] = max(pending['h'], row['h'])
                    pending['l'] = min(pending['l'], row['l'])
                    pending['c'] = row['c']
                    continue
                if pending:
                    writer.writerow([pending[k] for k in COLUMNS])
                    count += 1
                    first = pending['t'] if first is None else first
                pending = row
        if pending:
            writer.writerow([pending[k] for k in COLUMNS])
            count += 1
            first = pending['t'] if first is None else first
    return count, first, pending['t'] if pending else None


def months(first: date, last: date) -> list[date]:
    out, cursor = [], first.replace(day=1)
    while cursor <= last:
        out.append(cursor)
        cursor = (cursor + timedelta(days=32)).replace(day=1)
    return out


def download(symbol: str, jobs: list, scale: float, spread: float | None, workers: int, label: str):
    """Run (function, day-or-month) jobs in parallel; returns the results in order and the refused paths."""
    done, failed = 0, []

    def run(job):
        nonlocal done
        try:
            result = job[0](symbol, job[1], scale, spread)
        except Refused as error:
            failed.append(str(error))
            result = []
        done += 1
        if done % 50 == 0 or done == len(jobs):
            print(f'  {label}: {done}/{len(jobs)} files, {len(failed)} refused', file=sys.stderr, flush=True)
        return result

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run, jobs))
    return results, failed


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD', help='Dukascopy instrument, e.g. XAUUSD, EURUSD, BTCUSD')
    parser.add_argument('--days', type=int, default=365, help='how far back to pull (default 365)')
    parser.add_argument('--from', dest='start', type=date.fromisoformat, metavar='YYYY-MM-DD',
                        help='pull everything from this date instead of --days (year by year, resumable)')
    parser.add_argument('--to', dest='end', type=date.fromisoformat, metavar='YYYY-MM-DD',
                        help='last day to pull (default: yesterday, today is incomplete)')
    parser.add_argument('--out', type=Path, default=OUT, help=f'output folder (default {OUT.relative_to(ROOT)})')
    parser.add_argument('--workers', type=int, default=2, help='parallel downloads (Dukascopy throttles with 503s)')
    parser.add_argument('--spread', type=float, metavar='PRICE',
                        help='use this fixed spread (e.g. 0.20) instead of downloading ASK candles - half the files')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    scale = SCALE.get(symbol, 1000 if symbol.endswith('JPY') else 100000)
    weekends = symbol in ('BTCUSD', 'ETHUSD')                   # everything else is shut all Saturday
    end = args.end or datetime.now(timezone.utc).date() - timedelta(days=1)
    by_years = args.start is not None
    start = args.start or end - timedelta(days=args.days)
    warmup = 0 if by_years else WARMUP_DAYS['m15']               # --days keeps a few days of M1 before the range
    first_day = start - timedelta(days=warmup)
    days = [first_day + timedelta(days=i) for i in range((end - first_day).days + 1)]
    days = [d for d in days if weekends or d.weekday() != 5]
    context_months = [m for m in months(start - timedelta(days=WARMUP_DAYS['w1']), end) if epoch(m) < epoch(days[0])]
    out: Path = args.out if args.out.is_absolute() else ROOT / args.out
    years_dir = out / 'years'
    pulled_at = int(time.time())

    years = sorted({d.year for d in days})
    print(f'{symbol}: {len(days)} days of M1 ({days[0]} .. {days[-1]}) + {len(context_months)} months of H1 from '
          f'Dukascopy -> {out}', file=sys.stderr)
    hours, _ = download(symbol, [(hour_bars, m) for m in context_months], scale, args.spread, args.workers, 'H1 warm-up')
    context_hours = [b for r in hours for b in r]

    refused: dict[int, int] = {}
    for year in years:
        year_days = [d for d in days if d.year == year]
        complete = year < end.year and all((years_dir / f'{symbol}_{f}_{year}.csv').exists() for f in FRAMES)
        if by_years and complete:
            print(f'  {year}: already written, skipped', file=sys.stderr)
            context_hours = []                                  # the warm-up is already in that year's files
            continue
        results, failed = download(symbol, [(minute_bars, d) for d in year_days], scale, args.spread, args.workers,
                                   str(year))
        if failed:
            refused[year] = len(failed)
            print(f'  {year}: {len(failed)} files refused (first: {failed[0]}); year not written', file=sys.stderr)
            continue
        minute = [b for r in results for b in r]
        if not minute:
            print(f'  {year}: Dukascopy has no {symbol} data', file=sys.stderr)
        m1_start = minute[0]['t'] - minute[0]['t'] % 3600 if minute else epoch(year_days[0])
        frames = frames_from(minute, [b for b in context_hours if b['t'] < m1_start])
        context_hours = []                                      # only the first stretch gets the warm-up
        for name, bars in frames.items():
            write(years_dir / f'{symbol}_{name}_{year}.csv', bars)
        print(f'  {year}: {len(minute)} M1 bars', file=sys.stderr)

    if refused:
        raise SystemExit(f'{sum(refused.values())} files refused by Dukascopy in {sorted(refused)}. Merge skipped; '
                         'rerun the same command - the other files are cached, only these get fetched again.')

    meta = {'source': 'dukascopy', 'symbol': symbol, 'point': 1 / scale, 'digits': len(str(scale)) - 1,
            'pulled_at': pulled_at, 'from': str(start), 'to': str(end), 'years': years, 'frames': {}}
    if not by_years:
        meta['days'] = args.days
    for name in FRAMES:
        parts = [p for p in (years_dir / f'{symbol}_{name}_{y}.csv' for y in years) if p.exists()]
        path = out / f'{symbol}_{name}.csv'
        if by_years:
            count, first, last = merge(parts, path)
        else:                                                   # one year or two: trim the warm-up like before
            since = epoch(start - timedelta(days=WARMUP_DAYS.get(name, 0)))
            bars = [b for p in parts for b in read(p)]
            if name != 'm1':
                bars = aggregate(bars, bucket_of(name))
            bars = [b for b in bars if b['t'] >= since]
            write(path, bars)
            count, first, last = len(bars), bars[0]['t'] if bars else None, bars[-1]['t'] if bars else None
        meta['frames'][name] = {'bars': count, 'first': first, 'last': last}
        shown = datetime.fromtimestamp(first, timezone.utc) if first else None
        where = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
        print(f'{name:>4}: {count:>8} bars from {shown:%Y-%m-%d} -> {where}' if first else f'{name:>4}: no bars')
    if not by_years:
        for p in years_dir.glob(f'{symbol}_*'):
            p.unlink()
        if years_dir.exists() and not any(years_dir.iterdir()):
            years_dir.rmdir()
    (out / f'{symbol}_meta.json').write_text(json.dumps(meta, indent=2))


if __name__ == '__main__':
    main()
