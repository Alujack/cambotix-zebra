# XAUUSD ICT model walk-forward (2026-11-21 11:05 UTC)

Dataset `xauusd_ict_rr15.parquet`: 26,879 resolved candidates (15,642 filled), 2008-01-02 .. 2026-11-20. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (26 folds); one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.028R, PF 0.94 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.056R vs model -0.028R; AUC 0.546 vs control 0.503 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 years positive | 3 of 6 traded folds positive (26 folds in all); last 2 years -6.3R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 24.4R, 32 trades a year | no |
| 5 | holds on Exness prices and spreads (same fold models) | > +0.10R per trade and PF > 1.2 | 191 trades, -0.013R, PF 0.97 | no |

The model does not go to a forward test. ml/predict.py refuses this model unless run with --allow-failed-gates (research only).

Out-of-sample AUC on filled trades: **0.546** (shuffled-label control 0.503; 0.5 = no skill).

## Out-of-sample result, net R (all folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 16960 | 9932 | 36.4% | -0.192 | -1908.9 | 0.70 | 1916.4 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1546 | 38.5% | -0.130 | -201.3 | 0.78 | 212.9 |
| spread/risk cut-off | 1717 | 1114 | 40.9% | -0.090 | -100.7 | 0.82 | 106.7 |
| model | 615 | 407 | 45.5% | -0.028 | -11.4 | 0.94 | 24.4 |
| model, shuffled-label control | 248 | 136 | 39.7% | -0.056 | -7.6 | 0.91 | 19.5 |

Gross R (spread only, no slippage):

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 16960 | 9932 | 36.4% | -0.138 | -1369.7 | 0.77 | 1377.2 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1546 | 38.5% | -0.093 | -143.3 | 0.83 | 156.6 |
| spread/risk cut-off | 1717 | 1114 | 40.9% | -0.068 | -76.2 | 0.86 | 82.2 |
| model | 615 | 407 | 45.5% | -0.002 | -1.0 | 0.99 | 18.9 |

## Same fold models on Exness prices (2023-11-24 .. 2026-11-13), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 4010 | 2396 | 40.0% | -0.061 | -145.9 | 0.89 | 150.7 |
| ict_engine-style (killzone, session/day pools) | 537 | 337 | 39.8% | -0.067 | -22.7 | 0.88 | 25.9 |
| spread/risk cut-off | 2324 | 1464 | 40.8% | -0.044 | -64.3 | 0.92 | 70.8 |
| model | 306 | 191 | 44.0% | -0.013 | -2.6 | 0.97 | 18.3 |

## Model by fold

| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -76.5 |
| 2014-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -108.8 |
| 2015-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -63.6 |
| 2015-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -81.9 |
| 2016-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -77.1 |
| 2016-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -78.1 |
| 2017-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -83.4 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -34.1 |
| 2018-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -86.6 |
| 2018-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -101.3 |
| 2019-01-01 | 0.401 | 198 | 111 | 72 | 44.4% | +0.027 | +2.0 | 1.06 | 10.5 | -103.5 |
| 2019-07-01 | 0.400 | 210 | 172 | 113 | 40.7% | -0.162 | -18.3 | 0.71 | 19.9 | -99.9 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -62.9 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -51.0 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -44.3 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -91.0 |
| 2022-01-01 | 0.422 | 182 | 65 | 50 | 58.0% | +0.245 | +12.2 | 1.89 | 2.8 | -94.3 |
| 2022-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -82.6 |
| 2023-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -50.3 |
| 2023-07-01 | 0.412 | 207 | 52 | 42 | 45.2% | -0.187 | -7.8 | 0.61 | 7.8 | -62.7 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -114.3 |
| 2024-07-01 | 0.418 | 224 | 77 | 54 | 53.7% | +0.189 | +10.2 | 1.54 | 5.5 | -61.9 |
| 2025-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -75.9 |
| 2025-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -49.7 |
| 2026-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -36.8 |
| 2026-07-01 | 0.406 | 389 | 138 | 76 | 39.5% | -0.126 | -9.6 | 0.76 | 11.6 | -36.5 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2019 | 283 | 185 | 42.2% | -0.088 | -16.4 | 0.83 | 24.1 |
| 2022 | 65 | 50 | 58.0% | +0.245 | +12.2 | 1.89 | 2.8 |
| 2023 | 52 | 42 | 45.2% | -0.187 | -7.8 | 0.61 | 7.8 |
| 2024 | 77 | 54 | 53.7% | +0.189 | +10.2 | 1.54 | 5.5 |
| 2026 | 138 | 76 | 39.5% | -0.126 | -9.6 | 0.76 | 11.6 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 123 | 85 | 50.6% | +0.076 | +6.5 | 1.16 | 11.7 |
| close | 14 | 10 | 30.0% | -0.582 | -5.8 | 0.26 | 5.8 |
| london_kz | 60 | 38 | 39.5% | -0.050 | -1.9 | 0.92 | 5.4 |
| london_mid | 34 | 29 | 48.3% | +0.090 | +2.6 | 1.17 | 5.3 |
| ny_am_kz | 233 | 148 | 44.6% | -0.008 | -1.2 | 0.98 | 13.8 |
| ny_mid | 106 | 76 | 50.0% | -0.091 | -6.9 | 0.73 | 13.2 |
| ny_pm | 45 | 21 | 28.6% | -0.223 | -4.7 | 0.46 | 4.7 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 311 | 185 | 45.4% | -0.046 | -8.5 | 0.90 | 11.3 |
| SELL | 304 | 222 | 45.5% | -0.013 | -2.9 | 0.97 | 20.7 |

## Model by era

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2020 on | 332 | 222 | 48.2% | +0.023 | +5.0 | 1.05 | 12.1 |
| before 2020 | 283 | 185 | 42.2% | -0.088 | -16.4 | 0.83 | 24.1 |

## Calibration (filled test trades, probability deciles)

| predicted | actual win | trades | exp R |
|---|---|---|---|
| 0.281 | 0.285 | 1071 | -0.425 |
| 0.319 | 0.345 | 1071 | -0.225 |
| 0.336 | 0.340 | 1071 | -0.248 |
| 0.348 | 0.336 | 1071 | -0.253 |
| 0.358 | 0.354 | 1071 | -0.209 |
| 0.369 | 0.370 | 1070 | -0.142 |
| 0.379 | 0.360 | 1071 | -0.182 |
| 0.391 | 0.399 | 1071 | -0.105 |
| 0.406 | 0.418 | 1071 | -0.087 |
| 0.434 | 0.423 | 1071 | -0.068 |
