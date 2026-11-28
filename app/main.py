import hmac
import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import ledger, quotes
from app.agent import jobs, worker
from app.agent.telegram import deliver
from app.ai import tables as ai_tables
from app.ai.ollama import LocalAIError
from app.ai.review import classify
from app.db import database
from app.domain import (Analysis, Signal, allowed_symbols, cautions, freshness, gate_mode, notification_text, outcome,
                        synthetic, technical_rules)
from app.grader import simulate
from app.outbox import queue_message, telegram_enabled


@asynccontextmanager
async def lifespan(_):
    with database() as conn:
        ledger.migrate(conn)
        ai_tables.migrate(conn)
        quotes.migrate(conn)
    yield


app = FastAPI(title='Cambotix Zebra — signal analyzer', docs_url=None, redoc_url=None, lifespan=lifespan)


def authorize(x_zebra_token: Annotated[str | None, Header()] = None):
    expected = os.environ.get('ANALYZER_TOKEN', '')
    if not expected or not x_zebra_token or not hmac.compare_digest(expected, x_zebra_token):
        raise HTTPException(401, 'Unauthorized')


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Database unavailable; retry later'})


@app.get('/health')
def health():
    with database() as conn:
        conn.execute('SELECT 1')
    return {'status': 'ok', 'mode': 'manual_review', 'gate': gate_mode(), 'execution_enabled': False,
            'agent_enabled': worker.enabled()}


@app.post('/signals', dependencies=[Depends(authorize)])
async def ingest(request: Request):
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, 'Payload too large')
    try:
        signal = Signal.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, 'Invalid signal payload')
    if not freshness(signal):
        raise HTTPException(422, 'Signal must be a recent closed bar (Unix seconds)')
    payload = signal.model_dump()
    with database() as conn:
        inserted = conn.execute('''INSERT INTO signals(event_id, symbol, timeframe, bar_time, signal, payload)
          VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id''',
          (signal.event_id, signal.symbol, signal.timeframe, signal.bar_time, signal.signal, Jsonb(payload))).fetchone()
        if not inserted:
            existing = conn.execute('''SELECT event_id, payload FROM signals WHERE event_id=%s OR
              (symbol=%s AND timeframe=%s AND bar_time=%s AND signal=%s)''',
              (signal.event_id, signal.symbol, signal.timeframe, signal.bar_time, signal.signal)).fetchall()
            matches = [row for row in existing if {k: v for k, v in row['payload'].items() if k != 'event_id'} ==
                       {k: v for k, v in payload.items() if k != 'event_id'}]
            if len(existing) != 1 or len(matches) != 1:
                raise HTTPException(409, 'Event identity conflicts with stored signal')
            return JSONResponse(status_code=200, content={'status': 'duplicate', 'event_id': matches[0]['event_id']})
    return JSONResponse(status_code=202, content={'status': 'queued', 'event_id': signal.event_id})


def community_chat() -> str:
    """Group or channel that also receives real approved signals and their results ('' = none)."""
    return os.getenv('TELEGRAM_COMMUNITY_CHAT_ID', '').strip()


def finish(signal: Signal, status: str, analysis: Analysis | None, reasons: list[str], error_code=None):
    data = analysis.model_dump() if analysis else None
    with database() as conn:
        conn.execute('''UPDATE signals SET status=%s, analysis=%s, rule_reasons=%s,
            completed_at=now(), error_code=%s WHERE event_id=%s''',
            (status, Jsonb(data), Jsonb(reasons), error_code, signal.event_id))
        seq, warnings = None, []
        if status == 'approved':
            warnings = cautions(signal) + ledger.history_cautions(conn, signal)
        if status == 'approved' and not synthetic(signal.event_id):
            # Published in the same transaction as the approval: an approved setup is always on the record.
            now = int(time.time())
            seq, _ = ledger.append(conn, signal.event_id, 'published', now, ledger.plan_record(signal, now, warnings))
        if seq is not None and jobs.plan_notes_enabled():
            # The website's plain-language explanation, written later by the agent worker like every other note.
            jobs.enqueue(conn, 'plan_note', signal.event_id)
        if status == 'approved' and analysis is None and gate_mode() == 'rules' and jobs.signal_notes_enabled():
            # Commentary is written after the alert by the agent worker: a slow or offline model never delays it.
            jobs.enqueue(conn, 'signal_note', signal.event_id)
        conn.execute('''INSERT INTO notifications(event_id,message,status) VALUES (%s,%s,%s)
            ON CONFLICT DO NOTHING''', (signal.event_id, notification_text(signal, status, data, reasons, ledger_seq=seq,
                                                                         warnings=warnings),
                                        'pending' if telegram_enabled() else 'disabled'))
        if seq is not None and community_chat():
            # Only real, approved, recorded setups reach the community; tests and rejections stay private.
            queue_message(conn, f'community:signal:{signal.event_id}', 'signal', 'community',
                          notification_text(signal, status, data, reasons, ledger_seq=seq, warnings=warnings,
                                            audience='community'))


@app.post('/process', dependencies=[Depends(authorize)])
def process():
    # Session-level lock prevents overlapping n8n schedules from running concurrent models.
    with database() as guard:
        guard.autocommit = True
        if not guard.execute('SELECT pg_try_advisory_lock(914207) AS acquired').fetchone()['acquired']:
            return {'status': 'busy'}
        try:
            with database() as conn:
                # The lock proves no other processor is running; recover a process killed after claim.
                conn.execute("UPDATE signals SET status='queued' WHERE status='processing'")
                row = conn.execute('''UPDATE signals SET status='processing', started_at=now(), attempts=attempts+1
                  WHERE event_id=(SELECT event_id FROM signals WHERE status='queued' AND next_attempt_at<=now()
                    ORDER BY received_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''').fetchone()
            if not row:
                return {'status': 'idle'}
            signal = Signal.model_validate(row['payload'])
            reasons = technical_rules(signal)
            limit = int(os.getenv('MAX_OPEN_SAME_DIRECTION', '1'))
            if not reasons and limit > 0 and not synthetic(signal.event_id):
                # One idea, one plan: a second entry in the same direction from the same model doubles the same bet.
                direction = 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL'
                with database() as conn:
                    if ledger.open_count(conn, signal.symbol, direction, time.time(), signal.model) >= limit:
                        reasons = ['open_plan_same_direction']
            if reasons:
                finish(signal, 'rejected', None, reasons)
                return {'status': 'rejected', 'event_id': signal.event_id}
            mode = gate_mode()
            analysis = None
            if mode == 'ai':
                # AI-gated mode only: the model is part of the decision. In rules mode commentary is queued instead.
                try:
                    analysis = classify(signal)
                except (LocalAIError, httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
                    # No raw provider errors are logged: URLs may contain credentials.
                    analysis = None
            if analysis is None and mode == 'ai':
                if row['attempts'] < 3:
                    with database() as conn:
                        conn.execute("UPDATE signals SET status='queued', next_attempt_at=now()+interval '30 seconds', error_code='ai_unavailable_or_invalid' WHERE event_id=%s", (signal.event_id,))
                    return {'status': 'retry_queued', 'event_id': signal.event_id}
                finish(signal, 'error', None, ['ai_unavailable_or_invalid'], 'ai_unavailable_or_invalid')
                return {'status': 'error', 'event_id': signal.event_id}
            # In AI-gated mode the inference is part of the decision, so it must finish
            # while the setup is fresh. In rules mode commentary is non-authoritative.
            if mode == 'ai' and not freshness(signal):
                finish(signal, 'rejected', analysis, ['expired_during_analysis'])
                return {'status': 'rejected', 'event_id': signal.event_id}
            # Rules gate: every technical rule passed, so the setup is approved; the model only comments.
            status = outcome(signal, analysis) if mode == 'ai' else 'approved'
            finish(signal, status, analysis, [] if status == 'approved' else ['ai_quality_gate_rejected'])
            return {'status': status, 'event_id': signal.event_id}
        finally:
            guard.execute('SELECT pg_advisory_unlock(914207)')


@app.post('/notify', dependencies=[Depends(authorize)])
def notify():
    if not telegram_enabled():
        return {'status': 'disabled'}
    token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise HTTPException(503, 'Telegram is enabled but credentials are missing')
    chats = {'private': chat_id, 'digest': os.getenv('TELEGRAM_DIGEST_CHAT_ID') or chat_id, 'community': community_chat()}
    with database() as conn:
        # A send whose result was lost is never automatically resent.
        for table in ('notifications', 'messages'):
            conn.execute(f"UPDATE {table} SET status='unknown', error_code='interrupted_send' "
                         "WHERE status='sending' AND updated_at<now()-interval '2 minutes'")
        row = conn.execute('''UPDATE notifications SET status='sending', updated_at=now()
          WHERE event_id=(SELECT event_id FROM notifications WHERE status='pending'
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING event_id AS key, message''').fetchone()
        table, column, chat = 'notifications', 'event_id', chat_id
        if not row:
            # Signal alerts first; results and daily digests after them.
            row = conn.execute('''UPDATE messages SET status='sending', updated_at=now()
              WHERE ref=(SELECT ref FROM messages WHERE status='pending'
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING ref AS key, message, chat''').fetchone()
            if row:
                table, column, chat = 'messages', 'ref', chats[row['chat']]
    if not row:
        return {'status': 'idle'}
    status, error = deliver(token, chat, row['message']) if chat else ('failed', 'no_chat_configured')
    with database() as conn:
        conn.execute(f'UPDATE {table} SET status=%s,error_code=%s,updated_at=now() WHERE {column}=%s',
                     (status, error, row['key']))
    return {'status': status, ('event_id' if table == 'notifications' else 'ref'): row['key']}


class CandleBatch(BaseModel):
    """Closed broker M1 candles for [start, end): rows of [open_time, open, high, low, close, spread]."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    symbol: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z0-9]+$')
    start: int = Field(gt=0, strict=True)
    end: int = Field(gt=0, strict=True)
    candles: list[tuple[int, float, float, float, float, float]] = Field(max_length=6000)


@app.post('/candles', dependencies=[Depends(authorize)])
async def candles(request: Request):
    body = await request.body()
    if len(body) > 1_000_000:
        raise HTTPException(413, 'Payload too large')
    try:
        batch = CandleBatch.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, 'Invalid candle batch')
    now = time.time()
    if (batch.symbol not in allowed_symbols() or not batch.start < batch.end <= now + 60
            or batch.end - batch.start > 7 * 86400):
        raise HTTPException(422, 'Candle batch range or symbol is not accepted')
    for t, o, h, l, c, spread in batch.candles:
        if (t % 60 or not batch.start <= t <= batch.end - 60 or min(o, h, l, c) <= 0 or spread < 0
                or h < max(o, c) or l > min(o, c)):
            raise HTTPException(422, f'Invalid candle at {t}')
    with database() as conn:
        # First write wins: a stored candle is never replaced, so grading inputs cannot be revised.
        with conn.cursor() as cursor:
            cursor.executemany('''INSERT INTO candles(symbol,t,o,h,l,c,spread) VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT DO NOTHING''', [(batch.symbol, *row) for row in batch.candles])
        if batch.candles:
            ledger.refresh_h1(conn, batch.symbol, batch.start, batch.end)
        row = conn.execute('SELECT since, through FROM coverage WHERE symbol=%s FOR UPDATE', (batch.symbol,)).fetchone()
        if not row:
            since, through = batch.start, batch.end
        else:
            since, through = row['since'], row['through']
            # Coverage stays one contiguous window: batches extend it only where they touch it.
            if batch.start <= through < batch.end:
                through = batch.end
            if batch.start < since <= batch.end:
                since = batch.start
        conn.execute('''INSERT INTO coverage(symbol, since, through) VALUES (%s,%s,%s) ON CONFLICT (symbol)
            DO UPDATE SET since=excluded.since, through=excluded.through, updated_at=now()''',
            (batch.symbol, since, through))
        waiting = [item['plan']['published_at'] for item in ledger.open_plans(conn, batch.symbol)]
    older = [stamp for stamp in waiting if stamp < since]
    return {'symbol': batch.symbol, 'stored': len(batch.candles), 'since': since, 'through': through,
            'need_from': min(older) if older else through}


class TickBatch(BaseModel):
    """Broker ticks since the feeder's last pass: rows of [time_ms, bid, ask], for the website's live price only."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    symbol: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z0-9]+$')
    ticks: list[tuple[int, float, float]] = Field(min_length=1, max_length=2000)


@app.post('/ticks', dependencies=[Depends(authorize)])
async def ticks(request: Request):
    """Fold ticks into the symbol's live quote and current minute bar. Never graded: see app/quotes.py."""
    body = await request.body()
    if len(body) > 200_000:
        raise HTTPException(413, 'Payload too large')
    try:
        batch = TickBatch.model_validate_json(body)
    except ValidationError:
        raise HTTPException(422, 'Invalid tick batch')
    if batch.symbol not in allowed_symbols():
        raise HTTPException(422, 'Symbol is not accepted')
    if any(time_ms <= 0 or bid <= 0 or ask < bid for time_ms, bid, ask in batch.ticks):
        raise HTTPException(422, 'Invalid tick')
    with database() as conn:
        row = conn.execute('SELECT bid, ask, tick_ms, minute, o, h, l, c FROM quotes WHERE symbol=%s FOR UPDATE',
                           (batch.symbol,)).fetchone()
        quote, applied = quotes.fold(row, batch.ticks, int(time.time() * 1000))
        if applied:
            conn.execute('''INSERT INTO quotes(symbol, bid, ask, tick_ms, minute, o, h, l, c, updated_at)
                VALUES (%(symbol)s, %(bid)s, %(ask)s, %(tick_ms)s, %(minute)s, %(o)s, %(h)s, %(l)s, %(c)s, now())
                ON CONFLICT (symbol) DO UPDATE SET bid=excluded.bid, ask=excluded.ask, tick_ms=excluded.tick_ms,
                  minute=excluded.minute, o=excluded.o, h=excluded.h, l=excluded.l, c=excluded.c, updated_at=now()''',
                         {'symbol': batch.symbol, **quote})
    return {'symbol': batch.symbol, 'applied': applied, 'skipped': len(batch.ticks) - applied,
            'tick_ms': quote['tick_ms'] if quote else None}


def queue_digest(conn):
    zone = ZoneInfo(os.getenv('DIGEST_TIMEZONE', 'Asia/Phnom_Penh'))
    local = datetime.now(zone)
    if local.hour < int(os.getenv('DIGEST_HOUR', '7')):
        return
    ref = 'digest:' + local.strftime('%Y-%m-%d')
    if conn.execute('SELECT 1 FROM messages WHERE ref=%s', (ref,)).fetchone():
        return
    record = ledger.track_record(conn)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    window = (int((today - timedelta(days=1)).timestamp()), int(today.timestamp()))
    yesterday = [json.loads(row['body']) for row in ledger.rows(conn) if row['kind'] == 'closed']
    yesterday = [item for item in yesterday if window[0] <= item['time'] < window[1]]
    queue_message(conn, ref, 'digest', 'digest', ledger.digest_text(record, local.strftime('%Y-%m-%d'), yesterday))


@app.post('/grade', dependencies=[Depends(authorize)])
def grade():
    with database() as guard:
        guard.autocommit = True
        if not guard.execute('SELECT pg_try_advisory_lock(914208) AS acquired').fetchone()['acquired']:
            return {'status': 'busy'}
        try:
            recorded = 0
            with database() as conn:
                pending = ledger.open_plans(conn)
                coverage = {row['symbol']: row for row in conn.execute('SELECT symbol, since, through FROM coverage')}
                for item in pending:
                    plan, window = item['plan'], coverage.get(item['plan']['symbol'])
                    # No broker data for this plan yet: it stays open, never dropped.
                    if not window or window['since'] > plan['published_at'] or window['through'] <= plan['published_at']:
                        continue
                    rows = conn.execute('''SELECT t, o, h, l, c, spread FROM candles
                        WHERE symbol=%s AND t>=%s AND t<%s ORDER BY t''',
                        (plan['symbol'], plan['published_at'], window['through'])).fetchall()
                    new = [event for event in simulate(plan, rows, window['through']) if event['kind'] not in item['kinds']]
                    if not new:
                        continue
                    for event in new:
                        ledger.append(conn, item['event_id'], event['kind'], event['time'],
                                      {k: v for k, v in event.items() if k not in ('kind', 'time')})
                    text = ledger.result_text(plan, new, item['seq'])
                    queue_message(conn, f'result:{item["event_id"]}:{new[-1]["kind"]}', 'result', 'private', text)
                    if community_chat():
                        queue_message(conn, f'community:result:{item["event_id"]}:{new[-1]["kind"]}', 'result',
                                      'community', text)
                    if new[-1]['kind'] == 'closed' and jobs.trade_notes_enabled() and not synthetic(item['event_id']):
                        # The result goes out now; the local model's short review follows as its own message.
                        jobs.enqueue(conn, 'trade_note', item['event_id'])
                    # Commit per plan: the ledger lock stays brief for approvals running meanwhile.
                    conn.commit()
                    recorded += len(new)
                queue_digest(conn)
            return {'status': 'graded', 'recorded': recorded}
        finally:
            guard.execute('SELECT pg_advisory_unlock(914208)')


@app.get('/track-record', dependencies=[Depends(authorize)])
def track_record():
    with database() as conn:
        return ledger.track_record(conn)


@app.get('/ledger', dependencies=[Depends(authorize)])
def ledger_rows(after: int = 0):
    with database() as conn:
        return ledger.rows(conn, after=max(after, 0), limit=5000)


@app.get('/signals', dependencies=[Depends(authorize)])
def history():
    with database() as conn:
        return conn.execute('''SELECT s.*, n.status AS notification_status FROM signals s
          LEFT JOIN notifications n USING(event_id) ORDER BY received_at DESC LIMIT 100''').fetchall()


@app.post('/agent', dependencies=[Depends(authorize)])
def agent():
    """Telegram assistant, queued AI notes and the weekly report: one bounded tick under its own lock."""
    return worker.tick()
