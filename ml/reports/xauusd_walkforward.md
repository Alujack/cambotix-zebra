# XAUUSD ICT model walk-forward (2026-11-21 11:11 UTC)

Dataset `xauusd_ict.parquet`: 26,879 resolved candidates (16,826 filled), 2008-01-02 .. 2026-11-20. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (26 folds); one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.101R, PF 0.81 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.018R vs model -0.101R; AUC 0.574 vs control 0.498 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 years positive | 1 of 5 traded folds positive (26 folds in all); last 2 years -3.3R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 55.8R, 38 trades a year | no |
| 5 | holds on Exness prices and spreads (same fold models) | > +0.10R per trade and PF > 1.2 | 92 trades, -0.094R, PF 0.82 | no |

The model does not go to a forward test. ml/predict.py refuses this model unless run with --allow-failed-gates (research only).

Out-of-sample AUC on filled trades: **0.574** (shuffled-label control 0.498; 0.5 = no skill).

## Out-of-sample result, net R (all folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 16721 | 10558 | 32.2% | -0.212 | -2240.6 | 0.69 | 2247.8 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1659 | 33.9% | -0.183 | -304.4 | 0.71 | 313.6 |
| spread/risk cut-off | 1140 | 750 | 42.4% | -0.018 | -13.8 | 0.96 | 46.0 |
| model | 779 | 492 | 38.8% | -0.101 | -49.5 | 0.81 | 55.8 |
| model, shuffled-label control | 0 | 0 | - | - | 0.0 | - | 0.0 |

Gross R (spread only, no slippage):

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 16721 | 10558 | 32.2% | -0.151 | -1599.4 | 0.76 | 1606.6 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1659 | 33.9% | -0.140 | -232.1 | 0.77 | 243.3 |
| spread/risk cut-off | 1140 | 750 | 42.4% | +0.005 | +3.8 | 1.01 | 34.1 |
| model | 779 | 492 | 38.8% | -0.066 | -32.4 | 0.87 | 39.8 |

## Same fold models on Exness prices (2023-11-24 .. 2026-11-13), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 3942 | 2565 | 35.2% | -0.081 | -208.2 | 0.87 | 212.6 |
| ict_engine-style (killzone, session/day pools) | 537 | 358 | 34.9% | -0.106 | -37.8 | 0.83 | 42.0 |
| spread/risk cut-off | 1252 | 832 | 37.1% | -0.071 | -59.2 | 0.88 | 74.4 |
| model | 142 | 92 | 38.0% | -0.094 | -8.6 | 0.82 | 13.9 |

## Stress test: final model on 2008-2010 (never trained on; p99 spread floor), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 3904 | 2333 | 24.9% | -0.495 | -1154.1 | 0.41 | 1154.1 |
| ict_engine-style (killzone, session/day pools) | 644 | 413 | 29.1% | -0.385 | -158.9 | 0.51 | 158.9 |
| model | 0 | 0 | - | - | 0.0 | - | 0.0 |

## Model by fold

| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -84.1 |
| 2014-07-01 | 0.325 | 159 | 215 | 140 | 33.6% | -0.168 | -23.5 | 0.69 | 23.8 | -111.5 |
| 2015-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -93.7 |
| 2015-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -92.5 |
| 2016-01-01 | 0.342 | 267 | 262 | 159 | 40.9% | -0.073 | -11.6 | 0.87 | 14.3 | -63.5 |
| 2016-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -86.5 |
| 2017-01-01 | 0.361 | 161 | 68 | 41 | 48.8% | +0.070 | +2.9 | 1.16 | 6.6 | -98.7 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -57.2 |
| 2018-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -91.9 |
| 2018-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -121.7 |
| 2019-01-01 | 0.368 | 213 | 108 | 73 | 35.6% | -0.191 | -13.9 | 0.64 | 21.6 | -116.6 |
| 2019-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -116.5 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -86.2 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -54.6 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -66.3 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -116.7 |
| 2022-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -87.1 |
| 2022-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -81.1 |
| 2023-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -65.7 |
| 2023-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -96.5 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -127.1 |
| 2024-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -101.9 |
| 2025-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -95.1 |
| 2025-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -47.8 |
| 2026-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -26.2 |
| 2026-07-01 | 0.396 | 418 | 126 | 79 | 41.8% | -0.041 | -3.3 | 0.92 | 10.8 | -53.9 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2014 | 215 | 140 | 33.6% | -0.168 | -23.5 | 0.69 | 23.8 |
| 2016 | 262 | 159 | 40.9% | -0.073 | -11.6 | 0.87 | 14.3 |
| 2017 | 68 | 41 | 48.8% | +0.070 | +2.9 | 1.16 | 6.6 |
| 2019 | 108 | 73 | 35.6% | -0.191 | -13.9 | 0.64 | 21.6 |
| 2026 | 126 | 79 | 41.8% | -0.041 | -3.3 | 0.92 | 10.8 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 159 | 101 | 39.6% | -0.016 | -1.7 | 0.97 | 15.9 |
| close | 33 | 21 | 33.3% | -0.297 | -6.2 | 0.54 | 7.2 |
| london_kz | 56 | 42 | 33.3% | -0.253 | -10.6 | 0.62 | 10.6 |
| london_mid | 73 | 50 | 36.0% | -0.105 | -5.2 | 0.83 | 9.8 |
| ny_am_kz | 270 | 168 | 42.9% | -0.048 | -8.0 | 0.90 | 12.7 |
| ny_mid | 122 | 77 | 31.2% | -0.238 | -18.3 | 0.52 | 23.4 |
| ny_pm | 66 | 33 | 48.5% | +0.018 | +0.6 | 1.05 | 5.3 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 385 | 221 | 35.3% | -0.194 | -42.9 | 0.66 | 44.3 |
| SELL | 394 | 271 | 41.7% | -0.024 | -6.6 | 0.95 | 24.5 |

## Model by era

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2020 on | 126 | 79 | 41.8% | -0.041 | -3.3 | 0.92 | 10.8 |
| before 2020 | 653 | 413 | 38.3% | -0.112 | -46.3 | 0.79 | 48.4 |

## Calibration (filled test trades, probability deciles)

| predicted | actual win | trades | exp R |
|---|---|---|---|
| 0.227 | 0.224 | 1153 | -0.480 |
| 0.273 | 0.270 | 1153 | -0.302 |
| 0.290 | 0.282 | 1153 | -0.269 |
| 0.302 | 0.285 | 1152 | -0.254 |
| 0.314 | 0.317 | 1153 | -0.174 |
| 0.327 | 0.330 | 1153 | -0.177 |
| 0.342 | 0.333 | 1152 | -0.182 |
| 0.360 | 0.344 | 1153 | -0.170 |
| 0.383 | 0.393 | 1153 | -0.079 |
| 0.419 | 0.434 | 1153 | -0.046 |

## Feature importance (final model, gain)

| feature | share |
|---|---|
| spread_risk | 25.8% |
| risk_atr | 6.5% |
| atr_ratio_day | 5.9% |
| ny_hour | 4.9% |
| atr_pct | 4.6% |
| leg_atr | 4.5% |
| opp_pool_r | 3.3% |
| ob_dist_atr | 2.7% |
| atr_ratio_week | 2.5% |
| ret_1h_atr | 2.5% |
| asia_range_atr | 2.3% |
| day_range_atr | 2.2% |
| ote_fib | 2.1% |
| ret_4h_atr | 2.0% |
| sweep_wick_ratio | 1.9% |

## Saved model

`ml/models/xauusd_ict_lgbm_20261120.txt`: 14,302 filled trades 2011-01-03 .. 2026-11-20, 53 trees, threshold none (no profitable cut on validation: do not trade), gates FAILED.
