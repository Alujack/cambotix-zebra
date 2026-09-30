"""Deterministic outcome grading of a published trade plan against broker M1 candles.

Candles are broker bid prices with the bar's spread in price units, as MT5 reports them. A BUY fills at the ask
and exits at the bid; a SELL fills at the bid and exits at the ask. Whenever one candle could have hit two levels
and the order inside the candle is unknown, the worse outcome for the trader is assumed and the result is flagged
ambiguous. The same candles always produce the same events, so grading can be rerun as coverage grows.

Scores: r_tp1 closes the whole position at TP1 (the headline). r_scaled closes equal parts at each target, moving
the stop to break-even after TP1. Both are measured against the actual fill, so R is the real risk taken.
"""
from __future__ import annotations

MINUTE = 60


def find_fill(plan: dict, candles: list[dict], through: int, sign: int) -> tuple[dict | None, int, list[dict]]:
    """(fill, index of the fill candle, terminal events). No fill and no events means still waiting."""
    stop, tp1 = plan['stop'], plan['targets'][0][1]
    if plan['entry_type'] == 'market':
        if not candles:
            return None, 0, []
        first = candles[0]
        price = first['o'] + (first['spread'] if sign > 0 else 0)
        if sign * (price - stop) <= 0:
            return None, 0, [{'kind': 'not_filled', 'time': first['t'], 'reason': 'opened_beyond_stop'}]
        if sign * (price - tp1) >= 0:
            return None, 0, [{'kind': 'not_filled', 'time': first['t'], 'reason': 'opened_beyond_tp1'}]
        return {'time': first['t'], 'price': price}, 0, []
    expires = plan['published_at'] + plan['entry_expiry_minutes'] * MINUTE
    entry = plan['entry']
    for index, c in enumerate(candles):
        if c['t'] >= expires:
            break
        ask_open, ask_low = c['o'] + c['spread'], c['l'] + c['spread']
        if (ask_low <= entry) if sign > 0 else (c['h'] >= entry):
            # A gap through the limit fills at the better open price.
            price = min(entry, ask_open) if sign > 0 else max(entry, c['o'])
            return {'time': c['t'], 'price': price}, index, []
        if (c['h'] >= tp1) if sign > 0 else (ask_low <= tp1):
            return None, 0, [{'kind': 'not_filled', 'time': c['t'], 'reason': 'tp1_reached_before_entry'}]
    if through >= expires:
        return None, 0, [{'kind': 'not_filled', 'time': expires, 'reason': 'entry_expired'}]
    return None, 0, []


def simulate(plan: dict, candles: list[dict], through: int) -> list[dict]:
    """Events for `plan` from candles covering [plan published_at, through). The last event is terminal
    ('not_filled' or 'closed') once the trade is finished; otherwise the trade is still open."""
    sign = 1 if plan['direction'] == 'BUY' else -1
    targets = [price for _, price, _ in plan['targets']]
    usable = sorted((c for c in candles if c['t'] >= plan['published_at'] and c['t'] + MINUTE <= through),
                    key=lambda c: c['t'])
    fill, start, terminal = find_fill(plan, usable, through, sign)
    if fill is None:
        return terminal
    risk = abs(fill['price'] - plan['stop'])

    def r(price):
        return round(sign * (price - fill['price']) / risk, 4)

    def against(level, c):   # exit-side price reached the level against the position
        return c['l'] <= level if sign > 0 else c['h'] + c['spread'] >= level

    def favour(level, c):    # exit-side price reached the level in favour of the position
        return c['h'] >= level if sign > 0 else c['l'] + c['spread'] <= level

    target_r = [r(price) for price in targets]
    events = [{'kind': 'filled', 'time': fill['time'], 'price': round(fill['price'], 8)}]
    state = {'hit': 0, 'ambiguous': False}

    def finish(time, exit_kind, exit_r):
        hit = state['hit']
        tp1 = target_r[0] if hit else exit_r
        scaled = (sum(target_r[:hit]) + (len(targets) - hit) * exit_r) / len(targets)
        events.append({'kind': 'closed', 'time': time, 'exit': exit_kind, 'targets_hit': hit,
                       'ambiguous': state['ambiguous'], 'r_tp1': round(tp1, 4), 'r_scaled': round(scaled, 4)})
        return events

    hold_until = fill['time'] + plan['max_hold_minutes'] * MINUTE
    limit_fill = plan['entry_type'] == 'limit'
    for position, c in enumerate(usable[start:]):
        if c['t'] >= hold_until:
            price = c['o'] if sign > 0 else c['o'] + c['spread']
            events.append({'kind': 'timeout', 'time': c['t'], 'price': round(price, 8), 'r': r(price)})
            return finish(c['t'], 'timeout', r(price))
        hit = state['hit']
        level = plan['stop'] if hit == 0 else fill['price']
        # A limit fill candle cannot credit targets: they may have printed before the fill.
        fill_candle = limit_fill and position == 0
        reached = [] if fill_candle else [k for k in range(hit, len(targets)) if favour(targets[k], c)]
        if against(level, c):
            # Order inside the candle is unknown: assume the stop (or break-even) came first.
            state['ambiguous'] = state['ambiguous'] or bool(reached)
            kind, exit_r = ('sl', -1.0) if hit == 0 else ('be', 0.0)
            events.append({'kind': kind, 'time': c['t'], 'price': round(level, 8), 'r': exit_r})
            return finish(c['t'], kind, exit_r)
        if not reached:
            continue
        if hit == 0 and against(fill['price'], c):
            # TP1 and a return to entry in one candle: keep TP1, assume break-even came before later targets.
            state['ambiguous'] = state['ambiguous'] or len(reached) > 1
            events.append({'kind': 'tp1', 'time': c['t'], 'price': round(targets[0], 8), 'r': target_r[0]})
            state['hit'] = 1
            events.append({'kind': 'be', 'time': c['t'], 'price': round(fill['price'], 8), 'r': 0.0})
            return finish(c['t'], 'be', 0.0)
        for k in reached:
            events.append({'kind': f'tp{k + 1}', 'time': c['t'], 'price': round(targets[k], 8), 'r': target_r[k]})
        state['hit'] = reached[-1] + 1
        if state['hit'] == len(targets):
            return finish(c['t'], 'final_target', target_r[-1])
    return events


def summarize(outcomes: list[dict], min_trades: int, max_drawdown: float) -> dict:
    """Headline statistics over closed trades (`closed` bodies, oldest first) and the forward-test verdict."""
    n = len(outcomes)
    wins = sum(1 for o in outcomes if o['r_tp1'] > 0)
    gains = sum(o['r_tp1'] for o in outcomes if o['r_tp1'] > 0)
    losses = -sum(o['r_tp1'] for o in outcomes if o['r_tp1'] < 0)
    total = sum(o['r_tp1'] for o in outcomes)
    equity = peak = drawdown = 0.0
    for o in outcomes:
        equity += o['r_tp1']
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    expectancy = total / n if n else 0.0
    if n < min_trades:
        verdict = 'NOT ENOUGH DATA'
    elif expectancy > 0 and drawdown <= max_drawdown:
        verdict = 'GO'
    else:
        verdict = 'NO-GO'
    return {'closed': n, 'wins': wins, 'win_rate': round(wins / n, 4) if n else None,
            'total_r_tp1': round(total, 2), 'expectancy_r': round(expectancy, 3),
            'profit_factor': round(gains / losses, 2) if losses else None,
            'total_r_scaled': round(sum(o['r_scaled'] for o in outcomes), 2),
            'max_drawdown_r': round(drawdown, 2), 'ambiguous': sum(1 for o in outcomes if o['ambiguous']),
            'verdict': verdict, 'min_trades': min_trades, 'max_drawdown_limit_r': max_drawdown}
