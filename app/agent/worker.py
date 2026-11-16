"""One scheduled tick of the agent (POST /agent, every 10 s from n8n), under its own advisory lock:
1. read new Telegram messages and answer the owner's, 2. run queued AI notes, 3. send the weekly report when due.

Telegram updates are stored before they are answered and the read position is saved, so restarts and overlapping
runs never answer twice. A reply whose delivery result was lost is marked unknown and never resent."""
import logging
import os
import time

import httpx
import psycopg

from app.agent import jobs, memory, router, telegram, ui, weekly
from app.db import database

log = logging.getLogger('zebra.agent')
AGENT_LOCK = 914209
MENU_SET: dict[str, bool] = {}


def enabled() -> bool:
    return os.getenv('AGENT_ENABLED', 'false').lower() == 'true'


def ingest(token: str) -> int:
    with database() as conn:
        row = conn.execute("SELECT last_update_id FROM agent_state WHERE bot='telegram'").fetchone()
    found = telegram.updates(token, row['last_update_id'] + 1 if row else None)
    if not found:
        return 0
    with database() as conn:
        for item in found:
            message = item.get('message') or {}
            chat, sender = message.get('chat') or {}, message.get('from') or {}
            text = deep_reply(message)
            status = 'received' if message and telegram.allowed(message) else 'ignored'
            conn.execute('''INSERT INTO agent_updates(update_id, chat_id, user_id, chat_type, text, status)
                VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                (item['update_id'], str(chat.get('id', '')), str(sender.get('id', '')), chat.get('type'),
                 # Messages from anyone else are not kept.
                 (text or '')[:4000] if status == 'received' else None, status))
        last = max(item['update_id'] for item in found)
        conn.execute('''INSERT INTO agent_state(bot, last_update_id) VALUES ('telegram', %s) ON CONFLICT (bot)
            DO UPDATE SET last_update_id=GREATEST(agent_state.last_update_id, excluded.last_update_id), updated_at=now()''',
            (last,))
    return len(found)


def deep_reply(message: dict) -> str | None:
    """The message text; a reply to the bot's deep-question prompt becomes '/deep <question>'."""
    text = message.get('text')
    quoted = message.get('reply_to_message') or {}
    if (text and not text.startswith('/') and (quoted.get('from') or {}).get('is_bot')
            and (quoted.get('text') or '').startswith(ui.DEEP_PROMPT)):
        return '/deep ' + text
    return text


def recover():
    with database() as conn:
        conn.execute("""UPDATE agent_updates SET status=CASE WHEN attempts < 2 THEN 'received' ELSE 'failed' END,
            error_code='interrupted', updated_at=now() WHERE status='processing' AND updated_at < now() - interval '5 minutes'""")
        conn.execute("""UPDATE agent_updates SET status='unknown', error_code='interrupted_send', updated_at=now()
            WHERE status='replying' AND updated_at < now() - interval '2 minutes'""")


def claim() -> dict | None:
    with database() as conn:
        return conn.execute('''UPDATE agent_updates SET status='processing', attempts=attempts+1, updated_at=now()
          WHERE update_id=(SELECT update_id FROM agent_updates WHERE status='received'
            ORDER BY update_id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *''').fetchone()


def limited(chat_id: str) -> bool:
    with database() as conn:
        count = conn.execute("""SELECT count(*) AS n FROM agent_updates WHERE chat_id=%s
            AND status IN ('replying','answered','unknown') AND updated_at > now() - interval '1 hour'""",
            (chat_id,)).fetchone()['n']
    return count >= int(os.getenv('AGENT_RATE_LIMIT_PER_HOUR', '60'))


def answer(token: str, update: dict) -> str:
    chat_id = update['chat_id']
    try:
        if limited(chat_id):
            reply, route = '⏳ Too many messages this hour. Please wait a little.', 'rate_limited'
        else:
            telegram.typing(token, chat_id)
            reply, route = router.handle(chat_id, update['text'] or '')
    except psycopg.Error:
        reply, route = '⚠️ Data is unavailable right now (database). Try again shortly.', 'error'
    except Exception:
        log.exception('agent_reply_failed update=%s', update['update_id'])
        reply, route = '⚠️ Something went wrong while answering. Try again, or use /help.', 'error'
    with database() as conn:
        conn.execute("UPDATE agent_updates SET status='replying', reply=%s, route=%s, updated_at=now() WHERE update_id=%s",
                     (reply[:4000], route, update['update_id']))
    # The button keyboard rides on every reply; the deep prompt instead opens a reply box for the question.
    markup = ui.DEEP_REPLY if reply.startswith(ui.DEEP_PROMPT) else ui.KEYBOARD
    status, error = telegram.deliver(token, chat_id, reply[:4000], markup)
    final = 'answered' if status == 'sent' else status
    with database() as conn:
        conn.execute('UPDATE agent_updates SET status=%s, error_code=%s, updated_at=now() WHERE update_id=%s',
                     (final, error, update['update_id']))
    log.info('agent_reply update=%s route=%s status=%s', update['update_id'], route, final)
    return final


def tick() -> dict:
    with database() as guard:
        guard.autocommit = True
        if not guard.execute('SELECT pg_try_advisory_lock(%s) AS acquired', (AGENT_LOCK,)).fetchone()['acquired']:
            return {'status': 'busy'}
        try:
            return work()
        finally:
            guard.execute('SELECT pg_advisory_unlock(%s)', (AGENT_LOCK,))


def work() -> dict:
    started, result = time.monotonic(), {'status': 'ok', 'received': 0, 'answered': 0, 'jobs': 0}
    token = os.getenv('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.getenv('TELEGRAM_CHAT_ID', '').strip()
    if enabled() and token and chat_id:
        if MENU_SET.get(chat_id) is None:
            # Once per process (and per configured chat): the "/" command menu of the owner's chat.
            MENU_SET[chat_id] = telegram.set_commands(token, chat_id, ui.MENU)
        recover()
        try:
            result['received'] = ingest(token)
        except (httpx.HTTPError, ValueError):
            result['telegram'] = 'poll_failed'
        for _ in range(int(os.getenv('AGENT_MAX_UPDATES_PER_RUN', '5'))):
            update = claim()
            if not update:
                break
            answer(token, update)
            result['answered'] += 1
            if time.monotonic() - started > 150:
                break
    while time.monotonic() - started < 120 and result['jobs'] < 3:
        if jobs.run_one()['status'] == 'idle':
            break
        result['jobs'] += 1
    result['weekly'] = weekly.run()['status']
    with database() as conn:
        memory.prune(conn)
    return result
