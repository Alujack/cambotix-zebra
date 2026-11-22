# XAUUSD idea screen (2026-11-21 15:01 UTC)

Development gold only (Dukascopy M1 2010-06-01 .. 2024-11-19; nothing from 2024-11-20 on is loaded). Discovery 2011-01-01 to 2019-01-01, confirmation 2019-01-01 to 2024-11-20. One position at a time per idea. R = result divided by the stop distance. Costs: zero spread, half the recorded spread, the recorded spread.

Pass rule, fixed before the run: at zero cost in discovery mean R >= +0.03 with t >= 2; at the recorded spread in discovery mean R > 0; then in confirmation at the recorded spread mean R >= +0.05, profit factor >= 1.15, 60% of years positive and at least 50 trades a year.

**57 ideas tested (round 2 included), 0 passed.**

| Verdict | Ideas |
|---|---|
| no edge before costs | 48 |
| edge smaller than the spread | 8 |
| failed confirmation | 1 |

## Round 1: every idea

| Family | Idea | Trades a year | Zero cost: discovery R (t) | Zero cost: confirmation R | Half spread: confirmation R | Real spread: discovery R | Real spread: confirmation R | Confirmation PF | Years positive | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Move, then follow it | 5 min move >= 1, follow | 5798 | -0.015 (-3.3) | -0.027 | -0.149 | -0.313 | -0.275 | 0.53 | 0 of 6 | no edge before costs |
| Move, then fade it | 5 min move >= 1, fade | 5797 | +0.018 (+4.2) | +0.027 | -0.098 | -0.278 | -0.223 | 0.59 | 0 of 6 | no edge before costs |
| Move, then follow it | 5 min move >= 2, follow | 681 | +0.008 (+0.6) | -0.008 | -0.121 | -0.273 | -0.232 | 0.62 | 0 of 6 | no edge before costs |
| Move, then fade it | 5 min move >= 2, fade | 681 | -0.014 (-1.1) | +0.010 | -0.102 | -0.294 | -0.220 | 0.63 | 0 of 6 | no edge before costs |
| Move, then follow it | 15 min move >= 1, follow | 3955 | -0.005 (-1.3) | -0.013 | -0.083 | -0.177 | -0.154 | 0.58 | 0 of 6 | no edge before costs |
| Move, then fade it | 15 min move >= 1, fade | 3870 | +0.012 (+3.1) | +0.012 | -0.058 | -0.157 | -0.128 | 0.63 | 0 of 6 | no edge before costs |
| Move, then follow it | 15 min move >= 2, follow | 351 | +0.015 (+1.1) | +0.029 | -0.033 | -0.138 | -0.096 | 0.76 | 0 of 6 | no edge before costs |
| Move, then fade it | 15 min move >= 2, fade | 353 | -0.003 (-0.2) | -0.015 | -0.076 | -0.156 | -0.136 | 0.66 | 0 of 6 | no edge before costs |
| Move, then follow it | 60 min move >= 1, follow | 1642 | -0.012 (-2.6) | -0.008 | -0.043 | -0.096 | -0.078 | 0.67 | 0 of 6 | no edge before costs |
| Move, then fade it | 60 min move >= 1, fade | 1636 | +0.013 (+2.8) | +0.007 | -0.027 | -0.070 | -0.062 | 0.72 | 0 of 6 | no edge before costs |
| Move, then follow it | 60 min move >= 2, follow | 63 | -0.006 (-0.3) | -0.007 | -0.035 | -0.069 | -0.061 | 0.76 | 2 of 6 | no edge before costs |
| Move, then fade it | 60 min move >= 2, fade | 64 | +0.003 (+0.2) | +0.010 | -0.015 | -0.059 | -0.043 | 0.82 | 3 of 6 | no edge before costs |
| Move, then follow it | 240 min move >= 1, follow | 605 | +0.006 (+0.8) | +0.003 | -0.016 | -0.038 | -0.034 | 0.84 | 0 of 6 | no edge before costs |
| Move, then fade it | 240 min move >= 1, fade | 609 | +0.000 (+0.1) | +0.002 | -0.016 | -0.042 | -0.034 | 0.83 | 0 of 6 | no edge before costs |
| Move, then follow it | 240 min move >= 2, follow | 37 | -0.044 (-1.7) | +0.046 | +0.029 | -0.086 | +0.011 | 1.08 | 5 of 6 | no edge before costs |
| Move, then fade it | 240 min move >= 2, fade | 37 | +0.035 (+1.4) | -0.050 | -0.070 | -0.019 | -0.087 | 0.53 | 1 of 6 | no edge before costs |
| Channel break (M15) | 5 hour channel, follow | 982 | +0.007 (+0.5) | -0.014 | -0.065 | -0.113 | -0.113 | 0.82 | 0 of 6 | no edge before costs |
| Channel break (M15) | 5 hour channel, fade | 1062 | +0.008 (+0.6) | +0.019 | -0.028 | -0.100 | -0.079 | 0.87 | 0 of 6 | no edge before costs |
| Channel break (M15) | 24 hour channel, follow | 403 | +0.064 (+2.8) | +0.024 | -0.021 | -0.041 | -0.064 | 0.89 | 0 of 6 | edge smaller than the spread |
| Channel break (M15) | 24 hour channel, fade | 478 | +0.001 (+0.1) | -0.014 | -0.054 | -0.097 | -0.092 | 0.85 | 0 of 6 | no edge before costs |
| Squeeze break (M5) | squeeze, follow | 735 | +0.052 (+3.0) | -0.005 | -0.184 | -0.395 | -0.369 | 0.55 | 0 of 6 | edge smaller than the spread |
| Squeeze break (M5) | squeeze, fade | 709 | -0.037 (-2.1) | +0.016 | -0.162 | -0.458 | -0.351 | 0.56 | 0 of 6 | no edge before costs |
| Round numbers | $10 level, breakout | 444 | +0.061 (+2.9) | +0.076 | -0.002 | -0.154 | -0.107 | 0.83 | 0 of 6 | edge smaller than the spread |
| Round numbers | $10 level, rejection | 491 | +0.024 (+1.1) | -0.004 | -0.101 | -0.196 | -0.189 | 0.70 | 0 of 6 | no edge before costs |
| Round numbers | $50 level, breakout | 89 | +0.131 (+2.7) | +0.158 | +0.068 | -0.062 | -0.018 | 0.97 | 4 of 6 | edge smaller than the spread |
| Round numbers | $50 level, rejection | 92 | -0.083 (-1.6) | -0.061 | -0.143 | -0.283 | -0.219 | 0.66 | 0 of 6 | no edge before costs |
| Previous day high/low | first close beyond, follow | 232 | +0.049 (+1.5) | +0.036 | -0.037 | -0.150 | -0.117 | 0.83 | 0 of 6 | no edge before costs |
| Previous day high/low | first close beyond, fade | 232 | -0.028 (-0.9) | -0.019 | -0.084 | -0.203 | -0.166 | 0.76 | 0 of 6 | no edge before costs |
| News clock | 08:30 range break | 216 | -0.014 (-0.6) | -0.004 | -0.050 | -0.120 | -0.104 | 0.79 | 0 of 6 | no edge before costs |
| News clock | 10:00 range break | 203 | +0.009 (+0.4) | +0.056 | +0.012 | -0.101 | -0.033 | 0.92 | 2 of 6 | no edge before costs |
| One session predicts the next | Asia -> London, follow | 258 | -0.021 (-1.5) | +0.000 | -0.017 | -0.063 | -0.033 | 0.85 | 1 of 6 | no edge before costs |
| One session predicts the next | Asia -> London, fade | 258 | +0.015 (+1.1) | -0.000 | -0.018 | -0.027 | -0.035 | 0.85 | 1 of 6 | no edge before costs |
| One session predicts the next | overnight -> New York, follow | 258 | -0.003 (-0.2) | +0.008 | -0.007 | -0.040 | -0.021 | 0.92 | 2 of 6 | no edge before costs |
| One session predicts the next | overnight -> New York, fade | 258 | +0.002 (+0.2) | -0.001 | -0.017 | -0.034 | -0.031 | 0.89 | 2 of 6 | no edge before costs |
| One session predicts the next | COMEX first 30 min -> last hour, follow | 258 | +0.008 (+1.8) | -0.000 | -0.012 | -0.019 | -0.023 | 0.69 | 0 of 6 | no edge before costs |
| One session predicts the next | COMEX first 30 min -> last hour, fade | 258 | -0.008 (-1.6) | +0.000 | -0.011 | -0.034 | -0.023 | 0.69 | 0 of 6 | no edge before costs |
| One session predicts the next | New York day -> next Asia, follow | 251 | +0.012 (+0.8) | +0.003 | -0.024 | -0.049 | -0.049 | 0.83 | 0 of 6 | no edge before costs |
| One session predicts the next | New York day -> next Asia, fade | 251 | -0.019 (-1.3) | -0.022 | -0.047 | -0.082 | -0.073 | 0.75 | 0 of 6 | no edge before costs |
| Daily trend pullback (M15) | RSI 30/70 with the daily trend | 196 | -0.013 (-0.4) | +0.011 | -0.021 | -0.082 | -0.053 | 0.91 | 1 of 6 | no edge before costs |
| Hour of the day | buy the 01:00 hour | 258 | +0.020 (+3.0) | +0.004 | -0.021 | -0.041 | -0.047 | 0.66 | 0 of 6 | no edge before costs |
| Hour of the day | sell the 02:00 hour | 258 | +0.030 (+4.1) | -0.007 | -0.028 | -0.021 | -0.049 | 0.67 | 0 of 6 | edge smaller than the spread |
| Hour of the day | sell the 05:00 hour | 258 | +0.019 (+3.7) | -0.007 | -0.022 | -0.018 | -0.037 | 0.61 | 1 of 6 | no edge before costs |
| Hour of the day | sell the 16:00 hour | 251 | +0.036 (+10.5) | +0.020 | -0.010 | -0.058 | -0.041 | 0.48 | 0 of 6 | edge smaller than the spread |
| Hour of the day | sell the 17:00 hour | 0 | +0.045 (+2.9) | - | - | -0.082 | - | - | 0 of 0 | edge smaller than the spread |
| Hour of the day | buy the 18:00 hour | 0 | +0.066 (+4.8) | - | - | -0.063 | - | - | 0 of 0 | edge smaller than the spread |
| EURUSD leads gold (2020-12 on) | EURUSD 5 min move, gold follows | 189 | -0.049 (-1.0) | +0.045 | -0.072 | -0.304 | -0.201 | 0.64 | 0 of 2 | no edge before costs |
| EURUSD leads gold (2020-12 on) | EURUSD 5 min move, gold opposite | 188 | +0.049 (+1.0) | -0.065 | -0.195 | -0.206 | -0.308 | 0.49 | 0 of 2 | no edge before costs |
| EURUSD leads gold (2020-12 on) | EURUSD 15 min move, gold follows | 116 | -0.040 (-0.6) | +0.073 | -0.010 | -0.270 | -0.129 | 0.76 | 0 of 2 | no edge before costs |
| EURUSD leads gold (2020-12 on) | EURUSD 15 min move, gold opposite | 114 | +0.009 (+0.1) | -0.035 | -0.167 | -0.244 | -0.302 | 0.49 | 0 of 2 | no edge before costs |

## Round 2: level breaks with wider stops (exploratory)

Added after round 1 was read, so the confirmation years are no longer unseen for these entries. Same entries as the round 1 level breaks; stop, target and hold are 2x and 4x larger. A pass here is a candidate for the one lockbox run, not a result.

| Family | Idea | Trades a year | Zero cost: discovery R (t) | Zero cost: confirmation R | Half spread: confirmation R | Real spread: discovery R | Real spread: confirmation R | Confirmation PF | Years positive | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Channel break (M15) | 24 hour channel, follow, stop x2 | 290 | +0.035 (+1.6) | +0.013 | -0.011 | -0.017 | -0.034 | 0.93 | 1 of 6 | no edge before costs |
| Channel break (M15) | 24 hour channel, follow, stop x4 | 213 | +0.043 (+2.2) | +0.026 | +0.014 | +0.016 | +0.004 | 1.01 | 3 of 6 | failed confirmation |
| Round numbers | $10 level, breakout, stop x2 | 418 | +0.033 (+1.7) | +0.031 | -0.012 | -0.074 | -0.065 | 0.87 | 1 of 6 | no edge before costs |
| Round numbers | $10 level, breakout, stop x4 | 348 | -0.004 (-0.2) | +0.031 | +0.009 | -0.063 | -0.013 | 0.96 | 1 of 6 | no edge before costs |
| Round numbers | $50 level, breakout, stop x2 | 88 | +0.072 (+1.7) | +0.049 | +0.010 | -0.026 | -0.032 | 0.93 | 3 of 6 | no edge before costs |
| Round numbers | $50 level, breakout, stop x4 | 79 | +0.013 (+0.3) | +0.108 | +0.089 | -0.042 | +0.069 | 1.22 | 5 of 6 | no edge before costs |
| Previous day high/low | first close beyond, follow, stop x2 | 228 | +0.041 (+1.4) | +0.025 | -0.010 | -0.051 | -0.053 | 0.91 | 1 of 6 | no edge before costs |
| Previous day high/low | first close beyond, follow, stop x4 | 211 | +0.027 (+1.0) | +0.028 | +0.011 | -0.018 | -0.013 | 0.97 | 3 of 6 | no edge before costs |

## Drift by New York hour, zero cost (buy at the start of the hour, hold 60 minutes)

An hour is traded as an idea only if its discovery t is at least 2.5 in size.

| Hour | Discovery R (t) | Discovery $ per oz | Confirmation R (t) | Confirmation $ per oz |
|---|---|---|---|---|
| 00:00 | +0.002 (+0.3) | +0.001 | +0.006 (+0.8) | +0.036 |
| 01:00 | +0.020 (+3.0) | +0.105 | +0.004 (+0.5) | -0.016 |
| 02:00 | -0.029 (-4.0) | -0.168 | +0.008 (+0.9) | +0.107 |
| 03:00 | -0.014 (-1.9) | -0.077 | +0.001 (+0.1) | +0.052 |
| 04:00 | -0.009 (-1.8) | -0.098 | +0.002 (+0.4) | +0.009 |
| 05:00 | -0.018 (-3.5) | -0.190 | +0.007 (+1.3) | +0.044 |
| 06:00 | -0.004 (-0.7) | -0.034 | -0.001 (-0.3) | -0.027 |
| 07:00 | +0.004 (+0.6) | +0.045 | -0.005 (-0.8) | -0.087 |
| 08:00 | -0.005 (-0.5) | -0.075 | +0.013 (+1.0) | +0.090 |
| 09:00 | -0.013 (-2.1) | -0.258 | -0.002 (-0.3) | -0.116 |
| 10:00 | +0.009 (+1.6) | +0.182 | +0.004 (+0.6) | +0.074 |
| 11:00 | +0.001 (+0.2) | +0.023 | +0.001 (+0.3) | -0.006 |
| 12:00 | -0.004 (-0.9) | -0.033 | -0.001 (-0.3) | -0.029 |
| 13:00 | -0.002 (-0.4) | -0.027 | +0.002 (+0.3) | +0.049 |
| 14:00 | -0.003 (-0.5) | -0.076 | +0.010 (+1.6) | +0.104 |
| 15:00 | -0.001 (-0.2) | +0.044 | -0.005 (-1.1) | -0.064 |
| 16:00 | -0.036 (-10.5) | -0.178 | -0.020 (-5.3) | -0.111 |
| 17:00 | -0.046 (-3.0) | -0.262 | - (-) | - |
| 18:00 | +0.066 (+4.8) | +0.506 | - (-) | - |
| 19:00 | +0.008 (+1.3) | +0.061 | +0.019 (+3.1) | +0.134 |
| 20:00 | +0.018 (+2.2) | +0.084 | +0.002 (+0.2) | -0.035 |
| 21:00 | +0.013 (+1.7) | +0.152 | +0.021 (+2.1) | +0.073 |
| 22:00 | +0.001 (+0.3) | +0.066 | -0.001 (-0.1) | +0.015 |
| 23:00 | -0.006 (-1.3) | +0.010 | -0.001 (-0.2) | -0.013 |

For scale: the median recorded spread in the confirmation years is $0.34 per oz.

The 16:00 to 18:00 rows are not a real drift. The candles are bid prices: the spread widens into the 17:00 close, which pushes the bid down, and narrows again after the reopen. At the recorded spread those hours lose like the rest.
