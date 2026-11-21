# XAUUSD ICT model walk-forward (2026-11-21 11:06 UTC)

Dataset `xauusd_ict_mid.parquet`: 26,879 resolved candidates (14,515 filled), 2008-01-02 .. 2026-11-20. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (26 folds); one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.105R, PF 0.81 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.100R vs model -0.105R; AUC 0.574 vs control 0.498 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 years positive | 0 of 3 traded folds positive (26 folds in all); last 2 years +0.0R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 25.6R, 16 trades a year | no |
| 5 | holds on Exness prices and spreads (same fold models) | > +0.10R per trade and PF > 1.2 | 0 trades | no |

The model does not go to a forward test. ml/predict.py refuses this model unless run with --allow-failed-gates (research only).

Out-of-sample AUC on filled trades: **0.574** (shuffled-label control 0.498; 0.5 = no skill).

## Out-of-sample result, net R (all folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 17002 | 9269 | 31.4% | -0.227 | -2100.9 | 0.68 | 2106.9 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1422 | 33.7% | -0.178 | -252.5 | 0.73 | 265.1 |
| spread/risk cut-off | 1425 | 836 | 39.4% | -0.100 | -83.4 | 0.81 | 96.2 |
| model | 359 | 204 | 38.7% | -0.105 | -21.4 | 0.81 | 25.6 |
| model, shuffled-label control | 0 | 0 | - | - | 0.0 | - | 0.0 |

Gross R (spread only, no slippage):

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 17002 | 9269 | 31.4% | -0.159 | -1472.0 | 0.76 | 1478.0 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1422 | 33.7% | -0.130 | -184.5 | 0.79 | 199.0 |
| spread/risk cut-off | 1425 | 836 | 39.4% | -0.074 | -62.2 | 0.86 | 75.9 |
| model | 359 | 204 | 38.7% | -0.064 | -13.1 | 0.88 | 19.2 |

## Same fold models on Exness prices (2023-11-24 .. 2026-11-13), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 4001 | 2258 | 34.4% | -0.084 | -189.9 | 0.87 | 202.4 |
| ict_engine-style (killzone, session/day pools) | 537 | 306 | 32.4% | -0.165 | -50.5 | 0.75 | 54.5 |
| spread/risk cut-off | 1013 | 589 | 34.0% | -0.117 | -68.7 | 0.82 | 80.7 |
| model | 0 | 0 | - | - | 0.0 | - | 0.0 |

## Model by fold

| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -90.1 |
| 2014-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -102.1 |
| 2015-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -75.8 |
| 2015-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -92.9 |
| 2016-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -87.8 |
| 2016-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -89.7 |
| 2017-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -94.0 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -38.7 |
| 2018-01-01 | 0.345 | 160 | 155 | 86 | 40.7% | -0.071 | -6.1 | 0.87 | 10.7 | -99.9 |
| 2018-07-01 | 0.359 | 172 | 117 | 68 | 36.8% | -0.194 | -13.2 | 0.66 | 15.7 | -119.4 |
| 2019-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -128.2 |
| 2019-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -95.6 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -80.5 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -62.2 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -56.8 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -113.2 |
| 2022-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -71.2 |
| 2022-07-01 | 0.387 | 176 | 87 | 50 | 38.0% | -0.042 | -2.1 | 0.92 | 8.3 | -73.8 |
| 2023-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -56.0 |
| 2023-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -62.6 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -120.1 |
| 2024-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -80.4 |
| 2025-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -86.9 |
| 2025-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -36.1 |
| 2026-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -54.1 |
| 2026-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -32.8 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2018 | 272 | 154 | 39.0% | -0.125 | -19.3 | 0.78 | 21.8 |
| 2022 | 87 | 50 | 38.0% | -0.042 | -2.1 | 0.92 | 8.3 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 61 | 36 | 38.9% | -0.032 | -1.1 | 0.95 | 8.1 |
| close | 12 | 6 | 33.3% | -0.548 | -3.3 | 0.24 | 3.4 |
| london_kz | 16 | 6 | 33.3% | -0.037 | -0.2 | 0.95 | 3.2 |
| london_mid | 23 | 18 | 44.4% | +0.246 | +4.4 | 1.48 | 3.6 |
| ny_am_kz | 130 | 71 | 35.2% | -0.183 | -13.0 | 0.70 | 14.6 |
| ny_mid | 70 | 39 | 41.0% | -0.234 | -9.1 | 0.53 | 12.2 |
| ny_pm | 47 | 28 | 42.9% | +0.033 | +0.9 | 1.09 | 3.1 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 180 | 93 | 38.7% | -0.091 | -8.5 | 0.84 | 20.5 |
| SELL | 179 | 111 | 38.7% | -0.117 | -13.0 | 0.78 | 15.4 |

## Model by era

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2020 on | 87 | 50 | 38.0% | -0.042 | -2.1 | 0.92 | 8.3 |
| before 2020 | 272 | 154 | 39.0% | -0.125 | -19.3 | 0.78 | 21.8 |

## Calibration (filled test trades, probability deciles)

| predicted | actual win | trades | exp R |
|---|---|---|---|
| 0.209 | 0.204 | 995 | -0.579 |
| 0.262 | 0.264 | 994 | -0.322 |
| 0.283 | 0.295 | 994 | -0.239 |
| 0.298 | 0.283 | 994 | -0.256 |
| 0.310 | 0.298 | 995 | -0.216 |
| 0.322 | 0.300 | 994 | -0.226 |
| 0.335 | 0.347 | 994 | -0.114 |
| 0.350 | 0.358 | 994 | -0.137 |
| 0.370 | 0.377 | 994 | -0.087 |
| 0.411 | 0.403 | 995 | -0.119 |
