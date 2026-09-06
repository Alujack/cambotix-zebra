import os
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from tests.test_domain import analysis, candidate


@pytest.fixture(autouse=True)
def isolated_database(monkeypatch):
    assert os.getenv('DB_NAME') == 'zebra_tests', 'Integration tests require a separate zebra_tests database'
    monkeypatch.setenv('FILTER_SESSIONS', 'false')
    monkeypatch.setenv('TELEGRAM_ENABLED', 'false')
    with main.database() as conn:
        conn.execute('TRUNCATE notifications, signals')
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
