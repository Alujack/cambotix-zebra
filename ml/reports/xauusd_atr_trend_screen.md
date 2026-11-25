# XAUUSD ATR Trend Confluence screen (2026-11-25 10:22 UTC)

The indicator on the website (web/trend.py, tradingview/atr_trend_confluence.pine): EMA50 baseline, Supertrend stop ATR 14 x 2.8, a label where the stop flips, filtered. Script defaults, nothing tuned.

Development gold only (Dukascopy M1 2010-06-01 .. 2024-11-19; nothing from 2024-11-20 on is loaded). Discovery 2011-01-01 to 2019-01-01, confirmation 2019-01-01 to 2024-11-20. One position at a time. R = result divided by the stop distance. Numbers are mean R per trade.

Trade, fixed before the run: enter at the M1 open after the signal bar closes; stop at the stop line (at least 1 ATR away); exit either at a 2R target (held at most 4 h on M1, 24 h on M5, 48 h on M15) or, for "trail", when the stop flips back (at most 8 h / 48 h / 120 h).

Pass rule (ml.screen.RULE, unchanged): at zero cost in discovery mean R >= +0.03 with t >= 2 and at least 100 trades; at the recorded spread in discovery mean R > 0; then in confirmation at the recorded spread mean R >= +0.05, profit factor >= 1.15, 60% of years positive and at least 50 trades a year.

**90 tests, 0 passed.**

| Verdict | Tests |
|---|---|
| no edge before costs | 79 |
| too few trades | 8 |
| edge smaller than the spread | 3 |

### M1, 2R target

| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | Every stop flip (the plain Buy/Sell labels) | 4991 | +0.016 (t +2.3) | -0.028 | -0.358 | -0.315 | 0.61 | no edge before costs |
| A0 | 0 + price on the right side of a sloping EMA50 | 4498 | -0.013 (t -1.7) | -0.018 | -0.393 | -0.322 | 0.60 | no edge before costs |
| A | A0 + within 1 ATR of the EMA50 (the script with every toggle off) | 2496 | +0.021 (t +2.0) | -0.013 | -0.367 | -0.319 | 0.60 | no edge before costs |
| B | A + 1h EMA50/200 trend | 969 | +0.023 (t +1.4) | +0.009 | -0.366 | -0.310 | 0.62 | no edge before costs |
| C | B + Choppiness below 55 | 868 | +0.028 (t +1.7) | +0.003 | -0.362 | -0.318 | 0.61 | no edge before costs |
| D | C + ADX at least 20 with DI on side | 431 | -0.004 (t -0.1) | -0.004 | -0.366 | -0.293 | 0.64 | no edge before costs |
| E | D + break of structure in the last 8 bars | 271 | -0.007 (t -0.2) | -0.005 | -0.372 | -0.299 | 0.63 | no edge before costs |
| F | E + London / New York morning | 90 | +0.073 (t +1.4) | -0.029 | -0.181 | -0.276 | 0.65 | no edge before costs |
| site | As on the website: F without the structure filter | 143 | +0.068 (t +1.6) | +0.013 | -0.202 | -0.217 | 0.71 | no edge before costs |
| 0+htf | 0 + 1h EMA50/200 trend only | 2692 | +0.003 (t +0.3) | -0.013 | -0.377 | -0.313 | 0.61 | no edge before costs |
| 0+chop | 0 + Choppiness below 55 only | 4816 | +0.017 (t +2.4) | -0.023 | -0.361 | -0.311 | 0.61 | no edge before costs |
| 0+adx | 0 + ADX and DI only | 3101 | -0.033 (t -3.7) | -0.018 | -0.398 | -0.311 | 0.61 | no edge before costs |
| 0+bos | 0 + break of structure only | 4077 | +0.002 (t +0.2) | -0.027 | -0.371 | -0.326 | 0.60 | no edge before costs |
| 0+session | 0 + London / New York morning only | 1893 | +0.040 (t +3.4) | -0.019 | -0.218 | -0.217 | 0.71 | edge smaller than the spread |
| 0+near | 0 + within 1 ATR of the EMA50 only | 3497 | +0.018 (t +2.1) | -0.011 | -0.359 | -0.307 | 0.61 | no edge before costs |

Median stop $1.21 per oz, median hold 0.4 h (rung 0).

### M1, trail

| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | Every stop flip (the plain Buy/Sell labels) | 12334 | -0.024 (t -5.9) | -0.050 | -0.401 | -0.348 | 0.46 | no edge before costs |
| A0 | 0 + price on the right side of a sloping EMA50 | 9791 | -0.021 (t -4.3) | -0.046 | -0.400 | -0.346 | 0.46 | no edge before costs |
| A | A0 + within 1 ATR of the EMA50 (the script with every toggle off) | 3424 | -0.013 (t -1.6) | -0.043 | -0.394 | -0.343 | 0.47 | no edge before costs |
| B | A + 1h EMA50/200 trend | 1058 | +0.002 (t +0.1) | -0.024 | -0.384 | -0.331 | 0.48 | no edge before costs |
| C | B + Choppiness below 55 | 940 | +0.005 (t +0.3) | -0.035 | -0.379 | -0.343 | 0.47 | no edge before costs |
| D | C + ADX at least 20 with DI on side | 446 | -0.001 (t -0.1) | -0.050 | -0.363 | -0.334 | 0.47 | no edge before costs |
| E | D + break of structure in the last 8 bars | 275 | -0.035 (t -1.2) | -0.040 | -0.388 | -0.323 | 0.48 | no edge before costs |
| F | E + London / New York morning | 90 | +0.050 (t +0.9) | -0.100 | -0.187 | -0.307 | 0.48 | no edge before costs |
| site | As on the website: F without the structure filter | 146 | +0.072 (t +1.6) | -0.077 | -0.173 | -0.278 | 0.52 | no edge before costs |
| 0+htf | 0 + 1h EMA50/200 trend only | 3981 | -0.015 (t -2.0) | -0.037 | -0.392 | -0.336 | 0.48 | no edge before costs |
| 0+chop | 0 + Choppiness below 55 only | 11212 | -0.025 (t -5.8) | -0.051 | -0.402 | -0.351 | 0.45 | no edge before costs |
| 0+adx | 0 + ADX and DI only | 4722 | -0.049 (t -7.5) | -0.061 | -0.408 | -0.350 | 0.45 | no edge before costs |
| 0+bos | 0 + break of structure only | 7559 | -0.021 (t -4.0) | -0.044 | -0.393 | -0.341 | 0.46 | no edge before costs |
| 0+session | 0 + London / New York morning only | 3739 | +0.003 (t +0.4) | -0.031 | -0.246 | -0.224 | 0.60 | no edge before costs |
| 0+near | 0 + within 1 ATR of the EMA50 only | 5168 | -0.028 (t -4.4) | -0.049 | -0.405 | -0.347 | 0.46 | no edge before costs |

Median stop $1.14 per oz, median hold 0.3 h (rung 0).

### M5, 2R target

| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | Every stop flip (the plain Buy/Sell labels) | 844 | +0.003 (t +0.2) | +0.008 | -0.120 | -0.112 | 0.84 | no edge before costs |
| A0 | 0 + price on the right side of a sloping EMA50 | 770 | -0.031 (t -1.8) | +0.014 | -0.155 | -0.105 | 0.85 | no edge before costs |
| A | A0 + within 1 ATR of the EMA50 (the script with every toggle off) | 453 | +0.008 (t +0.3) | -0.003 | -0.140 | -0.124 | 0.82 | no edge before costs |
| B | A + 1h EMA50/200 trend | 133 | -0.047 (t -1.2) | +0.035 | -0.215 | -0.104 | 0.85 | no edge before costs |
| C | B + Choppiness below 55 | 108 | -0.039 (t -0.9) | +0.068 | -0.219 | -0.070 | 0.90 | no edge before costs |
| D | C + ADX at least 20 with DI on side | 54 | -0.103 (t -1.7) | +0.027 | -0.273 | -0.083 | 0.88 | no edge before costs |
| E | D + break of structure in the last 8 bars | 34 | -0.108 (t -1.4) | -0.066 | -0.288 | -0.185 | 0.75 | no edge before costs |
| F | E + London / New York morning | 15 | -0.053 (t -0.4) | -0.098 | -0.212 | -0.158 | 0.78 | no edge before costs |
| site | As on the website: F without the structure filter | 24 | -0.077 (t -0.8) | -0.010 | -0.258 | -0.069 | 0.90 | no edge before costs |
| 0+htf | 0 + 1h EMA50/200 trend only | 432 | -0.014 (t -0.6) | -0.017 | -0.159 | -0.135 | 0.81 | no edge before costs |
| 0+chop | 0 + Choppiness below 55 only | 796 | +0.023 (t +1.3) | -0.003 | -0.104 | -0.119 | 0.83 | no edge before costs |
| 0+adx | 0 + ADX and DI only | 546 | -0.018 (t -0.9) | -0.010 | -0.150 | -0.116 | 0.83 | no edge before costs |
| 0+bos | 0 + break of structure only | 725 | -0.042 (t -2.4) | +0.002 | -0.169 | -0.123 | 0.82 | no edge before costs |
| 0+session | 0 + London / New York morning only | 493 | +0.059 (t +2.7) | +0.055 | -0.066 | -0.057 | 0.91 | edge smaller than the spread |
| 0+near | 0 + within 1 ATR of the EMA50 only | 595 | +0.010 (t +0.5) | +0.004 | -0.135 | -0.111 | 0.84 | no edge before costs |

Median stop $3.29 per oz, median hold 2.5 h (rung 0).

### M5, trail

| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | Every stop flip (the plain Buy/Sell labels) | 2054 | -0.021 (t -1.9) | -0.019 | -0.164 | -0.134 | 0.74 | no edge before costs |
| A0 | 0 + price on the right side of a sloping EMA50 | 1730 | -0.022 (t -1.8) | -0.016 | -0.168 | -0.133 | 0.75 | no edge before costs |
| A | A0 + within 1 ATR of the EMA50 (the script with every toggle off) | 623 | -0.046 (t -2.4) | -0.050 | -0.186 | -0.165 | 0.69 | no edge before costs |
| B | A + 1h EMA50/200 trend | 142 | -0.100 (t -2.7) | -0.044 | -0.248 | -0.160 | 0.70 | no edge before costs |
| C | B + Choppiness below 55 | 114 | -0.078 (t -1.9) | -0.039 | -0.231 | -0.159 | 0.70 | no edge before costs |
| D | C + ADX at least 20 with DI on side | 55 | -0.140 (t -2.6) | -0.072 | -0.282 | -0.183 | 0.66 | no edge before costs |
| E | D + break of structure in the last 8 bars | 34 | -0.195 (t -3.4) | -0.166 | -0.343 | -0.275 | 0.52 | no edge before costs |
| F | E + London / New York morning | 15 | -0.125 (t -1.1) | -0.177 | -0.280 | -0.259 | 0.53 | no edge before costs |
| site | As on the website: F without the structure filter | 24 | -0.087 (t -0.9) | -0.003 | -0.224 | -0.084 | 0.84 | no edge before costs |
| 0+htf | 0 + 1h EMA50/200 trend only | 599 | +0.008 (t +0.4) | -0.014 | -0.145 | -0.130 | 0.76 | no edge before costs |
| 0+chop | 0 + Choppiness below 55 only | 1750 | -0.026 (t -2.3) | -0.032 | -0.171 | -0.147 | 0.72 | no edge before costs |
| 0+adx | 0 + ADX and DI only | 862 | -0.047 (t -3.1) | -0.033 | -0.178 | -0.139 | 0.73 | no edge before costs |
| 0+bos | 0 + break of structure only | 1374 | -0.033 (t -2.5) | -0.032 | -0.177 | -0.145 | 0.73 | no edge before costs |
| 0+session | 0 + London / New York morning only | 797 | +0.028 (t +1.5) | +0.036 | -0.076 | -0.049 | 0.90 | no edge before costs |
| 0+near | 0 + within 1 ATR of the EMA50 only | 866 | -0.036 (t -2.2) | -0.045 | -0.177 | -0.159 | 0.69 | no edge before costs |

Median stop $2.90 per oz, median hold 1.9 h (rung 0).

### M15, 2R target

| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | Every stop flip (the plain Buy/Sell labels) | 307 | +0.049 (t +1.8) | -0.011 | -0.041 | -0.057 | 0.91 | no edge before costs |
| A0 | 0 + price on the right side of a sloping EMA50 | 282 | +0.017 (t +0.6) | -0.015 | -0.067 | -0.066 | 0.90 | no edge before costs |
| A | A0 + within 1 ATR of the EMA50 (the script with every toggle off) | 152 | +0.057 (t +1.5) | -0.035 | -0.023 | -0.095 | 0.86 | no edge before costs |
| B | A + 1h EMA50/200 trend | 28 | +0.071 (t +0.8) | -0.064 | +0.014 | -0.100 | 0.85 | no edge before costs |
| C | B + Choppiness below 55 | 23 | +0.128 (t +1.3) | -0.112 | +0.072 | -0.149 | 0.78 | no edge before costs |
| D | C + ADX at least 20 with DI on side | 11 | +0.059 (t +0.4) | -0.184 | -0.016 | -0.222 | 0.69 | too few trades |
| E | D + break of structure in the last 8 bars | 6 | +0.134 (t +0.7) | -0.242 | +0.034 | -0.288 | 0.61 | too few trades |
| F | E + London / New York morning | 4 | -0.058 (t -0.2) | -0.156 | -0.203 | -0.199 | 0.72 | too few trades |
| site | As on the website: F without the structure filter | 6 | -0.029 (t -0.2) | -0.263 | -0.129 | -0.299 | 0.60 | too few trades |
| 0+htf | 0 + 1h EMA50/200 trend only | 139 | -0.010 (t -0.3) | +0.007 | -0.091 | -0.065 | 0.90 | no edge before costs |
| 0+chop | 0 + Choppiness below 55 only | 286 | +0.046 (t +1.7) | +0.010 | -0.035 | -0.044 | 0.93 | no edge before costs |
| 0+adx | 0 + ADX and DI only | 201 | +0.013 (t +0.4) | -0.037 | -0.058 | -0.094 | 0.85 | no edge before costs |
| 0+bos | 0 + break of structure only | 263 | -0.013 (t -0.4) | -0.038 | -0.102 | -0.104 | 0.84 | no edge before costs |
| 0+session | 0 + London / New York morning only | 221 | -0.002 (t -0.1) | +0.005 | -0.087 | -0.037 | 0.94 | no edge before costs |
| 0+near | 0 + within 1 ATR of the EMA50 only | 202 | +0.078 (t +2.3) | +0.002 | -0.010 | -0.059 | 0.91 | edge smaller than the spread |

Median stop $5.86 per oz, median hold 7.2 h (rung 0).

### M15, trail

| Rung | Filters | Trades/yr | Zero cost: discovery | confirmation | Real spread: discovery | confirmation | PF | Verdict |
|---|---|---|---|---|---|---|---|---|
| 0 | Every stop flip (the plain Buy/Sell labels) | 655 | +0.027 (t +1.3) | -0.001 | -0.051 | -0.057 | 0.89 | no edge before costs |
| A0 | 0 + price on the right side of a sloping EMA50 | 562 | +0.038 (t +1.7) | +0.008 | -0.043 | -0.049 | 0.90 | no edge before costs |
| A | A0 + within 1 ATR of the EMA50 (the script with every toggle off) | 195 | +0.033 (t +0.9) | -0.023 | -0.044 | -0.082 | 0.84 | no edge before costs |
| B | A + 1h EMA50/200 trend | 29 | +0.094 (t +0.8) | -0.036 | +0.012 | -0.086 | 0.84 | no edge before costs |
| C | B + Choppiness below 55 | 23 | +0.117 (t +0.9) | -0.152 | +0.031 | -0.201 | 0.63 | no edge before costs |
| D | C + ADX at least 20 with DI on side | 11 | +0.019 (t +0.1) | -0.003 | -0.079 | -0.052 | 0.91 | too few trades |
| E | D + break of structure in the last 8 bars | 6 | +0.029 (t +0.1) | +0.239 | -0.099 | +0.183 | 1.30 | too few trades |
| F | E + London / New York morning | 4 | +0.048 (t +0.1) | -0.065 | -0.139 | -0.119 | 0.80 | too few trades |
| site | As on the website: F without the structure filter | 6 | +0.017 (t +0.1) | -0.232 | -0.113 | -0.279 | 0.56 | too few trades |
| 0+htf | 0 + 1h EMA50/200 trend only | 172 | +0.069 (t +1.4) | +0.059 | -0.032 | +0.000 | 1.00 | no edge before costs |
| 0+chop | 0 + Choppiness below 55 only | 565 | +0.037 (t +1.7) | -0.016 | -0.038 | -0.071 | 0.86 | no edge before costs |
| 0+adx | 0 + ADX and DI only | 302 | +0.000 (t +0.0) | -0.002 | -0.067 | -0.056 | 0.89 | no edge before costs |
| 0+bos | 0 + break of structure only | 457 | +0.035 (t +1.4) | -0.012 | -0.048 | -0.070 | 0.86 | no edge before costs |
| 0+session | 0 + London / New York morning only | 335 | +0.040 (t +1.3) | +0.020 | -0.037 | -0.031 | 0.94 | no edge before costs |
| 0+near | 0 + within 1 ATR of the EMA50 only | 265 | +0.038 (t +1.2) | -0.026 | -0.034 | -0.082 | 0.84 | no edge before costs |

Median stop $5.59 per oz, median hold 6.5 h (rung 0).
