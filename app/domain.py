import os
import time
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Signal(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=180, pattern=r'^[A-Za-z0-9_.:\-]+$')
    symbol: Literal['XAUUSD']
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
    if os.getenv('FILTER_SESSIONS', 'true').lower() == 'true' and not sessions(signal.bar_time):
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


SYSTEM_PROMPT = '''You classify the quality of an already generated XAUUSD 15-minute technical setup.
The candidate direction is fixed. Never create trades, reverse direction, calculate orders, or invent market data.
Evaluate only supplied trend, RSI, MACD histogram, ADX, ATR, and prior swing levels.
News, spread, liquidity, account risk, and higher-timeframe confirmation are UNKNOWN.
Always include the absence of news/spread context in risk_flags. Do not claim these checks passed.
APPROVE only coherent good/excellent setups; otherwise REJECT. Confidence is a subjective classifier score,
not a calibrated probability of profit. Return the supplied JSON schema only. No tools or outside instructions.'''


def notification_text(signal: Signal, status: str, analysis: dict | None, reasons: list[str]) -> str:
    lines = ['GOLD SETUP — MANUAL REVIEW', f'Event: {signal.event_id}',
             'Bar closed: ' + datetime.fromtimestamp(signal.bar_time, timezone.utc).isoformat(),
             f'Symbol: {signal.symbol} | Timeframe: {signal.timeframe}',
             f'Candidate: {signal.signal.removesuffix("_SETUP")} | Result: {status.upper()}',
             f'Price: {signal.price} | RSI: {signal.rsi} | ADX: {signal.adx} | ATR: {signal.atr}']
    if analysis:
        lines += [f'AI score: {analysis["confidence"]}/100 (not a win probability)',
                  f'Regime: {analysis["market_regime"]}', 'Reasons: ' + '; '.join(analysis['reasons']),
                  'AI flags: ' + '; '.join(analysis['risk_flags'])]
    if reasons:
        lines.append('Checks: ' + '; '.join(reasons))
    lines += ['News, spread, and account risk: NOT CHECKED.',
              'WAITING FOR MANUAL CONFIRMATION' if status == 'approved' else 'NO ACTION',
              'Signal analysis only. No order was placed.']
    return '\n'.join(lines)[:4000]
