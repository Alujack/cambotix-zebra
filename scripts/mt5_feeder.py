"""Local signal source: MetaTrader 5 -> analyzer /signals.

Replaces the TradingView webhook for accounts without a webhook-capable plan.
Mirrors tradingview/gold_setups.pine bar for bar: same indicators, same gates,
same edge-triggered emission, same JSON contract. The analyzer re-validates
everything server-side, exactly as it does for a TradingView payload.

Every minute it also sends the broker's closed M1 candles (bid prices plus the
bar spread) to /candles, which the analyzer uses to grade every published plan.
The analyzer answers with the earliest time it still needs, so a feeder that was
offline backfills the gap on its next run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
BARS = 600                 # >= 200 for EMA200 plus warmup
TF_SECONDS = 900
DIRECTIONS = ('BUY_SETUP', 'SELL_SETUP')
CANDLE_CHUNK = 2 * 86400   # M1 rows per request stay well under the analyzer's 1 MB limit
FIRST_CANDLES = 3 * 3600   # history sent on the very first push


# -- config -------------------------------------------------------------------
def env() -> dict[str, str]:
    values = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            values[key.strip()] = value.strip()
    return values


# -- indicators: Wilder smoothing, matching Pine's ta.* -----------------------
def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def rma(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(alpha=1 / length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = rma(delta.clip(lower=0), length)
    loss = rma((-delta).clip(lower=0), length)
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def true_range(df: pd.DataFrame) -> pd.Series:
    close = df['close'].shift(1)
    return pd.concat([df['high'] - df['low'],
                      (df['high'] - close).abs(),
                      (df['low'] - close).abs()], axis=1).max(axis=1)


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """ta.dmi(14, 14): Wilder directional movement, then RMA of DX."""
    up, down = df['high'].diff(), -df['low'].diff()
    plus = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
    minus = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
    smoothed = rma(true_range(df), length).replace(0, np.nan)
    plus_di = 100 * rma(plus, length) / smoothed
    minus_di = 100 * rma(minus, length) / smoothed
    total = (plus_di + minus_di).replace(0, np.nan)
    return rma(100 * (plus_di - minus_di).abs() / total, length)


def indicators(df: pd.DataFrame, swing_bars: int) -> pd.DataFrame:
    out = df.copy()
    out['ema20'] = ema(out['close'], 20)
    out['ema50'] = ema(out['close'], 50)
    out['ema200'] = ema(out['close'], 200)
    out['rsi'] = rsi(out['close'])
    macd = ema(out['close'], 12) - ema(out['close'], 26)
    out['macd_hist'] = macd - ema(macd, 9)
    out['adx'] = adx(out)
    out['atr'] = rma(true_range(out), 14)
    out['swing_high'] = out['high'].shift(1).rolling(swing_bars).max()
    out['swing_low'] = out['low'].shift(1).rolling(swing_bars).min()
    return out


# -- gates: mirror of classic_rules / gold_setups.pine ------------------------
def in_session(close_epoch: int) -> bool:
    """The test the analyzer applies in domain.sessions(), on the same timestamp."""
    stamp = dt.datetime.fromtimestamp(close_epoch, dt.timezone.utc)
    for zone in ('Europe/London', 'America/New_York'):
        local = stamp.astimezone(ZoneInfo(zone))
        if local.weekday() < 5 and 8 <= local.hour < 17:
            return True
    return False


def qualifies(row: pd.Series, cfg: dict, direction: str) -> bool:
    readings = [row['ema200'], row['adx'], row['atr'], row['rsi'],
                row['macd_hist'], row['swing_high'], row['swing_low']]
    if not np.isfinite(readings).all():
        return False
    atr_percent = row['atr'] / row['close'] * 100
    if not cfg['min_atr'] <= atr_percent <= cfg['max_atr'] or row['adx'] < cfg['min_adx']:
        return False
    if direction == 'BUY_SETUP':
        return (row['ema20'] > row['ema50'] and row['close'] > row['ema200']
                and 50 <= row['rsi'] <= 70 and row['macd_hist'] > 0)
    return (row['ema20'] < row['ema50'] and row['close'] < row['ema200']
            and 30 <= row['rsi'] <= 50 and row['macd_hist'] < 0)


# -- market data --------------------------------------------------------------
def bars(symbol: str, attempts: int = 8) -> pd.DataFrame:
    """MT5 serves stale history for a few seconds after a cold terminal launch."""
    if not mt5.initialize():
        raise SystemExit(f'MT5 initialize failed: {mt5.last_error()}')
    mt5.symbol_select(symbol, True)
    for attempt in range(attempts):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, BARS)
        if rates is not None and len(rates) >= 250:
            df = pd.DataFrame(rates)
            age = time.time() - (int(df['time'].iloc[-1]) + TF_SECONDS)
            if age < 2 * TF_SECONDS:
                return df
            print(f'  warmup {attempt + 1}/{attempts}: history {age / 3600:.1f}h stale, resyncing')
        time.sleep(3)
    raise SystemExit('MT5 returned stale or empty history; open the terminal and check it is connected')


# -- emission -----------------------------------------------------------------
def payload(row: pd.Series, close_epoch: int, symbol: str, direction: str) -> dict:
    def number(value) -> float:
        return round(float(value), 8)

    return {
        'event_id': f'{symbol}-15m-{close_epoch}-{direction}',
        'symbol': symbol, 'timeframe': '15m', 'bar_time': close_epoch,
        'signal': direction, 'model': 'classic',
        'price': number(row['close']), 'ema20': number(row['ema20']),
        'ema50': number(row['ema50']), 'ema200': number(row['ema200']),
        'rsi': number(row['rsi']), 'macd_hist': number(row['macd_hist']),
        'adx': number(row['adx']), 'atr': number(row['atr']),
        'swing_high': number(row['swing_high']), 'swing_low': number(row['swing_low']),
    }


def post(body: dict, url: str, token: str, limit: int = 200) -> tuple[int, str]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json', 'X-Zebra-Token': token})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read().decode()[:limit]
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:limit]
    except urllib.error.URLError as exc:
        return 0, str(exc.reason)


def push_candles(cfg: dict, state: dict) -> None:
    """Send closed M1 candles from the analyzer's need_from up to the last closed minute."""
    if not mt5.initialize():
        print(f'  candles: MT5 initialize failed: {mt5.last_error()}')
        return
    info = mt5.symbol_info(cfg['mt5_symbol'])
    if info is None:
        print(f'  candles: unknown MT5 symbol {cfg["mt5_symbol"]}')
        return
    end = int(time.time()) // 60 * 60
    start = state.get('need_from') or end - FIRST_CANDLES
    for _ in range(20):
        start = min(start, end - 60)
        stop = min(end, start + CANDLE_CHUNK)
        rates = mt5.copy_rates_range(cfg['mt5_symbol'], mt5.TIMEFRAME_M1,
                                     dt.datetime.fromtimestamp(start, dt.timezone.utc),
                                     dt.datetime.fromtimestamp(stop, dt.timezone.utc))
        rows = [] if rates is None else [
            [int(r['time']), float(r['open']), float(r['high']), float(r['low']), float(r['close']),
             round(float(r['spread']) * info.point, 8)]
            for r in rates if start <= int(r['time']) and int(r['time']) + 60 <= stop]
        status, text = post({'symbol': cfg['symbol'], 'start': start, 'end': stop, 'candles': rows},
                            cfg['candles_url'], cfg['token'], limit=2000)
        if status != 200:
            print(f'  candles: HTTP {status} {text}')
            return
        reply = json.loads(text)
        state['need_from'] = reply['need_from']
        if reply['need_from'] >= end:
            return
        start = reply['need_from']
    print('  candles: backfill continues next minute')


def scan(cfg: dict, dry_run: bool) -> None:
    df = indicators(bars(cfg['mt5_symbol']), cfg['swing_bars'])
    closed, previous = df.iloc[-2], df.iloc[-3]      # -1 is the still-forming bar
    close_epoch = int(closed['time']) + TF_SECONDS
    stamp = dt.datetime.fromtimestamp(close_epoch, dt.timezone.utc)
    age = time.time() - close_epoch

    print(f'bar closed {stamp:%Y-%m-%d %H:%M} UTC ({age:.0f}s ago)  close={closed["close"]:.3f}  '
          f'adx={closed["adx"]:.1f}  rsi={closed["rsi"]:.1f}  '
          f'atr%={closed["atr"] / closed["close"] * 100:.3f}')

    valid = [d for d in DIRECTIONS if qualifies(closed, cfg, d)]
    if not valid:
        print('  no qualifying setup on this bar')
        return
    if not in_session(close_epoch):
        print(f'  {"/".join(valid)} valid, but outside London/New York session — not sent')
        return
    if age > cfg['max_age']:
        print(f'  bar is {age:.0f}s old; analyzer rejects beyond {cfg["max_age"]}s — not sent')
        return

    for direction in valid:
        # Pine: `setup and not setup[1]` — emit once, on the bar the setup appears.
        if qualifies(previous, cfg, direction):
            print(f'  {direction}: carried over from the previous bar — not re-sent')
            continue
        body = payload(closed, close_epoch, cfg['symbol'], direction)
        if dry_run:
            print(f'  [dry-run] would send {direction}: {json.dumps(body)}')
            continue
        status, text = post(body, cfg['url'], cfg['token'])
        print(f'  sent {direction} -> HTTP {status} {text}')


def main() -> None:
    parser = argparse.ArgumentParser(description='Feed MT5 15m setups into the analyzer.')
    parser.add_argument('--once', action='store_true', help='scan the last closed bar and exit')
    parser.add_argument('--dry-run', action='store_true', help='print the payload instead of sending')
    parser.add_argument('--no-candles', action='store_true', help='do not send M1 candles for outcome grading')
    parser.add_argument('--symbol', default=os.getenv('MT5_SYMBOL', 'XAUUSDc'),
                        help='broker symbol as named in MT5 (default XAUUSDc)')
    args = parser.parse_args()

    settings = env()
    broker_symbol = args.symbol
    cfg = {
        'mt5_symbol': broker_symbol,
        # Exness suffixes gold as XAUUSDc; the analyzer only accepts [A-Z0-9]+.
        'symbol': (broker_symbol[:-1] if broker_symbol.endswith('c') else broker_symbol).upper(),
        'url': f'http://127.0.0.1:{settings.get("ANALYZER_PORT", "8010")}/signals',
        'candles_url': f'http://127.0.0.1:{settings.get("ANALYZER_PORT", "8010")}/candles',
        'token': settings.get('ANALYZER_TOKEN', ''),
        'min_adx': float(settings.get('MIN_ADX', 20)),
        'min_atr': float(settings.get('MIN_ATR_PERCENT', 0.02)),
        'max_atr': float(settings.get('MAX_ATR_PERCENT', 0.5)),
        'max_age': int(settings.get('MAX_SIGNAL_AGE_SECONDS', 300)),
        'swing_bars': 10,
    }
    if not cfg['token']:
        raise SystemExit('ANALYZER_TOKEN missing from .env')
    print(f'{cfg["mt5_symbol"]} -> {cfg["symbol"]}  {cfg["url"]}  '
          f'(ADX>={cfg["min_adx"]}, ATR% {cfg["min_atr"]}-{cfg["max_atr"]})')

    candles = not (args.no_candles or args.dry_run)
    state: dict = {}
    try:
        if args.once:
            if candles:
                push_candles(cfg, state)
            scan(cfg, args.dry_run)
            return
        print('watching; candles every minute, setup scan 10s after each 15m close. Ctrl+C to stop.')
        scanned = None
        while True:
            time.sleep(max(1.0, 60 - time.time() % 60 + 10))
            if candles:
                push_candles(cfg, state)
            bar = int(time.time()) // TF_SECONDS
            if time.time() % TF_SECONDS < 60 and bar != scanned:
                scanned = bar
                scan(cfg, args.dry_run)
            sys.stdout.flush()
    except KeyboardInterrupt:
        print('stopped')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
