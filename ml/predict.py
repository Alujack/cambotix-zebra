#!/usr/bin/env python3
"""Score the latest closed M5 bar with the saved ICT model (ML plan section 9, roadmap phase 6).

    python -m ml.predict                                   # newest bar of the saved Dukascopy history
    python -m ml.predict --at 2026-11-20T14:35 --allow-failed-gates   # research: a past bar, a failed model

Loads ml/models/<symbol>_ict_lgbm.json (the version ml/train.py promoted) and its LightGBM file, runs the
detection engine over the last --lookback M5 bars and prints, as analyzer-style ICT payloads with
`ml_probability`, the candidates on the scored bar whose probability reaches the model's threshold.

Safety: a model whose walk-forward did not pass the section 8 gates, or that found no profitable threshold, is
refused (ModelRefused) unless --allow-failed-gates is given. Nothing here posts to the analyzer; wiring this into
scripts/mt5_feeder.py is section 9's step for a model that passes.

The lookback must be long enough for the slowest feature to converge: the H4 EMA50 proxy is an EMA over 2,400 M5
bars, so 3,000 bars would leave it about 8% short. The default 15,000 bars (about 52 trading days) makes the
features match a full-history run (tests/test_predict.py checks this).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.data import CRYPTO, Bars, load_m1, resample  # noqa: E402
from ml.ict_features import FEATURES, CandidateConfig, detect, payload  # noqa: E402

MODELS = ROOT / 'ml' / 'models'
LOOKBACK = 15_000


class ModelRefused(Exception):
    """The saved model must not be used for signals (failed gates or no profitable threshold)."""


def load_model(symbol: str = 'XAUUSD', folder: Path = MODELS, allow_failed: bool = False):
    """(booster, meta) of the promoted model. Raises FileNotFoundError or ModelRefused."""
    import lightgbm as lgb

    pointer = Path(folder) / f'{symbol.lower()}_ict_lgbm.json'
    if not pointer.exists():
        raise FileNotFoundError(f'no model: {pointer} (train one with python -m ml.train)')
    meta = json.loads(pointer.read_text())
    if not allow_failed:
        if not meta.get('gates_passed'):
            failed = [g['gate'] for g in meta.get('gates', []) if not g.get('passed')]
            raise ModelRefused(f"{meta.get('version')}: walk-forward gates {failed} failed "
                               '(ml/reports/*_walkforward.md); not for signals')
        if meta.get('threshold') is None:
            raise ModelRefused(f"{meta.get('version')}: no profitable threshold on validation; not for signals")
    if list(meta['features']) != list(FEATURES):
        raise ModelRefused(f"{meta.get('version')}: trained on different features than ml.ict_features.FEATURES")
    booster = lgb.Booster(model_file=str(Path(folder) / meta['model_file']))
    return booster, meta


def score(symbol: str, m5: Bars, booster, meta: dict, at: int | None = None, lookback: int = LOOKBACK) -> list[dict]:
    """Candidates whose signal bar is the last closed bar (or the bar closing at `at`), each with `probability`
    and `take` (probability >= the model's threshold). M5 must be closed bars only."""
    end = len(m5) if at is None else int(np.searchsorted(m5.t, at - 300, side='right'))
    if end == 0:
        return []
    window = m5.slice(max(0, end - lookback), end)
    cfg = CandidateConfig(rr=float(meta.get('rr', 2.0)), crypto=symbol.upper() in CRYPTO)
    rows = detect(symbol, window, cfg, start_index=len(window) - 1)
    if not rows:
        return []
    probs = booster.predict(np.array([[r[k] for k in FEATURES] for r in rows], dtype=float))
    threshold = meta.get('threshold')
    cut = math.inf if threshold is None else float(threshold)
    return [{**r, 'probability': float(p), 'take': bool(p >= cut)} for r, p in zip(rows, probs)]


def signals(rows: list[dict]) -> list[dict]:
    """Analyzer-style payloads for the rows the model takes."""
    return [payload(r, r['probability']) for r in rows if r['take']]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--symbol', default='XAUUSD')
    parser.add_argument('--folder', type=Path, default=ROOT / '.local' / 'history_dukascopy_full')
    parser.add_argument('--models', type=Path, default=MODELS)
    parser.add_argument('--at', help='score the M5 bar closing at this UTC time (YYYY-MM-DDTHH:MM) instead of the last')
    parser.add_argument('--lookback', type=int, default=LOOKBACK, help='M5 bars of history to detect on')
    parser.add_argument('--allow-failed-gates', action='store_true', help='research only: use a model that failed')
    args = parser.parse_args()

    symbol = args.symbol.upper()
    try:
        booster, meta = load_model(symbol, args.models, args.allow_failed_gates)
    except ModelRefused as error:
        raise SystemExit(f'refused: {error}')
    at = int(datetime.fromisoformat(args.at).replace(tzinfo=timezone.utc).timestamp()) if args.at else None
    # Only the bars the lookback needs (weekends: about 1.4x calendar time); the whole file when scoring the end.
    start = at - (args.lookback + 600) * 300 * 7 // 5 if at else None
    m5 = resample(load_m1(symbol, args.folder, start=start, end=at), 300)
    rows = score(symbol, m5, booster, meta, at, args.lookback)
    when = datetime.fromtimestamp(int(m5.t[-1]) + 300, timezone.utc).strftime('%Y-%m-%d %H:%M') if len(m5) else '-'
    print(f"model {meta['version']} (threshold {meta.get('threshold')}, gates "
          f"{'passed' if meta.get('gates_passed') else 'FAILED'}); bar closing {when} UTC: {len(rows)} candidate(s)")
    for r in rows:
        print(f"  {r['side']:<4} entry {r['entry']:.3f} stop {r['stop']:.3f} target {r['target']:.3f} "
              f"p={r['probability']:.3f} {'TAKE' if r['take'] else 'skip'} ({r['swept_name']})")
    for body in signals(rows):
        print(json.dumps(body))


if __name__ == '__main__':
    main()
