"""Public record API for the Next.js site: no authentication, read-only transactions, 60-second cache.

It exposes only what the public record shows. Open plans are listed without their levels (entry, stop,
targets): a live level is the product, the graded outcome is the proof. Everything a visitor sees here is
computed by the same `app.ledger` code that writes the Telegram digest, so the site and the messages agree.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query

from app import ledger, news
from app.db import readonly
from app.domain import SYNTHETIC_PREFIXES

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


def plan_view(seq: int, plan: dict, events: list[dict]) -> dict:
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
    return view


def build_signals(limit: int) -> list[dict]:
    with readonly() as conn:
        rows = conn.execute('''SELECT seq, event_id, kind, body FROM ledger WHERE event_id IN
            (SELECT event_id FROM ledger WHERE kind='published' ORDER BY seq DESC LIMIT %s) ORDER BY seq''',
                            (limit,)).fetchall()
    plans, events = {}, {}
    for row in rows:
        body = json.loads(row['body'])
        if row['kind'] == 'published':
            plans[row['event_id']] = (row['seq'], body)
        else:
            events.setdefault(row['event_id'], []).append(body)
    views = [plan_view(seq, plan, events.get(event_id, [])) for event_id, (seq, plan) in plans.items()]
    return sorted(views, key=lambda item: -item['seq'])


def build_tickers() -> list[dict]:
    with readonly() as conn:
        latest = conn.execute('SELECT DISTINCT ON (symbol) symbol, t, c FROM candles ORDER BY symbol, t DESC').fetchall()
        out = []
        for row in latest:
            earlier = conn.execute('SELECT c FROM candles WHERE symbol=%s AND t <= %s ORDER BY t DESC LIMIT 1',
                                   (row['symbol'], row['t'] - 86400)).fetchone()
            change = (row['c'] / earlier['c'] - 1) * 100 if earlier and earlier['c'] else None
            out.append({'symbol': row['symbol'], 'price': row['c'], 'time': row['t'] + 60,
                        'change_24h_pct': round(change, 2) if change is not None else None,
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
    plan = json.loads(rows[0]['body'])
    return plan_view(seq, plan, [json.loads(row['body']) for row in rows[1:]])


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
        if event['time'] < now - 86400 or event['time'] > now + 7 * 86400:
            continue
        severity = {'High': 'HIGH', 'Medium': 'MEDIUM'}.get(event['impact'], 'LOW')
        items.append({'time': int(event['time']), 'title': event['title'], 'country': event['country'], 'severity': severity,
                      'affects': ['XAUUSD', 'EURUSD'] if event['country'] in ('USD', 'EUR') else [],
                      'blocks_setups': severity == 'HIGH' and event['country'] in currencies})
    return items[:40]


@app.get('/news')
def news_feed():
    return cached('news', build_news)


@app.get('/tickers')
def tickers():
    return cached('tickers', build_tickers)


@app.get('/ledger')
def ledger_rows(after: int = Query(0, ge=0)):
    """Raw chain rows for anyone who wants to verify the record themselves."""
    with readonly() as conn:
        return ledger.rows(conn, after=after, limit=5000)
