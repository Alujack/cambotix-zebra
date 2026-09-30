import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import ledger, main
from tests.test_domain import analysis, candidate


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    assert os.getenv('DB_NAME') == 'zebra_tests', 'Integration tests require a separate zebra_tests database'
    monkeypatch.setenv('FILTER_SESSIONS', 'false')
    monkeypatch.setenv('TELEGRAM_ENABLED', 'false')
    monkeypatch.setenv('NEWS_FILTER', 'false')
    monkeypatch.setenv('DIGEST_HOUR', '24')
    monkeypatch.delenv('GATE_MODE', raising=False)
    with main.database() as conn:
        ledger.migrate(conn)
        # Test-only reset: replica mode skips the append-only triggers, which requires a database superuser.
        conn.execute('SET session_replication_role = replica')
        conn.execute('TRUNCATE messages, ledger, candles, coverage, notifications, signals')
    yield


@pytest.fixture
def client():
    with TestClient(main.app, headers={'X-Zebra-Token': os.environ['ANALYZER_TOKEN']}) as value:
        yield value


def payload(**changes):
    return candidate(bar_time=int(time.time()), **changes).model_dump()


def test_authentication_and_stale_signal(client):
    assert client.get('/signals', headers={'X-Zebra-Token': 'wrong'}).status_code == 401
    assert client.post('/signals', json={**payload(), 'bar_time': int(time.time()) - 600}).status_code == 422


def test_concurrent_deduplication(client):
    data = payload()
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(pool.map(lambda _: client.post('/signals', json=data).status_code, range(8)))
    assert codes.count(202) == 1
    assert codes.count(200) == 7
    assert len(client.get('/signals').json()) == 1
    assert client.post('/signals', json={**data, 'event_id': 'different-id'}).json()['status'] == 'duplicate'
    assert client.post('/signals', json={**data, 'price': 9999}).status_code == 409


def test_valid_signal_is_analyzed_and_audited(client, monkeypatch):
    monkeypatch.setattr(main, 'classify', lambda signal: analysis())
    assert client.post('/signals', json=payload()).status_code == 202
    assert client.post('/process').json()['status'] == 'approved'
    row = client.get('/signals').json()[0]
    assert row['analysis']['confidence'] == 80
    assert row['notification_status'] == 'disabled'
    assert client.post('/process').json()['status'] == 'idle'
    assert client.post('/notify').json()['status'] == 'disabled'


def test_rule_failure_never_calls_ai(client, monkeypatch):
    def forbidden(signal):
        pytest.fail('AI must not be called for rejected technical rules')
    monkeypatch.setattr(main, 'classify', forbidden)
    client.post('/signals', json=payload(adx=5))
    assert client.post('/process').json()['status'] == 'rejected'


def test_ai_failures_retry_then_fail_closed(client, monkeypatch):
    monkeypatch.setenv('GATE_MODE', 'ai')

    def invalid(signal):
        raise ValueError('Malformed AI output')
    monkeypatch.setattr(main, 'classify', invalid)
    client.post('/signals', json=payload())
    for expected in ['retry_queued', 'retry_queued', 'error']:
        assert client.post('/process').json()['status'] == expected
        with main.database() as conn:
            conn.execute('UPDATE signals SET next_attempt_at=now()')
    row = client.get('/signals').json()[0]
    assert row['attempts'] == 3 and row['analysis'] is None


def test_signal_expired_during_ai_is_rejected(client, monkeypatch):
    def slow_analysis(signal):
        monkeypatch.setattr(main, 'freshness', lambda signal: False)
        return analysis()
    monkeypatch.setattr(main, 'classify', slow_analysis)
    client.post('/signals', json=payload())
    assert client.post('/process').json()['status'] == 'rejected'
    assert client.get('/signals').json()[0]['rule_reasons'] == ['expired_during_analysis']


def test_restart_recovers_claim_and_overlapping_workers_skip(client, monkeypatch):
    monkeypatch.setattr(main, 'classify', lambda signal: analysis())
    client.post('/signals', json=payload())
    with main.database() as conn:
        conn.execute("UPDATE signals SET status='processing'")
    with main.database() as lock:
        lock.execute('SELECT pg_advisory_lock(914207)')
        assert client.post('/process').json()['status'] == 'busy'
    assert client.post('/process').json()['status'] == 'approved'


@pytest.mark.parametrize('result_code,expected', [(200, 'sent'), (400, 'failed'), (500, 'unknown'), (None, 'unknown')])
def test_telegram_outcomes_are_not_resent(client, monkeypatch, result_code, expected):
    monkeypatch.setenv('TELEGRAM_ENABLED', 'true')
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', 'fake-test-token')
    monkeypatch.setenv('TELEGRAM_CHAT_ID', 'fake-test-chat')
    signal = candidate(bar_time=int(time.time()))
    client.post('/signals', json=signal.model_dump())
    main.finish(signal, 'approved', analysis(), [])
    calls = []

    class FakeTelegram:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def post(self, url, json):
            calls.append(json)
            if result_code is None:
                raise httpx.ReadTimeout('Simulated timeout')
            return httpx.Response(result_code, json={'ok': result_code == 200}, request=httpx.Request('POST', url))

    monkeypatch.setattr(main.httpx, 'Client', FakeTelegram)
    assert client.post('/notify').json()['status'] == expected
    assert client.post('/notify').json()['status'] == 'idle'
    assert len(calls) == 1
    assert client.get('/signals').json()[0]['notification_status'] == expected


def ledger_rows():
    with main.database() as conn:
        return ledger.rows(conn)


def test_rules_gate_publishes_when_ai_is_down(client, monkeypatch):
    def down(signal):
        raise httpx.ConnectError('model offline')
    monkeypatch.setattr(main, 'classify', down)
    client.post('/signals', json=payload())
    assert client.post('/process').json()['status'] == 'approved'
    row = client.get('/signals').json()[0]
    assert row['error_code'] == 'ai_commentary_unavailable' and row['analysis'] is None
    rows = ledger_rows()
    assert [item['kind'] for item in rows] == ['published']
    plan = json.loads(rows[0]['body'])
    assert plan['entry_type'] == 'market' and plan['direction'] == 'BUY' and plan['prev'] == ledger.GENESIS
    with main.database() as conn:
        message = conn.execute('SELECT message FROM notifications').fetchone()['message']
    assert 'Ledger: #1' in message


def test_ai_gate_rejection_is_not_published(client, monkeypatch):
    monkeypatch.setenv('GATE_MODE', 'ai')
    monkeypatch.setattr(main, 'classify', lambda signal: analysis(decision='REJECT'))
    client.post('/signals', json=payload())
    assert client.post('/process').json()['status'] == 'rejected'
    assert ledger_rows() == []


def test_record_cannot_be_edited_or_removed(client, monkeypatch):
    monkeypatch.setattr(main, 'classify', lambda signal: analysis())
    client.post('/signals', json=payload())
    client.post('/process')
    for statement in ["UPDATE ledger SET body='{}'", 'DELETE FROM ledger', 'TRUNCATE ledger CASCADE',
                      'DELETE FROM signals', 'TRUNCATE signals CASCADE']:
        with pytest.raises(psycopg.errors.RaiseException, match='append-only'):
            with main.database() as conn:
                conn.execute(statement)
    assert len(ledger_rows()) == 1


def publish_in_past(client, monkeypatch, seconds_ago=7200):
    clock = [time.time() - seconds_ago]
    monkeypatch.setattr(main, 'time', SimpleNamespace(time=lambda: clock[0]))
    signal = candidate(bar_time=int(time.time()))
    client.post('/signals', json=signal.model_dump())
    main.finish(signal, 'approved', analysis(), [])
    clock[0] = time.time()
    return signal, json.loads(ledger_rows()[-1]['body'])


def test_candles_are_graded_into_the_record(client, monkeypatch):
    signal, plan = publish_in_past(client, monkeypatch)
    first = (plan['published_at'] // 60 + 1) * 60
    entry, stop, tp1 = plan['entry'], plan['stop'], plan['targets'][0][1]
    candles = [[first, entry, entry + 0.5, entry - 0.5, entry + 0.2, 0.0],
               [first + 60, entry + 0.2, tp1 + 0.3, entry + 0.1, tp1, 0.0],
               [first + 120, tp1, tp1 + 0.1, entry - 0.1, entry, 0.0]]
    batch = {'symbol': 'XAUUSD', 'start': first - 60, 'end': first + 180, 'candles': candles}
    reply = client.post('/candles', json=batch).json()
    assert reply == {'symbol': 'XAUUSD', 'stored': 3, 'since': first - 60, 'through': first + 180,
                     'need_from': first + 180}
    assert client.post('/grade').json() == {'status': 'graded', 'recorded': 4}
    assert client.post('/grade').json() == {'status': 'graded', 'recorded': 0}
    assert [row['kind'] for row in ledger_rows()] == ['published', 'filled', 'tp1', 'be', 'closed']
    record = client.get('/track-record').json()
    assert record['published'] == 1 and record['open'] == 0
    assert record['headline']['closed'] == 1 and record['headline']['wins'] == 1
    assert record['headline']['total_r_tp1'] == 1.0 and record['headline']['verdict'] == 'NOT ENOUGH DATA'
    assert record['chain']['valid'] is True and record['chain']['head_seq'] == 5
    with main.database() as conn:
        result = conn.execute("SELECT ref, message, status FROM messages WHERE kind='result'").fetchone()
    assert result['ref'] == f'result:{signal.event_id}:closed' and result['status'] == 'disabled'
    assert 'TP1 hit' in result['message'] and 'CLOSED (be)' in result['message']
    # A replayed batch with different prices cannot rewrite stored candles.
    replay = {**batch, 'candles': [[first + 60, entry, entry + 50, entry - 50, entry, 0.0]]}
    assert client.post('/candles', json=replay).status_code == 200
    with main.database() as conn:
        assert conn.execute('SELECT h FROM candles WHERE t=%s', (first + 60,)).fetchone()['h'] == tp1 + 0.3


def test_coverage_asks_for_missing_history(client, monkeypatch):
    _, plan = publish_in_past(client, monkeypatch)
    later = (plan['published_at'] // 60 + 30) * 60
    reply = client.post('/candles', json={'symbol': 'XAUUSD', 'start': later, 'end': later + 60, 'candles': []}).json()
    assert reply['since'] == later and reply['need_from'] == plan['published_at']
    assert client.post('/grade').json()['recorded'] == 0   # no data for the plan yet: it stays open
    start = plan['published_at'] // 60 * 60
    reply = client.post('/candles', json={'symbol': 'XAUUSD', 'start': start, 'end': later + 120, 'candles': []}).json()
    assert reply['since'] == start and reply['through'] == later + 120 and reply['need_from'] == later + 120


@pytest.mark.parametrize('change', [
    {'end': int(time.time()) + 3600},
    {'symbol': 'EURUSD'},
    {'candles': [[1_790_000_040, 10, 9, 8, 9, 0]]},
    {'candles': [[1_790_000_050, 10, 11, 9, 10, 0]]},
    {'candles': [[1_790_000_040, 10, 11, 9, 10, -1]]},
])
def test_invalid_candle_batches_are_refused(client, change):
    batch = {'symbol': 'XAUUSD', 'start': 1_790_000_040 - 60, 'end': 1_790_000_040 + 60, 'candles': [], **change}
    assert client.post('/candles', json=batch).status_code == 422


def test_daily_digest_carries_the_chain_head(client, monkeypatch):
    publish_in_past(client, monkeypatch)
    monkeypatch.setenv('DIGEST_HOUR', '0')
    client.post('/grade')
    client.post('/grade')
    with main.database() as conn:
        digests = conn.execute("SELECT message FROM messages WHERE kind='digest'").fetchall()
    head = client.get('/track-record').json()['chain']['head_hash']
    assert len(digests) == 1 and head in digests[0]['message'] and 'Chain head #1' in digests[0]['message']


def test_tampering_breaks_the_chain(client, monkeypatch):
    publish_in_past(client, monkeypatch)
    with main.database() as conn:
        conn.execute('SET session_replication_role = replica')
        conn.execute("UPDATE ledger SET body=replace(body, '\"direction\":\"BUY\"', '\"direction\":\"SELL\"')")
    assert client.get('/track-record').json()['chain'] == {'valid': False, 'broken_at': 1, 'rows': 1}


def test_synthetic_signals_never_reach_the_record(client, monkeypatch):
    monkeypatch.setattr(main, 'classify', lambda signal: analysis())
    client.post('/signals', json=payload(event_id='DEMO-SYNTHETIC-classic-XAUUSD-1-BUY_SETUP'))
    assert client.post('/process').json()['status'] == 'approved'
    assert ledger_rows() == []
    with main.database() as conn:
        assert 'not recorded (synthetic test signal)' in conn.execute('SELECT message FROM notifications').fetchone()['message']
