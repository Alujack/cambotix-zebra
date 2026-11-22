# XAUUSD forecast check (2026-11-22 00:43 UTC)

Development gold only (nothing from 2024-11-20 on is loaded). LightGBM regression on 37 inputs from closed M5 bars. Trained 2011-01-01 to 2018-01-01, stopped early on 2018-01-01 to 2019-01-01, judged on 2019-01-01 to 2024-11-20. The target is the move of the mid price from the next bar to 240 or 480 minutes later, in ATR of M5. A target never crosses the daily break or a weekend.

## Next 240 minutes

425,548 training bars, 344,640 test bars, 243 rounds. Rank correlation between forecast and outcome on the test years: **+0.0022** (0 = no skill).

Median spread on the test years: 0.322 ATR ($0.34 per oz). A trade has to beat that.

| Forecast tenth | Mean forecast (ATR) | Mean real move (ATR) | Mean real move ($ per oz) |
|---|---|---|---|
| lowest | -0.5333 | +0.0624 | +0.082 |
| 2 | -0.2896 | +0.1464 | +0.087 |
| 3 | -0.2009 | +0.1004 | +0.054 |
| 4 | -0.1442 | +0.2071 | +0.199 |
| 5 | -0.0885 | +0.1853 | +0.102 |
| 6 | -0.0306 | +0.2447 | +0.165 |
| 7 | +0.0293 | +0.1271 | -0.044 |
| 8 | +0.1018 | +0.1599 | +0.001 |
| 9 | +0.2031 | -0.0352 | -0.216 |
| highest | +0.4333 | +0.2341 | +0.106 |

Best tenth: $0.106 per oz before costs, against a spread of $0.34: **31% of the cost.**

Most used inputs: hour 16%, round_50 9%, ret_288 8%, prev_day_high 7%, prev_day_low 7%, weekday 5%.

## Next 480 minutes

350,514 training bars, 271,656 test bars, 352 rounds. Rank correlation between forecast and outcome on the test years: **+0.0026** (0 = no skill).

Median spread on the test years: 0.365 ATR ($0.35 per oz). A trade has to beat that.

| Forecast tenth | Mean forecast (ATR) | Mean real move (ATR) | Mean real move ($ per oz) |
|---|---|---|---|
| lowest | -1.0568 | -0.1618 | -0.326 |
| 2 | -0.6370 | +0.5227 | +0.341 |
| 3 | -0.4715 | +0.3948 | +0.311 |
| 4 | -0.3621 | +0.3392 | +0.111 |
| 5 | -0.2748 | +0.4467 | +0.287 |
| 6 | -0.1892 | +0.2309 | +0.135 |
| 7 | -0.0991 | +0.1742 | -0.058 |
| 8 | +0.0052 | +0.0890 | -0.232 |
| 9 | +0.1497 | +0.4106 | +0.217 |
| highest | +0.4986 | +0.7007 | +0.164 |

Best tenth: $0.326 per oz before costs, against a spread of $0.35: **94% of the cost.**

Most used inputs: round_50 13%, hour 9%, prev_day_high 7%, prev_day_close 7%, weekday 7%, day_low 6%.
