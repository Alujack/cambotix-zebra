# XAUUSD intraday screen (2026-11-22 00:42 UTC)

Development gold only (Dukascopy M1 2010-06-01 .. 2024-11-19; nothing from 2024-11-20 on is loaded). Discovery 2011-01-01 to 2019-01-01, confirmation 2019-01-01 to 2024-11-20. Signals from closed M15 or H1 bars, trades held for hours, one position at a time per idea. R = result divided by the stop distance. Costs: zero spread, half the recorded spread, the recorded spread. Times are New York.

Pass rule, fixed before the run: at zero cost in discovery mean R >= +0.03 with t >= 2; at the recorded spread in discovery mean R > 0; then in confirmation at the recorded spread mean R >= +0.05, profit factor >= 1.15, 60% of years positive and at least 50 trades a year.

**47 ideas tested, 0 passed.**

| Verdict | Ideas |
|---|---|
| no edge before costs | 42 |
| failed confirmation | 5 |

| Family | Idea | Trades a year | Median hold (hours) | Median stop ($) | Spread cost (R) | Zero cost: discovery R (t) | Zero cost: confirmation R | Real spread: discovery R | Real spread: confirmation R (t) | Confirmation PF | Confirmation total R | Years positive | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Session range break (M15) | Asia range, break in London, follow | 189 | 4.3 | 4.70 | 0.088 | +0.087 (+1.7) | -0.020 | -0.033 | -0.109 (-2.1) | 0.85 | -121.2 | 1 of 6 | no edge before costs |
| Session range break (M15) | Asia range, break in London, fade | 189 | 4.6 | 4.70 | 0.094 | -0.098 (-2.3) | -0.030 | -0.186 | -0.124 (-2.6) | 0.82 | -138.2 | 1 of 6 | no edge before costs |
| Session range break (M15) | London range, break in New York, follow | 227 | 2.6 | 5.20 | 0.071 | +0.036 (+0.9) | +0.024 | -0.063 | -0.046 (-1.1) | 0.93 | -61.7 | 2 of 6 | no edge before costs |
| Session range break (M15) | London range, break in New York, fade | 227 | 2.9 | 5.20 | 0.078 | +0.089 (+2.4) | -0.000 | +0.003 | -0.078 (-1.9) | 0.87 | -104.1 | 0 of 6 | failed confirmation |
| Session range break (M15) | Asia + London range, break in New York, follow | 191 | 4.8 | 6.62 | 0.059 | +0.042 (+1.2) | +0.011 | -0.031 | -0.048 (-1.2) | 0.91 | -53.7 | 2 of 6 | no edge before costs |
| Session range break (M15) | Asia + London range, break in New York, fade | 191 | 5.2 | 6.62 | 0.050 | +0.008 (+0.2) | +0.066 | -0.056 | +0.015 (+0.4) | 1.03 | +17.1 | 3 of 6 | no edge before costs |
| Session range break (M15) | New York 08:00 to 09:30 range, break by 13:00, follow | 219 | 4.8 | 6.09 | 0.069 | +0.005 (+0.2) | +0.055 | -0.067 | -0.013 (-0.4) | 0.97 | -17.3 | 3 of 6 | no edge before costs |
| Session range break (M15) | New York 08:00 to 09:30 range, break by 13:00, fade | 219 | 4.8 | 6.09 | 0.062 | +0.024 (+0.8) | +0.002 | -0.052 | -0.061 (-1.9) | 0.87 | -78.1 | 1 of 6 | no edge before costs |
| Volatility breakout (M15) | open +/- 0.5 x yesterday's range, follow | 159 | 6.8 | 9.51 | 0.034 | +0.115 (+2.8) | +0.044 | +0.067 | +0.010 (+0.2) | 1.02 | +9.0 | 2 of 6 | failed confirmation |
| Volatility breakout (M15) | open +/- 0.5 x yesterday's range, fade | 159 | 6.7 | 9.51 | 0.049 | +0.017 (+0.5) | -0.026 | -0.028 | -0.075 (-2.0) | 0.84 | -70.3 | 1 of 6 | no edge before costs |
| Volatility breakout (M15) | open +/- 1 x yesterday's range, follow | 61 | 6.5 | 16.82 | 0.022 | +0.151 (+3.5) | +0.054 | +0.122 | +0.032 (+0.8) | 1.12 | +11.4 | 4 of 6 | failed confirmation |
| Volatility breakout (M15) | open +/- 1 x yesterday's range, fade | 61 | 6.2 | 16.82 | 0.030 | -0.100 (-3.0) | -0.036 | -0.133 | -0.066 (-1.7) | 0.79 | -23.6 | 1 of 6 | no edge before costs |
| Narrow day, then the break (M15) | inside day, break of its high/low, follow | 32 | 7.2 | 8.03 | 0.054 | +0.209 (+1.9) | +0.092 | +0.140 | +0.038 (+0.3) | 1.07 | +7.1 | 4 of 6 | no edge before costs |
| Narrow day, then the break (M15) | inside day, break of its high/low, fade | 32 | 7.1 | 8.03 | 0.051 | +0.064 (+0.7) | +0.003 | -0.015 | -0.048 (-0.5) | 0.92 | -8.9 | 2 of 6 | no edge before costs |
| Narrow day, then the break (M15) | narrowest day of 7, break of its high/low, follow | 35 | 7.2 | 6.75 | 0.054 | +0.168 (+1.4) | +0.081 | +0.106 | +0.026 (+0.2) | 1.04 | +5.4 | 3 of 6 | no edge before costs |
| Narrow day, then the break (M15) | narrowest day of 7, break of its high/low, fade | 35 | 6.0 | 6.75 | 0.086 | +0.117 (+1.1) | -0.082 | +0.038 | -0.168 (-1.6) | 0.75 | -34.8 | 1 of 6 | no edge before costs |
| Channel break (H1) | 24 hour channel, follow | 222 | 8.9 | 9.25 | 0.048 | +0.053 (+1.9) | +0.012 | -0.011 | -0.036 (-1.1) | 0.93 | -46.9 | 1 of 6 | no edge before costs |
| Channel break (H1) | 24 hour channel, fade | 254 | 9.9 | 9.29 | 0.045 | -0.021 (-0.9) | -0.021 | -0.076 | -0.066 (-2.2) | 0.88 | -98.1 | 1 of 6 | no edge before costs |
| Channel break (H1) | 3 day channel, follow | 125 | 9.9 | 9.62 | 0.037 | +0.027 (+0.7) | -0.006 | -0.031 | -0.044 (-1.0) | 0.92 | -32.1 | 2 of 6 | no edge before costs |
| Channel break (H1) | 3 day channel, fade | 147 | 9.6 | 9.64 | 0.044 | -0.024 (-0.7) | -0.010 | -0.081 | -0.054 (-1.4) | 0.90 | -46.8 | 3 of 6 | no edge before costs |
| Channel break (H1) | 5 day channel, follow | 95 | 9.0 | 9.71 | 0.038 | +0.067 (+1.6) | +0.029 | +0.002 | -0.009 (-0.2) | 0.98 | -4.9 | 3 of 6 | no edge before costs |
| Channel break (H1) | 5 day channel, fade | 113 | 8.7 | 9.66 | 0.040 | -0.055 (-1.5) | -0.038 | -0.111 | -0.078 (-1.7) | 0.86 | -51.9 | 2 of 6 | no edge before costs |
| Moving averages (H1) | EMA 20 crosses EMA 50, follow | 89 | 24.0 | 13.32 | 0.024 | -0.015 (-0.4) | +0.034 | -0.053 | +0.010 (+0.2) | 1.03 | +5.2 | 4 of 6 | no edge before costs |
| Moving averages (H1) | EMA 20 crosses EMA 50, fade | 78 | 24.0 | 13.30 | 0.032 | -0.005 (-0.1) | -0.006 | -0.041 | -0.038 (-0.9) | 0.91 | -17.6 | 0 of 6 | no edge before costs |
| Moving averages (H1) | pullback to EMA 20 in the EMA 50/200 trend | 185 | 11.0 | 8.76 | 0.042 | +0.067 (+2.2) | -0.023 | +0.010 | -0.064 (-1.8) | 0.88 | -70.0 | 1 of 6 | failed confirmation |
| Stretched (H1) | RSI 30/70, follow | 150 | 5.8 | 9.47 | 0.047 | +0.029 (+1.2) | +0.000 | -0.021 | -0.047 (-1.7) | 0.88 | -41.9 | 0 of 6 | no edge before costs |
| Stretched (H1) | RSI 30/70, fade | 151 | 5.9 | 9.45 | 0.052 | -0.029 (-1.2) | -0.000 | -0.083 | -0.052 (-1.8) | 0.87 | -46.2 | 0 of 6 | no edge before costs |
| Stretched (H1) | close outside the Bollinger band, follow | 289 | 5.0 | 8.96 | 0.055 | +0.020 (+1.1) | +0.011 | -0.030 | -0.044 (-2.1) | 0.89 | -74.4 | 0 of 6 | no edge before costs |
| Stretched (H1) | close outside the Bollinger band, fade | 290 | 5.0 | 8.96 | 0.049 | -0.020 (-1.2) | -0.013 | -0.080 | -0.062 (-3.0) | 0.85 | -105.2 | 0 of 6 | no edge before costs |
| Round numbers (H1) | close crosses a $50 level, follow | 111 | 10.6 | 11.00 | 0.040 | +0.041 (+0.9) | +0.028 | -0.017 | -0.012 (-0.3) | 0.98 | -7.8 | 3 of 6 | no edge before costs |
| Round numbers (H1) | close crosses a $50 level, fade | 100 | 8.9 | 10.99 | 0.037 | -0.038 (-0.8) | -0.019 | -0.086 | -0.056 (-1.2) | 0.89 | -32.5 | 1 of 6 | no edge before costs |
| Round numbers (H1) | close crosses a $100 level, follow | 61 | 10.0 | 10.46 | 0.043 | -0.002 (-0.0) | +0.053 | -0.050 | +0.009 (+0.1) | 1.02 | +3.2 | 4 of 6 | no edge before costs |
| Round numbers (H1) | close crosses a $100 level, fade | 54 | 8.5 | 10.36 | 0.034 | -0.058 (-0.9) | -0.045 | -0.124 | -0.080 (-1.3) | 0.85 | -25.1 | 2 of 6 | no edge before costs |
| Last 24 hours at a session open (H1) | London open, last 24 hours, follow | 258 | 13.0 | 11.99 | 0.031 | +0.002 (+0.1) | +0.036 | -0.034 | +0.005 (+0.2) | 1.01 | +7.9 | 2 of 6 | no edge before costs |
| Last 24 hours at a session open (H1) | London open, last 24 hours, fade | 258 | 13.0 | 11.99 | 0.033 | +0.002 (+0.1) | -0.009 | -0.034 | -0.042 (-1.6) | 0.90 | -64.4 | 1 of 6 | no edge before costs |
| Last 24 hours at a session open (H1) | New York open, last 24 hours, follow | 258 | 8.0 | 12.26 | 0.030 | +0.015 (+0.8) | +0.037 | -0.020 | +0.006 (+0.3) | 1.02 | +9.9 | 4 of 6 | no edge before costs |
| Last 24 hours at a session open (H1) | New York open, last 24 hours, fade | 258 | 8.0 | 12.26 | 0.028 | +0.005 (+0.3) | -0.012 | -0.035 | -0.040 (-1.7) | 0.89 | -60.0 | 1 of 6 | no edge before costs |
| Day trade from a daily rule | yesterday's direction, follow | 258 | 21.0 | 23.96 | 0.019 | -0.006 (-0.4) | +0.013 | -0.028 | -0.006 (-0.4) | 0.98 | -9.2 | 3 of 6 | no edge before costs |
| Day trade from a daily rule | yesterday's direction, fade | 258 | 21.0 | 23.96 | 0.016 | +0.019 (+1.3) | -0.001 | -0.002 | -0.017 (-1.0) | 0.93 | -25.7 | 3 of 6 | no edge before costs |
| Day trade from a daily rule | yesterday's direction after a big day, follow | 64 | 21.0 | 24.06 | 0.017 | +0.001 (+0.0) | +0.075 | -0.020 | +0.058 (+1.8) | 1.27 | +21.7 | 5 of 6 | no edge before costs |
| Day trade from a daily rule | yesterday's direction after a big day, fade | 64 | 21.0 | 24.06 | 0.016 | +0.013 (+0.5) | -0.076 | -0.008 | -0.092 (-2.8) | 0.68 | -34.3 | 0 of 6 | no edge before costs |
| Day trade from a daily rule | side of the 20 day average, follow | 258 | 21.0 | 23.96 | 0.019 | +0.026 (+1.8) | +0.019 | +0.005 | +0.000 (+0.0) | 1.00 | +0.2 | 4 of 6 | no edge before costs |
| Day trade from a daily rule | side of the 20 day average, fade | 258 | 21.0 | 23.96 | 0.016 | -0.013 (-1.0) | -0.007 | -0.035 | -0.023 (-1.4) | 0.91 | -35.1 | 1 of 6 | no edge before costs |
| Day trade from a daily rule | side of the 50 day average, follow | 258 | 21.0 | 23.96 | 0.019 | +0.015 (+1.1) | +0.023 | -0.006 | +0.004 (+0.2) | 1.02 | +5.6 | 4 of 6 | no edge before costs |
| Day trade from a daily rule | side of the 50 day average, fade | 258 | 21.0 | 23.96 | 0.016 | -0.003 (-0.2) | -0.011 | -0.024 | -0.027 (-1.6) | 0.90 | -40.5 | 0 of 6 | no edge before costs |
| Day trade from a daily rule | always buy (benchmark) | 258 | 21.0 | 23.96 | 0.019 | -0.004 (-0.3) | +0.038 | -0.029 | +0.019 (+1.2) | 1.08 | +28.4 | 4 of 6 | no edge before costs |
| Session or weekday drift | sell London 03:00 to 08:00 | 258 | 5.0 | 11.99 | 0.030 | +0.037 (+3.1) | -0.005 | +0.002 | -0.035 (-2.7) | 0.83 | -52.7 | 1 of 6 | failed confirmation |

## Drift by session and by weekday, zero cost (buy at the start, flat at the end)

A row is traded as an idea only if its discovery t is at least 2.5 in size.

| Window | Discovery R (t) | Discovery $ per oz | Confirmation R (t) | Confirmation $ per oz |
|---|---|---|---|---|
| Asia 19:00 to 03:00 | +0.019 (+1.7) | +0.225 | +0.029 (+2.4) | +0.242 |
| London 03:00 to 08:00 | -0.034 (-2.9) | -0.341 | +0.003 (+0.3) | +0.001 |
| New York morning 08:00 to 12:00 | -0.005 (-0.3) | -0.158 | +0.018 (+0.8) | +0.102 |
| New York afternoon 12:00 to 16:00 | -0.009 (-0.9) | -0.100 | +0.008 (+0.7) | +0.081 |
| Monday 19:00 to 16:00 | -0.039 (-0.9) | -0.418 | -0.031 (-0.6) | -0.398 |
| Tuesday 19:00 to 16:00 | -0.011 (-0.2) | +0.028 | +0.093 (+1.5) | +1.205 |
| Wednesday 19:00 to 16:00 | -0.050 (-1.0) | -0.860 | +0.056 (+1.0) | +0.145 |
| Thursday 19:00 to 16:00 | -0.032 (-0.6) | -0.478 | +0.065 (+1.1) | +1.425 |
| Friday 19:00 to 16:00 | +0.068 (+1.3) | +0.882 | +0.146 (+2.2) | +0.974 |

For scale: the median recorded spread in the confirmation years is $0.34 per oz. "Spread cost (R)" is the zero-cost result minus the real-spread result in confirmation.

Gold rose from about $1,280 to about $2,630 in the confirmation years and fell in the discovery years. A rule that is mostly long looks good in confirmation for that reason alone; the "always buy" row shows how much of a result is that drift.
