"""The "ATR Trend Confluence System" indicator (tradingview/atr_trend_confluence.pine) on the broker's own candles.

A trend-following prototype: an EMA baseline, a Supertrend trailing stop, and a BUY/SELL label on the bar where the
stop flips, kept only when every filter agrees (baseline slope, the previous completed 1h candle's EMA stack, ADX with
+DI/-DI, the Choppiness Index, London/New York morning sessions, distance from the baseline, optionally a recent
break of structure). Like the Pine script it runs on whatever timeframe the chart shows and acts on closed bars only.

It is an indicator, not a tested model: nothing here is published, graded or backtested. The inputs are the script's
defaults for every symbol. Averages are seeded on the first bar and settle over the warmup, as in web/indicators.py.

Repaint safety, as in the script: the forming bar is never judged, and the 1h filter reads the last 1h candle that had
closed before the current one opened (request.security with a one-bar offset and lookahead on).
"""
from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from web.indicators import adx, aggregate, ema, rma, true_range

HTF = 3600                       # the higher timeframe of the directional filter: 1h
HTF_HISTORY = 260 * HTF          # M1 history loaded for it: EMA200 needs 200 closed 1h bars before it means much
WARMUP = 300                     # chart bars before the first one shown, so the EMA, ATR and the stop have settled
SESSIONS = (('London', 'Europe/London', 7, 11), ('New York', 'America/New_York', 8, 11))


@dataclass(frozen=True)
class TrendConfig:
    """The Pine script's inputs, at its defaults."""
    base_len: int = 50
    st_len: int = 14
    st_mult: float = 2.8
    htf_fast: int = 50
    htf_slow: int = 200
    di_len: int = 14
    adx_min: float = 20.0
    chop_len: int = 14
    max_chop: float = 55.0
    max_extension: float = 1.0
    use_htf: bool = True
    use_adx: bool = True
    use_chop: bool = True
    use_session: bool = True
    use_bos: bool = False
    bos_lookback: int = 8
    pivot_len: int = 3


def supertrend(bars: list[dict], atr: list[float], mult: float) -> tuple[list[float], list[int]]:
    """Pine ta.supertrend: the trailing line and its direction per bar (-1 = uptrend, line below price; 1 = downtrend).
    A band only tightens while price stays on its side; a close through the active band flips the trend."""
    line, direction = [], []
    upper = lower = 0.0
    for i, bar in enumerate(bars):
        mid = (bar['h'] + bar['l']) / 2
        basic_upper, basic_lower = mid + mult * atr[i], mid - mult * atr[i]
        if i == 0:
            upper, lower, trend = basic_upper, basic_lower, 1
        else:
            previous = bars[i - 1]['c']
            lower = basic_lower if basic_lower > lower or previous < lower else lower
            upper = basic_upper if basic_upper < upper or previous > upper else upper
            if direction[-1] == 1:
                trend = -1 if bar['c'] > upper else 1
            else:
                trend = 1 if bar['c'] < lower else -1
        direction.append(trend)
        line.append(lower if trend == -1 else upper)
    return line, direction


def choppiness(bars: list[dict], length: int) -> list[float | None]:
    """Choppiness Index: 100 * log10(sum of true range / high-low range) / log10(length). High = sideways."""
    ranges, out = true_range(bars), []
    for i in range(len(bars)):
        if i < length - 1:
            out.append(None)
            continue
        window = bars[i - length + 1:i + 1]
        total = sum(ranges[i - length + 1:i + 1])
        span = max(b['h'] for b in window) - min(b['l'] for b in window)
        out.append(100 * math.log10(total / span) / math.log10(length) if total > 0 and span > 0 else None)
    return out


def sessions(timestamp: int) -> list[str]:
    """Morning sessions open at this bar's opening time: London 07-11 and New York 08-11, local time, Monday to Friday."""
    stamp = datetime.fromtimestamp(timestamp, timezone.utc)
    found = []
    for name, zone, start, end in SESSIONS:
        local = stamp.astimezone(ZoneInfo(zone))
        if local.weekday() < 5 and start <= local.hour < end:
            found.append(name)
    return found


def structure(bars: list[dict], pivot: int, lookback: int) -> tuple[list[bool], list[bool]]:
    """Per bar: did a close break the last confirmed swing high (bullish BOS) / low (bearish) within `lookback` bars?
    A swing is confirmed `pivot` bars after it forms, so nothing here looks ahead."""
    swing_high = swing_low = None
    high_at = low_at = bull_at = bear_at = None
    bull, bear = [], []
    for i, bar in enumerate(bars):
        before_high, before_low = swing_high, swing_low
        centre = i - pivot
        if centre - pivot >= 0:
            left, right = bars[centre - pivot:centre], bars[centre + 1:i + 1]
            high, low = bars[centre]['h'], bars[centre]['l']
            if all(high > b['h'] for b in left) and all(high >= b['h'] for b in right):
                swing_high, high_at = high, i
            if all(low < b['l'] for b in left) and all(low <= b['l'] for b in right):
                swing_low, low_at = low, i
        if (swing_high is not None and before_high is not None and i > high_at
                and bar['c'] > swing_high and bars[i - 1]['c'] <= before_high):
            bull_at = i
        if (swing_low is not None and before_low is not None and i > low_at
                and bar['c'] < swing_low and bars[i - 1]['c'] >= before_low):
            bear_at = i
        bull.append(bull_at is not None and i - bull_at <= lookback)
        bear.append(bear_at is not None and i - bear_at <= lookback)
    return bull, bear


def higher_timeframe(m1: list[dict], cfg: TrendConfig) -> dict:
    hourly = aggregate(m1, HTF)
    closes = [bar['c'] for bar in hourly]
    return {'starts': [bar['t'] for bar in hourly], 'close': closes,
            'fast': ema(closes, cfg.htf_fast), 'slow': ema(closes, cfg.htf_slow)}


def htf_reading(htf: dict, t: int) -> dict | None:
    """The 1h candle before the one containing `t`: the last one that had closed when this chart bar opened."""
    i = bisect_left(htf['starts'], t - t % HTF) - 1
    if i < 0:
        return None
    return {'close': htf['close'][i], 'fast': htf['fast'][i], 'slow': htf['slow'][i], 'bars': i + 1}


def evaluate(m1: list[dict], seconds: int, cfg: TrendConfig) -> list[dict]:
    """One row per closed chart bar: every reading, the trend state, and what blocks a BUY or a SELL on that bar."""
    if not m1:
        return []
    last_minute = m1[-1]['t']
    bars = [bar for bar in aggregate(m1, seconds) if bar['t'] + seconds <= last_minute + 60]
    if not bars:
        return []
    closes = [bar['c'] for bar in bars]
    baseline = ema(closes, cfg.base_len)
    atr = rma(true_range(bars), cfg.st_len)
    line, direction = supertrend(bars, atr, cfg.st_mult)
    strength, plus, minus = adx(bars, cfg.di_len)
    chop = choppiness(bars, cfg.chop_len)
    bos_bull, bos_bear = structure(bars, cfg.pivot_len, cfg.bos_lookback)
    htf_on = cfg.use_htf and seconds < HTF
    htf = higher_timeframe(m1, cfg) if htf_on else None
    rows = []
    for i, bar in enumerate(bars):
        close, base = bar['c'], baseline[i]
        rising, falling = i > 0 and base > baseline[i - 1], i > 0 and base < baseline[i - 1]
        hour = htf_reading(htf, bar['t']) if htf_on else None
        hour_bull = bool(hour) and hour['close'] > hour['fast'] > hour['slow']
        hour_bear = bool(hour) and hour['close'] < hour['fast'] < hour['slow']
        active = sessions(bar['t'])
        calm = chop[i] is not None and chop[i] < cfg.max_chop
        near = abs(close - base) <= atr[i] * cfg.max_extension
        strong = strength[i] >= cfg.adx_min

        def blocked(buy: bool) -> list[str]:
            reasons = []
            if not ((close > base and rising) if buy else (close < base and falling)):
                reasons.append('baseline_not_aligned')
            if htf_on and not (hour_bull if buy else hour_bear):
                reasons.append('htf_not_aligned')
            if cfg.use_adx and not (strong and (plus[i] > minus[i] if buy else minus[i] > plus[i])):
                reasons.append('adx_weak_or_against')
            if cfg.use_chop and not calm:
                reasons.append('choppy')
            if cfg.use_session and not active:
                reasons.append('outside_session')
            if cfg.use_bos and not (bos_bull[i] if buy else bos_bear[i]):
                reasons.append('no_recent_bos')
            if not near:
                reasons.append('extended_from_baseline')
            return reasons

        flip = None
        if i > 0 and direction[i] != direction[i - 1]:
            flip = 'BUY' if direction[i] == -1 else 'SELL'
        rows.append({'t': bar['t'], 'close': close, 'baseline': base, 'rising': rising, 'falling': falling,
                     'trail': line[i], 'up': direction[i] == -1, 'atr': atr[i], 'adx': strength[i], 'plus_di': plus[i],
                     'minus_di': minus[i], 'chop': chop[i], 'sessions': active, 'htf': hour, 'htf_bull': hour_bull,
                     'htf_bear': hour_bear, 'bos_bull': bos_bull[i], 'bos_bear': bos_bear[i], 'flip': flip,
                     'buy_blocked': blocked(True), 'sell_blocked': blocked(False)})
    return rows


def table(row: dict, seconds: int, cfg: TrendConfig) -> dict:
    """The readings on the last closed bar: the WHY behind a label, or behind its absence."""
    htf_on = cfg.use_htf and seconds < HTF
    hour = row['htf']
    extension = abs(row['close'] - row['baseline']) / row['atr'] if row['atr'] else 0.0
    side = 'above' if row['close'] > row['baseline'] else 'below'
    slope = 'rising' if row['rising'] else 'falling' if row['falling'] else 'flat'
    aligned = (row['close'] > row['baseline'] and row['rising']) or (row['close'] < row['baseline'] and row['falling'])
    if not htf_on:
        hourly = {'reading': 'off on 1h and above', 'status': 'off', 'ok': True}
    elif not hour:
        hourly = {'reading': 'no closed 1h candle yet', 'status': 'no data', 'ok': False}
    else:
        settled = hour['bars'] >= cfg.htf_slow
        hourly = {'reading': f'{hour["bars"]} 1h bars' + ('' if settled else f' of {cfg.htf_slow}: EMA{cfg.htf_slow} not settled'),
                  'status': 'bullish' if row['htf_bull'] else 'bearish' if row['htf_bear'] else 'mixed',
                  'ok': row['htf_bull'] or row['htf_bear'], 'settled': settled}
    dominant = '+DI' if row['plus_di'] > row['minus_di'] else '-DI'
    blocked = row['buy_blocked'] if row['up'] else row['sell_blocked']
    return {
        'trail': {'reading': round(row['trail'], 5), 'status': 'uptrend' if row['up'] else 'downtrend', 'ok': True},
        'baseline': {'reading': f'price {side}, EMA{cfg.base_len} {slope}',
                     'status': ('bullish' if row['rising'] else 'bearish') if aligned else 'mixed', 'ok': aligned},
        'htf': hourly,
        'adx': {'reading': f'{row["adx"]:.1f} (min {cfg.adx_min:g}), {dominant} leads',
                'status': 'trending' if row['adx'] >= cfg.adx_min else 'weak', 'ok': row['adx'] >= cfg.adx_min},
        'chop': {'reading': f'{row["chop"]:.1f} (max {cfg.max_chop:g})' if row['chop'] is not None else 'n/a',
                 'status': 'directional' if row['chop'] is not None and row['chop'] < cfg.max_chop else 'choppy',
                 'ok': row['chop'] is not None and row['chop'] < cfg.max_chop},
        'session': {'reading': ' + '.join(row['sessions']) or 'outside London/New York mornings',
                    'status': 'open' if row['sessions'] else 'filtered', 'ok': bool(row['sessions'])},
        'extension': {'reading': f'{extension:.2f} ATR from the baseline (max {cfg.max_extension:g})',
                      'status': 'near' if extension <= cfg.max_extension else 'extended', 'ok': extension <= cfg.max_extension},
        'structure': {'reading': 'bullish BOS' if row['bos_bull'] else 'bearish BOS' if row['bos_bear'] else 'no recent break',
                      'status': 'required' if cfg.use_bos else 'info only', 'ok': True},
        # A label needs the stop to flip on a bar where nothing blocks it. Between flips this says what would.
        'signal': {'status': row['flip'] if row['flip'] and not blocked else 'wait', 'ok': bool(row['flip']) and not blocked,
                   'trend': 'up' if row['up'] else 'down', 'flipped_this_bar': row['flip'],
                   'buy_blocked': row['buy_blocked'], 'sell_blocked': row['sell_blocked']},
    }


def build(symbol: str, tf: str, m1: list[dict], seconds: int, show: int, cfg: TrendConfig = TrendConfig()) -> dict:
    """Lines, flips and filtered signals for the last `show` closed bars, and the table on the newest. `m1` includes warmup."""
    rows = evaluate(m1, seconds, cfg)
    shown = rows[-show:]
    flips = [{'t': row['t'], 'bar_time': row['t'] + seconds, 'direction': row['flip'], 'price': row['close'],
              'trail': round(row['trail'], 5), 'atr': round(row['atr'], 5),
              'blocked_by': row['buy_blocked'] if row['flip'] == 'BUY' else row['sell_blocked']}
             for row in shown if row['flip']]
    for flip in flips:
        flip['passed'] = not flip['blocked_by']
    last = rows[-1] if rows else None
    htf_on = cfg.use_htf and seconds < HTF
    hours = last['htf']['bars'] if last and last['htf'] else 0
    return {'symbol': symbol, 'tf': tf, 'name': 'ATR Trend Confluence System', 'bars': len(rows),
            'at': last['t'] if last else None, 'bar_time': last['t'] + seconds if last else None,
            'params': asdict(cfg),
            'htf': {'tf': '1h', 'enabled': htf_on, 'bars': hours, 'settled': not htf_on or hours >= cfg.htf_slow},
            'baseline': [{'t': row['t'], 'v': round(row['baseline'], 5)} for row in shown],
            'trail': [{'t': row['t'], 'v': round(row['trail'], 5), 'dir': 'up' if row['up'] else 'down'} for row in shown],
            'signals': [flip for flip in flips if flip['passed']], 'flips': flips,
            # Too few bars for the baseline and the stop to mean anything: no verdict rather than a wrong one.
            'table': table(last, seconds, cfg) if last and len(rows) > 2 * cfg.base_len else None}
