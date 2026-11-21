#!/usr/bin/env python3
"""Count and sanity-check the ICT candidates of a saved M1 history, year by year (ML plan Phase 1 / roadmap phase 2).

    python ml/check_candidates.py --symbol XAUUSD --folder .local/history_dukascopy_full

Runs ml.ict_features.detect on M5 bars rebuilt from <folder>/<SYMBOL>_m1.csv and reports, per year: trading days,
candidates, candidates per trading day, BUY share, killzone share and which pool named the sweep; then how often
each optional feature is missing.

    reject   a stop or target on the wrong side of the entry, a target that is not rr x risk, risk under the
             minimum, two candidates on the same bar and side, candidates out of time order, a feature that must
             always be a number being missing or infinite
    flag     a full year (200+ trading days) whose candidates per day are under half or over twice the median
             year, and a BUY share outside 40-60% overall: not errors, but look at them before building a dataset

Writes ml/reports/<symbol>_ict_candidates.md. Exit code 1 when anything in the reject list is found.
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.data import CRYPTO, Bars, load_m1, resample  # noqa: E402
from ml.ict_features import FEATURES, MAY_BE_MISSING, POOL_KINDS, CandidateConfig, detect, trading_days  # noqa: E402

REPORTS = ROOT / 'ml' / 'reports'
FULL_YEAR_DAYS = 200
RATE_BAND = (0.5, 2.0)             # x the median full year
BUY_BAND = (0.40, 0.60)


def check_rows(rows: list[dict], cfg: CandidateConfig) -> dict:
    """Counts of everything that must never happen in a candidate list."""
    bad = {'stop_wrong_side': 0, 'target_wrong_side': 0, 'target_not_rr': 0, 'risk_too_small': 0,
           'duplicates': 0, 'out_of_order': 0, 'feature_missing': 0}
    seen, last = set(), -1
    for r in rows:
        d = 1 if r['side'] == 'BUY' else -1
        risk = d * (r['entry'] - r['stop'])
        bad['stop_wrong_side'] += risk <= 0
        bad['target_wrong_side'] += d * (r['target'] - r['entry']) <= 0
        bad['target_not_rr'] += not math.isclose(d * (r['target'] - r['entry']), cfg.rr * risk, rel_tol=1e-9)
        bad['risk_too_small'] += r['risk_atr'] < cfg.min_risk_atr - 1e-9
        key = (r['bar_index'], r['side'])
        bad['duplicates'] += key in seen
        seen.add(key)
        bad['out_of_order'] += r['bar_index'] < last
        last = r['bar_index']
        bad['feature_missing'] += any(not math.isfinite(r[k]) for k in FEATURES if k not in MAY_BE_MISSING)
    return {k: int(v) for k, v in bad.items()}


def by_year(rows: list[dict], m5: Bars) -> list[dict]:
    """One line per calendar year (UTC) of the history, including years with no candidates."""
    _, weekday, day = trading_days(m5.t)
    bar_year = m5.t.astype('datetime64[s]').astype('datetime64[Y]').astype(int) + 1970
    weekdays = weekday < 5
    out = []
    for year in np.unique(bar_year):
        mine = [r for r in rows if bar_year[r['bar_index']] == year]
        days = int(len(np.unique(day[(bar_year == year) & weekdays])))
        pools = {kind: sum(1 for r in mine if POOL_KINDS[int(r['pool_kind'])] == kind) for kind in POOL_KINDS}
        out.append({
            'year': int(year), 'm5_bars': int((bar_year == year).sum()), 'trading_days': days,
            'candidates': len(mine), 'per_day': round(len(mine) / days, 2) if days else 0.0,
            'buy_share': round(sum(r['side'] == 'BUY' for r in mine) / len(mine), 3) if mine else None,
            'killzone_share': round(sum(r['in_killzone'] for r in mine) / len(mine), 3) if mine else None,
            'pools': pools,
        })
    return out


def find_flags(years: list[dict], rows: list[dict]) -> list[str]:
    flags = []
    full = [y for y in years if y['trading_days'] >= FULL_YEAR_DAYS]
    if full:
        median = float(np.median([y['per_day'] for y in full]))
        for y in full:
            if not RATE_BAND[0] * median <= y['per_day'] <= RATE_BAND[1] * median:
                flags.append(f"{y['year']}: {y['per_day']} candidates per day, the median full year has {median:.2f}")
    if rows:
        share = sum(r['side'] == 'BUY' for r in rows) / len(rows)
        if not BUY_BAND[0] <= share <= BUY_BAND[1]:
            flags.append(f'BUY share {share:.1%} overall is outside {BUY_BAND[0]:.0%}-{BUY_BAND[1]:.0%}')
    return flags


def missing_features(rows: list[dict]) -> dict:
    """Share of candidates where each optional feature is NaN (only the ones that ever are)."""
    if not rows:
        return {}
    share = {k: sum(math.isnan(r[k]) for r in rows) / len(rows) for k in FEATURES}
    return {k: round(v, 4) for k, v in share.items() if v > 0}


def run_checks(symbol: str, m5: Bars, cfg: CandidateConfig | None = None) -> dict:
    cfg = cfg or CandidateConfig(crypto=symbol.upper() in CRYPTO)
    started = time.time()
    rows = detect(symbol, m5, cfg)
    years = by_year(rows, m5)
    rejects = check_rows(rows, cfg)
    return {
        'symbol': symbol.upper(), 'm5_bars': len(m5), 'candidates': len(rows), 'seconds': round(time.time() - started, 1),
        'first': int(m5.t[0]) if len(m5) else None, 'last': int(m5.t[-1]) if len(m5) else None,
        'years': years, 'rejects': rejects, 'flags': find_flags(years, rows), 'missing': missing_features(rows),
        'passed': not any(rejects.values()),
    }


def markdown(r: dict) -> str:
    def day(t):
        return datetime.fromtimestamp(t, timezone.utc).strftime('%Y-%m-%d') if t else '-'

    def share(value):
        return f'{value:.1%}' if value is not None else '-'

    lines = [f"# {r['symbol']} ICT candidates by year", '',
             f"{r['candidates']} candidates from {r['m5_bars']} M5 bars, {day(r['first'])} to {day(r['last'])} "
             f"(detected in {r['seconds']} s). Result: **{'pass' if r['passed'] else 'REJECT'}**.", '',
             '| Year | M5 bars | Trading days | Candidates | Per day | BUY | In killzone | '
             + ' | '.join(POOL_KINDS) + ' |',
             '|---|---|---|---|---|---|---|' + '---|' * len(POOL_KINDS)]
    for y in r['years']:
        lines.append(f"| {y['year']} | {y['m5_bars']} | {y['trading_days']} | {y['candidates']} | {y['per_day']} | "
                     f"{share(y['buy_share'])} | {share(y['killzone_share'])} | "
                     + ' | '.join(str(y['pools'][k]) for k in POOL_KINDS) + ' |')
    lines += ['', '## Rejects', '']
    lines += [f'- {name}: {count}' for name, count in r['rejects'].items()]
    lines += ['', '## Flags', '']
    lines += [f'- {flag}' for flag in r['flags']] or ['- none']
    lines += ['', '## Optional features that are missing (share of candidates)', '']
    lines += [f'- {name}: {value:.2%}' for name, value in r['missing'].items()] or ['- none']
    return '\n'.join(lines) + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--folder', type=Path, default=ROOT / '.local' / 'history_dukascopy_full')
    parser.add_argument('--report', type=Path, default=None, help='Markdown report path (default ml/reports/)')
    args = parser.parse_args()
    symbol = args.symbol.upper()
    m5 = resample(load_m1(symbol, args.folder), 300)
    result = run_checks(symbol, m5)
    text = markdown(result)
    report = args.report or REPORTS / f'{symbol.lower()}_ict_candidates.md'
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text)
    print(text)
    print(f'report -> {report}')
    if not result['passed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
