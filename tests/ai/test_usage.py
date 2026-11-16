from datetime import datetime, timezone

import pytest

from app.ai import usage


@pytest.fixture(autouse=True)
def prices(monkeypatch):
    monkeypatch.setenv('OPENAI_PRICE_INPUT', '10')
    monkeypatch.setenv('OPENAI_PRICE_CACHED_INPUT', '1')
    monkeypatch.setenv('OPENAI_PRICE_OUTPUT', '50')


def test_cost_uses_cached_and_output_rates():
    assert usage.cost(1_000_000, 0) == pytest.approx(10)
    assert usage.cost(0, 1_000_000) == pytest.approx(50)
    # 100k of 1M input tokens cached: 900k x $10 + 100k x $1.
    assert usage.cost(1_000_000, 0, cached_tokens=100_000) == pytest.approx(9.1)
    assert usage.cost(1000, 0, cached_tokens=5000) == pytest.approx(0.001)    # cached can't exceed input


def test_reservation_covers_the_worst_case():
    amount = usage.reservation(input_chars=3000, max_output_tokens=4000)
    assert amount >= usage.cost(1000, 4000)
    assert amount == pytest.approx(usage.cost(1200, 4000))


def test_windows_follow_the_local_day(monkeypatch):
    monkeypatch.setenv('DIGEST_TIMEZONE', 'Asia/Phnom_Penh')
    # 2026-11-15 18:30 UTC is already 16 November 01:30 in Phnom Penh (UTC+7).
    day, month = usage.windows(datetime(2026, 11, 15, 18, 30, tzinfo=timezone.utc))
    assert datetime.fromtimestamp(day, timezone.utc) == datetime(2026, 11, 15, 17, 0, tzinfo=timezone.utc)
    assert datetime.fromtimestamp(month, timezone.utc) == datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc)


def test_limits_read_configuration(monkeypatch):
    monkeypatch.setenv('OPENAI_DAILY_LIMIT', '3')
    monkeypatch.setenv('OPENAI_MONTHLY_BUDGET_USD', '5')
    monkeypatch.setenv('OPENAI_SAFETY_RESERVE_USD', 'not-a-number')
    assert usage.limits() == {'daily': 3, 'budget': 5.0, 'reserve': 1.0}
