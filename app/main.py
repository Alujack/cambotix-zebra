import hmac
import json
import os
from contextlib import contextmanager
from typing import Annotated

import httpx
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.domain import Analysis, Signal, freshness, notification_text, outcome, session_exempt_symbols, sessions, system_prompt, technical_rules
from app.news import news_status

app = FastAPI(title='Cambotix Zebra — signal analyzer', docs_url=None, redoc_url=None)


@contextmanager
def database():
    with psycopg.connect(host=os.getenv('DB_HOST', 'postgres'), dbname=os.getenv('DB_NAME', 'zebra'),
                          user=os.getenv('DB_USER', 'zebra'), password=os.environ['POSTGRES_PASSWORD'],
                          connect_timeout=1, options='-c statement_timeout=1500 -c lock_timeout=500',
                          row_factory=dict_row) as conn:
        yield conn


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
    return {'status': 'ok', 'mode': 'manual_review', 'execution_enabled': False}


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
    with httpx.Client(timeout=float(os.getenv('AI_TIMEOUT_SECONDS', '120'))) as client:
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


def finish(signal: Signal, status: str, analysis: Analysis | None, reasons: list[str], error_code=None):
    data = analysis.model_dump() if analysis else None
    enabled = os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true'
    with database() as conn:
        conn.execute('''UPDATE signals SET status=%s, analysis=%s, rule_reasons=%s,
            completed_at=now(), error_code=%s WHERE event_id=%s''',
            (status, Jsonb(data), Jsonb(reasons), error_code, signal.event_id))
        conn.execute('''INSERT INTO notifications(event_id,message,status) VALUES (%s,%s,%s)
            ON CONFLICT DO NOTHING''', (signal.event_id, notification_text(signal, status, data, reasons),
                                        'pending' if enabled else 'disabled'))


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
            if reasons:
                finish(signal, 'rejected', None, reasons)
                return {'status': 'rejected', 'event_id': signal.event_id}
            try:
                analysis = classify(signal)
            except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError):
                # No raw provider errors are logged: URLs may contain credentials.
                if row['attempts'] < 3:
                    with database() as conn:
                        conn.execute("UPDATE signals SET status='queued', next_attempt_at=now()+interval '30 seconds', error_code='ai_unavailable_or_invalid' WHERE event_id=%s", (signal.event_id,))
                    return {'status': 'retry_queued', 'event_id': signal.event_id}
                finish(signal, 'error', None, ['ai_unavailable_or_invalid'], 'ai_unavailable_or_invalid')
                return {'status': 'error', 'event_id': signal.event_id}
            # Recheck age after inference. A slow model cannot revive an expired setup.
            if not freshness(signal):
                finish(signal, 'rejected', analysis, ['expired_during_analysis'])
                return {'status': 'rejected', 'event_id': signal.event_id}
            status = outcome(signal, analysis)
            finish(signal, status, analysis, [] if status == 'approved' else ['ai_quality_gate_rejected'])
            return {'status': status, 'event_id': signal.event_id}
        finally:
            guard.execute('SELECT pg_advisory_unlock(914207)')


@app.post('/notify', dependencies=[Depends(authorize)])
def notify():
    if os.getenv('TELEGRAM_ENABLED', 'false').lower() != 'true':
        return {'status': 'disabled'}
    token, chat_id = os.getenv('TELEGRAM_BOT_TOKEN'), os.getenv('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        raise HTTPException(503, 'Telegram is enabled but credentials are missing')
    with database() as conn:
        # A send whose result was lost is never automatically resent.
        conn.execute("UPDATE notifications SET status='unknown', error_code='interrupted_send' WHERE status='sending' AND updated_at<now()-interval '2 minutes'")
        row = conn.execute('''UPDATE notifications SET status='sending', updated_at=now()
          WHERE event_id=(SELECT event_id FROM notifications WHERE status='pending'
            ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''').fetchone()
    if not row:
        return {'status': 'idle'}
    status, error = 'sent', None
    try:
        with httpx.Client(timeout=15) as client:
            result = client.post(f'https://api.telegram.org/bot{token}/sendMessage',
                                 json={'chat_id': chat_id, 'text': row['message']})
            result.raise_for_status()
            if result.json().get('ok') is not True:
                status, error = 'failed', 'telegram_rejected'
    except httpx.HTTPStatusError as exc:
        status, error = ('failed' if 400 <= exc.response.status_code < 500 else 'unknown'), 'telegram_http_error'
    except (httpx.HTTPError, ValueError):
        status, error = 'unknown', 'telegram_result_unknown'
    with database() as conn:
        conn.execute('UPDATE notifications SET status=%s,error_code=%s,updated_at=now() WHERE event_id=%s',
                     (status, error, row['event_id']))
    return {'status': status, 'event_id': row['event_id']}


@app.get('/signals', dependencies=[Depends(authorize)])
def history():
    with database() as conn:
        return conn.execute('''SELECT s.*, n.status AS notification_status FROM signals s
          LEFT JOIN notifications n USING(event_id) ORDER BY received_at DESC LIMIT 100''').fetchall()
