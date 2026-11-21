# XAUUSD ICT model walk-forward (2026-11-21 11:07 UTC)

Dataset `xauusd_ict_market.parquet`: 26,880 resolved candidates (26,878 filled), 2008-01-02 .. 2026-11-20. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (26 folds); one-day embargo; thresholds chosen on the last 20% of each training window only. Net R = after spread (in the grade) and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.156R, PF 0.64 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.050R vs model -0.156R; AUC 0.550 vs control 0.496 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 years positive | 0 of 1 traded folds positive (26 folds in all); last 2 years +0.0R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 14.0R, 6 trades a year | no |
| 5 | holds on Exness prices and spreads (same fold models) | > +0.10R per trade and PF > 1.2 | 0 trades | no |

The model does not go to a forward test. ml/predict.py refuses this model unless run with --allow-failed-gates (research only).

Out-of-sample AUC on filled trades: **0.550** (shuffled-label control 0.496; 0.5 = no skill).

## Out-of-sample result, net R (all folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 15438 | 15436 | 37.1% | -0.154 | -2379.8 | 0.73 | 2385.5 |
| ict_engine-style (killzone, session/day pools) | 2645 | 2645 | 39.1% | -0.121 | -319.6 | 0.77 | 324.7 |
| spread/risk cut-off | 1672 | 1672 | 43.2% | -0.050 | -83.1 | 0.89 | 90.9 |
| model | 77 | 77 | 39.0% | -0.156 | -12.0 | 0.64 | 14.0 |
| model, shuffled-label control | 0 | 0 | - | - | 0.0 | - | 0.0 |

Gross R (spread only, no slippage):

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 15438 | 15436 | 37.1% | -0.112 | -1735.5 | 0.79 | 1741.1 |
| ict_engine-style (killzone, session/day pools) | 2645 | 2645 | 39.1% | -0.091 | -239.9 | 0.82 | 247.3 |
| spread/risk cut-off | 1672 | 1672 | 43.2% | -0.035 | -59.1 | 0.92 | 67.4 |
| model | 77 | 77 | 39.0% | -0.127 | -9.8 | 0.70 | 12.0 |

## Same fold models on Exness prices (2023-11-24 .. 2026-11-13), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all candidates | 3633 | 3632 | 39.8% | -0.046 | -168.4 | 0.91 | 181.7 |
| ict_engine-style (killzone, session/day pools) | 537 | 537 | 40.6% | -0.073 | -39.4 | 0.85 | 45.4 |
| spread/risk cut-off | 2340 | 2339 | 41.0% | -0.031 | -73.0 | 0.94 | 93.5 |
| model | 0 | 0 | - | - | 0.0 | - | 0.0 |

## Model by fold

| fold | threshold | val trades | signals | filled | win | exp R | total R | PF | max DD R | all candidates R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -112.3 |
| 2014-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -128.4 |
| 2015-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -91.5 |
| 2015-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -86.4 |
| 2016-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -62.1 |
| 2016-07-01 | 0.430 | 158 | 77 | 77 | 39.0% | -0.156 | -12.0 | 0.64 | 14.0 | -130.2 |
| 2017-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -77.1 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -76.8 |
| 2018-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -83.4 |
| 2018-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -114.7 |
| 2019-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -135.9 |
| 2019-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -113.5 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -124.0 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -65.7 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -72.2 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -123.0 |
| 2022-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -89.0 |
| 2022-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -112.1 |
| 2023-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -49.4 |
| 2023-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -104.7 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -76.2 |
| 2024-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -97.5 |
| 2025-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -79.2 |
| 2025-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -72.9 |
| 2026-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -37.4 |
| 2026-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -64.3 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2016 | 77 | 77 | 39.0% | -0.156 | -12.0 | 0.64 | 14.0 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 33 | 33 | 39.4% | -0.160 | -5.3 | 0.63 | 7.3 |
| close | 6 | 6 | 50.0% | +0.057 | +0.3 | 1.13 | 1.7 |
| london_kz | 3 | 3 | 0.0% | -0.744 | -2.2 | 0.00 | 2.2 |
| london_mid | 5 | 5 | 40.0% | -0.175 | -0.9 | 0.72 | 3.1 |
| ny_am_kz | 17 | 17 | 41.2% | -0.024 | -0.4 | 0.93 | 3.6 |
| ny_mid | 9 | 9 | 33.3% | -0.274 | -2.5 | 0.27 | 3.4 |
| ny_pm | 4 | 4 | 50.0% | -0.278 | -1.1 | 0.46 | 2.1 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 33 | 33 | 48.5% | -0.009 | -0.3 | 0.98 | 3.9 |
| SELL | 44 | 44 | 31.8% | -0.267 | -11.7 | 0.44 | 12.6 |

## Model by era

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| before 2020 | 77 | 77 | 39.0% | -0.156 | -12.0 | 0.64 | 14.0 |

## Calibration (filled test trades, probability deciles)

| predicted | actual win | trades | exp R |
|---|---|---|---|
| 0.294 | 0.276 | 1827 | -0.373 |
| 0.326 | 0.334 | 1827 | -0.227 |
| 0.340 | 0.352 | 1826 | -0.150 |
| 0.351 | 0.371 | 1827 | -0.110 |
| 0.361 | 0.361 | 1826 | -0.160 |
| 0.371 | 0.365 | 1827 | -0.149 |
| 0.381 | 0.388 | 1826 | -0.089 |
| 0.392 | 0.395 | 1827 | -0.115 |
| 0.407 | 0.404 | 1826 | -0.106 |
| 0.435 | 0.444 | 1827 | -0.068 |
