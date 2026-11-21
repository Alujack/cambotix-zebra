import json
import os
import time

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb

from app import ledger, main
from tests.test_domain import candidate
from web import api


@pytest.fixture(autouse=True)
def clean_record(monkeypatch):
    assert os.getenv('DB_NAME') == 'zebra_tests', 'Integration tests require a separate zebra_tests database'
    monkeypatch.setenv('FILTER_SESSIONS', 'false')
    monkeypatch.setenv('NEWS_FILTER', 'false')
    with main.database() as conn:
        ledger.migrate(conn)
        conn.execute('SET session_replication_role = replica')
        conn.execute('TRUNCATE messages, ledger, candles, coverage, notifications, signals')
    api.clear_cache()
    yield


@pytest.fixture
def client():
    return TestClient(api.app)


def publish(event_id, seconds_ago, direction='BUY_SETUP', status='approved'):
    signal = candidate(event_id=event_id, bar_time=int(time.time()) - seconds_ago, signal=direction)
    published_at = signal.bar_time + 30
    with main.database() as conn:
        conn.execute('''INSERT INTO signals(event_id, symbol, timeframe, bar_time, signal, payload, status, completed_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,now())''',
                     (event_id, signal.symbol, signal.timeframe, signal.bar_time, signal.signal, Jsonb(signal.model_dump()), status))
        if status == 'approved':
            ledger.append(conn, event_id, 'published', published_at, ledger.plan_record(signal, published_at, ['Weak trend: ADX 21']))
    return published_at


def close(event_id, published_at, r=1.0):
    with main.database() as conn:
        ledger.append(conn, event_id, 'filled', published_at + 60, {'price': 3510.3})
        if r > 0:
            ledger.append(conn, event_id, 'tp1', published_at + 600, {'price': 3516.6, 'r': 1.0})
        kind, exit_r = ('be', 0.0) if r > 0 else ('sl', -1.0)
        ledger.append(conn, event_id, kind, published_at + 900, {'price': 3510.3, 'r': exit_r})
        ledger.append(conn, event_id, 'closed', published_at + 900,
                      {'exit': kind, 'targets_hit': 1 if r > 0 else 0, 'ambiguous': False, 'r_tp1': r, 'r_scaled': 0.25 if r > 0 else -1.0})


def test_open_plans_hide_levels_and_closed_plans_show_them(client):
    won = publish('won', 7200)
    close('won', won, 1.0)
    lost = publish('lost', 5400, 'SELL_SETUP')
    close('lost', lost, -1.0)
    publish('open', 600)
    publish('DEMO-SYNTHETIC-classic-XAUUSD-1-BUY_SETUP', 300)
    publish('rejected-one', 200, status='rejected')
    items = client.get('/signals').json()
    assert [item['event_id'] for item in items] == ['DEMO-SYNTHETIC-classic-XAUUSD-1-BUY_SETUP', 'open', 'lost', 'won']
    open_plan = items[1]
    assert open_plan['status'] == 'open' and open_plan['levels_public'] is False and 'levels' not in open_plan
    assert open_plan['cautions'] == ['Weak trend: ADX 21'] and open_plan['events'] == []
    assert not any(key in open_plan for key in ('levels', 'entry', 'stop', 'targets'))
    assert '3510.25' not in json.dumps(open_plan) and '3503.95' not in json.dumps(open_plan)   # no level leaks anywhere
    closed = items[3]
    assert closed['status'] == 'closed' and closed['levels']['entry'] == 3510.25 and closed['levels']['targets'][0][0] == 1
    assert closed['result'] == {'exit': 'be', 'targets_hit': 1, 'ambiguous': False, 'r_tp1': 1.0, 'r_scaled': 0.25}
    assert [event['kind'] for event in closed['events']] == ['filled', 'tp1', 'be', 'closed']
    assert all('prev' not in event for event in closed['events'])
    assert client.get('/signals?limit=1').json()[0]['event_id'] == 'DEMO-SYNTHETIC-classic-XAUUSD-1-BUY_SETUP'


def test_record_counts_only_real_setups_and_is_cached(client):
    won = publish('won', 7200)
    close('won', won, 1.0)
    publish('DEMO-SYNTHETIC-x', 300)
    publish('rejected-one', 200, status='rejected')
    record = client.get('/record').json()
    assert record['headline']['closed'] == 1 and record['headline']['verdict'] == 'NOT ENOUGH DATA'
    assert record['journal'] == {'evaluated': 2, 'approved': 1, 'rejected': 1, 'pending': 0}
    assert record['chain']['valid'] is True and record['published'] == 2
    assert record['generated_at'].endswith('+00:00')
    lost = publish('lost', 5400, 'SELL_SETUP')
    close('lost', lost, -1.0)
    assert client.get('/record').json()['headline']['closed'] == 1      # cached
    api.clear_cache()
    assert client.get('/record').json()['headline']['closed'] == 2


def test_tickers_and_ledger_and_health(client):
    now = int(time.time()) // 60 * 60
    with main.database() as conn:
        with conn.cursor() as cursor:
            cursor.executemany('INSERT INTO candles(symbol,t,o,h,l,c,spread) VALUES (%s,%s,%s,%s,%s,%s,%s)', [
                ('XAUUSD', now - 86400 - 60, 3400.0, 3401.0, 3399.0, 3400.0, 0.1),
                ('XAUUSD', now - 60, 3500.0, 3501.0, 3499.0, 3502.0, 0.1),
                ('BTCUSD', now - 60, 80000.0, 80010.0, 79990.0, 80000.0, 1.0)])
    tickers = {item['symbol']: item for item in client.get('/tickers').json()}
    assert tickers['XAUUSD']['price'] == 3502.0 and tickers['XAUUSD']['change_24h_pct'] == 3.0 and tickers['XAUUSD']['time'] == now
    assert tickers['BTCUSD']['change_24h_pct'] is None
    assert client.get('/health').json() == {'status': 'ok'}
    won = publish('won', 7200)
    close('won', won, 1.0)
    rows = client.get('/ledger').json()
    assert [row['kind'] for row in rows] == ['published', 'filled', 'tp1', 'be', 'closed']
    assert client.get('/ledger?after=4').json()[0]['seq'] == 5
    assert ledger.verify(rows)['valid'] is True


def test_api_cannot_write():
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with api.readonly() as conn:
            conn.execute("INSERT INTO coverage(symbol, since, through) VALUES ('XAUUSD', 1, 2)")


def test_single_plan_by_ledger_number(client):
    won = publish('won', 7200)
    close('won', won, 1.0)
    publish('open', 600)
    closed = client.get('/signals/1').json()
    assert closed['event_id'] == 'won' and closed['status'] == 'closed' and closed['levels']['entry'] == 3510.25
    assert [event['kind'] for event in closed['events']] == ['filled', 'tp1', 'be', 'closed']
    open_seq = client.get('/signals').json()[0]['seq']
    open_plan = client.get(f'/signals/{open_seq}').json()
    assert open_plan['event_id'] == 'open' and open_plan['levels_public'] is False and 'levels' not in open_plan
    assert client.get('/signals/2').status_code == 404        # row 2 is a fill event, not a plan
    assert client.get('/signals/999').status_code == 404
