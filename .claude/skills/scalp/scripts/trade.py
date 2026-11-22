"""MT5 scalping helper that adapts to whichever account the terminal is logged in to.

It finds the right symbol name for the account (BTCUSDm on a standard demo, BTCUSDc on a cent account, ...),
sizes every trade from a risk percentage in the account's own currency, puts the stop loss and take profit on
the broker's server, and enforces the session limits written by `start`.

  trade.py status                                      account, open positions, session limits
  trade.py look [SYMBOL]                               chart reading: trend, ranges, M5 and M1 bars
  trade.py start [--max-loss-pct 6] [--target-pct 0] [--max-trades 5]
  trade.py plan SYMBOL buy|sell RISK_PCT SL_DIST TP_DIST          sizing only, sends nothing
  trade.py open SYMBOL buy|sell RISK_PCT SL_DIST TP_DIST [--wait 300] [--confirm-real LOGIN]
  trade.py trig SYMBOL buy|sell RISK_PCT SL_DIST TP_DIST LEVEL [--timeout 300] [--wait 200] [--confirm-real LOGIN]
  trade.py wait [SECONDS]                              wait for the open trade to hit its stop or target
  trade.py close                                       close the open trade at market
  trade.py session                                     results of this session

SYMBOL is the plain name (BTCUSD, XAUUSD, EURUSD); a broker suffix is found automatically.
SL_DIST / TP_DIST / LEVEL are in price units (for BTCUSD: dollars of BTC price).
Orders on a real-money account are refused unless --confirm-real carries that account's login.
"""
import argparse
import json
import math
import re
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

import MetaTrader5 as mt5
import pandas as pd

MAGIC = 52204
STATE = Path(tempfile.gettempdir()) / 'mt5_scalp_session.json'
MAX_SPREAD_SHARE = 0.25  # refuse a trade whose spread is more than this share of the stop distance
TYPES = {mt5.ACCOUNT_TRADE_MODE_DEMO: 'DEMO', mt5.ACCOUNT_TRADE_MODE_CONTEST: 'CONTEST', mt5.ACCOUNT_TRADE_MODE_REAL: 'REAL'}


def stop(message: str):
    mt5.shutdown()
    raise SystemExit(message)


def account():
    a = mt5.account_info()
    if a is None:
        stop(f'no account: {mt5.last_error()} (is MetaTrader 5 open and logged in?)')
    return a


def kind(a) -> str:
    return TYPES.get(a.trade_mode, str(a.trade_mode))


def resolve(base: str):
    """Symbol info for `base` on this account, whatever suffix the broker adds."""
    want = re.sub(r'[a-z.]+$', '', base).upper()
    names = [base] + sorted((s.name for s in mt5.symbols_get() or []
                             if re.sub(r'[a-z.]+$', '', s.name).upper() == want), key=len)
    for name in names:
        info = mt5.symbol_info(name)
        if info is not None and info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
            mt5.symbol_select(name, True)
            for _ in range(20):  # a newly selected symbol needs a moment before quotes arrive
                tick = mt5.symbol_info_tick(name)
                if tick is not None and tick.bid > 0:
                    return mt5.symbol_info(name)
                time.sleep(0.25)
            stop(f'{name}: no quotes (market closed or the feed is stalled)')
    stop(f'no tradable symbol like {want} on this account')


def loss_per_lot(info, price: float, dist: float) -> float:
    """Money lost by 1.00 lot when price moves `dist` against it, in the account currency."""
    value = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, info.name, 1.0, price, price - dist)
    if value is None or value == 0:
        value = dist / info.trade_tick_size * info.trade_tick_value
    return abs(value)


def lots_for(info, equity: float, risk_pct: float, price: float, sl_dist: float) -> tuple[float, float]:
    per_lot = loss_per_lot(info, price, sl_dist)
    step = info.volume_step
    lots = math.floor(equity * risk_pct / 100 / per_lot / step + 1e-9) * step
    lots = round(min(lots, info.volume_max), 8)
    return lots, per_lot


def load_state() -> dict | None:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=1))


def session_for(a) -> dict:
    state = load_state()
    if state is None or state['login'] != a.login or state['server'] != a.server:
        stop(f'REFUSED: no session for account {a.login}. Run `start` first; it sets the loss limit for this account.')
    return state


def my_positions():
    return [p for p in (mt5.positions_get() or []) if p.magic == MAGIC]


def deals_of(ticket: int):
    now = datetime.now()
    return [d for d in (mt5.history_deals_get(now - timedelta(days=3), now + timedelta(days=3)) or [])
            if d.position_id == ticket]


def report_closed(ticket: int) -> None:
    deals = []
    for _ in range(10):  # the closing deal reaches history a moment after the position disappears
        deals = deals_of(ticket)
        if any(d.entry == mt5.DEAL_ENTRY_OUT for d in deals):
            break
        time.sleep(0.5)
    outs = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
    pnl = sum(d.profit + d.commission + d.swap + d.fee for d in deals)
    reasons = {mt5.DEAL_REASON_SL: 'STOP LOSS', mt5.DEAL_REASON_TP: 'TAKE PROFIT', mt5.DEAL_REASON_MOBILE: 'the mobile app',
               mt5.DEAL_REASON_CLIENT: 'the desktop terminal', mt5.DEAL_REASON_EXPERT: 'this script'}
    why = reasons.get(outs[-1].reason, 'something else') if outs else 'unknown'
    a = account()
    state = load_state()
    r_text = ''
    if state and state.get('open') and state['open']['ticket'] == ticket:
        risk = state['open']['risk']
        r_text = f' = {pnl / risk:+.2f}R'
        state['results'].append({**state['open'], 'exit': outs[-1].price if outs else None, 'pnl': round(pnl, 2),
                                 'r': round(pnl / risk, 2), 'closed_by': why})
        state['open'] = None
        save_state(state)
    print(f'CLOSED by {why} at {outs[-1].price if outs else "?"} | result {pnl:+.2f} {a.currency}{r_text}')


def wait(seconds: int) -> None:
    mine = my_positions()
    if not mine:
        state = load_state()
        if state and state.get('open'):
            report_closed(state['open']['ticket'])
        else:
            print('no open trade')
        return
    ticket, symbol = mine[0].ticket, mine[0].symbol
    end = time.time() + seconds
    while time.time() < end:
        if not my_positions():
            report_closed(ticket)
            return
        time.sleep(0.5)
    p = my_positions()
    if not p:
        report_closed(ticket)
        return
    p, tick = p[0], mt5.symbol_info_tick(symbol)
    print(f'STILL OPEN after {seconds}s: {"SELL" if p.type else "BUY"} {p.volume} {symbol} @ {p.price_open} '
          f'sl {p.sl} tp {p.tp} | now bid {tick.bid} ask {tick.ask} | profit {p.profit:+.2f} {account().currency}')


def frame(symbol: str, timeframe: int, count: int) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    if rates is None or len(rates) == 0:
        stop(f'{symbol}: no bars ({mt5.last_error()})')
    d = pd.DataFrame(rates)
    d['time'] = pd.to_datetime(d['time'], unit='s')
    return d


def atr(d: pd.DataFrame, n: int = 14) -> pd.Series:
    prev = d['close'].shift()
    tr = pd.concat([d['high'] - d['low'], (d['high'] - prev).abs(), (d['low'] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> float:
    change = close.diff()
    up = change.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-change.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return float((100 - 100 / (1 + up / down)).iloc[-1])


def emas(close: pd.Series) -> tuple[float, float, float]:
    return tuple(float(close.ewm(span=n, adjust=False).mean().iloc[-1]) for n in (20, 50, 200))


def trend_word(price: float, e20: float, e50: float, e200: float) -> str:
    if price < e20 < e50 < e200:
        return 'DOWN (price < ema20 < ema50 < ema200)'
    if price > e20 > e50 > e200:
        return 'UP (price > ema20 > ema50 > ema200)'
    return 'MIXED'


def look(base: str) -> None:
    info = resolve(base)
    sym, digits = info.name, info.digits
    tick = mt5.symbol_info_tick(sym)
    spread = tick.ask - tick.bid
    m1 = frame(sym, mt5.TIMEFRAME_M1, 300)
    m1_atr = float(atr(m1).iloc[-1])
    age = time.time() - m1['time'].iloc[-1].timestamp()
    print(f'{sym} | bid {tick.bid} ask {tick.ask} | spread {spread:.{digits}f} = {spread / m1_atr:.0%} of M1 ATR '
          f'| newest bar {m1["time"].iloc[-1]:%H:%M} server time')
    if abs(time.time() - tick.time) > 600 and age > 600:
        print('WARNING: quotes look stale; the market may be closed')
    print(f'{"":4}{"close":>12} {"ema20":>12} {"ema50":>12} {"ema200":>12} {"atr14":>10} {"rsi14":>6}  trend')
    for name, tf in (('D1', mt5.TIMEFRAME_D1), ('H4', mt5.TIMEFRAME_H4), ('H1', mt5.TIMEFRAME_H1),
                     ('M15', mt5.TIMEFRAME_M15), ('M5', mt5.TIMEFRAME_M5), ('M1', mt5.TIMEFRAME_M1)):
        d = m1 if name == 'M1' else frame(sym, tf, 300)
        c = d['close']
        e = emas(c)
        print(f'{name:4}{c.iloc[-1]:12.{digits}f} {e[0]:12.{digits}f} {e[1]:12.{digits}f} {e[2]:12.{digits}f} '
              f'{atr(d).iloc[-1]:10.{digits}f} {rsi(c):6.0f}  {trend_word(c.iloc[-1], *e)}')
    for n in (15, 60, 240):
        print(f'last {n:3d} min: high {m1["high"].tail(n).max():.{digits}f}  low {m1["low"].tail(n).min():.{digits}f}')
    cols = ['time', 'open', 'high', 'low', 'close', 'tick_volume']
    for title, d in (('M5 (last 12 closed + the forming bar)', frame(sym, mt5.TIMEFRAME_M5, 13)),
                     ('M1 (last 20, final row still forming)', m1.tail(20))):
        d = d[cols].copy()
        d['time'] = d['time'].dt.strftime('%H:%M')
        print(title)
        print(d.round(digits).to_string(index=False))
    print(f'for sizing: 1.00 lot loses {loss_per_lot(info, tick.bid, m1_atr):.2f} {account().currency} per M1 ATR '
          f'({m1_atr:.{digits}f}) | lot min {info.volume_min} step {info.volume_step}')


def status() -> None:
    a = account()
    print(f'login {a.login} | {a.server} | {kind(a)} | balance {a.balance:.2f} equity {a.equity:.2f} {a.currency} '
          f'| leverage {a.leverage} | trading {"allowed" if a.trade_allowed else "DISABLED"} '
          f'| {"hedging" if a.margin_mode == mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING else "netting"}')
    if a.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO:
        print(f'THIS IS A REAL-MONEY ACCOUNT. Orders need --confirm-real {a.login}, after the user has said so.')
    for p in mt5.positions_get() or []:
        print(f'POSITION {p.symbol} {"SELL" if p.type else "BUY"} {p.volume} @ {p.price_open} sl {p.sl} tp {p.tp} '
              f'profit {p.profit:+.2f} {"(this skill)" if p.magic == MAGIC else f"(magic {p.magic}, not this skill)"}')
    state = load_state()
    if state and state['login'] == a.login and state['server'] == a.server:
        print(f'session: start {state["start_equity"]:.2f} | floor {state["floor"]:.2f} | '
              f'target {state["target"] or "none"} | trades {state["trades"]}/{state["max_trades"]}')
    else:
        print('session: none for this account (run `start`)')


def start(max_loss_pct: float, target_pct: float, max_trades: int) -> None:
    a = account()
    if my_positions():
        stop('REFUSED: a trade from this skill is still open; `wait` or `close` it first')
    state = {
        'login': a.login, 'server': a.server, 'type': kind(a), 'currency': a.currency,
        'started': datetime.now().isoformat(timespec='seconds'), 'start_equity': a.equity,
        'floor': round(a.equity * (1 - max_loss_pct / 100), 2),
        'target': round(a.equity * (1 + target_pct / 100), 2) if target_pct > 0 else None,
        'max_trades': max_trades, 'trades': 0, 'open': None, 'results': [],
    }
    save_state(state)
    print(f'session started on {a.login} ({kind(a)}): equity {a.equity:.2f} {a.currency}, no trade may take it below '
          f'{state["floor"]:.2f}, target {state["target"] or "none"}, at most {max_trades} trades')


def plan(base: str, side: str, risk_pct: float, sl_dist: float, tp_dist: float, send: bool, confirm_real: int | None,
         wait_s: int) -> None:
    a = account()
    info = resolve(base)
    tick = mt5.symbol_info_tick(info.name)
    buy = side == 'buy'
    price = tick.ask if buy else tick.bid
    spread = tick.ask - tick.bid
    lots, per_lot = lots_for(info, a.equity, risk_pct, price, sl_dist)
    risk, reward = lots * per_lot, lots * per_lot * tp_dist / sl_dist
    sign = 1 if buy else -1
    sl, tp = round(price - sign * sl_dist, info.digits), round(price + sign * tp_dist, info.digits)
    print(f'{info.name} {side.upper()} {lots} lots @ {price} | sl {sl} tp {tp} | risk {risk:.2f} {a.currency} '
          f'({risk / a.equity:.1%} of equity), target {reward:.2f} ({tp_dist / sl_dist:.2f}R) | '
          f'spread {spread / sl_dist:.0%} of the stop')
    if lots < info.volume_min:
        need = info.volume_min * per_lot / a.equity * 100
        stop(f'REFUSED: {risk_pct}% risk is below the smallest lot ({info.volume_min}); the minimum here is {need:.2f}% '
             f'with this stop. Use a tighter stop or a larger risk.')
    if spread > MAX_SPREAD_SHARE * sl_dist:
        stop(f'REFUSED: the spread is {spread / sl_dist:.0%} of the stop; the cost is too high for this trade')
    min_dist = info.trade_stops_level * info.point
    if min(sl_dist, tp_dist) <= min_dist + spread:
        stop(f'REFUSED: stop/target must be more than {min_dist + spread:.{info.digits}f} from price on this symbol')
    if not send:
        return

    if not a.trade_allowed:
        stop('REFUSED: the broker has trading disabled on this account')
    if a.trade_mode != mt5.ACCOUNT_TRADE_MODE_DEMO and confirm_real != a.login:
        stop(f'REFUSED: account {a.login} on {a.server} is REAL money. Tell the user, and only after they confirm '
             f'they want real-money trades on it, rerun with --confirm-real {a.login}')
    state = session_for(a)
    if state['trades'] >= state['max_trades']:
        stop(f'REFUSED: the session limit of {state["max_trades"]} trades is used up')
    if state['target'] and a.equity >= state['target']:
        stop('REFUSED: the session target is reached; trading is finished')
    if a.equity - risk < state['floor']:
        stop(f'REFUSED: this risk ({risk:.2f}) could take equity {a.equity:.2f} below the session floor {state["floor"]:.2f}')
    if my_positions():
        stop('REFUSED: a trade from this skill is already open')
    if a.margin_mode != mt5.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING and mt5.positions_get(symbol=info.name):
        stop(f'REFUSED: netting account with an open {info.name} position; a new order would merge with it')

    request = {
        'action': mt5.TRADE_ACTION_DEAL, 'symbol': info.name, 'volume': lots,
        'type': mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL, 'price': price, 'sl': sl, 'tp': tp,
        'deviation': max(50, int(3 * spread / info.point)), 'magic': MAGIC, 'comment': 'claude scalp',
        'type_time': mt5.ORDER_TIME_GTC,
    }
    # filling_mode is a bit mask (1 FOK, 2 IOC); RETURN is what remains for brokers that list neither.
    fills = [f for bit, f in ((2, mt5.ORDER_FILLING_IOC), (1, mt5.ORDER_FILLING_FOK)) if info.filling_mode & bit]
    result = None
    for fill in fills + [mt5.ORDER_FILLING_RETURN]:
        request['type_filling'] = fill
        check = mt5.order_check(request)
        if check is None or check.retcode not in (0, mt5.TRADE_RETCODE_DONE):
            continue
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            break
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        stop(f'ORDER FAILED: {result.retcode if result else mt5.last_error()} {result.comment if result else ""}')
    time.sleep(0.3)
    mine = my_positions()
    state['trades'] += 1
    state['open'] = {'ticket': mine[0].ticket if mine else result.order, 'symbol': info.name, 'side': side, 'lots': lots,
                     'entry': result.price, 'sl': sl, 'tp': tp, 'risk': round(risk, 2)}
    save_state(state)
    print(f'FILLED {side.upper()} {lots} {info.name} @ {result.price} (trade {state["trades"]}/{state["max_trades"]})')
    wait(wait_s)


def trigger(base: str, level: float, timeout: int) -> bool:
    info = resolve(base)
    from_below = mt5.symbol_info_tick(info.name).bid < level
    end = time.time() + timeout
    while time.time() < end:
        bid = mt5.symbol_info_tick(info.name).bid
        if (from_below and bid >= level) or (not from_below and bid <= level):
            return True
        time.sleep(0.25)
    print(f'NOT TRIGGERED in {timeout}s: bid {mt5.symbol_info_tick(info.name).bid} never touched {level}')
    return False


def close() -> None:
    for p in my_positions():
        info, tick = mt5.symbol_info(p.symbol), mt5.symbol_info_tick(p.symbol)
        request = {
            'action': mt5.TRADE_ACTION_DEAL, 'symbol': p.symbol, 'volume': p.volume, 'position': p.ticket,
            'type': mt5.ORDER_TYPE_BUY if p.type else mt5.ORDER_TYPE_SELL, 'price': tick.ask if p.type else tick.bid,
            'deviation': max(50, int(3 * (tick.ask - tick.bid) / info.point)), 'magic': MAGIC,
            'type_time': mt5.ORDER_TIME_GTC,
        }
        fills = [f for bit, f in ((2, mt5.ORDER_FILLING_IOC), (1, mt5.ORDER_FILLING_FOK)) if info.filling_mode & bit]
        for fill in fills + [mt5.ORDER_FILLING_RETURN]:
            request['type_filling'] = fill
            result = mt5.order_send(request)
            if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
                break
        report_closed(p.ticket)
    if not my_positions():
        print('no open trade from this skill')


def session() -> None:
    a = account()
    state = session_for(a)
    print(f'session on {a.login} ({state["type"]}) started {state["started"]}')
    for i, t in enumerate(state['results'], 1):
        print(f'{i}. {t["side"].upper()} {t["lots"]} {t["symbol"]} @ {t["entry"]} sl {t["sl"]} tp {t["tp"]} -> '
              f'{t["exit"]} by {t["closed_by"]}: {t["pnl"]:+.2f} {state["currency"]} ({t["r"]:+.2f}R)')
    if state.get('open'):
        print(f'open: {state["open"]}')
    total = a.equity - state['start_equity']
    print(f'equity {state["start_equity"]:.2f} -> {a.equity:.2f} {state["currency"]} ({total:+.2f}, '
          f'{total / state["start_equity"]:+.1%}) | trades {state["trades"]}/{state["max_trades"]} | floor {state["floor"]:.2f}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('status')
    sub.add_parser('session')
    sub.add_parser('close')
    p = sub.add_parser('look')
    p.add_argument('symbol', nargs='?', default='BTCUSD')
    p = sub.add_parser('start')
    p.add_argument('--max-loss-pct', type=float, default=6.0)
    p.add_argument('--target-pct', type=float, default=0.0)
    p.add_argument('--max-trades', type=int, default=5)
    p = sub.add_parser('wait')
    p.add_argument('seconds', nargs='?', type=int, default=300)
    for name in ('plan', 'open', 'trig'):
        p = sub.add_parser(name)
        p.add_argument('symbol')
        p.add_argument('side', choices=['buy', 'sell'])
        p.add_argument('risk_pct', type=float)
        p.add_argument('sl_dist', type=float)
        p.add_argument('tp_dist', type=float)
        if name == 'trig':
            p.add_argument('level', type=float)
            p.add_argument('--timeout', type=int, default=300)
        if name != 'plan':
            p.add_argument('--wait', type=int, default=200)
            p.add_argument('--confirm-real', type=int, default=None)
    args = parser.parse_args()

    if not mt5.initialize():
        raise SystemExit(f'MT5 not reachable: {mt5.last_error()} (open MetaTrader 5, log in, and untick '
                         '"Disable algorithmic trading via external Python API" in Options > Expert Advisors)')
    if args.cmd == 'status':
        status()
    elif args.cmd == 'look':
        look(args.symbol)
    elif args.cmd == 'start':
        start(args.max_loss_pct, args.target_pct, args.max_trades)
    elif args.cmd == 'plan':
        plan(args.symbol, args.side, args.risk_pct, args.sl_dist, args.tp_dist, False, None, 0)
    elif args.cmd == 'open':
        plan(args.symbol, args.side, args.risk_pct, args.sl_dist, args.tp_dist, True, args.confirm_real, args.wait)
    elif args.cmd == 'trig':
        if trigger(args.symbol, args.level, args.timeout):
            plan(args.symbol, args.side, args.risk_pct, args.sl_dist, args.tp_dist, True, args.confirm_real, args.wait)
    elif args.cmd == 'wait':
        wait(args.seconds)
    elif args.cmd == 'close':
        close()
    elif args.cmd == 'session':
        session()
    if args.cmd in ('open', 'trig', 'wait', 'close'):
        a = account()
        print(f'balance {a.balance:.2f} equity {a.equity:.2f} {a.currency}')
    mt5.shutdown()


if __name__ == '__main__':
    main()
