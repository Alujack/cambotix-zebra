from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.agent import weekly

PP = ZoneInfo('Asia/Phnom_Penh')


@pytest.fixture(autouse=True)
def schedule(monkeypatch):
    monkeypatch.setenv('WEEKLY_REPORT_DAY', 'sun')
    monkeypatch.setenv('WEEKLY_REPORT_HOUR', '9')
    monkeypatch.setenv('WEEKLY_REPORT_TIMEZONE', 'Asia/Phnom_Penh')


def test_due_on_sunday_from_nine_for_the_previous_seven_days():
    assert weekly.due(datetime(2026, 11, 15, 8, 59, tzinfo=PP)) is None          # Sunday, too early
    assert weekly.due(datetime(2026, 11, 16, 10, 0, tzinfo=PP)) is None          # Monday
    ref, start, end = weekly.due(datetime(2026, 11, 15, 9, 0, tzinfo=PP))
    assert ref == 'weekly:2026-11-15'
    assert datetime.fromtimestamp(start, PP) == datetime(2026, 11, 8, tzinfo=PP)
    assert datetime.fromtimestamp(end, PP) == datetime(2026, 11, 15, tzinfo=PP)
    assert weekly.label(start, end) == 'Nov 8 – Nov 14'
    # Later the same day is the same report: the ref is what deduplicates it.
    assert weekly.due(datetime(2026, 11, 15, 23, 0, tzinfo=PP))[0] == ref


def stats(closed=3, wins=2):
    head = {'closed': closed, 'wins': wins, 'win_rate': wins / closed if closed else None, 'total_r_tp1': 1.5,
            'expectancy_r': 0.5, 'profit_factor': 2.5, 'total_r_scaled': 1.2, 'max_drawdown_r': 1.0}
    return {'period': 'Nov 8 – Nov 14', 'timezone': 'Asia/Phnom_Penh', 'week': head, 'losses': 1, 'breakeven': 0,
            'published': 4, 'not_filled': 1, 'open_now': 0,
            'by_session': {'13:00 NY candle': head}, 'by_symbol': {'XAUUSD': head}, 'by_model': {'crt': head},
            'by_direction': {'BUY': head}, 'by_caution': {'no cautions': head},
            'previous_weeks': [{'period': 'Nov 1 – Nov 7', **head}],
            'data_notes': ['Small sample: 3 closed trades this week (under 20); no conclusion is reliable.']}


def test_report_numbers_come_from_code_and_ai_is_labelled():
    text = weekly.render(stats(), 'OBSERVATIONS:\n• London led.', None)
    assert 'Total trades: 3 · Wins: 2 · Losses: 1' in text and 'Net: +1.50R' in text and 'PF 2.5' in text
    assert 'AI ANALYSIS (OpenAI; numbers above are computed by code)' in text and '• London led.' in text
    assert '⚠️ Small sample' in text and 'not trading instructions' in text


def test_report_without_ai_still_has_every_statistic():
    text = weekly.render(stats(closed=0, wins=0), None, 'monthly budget reached')
    assert 'Win rate: n/a' in text and 'AI analysis unavailable (monthly budget reached)' in text


def test_disabled(monkeypatch):
    monkeypatch.setenv('WEEKLY_REPORT_ENABLED', 'false')
    assert weekly.run() == {'status': 'disabled'}
