import pytest

from app.agent import commands, jobs
from tests.test_domain import analysis, candidate


def test_parse():
    assert commands.parse('/record 30') == ('record', '30')
    assert commands.parse('/Price@ZebraBot  xauusd ') == ('price', 'xauusd')
    assert commands.parse('hello') is None


def test_number_is_clamped():
    assert commands.number('500', 5, 1, 20) == 20
    assert commands.number('abc', 5, 1, 20) == 5
    assert commands.number('', 0, 0, 3650) == 0


def test_open_trades_text(monkeypatch):
    monkeypatch.setattr(commands.tools, 'open_trades', lambda conn: [
        {'ledger': 7, 'event_id': 'e', 'symbol': 'XAUUSD', 'model': 'crt', 'direction': 'BUY', 'entry': 3506.0,
         'stop': 3493.4, 'targets': [3540.0, 3546.3], 'published': '2026-11-16 09:00 UTC', 'progress': ['filled']}])
    text = commands.open_text(None)
    assert 'BUY XAUUSD [crt] · Ledger #7' in text and 'Entry 3506.00 · Stop 3493.40' in text
    assert 'Targets 3540.00 / 3546.30' in text and 'filled' in text
    monkeypatch.setattr(commands.tools, 'open_trades', lambda conn: [])
    assert commands.open_text(None) == '📭 No open trades.'


def test_record_text_warns_on_small_samples(monkeypatch):
    head = {'closed': 4, 'wins': 3, 'win_rate': 0.75, 'total_r_tp1': 2.0, 'expectancy_r': 0.5, 'profit_factor': 3.0,
            'total_r_scaled': 1.0, 'max_drawdown_r': 1.0}
    monkeypatch.setattr(commands.tools, 'record', lambda conn, days: {'headline': head, 'by_symbol': {'XAUUSD': head},
                                                                       'by_session': {'13:00 NY candle': head}})
    text = commands.record_text(None, '30')
    assert text.startswith('📊 RECORD · last 30 days') and '4 trades · win 75% · +2.00R · PF 3' in text
    assert 'too small to judge' in text


def test_price_text_rejects_unknown_symbols(monkeypatch):
    monkeypatch.setenv('SYMBOLS', 'XAUUSD')
    assert commands.price_text(None, 'BTCUSD').startswith('Unknown symbol')
    monkeypatch.setattr(commands.tools, 'latest_price', lambda conn, symbol: None)
    assert 'No broker candles stored for XAUUSD' in commands.price_text(None, 'xauusdm')


def test_signal_review_message_says_rules_decide():
    text = jobs.review_text(candidate(), analysis(decision='REJECT').model_dump(), 12)
    assert text.startswith('🦓 AI REVIEW · BUY XAUUSD 15m [CLASSIC] · Ledger #12')
    assert 'Decision (rules): APPROVED' in text and 'AI view: REJECT' in text
    assert 'The rules decide; this note changes nothing.' in text


@pytest.mark.parametrize('flag,expected', [('true', True), ('false', False)])
def test_note_switches(monkeypatch, flag, expected):
    monkeypatch.setenv('AI_COMMENTARY', flag)
    monkeypatch.setenv('TRADE_NOTES', flag)
    assert jobs.signal_notes_enabled() is expected and jobs.trade_notes_enabled() is expected
