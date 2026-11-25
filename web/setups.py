"""The "Cambotix Zebra — 15m setup candidates" indicator (tradingview/gold_setups.pine) on the broker's own candles.

TradingView runs the Pine script on its vendor's prices; this runs the same indicator on the stored Exness M1 candles,
so the website and anything reading the API (the AI included) see exactly what the analyzer would judge. The rules and
levels are not re-implemented: every closed 15m bar is turned into a classic `Signal` and checked with the analyzer's
own `classic_rules` and `trade_plan`. Indicator math is the Wilder smoothing that scripts/mt5_feeder.py mirrors.

As in the Pine script, a candidate is the first closed bar on which every rule holds (`setup and not setup[1]`).
The economic-news block the analyzer adds at publish time is not applied: it only exists for live signals.
"""
from __future__ import annotations

import os

from pydantic import ValidationError

from app.domain import Signal, classic_rules, session_exempt_symbols, sessions, trade_plan
from web.indicators import adx, ema, rma, rsi, true_range

BAR = 900            # the classic rules are defined on 15m candles
WARMUP = 600         # bars before the first one shown, so EMA200 and the Wilder averages have settled (feeder: 600)
SWING_BARS = 10      # Pine `swingBars`: prior high/low lookback, excluding the current bar
DIRECTIONS = {'BUY_SETUP': 'BUY', 'SELL_SETUP': 'SELL'}


def closed_bars(bars: list[dict], last_minute: int | None) -> list[dict]:
    """15m bars whose last minute is stored; the forming bar is dropped, as Pine only acts on confirmed bars."""
    if last_minute is None:
        return []
    return [bar for bar in bars if bar['t'] + BAR <= last_minute + 60]


def readings(bars: list[dict]) -> list[dict]:
    """Per-bar inputs of the classic rules, oldest first."""
    closes = [bar['c'] for bar in bars]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    macd = [fast - slow for fast, slow in zip(ema(closes, 12), ema(closes, 26))]
    hist = [line - signal for line, signal in zip(macd, ema(macd, 9))]
    strength, _, _ = adx(bars)
    atr, momentum = rma(true_range(bars), 14), rsi(closes)
    out = []
    for i, bar in enumerate(bars):
        prior = bars[max(0, i - SWING_BARS):i]
        out.append({'t': bar['t'], 'close': bar['c'], 'ema20': e20[i], 'ema50': e50[i], 'ema200': e200[i],
                    'rsi': momentum[i], 'macd_hist': hist[i], 'adx': strength[i], 'atr': atr[i],
                    'swing_high': max(b['h'] for b in prior) if len(prior) == SWING_BARS else None,
                    'swing_low': min(b['l'] for b in prior) if len(prior) == SWING_BARS else None})
    return out


def signal_for(symbol: str, row: dict, direction: str) -> Signal | None:
    """The payload the feeder would post for this bar (scripts/mt5_feeder.py payload), or None if it cannot exist."""
    close_epoch = row['t'] + BAR
    try:
        return Signal.model_validate({
            'event_id': f'{symbol}-15m-{close_epoch}-{direction}', 'symbol': symbol, 'timeframe': '15m',
            'bar_time': close_epoch, 'signal': direction, 'model': 'classic', 'price': row['close'], 'atr': row['atr'],
            'ema20': row['ema20'], 'ema50': row['ema50'], 'ema200': row['ema200'], 'rsi': row['rsi'],
            'macd_hist': row['macd_hist'], 'adx': row['adx'], 'swing_high': row['swing_high'],
            'swing_low': row['swing_low']})
    except ValidationError:
        return None                                  # e.g. a flat stretch with zero ATR: no setup is possible


def failures(symbol: str, row: dict, direction: str) -> list[str]:
    signal = signal_for(symbol, row, direction)
    return ['invalid_inputs'] if signal is None else classic_rules(signal)


def candidate(symbol: str, row: dict, direction: str) -> dict:
    signal = signal_for(symbol, row, direction)
    plan = trade_plan(signal)
    return {'t': row['t'], 'bar_time': signal.bar_time, 'direction': DIRECTIONS[direction],
            'entry': plan['entry'], 'stop': plan['stop'], 'risk': plan['risk'], 'risk_atr': round(plan['risk_atr'], 2),
            'basis': plan['basis'], 'targets': [{'r': r, 'price': price} for r, price, _ in plan['targets']]}


def table(symbol: str, row: dict) -> dict:
    """The Pine rule table (the WHY), on the last closed bar."""
    low, high = float(os.getenv('MIN_ATR_PERCENT', '0.02')), float(os.getenv('MAX_ATR_PERCENT', '0.5'))
    min_adx = float(os.getenv('MIN_ADX', '20'))
    atr_percent = row['atr'] / row['close'] * 100
    bull = row['close'] > row['ema20'] > row['ema50'] > row['ema200']
    bear = row['close'] < row['ema20'] < row['ema50'] < row['ema200']
    active = sessions(row['t'])
    always = symbol in session_exempt_symbols()
    filtered = os.getenv('FILTER_SESSIONS', 'true').lower() == 'true'
    buy, sell = failures(symbol, row, 'BUY_SETUP'), failures(symbol, row, 'SELL_SETUP')
    return {
        'trend': {'reading': f'EMA20 {">" if row["ema20"] > row["ema50"] else "<"} EMA50, price '
                             f'{"above" if row["close"] > row["ema200"] else "below"} EMA200',
                  'status': 'BUY' if bull else 'SELL' if bear else 'mixed', 'ok': bull or bear},
        'rsi': {'reading': round(row['rsi'], 1), 'status': 'BUY band 50-70' if 50 <= row['rsi'] <= 70 else
                'SELL band 30-50' if 30 <= row['rsi'] <= 50 else 'out of band', 'ok': 30 <= row['rsi'] <= 70},
        'macd_hist': {'reading': round(row['macd_hist'], 5), 'ok': row['macd_hist'] != 0,
                      'status': 'bullish' if row['macd_hist'] > 0 else 'bearish' if row['macd_hist'] < 0 else 'flat'},
        'adx': {'reading': round(row['adx'], 1), 'min': min_adx, 'status': 'trending' if row['adx'] >= min_adx else 'weak',
                'ok': row['adx'] >= min_adx},
        'atr_percent': {'reading': round(atr_percent, 3), 'band': [low, high], 'ok': low <= atr_percent <= high,
                        'status': 'in band' if low <= atr_percent <= high else 'out of band'},
        'session': {'reading': '24/7 market' if always else ' + '.join(active) or 'closed',
                    'status': 'open' if always or active or not filtered else 'filtered',
                    'ok': always or bool(active) or not filtered},
        'setup': {'status': 'BUY' if not buy else 'SELL' if not sell else 'wait', 'ok': not buy or not sell,
                  'buy_failures': buy, 'sell_failures': sell},
    }


def build(symbol: str, bars: list[dict], show: int) -> dict:
    """Candidates among the last `show` closed bars plus the rule table on the newest one. `bars` include warmup."""
    rows = readings(bars)
    first = max(1, len(rows) - show)
    passing = {direction: [not failures(symbol, row, direction) if i >= first - 1 else False for i, row in enumerate(rows)]
               for direction in DIRECTIONS}
    candidates = [candidate(symbol, rows[i], direction)
                  for i in range(first, len(rows)) for direction in DIRECTIONS
                  if passing[direction][i] and not passing[direction][i - 1]]
    last = rows[-1] if rows else None
    return {'symbol': symbol, 'tf': '15m', 'model': 'classic', 'name': 'Cambotix Zebra — 15m setup candidates',
            'bars': len(rows), 'at': last['t'] if last else None, 'bar_time': last['t'] + BAR if last else None,
            'rules': {'min_adx': float(os.getenv('MIN_ADX', '20')), 'min_atr_percent': float(os.getenv('MIN_ATR_PERCENT', '0.02')),
                      'max_atr_percent': float(os.getenv('MAX_ATR_PERCENT', '0.5')),
                      'filter_sessions': os.getenv('FILTER_SESSIONS', 'true').lower() == 'true',
                      'tp_r_multiples': os.getenv('TP_R_MULTIPLES', '1,2,3,4')},
            'candidates': candidates, 'table': table(symbol, last) if last and len(rows) > 200 else None}
