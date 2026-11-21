#!/usr/bin/env python3
"""Replay the classic, CRT, ICT, EMA and MSS models over saved broker history and grade every plan the analyzer would publish.

Same code path as live wherever it matters: detection is the feeder's (classic indicators re-implemented
without pandas, CRT via scripts/crt_engine.detect, ICT via scripts/ict_engine.detect on M5, the EMA scalp via
scripts/ema_engine.detect on M1, sweep + MSS via scripts/mss_engine.detect on H1 built from M15); every payload goes
through app.domain's rule checks;
plans are frozen with app.ledger.plan_record; grading is app.grader.simulate on M1 candles including spread;
statistics are app.grader.summarize. Settings come from the environment (.env), and --set overrides them.

Not reproduced: the news blackout (no historical calendar).

Data: .local/history/<SYMBOL>_{m1,m15}.csv (ICT also needs _m5, built from M1 when missing) from scripts/pull_history.py (MT5, Windows) or
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

import crt_engine  # noqa: E402
import ema_engine  # noqa: E402
import ict_engine  # noqa: E402
import mss_engine  # noqa: E402
from app.domain import MODEL_RULES, Signal  # noqa: E402
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


# -- CRT ---------------------------------------------------------------------------------------------
def crt_config(symbol: str) -> crt_engine.CrtConfig:
    exempt = {x.strip().upper() for x in os.getenv('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if x.strip()}
    keys = os.getenv('CRT_KEY_TIMES', '').strip()
    return crt_engine.CrtConfig(htf_hours=int(os.getenv('CRT_HTF_HOURS', '4')),
                                key_times=tuple(int(k) for k in keys.split(',') if k.strip().isdigit()),
                                min_rr=float(os.getenv('CRT_MIN_RR', '2.0')),
                                stop_buffer_atr=float(os.getenv('CRT_STOP_BUFFER_ATR', '0.1')),
                                crypto=symbol in exempt)


def crt_payloads(symbol: str, data: dict) -> list[dict]:
    return crt_engine.detect(symbol, [{k: b[k] for k in 'tohlc'} for b in data['m15']], crt_config(symbol))


# -- ICT ---------------------------------------------------------------------------------------------
def m5_from_m1(m1: list[dict]) -> list[dict]:
    out: list[dict] = []
    for bar in m1:
        key = bar['t'] - bar['t'] % 300
        if out and out[-1]['t'] == key:
            last = out[-1]
            last['h'], last['l'], last['c'] = max(last['h'], bar['h']), min(last['l'], bar['l']), bar['c']
        else:
            out.append({'t': key, 'o': bar['o'], 'h': bar['h'], 'l': bar['l'], 'c': bar['c']})
    return out


def ict_payloads(symbol: str, data: dict) -> list[dict]:
    m5 = data.get('m5') or m5_from_m1(data['m1'])
    cfg = ict_engine.IctConfig(min_rr=float(os.getenv('ICT_MIN_RR', '2.0')))
    return ict_engine.detect(symbol, [{k: b[k] for k in 'tohlc'} for b in m5], cfg)


# -- EMA scalp ---------------------------------------------------------------------------------------
def ema_payloads(symbol: str, data: dict) -> list[dict]:
    exempt = {x.strip().upper() for x in os.getenv('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if x.strip()}
    cfg = ema_engine.EmaConfig(min_rr=float(os.getenv('EMA_MIN_RR', '1.5')),
                               pullback_bars=int(os.getenv('EMA_PULLBACK_BARS', '5')),
                               stop_buffer_atr=float(os.getenv('EMA_STOP_BUFFER_ATR', '0.2')),
                               min_risk_atr=float(os.getenv('EMA_MIN_RISK_ATR', '1.0')),
                               max_risk_atr=float(os.getenv('EMA_MAX_RISK_ATR', '4.0')),
                               cooldown_bars=int(os.getenv('EMA_COOLDOWN_BARS', '10')), crypto=symbol in exempt)
    return ema_engine.detect(symbol, [{k: b[k] for k in 'tohlc'} for b in data['m1']], cfg)


# -- sweep + MSS -------------------------------------------------------------------------------------
def mss_payloads(symbol: str, data: dict) -> list[dict]:
    exempt = {x.strip().upper() for x in os.getenv('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if x.strip()}
    cfg = mss_engine.MssConfig(min_rr=float(os.getenv('MSS_MIN_RR', '2.0')),
                               stop_buffer_atr=float(os.getenv('MSS_STOP_BUFFER_ATR', '0.5')),
                               body_atr=float(os.getenv('MSS_BODY_ATR', '1.5')), crypto=symbol in exempt)
    return mss_engine.detect(symbol, [{k: b[k] for k in 'tohlc'} for b in data['m15']], cfg)


# -- publish + grade ---------------------------------------------------------------------------------
def grade(payloads: list[dict], m1: list[dict]) -> tuple[list[dict], dict]:
    """Apply the analyzer's rules and open-plan limit in time order; grade each published plan."""
    times = [c['t'] for c in m1]
    end = m1[-1]['t'] + MINUTE if m1 else 0
    limit = int(os.getenv('MAX_OPEN_SAME_DIRECTION', '1'))
    open_until: list[tuple[str, str, int]] = []        # (model, direction, open until): the analyzer's per-model limit
    trades, rejected = [], {}
    for body in sorted(payloads, key=lambda p: (p['bar_time'], p['model'], p['signal'])):
        signal = Signal.model_validate(body)
        reasons = MODEL_RULES[signal.model](signal)
        direction = 'BUY' if signal.signal == 'BUY_SETUP' else 'SELL'
        bar_time, opened_at = signal.bar_time, signal.bar_time - signal.bar_seconds
        if not reasons and limit > 0 and sum(1 for m, d, until in open_until
                                             if m == signal.model and d == direction and until > bar_time) >= limit:
            reasons = ['open_plan_same_direction']
        if reasons:
            for r in reasons:
                rejected[r] = rejected.get(r, 0) + 1
            continue
        plan = ledger.plan_record(signal, signal.bar_time)
        horizon = bar_time + MINUTE * (plan['entry_expiry_minutes'] + plan['max_hold_minutes'] + 1)
        if horizon > end:
            break                                        # history ends before this plan could finish
        lo, hi = bisect.bisect_left(times, bar_time), bisect.bisect_left(times, horizon)
        events = simulate(plan, m1[lo:hi], horizon)
        last = events[-1] if events else None
        open_until.append((plan['model'], direction,
                           last['time'] if last and last['kind'] in ('closed', 'not_filled') else horizon))
        if last and last['kind'] == 'closed':
            ny = datetime.fromtimestamp(opened_at, timezone.utc).astimezone(ZoneInfo('America/New_York'))
            trades.append({**last, 'seq': len(trades), 'model': plan['model'], 'direction': direction,
                           'session': plan['session'], 'published_at': bar_time, 'entry': plan['entry'],
                           'stop': plan['stop'], 'tp1_r': plan['targets'][0][0], 'ny_hour': ny.hour,
                           'month': datetime.fromtimestamp(bar_time, timezone.utc).strftime('%Y-%m')})
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


def run(data: dict, symbol: str, models: set[str]) -> tuple[list[dict], dict]:
    payloads = []
    if 'classic' in models:
        payloads += classic_payloads(symbol, classic_indicators(data['m15']))
    if 'crt' in models:
        payloads += crt_payloads(symbol, data)
    if 'ict' in models:
        payloads += ict_payloads(symbol, data)
    if 'ema' in models:
        payloads += ema_payloads(symbol, data)
    if 'mss' in models:
        payloads += mss_payloads(symbol, data)
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
    parser.add_argument('--models', default='classic,crt')
    parser.add_argument('--from', dest='start', metavar='YYYY-MM-DD', help='replay from this UTC date (default: all history)')
    parser.add_argument('--to', dest='end', metavar='YYYY-MM-DD', help='replay up to this UTC date, exclusive')
    parser.add_argument('--set', action='append', default=[], metavar='KEY=VALUE', help='override a .env setting')
    parser.add_argument('--sweep', action='append', default=[], metavar='KEY=V1|V2',
                        help='grid-search a setting; repeat for more keys. Ranked on the first 2/3, checked on the last 1/3')
    parser.add_argument('--trades', help='write every graded trade to this JSON file')
    args = parser.parse_args()

    for item in args.set:
        key, _, value = item.partition('=')
        os.environ[key.strip()] = value.strip()
    # The analyzer only accepts symbols listed in SYMBOLS; a backtest may replay any symbol with saved history.
    enabled = {x.strip().upper() for x in os.getenv('SYMBOLS', 'XAUUSD').split(',') if x.strip()}
    os.environ['SYMBOLS'] = ','.join(sorted(enabled | {args.symbol.upper()}))
    folder = Path(args.data)
    models = {m.strip() for m in args.models.split(',') if m.strip()}
    if not models <= {'classic', 'crt', 'ict', 'ema', 'mss'}:
        raise SystemExit('--models accepts a comma list of classic, crt, ict, ema and mss')
    data = {frame: load(folder, args.symbol, frame) for frame in ('m1', 'm15')}
    if 'ict' in models and (folder / f'{args.symbol}_m5.csv').exists():
        data['m5'] = load(folder, args.symbol, 'm5')
    if args.start or args.end:
        epoch = lambda day: int(datetime.strptime(day, '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())
        lo, hi = epoch(args.start) if args.start else 0, epoch(args.end) if args.end else float('inf')
        data = {frame: [b for b in bars if lo <= b['t'] < hi] for frame, bars in data.items()}
        if not data['m1']:
            raise SystemExit(f'no {args.symbol} M1 candles between {args.start or "the start"} and {args.end or "the end"}')
    first, last = data['m1'][0]['t'], data['m1'][-1]['t']
    split = first + (last - first) * 2 // 3
    stamp = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d')
    print(f'{args.symbol} M1 {stamp(first)} .. {stamp(last)} ({len(data["m15"])} M15 bars), models={",".join(sorted(models))}')

    if not args.sweep:
        print('settings: ' + ', '.join(f'{k}={os.getenv(k)}' for k in ('TP_R_MULTIPLES', 'STOP_ATR_MULTIPLE', 'MIN_ADX',
                                                                         'CRT_HTF_HOURS', 'CRT_KEY_TIMES', 'CRT_MIN_RR',
                                                                         'CRT_MAX_HOLD_CANDLES', 'ICT_SYMBOLS',
                                                                         'ICT_ENTRY_EXPIRY_MINUTES', 'ICT_MAX_HOLD_MINUTES',
                                                                         'EMA_SYMBOLS', 'EMA_MIN_RR', 'EMA_MAX_HOLD_MINUTES',
                                                                         'MSS_SYMBOLS', 'MSS_MIN_RR', 'MSS_MAX_HOLD_HOURS')))
        trades, rejected = run(data, args.symbol, models)
        report(trades, rejected, split)
        if args.trades:
            Path(args.trades).write_text(json.dumps(trades, indent=1))
        return

    grid = [(key, values.split('|')) for key, _, values in (s.partition('=') for s in args.sweep)]
    results = []
    for combo in itertools.product(*[values for _, values in grid]):
        for (key, _), value in zip(grid, combo):
            os.environ[key] = value
        trades, _ = run(data, args.symbol, models)
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
