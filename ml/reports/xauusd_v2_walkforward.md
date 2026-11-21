# XAUUSD ICT model v2: development walk-forward (2026-11-21 11:59 UTC)

Development data only (`xauusd_ict_dev.parquet`, ends before 2024-11-20; the lockbox is unread). 23,476 tradable resolved candidates (14,609 filled), 2008-01-02 .. 2024-11-19. Training from 2011-01-01; test folds of 6 months from 2014-01-01 (22 folds); one-day embargo; cut chosen on the last 20% of each training window. Net R = after spread and 0.5 x spread slippage on stop and time exits.

## Gates: **FAILED**

| # | Gate | Required | Measured | Pass |
|---|---|---|---|---|
| 1 | expectancy and profit factor after spread and slippage | > +0.10R per trade and PF > 1.2 | -0.229R, PF 0.64 | no |
| 2 | beats every baseline and the shuffled control | +0.05R per trade over each, AUC +0.02 over control | best other -0.043R vs model -0.229R; AUC 0.597 vs control 0.495 | no |
| 3 | consistent across folds and recent | >= 60% of folds positive, last 2 development years positive | 0 of 1 traded folds positive (22 folds in all); last 2 years -12.4R | no |
| 4 | drawdown and enough trades | max drawdown <= 15R, >= 100 trades a year | max drawdown 14.3R, 5 trades a year | no |
| 5 | holds on broker prices with Dukascopy's spread (same fold models) | expectancy > +0.00R | 0 trades | no |

The development gates failed, so by plan v2 the work stops here: the lockbox stays closed, there is no forward test and no further v2 variant.

AUC of P(target) on filled test trades: **0.597** (shuffled-outcome control 0.495; 0.5 = no skill).

## Out-of-sample result, net R (all development folds)

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all tradable candidates | 13831 | 8670 | 31.7% | -0.229 | -1989.6 | 0.68 | 1993.0 |
| ict_engine-style (killzone, session/day pools) | 2197 | 1360 | 33.9% | -0.181 | -246.1 | 0.72 | 256.2 |
| spread/risk cut-off | 902 | 600 | 40.5% | -0.043 | -25.9 | 0.91 | 48.0 |
| model | 95 | 54 | 33.3% | -0.229 | -12.4 | 0.64 | 14.3 |
| model, shuffled-outcome control | 0 | 0 | - | - | 0.0 | - | 0.0 |

Sensitivity only (decides nothing): the model's chosen setups graded with half the spread:

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| model, spread halved | 95 | 56 | 37.5% | -0.158 | -8.8 | 0.74 | 10.9 |

## Same fold models on broker prices with Dukascopy's spread (2023-11-24 .. 2024-11-19), net R

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| all tradable candidates | 1259 | 782 | 30.9% | -0.235 | -184.1 | 0.67 | 189.2 |
| ict_engine-style (killzone, session/day pools) | 173 | 112 | 32.1% | -0.149 | -16.7 | 0.78 | 20.6 |
| spread/risk cut-off | 0 | 0 | - | - | 0.0 | - | 0.0 |
| model | 0 | 0 | - | - | 0.0 | - | 0.0 |

## Predicted against realised (filled test trades, tenths of expected R)

| Predicted R | Realised net R | Trades | Target | Stop | Timeout |
|---|---|---|---|---|---|
| -0.568 | -0.458 | 944 | 20.2% | 74.6% | 5.2% |
| -0.438 | -0.331 | 943 | 21.3% | 71.4% | 7.3% |
| -0.367 | -0.206 | 944 | 24.3% | 66.9% | 8.8% |
| -0.308 | -0.300 | 943 | 21.5% | 69.1% | 9.3% |
| -0.254 | -0.205 | 944 | 22.1% | 63.9% | 14.0% |
| -0.204 | -0.193 | 943 | 21.2% | 61.5% | 17.3% |
| -0.151 | -0.182 | 943 | 19.9% | 58.7% | 21.3% |
| -0.095 | -0.172 | 944 | 17.6% | 54.8% | 27.6% |
| -0.028 | -0.189 | 943 | 15.5% | 51.6% | 32.9% |
| +0.098 | -0.071 | 944 | 19.5% | 49.8% | 30.7% |

Cross-check: rank correlation between the expected-R score and a direct regression of net R, on validation, averages 0.75 over 22 folds; never under 0.5.

## Model by fold

| fold | cut (expected R) | val trades | signals | filled | win | exp R | total R | PF | max DD R | all tradable R |
|---|---|---|---|---|---|---|---|---|---|---|
| 2014-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -85.1 |
| 2014-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -111.5 |
| 2015-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -93.4 |
| 2015-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -92.5 |
| 2016-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -62.7 |
| 2016-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -84.1 |
| 2017-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -98.7 |
| 2017-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -56.7 |
| 2018-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -91.9 |
| 2018-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -121.7 |
| 2019-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -116.6 |
| 2019-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -113.4 |
| 2020-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -83.8 |
| 2020-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -51.8 |
| 2021-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -63.0 |
| 2021-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -119.1 |
| 2022-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -89.2 |
| 2022-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -84.8 |
| 2023-01-01 | +0.003 | 314 | 95 | 54 | 33.3% | -0.229 | -12.4 | 0.64 | 14.3 | -66.6 |
| 2023-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -97.6 |
| 2024-01-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -121.9 |
| 2024-07-01 | none | 0 | 0 | 0 | - | - | 0.0 | - | 0.0 | -83.2 |

## Model by year

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| 2023 | 95 | 54 | 33.3% | -0.229 | -12.4 | 0.64 | 14.3 |

## Model by session

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| asia | 30 | 16 | 18.8% | -0.492 | -7.9 | 0.38 | 8.8 |
| close | 2 | 1 | 0.0% | -0.391 | -0.4 | 0.00 | 0.4 |
| london_kz | 17 | 7 | 42.9% | +0.019 | +0.1 | 1.03 | 2.2 |
| london_mid | 13 | 9 | 22.2% | -0.369 | -3.3 | 0.55 | 5.3 |
| ny_am_kz | 19 | 12 | 41.7% | -0.084 | -1.0 | 0.86 | 3.9 |
| ny_mid | 9 | 7 | 42.9% | -0.226 | -1.6 | 0.44 | 1.7 |
| ny_pm | 5 | 2 | 100.0% | +0.837 | +1.7 | - | 0.0 |

## Model by side

| | signals | filled | win | exp R | total R | PF | max DD R |
|---|---|---|---|---|---|---|---|
| BUY | 45 | 25 | 36.0% | -0.143 | -3.6 | 0.76 | 5.1 |
| SELL | 50 | 29 | 31.0% | -0.303 | -8.8 | 0.56 | 11.7 |

## Account filter (stop at most $10 at the minimum position)

| Year | Resolved candidates | Removed as untradable |
|---|---|---|
| 2011 | 1639 | 96 |
| 2012 | 1413 | 26 |
| 2013 | 1348 | 33 |
| 2014 | 1441 | 12 |
| 2015 | 1347 | 1 |
| 2016 | 1412 | 11 |
| 2017 | 1328 | 2 |
| 2018 | 1439 | 3 |
| 2019 | 1420 | 8 |
| 2020 | 1400 | 80 |
| 2021 | 1381 | 23 |
| 2022 | 1467 | 39 |
| 2023 | 1394 | 33 |
| 2024 | 1325 | 79 |

## Feature importance (development model, gain; * = new in v2)

| feature | share |
|---|---|
| risk_atr | 14.3% |
| session_now | 14.1% |
| spread_risk | 12.5% |
| ny_hour | 8.6% |
| session_sweep | 2.9% |
| leg_atr | 2.6% |
| atr_ratio_week | 2.6% |
| ote_fib | 2.5% |
| atr_ratio_day | 2.5% |
| h4_swing_behind_atr * | 2.0% |
| weekday | 1.8% |
| asia_range_atr | 1.7% |
| h4_swing_ahead_atr * | 1.6% |
| opp_pool_r | 1.5% |
| leg_max_body_atr | 1.5% |

## Saved development model

`ml/models/xauusd_ict_v2_20241119.models.json`: 12,110 filled trades 2011-01-03 .. 2024-11-19, rounds {'cls': 177, 'timeout': 44}, cut none (no profitable cut on validation: do not trade), gates FAILED.
