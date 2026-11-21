"""Local signal source: MetaTrader 5 -> analyzer /signals.

Replaces the TradingView webhook for accounts without a webhook-capable plan.
Runs the detection models from the broker's own candles:
  classic  mirrors tradingview/gold_setups.pine bar for bar (EMA/RSI/MACD/ADX/ATR)
  crt      Candle Range Theory via scripts/crt_engine.py: on each New York-aligned
           H4 close, posts a setup when that candle swept one side of the previous
           H4 range and closed back inside it
  ict      ICT 2022 model via scripts/ict_engine.py: every 5 minutes, posts a limit
           setup when a killzone sweep, a structure shift and an FVG complete on M5
  ema      EMA pullback scalp via scripts/ema_engine.py: every minute, posts a market
           setup when a 1m candle resumes the EMA20/50/200 trend after a dip into EMA20
  mss      sweep + market structure shift via scripts/mss_engine.py: every hour, posts a
           market setup when an H1 displacement candle shifts structure after a sweep
Same JSON contract as the analyzer's /signals; the analyzer re-validates everything.

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
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from crt_engine import CrtConfig, detect, slot_closes  # noqa: E402
import ema_engine  # noqa: E402
import ict_engine  # noqa: E402
import mss_engine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BARS = 600                 # >= 200 for EMA200 plus warmup
TF_SECONDS = 900
M5_SECONDS = 300
M1_SECONDS = 60
ICT_BARS = 1500            # ~5 trading days of M5: covers the previous day's pools and the swing lookback
EMA_BARS = 1500            # M1: the engine's 600-bar EMA warmup plus the pullback window, with room for a daily break
MSS_BARS = 1500            # M15 = 375 H1 bars: the engine's 100-bar warmup plus its 80-bar window, with room for a weekend
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
    """Pine sessions are evaluated on the 15-minute bar's open time."""
    stamp = dt.datetime.fromtimestamp(close_epoch - TF_SECONDS, dt.timezone.utc)
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
        return (row['close'] > row['ema20'] > row['ema50'] > row['ema200']
                and 50 <= row['rsi'] <= 70 and row['macd_hist'] > 0)
    return (row['close'] < row['ema20'] < row['ema50'] < row['ema200']
            and 30 <= row['rsi'] <= 50 and row['macd_hist'] < 0)


# -- market data --------------------------------------------------------------
class NoFreshBars(Exception):
    """No recent closed bar: market closed (weekend, holiday, daily break) or the feed stalled. Wait, don't exit."""


def bars(symbol: str, attempts: int = 8, count: int = BARS, timeframe: int | None = None,
         seconds: int = TF_SECONDS) -> pd.DataFrame:
    """Closed bars only, oldest first. MT5 serves stale history for a few seconds after a cold terminal launch,
    while ticks are already current. Without recent ticks the market is closed or the feed is down, so retrying now
    cannot help. The still-forming bar is dropped by time, not position: in a quiet minute MT5 has not opened the
    next bar yet, and dropping the last row would then discard the bar that just closed."""
    if not mt5.initialize():
        raise SystemExit(f'MT5 initialize failed: {mt5.last_error()}')
    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    tick_age = time.time() - tick.time if tick is not None and tick.time else float('inf')
    if tick_age > 2 * TF_SECONDS:
        raise NoFreshBars(f'no ticks for {tick_age / 3600:.1f}h: market closed or the feed is stalled')
    for attempt in range(attempts):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15 if timeframe is None else timeframe, 0, count)
        if rates is not None and len(rates) >= 250:
            df = pd.DataFrame(rates)
            age = time.time() - (int(df['time'].iloc[-1]) + seconds)
            if age < 2 * seconds:
                return df[df['time'] + seconds <= time.time()].reset_index(drop=True)
            print(f'  warmup {attempt + 1}/{attempts}: history {age / 3600:.1f}h stale, resyncing')
        time.sleep(3)
    raise NoFreshBars('ticks are current but MT5 history stays stale; check the terminal is connected')


def crt_config(settings: dict, crypto: bool) -> CrtConfig:
    """Detection follows the analyzer's .env so a setup the feeder emits is one the server accepts."""
    keys = settings.get('CRT_KEY_TIMES', '')
    return CrtConfig(htf_hours=int(settings.get('CRT_HTF_HOURS', 4)),
                     key_times=tuple(int(k) for k in keys.split(',') if k.strip().isdigit()),
                     min_rr=float(settings.get('CRT_MIN_RR', 2.0)),
                     stop_buffer_atr=float(settings.get('CRT_STOP_BUFFER_ATR', 0.1)), crypto=crypto)


def scan_crt(cfg: dict, df: pd.DataFrame, close_epoch: int, dry_run: bool) -> None:
    """Post a CRT setup only when the bar that just closed also closed an HTF candle that swept the previous range."""
    crt = cfg['crt']
    if not slot_closes(close_epoch - TF_SECONDS, crt.htf_hours):
        return
    rows = [{'t': int(r.time), 'o': float(r.open), 'h': float(r.high), 'l': float(r.low), 'c': float(r.close)}
            for r in df.itertuples()]
    setups = [body for body in detect(cfg['symbol'], rows, crt) if body['bar_time'] == close_epoch]
    if not setups:
        print(f'  crt: H{crt.htf_hours} candle closed; no sweep-and-close-back setup')
    for body in setups:
        if dry_run:
            print(f'  [dry-run] would send {body["signal"]} (crt): {json.dumps(body)}')
            continue
        status, text = post(body, cfg['url'], cfg['token'])
        print(f'  sent {body["signal"]} (crt) -> HTTP {status} {text}')


def scan_ict(cfg: dict, dry_run: bool) -> None:
    """Replay the last ICT_BARS closed M5 bars and post the setup completed by the bar that just closed, if any."""
    try:
        raw = bars(cfg['mt5_symbol'], count=ICT_BARS, timeframe=mt5.TIMEFRAME_M5, seconds=M5_SECONDS)
    except NoFreshBars as reason:
        print(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC  ict: no fresh M5 bars ({reason})')
        return
    rows = [{'t': int(r.time), 'o': float(r.open), 'h': float(r.high), 'l': float(r.low), 'c': float(r.close)}
            for r in raw.itertuples()]
    close_epoch = rows[-1]['t'] + M5_SECONDS
    age = time.time() - close_epoch
    if age > cfg['max_age']:
        print(f'  ict: M5 bar is {age:.0f}s old; analyzer rejects beyond {cfg["max_age"]}s, nothing sent')
        return
    setups = [body for body in ict_engine.detect(cfg['symbol'], rows, cfg['ict']) if body['bar_time'] == close_epoch]
    zone = ict_engine.killzone(rows[-1]['t'], cfg['ict'])
    if zone and not setups:
        stamp = dt.datetime.fromtimestamp(close_epoch, dt.timezone.utc)
        print(f'ict M5 closed {stamp:%Y-%m-%d %H:%M} UTC ({zone} killzone)  close={rows[-1]["c"]:.5f}  no setup')
    for body in setups:
        if dry_run:
            print(f'  [dry-run] would send {body["signal"]} (ict): {json.dumps(body)}')
            continue
        status, text = post(body, cfg['url'], cfg['token'])
        print(f'  sent {body["signal"]} (ict) -> HTTP {status} {text}')


def scan_ema(cfg: dict, dry_run: bool) -> None:
    """Replay the last EMA_BARS closed M1 bars and post the scalp setup triggered by the bar that just closed, if any.
    Quiet minutes print nothing; a heartbeat every 15 minutes shows the scan is alive."""
    try:
        raw = bars(cfg['mt5_symbol'], count=EMA_BARS, timeframe=mt5.TIMEFRAME_M1, seconds=M1_SECONDS)
    except NoFreshBars as reason:
        print(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC  ema: no fresh M1 bars ({reason})')
        return
    rows = [{'t': int(r.time), 'o': float(r.open), 'h': float(r.high), 'l': float(r.low), 'c': float(r.close)}
            for r in raw.itertuples()]
    close_epoch = rows[-1]['t'] + M1_SECONDS
    age = time.time() - close_epoch
    if age > cfg['max_age']:
        print(f'  ema: M1 bar is {age:.0f}s old; analyzer rejects beyond {cfg["max_age"]}s, nothing sent')
        return
    setups = [body for body in ema_engine.detect(cfg['symbol'], rows, cfg['ema']) if body['bar_time'] == close_epoch]
    if not setups and close_epoch % TF_SECONDS == 0:
        stamp = dt.datetime.fromtimestamp(close_epoch, dt.timezone.utc)
        session = 'session' if ema_engine.in_session(rows[-1]['t'], cfg['ema']) else 'outside session'
        print(f'ema M1 closed {stamp:%Y-%m-%d %H:%M} UTC ({session})  close={rows[-1]["c"]:.5f}  no setup this quarter')
    for body in setups:
        if dry_run:
            print(f'  [dry-run] would send {body["signal"]} (ema): {json.dumps(body)}')
            continue
        status, text = post(body, cfg['url'], cfg['token'])
        print(f'  sent {body["signal"]} (ema) -> HTTP {status} {text}')


def scan_mss(cfg: dict, dry_run: bool) -> None:
    """Replay the last MSS_BARS closed M15 bars and post the sweep + MSS setup completed by the hour that just closed."""
    try:
        raw = bars(cfg['mt5_symbol'], count=MSS_BARS)
    except NoFreshBars as reason:
        print(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC  mss: no fresh M15 bars ({reason})')
        return
    rows = [{'t': int(r.time), 'o': float(r.open), 'h': float(r.high), 'l': float(r.low), 'c': float(r.close)}
            for r in raw.itertuples()]
    close_epoch = rows[-1]['t'] + TF_SECONDS
    if close_epoch % mss_engine.H1:
        return                                          # the bar that just closed did not close an hour
    age = time.time() - close_epoch
    if age > cfg['max_age']:
        print(f'  mss: H1 bar is {age:.0f}s old; analyzer rejects beyond {cfg["max_age"]}s, nothing sent')
        return
    setups = [body for body in mss_engine.detect(cfg['symbol'], rows, cfg['mss']) if body['bar_time'] == close_epoch]
    if not setups:
        stamp = dt.datetime.fromtimestamp(close_epoch, dt.timezone.utc)
        print(f'mss H1 closed {stamp:%Y-%m-%d %H:%M} UTC  close={rows[-1]["c"]:.5f}  no sweep + shift setup')
    for body in setups:
        if dry_run:
            print(f'  [dry-run] would send {body["signal"]} (mss): {json.dumps(body)}')
            continue
        status, text = post(body, cfg['url'], cfg['token'])
        print(f'  sent {body["signal"]} (mss) -> HTTP {status} {text}')


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
    except (TimeoutError, ConnectionError) as exc:
        # Docker Desktop's port forward stalls now and then; one failed post must not kill the feeder and its scans.
        return 0, f'{type(exc).__name__}: {exc}'


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
        if rates is None:
            print(f'  candles: MT5 returned no result for {start}-{stop}; coverage was not advanced')
            return
        rows = [
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
    try:
        raw = bars(cfg['mt5_symbol'])
    except NoFreshBars as reason:
        print(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC  no fresh bars ({reason}); next check at the next 15m close')
        return
    df = indicators(raw, cfg['swing_bars'])
    closed, previous = df.iloc[-1], df.iloc[-2]
    close_epoch = int(closed['time']) + TF_SECONDS
    stamp = dt.datetime.fromtimestamp(close_epoch, dt.timezone.utc)
    age = time.time() - close_epoch

    print(f'bar closed {stamp:%Y-%m-%d %H:%M} UTC ({age:.0f}s ago)  close={closed["close"]:.3f}  '
          f'adx={closed["adx"]:.1f}  rsi={closed["rsi"]:.1f}  '
          f'atr%={closed["atr"] / closed["close"] * 100:.3f}')
    if age > cfg['max_age']:
        print(f'  bar is {age:.0f}s old; analyzer rejects beyond {cfg["max_age"]}s — nothing sent')
        return
    if 'crt' in cfg['models']:
        scan_crt(cfg, df, close_epoch, dry_run)
    if 'classic' in cfg['models']:
        scan_classic(cfg, closed, previous, close_epoch, dry_run)


def scan_classic(cfg: dict, closed: pd.Series, previous: pd.Series, close_epoch: int, dry_run: bool) -> None:
    valid = [d for d in DIRECTIONS if qualifies(closed, cfg, d)]
    if not valid:
        print('  classic: no qualifying setup on this bar')
        return
    if not in_session(close_epoch):
        print(f'  classic: {"/".join(valid)} valid, but outside London/New York session — not sent')
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
    parser.add_argument('--symbol', default=os.getenv('MT5_SYMBOL', 'XAUUSDm'),
                        help='broker symbol as named in MT5 (default XAUUSDm)')
    parser.add_argument('--models', default='crt',
                        help='comma list of detection models: classic, crt, ict, ema, mss (default crt)')
    args = parser.parse_args()

    settings = env()
    # A remote analyzer (VPS over an SSH tunnel, see scripts/vps_feeder.ps1) overrides the local stack's address and token.
    analyzer = os.getenv('ZEBRA_ANALYZER_URL', f'http://127.0.0.1:{settings.get("ANALYZER_PORT", "8010")}').rstrip('/')
    broker_symbol = args.symbol
    models = {m.strip().lower() for m in args.models.split(',') if m.strip()}
    if not models <= {'classic', 'crt', 'ict', 'ema', 'mss'}:
        raise SystemExit('--models accepts a comma list of classic, crt, ict, ema and mss')
    cfg = {
        'models': models,
        'mt5_symbol': broker_symbol,
        # Exness suffixes gold by account type (XAUUSDc cent, XAUUSDm standard); the analyzer only accepts [A-Z0-9]+.
        'symbol': re.sub(r'[a-z.]+$', '', broker_symbol).upper(),
        'url': analyzer + '/signals',
        'candles_url': analyzer + '/candles',
        'token': os.getenv('ZEBRA_ANALYZER_TOKEN') or settings.get('ANALYZER_TOKEN', ''),
        'min_adx': float(settings.get('MIN_ADX', 20)),
        'min_atr': float(settings.get('MIN_ATR_PERCENT', 0.02)),
        'max_atr': float(settings.get('MAX_ATR_PERCENT', 0.5)),
        'max_age': int(settings.get('MAX_SIGNAL_AGE_SECONDS', 300)),
        'swing_bars': 10,
    }
    if not cfg['token']:
        raise SystemExit('ANALYZER_TOKEN missing from .env')
    if 'crt' in models:
        exempt = {s.strip().upper() for s in settings.get('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if s.strip()}
        cfg['crt'] = crt_config(settings, cfg['symbol'] in exempt)
    if 'ict' in models:
        ict_symbols = {s.strip().upper() for s in settings.get('ICT_SYMBOLS', 'EURUSD').split(',') if s.strip()}
        if cfg['symbol'] not in ict_symbols:
            raise SystemExit(f'{cfg["symbol"]} is not in ICT_SYMBOLS ({",".join(sorted(ict_symbols))}); the analyzer '
                             'would reject every ICT setup. The ICT backtest lost money on gold.')
        cfg['ict'] = ict_engine.IctConfig(min_rr=float(settings.get('ICT_MIN_RR', 2.0)))
    if 'ema' in models:
        ema_symbols = {s.strip().upper() for s in settings.get('EMA_SYMBOLS', 'XAUUSD').split(',') if s.strip()}
        if cfg['symbol'] not in ema_symbols:
            raise SystemExit(f'{cfg["symbol"]} is not in EMA_SYMBOLS ({",".join(sorted(ema_symbols))}); the analyzer '
                             'would reject every EMA setup.')
        exempt = {s.strip().upper() for s in settings.get('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if s.strip()}
        cfg['ema'] = ema_engine.EmaConfig(min_rr=float(settings.get('EMA_MIN_RR', 1.5)), crypto=cfg['symbol'] in exempt)
    if 'mss' in models:
        mss_symbols = {s.strip().upper() for s in settings.get('MSS_SYMBOLS', 'XAUUSD').split(',') if s.strip()}
        if cfg['symbol'] not in mss_symbols:
            raise SystemExit(f'{cfg["symbol"]} is not in MSS_SYMBOLS ({",".join(sorted(mss_symbols))}); the analyzer '
                             'would reject every MSS setup.')
        exempt = {s.strip().upper() for s in settings.get('SESSION_EXEMPT_SYMBOLS', 'BTCUSD,BTCUSDT').split(',') if s.strip()}
        cfg['mss'] = mss_engine.MssConfig(min_rr=float(settings.get('MSS_MIN_RR', 2.0)),
                                          stop_buffer_atr=float(settings.get('MSS_STOP_BUFFER_ATR', 0.5)),
                                          body_atr=float(settings.get('MSS_BODY_ATR', 1.5)), crypto=cfg['symbol'] in exempt)
    m15_models = bool(models & {'classic', 'crt'})
    print(f'{cfg["mt5_symbol"]} -> {cfg["symbol"]}  {cfg["url"]}  models={",".join(sorted(models))}  '
          f'(ADX>={cfg["min_adx"]}, ATR% {cfg["min_atr"]}-{cfg["max_atr"]})')

    candles = not (args.no_candles or args.dry_run)
    state: dict = {}
    try:
        if args.once:
            if candles:
                push_candles(cfg, state)
            if m15_models:
                scan(cfg, args.dry_run)
            if 'ict' in models:
                scan_ict(cfg, args.dry_run)
            if 'ema' in models:
                scan_ema(cfg, args.dry_run)
            if 'mss' in models:
                scan_mss(cfg, args.dry_run)
            return
        cadence = ', '.join((['15m scan'] if m15_models else []) + (['5m ICT scan'] if 'ict' in models else [])
                            + (['1m EMA scan'] if 'ema' in models else []) + (['hourly MSS scan'] if 'mss' in models else []))
        print(f'watching; candles every minute, {cadence} 10s after each bar close. Ctrl+C to stop.')
        scanned = scanned_m5 = scanned_h1 = None
        while True:
            time.sleep(max(1.0, 60 - time.time() % 60 + 10))
            if candles:
                push_candles(cfg, state)
            if 'ema' in models:
                scan_ema(cfg, args.dry_run)
            bar = int(time.time()) // TF_SECONDS
            if m15_models and time.time() % TF_SECONDS < 60 and bar != scanned:
                scanned = bar
                scan(cfg, args.dry_run)
            bar_m5 = int(time.time()) // M5_SECONDS
            if 'ict' in models and time.time() % M5_SECONDS < 60 and bar_m5 != scanned_m5:
                scanned_m5 = bar_m5
                scan_ict(cfg, args.dry_run)
            bar_h1 = int(time.time()) // mss_engine.H1
            if 'mss' in models and time.time() % mss_engine.H1 < 60 and bar_h1 != scanned_h1:
                scanned_h1 = bar_h1
                scan_mss(cfg, args.dry_run)
            sys.stdout.flush()
    except KeyboardInterrupt:
        print('stopped')
    finally:
        mt5.shutdown()


if __name__ == '__main__':
    main()
