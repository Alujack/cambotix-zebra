import hmac
import json
import os
import time
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta
from typing import Annotated
from zoneinfo import ZoneInfo

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import ledger
from app.domain import (Analysis, Signal, allowed_symbols, cautions, freshness, gate_mode, notification_text, outcome,
                        session_exempt_symbols, sessions, synthetic, system_prompt, technical_rules)
from app.grader import simulate
from app.news import news_status


@contextmanager
def database():
    with psycopg.connect(host=os.getenv('DB_HOST', 'postgres'), dbname=os.getenv('DB_NAME', 'zebra'),
                          user=os.getenv('DB_USER', 'zebra'), password=os.environ['POSTGRES_PASSWORD'],
                          connect_timeout=1, options='-c statement_timeout=1500 -c lock_timeout=500',
                          row_factory=dict_row) as conn:
        yield conn


@asynccontextmanager
async def lifespan(_):
    with database() as conn:
        ledger.migrate(conn)
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
    return {'status': 'ok', 'mode': 'manual_review', 'gate': gate_mode(), 'execution_enabled': False}


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


def classify(signal: Signal) -> Analysis:
    schema = Analysis.model_json_schema()
    timeout = float(os.getenv('AI_TIMEOUT_SECONDS', '120'))
    if gate_mode() == 'rules':
        # Commentary must never consume the signal's remaining lifetime. Leave a small
        # reserve for the approval and outbox transaction.
        maximum_age = int(os.getenv('MAX_SIGNAL_AGE_SECONDS', '300'))
        remaining = maximum_age - (time.time() - signal.bar_time) - 5
        timeout = min(timeout, max(1.0, remaining))
    with httpx.Client(timeout=timeout) as client:
        response = client.post(os.getenv('OLLAMA_BASE_URL', 'http://ollama:11434').rstrip('/') + '/api/chat', json={
            'model': os.getenv('OLLAMA_MODEL', 'qwen2.5:1.5b'), 'stream': False, 'format': schema,
            'options': {'temperature': 0, 'num_predict': 600, 'num_ctx': 4096},
            'messages': [{'role': 'system', 'content': system_prompt(signal) + '\nSchema: ' + json.dumps(schema)},
                         {'role': 'user', 'content': json.dumps({'candidate': signal.model_dump(),
                                                                 'sessions': sessions(signal.bar_time),
                                                                 'trades_continuously': signal.symbol in session_exempt_symbols(),
                                                                 'news': news_status(signal.bar_time)})}]
        })
        response.raise_for_status()
        return Analysis.model_validate_json(response.json()['message']['content'])


def telegram_enabled() -> bool:
    return os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'


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
        conn.execute('''INSERT INTO notifications(event_id,message,status) VALUES (%s,%s,%s)
            ON CONFLICT DO NOTHING''', (signal.event_id, notification_text(signal, status, data, reasons, ledger_seq=seq,
                                                                         warnings=warnings),
                                        'pending' if telegram_enabled() else 'disabled'))


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
                # One idea, one plan: a second entry in the same direction doubles the same bet.
                direction = 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL'
                with database() as conn:
                    if ledger.open_count(conn, signal.symbol, direction, time.time()) >= limit:
                        reasons = ['open_plan_same_direction']
            if reasons:
                finish(signal, 'rejected', None, reasons)
                return {'status': 'rejected', 'event_id': signal.event_id}
            mode = gate_mode()
            commentary = os.getenv('AI_COMMENTARY', 'true').lower() == 'true'
            analysis = None
            if mode == 'ai' or commentary:
                try:
                    analysis = classify(signal)
                except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
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
            finish(signal, status, analysis, [] if status == 'approved' else ['ai_quality_gate_rejected'],
                   None if analysis else 'ai_commentary_unavailable')
            return {'status': status, 'event_id': signal.event_id}
        finally:
            guard.execute('SELECT pg_advisory_unlock(914207)')


def deliver(token: str, chat_id: str, text: str) -> tuple[str, str | None]:
    try:
        with httpx.Client(timeout=15) as client:
            result = client.post(f'https://api.telegram.org/bot{token}/sendMessage', json={'chat_id': chat_id, 'text': text})
            result.raise_for_status()
            if result.json().get('ok') is not True:
                return 'failed', 'telegram_rejected'
    except httpx.HTTPStatusError as exc:
        return ('failed' if 400 <= exc.response.status_code < 500 else 'unknown'), 'telegram_http_error'
    except (httpx.HTTPError, ValueError):
        return 'unknown', 'telegram_result_unknown'
    return 'sent', None


@app.post('/notify', dependencies=[Depends(authorize)])
def notify():
    if not telegram_enabled():
        return {'status': 'disabled'}
    token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise HTTPException(503, 'Telegram is enabled but credentials are missing')
    chats = {'private': chat_id, 'digest': os.getenv('TELEGRAM_DIGEST_CHAT_ID') or chat_id}
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
    status, error = deliver(token, chat, row['message'])
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


def queue_message(conn, ref: str, kind: str, chat: str, text: str):
    conn.execute('''INSERT INTO messages(ref, kind, chat, message, status) VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT DO NOTHING''', (ref, kind, chat, text, 'pending' if telegram_enabled() else 'disabled'))


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
                    queue_message(conn, f'result:{item["event_id"]}:{new[-1]["kind"]}', 'result', 'private',
                                  ledger.result_text(plan, new, item['seq']))
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
