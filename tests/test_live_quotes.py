import asyncio
import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app import ledger, main, quotes
from web import api


def test_fold_builds_the_minute_bar_and_skips_old_and_future_ticks():
    now = 1_790_000_000_000
    minute = now // 60_000 * 60_000 - 120_000
    quote, applied = quotes.fold(None, [(minute + 900, 101.0, 101.2), (minute + 100, 100.0, 100.2),
                                        (minute + 500, 99.5, 99.7)], now)
    # Applied in time order whatever order they arrived in: the open is the earliest tick, the close the latest.
    assert applied == 3
    assert quote == {'bid': 101.0, 'ask': 101.2, 'tick_ms': minute + 900, 'minute': minute // 1000,
                     'o': 100.0, 'h': 101.0, 'l': 99.5, 'c': 101.0}
    later, applied = quotes.fold(quote, [(minute + 800, 50.0, 50.2), (now + 60_000, 200.0, 200.2)], now)
    assert applied == 0 and later == quote
    rolled, applied = quotes.fold(quote, [(minute + 60_000, 102.0, 102.1)], now)
    assert applied == 1 and rolled['minute'] == minute // 1000 + 60
    assert (rolled['o'], rolled['h'], rolled['l'], rolled['c']) == (102.0, 102.0, 102.0, 102.0)


@pytest.fixture
def live(monkeypatch):
    assert os.getenv('DB_NAME') == 'zebra_tests', 'Integration tests require a separate zebra_tests database'
    monkeypatch.setenv('SYMBOLS', 'XAUUSD,BTCUSD')
    with main.database() as conn:
        ledger.migrate(conn)
        quotes.migrate(conn)
        conn.execute('TRUNCATE quotes')
    with TestClient(main.app, headers={'X-Zebra-Token': os.environ['ANALYZER_TOKEN']}) as client:
        yield client


def minute_ago(minutes: int = 2) -> int:
    return (int(time.time() * 1000) // 60_000 - minutes) * 60_000


def stored(symbol: str = 'XAUUSD') -> dict:
    with main.database() as conn:
        return conn.execute('SELECT bid, ask, tick_ms, minute, o, h, l, c FROM quotes WHERE symbol=%s', (symbol,)).fetchone()


def test_ticks_require_the_token(live):
    batch = {'symbol': 'XAUUSD', 'ticks': [[minute_ago() + 100, 4000.0, 4000.2]]}
    assert live.post('/ticks', json=batch, headers={'X-Zebra-Token': 'wrong'}).status_code == 401
    assert live.post('/ticks', json=batch, headers={'X-Zebra-Token': ''}).status_code == 401
    assert stored() is None


def test_ticks_keep_high_and_low_between_reads_and_roll_the_minute(live):
    start = minute_ago()
    reply = live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 100, 4000.0, 4000.2],
                                                                     [start + 400, 4003.0, 4003.2]]}).json()
    assert reply == {'symbol': 'XAUUSD', 'applied': 2, 'skipped': 0, 'tick_ms': start + 400}
    live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 900, 3998.5, 3998.7]]})
    live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 1500, 4001.0, 4001.2]]})
    # The 4003.0 high and 3998.5 low came in separate batches and are no longer the latest tick; the bar keeps both.
    assert stored() == {'bid': 4001.0, 'ask': 4001.2, 'tick_ms': start + 1500, 'minute': start // 1000,
                        'o': 4000.0, 'h': 4003.0, 'l': 3998.5, 'c': 4001.0}
    live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 60_050, 4002.0, 4002.3]]})
    row = stored()
    assert row['minute'] == start // 1000 + 60
    assert (row['o'], row['h'], row['l'], row['c']) == (4002.0, 4002.0, 4002.0, 4002.0)


def test_old_and_future_ticks_are_skipped_and_bad_ticks_refused(live):
    start = minute_ago()
    live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 500, 4000.0, 4000.2]]})
    before = stored()
    future = int(time.time() * 1000) + 60_000
    reply = live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 400, 3900.0, 3900.2],
                                                                     [future, 4100.0, 4100.2]]}).json()
    assert reply['applied'] == 0 and reply['skipped'] == 2 and stored() == before
    for ticks in ([[start + 600, 4000.0, 3999.0]], [[start + 600, 0.0, 1.0]], [[start + 600, 4000.0]], []):
        assert live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': ticks}).status_code == 422
    assert live.post('/ticks', json={'symbol': 'GBPJPY', 'ticks': [[start + 600, 190.0, 190.1]]}).status_code == 422
    assert stored() == before


def test_quotes_snapshot_lists_only_public_symbols(live):
    start = minute_ago()
    live.post('/ticks', json={'symbol': 'BTCUSD', 'ticks': [[start + 100, 90000.0, 90010.0]]})
    live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 100, 4000.0, 4000.2]]})
    with TestClient(api.app) as public:
        body = public.get('/quotes').json()
    assert {item['symbol'] for item in body} == {'BTCUSD', 'XAUUSD'}
    btc = next(item for item in body if item['symbol'] == 'BTCUSD')
    assert btc == {'symbol': 'BTCUSD', 'bid': 90000.0, 'ask': 90010.0, 'time_ms': start + 100,
                   'bar': {'t': start // 1000, 'o': 90000.0, 'h': 90000.0, 'l': 90000.0, 'c': 90000.0}}


def test_stream_sends_the_snapshot_first_then_each_update(live):
    start = minute_ago()
    live.post('/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 100, 4000.0, 4000.2]]})

    def data(chunk: str) -> dict:
        assert chunk.startswith('data: ') and chunk.endswith('\n\n')
        return json.loads(chunk[len('data: '):])

    async def scenario():
        hub = api.QuoteHub()
        first = api.quote_events(hub)
        assert await anext(first) == 'retry: 3000\n\n'
        snapshot = data(await asyncio.wait_for(anext(first), 5))
        assert snapshot['symbol'] == 'XAUUSD' and snapshot['bid'] == 4000.0
        # A browser connecting later gets the current quote straight away, without waiting for a change.
        second = api.quote_events(hub)
        assert await anext(second) == 'retry: 3000\n\n'
        assert data(await asyncio.wait_for(anext(second), 1))['bid'] == 4000.0
        await asyncio.to_thread(live.post, '/ticks', json={'symbol': 'XAUUSD', 'ticks': [[start + 700, 4004.0, 4004.2]]})
        for events in (first, second):
            update = data(await asyncio.wait_for(anext(events), 5))
            assert update['time_ms'] == start + 700 and update['bar']['h'] == 4004.0 and update['bar']['o'] == 4000.0
        await first.aclose()
        await second.aclose()
        assert not hub.listeners

    asyncio.run(scenario())
