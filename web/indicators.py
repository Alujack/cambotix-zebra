"""Indicator values and verdicts for the website, computed in plain Python from stored broker candles.

Every verdict is derived from the number in code (RSI > 70 overbought, Bollinger %B is a 0-1 ratio, ADX bands),
never written as free text, so the page can never contradict itself.
"""
from __future__ import annotations

import math


def aggregate(candles: list[dict], seconds: int) -> list[dict]:
    """Closed M1 candles -> bars of `seconds`, aligned to the epoch. Partial last bars are kept; callers decide."""
    bars: list[dict] = []
    for c in candles:
        start = c['t'] - c['t'] % seconds
        if bars and bars[-1]['t'] == start:
            bar = bars[-1]
            bar['h'], bar['l'], bar['c'] = max(bar['h'], c['h']), min(bar['l'], c['l']), c['c']
            bar['n'] += 1
        else:
            bars.append({'t': start, 'o': c['o'], 'h': c['h'], 'l': c['l'], 'c': c['c'], 'n': 1})
    return bars


def ema(values: list[float], length: int) -> list[float]:
    out, k = [], 2 / (length + 1)
    for i, value in enumerate(values):
        out.append(value if i == 0 else out[-1] + k * (value - out[-1]))
    return out


def rma(values: list[float], length: int) -> list[float]:
    out = []
    for i, value in enumerate(values):
        out.append(value if i == 0 else out[-1] + (value - out[-1]) / length)
    return out


def rsi(closes: list[float], length: int = 14) -> list[float]:
    gains = [max(closes[i] - closes[i - 1], 0.0) if i else 0.0 for i in range(len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0.0) if i else 0.0 for i in range(len(closes))]
    avg_gain, avg_loss = rma(gains, length), rma(losses, length)
    return [100.0 if loss == 0 else 100 - 100 / (1 + gain / loss) for gain, loss in zip(avg_gain, avg_loss)]


def true_range(bars: list[dict]) -> list[float]:
    return [b['h'] - b['l'] if i == 0 else max(b['h'] - b['l'], abs(b['h'] - bars[i - 1]['c']), abs(b['l'] - bars[i - 1]['c']))
            for i, b in enumerate(bars)]


def adx(bars: list[dict], length: int = 14) -> tuple[list[float], list[float], list[float]]:
    plus, minus = [0.0], [0.0]
    for i in range(1, len(bars)):
        up, down = bars[i]['h'] - bars[i - 1]['h'], bars[i - 1]['l'] - bars[i]['l']
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    tr = rma(true_range(bars), length)
    plus_di = [100 * p / t if t else 0.0 for p, t in zip(rma(plus, length), tr)]
    minus_di = [100 * m / t if t else 0.0 for m, t in zip(rma(minus, length), tr)]
    dx = [100 * abs(p - m) / (p + m) if p + m else 0.0 for p, m in zip(plus_di, minus_di)]
    return rma(dx, length), plus_di, minus_di


def stochastic(bars: list[dict], k_len: int = 14, d_len: int = 3) -> tuple[float, float]:
    ks = []
    for i in range(len(bars)):
        window = bars[max(0, i - k_len + 1):i + 1]
        high, low = max(b['h'] for b in window), min(b['l'] for b in window)
        ks.append(50.0 if high == low else 100 * (bars[i]['c'] - low) / (high - low))
    d = sum(ks[-d_len:]) / min(d_len, len(ks))
    return ks[-1], d


def bollinger_percent_b(closes: list[float], length: int = 20, mult: float = 2.0) -> float:
    window = closes[-length:]
    mean = sum(window) / len(window)
    sd = math.sqrt(sum((x - mean) ** 2 for x in window) / len(window))
    upper, lower = mean + mult * sd, mean - mult * sd
    return 0.5 if upper == lower else (closes[-1] - lower) / (upper - lower)


def snapshot(bars: list[dict]) -> dict | None:
    """Indicator readings on the last bar, with verdicts. Needs 30+ bars; more gives EMA200 meaning."""
    if len(bars) < 30:
        return None
    closes = [b['c'] for b in bars]
    e20, e50, e200 = ema(closes, 20)[-1], ema(closes, 50)[-1], ema(closes, 200)[-1]
    macd_line = [a - b for a, b in zip(ema(closes, 12), ema(closes, 26))]
    hist = macd_line[-1] - ema(macd_line, 9)[-1]
    adx_v, plus_di, minus_di = adx(bars)
    k, d = stochastic(bars)
    pb = bollinger_percent_b(closes)
    atr = rma(true_range(bars), 14)[-1]
    r = rsi(closes)[-1]
    close = closes[-1]
    stack = 'UPTREND' if close > e20 > e50 > e200 else 'DOWNTREND' if close < e20 < e50 < e200 else 'MIXED'
    return {
        'close': close, 'bars': len(bars), 'at': bars[-1]['t'],
        'rsi': {'value': round(r, 2), 'verdict': 'overbought' if r > 70 else 'oversold' if r < 30 else 'neutral', 'tone': 'red' if r > 70 else 'green' if r < 30 else 'neutral', 'percent': round(r, 1)},
        'stoch': {'k': round(k, 2), 'd': round(d, 2), 'verdict': 'overbought' if k > 80 else 'oversold' if k < 20 else 'neutral', 'tone': 'red' if k > 80 else 'green' if k < 20 else 'neutral', 'percent': round(k, 1)},
        'macd_hist': {'value': round(hist, 5), 'verdict': 'bullish' if hist > 0 else 'bearish' if hist < 0 else 'flat', 'tone': 'green' if hist > 0 else 'red' if hist < 0 else 'neutral', 'percent': round(min(100, abs(hist) / atr * 100) if atr else 0, 1)},
        'adx': {'value': round(adx_v[-1], 2), 'plus_di': round(plus_di[-1], 2), 'minus_di': round(minus_di[-1], 2),
                'verdict': 'weak' if adx_v[-1] < 20 else 'strong' if adx_v[-1] <= 40 else 'very strong', 'tone': 'neutral' if adx_v[-1] < 20 else 'gold', 'percent': round(min(100, adx_v[-1] * 2), 1)},
        'bollinger_b': {'value': round(pb, 2), 'verdict': 'above upper band' if pb > 1 else 'below lower band' if pb < 0 else 'inside bands', 'tone': 'red' if pb > 1 else 'green' if pb < 0 else 'neutral', 'percent': round(max(0, min(100, pb * 100)), 1)},
        'atr': {'value': round(atr, 5), 'percent_of_price': round(atr / close * 100, 3), 'verdict': 'quiet' if atr / close < 0.0005 else 'active' if atr / close < 0.003 else 'volatile', 'tone': 'neutral', 'percent': round(min(100, atr / close * 100 / 0.5 * 100), 1)},
        'ema': {'ema20': round(e20, 5), 'ema50': round(e50, 5), 'ema200': round(e200, 5), 'verdict': stack, 'tone': 'green' if stack == 'UPTREND' else 'red' if stack == 'DOWNTREND' else 'neutral',
                'percent': 100 if stack != 'MIXED' else 50},
    }
