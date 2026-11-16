"""One authorized message in, one reply out:
/command -> code (free) · free text -> local model sorts it -> COMMAND (code) | SIMPLE (local model, free)
| DEEP (OpenAI with read-only tools, paid, budget-checked). There is no automatic swap between models: when one
is unavailable the reply says so instead of silently moving work (and cost) to the other."""
import json
import time

from app.agent import commands, deep, memory, tools
from app.ai import ollama, prompts, usage
from app.ai.classifier import route_question
from app.ai.openai_client import CloudAIError
from app.db import database, readonly

LOCAL_DOWN = ('The local AI is offline right now, so I can\'t read free-text questions. The commands still work '
              '(/help), and /deep <question> uses paid analysis.')


def snapshot(conn) -> dict:
    """Compact, code-computed facts for a simple local answer. The local model gets no database access."""
    def head(days):
        return tools.record(conn, days)['headline']
    return {'now': tools.iso(time.time()), 'last_7_days': head(7), 'last_7_days_by_session': tools.record(conn, 7)['by_session'],
            'last_30_days': head(30), 'all_time': head(None), 'open_trades': tools.open_trades(conn),
            'last_signals': tools.signals(conn, 5),
            'latest_prices': [tools.latest_price(conn, item['symbol']) for item in tools.feed(conn)],
            'news_next_12h': tools.news(12)}


def simple(question: str, history: list[dict]) -> str:
    with readonly() as conn:
        data = json.dumps(snapshot(conn), default=str, separators=(',', ':'))
    return ollama.chat('simple_answer', [
        {'role': 'system', 'content': prompts.SIMPLE}, *history,
        {'role': 'user', 'content': f'DATA: {data}\n\nQUESTION: {question[:1000]}'}],
        temperature=0.2, max_tokens=400)[:3500]


def deep_reply(question: str, history: list[dict]) -> tuple[str, bool]:
    """(reply, answered). Budget refusals and outages become a plain explanation, never a fallback model."""
    try:
        text = deep.answer(question, history)
    except usage.BudgetRefused as refused:
        if refused.code == 'daily_limit':
            return (f'🧠 Daily deep-analysis limit reached ({usage.limits()["daily"]} per day). It resets at midnight. '
                    'Meanwhile: /record 30, /signals 10.'), False
        return ('🧠 This month\'s AI budget is used up, so deep analysis is paused until next month. '
                'See /cost. The commands keep working.'), False
    except CloudAIError as error:
        if error.code == 'not_configured':
            return '🧠 Deep analysis is off: OpenAI is not configured (OPENAI_API_KEY / OPENAI_MODEL).', False
        return f'🧠 Deep analysis is unavailable right now ({error.code}). Try again later, or use /record.', False
    return f'🧠 DEEP ANALYSIS\n\n{text}\n\n⚠️ Analysis of past records, not a trading instruction.', True


def handle(chat_id: str, text: str) -> tuple[str, str]:
    """(reply, route) for one authorized message."""
    text = (text or '').strip()
    if not text:
        return 'I only read text messages. Send /help for the commands.', 'none'
    parsed = commands.parse(text)
    if parsed:
        name, argument = parsed
        if name in ('start', 'help'):
            return commands.HELP, 'command'
        if name == 'forget':
            with database() as conn:
                memory.forget(conn, chat_id)
            return '🧹 Conversation memory cleared.', 'command'
        if name == 'deep':
            if not argument:
                return 'Usage: /deep <question>, e.g. /deep why are London trades losing this month?', 'command'
            return converse(chat_id, argument, 'DEEP')
        if name in commands.COMMANDS:
            with readonly() as conn:
                return commands.COMMANDS[name](conn, argument), 'command'
        return 'Unknown command.\n\n' + commands.HELP, 'command'
    return converse(chat_id, text, None)


def converse(chat_id: str, question: str, forced: str | None) -> tuple[str, str]:
    with readonly() as conn:
        history = memory.recent(conn, chat_id)
    route, hinted = None, False
    if forced is None:
        try:
            route, hinted = route_question(question, history)
        except ollama.LocalAIError:
            return LOCAL_DOWN, 'local_down'
        if route.route == 'COMMAND':
            with readonly() as conn:
                return commands.COMMANDS[route.command](conn, route.argument), 'command'
    if forced == 'DEEP' or route.route == 'DEEP':
        reply, answered = deep_reply(question, history)
        name = 'deep'
    else:
        try:
            reply, answered = simple(question, history), True
        except ollama.LocalAIError:
            return LOCAL_DOWN, 'local_down'
        if hinted:
            reply += '\n\n(For a full investigation, send /deep followed by your question.)'
        name = 'simple'
    if answered:
        with database() as conn:
            memory.remember(conn, chat_id, question, reply)
    return reply, name
