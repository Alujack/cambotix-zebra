"""The read-only data layer of the agent. Fixed, parameterized queries only, run inside READ ONLY transactions:
no tool can write, delete, change a setting or touch a trade. Arguments are validated before any query runs."""
import json
import os
import time
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import ledger
from app.db import readonly
from app.domain import allowed_symbols
from app.grader import summarize
from app.news import upcoming

STAT_KEYS = ('closed', 'wins', 'win_rate', 'total_r_tp1', 'expectancy_r', 'profit_factor', 'total_r_scaled', 'max_drawdown_r')
TIMEFRAMES = {'15m': 900, '1h': 3600, '4h': 14400, '1d': 86400}


def iso(stamp: float | None) -> str | None:
    return None if stamp is None else datetime.fromtimestamp(stamp, timezone.utc).strftime('%Y-%m-%d %H:%M UTC')


def normalize_symbol(text: str | None) -> str | None:
    """'xauusdm', 'OANDA:XAUUSD' -> 'XAUUSD' when that symbol is configured; None otherwise."""
    allowed = allowed_symbols()
    if not text:
        return sorted(allowed)[0] if allowed else None
    value = ''.join(ch for ch in text.split(':')[-1].upper() if ch.isalnum())
    if value in allowed:
        return value
    if value.endswith('M') and value[:-1] in allowed:
        return value[:-1]
    return None


def stats(trades: list[dict]) -> dict:
    full = summarize(trades, int(os.getenv('GO_MIN_TRADES', '150')), float(os.getenv('GO_MAX_DRAWDOWN_R', '10')))
    return {key: full[key] for key in STAT_KEYS}


def grouped(trades: list[dict], key) -> dict:
    buckets = {}
    for item in trades:
        buckets.setdefault(key(item), []).append(item)
    return {name: stats(items) for name, items in sorted(buckets.items())}


def trade_row(item: dict) -> dict:
    return {'closed_at': iso(item['time']), 'symbol': item['symbol'], 'model': item['model'],
            'direction': item['direction'], 'session': item['session'], 'exit': item.get('exit'),
            'r_tp1': item['r_tp1'], 'r_scaled': item['r_scaled'], 'cautioned': item['cautioned'],
            'ambiguous': item['ambiguous']}


def record(conn, days: int | None = None, symbol: str | None = None, now: float | None = None) -> dict:
    since = None if days is None else (now or time.time()) - days * 86400
    trades = [item for item in ledger.closed_trades(conn, since) if symbol is None or item['symbol'] == symbol]
    return {'period_days': days, 'symbol': symbol, 'headline': stats(trades),
            'by_session': grouped(trades, lambda item: item['session']),
            'by_direction': grouped(trades, lambda item: item['direction']),
            'by_symbol': grouped(trades, lambda item: item['symbol']),
            'by_model': grouped(trades, lambda item: item['model']),
            'by_caution': grouped(trades, lambda item: 'with cautions' if item['cautioned'] else 'no cautions'),
            'note': 'r_tp1 is the headline result in R; groups with closed < 20 are too small to conclude from.'}


def closed(conn, days: int, symbol: str | None = None, limit: int = 50, now: float | None = None) -> list[dict]:
    trades = [item for item in ledger.closed_trades(conn, (now or time.time()) - days * 86400)
              if symbol is None or item['symbol'] == symbol]
    return [trade_row(item) for item in trades[-limit:]]


def signal_row(row: dict) -> dict:
    analysis = row.get('analysis') or {}
    return {'event_id': row['event_id'], 'symbol': row['symbol'], 'model': row['payload'].get('model', 'classic'),
            'timeframe': row['timeframe'], 'side': row['signal'], 'status': row['status'],
            'reasons': row.get('rule_reasons') or [], 'bar_closed': iso(row['bar_time']),
            'ai_view': analysis.get('decision')}


def signals(conn, limit: int = 5, status: str = 'any') -> list[dict]:
    rows = conn.execute('''SELECT event_id, symbol, timeframe, bar_time, signal, payload, status, rule_reasons, analysis
        FROM signals WHERE (%s = 'any' OR status = %s) AND event_id NOT ILIKE ALL(%s)
        ORDER BY received_at DESC LIMIT %s''',
        (status, status, ['demo-synthetic%', 'smoke-%', 'synthetic-%'], limit)).fetchall()
    return [signal_row(row) for row in rows]


def signal(conn, event_id: str) -> dict | None:
    row = conn.execute('''SELECT event_id, symbol, timeframe, bar_time, signal, payload, status, rule_reasons,
        analysis, error_code FROM signals WHERE event_id=%s''', (event_id,)).fetchone()
    if not row:
        return None
    events = conn.execute('SELECT seq, kind, body FROM ledger WHERE event_id=%s ORDER BY seq', (event_id,)).fetchall()
    return {**signal_row(row), 'payload': row['payload'], 'analysis': row['analysis'], 'error_code': row['error_code'],
            'record': [{'seq': item['seq'], 'kind': item['kind'],
                        **{k: v for k, v in json.loads(item['body']).items() if k not in ('prev', 'event_id', 'seq', 'kind')}}
                       for item in events]}


def open_trades(conn) -> list[dict]:
    result = []
    for item in ledger.open_plans(conn):
        plan = item['plan']
        result.append({'ledger': item['seq'], 'event_id': item['event_id'], 'symbol': plan['symbol'],
                       'model': plan['model'], 'direction': plan['direction'], 'entry': plan['entry'],
                       'stop': plan['stop'], 'targets': [level for _, level, _ in plan['targets']],
                       'published': iso(plan['published_at']),
                       'progress': sorted(kind for kind in item['kinds'] if kind != 'published')})
    return result


def latest_price(conn, symbol: str) -> dict | None:
    row = conn.execute('SELECT t, c, spread FROM candles WHERE symbol=%s ORDER BY t DESC LIMIT 1', (symbol,)).fetchone()
    if not row:
        return None
    return {'symbol': symbol, 'close': row['c'], 'spread': row['spread'], 'minute': iso(row['t']),
            'age_minutes': round((time.time() - row['t'] - 60) / 60)}


def candles(conn, symbol: str, timeframe: str, bars: int) -> list[dict]:
    """OHLC bars rebuilt from stored broker M1 candles (UTC-aligned buckets), newest last."""
    seconds = TIMEFRAMES[timeframe]
    last = conn.execute('SELECT max(t) AS t FROM candles WHERE symbol=%s', (symbol,)).fetchone()['t']
    if last is None:
        return []
    rows = conn.execute('''SELECT (t / %s) * %s AS t, (array_agg(o ORDER BY t))[1] AS o, max(h) AS h, min(l) AS l,
          (array_agg(c ORDER BY t DESC))[1] AS c, count(*) AS minutes
        FROM candles WHERE symbol=%s AND t >= %s GROUP BY 1 ORDER BY 1 DESC LIMIT %s''',
        (seconds, seconds, symbol, (last // seconds - bars + 1) * seconds, bars)).fetchall()
    return [{'open_time': iso(row['t']), 'o': row['o'], 'h': row['h'], 'l': row['l'], 'c': row['c'],
             'minutes': row['minutes']} for row in reversed(rows)]


def feed(conn) -> list[dict]:
    rows = conn.execute('SELECT symbol, through FROM coverage ORDER BY symbol').fetchall()
    return [{'symbol': row['symbol'], 'candles_through': iso(row['through']),
             'stale_minutes': max(0, round((time.time() - row['through']) / 60))} for row in rows]


def news(hours: int = 24) -> dict:
    found = upcoming(time.time(), hours)
    return {'state': found['state'],
            'events': [{'time': iso(e['time']), 'title': e['title'], 'currency': e['country']} for e in found['events']]}


# Tools offered to the deep-analysis model. Names map to the functions above; nothing else is callable.
class RecordArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    days: int | None = Field(default=None, ge=1, le=3650)
    symbol: str | None = Field(default=None, max_length=20)


class SignalsArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    limit: int = Field(default=10, ge=1, le=50)
    status: str = Field(default='any', pattern='^(any|approved|rejected|error)$')


class SignalArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: str = Field(min_length=1, max_length=120)


class NoArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ClosedArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    days: int = Field(default=30, ge=1, le=365)
    symbol: str | None = Field(default=None, max_length=20)
    limit: int = Field(default=50, ge=1, le=200)


class CandleArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    symbol: str = Field(max_length=20)
    timeframe: str = Field(pattern='^(15m|1h|4h|1d)$')
    bars: int = Field(default=30, ge=1, le=120)


class NewsArgs(BaseModel):
    model_config = ConfigDict(extra='forbid')
    hours: int = Field(default=24, ge=1, le=168)


def _symbol(value):
    if value is None:
        return None
    found = normalize_symbol(value)
    if found is None:
        raise ValueError(f'unknown symbol {value!r}; configured: {", ".join(sorted(allowed_symbols()))}')
    return found


TOOLS = {
    'get_track_record': ('Performance statistics (win rate, R, profit factor, by session/direction/symbol/model/'
                         'caution) over the last `days` days (omit for all time), optionally for one symbol.',
                         RecordArgs, lambda conn, a: record(conn, a.days, _symbol(a.symbol))),
    'get_signals': ('Most recent signals with their rule decision and reasons.', SignalsArgs,
                    lambda conn, a: signals(conn, a.limit, a.status)),
    'get_signal': ('Full details of one signal by event_id: inputs, decision, AI note and its graded record.',
                   SignalArgs, lambda conn, a: signal(conn, a.event_id) or {'error': 'no such signal'}),
    'get_open_trades': ('Published plans that are not finished yet.', NoArgs, lambda conn, a: open_trades(conn)),
    'get_closed_trades': ('Individual closed trades (newest last) over the last `days` days.', ClosedArgs,
                          lambda conn, a: closed(conn, a.days, _symbol(a.symbol), a.limit)),
    'get_candles': ('OHLC bars rebuilt from stored broker M1 candles (UTC-aligned), newest last.', CandleArgs,
                    lambda conn, a: candles(conn, _symbol(a.symbol), a.timeframe, a.bars)),
    'get_news': ('High-impact economic events from one hour ago to `hours` ahead.', NewsArgs,
                 lambda conn, a: news(a.hours)),
}


def specs() -> list[dict]:
    return [{'type': 'function', 'name': name, 'description': description, 'parameters': model.model_json_schema()}
            for name, (description, model, _) in TOOLS.items()]


def run(name: str, arguments: str, limit: int | None = None) -> str:
    """Execute one allowlisted tool with validated arguments; always returns text for the model, never raises."""
    limit = limit or int(os.getenv('AGENT_TOOL_OUTPUT_CHARS', '8000'))
    if name not in TOOLS:
        return json.dumps({'error': f'unknown tool {name!r}; tools are read-only: {", ".join(TOOLS)}'})
    _, model, action = TOOLS[name]
    try:
        args = model.model_validate_json(arguments or '{}')
        with readonly() as conn:
            text = json.dumps(action(conn, args), default=str, separators=(',', ':'))
    except ValidationError as error:
        return json.dumps({'error': 'invalid arguments', 'detail': error.errors(include_url=False, include_input=False)},
                          default=str)
    except ValueError as error:
        return json.dumps({'error': str(error)[:200]})
    except Exception:
        return json.dumps({'error': 'data unavailable'})
    if len(text) > limit:
        return text[:limit] + '...[truncated: ask for fewer rows or a shorter period]'
    return text
