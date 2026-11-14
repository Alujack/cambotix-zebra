#!/usr/bin/env python3
"""Replay the classic and SMC models over saved broker history and grade every plan the analyzer would publish.

Same code path as live wherever it matters: detection is the feeder's (classic indicators re-implemented
without pandas, SMC via scripts/smc_engine.Engine); every payload goes through app.domain's rule checks;
plans are frozen with app.ledger.plan_record; grading is app.grader.simulate on M1 candles including spread;
statistics are app.grader.summarize. Settings come from the environment (.env), and --set overrides them.

Not reproduced: the news blackout (no historical calendar) and the live feeder's 1500-bar SMC replay window
(the engine runs once over the whole history instead).

Data: .local/history/<SYMBOL>_{m1,m15,h4,d1,w1}.csv from scripts/pull_history.py (MT5, Windows) or
scripts/pull_dukascopy.py (no MT5, runs on the Mac).
Run in the analyzer image, which has the app's dependencies and reads .env:
  docker compose run --rm --no-deps -v "$PWD:/work" -w /work analyzer python scripts/backtest.py
"""
from __future__ import annotations

import argparse
import bisect
import csv
import itertools
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts')]

from smc_engine import Config, Engine  # noqa: E402
from app.domain import Signal, classic_rules, smc_rules  # noqa: E402
from app.grader import simulate, summarize  # noqa: E402
from app import ledger  # noqa: E402

M15, MINUTE = 900, 60
SWING_BARS = 10


# -- data ---------------------------------------------------------------------------------------------
def load(folder: Path, symbol: str, frame: str) -> list[dict]:
    path = folder / f'{symbol}_{frame}.csv'
    if not path.exists():
        raise SystemExit(f'missing {path}: run `python3 scripts/pull_dukascopy.py --symbol {symbol}` (any OS), '
                         'or `py -3.13 scripts/pull_history.py` on Windows with MT5 logged in')
    with path.open() as handle:
        return [{'t': int(r['t']), 'o': float(r['o']), 'h': float(r['h']), 'l': float(r['l']), 'c': float(r['c']),
                 'spread': float(r.get('spread') or 0)} for r in csv.DictReader(handle)]


# -- classic indicators: the feeder's pandas formulas, element by element ------------------------------
def ewm(values: list[float | None], alpha: float) -> list[float | None]:
    """pandas ewm(adjust=False).mean(): starts at the first non-missing value, missing inputs keep the last."""
    out, state = [], None
    for v in values:
        if v is not None:
            state = v if state is None else alpha * v + (1 - alpha) * state
        out.append(state)
    return out


def ema(values, n):
    return ewm(values, 2 / (n + 1))


def rma(values, n):
    return ewm(values, 1 / n)


def classic_indicators(bars: list[dict]) -> list[dict]:
    close = [b['c'] for b in bars]
    tr = [bars[0]['h'] - bars[0]['l']] + [max(b['h'] - b['l'], abs(b['h'] - p['c']), abs(b['l'] - p['c']))
                                          for p, b in zip(bars, bars[1:])]
    delta = [None] + [b - a for a, b in zip(close, close[1:])]
    gain = rma([None if d is None else max(d, 0.0) for d in delta], 14)
    loss = rma([None if d is None else max(-d, 0.0) for d in delta], 14)
    rsi = [None if g is None or not lo else 100 - 100 / (1 + g / lo) for g, lo in zip(gain, loss)]
    fast, slow = ema(close, 12), ema(close, 26)
    macd = [a - b for a, b in zip(fast, slow)]
    signal = ema(macd, 9)
    plus, minus = [0.0], [0.0]
    for p, b in zip(bars, bars[1:]):
        up, down = b['h'] - p['h'], p['l'] - b['l']
        plus.append(up if up > down and up > 0 else 0.0)
        minus.append(down if down > up and down > 0 else 0.0)
    atr = rma(tr, 14)
    rp, rm = rma(plus, 14), rma(minus, 14)
    dx = []
    for a, p, m in zip(atr, rp, rm):
        if not a:
            dx.append(None)
            continue
        pdi, mdi = 100 * p / a, 100 * m / a
        dx.append(None if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi))
    adx = rma(dx, 14)
    e20, e50, e200 = ema(close, 20), ema(close, 50), ema(close, 200)
    rows = []
    for i, b in enumerate(bars):
        prior = bars[max(0, i - SWING_BARS):i]
        full = i >= SWING_BARS
        rows.append({'t': b['t'], 'close': b['c'], 'ema20': e20[i], 'ema50': e50[i], 'ema200': e200[i], 'rsi': rsi[i],
                     'macd_hist': macd[i] - signal[i], 'adx': adx[i], 'atr': atr[i],
                     'swing_high': max(x['h'] for x in prior) if full else None,
                     'swing_low': min(x['l'] for x in prior) if full else None})
    return rows


def qualifies(row: dict, direction: str) -> bool:
    keys = ('ema200', 'adx', 'atr', 'rsi', 'macd_hist', 'swing_high', 'swing_low')
    if any(row[k] is None for k in keys):
        return False
    atr_percent = row['atr'] / row['close'] * 100
    if not float(os.getenv('MIN_ATR_PERCENT', '0.02')) <= atr_percent <= float(os.getenv('MAX_ATR_PERCENT', '0.5')):
        return False
    if row['adx'] < float(os.getenv('MIN_ADX', '20')):
        return False
    if direction == 'BUY_SETUP':
        return row['close'] > row['ema20'] > row['ema50'] > row['ema200'] and 50 <= row['rsi'] <= 70 and row['macd_hist'] > 0
    return row['close'] < row['ema20'] < row['ema50'] < row['ema200'] and 30 <= row['rsi'] <= 50 and row['macd_hist'] < 0


def in_session(close_epoch: int) -> bool:
    stamp = datetime.fromtimestamp(close_epoch - M15, timezone.utc)
    return any((local := stamp.astimezone(ZoneInfo(z))).weekday() < 5 and 8 <= local.hour < 17
               for z in ('Europe/London', 'America/New_York'))


def classic_payloads(symbol: str, rows: list[dict]) -> list[dict]:
    out = []
    for prev, row in zip(rows, rows[1:]):
        close_epoch = row['t'] + M15
        for direction in ('BUY_SETUP', 'SELL_SETUP'):
            if qualifies(row, direction) and not qualifies(prev, direction) and in_session(close_epoch):
                out.append({'event_id': f'{symbol}-15m-{close_epoch}-{direction}', 'symbol': symbol, 'timeframe': '15m',
                            'bar_time': close_epoch, 'signal': direction, 'model': 'classic', 'price': row['close'],
                            **{k: round(row[k], 8) for k in ('ema20', 'ema50', 'ema200', 'rsi', 'macd_hist', 'adx',
                                                               'atr', 'swing_high', 'swing_low')}})
    return out


# -- SMC ---------------------------------------------------------------------------------------------
class FastEngine(Engine):
    """Same engine; higher-timeframe lookups by binary search instead of a scan per 15m bar."""

    def _context(self, d1, h4, w1):
        super()._context(d1, h4, w1)
        self._times = {id(series): [b['t'] for b in series] for series in (d1, h4, w1)}

    def _last_closed(self, bars, period, stamp):
        k = bisect.bisect_right(self._times[id(bars)], stamp - period) - 1
        return k if k >= 0 else None

    def _containing(self, bars, stamp):
        k = bisect.bisect_right(self._times[id(bars)], stamp) - 1
        return k if k >= 0 else None


def smc_config(tick: float) -> Config:
    truthy = lambda key, default: os.getenv(key, default).strip().lower() == 'true'
    return Config(killzones=tuple(k.strip() for k in os.getenv('KILLZONES', 'London,NY AM').split(',') if k.strip()),
                  require_htf=truthy('REQUIRE_HTF_BIAS', 'true'), require_discount=truthy('REQUIRE_DISCOUNT', 'true'),
                  min_rr=float(os.getenv('MIN_RR', '1.5')), min_score=int(os.getenv('MIN_SMC_SCORE', '70')),
                  min_atr_pct=float(os.getenv('MIN_ATR_PERCENT', '0.02')),
                  max_atr_pct=float(os.getenv('MAX_ATR_PERCENT', '0.5')), tick=tick)


def smc_payloads(symbol: str, data: dict, tick: float) -> list[dict]:
    strip = lambda series: [{k: b[k] for k in 'tohlc'} for b in series]
    return FastEngine(symbol, smc_config(tick)).run(strip(data['m15']), strip(data['d1']), strip(data['h4']),
                                                    strip(data['w1']))


# -- publish + grade ---------------------------------------------------------------------------------
def grade(payloads: list[dict], m1: list[dict]) -> tuple[list[dict], dict]:
    """Apply the analyzer's rules and open-plan limit in time order; grade each published plan."""
    times = [c['t'] for c in m1]
    end = m1[-1]['t'] + MINUTE if m1 else 0
    limit = int(os.getenv('MAX_OPEN_SAME_DIRECTION', '1'))
    open_until: list[tuple[str, int]] = []
    trades, rejected = [], {}
    for body in sorted(payloads, key=lambda p: (p['bar_time'], p['model'], p['signal'])):
        signal = Signal.model_validate(body)
        reasons = smc_rules(signal) if signal.model == 'smc' else classic_rules(signal)
        direction = 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL'
        if not reasons and limit > 0 and sum(1 for d, until in open_until if d == direction and until > signal.bar_time) >= limit:
            reasons = ['open_plan_same_direction']
        if reasons:
            for r in reasons:
                rejected[r] = rejected.get(r, 0) + 1
            continue
        plan = ledger.plan_record(signal, signal.bar_time)
        horizon = signal.bar_time + MINUTE * (plan['entry_expiry_minutes'] + plan['max_hold_minutes'] + 1)
        if horizon > end:
            break                                        # history ends before this plan could finish
        lo, hi = bisect.bisect_left(times, signal.bar_time), bisect.bisect_left(times, horizon)
        events = simulate(plan, m1[lo:hi], horizon)
        last = events[-1] if events else None
        open_until.append((direction, last['time'] if last and last['kind'] in ('closed', 'not_filled') else horizon))
        if last and last['kind'] == 'closed':
            ny = datetime.fromtimestamp(signal.bar_time - M15, timezone.utc).astimezone(ZoneInfo('America/New_York'))
            trades.append({**last, 'seq': len(trades), 'model': plan['model'], 'direction': direction,
                           'session': plan['session'], 'published_at': signal.bar_time, 'entry': plan['entry'],
                           'stop': plan['stop'], 'tp1_r': plan['targets'][0][0], 'ny_hour': ny.hour,
                           'month': datetime.fromtimestamp(signal.bar_time, timezone.utc).strftime('%Y-%m')})
        else:
            key = 'not_filled:' + (last['reason'] if last and last['kind'] == 'not_filled' else 'unresolved')
            rejected[key] = rejected.get(key, 0) + 1
    return trades, rejected


def stats(trades: list[dict]) -> dict:
    s = summarize(sorted(trades, key=lambda t: (t['time'], t['seq'])), 0, float('inf'))
    return {k: s[k] for k in ('closed', 'wins', 'win_rate', 'expectancy_r', 'total_r_tp1', 'profit_factor',
                              'max_drawdown_r', 'total_r_scaled')}


def line(label: str, trades: list[dict]) -> str:
    s = stats(trades)
    if not s['closed']:
        return f'{label:<22} {"no trades":>8}'
    wr = f'{s["win_rate"] * 100:.0f}%'
    pf = '-' if s['profit_factor'] is None else f'{s["profit_factor"]:.2f}'
    return (f'{label:<22} {s["closed"]:>5} {wr:>5} {s["expectancy_r"]:>+7.3f} {s["total_r_tp1"]:>+8.2f} {pf:>5} '
            f'{s["max_drawdown_r"]:>6.2f} {s["total_r_scaled"]:>+8.2f}')


HEADER = f'{"":<22} {"trades":>5} {"win":>5} {"exp R":>7} {"total R":>8} {"PF":>5} {"maxDD":>6} {"scaled":>8}'


def run(data: dict, symbol: str, tick: float, models: set[str]) -> tuple[list[dict], dict]:
    payloads = []
    if 'classic' in models:
        payloads += classic_payloads(symbol, classic_indicators(data['m15']))
    if 'smc' in models:
        payloads += smc_payloads(symbol, data, tick)
    return grade(payloads, data['m1'])


def report(trades: list[dict], rejected: dict, split: int | None) -> None:
    print(HEADER)
    print(line('ALL', trades))
    for title, key in (('model', 'model'), ('direction', 'direction'), ('session', 'session'), ('month', 'month')):
        print(f'-- by {title}')
        for value in sorted({t[key] for t in trades}):
            print(line(f'  {value}', [t for t in trades if t[key] == value]))
    if split:
        print('-- in-sample / out-of-sample')
        print(line('  first 2/3', [t for t in trades if t['published_at'] < split]))
        print(line('  last 1/3', [t for t in trades if t['published_at'] >= split]))
    if rejected:
        print('-- not published / not filled: ' + ', '.join(f'{k} {v}' for k, v in sorted(rejected.items(), key=lambda kv: -kv[1])))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--data', default=str(ROOT / '.local' / 'history'))
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--models', default='classic,smc')
    parser.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help='override a .env setting')
    parser.add_argument('--sweep', action='append', default=[], metavar='KEY=V1|V2',
                        help='grid-search a setting; repeat for more keys. Ranked on the first 2/3, checked on the last 1/3')
    parser.add_argument('--trades', help='write every graded trade to this JSON file')
    args = parser.parse_args()

    for item in args.set:
        key, _, value = item.partition('=')
        os.environ[key.strip()] = value.strip()
    folder = Path(args.data)
    data = {frame: load(folder, args.symbol, frame) for frame in ('m1', 'm15', 'h4', 'd1', 'w1')}
    meta_path = folder / f'{args.symbol}_meta.json'
    tick = json.loads(meta_path.read_text()).get('point', 0.01) if meta_path.exists() else 0.01
    models = {m.strip() for m in args.models.split(',') if m.strip()}
    first, last = data['m1'][0]['t'], data['m1'][-1]['t']
    split = first + (last - first) * 2 // 3
    stamp = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d')
    print(f'{args.symbol} M1 {stamp(first)} .. {stamp(last)} ({len(data["m15"])} M15 bars), models={",".join(sorted(models))}')

    if not args.sweep:
        print('settings: ' + ', '.join(f'{k}={os.getenv(k)}' for k in ('TP_R_MULTIPLES', 'MIN_RR', 'STOP_ATR_MULTIPLE',
                                                                         'MIN_ADX', 'KILLZONES', 'REQUIRE_HTF_BIAS',
                                                                         'REQUIRE_DISCOUNT', 'MIN_SMC_SCORE')))
        trades, rejected = run(data, args.symbol, tick, models)
        report(trades, rejected, split)
        if args.trades:
            Path(args.trades).write_text(json.dumps(trades, indent=1))
        return

    grid = [(key, values.split('|')) for key, _, values in (s.partition('=') for s in args.sweep)]
    results = []
    for combo in itertools.product(*[values for _, values in grid]):
        for (key, _), value in zip(grid, combo):
            os.environ[key] = value
        trades, _ = run(data, args.symbol, tick, models)
        label = ' '.join(f'{key}={value}' for (key, _), value in zip(grid, combo))
        ins = [t for t in trades if t['published_at'] < split]
        out = [t for t in trades if t['published_at'] >= split]
        results.append((stats(ins)['total_r_tp1'], label, ins, out))
    print(f'ranked by total R in the first 2/3 (before {stamp(split)}); the second line of each is the unseen last 1/3')
    print(HEADER)
    for _, label, ins, out in sorted(results, key=lambda r: -r[0]):
        print(label)
        print(line('  in-sample', ins))
        print(line('  out-of-sample', out))


if __name__ == '__main__':
    main()
