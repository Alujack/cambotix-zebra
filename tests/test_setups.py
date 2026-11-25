import random

import pytest

from app.domain import classic_rules, trade_plan
from web import setups


@pytest.fixture(autouse=True)
def rules(monkeypatch):
    monkeypatch.setenv('FILTER_SESSIONS', 'false')
    monkeypatch.setenv('MIN_ADX', '20')
    monkeypatch.setenv('MIN_ATR_PERCENT', '0.02')
    monkeypatch.setenv('MAX_ATR_PERCENT', '0.5')
    monkeypatch.setenv('TP_R_MULTIPLES', '1,2,3,4')
    monkeypatch.setenv('STOP_ATR_MULTIPLE', '1.5')


def market(seed: int = 7, count: int = 900) -> list[dict]:
    """15m bars: quiet chop, then alternating trend legs, so both sides set up now and then."""
    rng, price, bars = random.Random(seed), 3000.0, []
    for i in range(count):
        drift = 0.0 if i < 300 else (0.9 if (i // 120) % 2 else -0.9)
        close = price + drift + rng.gauss(0, 2.0)
        bars.append({'t': 1_790_000_100 // 900 * 900 + i * 900, 'o': price, 'h': max(price, close) + abs(rng.gauss(0, 1)),
                     'l': min(price, close) - abs(rng.gauss(0, 1)), 'c': close, 'n': 15})
        price = close
    return bars


def test_candidates_are_exactly_what_the_analyzer_would_accept():
    bars = market()
    result = setups.build('XAUUSD', bars, 600)
    assert {item['direction'] for item in result['candidates']} == {'BUY', 'SELL'}
    rows = {row['t']: row for row in setups.readings(bars)}
    times = [bar['t'] for bar in bars]
    for item in result['candidates']:
        direction = item['direction'] + '_SETUP'
        signal = setups.signal_for('XAUUSD', rows[item['t']], direction)
        previous = rows[times[times.index(item['t']) - 1]]
        # Every rule holds on the bar, and did not on the bar before it (Pine: setup and not setup[1]).
        assert classic_rules(signal) == [] and setups.failures('XAUUSD', previous, direction) != []
        plan = trade_plan(signal)
        assert (item['entry'], item['stop'], item['basis']) == (plan['entry'], plan['stop'], plan['basis'])
        assert [target['price'] for target in item['targets']] == [price for _, price, _ in plan['targets']]
        assert item['bar_time'] == item['t'] + 900 and item['t'] >= times[-600]


def test_no_bar_left_out_of_the_window_is_marked_and_the_table_reads_the_last_bar():
    bars = market()
    every = {(item['t'], item['direction']) for item in setups.build('XAUUSD', bars, 600)['candidates']}
    recent = setups.build('XAUUSD', bars, 300)
    # The shorter window is the tail of the longer one, not a different computation.
    assert {(item['t'], item['direction']) for item in recent['candidates']} == {pair for pair in every if pair[0] >= bars[-300]['t']}
    table = recent['table']
    assert recent['at'] == bars[-1]['t'] and table['session'] == {'reading': 'closed', 'status': 'open', 'ok': True}
    assert table['setup']['status'] in ('BUY', 'SELL', 'wait')
    assert (table['setup']['status'] == 'wait') == bool(table['setup']['buy_failures'] and table['setup']['sell_failures'])


def test_the_forming_bar_is_never_judged():
    bars = market(count=10)
    last_minute = bars[-1]['t'] + 14 * 60                 # the newest 15m bar has all its minutes
    assert setups.closed_bars(bars, last_minute) == bars
    assert setups.closed_bars(bars, last_minute - 60) == bars[:-1]
    assert setups.closed_bars(bars, None) == []
    assert setups.build('XAUUSD', bars, 300)['table'] is None   # too short for EMA200: no verdict rather than a wrong one
