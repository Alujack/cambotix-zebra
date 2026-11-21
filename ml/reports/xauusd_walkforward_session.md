# XAUUSD ICT model walk-forward (2026-11-21 11:07 UTC)

Dataset `xauusd_ict.parquet` (session/day pools only): 10,505 resolved candidates (6,668 filled), 2008-01-02 .. 2026-11-20. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (20 folds); one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.041R, PF 0.92 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.086R vs model -0.041R; AUC 0.576 vs control 0.489 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 years positive | 1 of 3 traded folds positive (20 folds in all); last 2 years +0.0R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 15.2R, 18 trades a year | no |
| 5 | holds on Exness prices and spreads (same fold models) | > +0.10R per trade and PF > 1.2 | 0 trades | no |

The model does not go to a forward test. ml/predict.py refuses this model unless run with --allow-failed-gates (research only).

Out-of-sample AUC on filled trades: **0.576** (shuffled-label control 0.489; 0.5 = no skill).

## Out-of-sample result, net R (all folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 5500 | 3542 | 32.5% | -0.231 | -816.8 | 0.66 | 829.3 |
| ict_engine-style (killzone, session/day pools) | 2003 | 1245 | 32.9% | -0.209 | -260.7 | 0.68 | 264.0 |
| spread/risk cut-off | 183 | 115 | 42.6% | -0.086 | -9.9 | 0.83 | 16.0 |
| model | 270 | 173 | 45.1% | -0.041 | -7.0 | 0.92 | 15.2 |
| model, shuffled-label control | 0 | 0 | - | - | 0.0 | - | 0.0 |

Gross R (spread only, no slippage):

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 5500 | 3542 | 32.5% | -0.181 | -640.9 | 0.71 | 654.2 |
| ict_engine-style (killzone, session/day pools) | 2003 | 1245 | 32.9% | -0.168 | -208.8 | 0.73 | 212.4 |
| spread/risk cut-off | 183 | 115 | 42.6% | -0.065 | -7.4 | 0.87 | 15.1 |
| model | 270 | 173 | 45.1% | +0.001 | +0.1 | 1.00 | 13.7 |

## Same fold models on Exness prices (2023-11-27 .. 2026-11-13), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 1647 | 1108 | 37.4% | -0.046 | -50.6 | 0.92 | 90.3 |
| ict_engine-style (killzone, session/day pools) | 537 | 358 | 34.9% | -0.106 | -37.8 | 0.83 | 42.0 |
| spread/risk cut-off | 503 | 341 | 39.3% | +0.013 | +4.5 | 1.02 | 33.4 |
| model | 0 | 0 | - | - | 0.0 | - | 0.0 |

## Model by fold

| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2017-01-01 | 0.361 | 165 | 116 | 71 | 40.8% | -0.058 | -4.1 | 0.90 | 15.2 | -37.6 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -35.5 |
| 2018-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -28.2 |
| 2018-07-01 | 0.374 | 155 | 78 | 50 | 54.0% | +0.042 | +2.1 | 1.10 | 7.5 | -53.0 |
| 2019-01-01 | 0.369 | 167 | 76 | 52 | 42.3% | -0.097 | -5.0 | 0.78 | 13.1 | -67.4 |
| 2019-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -39.3 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -67.4 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -24.9 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -36.9 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -51.0 |
| 2022-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -57.4 |
| 2022-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -53.0 |
| 2023-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -33.4 |
| 2023-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -36.0 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -54.4 |
| 2024-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -41.8 |
| 2025-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -47.4 |
| 2025-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -5.4 |
| 2026-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -13.2 |
| 2026-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -33.5 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2017 | 116 | 71 | 40.8% | -0.058 | -4.1 | 0.90 | 15.2 |
| 2018 | 78 | 50 | 54.0% | +0.042 | +2.1 | 1.10 | 7.5 |
| 2019 | 76 | 52 | 42.3% | -0.097 | -5.0 | 0.78 | 13.1 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 17 | 12 | 25.0% | -0.560 | -6.7 | 0.24 | 6.7 |
| close | 6 | 4 | 50.0% | -0.330 | -1.3 | 0.40 | 1.3 |
| london_kz | 22 | 9 | 44.4% | -0.254 | -2.3 | 0.56 | 3.6 |
| london_mid | 34 | 27 | 48.1% | +0.105 | +2.8 | 1.19 | 6.5 |
| ny_am_kz | 105 | 65 | 47.7% | +0.130 | +8.5 | 1.29 | 5.3 |
| ny_mid | 49 | 35 | 48.6% | -0.099 | -3.5 | 0.76 | 5.9 |
| ny_pm | 37 | 21 | 38.1% | -0.214 | -4.5 | 0.63 | 8.2 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 124 | 74 | 45.9% | -0.127 | -9.4 | 0.76 | 14.2 |
| SELL | 146 | 99 | 44.4% | +0.024 | +2.4 | 1.05 | 10.4 |

## Model by era

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| before 2020 | 270 | 173 | 45.1% | -0.041 | -7.0 | 0.92 | 15.2 |

## Calibration (filled test trades, probability deciles)

| predicted | actual win | trades | exp R |
|---|---|---|---|
| 0.240 | 0.252 | 357 | -0.361 |
| 0.275 | 0.278 | 356 | -0.282 |
| 0.297 | 0.275 | 356 | -0.286 |
| 0.318 | 0.250 | 356 | -0.358 |
| 0.336 | 0.303 | 356 | -0.226 |
| 0.354 | 0.326 | 356 | -0.245 |
| 0.372 | 0.340 | 356 | -0.191 |
| 0.392 | 0.410 | 356 | -0.082 |
| 0.418 | 0.402 | 356 | -0.160 |
| 0.468 | 0.413 | 356 | -0.101 |
