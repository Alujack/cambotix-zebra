"""Queued local-model commentary that is sent AFTER the original message, so a slow or offline model can never
delay or block a signal alert or a trade result. Facts come from code; the model only words them."""
import json
import logging
import os
import time

from psycopg.types.json import Jsonb
from pydantic import ValidationError

from app.ai import ollama, prompts
from app.ai.review import classify
from app.ai.schemas import TradeNote, unsupported_numbers
from app.agent.tools import iso
from app.db import database
from app.domain import Signal, plain_reason
from app.outbox import queue_message

MAX_ATTEMPTS = 3
log = logging.getLogger('zebra.ai')


def enqueue(conn, kind: str, ref: str):
    conn.execute('INSERT INTO ai_jobs(kind, ref) VALUES (%s,%s) ON CONFLICT DO NOTHING', (kind, ref))


def signal_notes_enabled() -> bool:
    return os.getenv('AI_COMMENTARY', 'true').lower() == 'true'


def trade_notes_enabled() -> bool:
    return os.getenv('TRADE_NOTES', 'true').lower() == 'true'


def claim() -> dict | None:
    with database() as conn:
        # A worker killed mid-job leaves it running; give it back (or give up) after ten minutes.
        conn.execute(f"""UPDATE ai_jobs SET status=CASE WHEN attempts < {MAX_ATTEMPTS} THEN 'queued' ELSE 'failed' END,
            error_code='interrupted', updated_at=now() WHERE status='running' AND updated_at < now() - interval '10 minutes'""")
        return conn.execute('''UPDATE ai_jobs SET status='running', attempts=attempts+1, updated_at=now()
          WHERE id=(SELECT id FROM ai_jobs WHERE status='queued' AND next_attempt_at<=now()
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''').fetchone()


def finish(job: dict, status: str, error: str | None = None):
    with database() as conn:
        if status == 'retry':
            status = 'queued' if job['attempts'] < MAX_ATTEMPTS else 'failed'
        conn.execute('''UPDATE ai_jobs SET status=%s, error_code=%s, updated_at=now(),
            next_attempt_at=now() + make_interval(mins => %s) WHERE id=%s''', (status, error, 2 * job['attempts'], job['id']))


def run_one() -> dict:
    job = claim()
    if not job:
        return {'status': 'idle'}
    try:
        outcome = (signal_note if job['kind'] == 'signal_note' else trade_note)(job['ref'])
    except ollama.LocalAIError as error:
        finish(job, 'retry', error.code)
        return {'status': 'retry', 'kind': job['kind'], 'error': error.code}
    except ValidationError:
        finish(job, 'retry', 'invalid_output')
        return {'status': 'retry', 'kind': job['kind'], 'error': 'invalid_output'}
    except Exception:
        # Notes are optional: one broken job must not stop the tick that also answers Telegram.
        log.exception('ai_job_failed id=%s kind=%s', job['id'], job['kind'])
        finish(job, 'retry', 'error')
        return {'status': 'retry', 'kind': job['kind'], 'error': 'error'}
    finish(job, outcome)
    return {'status': outcome, 'kind': job['kind']}


def too_old(stamp: float, minutes_env: str, default: str) -> bool:
    return time.time() - stamp > int(os.getenv(minutes_env, default)) * 60


def signal_note(event_id: str) -> str:
    with database() as conn:
        row = conn.execute('SELECT payload, status, analysis FROM signals WHERE event_id=%s', (event_id,)).fetchone()
        seq = conn.execute("SELECT seq FROM ledger WHERE event_id=%s AND kind='published'", (event_id,)).fetchone()
    if not row or row['status'] != 'approved' or row['analysis'] is not None:
        return 'skipped'
    signal = Signal.model_validate(row['payload'])
    if too_old(signal.bar_time, 'AI_NOTE_MAX_AGE_MINUTES', '60'):
        return 'skipped'
    analysis = classify(signal).model_dump()
    with database() as conn:
        # finish() stores "no analysis" as JSON null, which is not SQL NULL.
        conn.execute("UPDATE signals SET analysis=%s WHERE event_id=%s AND (analysis IS NULL OR analysis='null'::jsonb)",
                     (Jsonb(analysis), event_id))
        queue_message(conn, f'ai:{event_id}', 'ai_review', 'private', review_text(signal, analysis, seq and seq['seq']))
    return 'done'


def review_text(signal: Signal, analysis: dict, seq: int | None) -> str:
    side = 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL'
    lines = [f'🦓 AI REVIEW · {side} {signal.symbol} {signal.timeframe} [{signal.model.upper()}]'
             + (f' · Ledger #{seq}' if seq else ''),
             'Decision (rules): APPROVED', '',
             f'AI view: {analysis["decision"]} · quality {analysis["setup_quality"]} · regime {analysis["market_regime"]}'
             f' · score {analysis["confidence"]}/100 (not a win probability)']
    lines += ['• ' + item for item in analysis['reasons']]
    if analysis['risk_flags']:
        lines += ['Risk flags:'] + ['• ' + item for item in analysis['risk_flags']]
    lines += ['', '⚠️ AI commentary only. The rules decide; this note changes nothing.']
    return '\n'.join(lines)[:4000]


def trade_facts(conn, event_id: str) -> dict | None:
    rows = conn.execute('SELECT seq, kind, body FROM ledger WHERE event_id=%s ORDER BY seq', (event_id,)).fetchall()
    bodies = {row['kind']: (row['seq'], json.loads(row['body'])) for row in rows}
    if 'published' not in bodies or 'closed' not in bodies:
        return None
    seq, plan = bodies['published']
    closed = bodies['closed'][1]
    events = [json.loads(row['body']) for row in rows if row['kind'] not in ('published', 'closed')]
    fill = next((item for item in events if item['kind'] == 'filled'), None)
    start, end = (fill or {'time': plan['published_at']})['time'], closed['time']
    payload = conn.execute('SELECT payload FROM signals WHERE event_id=%s', (event_id,)).fetchone()['payload']
    seconds = 900 if end - start <= 24 * 900 else 3600
    bars = conn.execute('''SELECT (t / %s) * %s AS t, (array_agg(o ORDER BY t))[1] AS o, max(h) AS h, min(l) AS l,
          (array_agg(c ORDER BY t DESC))[1] AS c FROM candles WHERE symbol=%s AND t >= %s AND t <= %s
        GROUP BY 1 ORDER BY 1 LIMIT 48''', (seconds, seconds, plan['symbol'], start, end)).fetchall()
    return {'seq': seq, 'closed_at': end, 'plan': {
                'symbol': plan['symbol'], 'model': plan['model'], 'timeframe': plan['timeframe'],
                'direction': plan['direction'], 'session': plan.get('session'), 'entry': plan['entry'],
                'stop': plan['stop'], 'targets': [level for _, level, _ in plan['targets']],
                'setup': plain_reason(Signal.model_validate(payload))},
            'events': [{'kind': item['kind'], 'time': iso(item['time']),
                        **{k: item[k] for k in ('price', 'r', 'reason') if k in item}} for item in events],
            'result': {'exit': closed.get('exit'), 'r_tp1': closed['r_tp1'], 'r_scaled': closed['r_scaled'],
                       'closed': iso(closed['time']), 'duration_minutes': round((end - start) / 60),
                       'ambiguous_candle': closed.get('ambiguous', False)},
            'candles': {'timeframe': '15m' if seconds == 900 else '1h',
                        'bars': [{'t': iso(bar['t']), 'o': round(bar['o'], 2), 'h': round(bar['h'], 2),
                                  'l': round(bar['l'], 2), 'c': round(bar['c'], 2)} for bar in bars]}}


def trade_note(event_id: str) -> str:
    with database() as conn:
        facts = trade_facts(conn, event_id)
    if facts is None or too_old(facts.pop('closed_at'), 'TRADE_NOTE_MAX_AGE_MINUTES', '1440'):
        return 'skipped'
    data = json.dumps(facts, default=str, separators=(',', ':'))
    text = ollama.chat('trade_note', [{'role': 'system', 'content': prompts.TRADE_NOTE},
                                      {'role': 'user', 'content': 'DATA: ' + data}],
                       schema=TradeNote.model_json_schema(), temperature=0.2, max_tokens=160)
    note = TradeNote.model_validate_json(text).note
    if unsupported_numbers(note, data):
        # A number that is in none of the facts is an invented level: discard rather than publish it.
        raise ollama.LocalAIError('invented_numbers')
    plan, result = facts['plan'], facts['result']
    message = '\n'.join([f'📝 AI REVIEW · {plan["direction"]} {plan["symbol"]} · Ledger #{facts["seq"]} · '
                         f'{result["exit"]} {result["r_tp1"]:+.2f}R', note, '',
                         '⚠️ AI commentary only; the result above is graded by code.'])
    with database() as conn:
        queue_message(conn, f'note:{event_id}', 'trade_note', 'private', message)
    return 'done'
