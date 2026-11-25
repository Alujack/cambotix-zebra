"""Live broker quotes for the website: the latest tick per symbol and the minute bar it is building.

Display only. The grader reads closed M1 candles from `candles` and never this table, so it is UNLOGGED (fast; emptied
after a database crash, refilled by the next tick) and carries none of the append-only triggers of the record.
The bar is built from bid prices, like the stored candles, so a live candle and the stored one agree.
"""
from __future__ import annotations

SCHEMA = '''
CREATE UNLOGGED TABLE IF NOT EXISTS quotes (
    symbol text PRIMARY KEY,
    bid double precision NOT NULL,
    ask double precision NOT NULL,
    tick_ms bigint NOT NULL,
    minute bigint NOT NULL,
    o double precision NOT NULL,
    h double precision NOT NULL,
    l double precision NOT NULL,
    c double precision NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
'''

FUTURE_MS = 10_000   # a tick stamped further ahead of the server clock than this is a broken clock, not a price


def migrate(conn) -> None:
    conn.execute(SCHEMA)


def fold(quote: dict | None, ticks: list[tuple[int, float, float]], now_ms: int) -> tuple[dict | None, int]:
    """Apply [time_ms, bid, ask] ticks to the stored quote; returns the new quote and how many ticks were used.

    A tick older than the stored one, or more than FUTURE_MS ahead of `now_ms`, is skipped. A tick in a later minute
    starts a fresh bar; otherwise it moves the bar's high, low and close, so an extreme between two reads is kept."""
    current = dict(quote) if quote else None
    applied = 0
    for time_ms, bid, ask in sorted(ticks, key=lambda tick: tick[0]):
        if time_ms > now_ms + FUTURE_MS or (current and time_ms < current['tick_ms']):
            continue
        minute = time_ms // 60_000 * 60
        if current is None or minute != current['minute']:
            current = {'bid': bid, 'ask': ask, 'tick_ms': time_ms, 'minute': minute, 'o': bid, 'h': bid, 'l': bid, 'c': bid}
        else:
            current.update(bid=bid, ask=ask, tick_ms=time_ms, h=max(current['h'], bid), l=min(current['l'], bid), c=bid)
        applied += 1
    return current, applied
