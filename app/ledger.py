"""Append-only, hash-chained record of every published plan and its graded outcome.

Each row's body is canonical JSON that includes the previous row's hash, so rewriting any past row changes every
later hash. Triggers refuse UPDATE, DELETE and TRUNCATE; a database superuser can still bypass triggers, which is
why the chain head is posted to Telegram every day: a rewritten history no longer matches the posted hash.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone

from app.domain import Signal, session_label, trade_plan
from app.grader import summarize

GENESIS = '0' * 64
TERMINAL = ('closed', 'not_filled')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS ledger (
    seq bigint PRIMARY KEY,
    event_id text NOT NULL REFERENCES signals(event_id),
    kind text NOT NULL,
    body text NOT NULL,
    hash text NOT NULL UNIQUE,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (event_id, kind)
);
CREATE TABLE IF NOT EXISTS candles (
    symbol text NOT NULL,
    t bigint NOT NULL,
    o double precision NOT NULL,
    h double precision NOT NULL,
    l double precision NOT NULL,
    c double precision NOT NULL,
    spread double precision NOT NULL,
    PRIMARY KEY (symbol, t)
);
CREATE TABLE IF NOT EXISTS coverage (
    symbol text PRIMARY KEY,
    since bigint NOT NULL,
    through bigint NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS messages (
    ref text PRIMARY KEY,
    kind text NOT NULL,
    chat text NOT NULL CHECK (chat IN ('private', 'digest')),
    message text NOT NULL,
    status text NOT NULL CHECK (status IN ('disabled', 'pending', 'sending', 'sent', 'failed', 'unknown')),
    error_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ledger_kind_recorded_idx ON ledger (kind, recorded_at);
CREATE OR REPLACE FUNCTION zebra_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % refused', TG_TABLE_NAME, TG_OP;
END $$;
CREATE OR REPLACE TRIGGER ledger_append_only BEFORE UPDATE OR DELETE ON ledger
    FOR EACH ROW EXECUTE FUNCTION zebra_append_only();
CREATE OR REPLACE TRIGGER ledger_no_truncate BEFORE TRUNCATE ON ledger
    FOR EACH STATEMENT EXECUTE FUNCTION zebra_append_only();
CREATE OR REPLACE TRIGGER candles_append_only BEFORE UPDATE OR DELETE ON candles
    FOR EACH ROW EXECUTE FUNCTION zebra_append_only();
CREATE OR REPLACE TRIGGER candles_no_truncate BEFORE TRUNCATE ON candles
    FOR EACH STATEMENT EXECUTE FUNCTION zebra_append_only();
CREATE OR REPLACE TRIGGER signals_no_delete BEFORE DELETE ON signals
    FOR EACH ROW EXECUTE FUNCTION zebra_append_only();
CREATE OR REPLACE TRIGGER signals_no_truncate BEFORE TRUNCATE ON signals
    FOR EACH STATEMENT EXECUTE FUNCTION zebra_append_only();
'''


def migrate(conn) -> None:
    conn.execute(SCHEMA)


def canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def digest(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def append(conn, event_id: str, kind: str, time: int, data: dict) -> tuple[int, str]:
    """Add one row at the end of the chain inside the caller's transaction."""
    conn.execute('LOCK TABLE ledger IN SHARE ROW EXCLUSIVE MODE')
    last = conn.execute('SELECT seq, hash FROM ledger ORDER BY seq DESC LIMIT 1').fetchone()
    seq, prev = (last['seq'] + 1, last['hash']) if last else (1, GENESIS)
    body = canonical({**data, 'seq': seq, 'event_id': event_id, 'kind': kind, 'time': int(time), 'prev': prev})
    value = digest(body)
    conn.execute('INSERT INTO ledger(seq, event_id, kind, body, hash) VALUES (%s,%s,%s,%s,%s)',
                 (seq, event_id, kind, body, value))
    return seq, value


def verify(rows: list[dict]) -> dict:
    """Recompute the chain; rows are {seq, body, hash} in seq order."""
    prev = GENESIS
    for expected, row in enumerate(rows, 1):
        body = json.loads(row['body'])
        if row['seq'] != expected or body.get('seq') != expected or body.get('prev') != prev or digest(row['body']) != row['hash']:
            return {'valid': False, 'broken_at': expected, 'rows': len(rows)}
        prev = row['hash']
    return {'valid': True, 'broken_at': None, 'rows': len(rows), 'head_seq': len(rows), 'head_hash': prev}


def plan_record(signal: Signal, published_at: int, warnings: list[str] | None = None) -> dict:
    """The frozen plan the grader scores. Later config changes never alter a published plan."""
    plan = trade_plan(signal)
    session_time = signal.setup_bar_time if signal.model == 'smc' and signal.setup_bar_time else signal.bar_time
    return {'symbol': signal.symbol, 'model': signal.model, 'timeframe': signal.timeframe,
            'session': session_label(signal.symbol, signal.model, session_time), 'cautions': warnings or [],
            'direction': 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL', 'bar_time': signal.bar_time,
            'setup_bar_time': signal.setup_bar_time,
            'published_at': published_at,
            'entry_type': ('limit' if signal.model == 'smc' and signal.entry_mode == 'limit' else 'market'),
            'entry_model': (signal.entry_mode if signal.model == 'smc' else 'signal_close'),
            'entry': plan['entry'], 'stop': plan['stop'],
            'targets': [[multiple, level, note] for multiple, level, note in plan['targets']],
            'entry_expiry_minutes': int(os.getenv('ENTRY_EXPIRY_MINUTES', '120')),
            'max_hold_minutes': int(os.getenv('MAX_HOLD_MINUTES', '1440')),
            'gate': os.getenv('GATE_MODE', 'rules')}


def rows(conn, after: int = 0, limit: int | None = None) -> list[dict]:
    query = 'SELECT seq, event_id, kind, body, hash FROM ledger WHERE seq > %s ORDER BY seq'
    return conn.execute(query + (' LIMIT %s' if limit else ''), (after, limit) if limit else (after,)).fetchall()


def open_plans(conn, symbol: str | None = None) -> list[dict]:
    """Published plans without a terminal row, with the kinds already recorded for each."""
    found = conn.execute('''SELECT p.seq, p.event_id, p.body,
          ARRAY(SELECT k.kind FROM ledger k WHERE k.event_id=p.event_id) AS kinds
        FROM ledger p WHERE p.kind='published' AND NOT EXISTS
          (SELECT 1 FROM ledger t WHERE t.event_id=p.event_id AND t.kind IN ('closed','not_filled'))
        ORDER BY p.seq''').fetchall()
    plans = [{'seq': row['seq'], 'event_id': row['event_id'], 'plan': json.loads(row['body']), 'kinds': set(row['kinds'])}
             for row in found]
    return [item for item in plans if symbol is None or item['plan']['symbol'] == symbol]


def open_count(conn, symbol: str, direction: str, now: float) -> int:
    """Open plans on this symbol and side that can still be live by their own frozen expiry and hold limits.
    A plan past both limits is finished by definition, even if missing candles kept it from being graded."""
    return sum(1 for item in open_plans(conn, symbol) if item['plan']['direction'] == direction and
               item['plan']['published_at'] + 60 * (item['plan']['entry_expiry_minutes'] + item['plan']['max_hold_minutes']) > now)


def trade_view(closed: dict, plan: dict) -> dict:
    return {**closed, 'symbol': plan['symbol'], 'model': plan['model'], 'direction': plan['direction'],
            'session': plan.get('session') or session_label(plan['symbol'], plan['model'], plan['bar_time']),
            'cautioned': bool(plan.get('cautions'))}


def closed_trades(conn, since: float | None = None) -> list[dict]:
    """Closed trades joined with their plans, oldest close first. With `since`, only trades closed at or after
    it: a close is recorded after it happened, so filtering on recorded_at never drops a qualifying row."""
    if since is None:
        closed = conn.execute("SELECT event_id, body FROM ledger WHERE kind='closed' ORDER BY seq").fetchall()
    else:
        closed = conn.execute("SELECT event_id, body FROM ledger WHERE kind='closed' AND recorded_at >= to_timestamp(%s) "
                              'ORDER BY seq', (since,)).fetchall()
    if not closed:
        return []
    plans = {row['event_id']: json.loads(row['body']) for row in conn.execute(
        "SELECT event_id, body FROM ledger WHERE kind='published' AND event_id = ANY(%s)",
        ([row['event_id'] for row in closed],)).fetchall()}
    trades = [trade_view(json.loads(row['body']), plans[row['event_id']]) for row in closed]
    if since is not None:
        trades = [item for item in trades if item['time'] >= since]
    return sorted(trades, key=lambda item: (item['time'], item['seq']))


def history_cautions(conn, signal: Signal, now: float | None = None) -> list[str]:
    """A warning when this symbol, side, model and session has lost money recently on the record itself."""
    need, days = int(os.getenv('HISTORY_MIN_SAMPLES', '30')), int(os.getenv('HISTORY_DAYS', '60'))
    direction = 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL'
    session_time = signal.setup_bar_time if signal.model == 'smc' and signal.setup_bar_time else signal.bar_time
    label = session_label(signal.symbol, signal.model, session_time)
    since = (time.time() if now is None else now) - days * 86400
    same = [item for item in closed_trades(conn, since) if item['symbol'] == signal.symbol
            and item['direction'] == direction and item['model'] == signal.model and item['session'] == label]
    if len(same) < need:
        return []
    wins = sum(1 for item in same if item['r_tp1'] > 0)
    expectancy = sum(item['r_tp1'] for item in same) / len(same)
    if expectancy >= 0 and wins / len(same) >= 0.4:
        return []
    return [f'History: {direction} {signal.symbol} ({signal.model}) in {label} won {wins} of {len(same)} '
            f'({wins / len(same) * 100:.0f}%) over {days} days, expectancy {expectancy:+.2f}R']


def utc(stamp: int, pattern: str = '%Y-%m-%d %H:%M UTC') -> str:
    return datetime.fromtimestamp(stamp, timezone.utc).strftime(pattern)


def result_text(plan: dict, events: list[dict], published_seq: int) -> str:
    decimals = 2 if plan['entry'] >= 100 else 5
    lines = [f'📊 RESULT {plan["direction"]} {plan["symbol"]} {plan["timeframe"]} [{plan["model"]}] | Ledger #{published_seq}',
             f'Plan: entry {plan["entry"]:.{decimals}f} | stop {plan["stop"]:.{decimals}f} | '
             f'TP1 {plan["targets"][0][1]:.{decimals}f}', '']
    labels = {'filled': '✅ Filled', 'sl': '🛑 Stop loss hit', 'be': '➖ Back to entry (break-even)',
              'timeout': '⏱ Time limit reached, closed', 'not_filled': '⌛ Not filled'}
    for event in events:
        kind = event['kind']
        if kind == 'closed':
            lines += ['', f'CLOSED ({event["exit"]}): TP1 basis {event["r_tp1"]:+.2f}R | scale-out {event["r_scaled"]:+.2f}R'
                      + (' | ambiguous candle, worst case counted' if event['ambiguous'] else '')]
            continue
        label = labels.get(kind, f'🎯 {kind.upper()} hit')
        detail = f' {event["price"]:.{decimals}f}' if 'price' in event else ''
        detail += f' ({event["r"]:+.2f}R)' if 'r' in event and kind != 'filled' else ''
        detail += f' ({event["reason"]})' if 'reason' in event else ''
        lines.append(f'{label}{detail} at {utc(event["time"])}')
        if kind == 'tp1':
            lines.append('   Stop moves to entry for the remaining position.')
    lines += ['', 'Graded on broker candles incl. spread. Paper tracking; no order was placed.']
    return '\n'.join(lines)[:4000]


def track_record(conn) -> dict:
    """Everything the public record needs, computed from the ledger alone."""
    # One pass over one fetch: the same rows feed the counts, the closed trades and the chain check.
    all_rows = rows(conn)
    published, not_filled, closed, finished = {}, {}, [], set()
    for row in all_rows:
        if row['kind'] == 'published':
            published[row['event_id']] = json.loads(row['body'])
        elif row['kind'] == 'closed':
            closed.append(trade_view(json.loads(row['body']), published[row['event_id']]))
            finished.add(row['event_id'])
        elif row['kind'] == 'not_filled':
            reason = json.loads(row['body'])['reason']
            not_filled[reason] = not_filled.get(reason, 0) + 1
            finished.add(row['event_id'])
    closed.sort(key=lambda item: (item['time'], item['seq']))
    min_trades, max_dd = int(os.getenv('GO_MIN_TRADES', '150')), float(os.getenv('GO_MAX_DRAWDOWN_R', '10'))

    def group(key):
        buckets = {}
        for item in closed:
            buckets.setdefault(key(item), []).append(item)
        return {name: {k: v for k, v in summarize(items, min_trades, max_dd).items()
                       if k in ('closed', 'wins', 'win_rate', 'total_r_tp1', 'expectancy_r', 'total_r_scaled')}
                for name, items in sorted(buckets.items())}

    return {'published': len(published), 'open': len(set(published) - finished),
            'not_filled': sum(not_filled.values()), 'not_filled_reasons': not_filled,
            'headline': summarize(closed, min_trades, max_dd),
            'by_model': group(lambda item: item['model']),
            'by_symbol': group(lambda item: item['symbol']),
            'by_month': group(lambda item: utc(item['time'], '%Y-%m')),
            'by_session': group(lambda item: f'{item["direction"]} {item["session"]}'),
            'by_caution': group(lambda item: 'with cautions' if item['cautioned'] else 'no cautions'),
            'chain': verify(all_rows),
            'basis': ('Every published plan is graded on broker M1 candles including spread. TP1 basis closes the '
                      'whole position at TP1; scale-out closes equal parts at each target with the stop at entry '
                      'after TP1. Ambiguous candles count the worse outcome. Rows are never removed.')}


def digest_text(record: dict, day: str, yesterday: list[dict]) -> str:
    head = record['headline']
    chain = record['chain']
    wins = sum(1 for item in yesterday if item['r_tp1'] > 0)
    lines = [f'🧾 ZEBRA DAILY RECORD {day}', '',
             f'Yesterday: {len(yesterday)} closed, {wins} won, '
             f'{sum(item["r_tp1"] for item in yesterday):+.2f}R (TP1 basis)',
             f'All time: {head["closed"]} closed | win rate '
             + (f'{head["win_rate"] * 100:.0f}%' if head['win_rate'] is not None else 'n/a')
             + f' | {head["total_r_tp1"]:+.2f}R | expectancy {head["expectancy_r"]:+.3f}R | max drawdown {head["max_drawdown_r"]:.2f}R',
             f'Open: {record["open"]} | never filled: {record["not_filled"]} | ambiguous candles: {head["ambiguous"]}',
             f'Forward test ({head["min_trades"]} trades, drawdown <= {head["max_drawdown_limit_r"]:g}R): {head["verdict"]}', '']
    if chain['valid']:
        lines += [f'Chain head #{chain.get("head_seq", 0)}:', chain.get('head_hash', GENESIS),
                  'Keep this hash: any later edit to past results changes it.']
    else:
        lines.append(f'⚠️ CHAIN BROKEN at row {chain["broken_at"]}: the record was altered.')
    return '\n'.join(lines)[:4000]
