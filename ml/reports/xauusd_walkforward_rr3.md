# XAUUSD ICT model walk-forward (2026-11-21 11:06 UTC)

Dataset `xauusd_ict_rr3.parquet`: 26,879 resolved candidates (17,736 filled), 2008-01-02 .. 2026-11-20. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (26 folds); one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.134R, PF 0.77 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.061R vs model -0.134R; AUC 0.610 vs control 0.500 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 years positive | 0 of 4 traded folds positive (26 folds in all); last 2 years +0.0R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 71.7R, 37 trades a year | no |
| 5 | holds on Exness prices and spreads (same fold models) | > +0.10R per trade and PF > 1.2 | 0 trades | no |

The model does not go to a forward test. ml/predict.py refuses this model unless run with --allow-failed-gates (research only).

Out-of-sample AUC on filled trades: **0.610** (shuffled-label control 0.500; 0.5 = no skill).

## Out-of-sample result, net R (all folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 16482 | 10983 | 28.4% | -0.227 | -2490.5 | 0.69 | 2499.3 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1737 | 31.5% | -0.167 | -290.1 | 0.75 | 300.7 |
| spread/risk cut-off | 1512 | 1012 | 40.1% | -0.061 | -61.7 | 0.88 | 85.9 |
| model | 747 | 481 | 37.8% | -0.134 | -64.2 | 0.77 | 71.7 |
| model, shuffled-label control | 242 | 163 | 31.3% | -0.160 | -26.1 | 0.78 | 32.8 |

Gross R (spread only, no slippage):

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 16482 | 10983 | 28.4% | -0.158 | -1734.1 | 0.77 | 1742.9 |
| ict_engine-style (killzone, session/day pools) | 2646 | 1737 | 31.5% | -0.118 | -205.2 | 0.81 | 218.0 |
| spread/risk cut-off | 1512 | 1012 | 40.1% | -0.037 | -37.9 | 0.92 | 65.2 |
| model | 747 | 481 | 37.8% | -0.097 | -46.6 | 0.82 | 59.9 |

## Same fold models on Exness prices (2023-11-24 .. 2026-11-13), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 3860 | 2658 | 31.6% | -0.069 | -183.3 | 0.90 | 188.8 |
| ict_engine-style (killzone, session/day pools) | 537 | 371 | 33.7% | -0.072 | -26.7 | 0.88 | 33.1 |
| spread/risk cut-off | 2004 | 1392 | 32.3% | -0.080 | -110.8 | 0.88 | 113.2 |
| model | 0 | 0 | - | - | 0.0 | - | 0.0 |

## Model by fold

| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -106.9 |
| 2014-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -141.0 |
| 2015-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -125.6 |
| 2015-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -90.0 |
| 2016-01-01 | 0.291 | 331 | 314 | 195 | 38.5% | -0.018 | -3.4 | 0.97 | 15.6 | -60.5 |
| 2016-07-01 | 0.337 | 155 | 146 | 96 | 34.4% | -0.230 | -22.1 | 0.59 | 24.1 | -104.0 |
| 2017-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -127.4 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -69.2 |
| 2018-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -97.1 |
| 2018-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -123.5 |
| 2019-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -148.5 |
| 2019-07-01 | 0.343 | 239 | 187 | 123 | 38.2% | -0.216 | -26.6 | 0.62 | 26.6 | -118.9 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -99.1 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -68.5 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -62.4 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -153.5 |
| 2022-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -94.0 |
| 2022-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -96.6 |
| 2023-01-01 | 0.392 | 226 | 100 | 67 | 40.3% | -0.181 | -12.2 | 0.64 | 15.0 | -81.2 |
| 2023-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -100.8 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -123.6 |
| 2024-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -101.2 |
| 2025-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -83.7 |
| 2025-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -57.4 |
| 2026-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -11.8 |
| 2026-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -44.1 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2016 | 460 | 291 | 37.1% | -0.088 | -25.5 | 0.85 | 32.9 |
| 2019 | 187 | 123 | 38.2% | -0.216 | -26.6 | 0.62 | 26.6 |
| 2023 | 100 | 67 | 40.3% | -0.181 | -12.2 | 0.64 | 15.0 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 117 | 72 | 37.5% | -0.103 | -7.4 | 0.84 | 12.2 |
| close | 51 | 31 | 29.0% | -0.377 | -11.7 | 0.46 | 14.3 |
| london_kz | 45 | 35 | 34.3% | -0.186 | -6.5 | 0.72 | 16.1 |
| london_mid | 46 | 36 | 38.9% | +0.004 | +0.1 | 1.01 | 8.2 |
| ny_am_kz | 259 | 172 | 37.2% | -0.088 | -15.1 | 0.84 | 21.9 |
| ny_mid | 139 | 85 | 38.8% | -0.242 | -20.6 | 0.51 | 21.0 |
| ny_pm | 90 | 50 | 46.0% | -0.061 | -3.0 | 0.87 | 9.8 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 357 | 210 | 37.1% | -0.163 | -34.3 | 0.71 | 35.5 |
| SELL | 390 | 271 | 38.4% | -0.110 | -29.9 | 0.81 | 48.4 |

## Model by era

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2020 on | 100 | 67 | 40.3% | -0.181 | -12.2 | 0.64 | 15.0 |
| before 2020 | 647 | 414 | 37.4% | -0.126 | -52.1 | 0.78 | 59.5 |

## Calibration (filled test trades, probability deciles)

| predicted | actual win | trades | exp R |
|---|---|---|---|
| 0.166 | 0.165 | 1217 | -0.519 |
| 0.208 | 0.191 | 1217 | -0.391 |
| 0.231 | 0.227 | 1217 | -0.250 |
| 0.250 | 0.250 | 1217 | -0.209 |
| 0.268 | 0.260 | 1217 | -0.234 |
| 0.288 | 0.279 | 1217 | -0.219 |
| 0.311 | 0.317 | 1217 | -0.158 |
| 0.337 | 0.324 | 1217 | -0.165 |
| 0.368 | 0.398 | 1217 | -0.037 |
| 0.417 | 0.418 | 1217 | -0.087 |
