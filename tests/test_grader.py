import json

from app import ledger
from app.grader import simulate, summarize

BASE = 1_790_000_000 - 1_790_000_000 % 60


def plan(**changes):
    value = {'symbol': 'XAUUSD', 'model': 'classic', 'timeframe': '15m', 'direction': 'BUY', 'bar_time': BASE,
             'published_at': BASE, 'entry_type': 'market', 'entry': 100.0, 'stop': 99.0,
             'targets': [[1, 101.0, ''], [2, 102.0, ''], [3, 103.0, ''], [4, 104.0, '']],
             'entry_expiry_minutes': 120, 'max_hold_minutes': 1440}
    return {**value, **changes}


def candle(minute, o, h, l, c, spread=0.0):
    return {'t': BASE + minute * 60, 'o': o, 'h': h, 'l': l, 'c': c, 'spread': spread}


def run(p, candles, through_minutes=10_000):
    return simulate(p, candles, BASE + through_minutes * 60)


def kinds(events):
    return [event['kind'] for event in events]


def test_buy_market_tp1_then_break_even():
    events = run(plan(), [candle(0, 100, 100.4, 99.6, 100.2), candle(1, 100.2, 101.2, 100.1, 101),
                          candle(2, 101, 101.1, 99.9, 100)])
    assert kinds(events) == ['filled', 'tp1', 'be', 'closed']
    assert events[-1] == {'kind': 'closed', 'time': BASE + 120, 'exit': 'be', 'targets_hit': 1, 'ambiguous': False,
                          'r_tp1': 1.0, 'r_scaled': 0.25}


def test_buy_stop_loss_counts_minus_one_r():
    events = run(plan(), [candle(0, 100, 100.3, 98.9, 99)])
    assert kinds(events) == ['filled', 'sl', 'closed']
    assert events[-1]['r_tp1'] == -1.0 and events[-1]['r_scaled'] == -1.0 and not events[-1]['ambiguous']


def test_candle_hitting_stop_and_target_counts_the_loss():
    events = run(plan(), [candle(0, 100, 100.2, 99.8, 100), candle(1, 100, 101.5, 98.5, 100)])
    assert kinds(events) == ['filled', 'sl', 'closed']
    assert events[-1]['ambiguous'] is True and events[-1]['r_tp1'] == -1.0


def test_spread_is_paid_on_entry():
    events = run(plan(), [candle(0, 100, 100.2, 99.9, 100, spread=0.5), candle(1, 100, 101.1, 100, 101, spread=0.5)])
    assert events[0]['price'] == 100.5
    assert events[1] == {'kind': 'tp1', 'time': BASE + 60, 'price': 101.0, 'r': 0.3333}


def test_sell_limit_fills_then_reaches_every_target():
    sell = plan(direction='SELL', entry_type='limit', entry=100.0, stop=101.0,
                targets=[[1, 99.0, 'liquidity'], [2, 98.0, '']])
    events = run(sell, [candle(0, 99.5, 99.8, 99.4, 99.7, 0.1), candle(1, 99.8, 100.1, 99.7, 100, 0.1),
                        candle(2, 99.8, 99.85, 98.8, 99, 0.1), candle(3, 99, 99.1, 97.8, 98, 0.1)])
    assert kinds(events) == ['filled', 'tp1', 'tp2', 'closed']
    assert events[0]['price'] == 100.0
    assert events[-1]['exit'] == 'final_target' and events[-1]['r_scaled'] == 1.5


def test_limit_fill_candle_cannot_credit_targets():
    buy = plan(entry_type='limit', entry=100.0)
    events = run(buy, [candle(0, 100.5, 101.5, 99.9, 101)], through_minutes=5)
    assert kinds(events) == ['filled']


def test_limit_not_filled_is_recorded():
    buy = plan(entry_type='limit', entry=100.0, entry_expiry_minutes=2)
    waiting = [candle(0, 100.5, 100.8, 100.3, 100.6), candle(1, 100.6, 100.9, 100.4, 100.7)]
    assert run(buy, waiting, through_minutes=2) == [{'kind': 'not_filled', 'time': BASE + 120, 'reason': 'entry_expired'}]
    assert run(buy, waiting, through_minutes=1) == []
    missed = run(buy, [candle(0, 100.5, 101.2, 100.3, 101)])
    assert missed == [{'kind': 'not_filled', 'time': BASE, 'reason': 'tp1_reached_before_entry'}]


def test_market_open_beyond_stop_is_not_filled():
    assert kinds(run(plan(), [candle(0, 98.5, 98.7, 98.2, 98.4)])) == ['not_filled']


def test_limit_gap_beyond_stop_is_not_a_fake_minus_one_r():
    buy = plan(entry_type='limit', entry=100.0)
    assert run(buy, [candle(0, 98.5, 100.2, 98.2, 99.5)]) == [
        {'kind': 'not_filled', 'time': BASE, 'reason': 'opened_beyond_stop'}]
    sell = plan(direction='SELL', entry_type='limit', entry=100.0, stop=101.0,
                targets=[[1, 99.0, 'liquidity']])
    assert run(sell, [candle(0, 101.5, 101.8, 99.8, 100.5)]) == [
        {'kind': 'not_filled', 'time': BASE, 'reason': 'opened_beyond_stop'}]


def test_timeout_closes_at_market():
    events = run(plan(max_hold_minutes=2), [candle(0, 100, 100.4, 99.6, 100.2), candle(1, 100.2, 100.6, 99.8, 100.4),
                                            candle(2, 100.5, 100.7, 100.3, 100.6)])
    assert kinds(events) == ['filled', 'timeout', 'closed']
    assert events[-1]['r_tp1'] == 0.5 and events[-1]['exit'] == 'timeout'


def test_tp1_and_return_to_entry_in_one_candle():
    events = run(plan(), [candle(0, 100, 100.2, 99.8, 100.1), candle(1, 100.1, 102.5, 99.95, 100.5)])
    assert kinds(events) == ['filled', 'tp1', 'be', 'closed']
    assert events[-1]['ambiguous'] is True and events[-1]['r_scaled'] == 0.25


def test_grading_is_incremental_and_deterministic():
    candles = [candle(0, 100, 100.4, 99.6, 100.2), candle(1, 100.2, 101.2, 100.1, 101),
               candle(2, 101, 102.1, 100.9, 102), candle(3, 102, 102.2, 99.9, 100)]
    full = run(plan(), candles)
    for minutes in range(0, 5):
        partial = run(plan(), candles, through_minutes=minutes)
        assert partial == full[:len(partial)]
    assert kinds(full) == ['filled', 'tp1', 'tp2', 'be', 'closed']


def test_summary_and_verdict():
    trade = lambda r: {'r_tp1': r, 'r_scaled': r, 'ambiguous': False}
    result = summarize([trade(1), trade(-1), trade(-1), trade(1.5)], min_trades=3, max_drawdown=5)
    assert result['closed'] == 4 and result['wins'] == 2 and result['win_rate'] == 0.5
    assert result['total_r_tp1'] == 0.5 and result['max_drawdown_r'] == 2.0 and result['profit_factor'] == 1.25
    assert result['verdict'] == 'GO'
    assert summarize([trade(1)], min_trades=3, max_drawdown=5)['verdict'] == 'NOT ENOUGH DATA'
    assert summarize([trade(-1)] * 3, min_trades=3, max_drawdown=5)['verdict'] == 'NO-GO'


def test_chain_verification_detects_any_edit():
    chain, prev = [], ledger.GENESIS
    for seq in range(1, 4):
        body = ledger.canonical({'seq': seq, 'event_id': f'e{seq}', 'kind': 'published', 'time': seq, 'prev': prev})
        prev = ledger.digest(body)
        chain.append({'seq': seq, 'body': body, 'hash': prev})
    assert ledger.verify(chain) == {'valid': True, 'broken_at': None, 'rows': 3, 'head_seq': 3, 'head_hash': prev}
    edited = [dict(row) for row in chain]
    edited[1]['body'] = edited[1]['body'].replace('"time":2', '"time":9')
    assert ledger.verify(edited)['broken_at'] == 2
    assert ledger.verify(chain[:1] + chain[2:])['valid'] is False
    assert json.loads(chain[2]['body'])['prev'] == chain[1]['hash']
