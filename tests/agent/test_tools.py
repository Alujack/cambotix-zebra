import json
from contextlib import contextmanager

import pytest

from app.agent import tools


@pytest.fixture
def no_database(monkeypatch):
    @contextmanager
    def forbidden():
        pytest.fail('the database must not be touched')
        yield
    monkeypatch.setattr(tools, 'readonly', forbidden)


@pytest.mark.parametrize('name', ['close_trade', 'execute_sql', 'update_settings', 'place_order', ''])
def test_only_allowlisted_read_tools_exist(no_database, name):
    result = json.loads(tools.run(name, '{"sql": "DELETE FROM ledger"}'))
    assert 'unknown tool' in result['error']


@pytest.mark.parametrize('name,arguments', [
    ('get_signals', '{"limit": 5000}'),
    ('get_signals', '{"status": "approved; DROP TABLE signals"}'),
    ('get_track_record', '{"days": 30, "sql": "SELECT 1"}'),
    ('get_candles', '{"symbol": "XAUUSD", "timeframe": "1m"}'),
    ('get_closed_trades', 'not json'),
])
def test_invalid_arguments_never_reach_the_database(no_database, name, arguments):
    assert json.loads(tools.run(name, arguments))['error'] == 'invalid arguments'


def test_tool_specs_cover_exactly_the_read_tools():
    names = [item['name'] for item in tools.specs()]
    assert names == ['get_track_record', 'get_signals', 'get_signal', 'get_open_trades', 'get_closed_trades',
                     'get_candles', 'get_news']
    assert all(item['parameters'].get('additionalProperties') is False for item in tools.specs())


def test_large_results_are_truncated(monkeypatch):
    @contextmanager
    def fake():
        yield object()
    monkeypatch.setattr(tools, 'readonly', fake)
    monkeypatch.setitem(tools.TOOLS, 'get_open_trades', ('', tools.NoArgs, lambda conn, args: ['x' * 100] * 200))
    text = tools.run('get_open_trades', '{}', limit=500)
    assert len(text) < 600 and text.endswith('[truncated: ask for fewer rows or a shorter period]')


def test_database_errors_become_a_plain_message(monkeypatch):
    @contextmanager
    def broken():
        raise RuntimeError('connection refused to postgres:5432 password=secret')
        yield
    monkeypatch.setattr(tools, 'readonly', broken)
    assert json.loads(tools.run('get_open_trades', '{}')) == {'error': 'data unavailable'}


def test_symbols_are_normalized(monkeypatch):
    monkeypatch.setenv('SYMBOLS', 'XAUUSD,EURUSD')
    assert tools.normalize_symbol('xauusdm') == 'XAUUSD'
    assert tools.normalize_symbol('OANDA:EURUSD') == 'EURUSD'
    assert tools.normalize_symbol(None) == 'EURUSD'
    assert tools.normalize_symbol('BTCUSD') is None

    @contextmanager
    def fake():
        yield object()
    monkeypatch.setattr(tools, 'readonly', fake)
    assert 'unknown symbol' in json.loads(tools.run('get_closed_trades', '{"symbol": "BTCUSD"}'))['error']
