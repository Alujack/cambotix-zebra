#!/usr/bin/env python3
"""Score the latest closed M5 bar with the promoted v2 model (plan section 9 and V2.6; roadmap phase 6).

    python -m ml.predict                                   # newest bar of the saved Dukascopy history
    python -m ml.predict --at 2024-06-12T14:35 --research  # research: a past bar, whatever the model's status

Loads the promoted model (ml/models/<symbol>_ict_v2.json), runs the detection engine over the last --lookback M5
bars and prints the candidates on the scored bar with their expected net R, and, as analyzer-style ICT payloads,
the ones the model takes: expected R at or above the model's cut and a stop the account can size.

Safety: the model is refused (ModelRefused) unless it passed the five development gates, has a cut, and the final
test on the lockbox ran and passed (ml/models/<symbol>_final_test.json). --research skips those checks to inspect
a model; its output is not a signal. Nothing here posts to the analyzer.

The lookback must be long enough for the slowest feature to converge: the H4 EMA50 proxy is an EMA over 2,400 M5
bars, so 3,000 bars would leave it about 8% short. The default 15,000 bars (about 52 trading days) makes every
feature, including the H1/H4 structure, match a full-history run (tests/test_ml_model.py checks this).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml import lockbox, train  # noqa: E402
from ml.data import CRYPTO, Bars, load_m1, resample  # noqa: E402
from ml.ict_features import CATEGORICAL, FEATURES, CandidateConfig, detect, payload  # noqa: E402

MODELS = train.MODELS
LOOKBACK = 15_000
ACCOUNT_RISK_USD = 10.0              # as ml.dataset: the stop must fit the account at the minimum position


class ModelRefused(Exception):
    """The promoted model must not be used for signals."""


def load_model(symbol: str = 'XAUUSD', folder: Path = MODELS, research: bool = False) -> tuple[dict, dict]:
    """(bundle, meta) of the promoted model. Raises FileNotFoundError or ModelRefused."""
    bundle, meta = train.load_model(symbol, folder)
    if list(meta['features']) != list(FEATURES):
        raise ModelRefused(f"{meta['version']}: trained on different features than ml.ict_features.FEATURES")
    if research:
        return bundle, meta
    if not meta.get('gates_passed'):
        failed = [g['gate'] for g in meta.get('gates', []) if not g.get('passed')]
        raise ModelRefused(f"{meta['version']}: development gates {failed} failed; not for signals")
    if meta.get('threshold') is None:
        raise ModelRefused(f"{meta['version']}: no profitable cut on validation; not for signals")
    final = lockbox.record(symbol, folder)
    if final is None:
        raise ModelRefused(f"{meta['version']}: the final test on the lockbox has not run (python -m ml.final_test)")
    if not final.get('passed') or final.get('model') != meta['version']:
        raise ModelRefused(f"{meta['version']}: the final test on the lockbox did not pass for this model")
    return bundle, meta


def score(symbol: str, m5: Bars, bundle: dict, meta: dict, at: int | None = None,
          lookback: int = LOOKBACK) -> list[dict]:
    """Candidates whose signal bar is the last closed bar (or the bar closing at `at`), each with p_target,
    expected_r and `take` (expected R at or above the cut, and a stop the account can size). M5 = closed bars."""
    end = len(m5) if at is None else int(np.searchsorted(m5.t, at - 300, side='right'))
    if end == 0:
        return []
    window = m5.slice(max(0, end - lookback), end)
    cfg = CandidateConfig(rr=float(meta.get('rr', 2.0)), crypto=symbol.upper() in CRYPTO)
    rows = detect(symbol, window, cfg, start_index=len(window) - 1)
    if not rows:
        return []
    frame = pd.DataFrame(rows)
    for col in CATEGORICAL:
        frame[col] = frame[col].astype(int)
    scores = train.score(bundle, frame)
    threshold = meta.get('threshold')
    cut = math.inf if threshold is None else float(threshold)
    return [{**row, 'p_target': float(s.p_target), 'expected_r': float(s.expected_r),
             'tradable': bool(row['risk'] <= ACCOUNT_RISK_USD),
             'take': bool(s.expected_r >= cut and row['risk'] <= ACCOUNT_RISK_USD)}
            for row, s in zip(rows, scores.itertuples())]


def signals(rows: list[dict]) -> list[dict]:
    """Analyzer-style payloads for the rows the model takes."""
    out = []
    for r in rows:
        if r['take']:
            body = payload(r, r['p_target'])
            body['ml_expected_r'] = round(r['expected_r'], 4)
            out.append(body)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--folder', type=Path, default=ROOT / '.local' / 'history_dukascopy_full')
    parser.add_argument('--models', type=Path, default=MODELS)
    parser.add_argument('--at', help='score the M5 bar closing at this UTC time (YYYY-MM-DDTHH:MM) instead of the last')
    parser.add_argument('--lookback', type=int, default=LOOKBACK, help='M5 bars of history to detect on')
    parser.add_argument('--research', action='store_true', help='inspect a model that may not be used for signals')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    try:
        bundle, meta = load_model(symbol, args.models, args.research)
    except ModelRefused as error:
        raise SystemExit(f'refused: {error}')
    at = int(datetime.fromisoformat(args.at).replace(tzinfo=timezone.utc).timestamp()) if args.at else None
    # Only the bars the lookback needs (weekends: about 1.4x calendar time); the whole file when scoring the end.
    start = at - (args.lookback + 600) * 300 * 7 // 5 if at else None
    m5 = resample(load_m1(symbol, args.folder, start=start, end=at), 300)
    rows = score(symbol, m5, bundle, meta, at, args.lookback)
    when = datetime.fromtimestamp(int(m5.t[-1]) + 300, timezone.utc).strftime('%Y-%m-%d %H:%M') if len(m5) else '-'
    cut = meta.get('threshold')
    print(f"model {meta['version']} (cut {'none' if cut is None else f'{cut:+.3f}R'}, development gates "
          f"{'passed' if meta.get('gates_passed') else 'FAILED'}{', RESEARCH MODE' if args.research else ''}); "
          f"bar closing {when} UTC: {len(rows)} candidate(s)")
    for r in rows:
        print(f"  {r['side']:<4} entry {r['entry']:.3f} stop {r['stop']:.3f} target {r['target']:.3f} "
              f"expected {r['expected_r']:+.3f}R p(target)={r['p_target']:.3f} "
              f"{'TAKE' if r['take'] else 'skip'}{'' if r['tradable'] else ' (stop too wide for the account)'} "
              f"({r['swept_name']})")
    if not args.research:
        for body in signals(rows):
            print(json.dumps(body))


if __name__ == '__main__':
    main()
