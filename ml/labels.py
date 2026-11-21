"""Outcome labels from the live grader.

Every candidate becomes the plan the analyzer would freeze for an ICT signal (limit at the FVG edge, expiry
ICT_ENTRY_EXPIRY_MINUTES, hold ICT_MAX_HOLD_MINUTES, one target) and is scored by app.grader.simulate on M1 with
spread: fills at the ask for buys, the worse outcome inside an ambiguous candle. So a label here means exactly what
a graded live trade would have meant.
"""
from __future__ import annotations

import bisect
import sys

from ml.data import ROOT, Bars

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.grader import simulate  # noqa: E402

MINUTE = 60
ENTRY_EXPIRY_MINUTES = 120
MAX_HOLD_MINUTES = 360
WEEKEND = 3 * 86_400


def plan_for(row: dict, rr: float, expiry: int = ENTRY_EXPIRY_MINUTES, hold: int = MAX_HOLD_MINUTES) -> dict:
    return {'direction': row['side'], 'entry_type': 'limit', 'entry': row['entry'], 'stop': row['stop'],
            'targets': [[rr, row['target'], f'{rr:g}R']], 'published_at': int(row['bar_time']),
            'entry_expiry_minutes': expiry, 'max_hold_minutes': hold}


def label(rows: list[dict], m1: Bars, rr: float = 2.0, expiry: int = ENTRY_EXPIRY_MINUTES,
          hold: int = MAX_HOLD_MINUTES) -> list[dict]:
    """Outcome fields for each candidate row (same order). Rows whose horizon passes the end of M1 are 'unresolved'."""
    times = m1.t
    end = int(times[-1]) + MINUTE if len(times) else 0
    out = []
    for row in rows:
        plan = plan_for(row, rr, expiry, hold)
        start = plan['published_at']
        horizon = start + MINUTE * (expiry + hold + 1)
        if horizon > end:
            out.append({'outcome': 'unresolved', 'r': float('nan'), 'win': float('nan'), 'exit': '',
                        'ambiguous': 0.0, 'fill_time': float('nan'), 'end_time': float(horizon)})
            continue
        lo, hi = bisect.bisect_left(times, start), bisect.bisect_left(times, horizon)
        events = simulate(plan, m1.dicts(lo, hi), horizon)
        last = events[-1] if events else None
        if (last is None or last['kind'] not in ('closed', 'not_filled')) and horizon + WEEKEND <= end:
            # A weekend or a data gap inside the window: the live grader keeps the trade open until the first
            # candle past its hold limit, so give it the candles after the gap.
            horizon += WEEKEND
            hi = bisect.bisect_left(times, horizon)
            events = simulate(plan, m1.dicts(lo, hi), horizon)
            last = events[-1] if events else None
        fill = next((e['time'] for e in events if e['kind'] == 'filled'), float('nan'))
        if last and last['kind'] == 'closed':
            out.append({'outcome': 'closed', 'r': float(last['r_tp1']), 'win': float(last['r_tp1'] > 0),
                        'exit': last['exit'], 'ambiguous': float(last['ambiguous']), 'fill_time': float(fill),
                        'end_time': float(last['time'])})
        elif last and last['kind'] == 'not_filled':
            out.append({'outcome': 'not_filled:' + last['reason'], 'r': 0.0, 'win': float('nan'), 'exit': '',
                        'ambiguous': 0.0, 'fill_time': float('nan'), 'end_time': float(last['time'])})
        else:
            out.append({'outcome': 'unresolved', 'r': float('nan'), 'win': float('nan'), 'exit': '',
                        'ambiguous': 0.0, 'fill_time': float('nan'), 'end_time': float(horizon)})
    return out
