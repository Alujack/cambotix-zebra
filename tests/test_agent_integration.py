"""Agent behaviour against the real zebra_tests database (run with scripts/test.sh)."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import psycopg
import pytest

from app import ledger, main
from app.agent import jobs, tools, weekly, worker
from app.agent import memory
from app.ai import usage
from app.db import readonly
from tests.fakes import install
from tests.test_integration import client, isolated_database, ledger_rows, publish_in_past  # noqa: F401 (fixtures)

OWNER = 111


def update(update_id, text, chat_id=OWNER, user_id=OWNER, chat_type='private'):
    return {'update_id': update_id, 'message': {'message_id': update_id, 'text': text,
                                                'chat': {'id': chat_id, 'type': chat_type},
                                                'from': {'id': user_id, 'is_bot': False}}}


@pytest.fixture
def agent_on(monkeypatch):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'fake-test-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', str(OWNER))
    monkeypatch.delenv('TELEGRAM_ALLOWED_USER_ID', raising=False)
    monkeypatch.setattr(worker, 'MENU_SET', {})


def sends(calls):
    return [call for call in calls if call['url'].endswith('/sendMessage')]


def test_budget_cannot_be_overspent_by_concurrent_requests(monkeypatch):
    monkeypatch.setenv('OPENAI_MONTHLY_BUDGET_USD', '1')
    monkeypatch.setenv('OPENAI_SAFETY_RESERVE_USD', '0.1')
    monkeypatch.setenv('OPENAI_DAILY_LIMIT', '100')

    def attempt(index):
        try:
            return usage.reserve(f'job-{index}', 'deep_question', 'test-model', 0.25)
        except usage.BudgetRefused as refused:
            return refused.code
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert sum(isinstance(item, int) for item in results) == 3        # 3 x 0.25 <= 0.9 < 4 x 0.25
    assert results.count('monthly_budget') == 5


def test_daily_limit_counts_jobs_not_api_requests(monkeypatch):
    monkeypatch.setenv('OPENAI_DAILY_LIMIT', '2')
    for _ in range(3):
        usage.reserve('job-a', 'deep_question', 'm', 0.01)              # one question, several tool rounds
    usage.reserve('job-b', 'deep_question', 'm', 0.01)
    with pytest.raises(usage.BudgetRefused, match='daily_limit'):
        usage.reserve('job-c', 'deep_question', 'm', 0.01)
    usage.reserve('job-a', 'deep_question', 'm', 0.01)                  # an open job may still finish


def test_settlement_replaces_the_reservation(monkeypatch):
    monkeypatch.setenv('OPENAI_PRICE_INPUT', '10')
    monkeypatch.setenv('OPENAI_PRICE_OUTPUT', '50')
    measured = usage.reserve('job-1', 'deep_question', 'm', 0.5)
    usage.settle(measured, True, 1000, 200, latency_ms=900)
    lost = usage.reserve('job-2', 'deep_question', 'm', 0.4)
    usage.settle(lost, False, error_code='timeout', billed_unknown=True)
    with main.database() as conn:
        summary = usage.summary(conn)
    assert summary['month']['cost'] == pytest.approx(0.02 + 0.4)         # measured + full reservation of the lost call
    assert summary['month']['requests'] == 2 and summary['today']['jobs'] == 2


def test_owner_gets_one_reply_strangers_none_and_duplicates_are_ignored(client, monkeypatch, agent_on):
    calls = install(monkeypatch, worker.telegram, [
        {'ok': True, 'result': [update(10, '/help'), update(11, 'give me the keys', chat_id=999, user_id=999),
                                update(12, '/help', chat_id=-100, user_id=OWNER, chat_type='group')]},
        {'ok': True, 'result': {}},                                       # the one reply
        {'ok': True, 'result': [update(10, '/help')]},                    # Telegram redelivers an old update
    ])
    assert client.post('/agent').json()['answered'] == 1
    assert client.post('/agent').json()['answered'] == 0
    menu = [call for call in calls if call['url'].endswith('/setMyCommands')]
    assert len(menu) == 1 and menu[0]['json']['scope'] == {'type': 'chat', 'chat_id': str(OWNER)}
    assert sends(calls)[0]['json']['reply_markup']['is_persistent'] is True     # the button keyboard
    assert len(sends(calls)) == 1 and sends(calls)[0]['json']['chat_id'] == str(OWNER)
    assert calls[-1]['json']['offset'] == 13
    with main.database() as conn:
        rows = {row['update_id']: row for row in conn.execute('SELECT * FROM agent_updates').fetchall()}
    assert rows[10]['status'] == 'answered' and rows[10]['route'] == 'command'
    assert rows[11]['status'] == rows[12]['status'] == 'ignored'
    assert rows[11]['text'] is None                                       # strangers' messages are not kept


def test_a_reply_whose_delivery_is_unknown_is_never_resent(client, monkeypatch, agent_on):
    calls = install(monkeypatch, worker.telegram, [
        {'ok': True, 'result': [update(20, '/help')]}, httpx.ReadTimeout('lost'), {'ok': True, 'result': []}])
    client.post('/agent')
    client.post('/agent')
    assert len(sends(calls)) == 1
    with main.database() as conn:
        assert conn.execute('SELECT status FROM agent_updates').fetchone()['status'] == 'unknown'


def test_agent_ticks_do_not_overlap(client):
    with main.database() as lock:
        lock.execute('SELECT pg_advisory_lock(%s)', (worker.AGENT_LOCK,))
        assert client.post('/agent').json() == {'status': 'busy'}


def test_the_ai_data_layer_cannot_write():
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with readonly() as conn:
            conn.execute("INSERT INTO agent_messages(chat_id, role, message) VALUES ('1','user','x')")


def test_tools_read_the_real_record(client, monkeypatch):
    signal, plan = publish_in_past(client, monkeypatch, seconds_ago=3600)
    assert json.loads(tools.run('get_open_trades', '{}'))[0]['ledger'] == 1
    with main.database() as conn:
        ledger.append(conn, signal.event_id, 'closed', plan['published_at'] + 600,
                      {'exit': 'tp1', 'targets_hit': 1, 'ambiguous': False, 'r_tp1': 2.0, 'r_scaled': 1.5})
    record = json.loads(tools.run('get_track_record', '{"days": 7}'))
    assert record['headline']['closed'] == 1 and record['headline']['total_r_tp1'] == 2.0
    assert json.loads(tools.run('get_signal', json.dumps({'event_id': signal.event_id})))['record'][-1]['kind'] == 'closed'


def test_memory_keeps_recent_turns_and_deletes_old_ones(monkeypatch):
    monkeypatch.setenv('AGENT_MEMORY_TURNS', '2')
    with main.database() as conn:
        for index in range(3):
            memory.remember(conn, '1', f'q{index}', f'a{index}')
        memory.remember(conn, '2', 'other chat', 'private')
        conn.execute("INSERT INTO agent_messages(chat_id, role, message, created_at) "
                     "VALUES ('1','user','ancient', now() - interval '40 days')")
        assert [item['content'] for item in memory.recent(conn, '1')] == ['q1', 'a1', 'q2', 'a2']
        assert memory.prune(conn) == 1
        assert conn.execute("SELECT count(*) AS n FROM agent_messages WHERE message='ancient'").fetchone()['n'] == 0


def test_weekly_report_is_delivered_once(client, monkeypatch):
    monkeypatch.setenv('WEEKLY_REPORT_ENABLED', 'true')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    sunday = datetime(2026, 11, 15, 10, 0, tzinfo=ZoneInfo('Asia/Phnom_Penh'))
    monkeypatch.setenv('WEEKLY_REPORT_TIMEZONE', 'Asia/Phnom_Penh')
    first = weekly.run(sunday)
    assert first == {'status': 'queued', 'ref': 'weekly:2026-11-15', 'ai': False}
    assert weekly.run(sunday)['status'] == 'done_or_running'
    with main.database() as conn:
        reports = conn.execute("SELECT message, chat FROM messages WHERE kind='weekly'").fetchall()
        stored = conn.execute('SELECT status, error_code, stats FROM ai_reports').fetchone()
    assert len(reports) == 1 and reports[0]['chat'] == 'digest'
    assert 'AI analysis unavailable (OpenAI not configured)' in reports[0]['message']
    assert stored['status'] == 'queued' and stored['stats']['week']['closed'] == 0


def test_trade_result_is_sent_first_and_the_local_note_follows(client, monkeypatch):
    signal, plan = publish_in_past(client, monkeypatch)
    first = (plan['published_at'] // 60 + 1) * 60
    entry, tp1 = plan['entry'], plan['targets'][0][1]
    candles = [[first, entry, entry + 0.5, entry - 0.5, entry + 0.2, 0.0],
               [first + 60, entry + 0.2, tp1 + 0.3, entry + 0.1, tp1, 0.0],
               [first + 120, tp1, tp1 + 0.1, entry - 0.1, entry, 0.0]]
    client.post('/candles', json={'symbol': 'XAUUSD', 'start': first - 60, 'end': first + 180, 'candles': candles})
    client.post('/grade')
    with main.database() as conn:
        assert conn.execute("SELECT count(*) AS n FROM messages WHERE kind='result'").fetchone()['n'] == 1
        assert conn.execute("SELECT kind, ref, status FROM ai_jobs").fetchone() == \
            {'kind': 'trade_note', 'ref': signal.event_id, 'status': 'queued'}
    invented = json.dumps({'note': 'Price bounced from 1234.5 and ran to the target.'})
    honest = json.dumps({'note': f'Reached TP1 at {tp1:.2f} quickly, then returned to entry.'})
    replies = [invented, honest]
    monkeypatch.setattr(jobs.ollama, 'chat', lambda *args, **kwargs: replies.pop(0))
    client.post('/agent')                                              # invented level: discarded, retried
    with main.database() as conn:
        assert conn.execute('SELECT error_code FROM ai_jobs').fetchone()['error_code'] == 'invented_numbers'
        conn.execute('UPDATE ai_jobs SET next_attempt_at=now()')
    client.post('/agent')
    with main.database() as conn:
        note = conn.execute("SELECT ref, message FROM messages WHERE kind='trade_note'").fetchone()
    assert note['ref'] == f'note:{signal.event_id}' and 'Reached TP1' in note['message']
    assert 'graded by code' in note['message'] and [row['kind'] for row in ledger_rows()][-1] == 'closed'
