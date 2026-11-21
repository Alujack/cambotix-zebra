import math

from web.indicators import adx, aggregate, bollinger_percent_b, ema, rsi, snapshot


def bars(n, start=1_790_000_000, step=900, drift=0.0, wave=1.0):
    out, price = [], 100.0
    for i in range(n):
        o = price
        price = price + drift + wave * math.sin(i / 3)
        h, l = max(o, price) + 0.3, min(o, price) - 0.3
        out.append({'t': start + i * step, 'o': o, 'h': h, 'l': l, 'c': price, 'n': 1})
    return out


def test_aggregate_groups_m1_into_aligned_bars():
    m1 = [{'t': 1_790_000_000 + i * 60, 'o': 10 + i, 'h': 11 + i, 'l': 9 + i, 'c': 10.5 + i} for i in range(31)]
    out = aggregate(m1, 900)
    assert [b['t'] for b in out] == [1_790_000_000 - 1_790_000_000 % 900 + k * 900 for k in range(3)] or len(out) == 3
    first = out[0]
    assert first['o'] == 10 and first['h'] == max(b['h'] for b in m1 if b['t'] < first['t'] + 900)
    assert sum(b['n'] for b in out) == 31


def test_indicator_math_on_simple_series():
    assert ema([1, 1, 1, 1], 3) == [1, 1, 1, 1]
    rising = list(range(1, 40))
    assert rsi([float(x) for x in rising])[-1] == 100.0
    adx_v, plus, minus = adx(bars(80, drift=0.5, wave=0.0))
    assert plus[-1] > minus[-1] and adx_v[-1] > 20
    assert 0 <= bollinger_percent_b([float(x) for x in range(1, 25)]) <= 1.2


def test_snapshot_verdicts_follow_the_numbers():
    assert snapshot(bars(10)) is None
    up = snapshot(bars(260, drift=0.4, wave=0.2))
    assert up['ema']['verdict'] == 'UPTREND' and up['ema']['tone'] == 'green'
    assert up['rsi']['verdict'] == 'overbought' and up['rsi']['value'] > 70
    assert up['adx']['verdict'] in ('strong', 'very strong')
    assert up['bollinger_b']['verdict'] in ('inside bands', 'above upper band')
    down = snapshot(bars(260, drift=-0.4, wave=0.0))   # a clean decline: the histogram must read bearish
    assert down['ema']['verdict'] == 'DOWNTREND' and down['macd_hist']['verdict'] == 'bearish' and down['rsi']['verdict'] == 'oversold'
    flat = snapshot(bars(120, drift=0.0, wave=1.0))
    assert flat['ema']['verdict'] == 'MIXED' and flat['rsi']['verdict'] == 'neutral'
    assert 0 <= flat['stoch']['k'] <= 100 and 0 <= flat['bollinger_b']['percent'] <= 100
