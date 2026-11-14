import math
import os
import time
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.news import news_status, next_event


def allowed_symbols() -> set[str]:
    return {item.strip().upper() for item in os.getenv('SYMBOLS', 'XAUUSD').split(',') if item.strip()}


def session_exempt_symbols() -> set[str]:
    # Markets that trade around the clock; weekday-only filters do not apply to them.
    return {item.strip().upper() for item in os.getenv('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if item.strip()}


CLASSIC_FIELDS = ('ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx')
CRT_FIELDS = ('range_high', 'range_low', 'sweep_level', 'entry', 'stop', 'target_liquidity')
NUMERIC_FIELDS = ('price', 'atr', 'ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx', 'swing_high', 'swing_low',
                  'sweep_level', 'range_high', 'range_low', 'entry', 'stop', 'target_liquidity')
NAME_PATTERN = r'^[A-Za-z0-9 _\-/.]*$'
NY = ZoneInfo('America/New_York')

# Bar length of each timeframe: classic runs on 15m bars, CRT on the higher-timeframe candle whose close is the signal.
TIMEFRAME_SECONDS = {'15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}


class Signal(BaseModel):
    """One setup candidate. `model` selects which field group is mandatory:
    classic = EMA/RSI/MACD/ADX indicator setup on 15m bars;
    crt     = Candle Range Theory: the previous HTF candle's range (range_high/range_low) was swept on one side by
              the next candle (its wick: sweep_level), which closed back inside at `price`."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=180, pattern=r'^[A-Za-z0-9_.:\-]+$')
    symbol: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z0-9]+$')
    timeframe: Literal['15m', '1h', '4h', '1d']
    bar_time: int = Field(gt=0, strict=True)
    signal: Literal['BUY_SETUP', 'SELL_SETUP']
    model: Literal['classic', 'crt'] = 'classic'
    price: float = Field(gt=0)
    atr: float = Field(gt=0)
    # classic indicator model
    ema20: float | None = Field(default=None, gt=0)
    ema50: float | None = Field(default=None, gt=0)
    ema200: float | None = Field(default=None, gt=0)
    rsi: float | None = Field(default=None, ge=0, le=100)
    macd_hist: float | None = None
    adx: float | None = Field(default=None, ge=0, le=100)
    swing_high: float | None = Field(default=None, gt=0)
    swing_low: float | None = Field(default=None, gt=0)
    # Candle Range Theory model
    range_high: float | None = Field(default=None, gt=0)
    range_low: float | None = Field(default=None, gt=0)
    sweep_level: float | None = Field(default=None, gt=0)
    entry: float | None = Field(default=None, gt=0)
    stop: float | None = Field(default=None, gt=0)
    target_liquidity: float | None = Field(default=None, gt=0)
    swept_name: str | None = Field(default=None, max_length=24, pattern=NAME_PATTERN)
    target_name: str | None = Field(default=None, max_length=24, pattern=NAME_PATTERN)

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
        aliases = {'15': '15m', '15M': '15m', '60': '1h', '240': '4h', 'H4': '4h', '4H': '4h', 'D': '1d', '1D': '1d'}
        return aliases.get(value, value) if isinstance(value, str) else value

    @property
    def bar_seconds(self) -> int:
        return TIMEFRAME_SECONDS[self.timeframe]

    @field_validator(*NUMERIC_FIELDS, mode='before')
    @classmethod
    def numeric_only(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
            raise ValueError('Expected a JSON number')
        return value

    @model_validator(mode='after')
    def fields_for_model(self):
        needed = CLASSIC_FIELDS if self.model == 'classic' else CRT_FIELDS
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError(f'{self.model} setup is missing {", ".join(missing)}')
        if self.model == 'classic' and self.timeframe != '15m':
            raise ValueError('classic setups are 15m only')
        if self.model == 'crt' and self.timeframe == '15m':
            raise ValueError('crt setups use the range candle timeframe (1h, 4h or 1d)')
        return self


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


def atr_percent_ok(signal: Signal) -> bool:
    percent = signal.atr / signal.price * 100
    return float(os.getenv('MIN_ATR_PERCENT', '0.02')) <= percent <= float(os.getenv('MAX_ATR_PERCENT', '0.5'))


def classic_rules(signal: Signal) -> list[str]:
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    if (os.getenv('FILTER_SESSIONS', 'true').lower() == 'true' and signal.symbol not in session_exempt_symbols()
            and not sessions(signal.bar_time - signal.bar_seconds)):
        reasons.append('outside_london_or_new_york_session')
    if not ((signal.price > signal.ema20 > signal.ema50 > signal.ema200) if buy else
            (signal.price < signal.ema20 < signal.ema50 < signal.ema200)):
        reasons.append('trend_mismatch')
    if not ((50 <= signal.rsi <= 70) if buy else (30 <= signal.rsi <= 50)):
        reasons.append('rsi_outside_range')
    if not ((signal.macd_hist > 0) if buy else (signal.macd_hist < 0)):
        reasons.append('macd_mismatch')
    if signal.adx < float(os.getenv('MIN_ADX', '20')):
        reasons.append('weak_trend')
    if not atr_percent_ok(signal):
        reasons.append('atr_outside_range')
    return reasons


def crt_key_times() -> set[int]:
    """New York open hours of the sweep candle that may signal (CRT_KEY_TIMES, e.g. 1,5,9); empty = every candle."""
    return {int(item) for item in os.getenv('CRT_KEY_TIMES', '').split(',') if item.strip().isdigit()}


def crt_rules(signal: Signal) -> list[str]:
    """Candle Range Theory geometry: one side of the range swept, close back inside, stop beyond the sweep wick,
    target at the opposite range extreme, enough reward for the risk."""
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    opened = datetime.fromtimestamp(signal.bar_time - signal.bar_seconds, timezone.utc).astimezone(NY)
    # Weekday of the candle's last minute: a Monday D1 candle opens Sunday 17:00 New York but is a Monday session.
    last = datetime.fromtimestamp(signal.bar_time - 1, timezone.utc).astimezone(NY)
    if last.weekday() >= 5 and signal.symbol not in session_exempt_symbols():
        reasons.append('weekend_candle')
    keys = crt_key_times()
    if keys and opened.hour not in keys:
        reasons.append('outside_crt_key_times')
    high, low = signal.range_high, signal.range_low
    if not low < high:
        reasons.append('invalid_range')
    if not ((signal.sweep_level < low) if buy else (signal.sweep_level > high)):
        reasons.append('range_not_swept')
    if not low < signal.price < high:
        reasons.append('close_not_back_inside')
    if not ((signal.stop < signal.sweep_level) if buy else (signal.stop > signal.sweep_level)):
        reasons.append('stop_not_beyond_sweep')
    if not math.isclose(signal.target_liquidity, high if buy else low, rel_tol=1e-9):
        reasons.append('target_not_opposite_extreme')
    risk = abs(signal.entry - signal.stop)
    if risk < 0.3 * signal.atr:
        reasons.append('stop_too_tight')
    reward = (signal.target_liquidity - signal.entry) if buy else (signal.entry - signal.target_liquidity)
    if risk <= 0 or reward / risk < float(os.getenv('CRT_MIN_RR', '2.0')):
        reasons.append('target_too_close')
    return reasons


def technical_rules(signal: Signal, now: float | None = None) -> list[str]:
    reasons = []
    if not freshness(signal, now):
        reasons.append('stale_or_future_signal')
    if news_status(signal.bar_time)['state'] == 'blocked':
        reasons.append('high_impact_news_window')
    return reasons + (crt_rules(signal) if signal.model == 'crt' else classic_rules(signal))


def position_size(signal: Signal, risk_distance: float) -> dict | None:
    """Units and lots for RISK_PERCENT of ACCOUNT_SIZE at the plan's stop distance; None when not configured."""
    account = float(os.getenv('ACCOUNT_SIZE', '0') or 0)
    if account <= 0 or risk_distance <= 0:
        return None
    percent = float(os.getenv('RISK_PERCENT', '0.5'))
    contracts = dict(item.split('=', 1) for item in os.getenv('CONTRACT_SIZES', 'XAUUSD=100').split(',') if '=' in item)
    contract = float(contracts.get(signal.symbol, '1') or 1)
    money = account * percent / 100
    units = money / risk_distance
    return {'account': account, 'percent': percent, 'money': money, 'units': units, 'lots': units / contract, 'contract': contract}


SYNTHETIC_PREFIXES = ('demo-synthetic', 'smoke-', 'synthetic-')


def synthetic(event_id: str) -> bool:
    """Test traffic from scripts/demo.py, smoke.py and check-ai.sh: journaled, never put on the track record."""
    return event_id.lower().startswith(SYNTHETIC_PREFIXES)


def gate_mode() -> str:
    """rules (default): the technical rules decide and the model only comments. ai: the model must also approve."""
    return 'ai' if os.getenv('GATE_MODE', 'rules').strip().lower() == 'ai' else 'rules'


def outcome(signal: Signal, analysis: Analysis) -> str:
    expected = 'bullish_trend' if signal.signal == 'BUY_SETUP' else 'bearish_trend'
    return 'approved' if (analysis.decision == 'APPROVE' and
                          analysis.confidence >= int(os.getenv('MIN_CONFIDENCE', '75')) and
                          analysis.market_regime == expected and
                          analysis.setup_quality in ('good', 'excellent')) else 'rejected'


SYSTEM_PROMPT = '''You classify the quality of an already generated {symbol} {timeframe} technical setup from the {model} model.
The candidate direction is fixed. Never create trades, reverse direction, calculate orders, or invent market data.
{inputs}
News, spread, liquidity depth, and account risk are UNKNOWN unless supplied. Higher-timeframe context is unknown unless supplied.
Include only genuinely missing news/spread context in risk_flags. Do not claim an unsupplied check passed.
APPROVE only coherent good/excellent setups; otherwise REJECT. Confidence is a subjective classifier score,
not a calibrated probability of profit. Return the supplied JSON schema only. No tools or outside instructions.'''

MODEL_INPUTS = {
    'classic': 'Evaluate only the supplied trend (EMA20/50/200), RSI, MACD histogram, ADX, ATR, and prior swing levels.',
    'crt': ('Evaluate only the supplied Candle Range Theory elements: the previous higher-timeframe candle range '
            '(range_high/range_low), the next candle sweeping one side of it (sweep_level) and closing back inside the '
            'range (price), the stop beyond the sweep wick, the target at the opposite range extreme, and ATR (15m). '
            'Judge whether these elements are coherent for the fixed direction.'),
}


def system_prompt(signal: Signal) -> str:
    return SYSTEM_PROMPT.format(symbol=signal.symbol, timeframe=signal.timeframe, model=signal.model,
                                inputs=MODEL_INPUTS[signal.model])


def trade_plan(signal: Signal) -> dict:
    """Deterministic reference levels computed from the payload, never by the language model.
    classic: stop beyond the prior swing plus a 0.2 ATR buffer when within 1 to 3 ATR, else STOP_ATR_MULTIPLE x ATR;
             targets at TP_R_MULTIPLES multiples of the stop distance (R).
    crt:     market entry at the sweep candle's close, stop beyond its wick, a single target at the opposite extreme
             of the swept range (the backtested plan; no further R multiples)."""
    buy = signal.signal == 'BUY_SETUP'
    sign = 1 if buy else -1
    multiples = [float(m) for m in os.getenv('TP_R_MULTIPLES', '1,2,3,4').split(',') if m.strip()]
    if signal.model == 'crt':
        entry, distance = signal.price, abs(signal.price - signal.stop)
        reward_r = abs(signal.target_liquidity - entry) / distance if distance else 0.0
        target = signal.target_name or ('range high' if buy else 'range low')
        return {'entry': entry, 'entry_note': 'market at the sweep candle close', 'stop': signal.stop, 'risk': distance,
                'risk_atr': distance / signal.atr, 'basis': f'beyond the sweep wick {signal.sweep_level:g}',
                'targets': [(round(reward_r, 2), signal.target_liquidity, target)]}
    entry, atr = signal.price, signal.atr
    multiple = float(os.getenv('STOP_ATR_MULTIPLE', '1.5'))
    distance, basis = multiple * atr, 'no usable prior swing'
    swing = signal.swing_low if buy else signal.swing_high
    if swing is not None:
        candidate = (entry - swing if buy else swing - entry) + 0.2 * atr
        if 1.0 * atr <= candidate <= 3.0 * atr:
            distance = candidate
            basis = ('below swing low' if buy else 'above swing high') + f' {swing:g} + 0.2 ATR'
    return {'entry': entry, 'entry_note': '', 'stop': entry - sign * distance, 'risk': distance, 'risk_atr': distance / atr,
            'basis': basis, 'targets': [(m, entry + sign * m * distance, '') for m in multiples]}


def rule_support(signal: Signal) -> list[str]:
    """Factual one-line readings of every rule input, for the WHY section of a message."""
    buy = signal.signal == 'BUY_SETUP'
    atr_percent = signal.atr / signal.price * 100
    volatility = (f'Volatility: ATR {signal.atr:g} = {atr_percent:.2f}% of price '
                  f'(band {os.getenv("MIN_ATR_PERCENT", "0.02")}-{os.getenv("MAX_ATR_PERCENT", "0.5")}%)')
    if signal.model == 'crt':
        opened = datetime.fromtimestamp(signal.bar_time - signal.bar_seconds, timezone.utc).astimezone(NY)
        side, other = ('low', 'high') if buy else ('high', 'low')
        width = signal.range_high - signal.range_low
        position = (signal.price - signal.range_low) / width * 100 if width else 50.0
        return [f'Range: previous {signal.timeframe} candle {signal.range_low:g}-{signal.range_high:g}',
                f'Sweep: the {opened:%H:%M} New York {signal.timeframe} candle took the range {side} to '
                f'{signal.sweep_level:g} and closed back inside at {signal.price:g} ({position:.0f}% of the range)',
                f'Target: range {other} {signal.target_liquidity:g} (TP1)',
                volatility, news_line(signal)]
    active = sessions(signal.bar_time - signal.bar_seconds)
    session = ', '.join(active) if active else ('24/7 market' if signal.symbol in session_exempt_symbols()
                                                 else 'outside London/New York hours')
    lines = [f'Trend: EMA20 {signal.ema20:g} {">" if signal.ema20 > signal.ema50 else "<"} EMA50 {signal.ema50:g}; '
             f'price {"above" if signal.price > signal.ema200 else "below"} EMA200 {signal.ema200:g}',
             f'Momentum: RSI {signal.rsi:g} ({"50-70" if buy else "30-50"} band wanted); '
             f'MACD histogram {signal.macd_hist:+g}',
             f'Strength: ADX {signal.adx:g} (minimum {float(os.getenv("MIN_ADX", "20")):g})', volatility,
             f'Session: {session}']
    if signal.swing_high is not None or signal.swing_low is not None:
        lines.append(f'Structure: prior swing high {signal.swing_high or "n/a"} / low {signal.swing_low or "n/a"}')
    return lines + [news_line(signal)]


def session_label(symbol: str, model: str, bar_time: int, bar_seconds: int = 900) -> str:
    """The trading window a setup belongs to, used to group its history."""
    if model == 'crt':
        opened = datetime.fromtimestamp(bar_time - bar_seconds, timezone.utc).astimezone(NY)
        return f'{opened:%H}:00 NY candle'
    active = sessions(bar_time - bar_seconds)
    if len(active) == 2:
        return 'London/New York overlap'
    if active:
        return active[0]
    return '24/7 hours' if symbol in session_exempt_symbols() else 'outside sessions'


def cautions(signal: Signal, events: list | None = None) -> list[str]:
    """Soft warnings on a setup that passed every rule. They never block; they say what is weak about it."""
    found = []
    buy = signal.signal == 'BUY_SETUP'
    plan = trade_plan(signal)
    low, high = float(os.getenv('MIN_ATR_PERCENT', '0.02')), float(os.getenv('MAX_ATR_PERCENT', '0.5'))
    atr_percent = signal.atr / signal.price * 100
    if atr_percent >= 0.85 * high:
        found.append(f'High volatility: ATR {atr_percent:.2f}% is near the {high:g}% limit; expect wide swings')
    elif atr_percent <= 1.25 * low:
        found.append(f'Low volatility: ATR {atr_percent:.2f}% is near the {low:g}% floor; price may stall before TP1')
    if signal.model == 'crt':
        reward = plan['targets'][0][0]
        if reward < 2.5:
            found.append(f'Thin reward: the opposite range extreme is only {reward:.2f}R away')
        width = signal.range_high - signal.range_low
        position = (signal.price - signal.range_low) / width * 100 if width else 50.0
        if (position > 50) if buy else (position < 50):
            found.append(f'Close already past the range midpoint ({position:.0f}%); less room to the target')
    else:
        if (signal.rsi >= 67) if buy else (signal.rsi <= 33):
            found.append(f'Stretched momentum: RSI {signal.rsi:g} is at the edge of its band')
        minimum = float(os.getenv('MIN_ADX', '20'))
        if signal.adx < minimum + 3:
            found.append(f'Weak trend: ADX {signal.adx:g} is only just above the {minimum:g} minimum')
        extension = abs(signal.price - signal.ema20) / signal.atr
        if extension > 1.5:
            found.append(f'Extended: price is {extension:.1f} ATR from EMA20; a pullback is common')
        if plan['basis'] == 'no usable prior swing':
            found.append('No usable prior swing: the stop is a plain ATR multiple, not behind structure')
    event = next_event(signal.bar_time, events)
    horizon = int(os.getenv('NEWS_CAUTION_MIN', '120'))
    if event and event['time'] - signal.bar_time <= horizon * 60:
        found.append(f'News soon: {event["title"]} ({event["country"]}) in {(event["time"] - signal.bar_time) / 60:.0f} min; '
                     'consider waiting or a smaller size')
    return found


def news_line(signal: Signal) -> str:
    status = news_status(signal.bar_time)
    prefix = {'blocked': 'News: BLOCKED, ', 'clear': 'News: clear; ', 'unknown': 'News: ', 'off': 'News: '}[status['state']]
    return prefix + status['detail']


AI_STAGE_CODES = {'ai_quality_gate_rejected', 'expired_during_analysis', 'ai_unavailable_or_invalid'}


def notification_text(signal: Signal, status: str, analysis: dict | None, reasons: list[str],
                      ledger_seq: int | None = None, warnings: list[str] | None = None) -> str:
    buy = signal.signal == 'BUY_SETUP'
    direction = 'BUY' if buy else 'SELL'
    decimals = 2 if signal.price >= 100 else 5
    icon = {'approved': '✅', 'rejected': '❌', 'error': '⚠️'}.get(status, '•')
    tag = 'CRT' if signal.model == 'crt' else 'classic'
    lines = [f'{"🟢" if buy else "🔴"} {direction} {signal.symbol} {signal.timeframe} [{tag}] | {icon} {status.upper()}'
             + (' (manual review)' if status == 'approved' else ''),
             f'Event: {signal.event_id}',
             'Bar closed: ' + datetime.fromtimestamp(signal.bar_time, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')]
    if ledger_seq is not None:
        lines.append(f'Ledger: #{ledger_seq} (graded to its outcome, never removed)')
    elif status == 'approved' and synthetic(signal.event_id):
        lines.append('Ledger: not recorded (synthetic test signal)')
    lines.append('')
    # Levels are shown only when the setup is structurally valid (every technical rule passed).
    if not [code for code in reasons if code not in AI_STAGE_CODES]:
        plan = trade_plan(signal)
        lines += [f'{direction} AT: {plan["entry"]:.{decimals}f}' + (f'  ({plan["entry_note"]})' if plan['entry_note'] else '')
                  + ('' if status == 'approved' else '  (reference only, setup NOT approved)'),
                  f'STOP LOSS: {plan["stop"]:.{decimals}f}  (risk {plan["risk"]:.{decimals}f} = '
                  f'{plan["risk_atr"]:.1f} ATR, {plan["basis"]})']
        lines += [f'TP{index}: {level:.{decimals}f}  (+{multiple:g}R{", " + note if note else ""})'
                  for index, (multiple, level, note) in enumerate(plan['targets'], 1)]
        risk = f'RISK: 1R = {plan["risk"]:.{decimals}f} ({plan["risk"] / signal.price * 100:.2f}% of price) | RR to TP1 {plan["targets"][0][0]:g}'
        sizing = position_size(signal, plan['risk'])
        if sizing:
            risk += (f' | {sizing["percent"]:g}% of {sizing["account"]:g} = {sizing["money"]:.2f} -> '
                     f'{sizing["lots"]:.3f} lots ({sizing["units"]:.2f} units)')
        lines += [risk, '']
    if warnings:
        lines += ['CAUTIONS (the setup is still valid):'] + ['⚠️ ' + item for item in warnings] + ['']
    lines.append('WHY (rules):')
    lines += ['• ' + item for item in rule_support(signal)]
    if analysis:
        label = 'AI VIEW' if gate_mode() == 'ai' else 'AI NOTE (commentary only; the rules decide)'
        lines += ['', f'{label} ({os.getenv("OLLAMA_MODEL", "local model")}): {analysis["decision"]} | '
                  f'score {analysis["confidence"]}/100 (not a win probability)',
                  f'• Regime: {analysis["market_regime"]} | Quality: {analysis["setup_quality"]}']
        lines += ['• ' + item for item in analysis['reasons']]
        if analysis['risk_flags']:
            lines += ['RISK FLAGS:'] + ['• ' + item for item in analysis['risk_flags']]
    if reasons:
        lines += ['', 'CHECKS FAILED: ' + '; '.join(reasons)]
    checked = news_status(signal.bar_time)['state'] in ('clear', 'blocked')
    lines += ['', ('Spread and account risk: NOT CHECKED. News: checked against the high-impact calendar.' if checked
                   else 'News, spread, and account risk: NOT CHECKED.'),
              'WAITING FOR MANUAL CONFIRMATION' if status == 'approved' else 'NO ACTION',
              'Signal analysis only. No order was placed.']
    return '\n'.join(lines)[:4000]
