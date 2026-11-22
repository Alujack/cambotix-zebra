"""Live BTC trader for MetaTrader 5. THIS SCRIPT SENDS REAL ORDERS.

Rule (signals from closed 1-minute bars):
  long  when the bar closes above the highest high of the previous N bars and above EMA 200
  short when the bar closes below the lowest low of the previous N bars and below EMA 200
  stop   = K x ATR(14), at least MIN_STOP dollars;  target = M x stop
  one position at a time, closed after MAX_HOLD_MIN minutes if neither level is hit

Account rules:
  equity >= --target  -> close everything and stop for good
  equity <= --floor   -> close everything and stop for good
  each trade risks --risk (account currency), never more than what is left above the floor

Stop/target are attached to the order at the broker, so an open trade stays protected if
this script dies. The time exit and the account rules only work while the script runs.

Run:   py -3.13 -u scripts/btc_scalper.py            (live)
       py -3.13 -u scripts/btc_scalper.py --dry-run  (no orders, logs what it would do)
Stop:  create the file .local/btc_scalper.stop  (closes the open trade and exits)
"""
from __future__ import annotations

import argparse
import datetime as dt
import msvcrt
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
LOCAL = ROOT / ".local"
LOG = LOCAL / "btc_scalper.log"
STOP_FILE = LOCAL / "btc_scalper.stop"
DONE_FILE = LOCAL / "btc_scalper.done"
LOCK_FILE = LOCAL / "btc_scalper.lock"

MAGIC = 22112601
N, K, M = 60, 8.0, 2.0
MIN_STOP = 40.0
MAX_HOLD_MIN = 240
BARS = 1500


def log(msg: str) -> None:
    line = f"{dt.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def signal(df: pd.DataFrame) -> tuple[int, float]:
    """Side (+1 long, -1 short, 0 none) and stop distance for the LAST row of closed bars."""
    h, l, c = df["high"].to_numpy(float), df["low"].to_numpy(float), df["close"].to_numpy(float)
    if len(c) < N + 201:
        return 0, 0.0
    prev = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev), np.abs(l - prev)))
    atr = pd.Series(tr).ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    ema = pd.Series(c).ewm(span=200, adjust=False).mean().iloc[-1]
    hh, ll = h[-N - 1:-1].max(), l[-N - 1:-1].min()
    side = 0
    if c[-1] > hh and c[-1] > ema:
        side = 1
    elif c[-1] < ll and c[-1] < ema:
        side = -1
    return side, max(K * atr, MIN_STOP)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="BTCUSDc")
    ap.add_argument("--login", type=int, default=160216737)
    ap.add_argument("--server", default="Exness-MT5Real20")
    ap.add_argument("--target", type=float, default=2000.0, help="stop for good at this equity")
    ap.add_argument("--floor", type=float, default=500.0, help="stop for good at this equity")
    ap.add_argument("--risk", type=float, default=100.0, help="loss per trade at the stop, account currency")
    ap.add_argument("--max-spread", type=float, default=10.0, help="skip entries above this spread (price units)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reset", action="store_true", help="clear a previous target/floor stop")
    a = ap.parse_args()

    LOCAL.mkdir(exist_ok=True)
    lock = LOCK_FILE.open("w")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("another btc_scalper is already running")
        return 1
    if a.reset:
        DONE_FILE.unlink(missing_ok=True)
    if DONE_FILE.exists() and not a.dry_run:
        print("already finished:", DONE_FILE.read_text().strip(), "(use --reset to start again)")
        return 1
    STOP_FILE.unlink(missing_ok=True)

    import MetaTrader5 as mt5

    def connect() -> bool:
        if not mt5.initialize():
            return False
        acc = mt5.account_info()
        if acc is None:
            return False
        if acc.login != a.login or acc.server != a.server:
            log(f"WRONG ACCOUNT {acc.login} {acc.server}; expected {a.login} {a.server}. Not trading.")
            raise SystemExit(2)
        return mt5.symbol_select(a.symbol, True)

    if not connect():
        log(f"cannot connect to MT5: {mt5.last_error()}")
        return 1

    def mine():
        return [p for p in (mt5.positions_get(symbol=a.symbol) or []) if p.magic == MAGIC]

    def send(req: dict):
        if a.dry_run:
            r = mt5.order_check(req)
            log(f"DRY RUN order_check retcode={r.retcode} {r.comment} req={ {k: req[k] for k in ('type', 'volume', 'price', 'sl', 'tp') if k in req} }")
            return None
        r = mt5.order_send(req)
        if r is None or r.retcode != mt5.TRADE_RETCODE_DONE:
            log(f"ORDER FAILED {None if r is None else (r.retcode, r.comment)} last_error={mt5.last_error()}")
            return None
        return r

    def close(p, why: str) -> bool:
        k = mt5.symbol_info_tick(a.symbol)
        buy = p.type == mt5.POSITION_TYPE_BUY
        r = send(dict(action=mt5.TRADE_ACTION_DEAL, symbol=a.symbol, volume=p.volume, position=p.ticket,
                      type=mt5.ORDER_TYPE_SELL if buy else mt5.ORDER_TYPE_BUY, price=k.bid if buy else k.ask,
                      deviation=1000, magic=MAGIC, comment="zebra close", type_time=mt5.ORDER_TIME_GTC,
                      type_filling=mt5.ORDER_FILLING_IOC))
        if r:
            log(f"CLOSED {p.ticket} at {r.price:.2f} ({why}); floating result was {p.profit:+.2f}")
        return bool(r)

    def finish(why: str) -> int:
        for _ in range(5):
            ps = mine()
            if not ps or a.dry_run:
                break
            for p in ps:
                close(p, why)
            time.sleep(1)
        acc = mt5.account_info()
        log(f"STOPPED: {why}. balance {acc.balance:.2f} equity {acc.equity:.2f} {acc.currency}")
        return 0

    acc = mt5.account_info()
    info = mt5.symbol_info(a.symbol)
    log(f"started{' (DRY RUN)' if a.dry_run else ''}: {a.symbol} on {acc.login} {acc.server}, equity {acc.equity:.2f} {acc.currency}, "
        f"target {a.target:.0f}, floor {a.floor:.0f}, risk {a.risk:.0f} per trade, rule N={N} K={K} M={M}")

    r0 = mt5.copy_rates_from_pos(a.symbol, mt5.TIMEFRAME_M1, 0, 3)
    last_bar = int(r0[-2]["time"]) if r0 is not None and len(r0) >= 2 else 0  # only act on bars that close from now on
    fails = 0
    known: dict[int, float] = {p.ticket: p.price_open for p in mine()}
    next_beat = 0.0

    while True:
        try:
            time.sleep(1)
            acc = mt5.account_info()
            tick = mt5.symbol_info_tick(a.symbol)
            if acc is None or tick is None:
                log(f"MT5 not answering ({mt5.last_error()}); reconnecting")
                mt5.shutdown()
                time.sleep(5)
                connect()
                continue

            ps = mine()
            for t in list(known):
                if t not in {p.ticket for p in ps}:
                    deals = mt5.history_deals_get(position=t) or []
                    pnl = sum(d.profit + d.commission + d.swap for d in deals)
                    log(f"TRADE {t} is closed: result {pnl:+.2f} {acc.currency}; balance {acc.balance:.2f}")
                    del known[t]

            if STOP_FILE.exists():
                STOP_FILE.unlink(missing_ok=True)
                return finish("stop file")
            if acc.equity >= a.target:
                if not a.dry_run:
                    DONE_FILE.write_text(f"{dt.datetime.now():%Y-%m-%d %H:%M} target reached, equity {acc.equity:.2f}")
                return finish(f"TARGET reached (equity {acc.equity:.2f} >= {a.target:.0f})")
            if acc.equity <= a.floor:
                if not a.dry_run:
                    DONE_FILE.write_text(f"{dt.datetime.now():%Y-%m-%d %H:%M} loss limit reached, equity {acc.equity:.2f}")
                return finish(f"LOSS LIMIT reached (equity {acc.equity:.2f} <= {a.floor:.0f})")

            if time.time() >= next_beat:
                next_beat = time.time() + 900
                pos = "; ".join(f"{'BUY' if p.type == 0 else 'SELL'} {p.volume} @ {p.price_open:.2f} now {p.profit:+.2f}" for p in ps) or "flat"
                log(f"alive: equity {acc.equity:.2f}, {a.symbol} {tick.bid:.2f}, spread {tick.ask - tick.bid:.2f}, {pos}")

            if ps:
                for p in ps:
                    if tick.time - p.time >= MAX_HOLD_MIN * 60:
                        close(p, f"held {MAX_HOLD_MIN} min")
                continue

            r = mt5.copy_rates_from_pos(a.symbol, mt5.TIMEFRAME_M1, 0, 3)
            if r is None or len(r) < 2 or int(r[-2]["time"]) <= last_bar:
                continue
            last_bar = int(r[-2]["time"])
            if abs(time.time() - tick.time) > 30 or tick.time - (last_bar + 60) > 20:
                continue  # stale feed or a late bar: do not act on old signals
            rates = mt5.copy_rates_from_pos(a.symbol, mt5.TIMEFRAME_M1, 0, BARS)
            if rates is None or len(rates) < N + 202:
                continue
            df = pd.DataFrame(rates)
            df = df[df["time"] <= last_bar]
            side, stop = signal(df)
            if not side:
                continue
            spread = tick.ask - tick.bid
            if spread > a.max_spread:
                log(f"signal {'BUY' if side > 0 else 'SELL'} skipped: spread {spread:.2f} > {a.max_spread:.2f}")
                continue
            risk = min(a.risk, acc.balance - a.floor)
            buy = side > 0
            price = tick.ask if buy else tick.bid
            sl = price - stop if buy else price + stop
            tp = price + M * stop if buy else price - M * stop
            otype = mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL
            loss1 = mt5.order_calc_profit(otype, a.symbol, 1.0, price, sl)
            if not loss1:
                log(f"cannot size the trade: {mt5.last_error()}")
                continue
            step = info.volume_step
            lots = round(int(risk / abs(loss1) / step) * step, 2)
            if lots < info.volume_min:
                return finish(f"not enough left above the floor to open the smallest trade (risk {risk:.2f})")
            res = send(dict(action=mt5.TRADE_ACTION_DEAL, symbol=a.symbol, volume=lots, type=otype, price=price,
                            sl=round(sl, info.digits), tp=round(tp, info.digits), deviation=500, magic=MAGIC,
                            comment="zebra m1 break", type_time=mt5.ORDER_TIME_GTC, type_filling=mt5.ORDER_FILLING_IOC))
            if res:
                fails = 0
                known[res.order] = res.price
                log(f"OPENED {'BUY' if buy else 'SELL'} {lots} lot at {res.price:.2f}, stop {sl:.2f}, target {tp:.2f} "
                    f"(risk {lots * abs(loss1):.1f}, stop distance {stop:.0f}, spread {spread:.2f}) ticket {res.order}")
            elif not a.dry_run:
                fails += 1
                if fails >= 5:
                    return finish("5 orders in a row were rejected")
        except SystemExit:
            raise
        except KeyboardInterrupt:
            log("interrupted; any open trade keeps its stop and target at the broker")
            return 0
        except Exception as e:  # keep running; the open trade is protected at the broker
            log(f"ERROR {type(e).__name__}: {e}")
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
