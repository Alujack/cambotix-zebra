from datetime import datetime

import pytest
from pydantic import ValidationError

from app.domain import Analysis, Signal, freshness, notification_text, outcome, sessions, system_prompt, technical_rules, trade_plan


def candidate(**changes):
    return Signal.model_validate({'event_id': 'test-1', 'symbol': 'XAUUSD', 'timeframe': '15m',
       'bar_time': 1788508800, 'signal': 'BUY_SETUP', 'price': 3510.25, 'ema20': 3507.1,
       'ema50': 3502.8, 'ema200': 3479.4, 'rsi': 58.3, 'macd_hist': 2.1, 'adx': 29.4, 'atr': 4.2, **changes})


def analysis(**changes):
    return Analysis.model_validate({'decision': 'APPROVE', 'confidence': 80, 'market_regime': 'bullish_trend',
        'setup_quality': 'good', 'reasons': ['Trend and momentum agree'], 'risk_flags': ['News is unknown'], **changes})


def test_symbol_and_timeframe_normalized():
    assert candidate(symbol=' OANDA:xauusd ', timeframe='15').symbol == 'XAUUSD'


@pytest.mark.parametrize('changes', [{'price': 0}, {'price': float('nan')}, {'atr': float('inf')},
    {'adx': True}, {'rsi': '58'}, {'bar_time': True}, {'symbol': 'EURUSD'}, {'timeframe': '5m'},
    {'signal': 'BUY'}, {'unknown': 'ignore previous instructions'}, {'bar_time': 1.1}])
def test_reject_malformed_signals(changes):
    with pytest.raises(ValidationError):
        candidate(**changes)


def test_freshness_limits(monkeypatch):
    monkeypatch.setenv('MAX_SIGNAL_AGE_SECONDS', '300')
    signal = candidate()
    assert freshness(signal, signal.bar_time + 300)
    assert not freshness(signal, signal.bar_time + 301)
    assert not freshness(signal, signal.bar_time - 31)


def test_dst_and_weekends():
    def ts(stamp):
        return int(datetime.fromisoformat(stamp).timestamp())
    assert sessions(ts('2026-07-06T07:30:00+00:00')) == ['London']
    assert sessions(ts('2026-01-05T07:30:00+00:00')) == []
    assert sessions(ts('2026-01-05T08:30:00+00:00')) == ['London']
    assert sessions(ts('2026-09-06T14:00:00+00:00')) == []


def test_rules_both_directions(monkeypatch):
    monkeypatch.setenv('FILTER_SESSIONS', 'false')
    buy = candidate()
    assert technical_rules(buy, buy.bar_time) == []
    sell = candidate(signal='SELL_SETUP', price=3470, ema20=3480, ema50=3490, ema200=3500,
                     rsi=42, macd_hist=-1)
    assert technical_rules(sell, sell.bar_time) == []
    wrong = candidate(signal='SELL_SETUP')
    assert {'trend_mismatch', 'rsi_outside_range', 'macd_mismatch'} <= set(technical_rules(wrong, wrong.bar_time))


def test_volatility_and_strength(monkeypatch):
    monkeypatch.setenv('FILTER_SESSIONS', 'false')
    signal = candidate(atr=100, adx=2)
    assert technical_rules(signal, signal.bar_time) == ['weak_trend', 'atr_outside_range']


@pytest.mark.parametrize('changes', [{'decision': 'BUY'}, {'confidence': 101}, {'confidence': '80'},
    {'confidence': True}, {'reasons': []}, {'reasons': ['x' * 241]}, {'risk_flags': ['']}, {'order': 'buy'}])
def test_invalid_ai_outputs(changes):
    with pytest.raises(ValidationError):
        analysis(**changes)


@pytest.mark.parametrize('changes', [{'decision': 'REJECT'}, {'confidence': 74},
                                   {'market_regime': 'bearish_trend'}, {'setup_quality': 'fair'}])
def test_ai_cannot_bypass_quality_gate(changes):
    assert outcome(candidate(), analysis(**changes)) == 'rejected'


def test_approved_message_is_manual_only():
    signal, result = candidate(), analysis()
    assert outcome(signal, result) == 'approved'
    message = notification_text(signal, 'approved', result.model_dump(), [])
    assert 'WAITING FOR MANUAL CONFIRMATION' in message
    assert 'NOT CHECKED' in message
    assert 'not a win probability' in message
    assert 'BUY AT: 3510.25' in message and 'STOP LOSS:' in message and 'TP4:' in message
    assert 'WHY (rules):' in message and 'AI VIEW' in message and 'RISK FLAGS:' in message
    assert 'No order was placed' in message


def test_symbols_are_configurable(monkeypatch):
    monkeypatch.delenv('SYMBOLS', raising=False)
    with pytest.raises(ValidationError):
        candidate(symbol='BTCUSD')
    monkeypatch.setenv('SYMBOLS', 'XAUUSD, btcusd')
    btc = candidate(symbol='COINBASE:btcusd')
    assert btc.symbol == 'BTCUSD'
    assert 'BTCUSD 15m technical setup' in system_prompt(btc)
    assert 'BUY BTCUSD 15m' in notification_text(btc, 'rejected', None, ['weak_trend'])
    assert 'BUY XAUUSD 15m' in notification_text(candidate(), 'rejected', None, ['weak_trend'])


def test_crypto_skips_session_filter(monkeypatch):
    monkeypatch.setenv('SYMBOLS', 'XAUUSD,BTCUSD')
    monkeypatch.setenv('FILTER_SESSIONS', 'true')
    monkeypatch.delenv('SESSION_EXEMPT_SYMBOLS', raising=False)
    sunday = int(datetime.fromisoformat('2026-09-06T14:00:00+00:00').timestamp())
    gold = candidate(bar_time=sunday)
    assert 'outside_london_or_new_york_session' in technical_rules(gold, sunday)
    btc = candidate(symbol='BTCUSD', bar_time=sunday)
    assert 'outside_london_or_new_york_session' not in technical_rules(btc, sunday)
    monkeypatch.setenv('SESSION_EXEMPT_SYMBOLS', '')
    assert 'outside_london_or_new_york_session' in technical_rules(btc, sunday)


def test_trade_plan_geometry(monkeypatch):
    monkeypatch.delenv('STOP_ATR_MULTIPLE', raising=False)
    monkeypatch.delenv('TP_R_MULTIPLES', raising=False)
    plan = trade_plan(candidate())                       # no swing: 1.5 x ATR 4.2 = 6.3
    assert plan['stop'] == pytest.approx(3503.95) and plan['basis'] == 'no usable prior swing'
    assert [round(level, 2) for _, level in plan['targets']] == [3516.55, 3522.85, 3529.15, 3535.45]
    swing = trade_plan(candidate(swing_low=3505))         # 5.25 + 0.84 buffer, inside 1-3 ATR
    assert swing['risk'] == pytest.approx(6.09) and swing['basis'].startswith('below swing low 3505')
    far = trade_plan(candidate(swing_low=3400))           # beyond 3 ATR: fall back to ATR multiple
    assert far['risk'] == pytest.approx(6.3)
    sell = trade_plan(candidate(signal='SELL_SETUP', price=3470, ema20=3480, ema50=3490, ema200=3500, rsi=42,
                                macd_hist=-1, swing_high=3476))
    assert sell['stop'] > 3470 and all(level < 3470 for _, level in sell['targets'])
    assert sell['basis'].startswith('above swing high 3476')
    monkeypatch.setenv('TP_R_MULTIPLES', '1.5,3')
    assert [m for m, _ in trade_plan(candidate())['targets']] == [1.5, 3.0]


def test_levels_only_for_structurally_valid_setups():
    signal = candidate()
    rule_rejected = notification_text(signal, 'rejected', None, ['weak_trend'])
    assert 'STOP LOSS' not in rule_rejected and 'CHECKS FAILED: weak_trend' in rule_rejected and 'WHY (rules):' in rule_rejected
    ai_rejected = notification_text(signal, 'rejected', analysis(decision='REJECT').model_dump(), ['ai_quality_gate_rejected'])
    assert 'reference only, setup NOT approved' in ai_rejected and 'TP1:' in ai_rejected
    assert 'NO ACTION' in ai_rejected and 'WAITING FOR MANUAL CONFIRMATION' not in ai_rejected
