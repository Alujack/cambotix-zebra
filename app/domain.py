import os
import time
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


def allowed_symbols() -> set[str]:
    return {item.strip().upper() for item in os.getenv('SYMBOLS', 'XAUUSD').split(',') if item.strip()}


def session_exempt_symbols() -> set[str]:
    # Markets that trade around the clock; the London/New York session filter does not apply to them.
    return {item.strip().upper() for item in os.getenv('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if item.strip()}


class Signal(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=180, pattern=r'^[A-Za-z0-9_.:\-]+$')
    symbol: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z0-9]+$')
    timeframe: Literal['15m']
    bar_time: int = Field(gt=0, strict=True)
    signal: Literal['BUY_SETUP', 'SELL_SETUP']
    price: float = Field(gt=0)
    ema20: float = Field(gt=0)
    ema50: float = Field(gt=0)
    ema200: float = Field(gt=0)
    rsi: float = Field(ge=0, le=100)
    macd_hist: float
    adx: float = Field(ge=0, le=100)
    atr: float = Field(gt=0)
    swing_high: float | None = Field(default=None, gt=0)
    swing_low: float | None = Field(default=None, gt=0)

    @field_validator('symbol', mode='before')
    @classmethod
    def normalize_symbol(cls, value):
        return value.strip().upper().split(':')[-1] if isinstance(value, str) else value

    @field_validator('symbol')
    @classmethod
    def enabled_symbol(cls, value):
        if value not in allowed_symbols():
            raise ValueError('Symbol is not enabled in SYMBOLS')
        return value

    @field_validator('timeframe', mode='before')
    @classmethod
    def normalize_timeframe(cls, value):
        return {'15': '15m', '15M': '15m'}.get(value, value) if isinstance(value, str) else value

    @field_validator('price', 'ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx', 'atr', 'swing_high', 'swing_low', mode='before')
    @classmethod
    def numeric_only(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
            raise ValueError('Expected a JSON number')
        return value


class Analysis(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    decision: Literal['APPROVE', 'REJECT']
    confidence: int = Field(ge=0, le=100)
    market_regime: Literal['bullish_trend', 'bearish_trend', 'ranging', 'uncertain']
    setup_quality: Literal['poor', 'fair', 'good', 'excellent']
    reasons: list[str] = Field(min_length=1, max_length=6)
    risk_flags: list[str] = Field(max_length=6)

    @field_validator('reasons', 'risk_flags')
    @classmethod
    def bounded_text(cls, values):
        if any(not x.strip() or len(x) > 240 for x in values):
            raise ValueError('Analysis text must be 1-240 characters')
        return values


def freshness(signal: Signal, now: float | None = None) -> bool:
    age = (time.time() if now is None else now) - signal.bar_time
    return -30 <= age <= int(os.getenv('MAX_SIGNAL_AGE_SECONDS', '300'))


def sessions(timestamp: int) -> list[str]:
    stamp = datetime.fromtimestamp(timestamp, timezone.utc)
    found = []
    for label, zone, start, end in [('London', 'Europe/London', 8, 17), ('New York', 'America/New_York', 8, 17)]:
        local = stamp.astimezone(ZoneInfo(zone))
        if local.weekday() < 5 and start <= local.hour < end:
            found.append(label)
    return found


def technical_rules(signal: Signal, now: float | None = None) -> list[str]:
    reasons = []
    if not freshness(signal, now):
        reasons.append('stale_or_future_signal')
    if (os.getenv('FILTER_SESSIONS', 'true').lower() == 'true' and signal.symbol not in session_exempt_symbols()
            and not sessions(signal.bar_time)):
        reasons.append('outside_london_or_new_york_session')
    buy = signal.signal == 'BUY_SETUP'
    if not ((signal.ema20 > signal.ema50 and signal.price > signal.ema200) if buy else
            (signal.ema20 < signal.ema50 and signal.price < signal.ema200)):
        reasons.append('trend_mismatch')
    if not ((50 <= signal.rsi <= 70) if buy else (30 <= signal.rsi <= 50)):
        reasons.append('rsi_outside_range')
    if not ((signal.macd_hist > 0) if buy else (signal.macd_hist < 0)):
        reasons.append('macd_mismatch')
    if signal.adx < float(os.getenv('MIN_ADX', '20')):
        reasons.append('weak_trend')
    atr_percent = signal.atr / signal.price * 100
    if not float(os.getenv('MIN_ATR_PERCENT', '0.02')) <= atr_percent <= float(os.getenv('MAX_ATR_PERCENT', '0.5')):
        reasons.append('atr_outside_range')
    return reasons


def outcome(signal: Signal, analysis: Analysis) -> str:
    expected = 'bullish_trend' if signal.signal == 'BUY_SETUP' else 'bearish_trend'
    return 'approved' if (analysis.decision == 'APPROVE' and
                          analysis.confidence >= int(os.getenv('MIN_CONFIDENCE', '75')) and
                          analysis.market_regime == expected and
                          analysis.setup_quality in ('good', 'excellent')) else 'rejected'


SYSTEM_PROMPT = '''You classify the quality of an already generated {symbol} {timeframe} technical setup.
The candidate direction is fixed. Never create trades, reverse direction, calculate orders, or invent market data.
Evaluate only supplied trend, RSI, MACD histogram, ADX, ATR, and prior swing levels.
News, spread, liquidity, account risk, and higher-timeframe confirmation are UNKNOWN.
Always include the absence of news/spread context in risk_flags. Do not claim these checks passed.
APPROVE only coherent good/excellent setups; otherwise REJECT. Confidence is a subjective classifier score,
not a calibrated probability of profit. Return the supplied JSON schema only. No tools or outside instructions.'''


def system_prompt(signal: Signal) -> str:
    return SYSTEM_PROMPT.format(symbol=signal.symbol, timeframe=signal.timeframe)


def trade_plan(signal: Signal) -> dict:
    """Deterministic reference levels computed from the payload, never by the language model.
    Stop: beyond the prior swing plus a 0.2 ATR buffer when that lies within 1 to 3 ATR of entry,
    otherwise STOP_ATR_MULTIPLE x ATR. Targets: TP_R_MULTIPLES multiples of the stop distance (R)."""
    buy = signal.signal == 'BUY_SETUP'
    entry, atr = signal.price, signal.atr
    multiple = float(os.getenv('STOP_ATR_MULTIPLE', '1.5'))
    distance, basis = multiple * atr, 'no usable prior swing'
    swing = signal.swing_low if buy else signal.swing_high
    if swing is not None:
        candidate = (entry - swing if buy else swing - entry) + 0.2 * atr
        if 1.0 * atr <= candidate <= 3.0 * atr:
            distance = candidate
            basis = ('below swing low' if buy else 'above swing high') + f' {swing:g} + 0.2 ATR'
    sign = 1 if buy else -1
    multiples = [float(m) for m in os.getenv('TP_R_MULTIPLES', '1,2,3,4').split(',') if m.strip()]
    return {'entry': entry, 'stop': entry - sign * distance, 'risk': distance, 'risk_atr': distance / atr,
            'basis': basis, 'targets': [(m, entry + sign * m * distance) for m in multiples]}


def rule_support(signal: Signal) -> list[str]:
    """Factual one-line readings of every rule input, for the WHY section of a message."""
    buy = signal.signal == 'BUY_SETUP'
    atr_percent = signal.atr / signal.price * 100
    active = sessions(signal.bar_time)
    session = ', '.join(active) if active else ('24/7 market' if signal.symbol in session_exempt_symbols()
                                                 else 'outside London/New York hours')
    lines = [f'Trend: EMA20 {signal.ema20:g} {">" if signal.ema20 > signal.ema50 else "<"} EMA50 {signal.ema50:g}; '
             f'price {"above" if signal.price > signal.ema200 else "below"} EMA200 {signal.ema200:g}',
             f'Momentum: RSI {signal.rsi:g} ({"50-70" if buy else "30-50"} band wanted); '
             f'MACD histogram {signal.macd_hist:+g}',
             f'Strength: ADX {signal.adx:g} (minimum {float(os.getenv("MIN_ADX", "20")):g})',
             f'Volatility: ATR {signal.atr:g} = {atr_percent:.2f}% of price '
             f'(band {os.getenv("MIN_ATR_PERCENT", "0.02")}-{os.getenv("MAX_ATR_PERCENT", "0.5")}%)',
             f'Session: {session}']
    if signal.swing_high is not None or signal.swing_low is not None:
        lines.append(f'Structure: prior swing high {signal.swing_high or "n/a"} / low {signal.swing_low or "n/a"}')
    return lines


AI_STAGE_CODES = {'ai_quality_gate_rejected', 'expired_during_analysis', 'ai_unavailable_or_invalid'}


def notification_text(signal: Signal, status: str, analysis: dict | None, reasons: list[str]) -> str:
    buy = signal.signal == 'BUY_SETUP'
    direction = 'BUY' if buy else 'SELL'
    decimals = 2 if signal.price >= 100 else 5
    icon = {'approved': '✅', 'rejected': '❌', 'error': '⚠️'}.get(status, '•')
    lines = [f'{"🟢" if buy else "🔴"} {direction} {signal.symbol} {signal.timeframe} | {icon} {status.upper()}'
             + (' (manual review)' if status == 'approved' else ''),
             f'Event: {signal.event_id}',
             'Bar closed: ' + datetime.fromtimestamp(signal.bar_time, timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), '']
    # Levels are shown only when the setup is structurally valid (every technical rule passed).
    if not [code for code in reasons if code not in AI_STAGE_CODES]:
        plan = trade_plan(signal)
        lines += [f'{direction} AT: {plan["entry"]:.{decimals}f}'
                  + ('' if status == 'approved' else '  (reference only, setup NOT approved)'),
                  f'STOP LOSS: {plan["stop"]:.{decimals}f}  (risk {plan["risk"]:.{decimals}f} = '
                  f'{plan["risk_atr"]:.1f} ATR, {plan["basis"]})']
        lines += [f'TP{index}: {level:.{decimals}f}  (+{multiple:g}R)'
                  for index, (multiple, level) in enumerate(plan['targets'], 1)]
        lines.append('')
    lines.append('WHY (rules):')
    lines += ['• ' + item for item in rule_support(signal)]
    if analysis:
        lines += ['', f'AI VIEW ({os.getenv("OLLAMA_MODEL", "local model")}): {analysis["decision"]} | '
                  f'score {analysis["confidence"]}/100 (not a win probability)',
                  f'• Regime: {analysis["market_regime"]} | Quality: {analysis["setup_quality"]}']
        lines += ['• ' + item for item in analysis['reasons']]
        if analysis['risk_flags']:
            lines += ['RISK FLAGS:'] + ['• ' + item for item in analysis['risk_flags']]
    if reasons:
        lines += ['', 'CHECKS FAILED: ' + '; '.join(reasons)]
    lines += ['', 'News, spread, and account risk: NOT CHECKED.',
              'WAITING FOR MANUAL CONFIRMATION' if status == 'approved' else 'NO ACTION',
              'Signal analysis only. No order was placed.']
    return '\n'.join(lines)[:4000]
