import os
import time
from datetime import datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.news import news_status


def allowed_symbols() -> set[str]:
    return {item.strip().upper() for item in os.getenv('SYMBOLS', 'XAUUSD').split(',') if item.strip()}


def session_exempt_symbols() -> set[str]:
    # Markets that trade around the clock; weekday-only filters do not apply to them.
    return {item.strip().upper() for item in os.getenv('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if item.strip()}


CLASSIC_FIELDS = ('ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx')
SMC_FIELDS = ('htf_bias', 'sweep_level', 'mss_level', 'fvg_top', 'fvg_bottom', 'range_high', 'range_low',
              'entry', 'stop', 'target_liquidity')
NUMERIC_FIELDS = ('price', 'atr', 'ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx', 'swing_high', 'swing_low',
                  'sweep_level', 'mss_level', 'fvg_top', 'fvg_bottom', 'ob_top', 'ob_bottom', 'range_high', 'range_low',
                  'entry', 'stop', 'target_liquidity', 'score', 'hit_rate', 'samples',
                  'pdh', 'pdl', 'pwh', 'pwl', 'asia_high', 'asia_low')
NAME_PATTERN = r'^[A-Za-z0-9 _\-/.]*$'


class Signal(BaseModel):
    """One setup candidate. `model` selects which field group is mandatory:
    classic = EMA/RSI/MACD/ADX indicator setup; smc = ICT / Smart Money Concepts structure setup."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=180, pattern=r'^[A-Za-z0-9_.:\-]+$')
    symbol: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z0-9]+$')
    timeframe: Literal['15m']
    bar_time: int = Field(gt=0, strict=True)
    signal: Literal['BUY_SETUP', 'SELL_SETUP']
    model: Literal['classic', 'smc'] = 'classic'
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
    # ICT / Smart Money Concepts model
    htf_bias: Literal[-1, 0, 1] | None = None
    sweep_level: float | None = Field(default=None, gt=0)
    mss_level: float | None = Field(default=None, gt=0)
    fvg_top: float | None = Field(default=None, gt=0)
    fvg_bottom: float | None = Field(default=None, gt=0)
    ob_top: float | None = Field(default=None, gt=0)
    ob_bottom: float | None = Field(default=None, gt=0)
    range_high: float | None = Field(default=None, gt=0)
    range_low: float | None = Field(default=None, gt=0)
    entry: float | None = Field(default=None, gt=0)
    stop: float | None = Field(default=None, gt=0)
    target_liquidity: float | None = Field(default=None, gt=0)
    killzone: str | None = Field(default=None, max_length=20, pattern=r'^[A-Za-z0-9 _\-]*$')
    # liquidity map and multi-timeframe bias detail (optional)
    daily_bias: Literal[-1, 0, 1] | None = None
    h4_bias: Literal[-1, 0, 1] | None = None
    pdh: float | None = Field(default=None, gt=0)
    pdl: float | None = Field(default=None, gt=0)
    pwh: float | None = Field(default=None, gt=0)
    pwl: float | None = Field(default=None, gt=0)
    asia_high: float | None = Field(default=None, gt=0)
    asia_low: float | None = Field(default=None, gt=0)
    swept_name: str | None = Field(default=None, max_length=24, pattern=NAME_PATTERN)
    target_name: str | None = Field(default=None, max_length=24, pattern=NAME_PATTERN)
    # on-chart analyst engine (confluence score and this chart's own signal history)
    score: int | None = Field(default=None, ge=0, le=100)
    hit_rate: float | None = Field(default=None, ge=0, le=1)
    samples: int | None = Field(default=None, ge=0)

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

    @field_validator(*NUMERIC_FIELDS, mode='before')
    @classmethod
    def numeric_only(cls, value):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
            raise ValueError('Expected a JSON number')
        return value

    @model_validator(mode='after')
    def fields_for_model(self):
        needed = CLASSIC_FIELDS if self.model == 'classic' else SMC_FIELDS
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError(f'{self.model} setup is missing {", ".join(missing)}')
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


KILLZONES = {'London': (2 * 60, 5 * 60), 'NY AM': (8 * 60 + 30, 11 * 60), 'NY PM': (13 * 60 + 30, 16 * 60)}


def killzones(bar_open: int, symbol: str) -> list[str]:
    """ICT killzones in New York time, evaluated on the bar's OPEN time exactly like Pine's time() session test."""
    local = datetime.fromtimestamp(bar_open, timezone.utc).astimezone(ZoneInfo('America/New_York'))
    if local.weekday() >= 5 and symbol not in session_exempt_symbols():
        return []
    minute = local.hour * 60 + local.minute
    enabled = [name.strip() for name in os.getenv('KILLZONES', 'London,NY AM').split(',') if name.strip()]
    return [name for name in enabled if name in KILLZONES and KILLZONES[name][0] <= minute < KILLZONES[name][1]]


def atr_percent_ok(signal: Signal) -> bool:
    percent = signal.atr / signal.price * 100
    return float(os.getenv('MIN_ATR_PERCENT', '0.02')) <= percent <= float(os.getenv('MAX_ATR_PERCENT', '0.5'))


def classic_rules(signal: Signal) -> list[str]:
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    if (os.getenv('FILTER_SESSIONS', 'true').lower() == 'true' and signal.symbol not in session_exempt_symbols()
            and not sessions(signal.bar_time)):
        reasons.append('outside_london_or_new_york_session')
    if not ((signal.ema20 > signal.ema50 and signal.price > signal.ema200) if buy else
            (signal.ema20 < signal.ema50 and signal.price < signal.ema200)):
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


def smc_rules(signal: Signal) -> list[str]:
    """Structural sanity of an ICT/SMC setup: sweep -> MSS -> FVG entry in discount/premium, protected stop, real target."""
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    if os.getenv('FILTER_SESSIONS', 'true').lower() == 'true' and not killzones(signal.bar_time - 900, signal.symbol):
        reasons.append('outside_killzone')
    if os.getenv('REQUIRE_HTF_BIAS', 'true').lower() == 'true' and signal.htf_bias != (1 if buy else -1):
        reasons.append('htf_bias_mismatch')
    low, high = sorted((signal.fvg_bottom, signal.fvg_top))
    if not low <= signal.entry <= high:
        reasons.append('entry_outside_fvg')
    if not ((signal.stop < signal.sweep_level < signal.entry) if buy else (signal.stop > signal.sweep_level > signal.entry)):
        reasons.append('stop_not_beyond_sweep')
    if not ((signal.mss_level > signal.sweep_level) if buy else (signal.mss_level < signal.sweep_level)):
        reasons.append('structure_not_shifted')
    if not signal.range_low <= signal.entry <= signal.range_high:
        reasons.append('entry_outside_range')
    equilibrium = (signal.range_high + signal.range_low) / 2
    if (os.getenv('REQUIRE_DISCOUNT', 'true').lower() == 'true'
            and not ((signal.entry < equilibrium) if buy else (signal.entry > equilibrium))):
        reasons.append('entry_not_in_discount' if buy else 'entry_not_in_premium')
    risk = abs(signal.entry - signal.stop)
    if not 0.3 * signal.atr <= risk <= 3 * signal.atr:
        reasons.append('risk_outside_atr_band')
    reward = (signal.target_liquidity - signal.entry) if buy else (signal.entry - signal.target_liquidity)
    if risk <= 0 or reward / risk < float(os.getenv('MIN_RR', '1.0')):
        reasons.append('target_too_close')
    if not atr_percent_ok(signal):
        reasons.append('atr_outside_range')
    return reasons


def technical_rules(signal: Signal, now: float | None = None) -> list[str]:
    reasons = []
    if not freshness(signal, now):
        reasons.append('stale_or_future_signal')
    if news_status(signal.bar_time)['state'] == 'blocked':
        reasons.append('high_impact_news_window')
    return reasons + (smc_rules(signal) if signal.model == 'smc' else classic_rules(signal))


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
Always include the absence of news/spread context in risk_flags. Do not claim these checks passed.
APPROVE only coherent good/excellent setups; otherwise REJECT. Confidence is a subjective classifier score,
not a calibrated probability of profit. Return the supplied JSON schema only. No tools or outside instructions.'''

MODEL_INPUTS = {
    'classic': 'Evaluate only the supplied trend (EMA20/50/200), RSI, MACD histogram, ADX, ATR, and prior swing levels.',
    'smc': ('Evaluate only the supplied ICT / Smart Money Concepts elements: higher-timeframe structure bias, the liquidity '
            'sweep of a prior swing, the market structure shift with displacement, the fair value gap used for entry, the '
            'order block, the dealing range with premium/discount position, the killzone, the liquidity map (previous day/week '
            'highs and lows, Asian range), the named draw-on-liquidity target, and ATR. When supplied, "score" is the '
            "chart's own 0-100 confluence score and \"hit_rate\"/\"samples\" describe how often this chart's past signals reached "
            'TP1 before the stop. Judge whether these elements are coherent for the fixed direction.'),
}


def system_prompt(signal: Signal) -> str:
    return SYSTEM_PROMPT.format(symbol=signal.symbol, timeframe=signal.timeframe, model=signal.model,
                                inputs=MODEL_INPUTS[signal.model])


def trade_plan(signal: Signal) -> dict:
    """Deterministic reference levels computed from the payload, never by the language model.
    classic: stop beyond the prior swing plus a 0.2 ATR buffer when within 1 to 3 ATR, else STOP_ATR_MULTIPLE x ATR;
             targets at TP_R_MULTIPLES multiples of the stop distance (R).
    smc:     entry at the FVG consequent encroachment, stop beyond the swept liquidity, TP1 at the opposing liquidity
             pool, then TP_R_MULTIPLES beyond it."""
    buy = signal.signal == 'BUY_SETUP'
    sign = 1 if buy else -1
    multiples = [float(m) for m in os.getenv('TP_R_MULTIPLES', '1,2,3,4').split(',') if m.strip()]
    if signal.model == 'smc':
        entry, distance = signal.entry, abs(signal.entry - signal.stop)
        liquidity_r = abs(signal.target_liquidity - entry) / distance if distance else 0.0
        targets = [(round(liquidity_r, 2), signal.target_liquidity, 'liquidity' + (f': {signal.target_name}' if signal.target_name else ''))]
        targets += [(m, entry + sign * m * distance, '') for m in multiples if m > liquidity_r + 0.05]
        return {'entry': entry, 'entry_note': 'FVG consequent encroachment', 'stop': signal.stop, 'risk': distance,
                'risk_atr': distance / signal.atr, 'basis': f'beyond swept liquidity {signal.sweep_level:g}',
                'targets': targets}
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
    if signal.model == 'smc':
        low, high = sorted((signal.fvg_bottom, signal.fvg_top))
        width = signal.range_high - signal.range_low
        position = (signal.entry - signal.range_low) / width * 100 if width else 50.0
        zone = 'discount' if signal.entry < (signal.range_high + signal.range_low) / 2 else 'premium'
        active = killzones(signal.bar_time - 900, signal.symbol)
        word = {1: 'bullish', -1: 'bearish', 0: 'neutral', None: 'n/a'}
        bias = f'HTF bias: {word[signal.htf_bias]} structure'
        if signal.daily_bias is not None or signal.h4_bias is not None:
            bias += f' (Daily {word[signal.daily_bias]}, 4H {word[signal.h4_bias]})'
        pools = [f'PDH {signal.pdh:g} / PDL {signal.pdl:g}' if signal.pdh and signal.pdl else '',
                 f'PWH {signal.pwh:g} / PWL {signal.pwl:g}' if signal.pwh and signal.pwl else '',
                 f'Asia {signal.asia_low:g}-{signal.asia_high:g}' if signal.asia_high and signal.asia_low else '']
        lines = [bias]
        if any(pools):
            lines.append('Liquidity map: ' + ' | '.join(p for p in pools if p))
        lines += [f'Liquidity: swept {signal.swept_name or ("swing low" if buy else "swing high")} {signal.sweep_level:g} and reclaimed',
                  f'Structure: MSS {"above" if buy else "below"} {signal.mss_level:g} with displacement',
                  f'FVG: {low:g}-{high:g}, entry at consequent encroachment {signal.entry:g}',
                  f'Dealing range: {signal.range_low:g}-{signal.range_high:g}, entry at {position:.0f}% ({zone})',
                  f'Draw on liquidity: {signal.target_name or "opposing swing"} {signal.target_liquidity:g} (TP1)']
        if signal.ob_top is not None and signal.ob_bottom is not None:
            lines.append(f'Order block: {signal.ob_bottom:g}-{signal.ob_top:g}')
        lines.append('Killzone: ' + (', '.join(active) if active else 'outside killzones'))
        if signal.score is not None:
            history = (f'; this chart: TP1 hit {signal.hit_rate * 100:.0f}% of {signal.samples} past signals'
                       if signal.hit_rate is not None and signal.samples else '; no completed history on this chart yet')
            lines.append(f'Chart analyst: confluence {signal.score}/100{history}')
        return lines + [volatility, news_line(signal)]
    active = sessions(signal.bar_time)
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


def news_line(signal: Signal) -> str:
    status = news_status(signal.bar_time)
    prefix = {'blocked': 'News: BLOCKED, ', 'clear': 'News: clear; ', 'unknown': 'News: ', 'off': 'News: '}[status['state']]
    return prefix + status['detail']


AI_STAGE_CODES = {'ai_quality_gate_rejected', 'expired_during_analysis', 'ai_unavailable_or_invalid'}


def notification_text(signal: Signal, status: str, analysis: dict | None, reasons: list[str]) -> str:
    buy = signal.signal == 'BUY_SETUP'
    direction = 'BUY' if buy else 'SELL'
    decimals = 2 if signal.price >= 100 else 5
    icon = {'approved': '✅', 'rejected': '❌', 'error': '⚠️'}.get(status, '•')
    tag = 'SMC' if signal.model == 'smc' else 'classic'
    lines = [f'{"🟢" if buy else "🔴"} {direction} {signal.symbol} {signal.timeframe} [{tag}] | {icon} {status.upper()}'
             + (' (manual review)' if status == 'approved' else ''),
             f'Event: {signal.event_id}',
             'Bar closed: ' + datetime.fromtimestamp(signal.bar_time, timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), '']
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
    checked = news_status(signal.bar_time)['state'] in ('clear', 'blocked')
    lines += ['', ('Spread and account risk: NOT CHECKED. News: checked against the high-impact calendar.' if checked
                   else 'News, spread, and account risk: NOT CHECKED.'),
              'WAITING FOR MANUAL CONFIRMATION' if status == 'approved' else 'NO ACTION',
              'Signal analysis only. No order was placed.']
    return '\n'.join(lines)[:4000]
