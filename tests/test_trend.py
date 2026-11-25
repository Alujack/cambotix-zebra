import random
from datetime import datetime, timezone

from web import trend
from web.indicators import aggregate, rma, true_range

START = 1_790_000_100 // 3600 * 3600
OPEN = trend.TrendConfig(use_htf=False, use_adx=False, use_chop=False, use_session=False, max_extension=1e9)


def minutes(count: int, drift=lambda i: 0.0, noise: float = 0.3, seed: int = 3, price: float = 3000.0) -> list[dict]:
    rng, rows = random.Random(seed), []
    for i in range(count):
        close = price + drift(i) + rng.gauss(0, noise)
        rows.append({'t': START + i * 60, 'o': price, 'h': max(price, close) + abs(rng.gauss(0, noise / 3)),
                     'l': min(price, close) - abs(rng.gauss(0, noise / 3)), 'c': close})
        price = close
    return rows


def legs(i: int) -> float:
    return 0.25 if (i // 900) % 2 == 0 else -0.25           # 15-hour legs up, then down


def test_the_stop_trails_price_and_only_a_close_through_it_flips_the_trend():
    bars = aggregate(minutes(6000, legs), 300)
    line, direction = trend.supertrend(bars, rma(true_range(bars), 14), 2.8)
    flips = 0
    for i in range(1, len(bars)):
        if direction[i] == -1:
            assert bars[i]['c'] >= line[i]                    # uptrend: the line is under the close
            if direction[i - 1] == -1:
                assert line[i] >= line[i - 1]                 # and never steps down while the trend lasts
        else:
            assert bars[i]['c'] <= line[i]
            if direction[i - 1] == 1:
                assert line[i] <= line[i - 1]
        if direction[i] != direction[i - 1]:
            flips += 1
            # The flip bar closed beyond the line that was active on the bar before.
            assert (bars[i]['c'] > line[i - 1]) == (direction[i] == -1)
    assert flips >= 5                                         # the legs really do turn the trend, both ways


def test_a_label_is_a_flip_that_no_filter_blocks():
    # Gentle legs: in a steep trend the stop flips while price is still far on the wrong side of the EMA, so the
    # baseline filter alone drops every flip (true of `legs` above); labels need the turn to happen near the baseline.
    assert trend.build('XAUUSD', '5m', minutes(6000, legs), 300, 900, OPEN)['signals'] == []
    rows = minutes(6000, lambda i: 0.04 if (i // 900) % 2 == 0 else -0.04)
    result = trend.build('XAUUSD', '5m', rows, 300, 900, OPEN)
    assert {flip['direction'] for flip in result['flips']} == {'BUY', 'SELL'}
    assert result['signals'] == [flip for flip in result['flips'] if not flip['blocked_by']] and result['signals']
    # With only the baseline filter left, that is the one reason a flip can be dropped.
    assert {reason for flip in result['flips'] for reason in flip['blocked_by']} <= {'baseline_not_aligned'}
    # Every filter on: nothing new appears, and each dropped flip says why.
    strict = trend.build('XAUUSD', '5m', rows, 300, 900)
    assert [flip['t'] for flip in strict['flips']] == [flip['t'] for flip in result['flips']]
    assert {signal['t'] for signal in strict['signals']} <= {signal['t'] for signal in result['signals']}
    assert all(flip['blocked_by'] for flip in strict['flips'] if not flip['passed'])
    assert [point['t'] for point in strict['trail']] == [point['t'] for point in strict['baseline']]
    assert strict['table']['signal']['trend'] == strict['trail'][-1]['dir']


def test_choppiness_separates_a_trend_from_a_range():
    def bar(i, close, previous):
        return {'t': START + i * 300, 'o': previous, 'h': max(close, previous) + 0.1, 'l': min(close, previous) - 0.1, 'c': close}
    trending = [bar(i, 3000 + 2.0 * (i + 1), 3000 + 2.0 * i) for i in range(40)]
    ranging = [bar(i, 3000 + (1 if i % 2 else -1), 3000 + (-1 if i % 2 else 1)) for i in range(40)]
    assert trend.choppiness(trending, 14)[12] is None
    assert trend.choppiness(trending, 14)[-1] < 38.2 and trend.choppiness(ranging, 14)[-1] > 61.8


def test_sessions_follow_local_market_time():
    def at(*stamp):
        return int(datetime(*stamp, tzinfo=timezone.utc).timestamp())
    assert trend.sessions(at(2026, 11, 25, 9, 0)) == ['London']            # winter: London is UTC
    assert trend.sessions(at(2026, 11, 25, 12, 0)) == []                   # London closed 11:00, New York is 07:00
    assert trend.sessions(at(2026, 11, 25, 13, 30)) == ['New York']        # 08:30 in New York
    assert trend.sessions(at(2026, 7, 1, 6, 30)) == ['London']             # summer: 07:30 in London
    assert trend.sessions(at(2026, 11, 28, 9, 0)) == []                    # Saturday


def test_the_hourly_filter_reads_only_a_candle_that_had_already_closed():
    rows = minutes(1200, lambda i: 0.2)
    cfg = trend.TrendConfig(use_adx=False, use_chop=False, use_session=False, max_extension=1e9)
    before = trend.evaluate(rows, 300, cfg)
    last_hour = rows[-1]['t'] - rows[-1]['t'] % 3600
    # Rewrite everything in the hour still forming: the bars inside it must see the same 1h reading as before.
    crashed = [dict(row, c=row['c'] - 500, l=row['l'] - 500) if row['t'] >= last_hour else row for row in rows]
    after = trend.evaluate(crashed, 300, cfg)
    inside = [i for i, row in enumerate(before) if row['t'] >= last_hour]
    assert inside and all(before[i]['htf'] == after[i]['htf'] for i in inside)
    assert before[0]['htf'] is None and 'htf_not_aligned' in before[0]['buy_blocked']   # no closed 1h candle yet
    result = trend.build('XAUUSD', '5m', rows, 300, 300, cfg)
    assert result['htf'] == {'tf': '1h', 'enabled': True, 'bars': 19, 'settled': False}
    assert 'not settled' in result['table']['htf']['reading']
    assert trend.build('XAUUSD', '1h', rows, 3600, 300, cfg)['htf']['enabled'] is False


def test_structure_breaks_use_confirmed_swings_and_the_forming_bar_is_dropped():
    highs = [10, 11, 12, 15, 12, 11, 10, 11, 12, 13, 16, 17]
    bars = [{'t': START + i * 300, 'o': h - 1, 'h': h, 'l': h - 2, 'c': h - 0.5} for i, h in enumerate(highs)]
    bull, bear = trend.structure(bars, 3, 8)
    # The 15 high (bar 3) is confirmed at bar 6; the first close above it is bar 10 (15.5).
    assert bull == [False] * 10 + [True, True] and not any(bear)
    rows = minutes(601)                                   # 601 minutes: two full 5m bars' worth short of a third
    assert len(trend.evaluate(rows, 300, OPEN)) == 120 and trend.evaluate([], 300, OPEN) == []
    assert trend.build('XAUUSD', '5m', minutes(200), 300, 300, OPEN)['table'] is None
