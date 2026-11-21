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
ICT_FIELDS = ('sweep_level', 'mss_level', 'fvg_high', 'fvg_low', 'entry', 'stop', 'target_liquidity')
EMA_FIELDS = ('ema20', 'ema50', 'ema200', 'swing_high', 'swing_low', 'entry', 'stop', 'target_liquidity')
MSS_FIELDS = ('sweep_level', 'mss_level', 'entry', 'stop', 'target_liquidity')
MODEL_FIELDS = {'classic': CLASSIC_FIELDS, 'crt': CRT_FIELDS, 'ict': ICT_FIELDS, 'ema': EMA_FIELDS, 'mss': MSS_FIELDS}
NUMERIC_FIELDS = ('price', 'atr', 'ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx', 'swing_high', 'swing_low',
                  'sweep_level', 'range_high', 'range_low', 'entry', 'stop', 'target_liquidity', 'mss_level',
                  'fvg_high', 'fvg_low')
NAME_PATTERN = r'^[A-Za-z0-9 _\-/.]*$'
NY = ZoneInfo('America/New_York')

# Bar length of each timeframe: classic runs on 15m bars, CRT on the higher-timeframe candle whose close is the signal,
# ICT on the 5m candle that completed the setup, the EMA scalper on the 1m trigger candle, MSS on the H1 shift candle.
TIMEFRAME_SECONDS = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}
# ICT killzones in New York minutes of the day (scripts/ict_engine.py KILLZONES).
ICT_KILLZONES = {'London': (2 * 60, 5 * 60), 'NY AM': (8 * 60 + 30, 11 * 60)}


class Signal(BaseModel):
    """One setup candidate. `model` selects which field group is mandatory:
    classic = EMA/RSI/MACD/ADX indicator setup on 15m bars;
    crt     = Candle Range Theory: the previous HTF candle's range (range_high/range_low) was swept on one side by
              the next candle (its wick: sweep_level), which closed back inside at `price`;
    ict     = ICT 2022 model on 5m: a killzone sweep of a liquidity pool (sweep_level), a close through the last swing
              (mss_level) and a fair value gap (fvg_low-fvg_high) whose near edge is the limit `entry`;
    ema     = EMA pullback scalp on 1m: the EMA20/50/200 stack, a pullback into EMA20 whose extreme is swing_low
              (buy) or swing_high (sell), market `entry` at the trigger close, `stop` beyond the pullback;
    mss     = liquidity sweep + market structure shift on 1h: a wick through the last swing (swing_low for a buy,
              swing_high for a sell; the wick is sweep_level) that closed back, then a displacement close through
              the opposing swing (mss_level); market `entry` at that close, `stop` beyond the sweep wick."""
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: str = Field(min_length=1, max_length=180, pattern=r'^[A-Za-z0-9_.:\-]+$')
    symbol: str = Field(min_length=3, max_length=20, pattern=r'^[A-Z0-9]+$')
    timeframe: Literal['1m', '5m', '15m', '1h', '4h', '1d']
    bar_time: int = Field(gt=0, strict=True)
    signal: Literal['BUY_SETUP', 'SELL_SETUP']
    model: Literal['classic', 'crt', 'ict', 'ema', 'mss'] = 'classic'
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
    # ICT model (also uses sweep_level, entry, stop, target_liquidity)
    mss_level: float | None = Field(default=None, gt=0)
    fvg_high: float | None = Field(default=None, gt=0)
    fvg_low: float | None = Field(default=None, gt=0)
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
        aliases = {'1': '1m', 'M1': '1m', '5': '5m', 'M5': '5m', '15': '15m', '15M': '15m', '60': '1h', '240': '4h', 'H4': '4h', '4H': '4h', 'D': '1d', '1D': '1d'}
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
        needed = MODEL_FIELDS[self.model]
        missing = [name for name in needed if getattr(self, name) is None]
        if missing:
            raise ValueError(f'{self.model} setup is missing {", ".join(missing)}')
        if self.model == 'classic' and self.timeframe != '15m':
            raise ValueError('classic setups are 15m only')
        if self.model == 'crt' and self.timeframe in ('5m', '15m'):
            raise ValueError('crt setups use the range candle timeframe (1h, 4h or 1d)')
        if self.model == 'ict' and self.timeframe != '5m':
            raise ValueError('ict setups are 5m only')
        if self.model == 'ema' and self.timeframe != '1m':
            raise ValueError('ema setups are 1m only')
        if self.model == 'mss' and self.timeframe != '1h':
            raise ValueError('mss setups are 1h only')
        if self.model == 'mss' and (self.swing_low if self.signal == 'BUY_SETUP' else self.swing_high) is None:
            raise ValueError('mss setup is missing the swept swing (swing_low for a buy, swing_high for a sell)')
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


def ict_symbols() -> set[str]:
    """Symbols the ICT model may signal on. Its backtest held up on EURUSD and lost on gold, so it is opt-in."""
    return {item.strip().upper() for item in os.getenv('ICT_SYMBOLS', 'EURUSD').split(',') if item.strip()}


def ict_killzone(signal: Signal) -> str | None:
    """Killzone the setup candle opened in, or None."""
    opened = datetime.fromtimestamp(signal.bar_time - signal.bar_seconds, timezone.utc).astimezone(NY)
    minute = opened.hour * 60 + opened.minute
    return next((name for name, (start, end) in ICT_KILLZONES.items() if start <= minute < end), None)


def ict_rules(signal: Signal) -> list[str]:
    """ICT 2022 geometry: a killzone setup, a valid FVG with the limit at its near edge, the sweep beyond the entry,
    the stop beyond the sweep, and a target at least ICT_MIN_RR away."""
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    if signal.symbol not in ict_symbols():
        reasons.append('ict_not_enabled_for_symbol')
    opened = datetime.fromtimestamp(signal.bar_time - signal.bar_seconds, timezone.utc).astimezone(NY)
    if opened.weekday() >= 5 and signal.symbol not in session_exempt_symbols():
        reasons.append('weekend_candle')
    elif ict_killzone(signal) is None:
        reasons.append('outside_ict_killzone')
    if not signal.fvg_low < signal.fvg_high:
        reasons.append('invalid_fvg')
    elif not math.isclose(signal.entry, signal.fvg_high if buy else signal.fvg_low, rel_tol=1e-9):
        reasons.append('entry_not_at_fvg_edge')
    if not ((signal.sweep_level < signal.entry) if buy else (signal.sweep_level > signal.entry)):
        reasons.append('sweep_not_beyond_entry')
    if not ((signal.stop < signal.sweep_level) if buy else (signal.stop > signal.sweep_level)):
        reasons.append('stop_not_beyond_sweep')
    risk = abs(signal.entry - signal.stop)
    if risk < 0.3 * signal.atr:
        reasons.append('stop_too_tight')
    reward = (signal.target_liquidity - signal.entry) if buy else (signal.entry - signal.target_liquidity)
    # The target sits exactly at ICT_MIN_RR; payload prices are rounded to 8 decimals, so allow 0.001R of slack.
    if risk <= 0 or reward / risk < float(os.getenv('ICT_MIN_RR', '2.0')) - 1e-3:
        reasons.append('target_too_close')
    return reasons


def ema_symbols() -> set[str]:
    """Symbols the EMA scalper may signal on (EMA_SYMBOLS). It is a forward test: keep it to what was backtested."""
    return {item.strip().upper() for item in os.getenv('EMA_SYMBOLS', 'XAUUSD').split(',') if item.strip()}


def ema_rules(signal: Signal) -> list[str]:
    """EMA pullback scalp geometry: an enabled symbol in London/New York hours, the EMA stack in the trade's direction,
    a market entry at the trigger close, the stop beyond the pullback extreme (0.5 to 5 ATR away) and a target at least
    EMA_MIN_RR away."""
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    if signal.symbol not in ema_symbols():
        reasons.append('ema_not_enabled_for_symbol')
    if signal.symbol not in session_exempt_symbols() and not sessions(signal.bar_time - signal.bar_seconds):
        reasons.append('outside_london_or_new_york_session')
    if not ((signal.price > signal.ema20 > signal.ema50 > signal.ema200) if buy else
            (signal.price < signal.ema20 < signal.ema50 < signal.ema200)):
        reasons.append('trend_mismatch')
    if not math.isclose(signal.entry, signal.price, rel_tol=1e-9):
        reasons.append('entry_not_at_close')
    if not ((signal.stop < signal.swing_low) if buy else (signal.stop > signal.swing_high)):
        reasons.append('stop_not_beyond_pullback')
    risk = abs(signal.entry - signal.stop)
    if risk < 0.5 * signal.atr:
        reasons.append('stop_too_tight')
    elif risk > 5 * signal.atr:
        reasons.append('stop_too_wide')
    reward = (signal.target_liquidity - signal.entry) if buy else (signal.entry - signal.target_liquidity)
    # The target sits exactly at EMA_MIN_RR; payload prices are rounded to 8 decimals, so allow 0.001R of slack.
    if risk <= 0 or reward / risk < float(os.getenv('EMA_MIN_RR', '1.5')) - 1e-3:
        reasons.append('target_too_close')
    return reasons


def mss_symbols() -> set[str]:
    """Symbols the sweep + MSS model may signal on (MSS_SYMBOLS). A forward test: keep it to what was backtested."""
    return {item.strip().upper() for item in os.getenv('MSS_SYMBOLS', 'XAUUSD').split(',') if item.strip()}


def mss_rules(signal: Signal) -> list[str]:
    """Sweep + MSS geometry on H1: an enabled symbol on a weekday candle, the sweep wick beyond the swept swing, the
    shift close through the broken swing, a market entry at that close, the stop beyond the sweep wick (at least
    0.3 ATR away) and a target at least MSS_MIN_RR away."""
    reasons = []
    buy = signal.signal == 'BUY_SETUP'
    if signal.symbol not in mss_symbols():
        reasons.append('mss_not_enabled_for_symbol')
    if signal.symbol not in session_exempt_symbols() and \
            datetime.fromtimestamp(signal.bar_time - signal.bar_seconds, timezone.utc).weekday() >= 5:
        reasons.append('weekend_candle')
    swept = signal.swing_low if buy else signal.swing_high
    if not ((signal.sweep_level < swept < signal.price) if buy else (signal.sweep_level > swept > signal.price)):
        reasons.append('sweep_not_beyond_swing')
    if not ((signal.price > signal.mss_level) if buy else (signal.price < signal.mss_level)):
        reasons.append('no_structure_shift')
    if not math.isclose(signal.entry, signal.price, rel_tol=1e-9):
        reasons.append('entry_not_at_close')
    if not ((signal.stop < signal.sweep_level) if buy else (signal.stop > signal.sweep_level)):
        reasons.append('stop_not_beyond_sweep')
    risk = abs(signal.entry - signal.stop)
    if risk < 0.3 * signal.atr:
        reasons.append('stop_too_tight')
    reward = (signal.target_liquidity - signal.entry) if buy else (signal.entry - signal.target_liquidity)
    # A projected target sits exactly at MSS_MIN_RR; payload prices are rounded to 8 decimals, so allow 0.001R.
    if risk <= 0 or reward / risk < float(os.getenv('MSS_MIN_RR', '2.0')) - 1e-3:
        reasons.append('target_too_close')
    return reasons


MODEL_RULES = {'classic': classic_rules, 'crt': crt_rules, 'ict': ict_rules, 'ema': ema_rules, 'mss': mss_rules}


def technical_rules(signal: Signal, now: float | None = None) -> list[str]:
    reasons = []
    if not freshness(signal, now):
        reasons.append('stale_or_future_signal')
    if news_status(signal.bar_time)['state'] == 'blocked':
        reasons.append('high_impact_news_window')
    return reasons + MODEL_RULES[signal.model](signal)


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
    'ict': ('Evaluate only the supplied ICT 2022 model elements on 5m candles: the liquidity pool swept inside a killzone '
            '(swept_name, sweep_level), the close through the last swing that shifted structure (mss_level), the fair '
            'value gap left by that move (fvg_low-fvg_high) with a limit entry at its near edge, the stop beyond the '
            'sweep, the target in R, and ATR (5m). Judge whether these elements are coherent for the fixed direction.'),
    'ema': ('Evaluate only the supplied EMA pullback scalp elements on 1m candles: the EMA20/EMA50/EMA200 stack, the '
            'pullback extreme (swing_low for a buy, swing_high for a sell) the price resumed from, the market entry at '
            'the trigger close, the stop beyond the pullback, the target in R, and ATR (1m). Judge whether these '
            'elements are coherent for the fixed direction.'),
    'mss': ('Evaluate only the supplied sweep + market structure shift elements on 1h candles: the swing that was '
            'swept (swing_low for a buy, swing_high for a sell) and the sweep wick (sweep_level), the displacement '
            'close through the opposing swing (mss_level) that is the market entry, the stop beyond the sweep wick, '
            'the target (the next swing or a fixed R), and ATR (1h). Judge whether these elements are coherent for '
            'the fixed direction.'),
}


def system_prompt(signal: Signal) -> str:
    return SYSTEM_PROMPT.format(symbol=signal.symbol, timeframe=signal.timeframe, model=signal.model,
                                inputs=MODEL_INPUTS[signal.model])


def trade_plan(signal: Signal) -> dict:
    """Deterministic reference levels computed from the payload, never by the language model.
    classic: stop beyond the prior swing plus a 0.2 ATR buffer when within 1 to 3 ATR, else STOP_ATR_MULTIPLE x ATR;
             targets at TP_R_MULTIPLES multiples of the stop distance (R).
    crt:     market entry at the sweep candle's close, stop beyond its wick, a single target at the opposite extreme
             of the swept range (the backtested plan; no further R multiples).
    ict:     limit at the FVG's near edge, stop beyond the sweep, one target at ICT_MIN_RR (the backtested plan).
    ema:     market entry at the trigger close, stop beyond the pullback extreme, one target at EMA_MIN_RR.
    mss:     market entry at the shift candle's close, stop beyond the sweep wick, one target at the next swing or
             MSS_MIN_RR (the backtested plan)."""
    buy = signal.signal == 'BUY_SETUP'
    sign = 1 if buy else -1
    multiples = [float(m) for m in os.getenv('TP_R_MULTIPLES', '1,2,3,4').split(',') if m.strip()]
    if signal.model == 'crt':
        entry, distance = signal.price, abs(signal.price - signal.stop)
        reward_r = abs(signal.target_liquidity - entry) / distance if distance else 0.0
        target = signal.target_name or ('range high' if buy else 'range low')
        # TP1 is the backtested CRT target; CRT_EXTRA_TARGETS_R adds TP2+ that many R beyond it (runners).
        extras = [float(item) for item in os.getenv('CRT_EXTRA_TARGETS_R', '0.5,1,1.5').split(',')
                  if item.strip().replace('.', '', 1).isdigit()]
        targets = [(round(reward_r, 2), signal.target_liquidity, target)]
        targets += [(round(reward_r + k, 2), signal.target_liquidity + sign * k * distance, '') for k in extras]
        return {'entry': entry, 'entry_note': 'market at the sweep candle close', 'stop': signal.stop, 'risk': distance,
                'risk_atr': distance / signal.atr, 'basis': f'beyond the sweep wick {signal.sweep_level:g}',
                'targets': targets}
    if signal.model == 'ict':
        entry, distance = signal.entry, abs(signal.entry - signal.stop)
        reward_r = abs(signal.target_liquidity - entry) / distance if distance else 0.0
        return {'entry': entry, 'entry_note': 'limit at the FVG edge', 'stop': signal.stop, 'risk': distance,
                'risk_atr': distance / signal.atr, 'basis': f'beyond the sweep {signal.sweep_level:g}',
                'targets': [(round(reward_r, 2), signal.target_liquidity, signal.target_name or '')]}
    if signal.model == 'ema':
        entry, distance = signal.price, abs(signal.price - signal.stop)
        reward_r = abs(signal.target_liquidity - entry) / distance if distance else 0.0
        extreme = signal.swing_low if buy else signal.swing_high
        return {'entry': entry, 'entry_note': 'market at the trigger candle close', 'stop': signal.stop, 'risk': distance,
                'risk_atr': distance / signal.atr, 'basis': f'beyond the pullback {"low" if buy else "high"} {extreme:g}',
                'targets': [(round(reward_r, 2), signal.target_liquidity, signal.target_name or '')]}
    if signal.model == 'mss':
        entry, distance = signal.price, abs(signal.price - signal.stop)
        reward_r = abs(signal.target_liquidity - entry) / distance if distance else 0.0
        return {'entry': entry, 'entry_note': 'market at the shift candle close', 'stop': signal.stop, 'risk': distance,
                'risk_atr': distance / signal.atr, 'basis': f'beyond the sweep wick {signal.sweep_level:g}',
                'targets': [(round(reward_r, 2), signal.target_liquidity, signal.target_name or '')]}
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
    if signal.model == 'ict':
        side = 'low' if buy else 'high'
        return [f'Sweep: {ict_killzone(signal) or "outside"} killzone took the {signal.swept_name or "liquidity " + side} '
                f'to {signal.sweep_level:g}',
                f'Shift: a 5m close {"above" if buy else "below"} the last swing {signal.mss_level:g}',
                f'Gap: FVG {signal.fvg_low:g}-{signal.fvg_high:g}; limit at its edge {signal.entry:g}',
                f'Target: {signal.target_name or "TP1"} at {signal.target_liquidity:g}', news_line(signal)]
    if signal.model == 'ema':
        extreme = signal.swing_low if buy else signal.swing_high
        active = sessions(signal.bar_time - signal.bar_seconds)
        return [f'Trend: 1m EMA20 {signal.ema20:g} {">" if buy else "<"} EMA50 {signal.ema50:g} '
                f'{">" if buy else "<"} EMA200 {signal.ema200:g}',
                f'Pullback: price dipped into EMA20 ({"low" if buy else "high"} {extreme:g}) and resumed with a close at '
                f'{signal.price:g} through the previous candle',
                f'Target: {signal.target_name or "TP1"} at {signal.target_liquidity:g}',
                f'Session: {", ".join(active) if active else "outside London/New York hours"}', news_line(signal)]
    if signal.model == 'mss':
        swept = signal.swing_low if buy else signal.swing_high
        return [f'Sweep: an H1 wick took the last swing {"low" if buy else "high"} {swept:g} to {signal.sweep_level:g} '
                f'and closed back {"above" if buy else "below"} it',
                f'Shift: a displacement H1 close at {signal.price:g} {"above" if buy else "below"} the last swing '
                f'{"high" if buy else "low"} {signal.mss_level:g}',
                f'Target: {signal.target_name or "TP1"} at {signal.target_liquidity:g}', volatility, news_line(signal)]
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
    if model == 'ict':
        opened = datetime.fromtimestamp(bar_time - bar_seconds, timezone.utc).astimezone(NY)
        minute = opened.hour * 60 + opened.minute
        zone = next((name for name, (start, end) in ICT_KILLZONES.items() if start <= minute < end), 'outside')
        return f'{zone} killzone'
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
    if signal.model in ('ict', 'ema', 'mss'):
        pass                      # 5m/1m/1h ATR is not on the 15m percent band's scale; those backtests used no volatility filter
    elif atr_percent >= 0.85 * high:
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
    elif signal.model == 'ema':
        extension = abs(signal.price - signal.ema20) / signal.atr
        if extension > 2:
            found.append(f'Extended: the trigger closed {extension:.1f} ATR from EMA20; a fast scalp, not a swing')
        if plan['risk_atr'] >= 3.5:
            found.append(f'Wide stop: {plan["risk_atr"]:.1f} ATR to the pullback extreme; the target is far for a 1m scalp')
    elif signal.model == 'classic':
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


def message_style() -> str:
    """compact (default): a short phone-readable alert. detailed: every rule reading and the AI commentary."""
    return 'detailed' if os.getenv('MESSAGE_STYLE', 'compact').strip().lower() == 'detailed' else 'compact'


def plain_reason(signal: Signal) -> str:
    """One sentence a person can read on a phone: why this setup exists."""
    buy = signal.signal == 'BUY_SETUP'
    if signal.model == 'crt':
        side, other = ('low', 'high') if buy else ('high', 'low')
        verb = 'dipped below' if buy else 'pushed above'
        return (f'price {verb} the previous {signal.timeframe} range {side} ({signal.sweep_level:g}) and closed back inside. '
                f'Aiming for the range {other}.')
    if signal.model == 'ict':
        pool = signal.swept_name or ('liquidity low' if buy else 'liquidity high')
        return (f'the {ict_killzone(signal) or "session"} killzone swept the {pool} ({signal.sweep_level:g}), then price '
                f'broke structure and left a fair value gap. {"Buy" if buy else "Sell"} on the retrace into it.')
    if signal.model == 'ema':
        extreme = signal.swing_low if buy else signal.swing_high
        return (f'1m {"uptrend" if buy else "downtrend"} (EMA20/50/200 stacked): price pulled back into EMA20 '
                f'({extreme:g}) and resumed. Quick {"buy" if buy else "sell"} for {signal.target_name or "the target"}.')
    if signal.model == 'mss':
        swept = signal.swing_low if buy else signal.swing_high
        return (f'an H1 wick swept the last swing {"low" if buy else "high"} ({swept:g}) and closed back, then a strong '
                f'candle closed {"above" if buy else "below"} the last swing {"high" if buy else "low"} ({signal.mss_level:g}): '
                f'structure shifted. {"Buy" if buy else "Sell"} for {signal.target_name or "the target"}.')
    trend = 'Uptrend' if buy else 'Downtrend'
    return (f'{trend}: price {"above" if buy else "below"} EMA20, EMA50 and EMA200, '
            f'RSI {signal.rsi:.0f}, ADX {signal.adx:.0f} (trend strength).')


def size_line(sizing: dict, risk_distance: float) -> tuple[str, float]:
    """Lots the broker accepts (rounded down to LOT_STEP, never below one step) and the real money at risk.
    When even the minimum lot risks clearly more than RISK_PERCENT, say so instead of hiding it."""
    step = float(os.getenv('LOT_STEP', '0.01'))
    lots = max(step, math.floor(sizing['lots'] / step + 1e-9) * step)
    money = lots * sizing['contract'] * risk_distance
    percent = money / sizing['account'] * 100
    line = f'💰 Size:   {lots:.2f} lots (risk {money:.2f} = {percent:.1f}%)'
    if percent > sizing['percent'] * 1.25:
        line += f'\n⚠️ Minimum lot risks {percent:.1f}%, more than your {sizing["percent"]:g}%: skip or accept'
    return line, lots


def compact_text(signal: Signal, status: str, reasons: list[str], ledger_seq: int | None,
                 warnings: list[str] | None, audience: str = 'private') -> str:
    buy = signal.signal == 'BUY_SETUP'
    decimals = 2 if signal.price >= 100 else 5
    tag = {'crt': 'CRT', 'ict': 'ICT · forward test', 'ema': 'EMA scalp · forward test',
           'mss': 'Sweep+MSS · forward test'}.get(signal.model, 'Classic')
    structural = not [code for code in reasons if code not in AI_STAGE_CODES]
    lines = ['🧪 TEST SIGNAL (made-up prices)'] if synthetic(signal.event_id) else []
    head = f'{"🟢 BUY" if buy else "🔴 SELL"} {signal.symbol} · {tag} {signal.timeframe}'
    if status != 'approved':
        head += '  ❌ NOT A TRADE'
    lines += [head, '']
    if structural:
        plan = trade_plan(signal)
        if signal.model == 'ict':
            expiry = int(os.getenv('ICT_ENTRY_EXPIRY_MINUTES', '120'))
            order = f'▶️ {"BUY" if buy else "SELL"} LIMIT: {plan["entry"]:.{decimals}f}  (cancel if not filled in {expiry} min)'
        else:
            order = f'▶️ {"BUY" if buy else "SELL"} NOW (market order): {plan["entry"]:.{decimals}f}'
        lines += [order,
                  f'🛑 Stop:   {plan["stop"]:.{decimals}f}  (risk {plan["risk"]:.{decimals}f})']
        for index, (multiple, level, _) in enumerate(plan['targets'], 1):
            label = 'Target' if len(plan['targets']) == 1 else f'TP{index}'
            lines.append(f'🎯 {label}: {level:.{decimals}f}  (+{multiple:g}R)')
        # The owner's account size means nothing to community members: they size their own trades.
        sizing = position_size(signal, plan['risk']) if audience == 'private' else None
        size_text, lots = size_line(sizing, plan['risk']) if sizing else ('', None)
        step = float(os.getenv('LOT_STEP', '0.01'))
        if len(plan['targets']) > 1:
            # Scaling out needs one minimum lot per target; a smaller position closes in full at TP1.
            splittable = lots is None or lots + 1e-9 >= step * len(plan['targets'])
            lines.append('↪️ After TP1: close part, move stop to entry' if splittable
                         else '↪️ Lot too small to split: close all at TP1')
        if size_text:
            lines.append(size_text)
        lines.append('')
    lines.append('Why: ' + plain_reason(signal))
    lines += ['⚠️ ' + item for item in warnings or []]
    if reasons:
        lines.append('Not valid: ' + ', '.join(code.replace('_', ' ') for code in reasons))
    news = news_status(signal.bar_time)
    lines.append({'blocked': f'📰 News: BLOCKED ({news["detail"]})', 'clear': '📰 News: clear'}.get(news['state'], '📰 News: not checked'))
    footer = f'Ledger #{ledger_seq} · ' if ledger_seq is not None else ''
    if audience == 'community':
        lines += ['', footer + 'Size your own trade: risk 0.5-1% of your account. Not financial advice.']
    else:
        lines += ['', footer + ('Manual review. No order placed.' if status == 'approved' else 'No action.')]
    return '\n'.join(lines)[:4000]


def notification_text(signal: Signal, status: str, analysis: dict | None, reasons: list[str],
                      ledger_seq: int | None = None, warnings: list[str] | None = None, audience: str = 'private') -> str:
    if message_style() == 'compact' or audience == 'community':
        return compact_text(signal, status, reasons, ledger_seq, warnings, audience)
    buy = signal.signal == 'BUY_SETUP'
    direction = 'BUY' if buy else 'SELL'
    decimals = 2 if signal.price >= 100 else 5
    icon = {'approved': '✅', 'rejected': '❌', 'error': '⚠️'}.get(status, '•')
    tag = {'crt': 'CRT', 'ict': 'ICT forward test', 'ema': 'EMA scalp forward test',
           'mss': 'Sweep+MSS forward test'}.get(signal.model, 'classic')
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
