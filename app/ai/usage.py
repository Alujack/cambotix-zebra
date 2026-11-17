"""Every AI call is recorded here. OpenAI calls must first reserve their worst-case cost inside one locked
transaction, so concurrent requests can never spend past OPENAI_DAILY_LIMIT or the monthly budget.

Cost is an estimate from the token counts the API returns and the OPENAI_PRICE_* rates; OpenAI does not return a
billed amount per request, so `actual_cost` stays empty unless it is filled from the billing export. A request whose
outcome is unknown (timeout, server error) keeps its full reservation as cost: a failed call is never assumed free."""
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg

from app.db import database

log = logging.getLogger('zebra.ai')
BUDGET_LOCK = 914210


class BudgetRefused(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _float(name: str, default: str) -> float:
    try:
        return float(os.getenv(name, default) or default)
    except ValueError:
        return float(default)


def prices() -> dict:
    """USD per one million tokens."""
    return {'input': _float('OPENAI_PRICE_INPUT', '10'), 'cached': _float('OPENAI_PRICE_CACHED_INPUT', '1'),
            'output': _float('OPENAI_PRICE_OUTPUT', '50')}


def cost(input_tokens: int, output_tokens: int, cached_tokens: int = 0) -> float:
    rate = prices()
    cached = min(max(cached_tokens, 0), max(input_tokens, 0))
    return ((input_tokens - cached) * rate['input'] + cached * rate['cached'] + output_tokens * rate['output']) / 1e6


def reservation(input_chars: int, max_output_tokens: int) -> float:
    """Worst case for one request: generous input token count (3 characters per token) plus the output cap."""
    return round(cost(input_chars // 3 + 200, max_output_tokens), 6)


def limits() -> dict:
    return {'daily': int(_float('OPENAI_DAILY_LIMIT', '20')), 'budget': _float('OPENAI_MONTHLY_BUDGET_USD', '10'),
            'reserve': _float('OPENAI_SAFETY_RESERVE_USD', '1')}


def windows(now: datetime | None = None) -> tuple[float, float]:
    """Start of today and of this month in the local zone (DIGEST_TIMEZONE), as Unix seconds."""
    zone = ZoneInfo(os.getenv('DIGEST_TIMEZONE', 'Asia/Phnom_Penh'))
    local = (now or datetime.now(zone)).astimezone(zone)
    day = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return day.timestamp(), day.replace(day=1).timestamp()


COMMITTED = '''COALESCE(SUM(CASE WHEN status='reserved' THEN reserved_usd
                              ELSE COALESCE(actual_cost, estimated_cost, 0) END), 0)'''


def reserve(job_id: str, job: str, model: str, amount: float) -> int:
    """Claim `amount` USD for one OpenAI request of `job_id`, or raise BudgetRefused. Commits before returning,
    so the reservation is visible to every other worker at once."""
    limit = limits()
    day, month = windows()
    with database() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(%s)', (BUDGET_LOCK,))
        known = conn.execute("SELECT 1 FROM ai_usage WHERE provider='openai' AND job_id=%s LIMIT 1", (job_id,)).fetchone()
        if not known:
            jobs = conn.execute("""SELECT count(DISTINCT job_id) AS n FROM ai_usage
                WHERE provider='openai' AND created_at >= to_timestamp(%s)""", (day,)).fetchone()['n']
            if jobs >= limit['daily']:
                raise BudgetRefused('daily_limit')
        spent = float(conn.execute(f"""SELECT {COMMITTED} AS v FROM ai_usage
            WHERE provider='openai' AND created_at >= to_timestamp(%s)""", (month,)).fetchone()['v'])
        if spent + amount > limit['budget'] - limit['reserve']:
            raise BudgetRefused('monthly_budget')
        return conn.execute('''INSERT INTO ai_usage(job_id, provider, model, job, reserved_usd, status)
            VALUES (%s,'openai',%s,%s,%s,'reserved') RETURNING id''', (job_id, model, job, amount)).fetchone()['id']


def settle(usage_id: int, ok: bool, input_tokens: int = 0, output_tokens: int = 0, cached_tokens: int = 0,
           latency_ms: int | None = None, error_code: str | None = None, billed_unknown: bool = False):
    """Replace a reservation by the measured cost. Without a token count and an unknown outcome, the full
    reservation stays charged."""
    with database() as conn:
        row = conn.execute('SELECT reserved_usd FROM ai_usage WHERE id=%s', (usage_id,)).fetchone()
        estimate = cost(input_tokens, output_tokens, cached_tokens)
        if billed_unknown and not (input_tokens or output_tokens):
            estimate = float(row['reserved_usd']) if row else 0.0
        conn.execute('''UPDATE ai_usage SET status=%s, input_tokens=%s, output_tokens=%s, estimated_cost=%s,
            latency_ms=%s, error_code=%s, settled_at=now() WHERE id=%s''',
            ('ok' if ok else 'failed', input_tokens, output_tokens, round(estimate, 6), latency_ms, error_code, usage_id))


def record_local(job: str, model: str, ok: bool, input_tokens: int = 0, output_tokens: int = 0,
                 latency_ms: int | None = None, error_code: str | None = None):
    """Best effort: a usage-log failure must never break the work it describes."""
    try:
        with database() as conn:
            conn.execute('''INSERT INTO ai_usage(job_id, provider, model, job, input_tokens, output_tokens,
                estimated_cost, status, error_code, latency_ms, settled_at)
                VALUES (%s,'ollama',%s,%s,%s,%s,0,%s,%s,%s,now())''',
                (job, model, job, input_tokens, output_tokens, 'ok' if ok else 'failed', error_code, latency_ms))
    except (psycopg.Error, KeyError):
        log.warning('ai_usage_not_recorded provider=ollama job=%s', job)


def summary(conn) -> dict:
    day, month = windows()
    limit = limits()

    def openai(since):
        return conn.execute(f"""SELECT count(*) AS requests, count(DISTINCT job_id) AS jobs, {COMMITTED} AS cost,
            COALESCE(SUM(input_tokens), 0) AS input_tokens, COALESCE(SUM(output_tokens), 0) AS output_tokens
            FROM ai_usage WHERE provider='openai' AND created_at >= to_timestamp(%s)""", (since,)).fetchone()

    today, this_month = openai(day), openai(month)
    local = conn.execute("""SELECT count(*) AS requests, count(*) FILTER (WHERE status='ok') AS ok
        FROM ai_usage WHERE provider='ollama' AND created_at >= to_timestamp(%s)""", (month,)).fetchone()
    spent = float(this_month['cost'])
    return {'today': {**today, 'cost': float(today['cost'])}, 'month': {**this_month, 'cost': spent},
            'ollama_month': local, 'daily_limit': limit['daily'], 'budget': limit['budget'],
            'reserve': limit['reserve'], 'available': max(0.0, limit['budget'] - limit['reserve'] - spent)}


def health(conn, hours: int = 24) -> list[dict]:
    """Success rate and latency per provider over the last `hours`, for /status."""
    return conn.execute('''SELECT provider, count(*) AS calls, count(*) FILTER (WHERE status='ok') AS ok,
        round(avg(latency_ms) FILTER (WHERE status='ok')) AS avg_ms, max(created_at) AS last_at
        FROM ai_usage WHERE created_at >= now() - make_interval(hours => %s) AND status <> 'reserved'
        GROUP BY provider ORDER BY provider''', (hours,)).fetchall()
