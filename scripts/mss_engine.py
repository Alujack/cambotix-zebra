"""Liquidity sweep + market structure shift (MSS) on H1: ICT's canonical reversal, ported from a sibling project
whose walk-forward found a gold-only, regime-local edge on this timeframe (README "MSS model").

    swings   2/2 fractals: a high above the two bars on each side is a swing high, a low below them a swing low
             (strict, so equal highs are not swings). A swing is known two bars after its pivot, never earlier.
    sweep    within the last sweep_lookback H1 bars (the decision bar included) a bar traded below the last known
             swing low but closed back above it: a buy. The mirror above a swing high is a sell. The latest such
             bar counts and its wick is the sweep extreme.
    MSS      the decision bar is a displacement candle (body >= body_atr x ATR(14, H1) and at least body_ratio of
             its range) that closes beyond the last known opposing swing: above the last swing high for a buy.
    plan     market entry at the decision bar's close, stop beyond the sweep extreme + stop_buffer_atr x ATR, target
             the nearest known swing beyond the entry (the next liquidity pool) when it is at least min_rr away,
             else min_rr x risk. No session or killzone filter: the sweep and the shift set the bias.

Every decision sees only the last `lookback` H1 bars, as the live feeder does, so a backtest and the feeder find the
same swings and the same liquidity targets; the first warmup_bars bars never signal so ATR has settled. H1 candles
are built from closed M15 bars on the hour of the broker's clock (UTC on Exness); a forming hour never signals.

detect() returns analyzer payloads (app.domain.Signal, model 'mss'), one per setup, keyed by the close time of the
decision bar; the feeder posts only the one that just closed. Standard library only; bars are dicts t,o,h,l,c with
t = open time in UTC seconds.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

M15, H1 = 900, 3600


@dataclass
class MssConfig:
    swing_k: int = 2                  # bars on each side of a fractal pivot
    sweep_lookback: int = 5           # H1 bars (the decision bar included) in which the sweep must have printed
    lookback: int = 80                # H1 bars a decision sees: swings and liquidity targets come from this window
    body_atr: float = 1.5             # displacement: body >= body_atr x ATR(14, H1)
    body_ratio: float = 0.5           # and body / range >= body_ratio
    stop_buffer_atr: float = 0.5
    min_rr: float = 2.0               # the target is at least this many R (the analyzer re-checks MSS_MIN_RR)
    min_risk_atr: float = 0.3         # skip stops tighter than spread noise (the analyzer re-checks)
    warmup_bars: int = 100            # H1 bars before the first decision: Wilder ATR(14) has settled by then
    crypto: bool = False              # trade weekends
    bar_minutes: int = 60             # decision candle size; the analyzer accepts 60 (1h) only, other sizes are research
    source_minutes: int = 15          # size of the bars handed to detect(), which are aggregated into decision candles


def aggregate(bars: list[dict], period: int, source: int) -> list[dict]:
    """Candles of `period` seconds aligned on the clock, built from closed `source`-second bars. The last candle
    counts only when its final source bar is present, so a forming candle never signals."""
    out: list[dict] = []
    for bar in bars:
        key = bar['t'] - bar['t'] % period
        if out and out[-1]['t'] == key:
            last = out[-1]
            last['h'], last['l'], last['c'] = max(last['h'], bar['h']), min(last['l'], bar['l']), bar['c']
        else:
            out.append({'t': key, 'o': bar['o'], 'h': bar['h'], 'l': bar['l'], 'c': bar['c']})
    if bars and bars[-1]['t'] % period != period - source:
        out.pop()
    return out


def h1_from_m15(m15: list[dict]) -> list[dict]:
    """Hourly candles on the hour. The last hour counts only when its final M15 bar (:45) is present."""
    return aggregate(m15, H1, M15)


def atr_series(bars: list[dict], n: int = 14) -> list[float]:
    out, prev_close, value = [], None, None
    for bar in bars:
        tr = bar['h'] - bar['l'] if prev_close is None else max(bar['h'] - bar['l'], abs(bar['h'] - prev_close),
                                                                abs(bar['l'] - prev_close))
        value = tr if value is None else (value * (n - 1) + tr) / n
        out.append(value)
        prev_close = bar['c']
    return out


def swing_flags(bars: list[dict], k: int) -> tuple[list[bool], list[bool]]:
    """(is swing high, is swing low) per bar: a strict local extreme over the k bars on each side."""
    n = len(bars)
    highs, lows = [False] * n, [False] * n
    for i in range(k, n - k):
        around = [j for j in range(i - k, i + k + 1) if j != i]
        highs[i] = all(bars[i]['h'] > bars[j]['h'] for j in around)
        lows[i] = all(bars[i]['l'] < bars[j]['l'] for j in around)
    return highs, lows


def is_displacement(bar: dict, atr: float, cfg: MssConfig) -> bool:
    body, rng = abs(bar['c'] - bar['o']), bar['h'] - bar['l']
    return rng > 0 and atr > 0 and body >= cfg.body_atr * atr and body / rng >= cfg.body_ratio


def weekday(stamp: int) -> bool:
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).weekday() < 5


def detect(symbol: str, m15: list[dict], cfg: MssConfig) -> list[dict]:
    """Every sweep + MSS setup in closed M15 history, as analyzer payloads in time order."""
    period = cfg.bar_minutes * 60
    h1 = aggregate(m15, period, cfg.source_minutes * 60)
    timeframe = '1h' if cfg.bar_minutes == 60 else f'{cfg.bar_minutes}m'
    atr = atr_series(h1)
    high_flags, low_flags = swing_flags(h1, cfg.swing_k)
    setups: list[dict] = []
    for i in range(max(cfg.warmup_bars, 2 * cfg.swing_k + 2), len(h1)):
        bar = h1[i]
        if not cfg.crypto and not weekday(bar['t']):
            continue
        if not is_displacement(bar, atr[i], cfg):
            continue
        start = max(0, i - cfg.lookback + 1)

        def last_swing(flags: list[bool], before: int, known_by: int) -> int | None:
            """Index of the most recent pivot before `before` that is already known (k bars old) at `known_by`."""
            for j in range(min(before, known_by - cfg.swing_k + 1) - 1, start - 1, -1):
                if flags[j]:
                    return j
            return None

        best = None
        for buy in (True, False):
            swept_flags, broken_flags = (low_flags, high_flags) if buy else (high_flags, low_flags)
            sweep = None
            for j in range(max(start, i - cfg.sweep_lookback + 1), i + 1):
                p = last_swing(swept_flags, j, j)
                if p is None:
                    continue
                level, b = (h1[p]['l'] if buy else h1[p]['h']), h1[j]
                if (b['l'] < level < b['c']) if buy else (b['h'] > level > b['c']):
                    sweep = (level, b['l'] if buy else b['h'])
            if sweep is None:
                continue
            broken = last_swing(broken_flags, i, i)
            if broken is None:
                continue
            mss_level = h1[broken]['h'] if buy else h1[broken]['l']
            if not ((bar['c'] > mss_level) if buy else (bar['c'] < mss_level)):
                continue
            entry = bar['c']
            stop = sweep[1] - cfg.stop_buffer_atr * atr[i] if buy else sweep[1] + cfg.stop_buffer_atr * atr[i]
            risk = abs(entry - stop)
            if risk < cfg.min_risk_atr * atr[i]:
                continue
            pools = [h1[j]['h'] if buy else h1[j]['l'] for j in range(start, i - cfg.swing_k + 1) if broken_flags[j]]
            beyond = [p for p in pools if ((p > entry) if buy else (p < entry))]
            liquidity = (min(beyond) if buy else max(beyond)) if beyond else None
            if liquidity is not None and abs(liquidity - entry) / risk >= cfg.min_rr:
                target, target_name = liquidity, 'swing high' if buy else 'swing low'
            else:
                target, target_name = entry + (1 if buy else -1) * cfg.min_rr * risk, f'{cfg.min_rr:g}R'
            rr = abs(target - entry) / risk
            if best is None or rr > best[0]:
                best = (rr, buy, sweep, mss_level, stop, target, target_name)
        if best is None:
            continue
        _, buy, sweep, mss_level, stop, target, target_name = best
        close_time = bar['t'] + period
        direction = 'BUY_SETUP' if buy else 'SELL_SETUP'
        number = lambda value: round(float(value), 8)
        setups.append({
            'event_id': f'{symbol}-{timeframe}-mss-{close_time}-{direction}', 'symbol': symbol, 'timeframe': timeframe,
            'bar_time': close_time, 'signal': direction, 'model': 'mss', 'price': number(bar['c']), 'atr': number(atr[i]),
            'sweep_level': number(sweep[1]), 'mss_level': number(mss_level),
            ('swing_low' if buy else 'swing_high'): number(sweep[0]),
            'entry': number(bar['c']), 'stop': number(stop), 'target_liquidity': number(target),
            'swept_name': 'swing low' if buy else 'swing high', 'target_name': target_name,
        })
    return setups
