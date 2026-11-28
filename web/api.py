"""Public record API for the Next.js site: no authentication, read-only transactions, 60-second cache.

It exposes only what the public record shows. Open plans are listed without their levels (entry, stop,
targets): a live level is the product, the graded outcome is the proof. Everything a visitor sees here is
computed by the same `app.ledger` code that writes the Telegram digest, so the site and the messages agree.

`/stream` is the one live endpoint: the broker's latest tick and current minute bar per symbol, as Server-Sent
Events. One poller reads the `quotes` table for every listener, so visitors add no database load.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone

import psycopg
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from app import ledger, news
from app.db import connect, readonly
from app.domain import SYNTHETIC_PREFIXES
from web import setups as setups_engine
from web import trend as trend_engine
from web.indicators import aggregate, snapshot

app = FastAPI(title='Cambotix Zebra — public record', docs_url=None, redoc_url=None)
TERMINAL = ('closed', 'not_filled')
_cache: dict[str, tuple[float, object]] = {}
_lock = threading.Lock()


def cached(key: str, build):
    seconds = int(os.getenv('WEB_CACHE_SECONDS', '60'))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < seconds:
            return hit[1]
    value = build()
    with _lock:
        _cache[key] = (now, value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def journal(conn) -> dict:
    """How many real setups the rules have seen and what became of them; synthetic test traffic is excluded."""
    counts = {row['status']: row['n'] for row in conn.execute(
        'SELECT status, count(*) AS n FROM signals WHERE NOT (lower(event_id) LIKE ANY(%s)) GROUP BY status',
        ([prefix + '%' for prefix in SYNTHETIC_PREFIXES],))}
    return {'evaluated': sum(counts.values()), 'approved': counts.get('approved', 0),
            'rejected': counts.get('rejected', 0), 'pending': counts.get('queued', 0) + counts.get('processing', 0)}


def build_record() -> dict:
    with readonly() as conn:
        record = ledger.track_record(conn)
        record['journal'] = journal(conn)
    record['generated_at'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    return record


def plan_view(seq: int, plan: dict, events: list[dict], notes: dict | None = None) -> dict:
    last = events[-1] if events else None
    status = last['kind'] if last and last['kind'] in TERMINAL else 'open'
    view = {'seq': seq, 'event_id': plan['event_id'], 'symbol': plan['symbol'], 'model': plan['model'],
            'timeframe': plan['timeframe'], 'direction': plan['direction'], 'session': plan.get('session'),
            'cautions': plan.get('cautions', []), 'published_at': plan['published_at'], 'status': status,
            'entry_type': plan.get('entry_type'), 'levels_public': status != 'open',
            'entry_expiry_minutes': plan.get('entry_expiry_minutes', 0), 'max_hold_minutes': plan.get('max_hold_minutes', 0),
            # A limit plan is cancelled at expires_at if unfilled; any plan is closed at market by hold_until at the latest.
            'expires_at': plan['published_at'] + 60 * plan.get('entry_expiry_minutes', 0),
            'hold_until': plan['published_at'] + 60 * (plan.get('entry_expiry_minutes', 0) + plan.get('max_hold_minutes', 0)),
            'events': [{k: v for k, v in event.items() if k not in ('seq', 'event_id', 'prev')} for event in events]}
    if status != 'open':
        view['levels'] = {'entry': plan['entry'], 'stop': plan['stop'], 'targets': plan['targets']}
    if status == 'closed':
        view['result'] = {k: last[k] for k in ('exit', 'targets_hit', 'ambiguous', 'r_tp1', 'r_scaled')}
    elif status == 'not_filled':
        view['result'] = {'reason': last['reason']}
    # AI explanations (commentary, never part of the record). The plan note is written without prices, so it is
    # public from the start; the result review only once the plan has closed.
    notes = notes or {}
    view['ai'] = {'plan': notes.get('plan'), 'result': notes.get('result') if status == 'closed' else None,
                  'model': notes.get('model')}
    return view


def ai_notes(conn, event_ids: list[str]) -> dict[str, dict]:
    """{event_id: {'plan': text, 'result': text, 'model': name}}; empty when the analyzer has not created the table yet."""
    if not event_ids or conn.execute("SELECT to_regclass('ai_notes') AS t").fetchone()['t'] is None:
        return {}
    found: dict[str, dict] = {}
    for row in conn.execute('SELECT event_id, kind, note, model FROM ai_notes WHERE event_id = ANY(%s)', (event_ids,)):
        found.setdefault(row['event_id'], {})[row['kind']] = row['note']
        found[row['event_id']]['model'] = row['model']
    return found


def build_signals(limit: int) -> list[dict]:
    with readonly() as conn:
        rows = conn.execute('''SELECT seq, event_id, kind, body FROM ledger WHERE event_id IN
            (SELECT event_id FROM ledger WHERE kind='published' ORDER BY seq DESC LIMIT %s) ORDER BY seq''',
                            (limit,)).fetchall()
        notes = ai_notes(conn, list({row['event_id'] for row in rows}))
    plans, events = {}, {}
    for row in rows:
        body = json.loads(row['body'])
        if row['kind'] == 'published':
            plans[row['event_id']] = (row['seq'], body)
        else:
            events.setdefault(row['event_id'], []).append(body)
    views = [plan_view(seq, plan, events.get(event_id, []), notes.get(event_id)) for event_id, (seq, plan) in plans.items()]
    return sorted(views, key=lambda item: -item['seq'])


def build_tickers() -> list[dict]:
    with readonly() as conn:
        # One primary-key lookup per configured symbol: DISTINCT ON over the whole table scans every stored candle
        # (millions once history is backfilled) and hits the read-only statement timeout.
        latest = [row for symbol in sorted(allowed()) if (row := conn.execute(
            'SELECT symbol, t, c FROM candles WHERE symbol=%s ORDER BY t DESC LIMIT 1', (symbol,)).fetchone())]
        out = []
        for row in latest:
            earlier = conn.execute('SELECT c FROM candles WHERE symbol=%s AND t <= %s ORDER BY t DESC LIMIT 1',
                                   (row['symbol'], row['t'] - 86400)).fetchone()
            change = (row['c'] / earlier['c'] - 1) * 100 if earlier and earlier['c'] else None
            out.append({'symbol': row['symbol'], 'price': row['c'], 'time': row['t'] + 60,
                        'change_24h_pct': round(change, 2) if change is not None else None,
                        # The close 24 h earlier, so the site can recompute the change on every live tick.
                        'price_24h': earlier['c'] if earlier else None,
                        'source': 'broker M1 close, about 1 minute delayed'})
    return out


@app.get('/health')
def health():
    with readonly() as conn:
        conn.execute('SELECT 1')
    return {'status': 'ok'}


@app.get('/record')
def record():
    return cached('record', build_record)


@app.get('/signals')
def signals(limit: int = Query(60, ge=1, le=200)):
    return cached(f'signals:{limit}', lambda: build_signals(limit))


def build_plan(seq: int) -> dict | None:
    with readonly() as conn:
        head = conn.execute("SELECT event_id FROM ledger WHERE seq=%s AND kind='published'", (seq,)).fetchone()
        if not head:
            return None
        rows = conn.execute('SELECT seq, kind, body FROM ledger WHERE event_id=%s ORDER BY seq', (head['event_id'],)).fetchall()
        notes = ai_notes(conn, [head['event_id']])
    plan = json.loads(rows[0]['body'])
    return plan_view(seq, plan, [json.loads(row['body']) for row in rows[1:]], notes.get(head['event_id']))


@app.get('/signals/{seq}')
def signal(seq: int):
    """One published plan by its ledger number, with the same redaction as the list."""
    view = cached(f'plan:{seq}', lambda: build_plan(seq))
    if view is None:
        raise HTTPException(404, 'No published plan with that ledger number')
    return view


def build_news() -> list[dict]:
    """The economic calendar the rules already use, as a feed: severity from impact, no invented trade ideas."""
    events = news._load() or []
    currencies = {c.strip().upper() for c in os.getenv('NEWS_CURRENCIES', 'USD').split(',') if c.strip()}
    now = time.time()
    items = []
    for event in sorted(events, key=lambda item: item['time']):
        if event['time'] < now - 6 * 3600 or event['time'] > now + 7 * 86400:
            continue
        severity = {'High': 'HIGH', 'Medium': 'MEDIUM'}.get(event['impact'], 'LOW')
        if severity == 'LOW':
            continue   # the feed is for events that can move price; low-impact noise stays out
        items.append({'time': int(event['time']), 'title': event['title'], 'country': event['country'], 'severity': severity,
                      'affects': ['XAUUSD', 'EURUSD'] if event['country'] in ('USD', 'EUR') else [],
                      'blocks_setups': severity == 'HIGH' and event['country'] in currencies})
    return items[:40]


@app.get('/news')
def news_feed():
    return cached('news', build_news)


FEAR_GREED_URL = 'https://api.alternative.me/fng/?limit=1'


def build_sentiment() -> dict:
    """Crypto Fear & Greed index (alternative.me, daily, 0-100). Null when the source is down; nothing is estimated."""
    try:
        request = urllib.request.Request(FEAR_GREED_URL, headers={'User-Agent': 'zebra-web/1.0'})
        with urllib.request.urlopen(request, timeout=5) as response:
            row = json.load(response)['data'][0]
        return {'crypto_fear_greed': {'value': int(row['value']), 'label': row['value_classification'],
                                      'time': int(row['timestamp']), 'source': 'alternative.me'}}
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return {'crypto_fear_greed': None}


@app.get('/sentiment')
def sentiment():
    return cached('sentiment', build_sentiment)


TIMEFRAMES = {'1m': 60, '5m': 300, '15m': 900, '30m': 1800, '1h': 3600, '4h': 14400, '1d': 86400}


def load_m1(symbol: str, start: int, end: int) -> list[dict]:
    with readonly() as conn:
        return conn.execute('SELECT t, o, h, l, c FROM candles WHERE symbol=%s AND t>=%s AND t<%s ORDER BY t',
                            (symbol, start, end)).fetchall()


def load_bars(symbol: str, start: int, end: int, seconds: int) -> list[dict]:
    """Stored M1 bucketed into epoch-aligned bars in the database (same result as aggregate(load_m1(...))), so a
    daily or 4h chart does not pull hundreds of thousands of M1 rows into Python."""
    with readonly() as conn:
        return conn.execute('''SELECT t - t %% %s AS t, (array_agg(o ORDER BY t))[1] AS o, max(h) AS h, min(l) AS l,
            (array_agg(c ORDER BY t DESC))[1] AS c, count(*)::int AS n
            FROM candles WHERE symbol=%s AND t>=%s AND t<%s GROUP BY 1 ORDER BY 1''',
                            (seconds, symbol, start, end)).fetchall()


@app.get('/candles/{symbol}')
def candles(symbol: str, tf: str = Query('15m'), to: int | None = None, bars: int = Query(300, ge=20, le=1500)):
    """Broker candles aggregated from stored M1, ending at `to` (default: latest). Same data the grader uses."""
    if tf not in TIMEFRAMES or symbol not in allowed():
        raise HTTPException(404, 'Unknown symbol or timeframe')
    seconds = TIMEFRAMES[tf]
    end = (to or int(time.time())) // 60 * 60
    start = end - bars * seconds

    def build():
        out = load_bars(symbol.upper(), start, end, seconds)
        return {'symbol': symbol.upper(), 'tf': tf, 'candles': out[-bars:]}
    return cached(f'candles:{symbol}:{tf}:{end}:{bars}', build)


@app.get('/indicators/{symbol}')
def indicators(symbol: str, tf: str = Query('15m'), at: int | None = None):
    """Indicator readings with code-derived verdicts on the bar containing `at` (default: now)."""
    if tf not in TIMEFRAMES or symbol not in allowed():
        raise HTTPException(404, 'Unknown symbol or timeframe')
    seconds = TIMEFRAMES[tf]
    end = ((at or int(time.time())) // seconds + 1) * seconds

    def build():
        bars = load_bars(symbol.upper(), end - 260 * seconds, end, seconds)
        reading = snapshot(bars)
        if reading is None:
            raise HTTPException(404, 'Not enough broker candles for this symbol yet')
        return {'symbol': symbol.upper(), 'tf': tf, **reading}
    return cached(f'indicators:{symbol}:{tf}:{end}', build)


@app.get('/setups/{symbol}')
def setups(symbol: str, to: int | None = None, bars: int = Query(300, ge=20, le=1500)):
    """Our own indicator (tradingview/gold_setups.pine) on the broker's candles: classic 15m setup candidates with
    the analyzer's levels, and the rule table on the last closed 15m bar. Indicator output, not published plans."""
    if symbol.upper() not in allowed():
        raise HTTPException(404, 'Unknown symbol')
    symbol = symbol.upper()
    end = (to or int(time.time())) // 60 * 60

    def build():
        rows = load_m1(symbol, end - (bars + setups_engine.WARMUP) * setups_engine.BAR, end)
        closed = setups_engine.closed_bars(aggregate(rows, setups_engine.BAR), rows[-1]['t'] if rows else None)
        return setups_engine.build(symbol, closed, bars)
    return cached(f'setups:{symbol}:{end}:{bars}', build)


@app.get('/trend/{symbol}')
def trend(symbol: str, tf: str = Query('5m'), to: int | None = None, bars: int = Query(300, ge=20, le=1500)):
    """The ATR Trend Confluence System (tradingview/atr_trend_confluence.pine) on the broker's candles, on the chart's
    timeframe: baseline and trailing-stop lines, every stop flip with what blocked it, and the filtered BUY/SELL
    labels. An untested indicator prototype: nothing here is a published plan."""
    if tf not in TIMEFRAMES or symbol.upper() not in allowed():
        raise HTTPException(404, 'Unknown symbol or timeframe')
    symbol, seconds = symbol.upper(), TIMEFRAMES[tf]
    end = (to or int(time.time())) // 60 * 60
    # Warmup for the chart bars and for the 1h filter, capped so a daily chart never loads years of M1 rows.
    start = end - min(max((bars + trend_engine.WARMUP) * seconds, trend_engine.HTF_HISTORY), 45 * 86400)
    return cached(f'trend:{symbol}:{tf}:{end}:{bars}',
                  lambda: trend_engine.build(symbol, tf, load_m1(symbol, start, end), seconds, bars))


def allowed() -> set[str]:
    return {s.strip().upper() for s in os.getenv('SYMBOLS', 'XAUUSD').split(',') if s.strip()}


@app.get('/tickers')
def tickers():
    return cached('tickers', build_tickers)


@app.get('/ledger')
def ledger_rows(after: int = Query(0, ge=0)):
    """Raw chain rows for anyone who wants to verify the record themselves."""
    with readonly() as conn:
        return ledger.rows(conn, after=after, limit=5000)


# -- live quotes --------------------------------------------------------------
POLL_SECONDS = 0.25
HEARTBEAT_SECONDS = 15        # well inside the Cloudflare tunnel's 100 s idle limit


def read_quotes(conn) -> dict[str, dict]:
    """Latest tick and current minute bar per public symbol. Empty until the analyzer has created the table."""
    try:
        rows = conn.execute('SELECT symbol, bid, ask, tick_ms, minute, o, h, l, c FROM quotes WHERE symbol = ANY(%s)',
                            (sorted(allowed()),)).fetchall()
    except psycopg.errors.UndefinedTable:
        return {}
    return {row['symbol']: {'symbol': row['symbol'], 'bid': row['bid'], 'ask': row['ask'], 'time_ms': row['tick_ms'],
                            'bar': {'t': row['minute'], 'o': row['o'], 'h': row['h'], 'l': row['l'], 'c': row['c']}}
            for row in rows}


class QuoteHub:
    """Reads `quotes` every 250 ms while anyone is listening and hands each changed quote to every listener."""

    def __init__(self) -> None:
        self.listeners: set[asyncio.Queue] = set()
        self.latest: dict[str, dict] = {}
        self.task: asyncio.Task | None = None
        self.conn: psycopg.Connection | None = None

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self.listeners.add(queue)
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    def read(self) -> dict[str, dict]:
        """Runs in a worker thread. One connection, kept open while the poller runs and read-only for its lifetime."""
        if self.conn is None or self.conn.closed:
            self.conn = connect()
            self.conn.autocommit = True
            self.conn.execute('SET default_transaction_read_only = on')
        try:
            return read_quotes(self.conn)
        except psycopg.Error:
            self.close()
            raise

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        try:
            while self.listeners:
                started = loop.time()
                try:
                    current = await asyncio.to_thread(self.read)
                except psycopg.Error:
                    await asyncio.sleep(1)          # database restarting: listeners keep their last quote
                    continue
                for symbol, quote in current.items():
                    if self.latest.get(symbol) != quote:
                        self.latest[symbol] = quote
                        self.publish(quote)
                await asyncio.sleep(max(0.0, POLL_SECONDS - (loop.time() - started)))
        finally:
            self.close()

    def publish(self, quote: dict) -> None:
        for queue in list(self.listeners):
            try:
                queue.put_nowait(quote)
            except asyncio.QueueFull:
                pass                                # a stalled browser skips a step; the next quote carries the whole bar


hub = QuoteHub()


def sse(quote: dict) -> str:
    return f'data: {json.dumps(quote, separators=(",", ":"))}\n\n'


async def quote_events(source: QuoteHub):
    """The SSE body: the current quote for every symbol, then each change, with a comment line as heartbeat."""
    queue = source.subscribe()
    try:
        # Nothing awaits between subscribing and copying `latest`, so no change can fall between the two.
        current = list(source.latest.values())
        yield 'retry: 3000\n\n'
        for quote in current:
            yield sse(quote)
        while True:
            try:
                quote = await asyncio.wait_for(queue.get(), HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield ': ping\n\n'
                continue
            yield sse(quote)
    finally:
        source.unsubscribe(queue)


@app.get('/stream')
async def stream():
    if len(hub.listeners) >= int(os.getenv('STREAM_MAX_LISTENERS', '500')):
        raise HTTPException(503, 'Too many live listeners; retry shortly')
    # no-transform keeps Next.js and any proxy from compressing (and so buffering) the stream.
    return StreamingResponse(quote_events(hub), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no'})


@app.get('/quotes')
def quotes_snapshot():
    """The same quotes as /stream, once, for server-rendered pages. Never cached: it is the live price."""
    with readonly() as conn:
        return list(read_quotes(conn).values())
