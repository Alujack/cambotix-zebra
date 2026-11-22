# XAUUSD forecast check (2026-11-22 00:42 UTC)

Development gold only (nothing from 2024-11-20 on is loaded). LightGBM regression on 37 inputs from closed M5 bars. Trained 2011-01-01 to 2018-01-01, stopped early on 2018-01-01 to 2019-01-01, judged on 2019-01-01 to 2024-11-20. The target is the move of the mid price from the next bar to 30 or 60 minutes later, in ATR of M5.

## Next 30 minutes

491,742 training bars, 408,578 test bars, 62 rounds. Rank correlation between forecast and outcome on the test years: **+0.0356** (0 = no skill).

Median spread on the test years: 0.319 ATR ($0.34 per oz). A trade has to beat that.

| Forecast tenth | Mean forecast (ATR) | Mean real move (ATR) | Mean real move ($ per oz) |
|---|---|---|---|
| lowest | -0.1199 | -0.0336 | -0.037 |
| 2 | -0.0789 | -0.0060 | -0.014 |
| 3 | -0.0558 | +0.0083 | +0.009 |
| 4 | -0.0380 | +0.0135 | +0.011 |
| 5 | -0.0231 | +0.0132 | +0.003 |
| 6 | -0.0075 | +0.0031 | +0.014 |
| 7 | +0.0151 | +0.0125 | +0.002 |
| 8 | +0.0457 | -0.0004 | -0.023 |
| 9 | +0.0772 | +0.0324 | +0.018 |
| highest | +0.1351 | +0.0789 | +0.084 |

Best tenth: $0.084 per oz before costs, against a spread of $0.34: **25% of the cost.**

Most used inputs: rsi_14 38%, hour 9%, z_sma_20 9%, to_high_48 4%, pos_288 3%, pos_48 3%.

## Next 60 minutes

482,132 training bars, 399,434 test bars, 45 rounds. Rank correlation between forecast and outcome on the test years: **+0.0288** (0 = no skill).

Median spread on the test years: 0.317 ATR ($0.34 per oz). A trade has to beat that.

| Forecast tenth | Mean forecast (ATR) | Mean real move (ATR) | Mean real move ($ per oz) |
|---|---|---|---|
| lowest | -0.1066 | +0.0027 | +0.011 |
| 2 | -0.0830 | +0.0020 | -0.014 |
| 3 | -0.0605 | +0.0074 | +0.005 |
| 4 | -0.0414 | +0.0596 | +0.045 |
| 5 | -0.0273 | +0.0152 | +0.015 |
| 6 | -0.0112 | +0.0063 | -0.041 |
| 7 | +0.0136 | +0.0246 | +0.015 |
| 8 | +0.0408 | -0.0156 | -0.067 |
| 9 | +0.0698 | +0.0656 | +0.038 |
| highest | +0.1202 | +0.1265 | +0.138 |

Best tenth: $0.138 per oz before costs, against a spread of $0.34: **41% of the cost.**

Most used inputs: rsi_14 33%, hour 15%, z_sma_20 6%, to_high_48 4%, day_low 3%, pos_288 3%.
