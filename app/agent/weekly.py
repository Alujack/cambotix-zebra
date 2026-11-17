"""Sunday weekly report. Every statistic is calculated here by code from the ledger; OpenAI only interprets the
finished numbers (observations and backtest suggestions). Without OpenAI the report still goes out, numbers only.
A report is claimed by its period before any work, so a scheduler that runs twice still delivers one report."""
import json
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app import ledger
from app.agent import tools
from app.ai import openai_client, prompts, usage
from app.ai.openai_client import CloudAIError
from app.db import database
from app.outbox import queue_message

DAYS = {'mon': 0, 'tue': 1, 'wed': 2, 'thu': 3, 'fri': 4, 'sat': 5, 'sun': 6}
SMALL = 20


def enabled() -> bool:
    return os.getenv('WEEKLY_REPORT_ENABLED', 'true').lower() == 'true'


def zone() -> ZoneInfo:
    return ZoneInfo(os.getenv('WEEKLY_REPORT_TIMEZONE') or os.getenv('DIGEST_TIMEZONE', 'Asia/Phnom_Penh'))


def due(now: datetime | None = None) -> tuple[str, float, float] | None:
    """(ref, period start, period end) when this week's report is due: on WEEKLY_REPORT_DAY from WEEKLY_REPORT_HOUR,
    covering the seven local days that ended at midnight."""
    local = (now or datetime.now(zone())).astimezone(zone())
    day = DAYS.get(os.getenv('WEEKLY_REPORT_DAY', 'sun').strip().lower()[:3], 6)
    if local.weekday() != day or local.hour < int(os.getenv('WEEKLY_REPORT_HOUR', '9')):
        return None
    end = local.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)
    return 'weekly:' + end.strftime('%Y-%m-%d'), start.timestamp(), end.timestamp()


def label(start: float, end: float) -> str:
    first, last = datetime.fromtimestamp(start, zone()), datetime.fromtimestamp(end - 1, zone())
    return f'{first:%b} {first.day} – {last:%b} {last.day}'


def compute(conn, start: float, end: float, weeks: int = 4) -> dict:
    """The week's statistics, the previous `weeks` weeks for comparison, and data-quality notes."""
    span = 7 * 86400
    trades = [item for item in ledger.closed_trades(conn, start - weeks * span) if item['time'] < end]
    week = [item for item in trades if item['time'] >= start]
    previous = []
    for index in range(1, weeks + 1):
        low, high = start - index * span, end - index * span
        items = [item for item in trades if low <= item['time'] < high]
        previous.append({'period': label(low, high), **tools.stats(items)})
    published = conn.execute('''SELECT count(*) AS n FROM ledger WHERE kind='published'
        AND recorded_at >= to_timestamp(%s) AND recorded_at < to_timestamp(%s)''', (start, end)).fetchone()['n']
    never = conn.execute('''SELECT count(*) AS n FROM ledger WHERE kind='not_filled'
        AND recorded_at >= to_timestamp(%s) AND recorded_at < to_timestamp(%s)''', (start, end)).fetchone()['n']
    notes = []
    if len(week) < SMALL:
        notes.append(f'Small sample: {len(week)} closed trades this week (under {SMALL}); no conclusion is reliable.')
    for item in tools.feed(conn):
        if item['stale_minutes'] > 24 * 60:
            notes.append(f'MT5 candles for {item["symbol"]} stop at {item["candles_through"]}: grading may be incomplete.')
    ambiguous = sum(1 for item in week if item['ambiguous'])
    if ambiguous:
        notes.append(f'{ambiguous} trade(s) had an ambiguous candle; the worse outcome was counted.')
    head = tools.stats(week)
    return {'period': label(start, end), 'timezone': str(zone()), 'week': head,
            'losses': sum(1 for item in week if item['r_tp1'] < 0),
            'breakeven': sum(1 for item in week if item['r_tp1'] == 0),
            'published': published, 'not_filled': never, 'open_now': len(ledger.open_plans(conn)),
            'by_session': tools.grouped(week, lambda item: item['session']),
            'by_symbol': tools.grouped(week, lambda item: item['symbol']),
            'by_model': tools.grouped(week, lambda item: item['model']),
            'by_direction': tools.grouped(week, lambda item: item['direction']),
            'by_caution': tools.grouped(week, lambda item: 'with cautions' if item['cautioned'] else 'no cautions'),
            'previous_weeks': previous, 'data_notes': notes}


def line(name: str, item: dict) -> str:
    rate = f'{item["win_rate"] * 100:.0f}%' if item['win_rate'] is not None else 'n/a'
    return f'• {name}: {item["closed"]} trades, win {rate}, {item["total_r_tp1"]:+.2f}R'


def render(stats: dict, analysis: str | None, reason: str | None) -> str:
    head = stats['week']
    rate = f'{head["win_rate"] * 100:.1f}%' if head['win_rate'] is not None else 'n/a'
    pf = f'{head["profit_factor"]:g}' if head['profit_factor'] is not None else 'n/a'
    lines = ['🦓 ZEBRA WEEKLY REPORT', f'Period: {stats["period"]} ({stats["timezone"]})', '', 'PERFORMANCE',
             f'Total trades: {head["closed"]} · Wins: {head["wins"]} · Losses: {stats["losses"]}'
             + (f' · Break-even: {stats["breakeven"]}' if stats['breakeven'] else ''),
             f'Win rate: {rate} · Net: {head["total_r_tp1"]:+.2f}R · PF {pf} · Expectancy {head["expectancy_r"]:+.3f}R',
             f'Published {stats["published"]} · never filled {stats["not_filled"]} · open now {stats["open_now"]}',
             '', 'PREVIOUS WEEKS'] + [line(item['period'], item) for item in stats['previous_weeks']]
    for title, key in (('SESSIONS', 'by_session'), ('SYMBOLS', 'by_symbol'), ('CAUTIONS', 'by_caution')):
        if stats[key]:
            lines += ['', title] + [line(name, item) for name, item in stats[key].items()]
    if stats['data_notes']:
        lines += ['', 'DATA'] + ['⚠️ ' + note for note in stats['data_notes']]
    lines.append('')
    if analysis:
        lines += ['AI ANALYSIS (OpenAI; numbers above are computed by code)', analysis]
    else:
        lines.append(f'AI analysis unavailable ({reason}). The statistics above are complete.')
    lines += ['', '⚠️ Suggestions are hypotheses to backtest, not trading instructions.']
    return '\n'.join(lines)[:4000]


def interpret(ref: str, stats: dict) -> tuple[str | None, str | None]:
    try:
        data = openai_client.respond(f'{ref}-{int(time.time())}', 'weekly_report', prompts.WEEKLY,
                                     [{'role': 'user', 'content': 'DATA: ' + json.dumps(stats, default=str)}],
                                     max_output_tokens=int(os.getenv('WEEKLY_REPORT_MAX_OUTPUT_TOKENS', '3000')))
    except usage.BudgetRefused as refused:
        return None, refused.code.replace('_', ' ') + ' reached'
    except CloudAIError as error:
        return None, 'OpenAI not configured' if error.code == 'not_configured' else error.code
    text = openai_client.output_text(data)
    return (text[:2000], None) if text else (None, 'empty answer')


def run(now: datetime | None = None) -> dict:
    if not enabled():
        return {'status': 'disabled'}
    window = due(now)
    if not window:
        return {'status': 'not_due'}
    ref, start, end = window
    with database() as conn:
        claimed = conn.execute('''INSERT INTO ai_reports(ref, period_start, period_end, stats, status)
            VALUES (%s,%s,%s,'{}','generating') ON CONFLICT (ref) DO UPDATE SET updated_at=now()
            WHERE ai_reports.status='generating' AND ai_reports.updated_at < now() - interval '30 minutes'
            RETURNING ref''', (ref, int(start), int(end))).fetchone()
        if not claimed:
            return {'status': 'done_or_running', 'ref': ref}
        stats = compute(conn, start, end)
    analysis, reason = interpret(ref, stats)
    with database() as conn:
        queue_message(conn, ref, 'weekly', 'digest', render(stats, analysis, reason))
        conn.execute('''UPDATE ai_reports SET stats=%s, analysis=%s, error_code=%s, status='queued', updated_at=now()
            WHERE ref=%s''', (Jsonb(stats), analysis, reason, ref))
    return {'status': 'queued', 'ref': ref, 'ai': analysis is not None}
