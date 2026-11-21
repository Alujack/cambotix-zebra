"""Synthetic labelled candidates for the ML tests: the same columns as ml/data/<name>_dev.parquet."""
import numpy as np
import pandas as pd

from ml.ict_features import CATEGORICAL, FEATURES

START = 1293840000           # 2011-01-01 UTC
YEAR = 365 * 86400


def candidates(n=9000, seed=1, signal=True, start=START, years=5.0):
    """Candidates spread over `years`. With `signal`, setups with a low spread/risk reach the 2R target far more
    often; without it every setup has the same odds. About 65% fill; outcomes are target / stop / timeout."""
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({name: rng.normal(size=n) for name in FEATURES})
    for name in CATEGORICAL:
        df[name] = rng.integers(0, 4, n)
    df['in_killzone'] = rng.integers(0, 2, n).astype(float)
    df['spread_risk'] = rng.uniform(0.02, 0.4, n)
    df['bar_time'] = np.sort(rng.integers(start, start + int(years * YEAR), n))
    df['end_time'] = (df['bar_time'] + 8 * 3600).astype(float)
    df['side'] = np.where(rng.random(n) < 0.5, 'BUY', 'SELL')
    df['symbol'] = 'XAUUSD'
    df['year'] = pd.to_datetime(df['bar_time'], unit='s').dt.year.astype(int)
    df['entry'], df['risk'] = 2000.0, rng.uniform(1.0, 8.0, n)
    df['target'] = df['entry'] + 2 * df['risk']
    df['tradable'] = True
    filled = rng.random(n) < 0.65
    p_target = np.where(df['spread_risk'] < 0.1, 0.55, 0.15) if signal else np.full(n, 0.22)
    u = rng.random(n)
    cls = np.where(u < p_target, 0, np.where(u < p_target + 0.2, 2, 1))        # 20% time out, the rest stop
    timeout_r = rng.normal(0.2, 0.6, n)
    r = np.where(cls == 0, 2.0, np.where(cls == 1, -1.0, timeout_r)) - df['spread_risk'].to_numpy() * 0.5
    df['outcome'] = np.where(filled, 'closed', 'not_filled:entry_expired')
    df['outcome_class'] = np.where(filled, cls.astype(float), np.nan)
    df['exit'] = np.where(filled, np.array(['final_target', 'sl', 'timeout'])[cls], '')
    df['r'] = np.where(filled, r, 0.0)
    df['win'] = np.where(filled, (r > 0).astype(float), np.nan)
    return df
