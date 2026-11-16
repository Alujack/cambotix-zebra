"""Telegram commands answered by code from the database: exact, instant and free."""
import os
import time

from app.agent import tools
from app.ai import ollama, openai_client, usage
from app.domain import allowed_symbols

HELP = '''🦓 Zebra assistant (read-only: it never places or changes trades)

/open: open trades
/price XAUUSD: latest broker price
/record 30: performance over 30 days (no number = all time)
/signals 5: recent signals and why
/news: high-impact news, next 24 h
/cost: AI spending and budget
/status: system health
/deep <question>: full analysis (paid, OpenAI)
/forget: clear this chat's memory

Or just ask a question. Simple ones are answered locally for free; "why" and comparison questions go to deep analysis.'''


def number(text: str, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(text)))
    except (TypeError, ValueError):
        return default


def fmt(value: float) -> str:
    return f'{value:.2f}' if value >= 100 else f'{value:.5f}'


def stat_line(item: dict) -> str:
    rate = f'{item["win_rate"] * 100:.0f}%' if item['win_rate'] is not None else 'n/a'
    pf = f' · PF {item["profit_factor"]:g}' if item.get('profit_factor') is not None else ''
    return f'{item["closed"]} trades · win {rate} · {item["total_r_tp1"]:+.2f}R{pf}'


def open_text(conn) -> str:
    found = tools.open_trades(conn)
    if not found:
        return '📭 No open trades.'
    lines = [f'📂 OPEN TRADES ({len(found)})']
    for item in found:
        targets = ' / '.join(fmt(level) for level in item['targets'])
        progress = ', '.join(item['progress']) or 'waiting for fill'
        lines += ['', f'{"🟢" if item["direction"] == "BUY" else "🔴"} {item["direction"]} {item["symbol"]} '
                      f'[{item["model"]}] · Ledger #{item["ledger"]}',
                  f'Entry {fmt(item["entry"])} · Stop {fmt(item["stop"])}', f'Targets {targets}',
                  f'Since {item["published"]} · {progress}']
    return '\n'.join(lines)


def price_text(conn, argument: str) -> str:
    symbol = tools.normalize_symbol(argument.strip() or None)
    if symbol is None:
        return f'Unknown symbol. Configured: {", ".join(sorted(allowed_symbols()))}'
    found = tools.latest_price(conn, symbol)
    if not found:
        return f'No broker candles stored for {symbol} yet. Is the MT5 feeder running?'
    stale = ' ⚠️ feed looks stale (market closed or feeder down)' if found['age_minutes'] > 15 else ''
    return (f'💹 {symbol}: {fmt(found["close"])} (bid close of the {found["minute"]} minute, spread '
            f'{found["spread"]:g}){stale}')


def record_text(conn, argument: str) -> str:
    days = number(argument, 0, 0, 3650) or None
    data = tools.record(conn, days)
    head = data['headline']
    if not head['closed']:
        return f'📊 No closed trades {"in the last " + str(days) + " days" if days else "on the record yet"}.'
    lines = [f'📊 RECORD · {"last " + str(days) + " days" if days else "all time"}', stat_line(head),
             f'Expectancy {head["expectancy_r"]:+.3f}R · max drawdown {head["max_drawdown_r"]:.2f}R', '', 'By symbol:']
    lines += [f'• {name}: {stat_line(item)}' for name, item in data['by_symbol'].items()]
    lines += ['', 'By session:'] + [f'• {name}: {stat_line(item)}' for name, item in data['by_session'].items()]
    if head['closed'] < 20:
        lines += ['', '⚠️ Fewer than 20 trades: too small to judge the strategy.']
    return '\n'.join(lines)[:4000]


def signals_text(conn, argument: str) -> str:
    found = tools.signals(conn, number(argument, 5, 1, 20))
    if not found:
        return 'No signals received yet.'
    icons = {'approved': '✅', 'rejected': '❌', 'error': '⚠️'}
    lines = [f'📡 LAST {len(found)} SIGNALS']
    for item in found:
        why = ', '.join(code.replace('_', ' ') for code in item['reasons']) or 'all rules passed'
        lines.append(f'{icons.get(item["status"], "•")} {item["bar_closed"]} {item["side"].split("_")[0]} {item["symbol"]} '
                     f'{item["timeframe"]} [{item["model"]}]: {item["status"]} ({why})')
    return '\n'.join(lines)[:4000]


def news_text(_conn=None, _argument: str = '') -> str:
    found = tools.news(24)
    if found['state'] == 'off':
        return '📰 The news filter is off (NEWS_FILTER=false).'
    if found['state'] == 'unknown':
        return '📰 Economic calendar unavailable right now: news is NOT checked.'
    if not found['events']:
        return '📰 No high-impact events in the next 24 hours.'
    return '\n'.join(['📰 HIGH-IMPACT NEWS (next 24 h)'] +
                     [f'• {e["time"]} {e["currency"]}: {e["title"]}' for e in found['events']])


def cost_text(conn, _argument: str = '') -> str:
    data = usage.summary(conn)
    today, month = data['today'], data['month']
    return '\n'.join([
        '💰 ZEBRA AI USAGE', '', 'TODAY',
        f'Deep jobs: {today["jobs"]} of {data["daily_limit"]} · API requests: {today["requests"]}',
        f'Estimated cost: ${today["cost"]:.2f}', '', 'THIS MONTH',
        f'Deep jobs: {month["jobs"]} · API requests: {month["requests"]}',
        f'Tokens: {month["input_tokens"]:,} in / {month["output_tokens"]:,} out',
        f'Estimated cost: ${month["cost"]:.2f}', '',
        f'Monthly budget: ${data["budget"]:.2f}', f'Safety reserve: ${data["reserve"]:.2f}',
        f'Available: ${data["available"]:.2f}', '', 'OLLAMA (local)',
        f'Requests this month: {data["ollama_month"]["requests"]:,} ({data["ollama_month"]["ok"]:,} ok) · cost $0.00', '',
        'Estimates from token counts × OPENAI_PRICE_*; check the OpenAI billing page for billed amounts.'])


def status_text(conn, _argument: str = '') -> str:
    local_ok, local_detail = ollama.available()
    cloud_ok, cloud_detail = openai_client.configured()
    lines = ['🩺 ZEBRA STATUS', '✅ Database: ok', f'{"✅" if local_ok else "❌"} Ollama: {local_detail}',
             f'{"✅" if cloud_ok else "⚪"} OpenAI: {cloud_detail if cloud_ok else cloud_detail + " (deep analysis off)"}']
    for row in usage.health(conn):
        rate = row['ok'] / row['calls'] * 100 if row['calls'] else 0
        latency = f', avg {int(row["avg_ms"])} ms' if row['avg_ms'] is not None else ''
        lines.append(f'   {row["provider"]} 24 h: {row["calls"]} calls, {rate:.0f}% ok{latency}')
    feed = tools.feed(conn)
    if not feed:
        lines.append('⚪ MT5 feed: no candles received yet')
    for item in feed:
        icon = '✅' if item['stale_minutes'] <= 15 else '⚠️'
        lines.append(f'{icon} MT5 {item["symbol"]}: candles through {item["candles_through"]} '
                     f'({item["stale_minutes"]} min ago)')
    queues = conn.execute('''SELECT
        (SELECT count(*) FROM signals WHERE status IN ('queued','processing')) AS signals,
        (SELECT count(*) FROM notifications WHERE status IN ('pending','sending')) AS alerts,
        (SELECT count(*) FROM messages WHERE status IN ('pending','sending')) AS messages,
        (SELECT count(*) FROM ai_jobs WHERE status IN ('queued','running')) AS ai_jobs,
        (SELECT count(*) FROM notifications WHERE status IN ('failed','unknown') AND updated_at > now()-interval '1 day')
          + (SELECT count(*) FROM messages WHERE status IN ('failed','unknown') AND updated_at > now()-interval '1 day')
          AS delivery_failures''').fetchone()
    last = conn.execute('SELECT max(received_at) AS at FROM signals').fetchone()['at']
    lines += [f'📥 Queues: {queues["signals"]} signals · {queues["alerts"]} alerts · {queues["messages"]} messages · '
              f'{queues["ai_jobs"]} AI jobs',
              f'{"⚠️" if queues["delivery_failures"] else "✅"} Telegram failures (24 h): {queues["delivery_failures"]}',
              f'Last signal received: {last:%Y-%m-%d %H:%M UTC}' if last else 'No signal received yet',
              f'Rules decide; AI is commentary only. Gate: {os.getenv("GATE_MODE", "rules")}.',
              f'Checked {tools.iso(time.time())}']
    return '\n'.join(lines)


COMMANDS = {'open': open_text, 'price': price_text, 'record': record_text, 'signals': signals_text,
            'news': news_text, 'cost': cost_text, 'status': status_text}


def parse(text: str) -> tuple[str, str] | None:
    """('/price xauusd' -> ('price', 'xauusd')); '/cmd@BotName' is accepted. None when not a command."""
    if not text.startswith('/'):
        return None
    head, _, rest = text[1:].partition(' ')
    return head.split('@')[0].lower(), rest.strip()
