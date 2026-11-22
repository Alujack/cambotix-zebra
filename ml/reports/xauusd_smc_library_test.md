# smart-money-concepts library on XAUUSD (2026-11-21 16:58 UTC)

Library: github.com/joshyattridge/smart-money-concepts v0.0.27, its own code, unchanged. Development gold only (Dukascopy; nothing from 2024-11-20 on is loaded). Discovery 2011-01-01 to 2019-01-01, confirmation 2019-01-01 to 2024-11-20.

Every trade: enter at the open after the signal bar, stop 2 ATR, target 2R, hold at most 48 bars, one position at a time. "Swing" is the library's `swing_length`.

Pass rule (the same as the idea screen, fixed before the run): at zero cost in discovery mean R >= +0.03 with t >= 2; at the recorded spread in discovery mean R > 0; in confirmation at the recorded spread mean R >= +0.05, profit factor >= 1.15, 60% of years positive, at least 50 trades a year.

**48 live tests, 0 passed.**

| Verdict | Tests |
|---|---|
| no edge before costs | 41 |
| failed confirmation | 3 |
| too few trades | 3 |
| edge smaller than the spread | 1 |

## Live: the library sees only candles up to now

| Timeframe | Swing | Signal | Traded | Trades a year | Zero cost: discovery R (t) | Zero cost: confirmation R | Half spread: confirmation R | Real spread: discovery R | Real spread: confirmation R | Confirmation PF | Years positive | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| M5 | - | Fair value gap forms | as the concept says | 3792 | -0.012 (-1.5) | +0.000 | -0.092 | -0.237 | -0.197 | 0.72 | 0 of 6 | no edge before costs |
| M5 | - | Fair value gap forms | opposite | 3703 | +0.025 (+3.3) | +0.016 | -0.074 | -0.191 | -0.169 | 0.75 | 0 of 6 | no edge before costs |
| M5 | - | Fair value gap retest | as the concept says | 3561 | +0.027 (+3.4) | +0.016 | -0.082 | -0.191 | -0.179 | 0.74 | 0 of 6 | no edge before costs |
| M5 | - | Fair value gap retest | opposite | 3574 | -0.009 (-1.2) | -0.024 | -0.118 | -0.229 | -0.207 | 0.71 | 0 of 6 | no edge before costs |
| M5 | 5 | Break of structure | as the concept says | 1049 | -0.007 (-0.5) | -0.024 | -0.124 | -0.239 | -0.225 | 0.69 | 0 of 6 | no edge before costs |
| M5 | 5 | Break of structure | opposite | 1039 | +0.008 (+0.6) | +0.038 | -0.069 | -0.221 | -0.177 | 0.74 | 0 of 6 | no edge before costs |
| M5 | 5 | Change of character | as the concept says | 777 | -0.008 (-0.4) | -0.020 | -0.110 | -0.236 | -0.202 | 0.71 | 0 of 6 | no edge before costs |
| M5 | 5 | Change of character | opposite | 732 | +0.000 (+0.0) | +0.012 | -0.086 | -0.227 | -0.175 | 0.75 | 0 of 6 | no edge before costs |
| M5 | 5 | Order block retest | as the concept says | 1819 | +0.009 (+0.8) | +0.008 | -0.086 | -0.213 | -0.181 | 0.74 | 0 of 6 | no edge before costs |
| M5 | 5 | Order block retest | opposite | 1844 | +0.001 (+0.1) | +0.002 | -0.090 | -0.236 | -0.180 | 0.74 | 0 of 6 | no edge before costs |
| M5 | 5 | Liquidity sweep, then reverse | as the concept says | 620 | -0.024 (-1.3) | -0.009 | -0.116 | -0.264 | -0.221 | 0.69 | 0 of 6 | no edge before costs |
| M5 | 5 | Liquidity sweep, then reverse | opposite | 628 | +0.003 (+0.2) | -0.004 | -0.105 | -0.240 | -0.211 | 0.71 | 0 of 6 | no edge before costs |
| M5 | 5 | Fair value gap retest with the structure | as the concept says | 2774 | -0.000 (-0.0) | -0.003 | -0.101 | -0.215 | -0.192 | 0.72 | 0 of 6 | no edge before costs |
| M5 | 5 | Order block retest with the structure | as the concept says | 1236 | -0.013 (-1.0) | -0.025 | -0.117 | -0.237 | -0.213 | 0.70 | 0 of 6 | no edge before costs |
| M5 | 20 | Break of structure | as the concept says | 260 | +0.058 (+1.9) | -0.005 | -0.117 | -0.173 | -0.211 | 0.71 | 0 of 6 | no edge before costs |
| M5 | 20 | Break of structure | opposite | 260 | -0.037 (-1.3) | +0.020 | -0.085 | -0.269 | -0.186 | 0.74 | 0 of 6 | no edge before costs |
| M5 | 20 | Change of character | as the concept says | 185 | -0.066 (-1.9) | -0.063 | -0.121 | -0.224 | -0.207 | 0.71 | 0 of 6 | no edge before costs |
| M5 | 20 | Change of character | opposite | 185 | +0.019 (+0.5) | +0.014 | -0.066 | -0.186 | -0.150 | 0.78 | 0 of 6 | no edge before costs |
| M5 | 20 | Order block retest | as the concept says | 619 | -0.016 (-0.8) | -0.013 | -0.097 | -0.209 | -0.184 | 0.74 | 0 of 6 | no edge before costs |
| M5 | 20 | Order block retest | opposite | 614 | +0.009 (+0.5) | +0.019 | -0.071 | -0.197 | -0.155 | 0.78 | 0 of 6 | no edge before costs |
| M5 | 20 | Liquidity sweep, then reverse | as the concept says | 86 | -0.094 (-1.9) | +0.004 | -0.114 | -0.269 | -0.227 | 0.69 | 0 of 6 | no edge before costs |
| M5 | 20 | Liquidity sweep, then reverse | opposite | 87 | +0.070 (+1.3) | -0.064 | -0.122 | -0.169 | -0.201 | 0.72 | 0 of 6 | no edge before costs |
| M5 | 20 | Fair value gap retest with the structure | as the concept says | 1054 | +0.018 (+1.2) | +0.010 | -0.073 | -0.172 | -0.155 | 0.77 | 0 of 6 | no edge before costs |
| M5 | 20 | Order block retest with the structure | as the concept says | 158 | -0.033 (-0.9) | -0.055 | -0.123 | -0.209 | -0.212 | 0.70 | 0 of 6 | no edge before costs |
| M15 | - | Fair value gap forms | as the concept says | 1222 | +0.013 (+1.0) | +0.029 | -0.016 | -0.102 | -0.065 | 0.90 | 0 of 6 | no edge before costs |
| M15 | - | Fair value gap forms | opposite | 1229 | +0.016 (+1.2) | +0.004 | -0.041 | -0.095 | -0.096 | 0.85 | 0 of 6 | no edge before costs |
| M15 | - | Fair value gap retest | as the concept says | 1183 | +0.037 (+2.7) | -0.007 | -0.057 | -0.070 | -0.095 | 0.85 | 0 of 6 | edge smaller than the spread |
| M15 | - | Fair value gap retest | opposite | 1173 | -0.016 (-1.2) | -0.006 | -0.050 | -0.125 | -0.085 | 0.87 | 0 of 6 | no edge before costs |
| M15 | 20 | Break of structure | as the concept says | 88 | +0.092 (+1.8) | +0.003 | -0.038 | -0.030 | -0.092 | 0.86 | 1 of 6 | no edge before costs |
| M15 | 20 | Break of structure | opposite | 89 | -0.073 (-1.5) | -0.007 | -0.067 | -0.166 | -0.125 | 0.81 | 1 of 6 | no edge before costs |
| M15 | 20 | Change of character | as the concept says | 49 | +0.250 (+3.8) | -0.060 | -0.116 | +0.096 | -0.151 | 0.77 | 1 of 6 | failed confirmation |
| M15 | 20 | Change of character | opposite | 48 | -0.201 (-3.5) | +0.145 | +0.108 | -0.310 | +0.049 | 1.08 | 4 of 6 | no edge before costs |
| M15 | 20 | Order block retest | as the concept says | 203 | -0.026 (-0.8) | -0.026 | -0.065 | -0.139 | -0.116 | 0.81 | 0 of 6 | no edge before costs |
| M15 | 20 | Order block retest | opposite | 200 | +0.050 (+1.6) | +0.045 | +0.011 | -0.070 | -0.039 | 0.94 | 2 of 6 | no edge before costs |
| M15 | 20 | Liquidity sweep, then reverse | as the concept says | 26 | -0.100 (-1.0) | -0.051 | -0.083 | -0.201 | -0.145 | 0.78 | 1 of 6 | no edge before costs |
| M15 | 20 | Liquidity sweep, then reverse | opposite | 26 | +0.241 (+2.2) | -0.021 | -0.054 | +0.160 | -0.081 | 0.88 | 3 of 6 | failed confirmation |
| M15 | 20 | Fair value gap retest with the structure | as the concept says | 306 | +0.045 (+1.8) | -0.039 | -0.081 | -0.055 | -0.124 | 0.80 | 0 of 6 | no edge before costs |
| M15 | 20 | Order block retest with the structure | as the concept says | 50 | +0.036 (+0.5) | -0.013 | -0.047 | -0.088 | -0.104 | 0.83 | 1 of 6 | no edge before costs |
| M15 | 50 | Break of structure | as the concept says | 39 | +0.191 (+2.5) | +0.139 | +0.071 | +0.088 | +0.046 | 1.08 | 3 of 6 | failed confirmation |
| M15 | 50 | Break of structure | opposite | 39 | -0.034 (-0.5) | -0.160 | -0.188 | -0.141 | -0.232 | 0.66 | 2 of 6 | no edge before costs |
| M15 | 50 | Change of character | as the concept says | 26 | +0.110 (+1.1) | +0.054 | +0.031 | +0.001 | -0.015 | 0.98 | 3 of 6 | no edge before costs |
| M15 | 50 | Change of character | opposite | 26 | -0.234 (-2.8) | +0.058 | +0.036 | -0.301 | +0.015 | 1.02 | 4 of 6 | no edge before costs |
| M15 | 50 | Order block retest | as the concept says | 83 | +0.013 (+0.3) | -0.123 | -0.152 | -0.080 | -0.186 | 0.71 | 0 of 6 | no edge before costs |
| M15 | 50 | Order block retest | opposite | 82 | +0.037 (+0.7) | +0.108 | +0.070 | -0.053 | +0.027 | 1.05 | 4 of 6 | no edge before costs |
| M15 | 50 | Liquidity sweep, then reverse | as the concept says | 7 | -0.105 (-0.5) | -0.168 | -0.189 | -0.246 | -0.283 | 0.58 | 0 of 6 | too few trades |
| M15 | 50 | Liquidity sweep, then reverse | opposite | 7 | +0.296 (+1.1) | -0.044 | -0.143 | +0.200 | -0.169 | 0.75 | 1 of 6 | too few trades |
| M15 | 50 | Fair value gap retest with the structure | as the concept says | 141 | +0.045 (+1.2) | -0.006 | -0.050 | -0.048 | -0.089 | 0.85 | 1 of 6 | no edge before costs |
| M15 | 50 | Order block retest with the structure | as the concept says | 11 | -0.134 (-1.0) | -0.142 | -0.201 | -0.242 | -0.222 | 0.65 | 3 of 6 | too few trades |

## Hindsight against live

Hindsight: the library is run once on a finished chart of 2,000 candles and every signal is traded at the bar where it is drawn. Live: the same signal, taken only when the library reports it for the last closed bar. Same stop, target and hold. Mean R per trade at zero cost.

| Timeframe | Swing | Signal | Hindsight: trades a year | Hindsight: discovery R | Hindsight: confirmation R | Hindsight: win rate | Live: trades a year | Live: discovery R | Live: confirmation R | Live: win rate |
|---|---|---|---|---|---|---|---|---|---|---|
| M5 | 5 | Break of structure | 1506 | +0.007 | -0.021 | 36% | 1034 | -0.007 | -0.024 | 36% |
| M5 | 5 | Change of character | 1014 | +0.004 | -0.010 | 36% | 773 | -0.008 | -0.020 | 36% |
| M5 | 5 | Liquidity sweep, then reverse | 1251 | -0.017 | +0.005 | 37% | 614 | -0.024 | -0.009 | 36% |
| M5 | 20 | Break of structure | 498 | +0.048 | +0.024 | 37% | 260 | +0.058 | -0.005 | 36% |
| M5 | 20 | Change of character | 306 | -0.021 | -0.032 | 36% | 185 | -0.066 | -0.063 | 34% |
| M5 | 20 | Liquidity sweep, then reverse | 181 | -0.116 | -0.052 | 35% | 86 | -0.094 | +0.004 | 36% |
| M15 | 20 | Break of structure | 169 | +0.069 | +0.067 | 38% | 88 | +0.092 | +0.003 | 36% |
| M15 | 20 | Change of character | 93 | +0.120 | -0.072 | 36% | 49 | +0.250 | -0.060 | 35% |
| M15 | 20 | Liquidity sweep, then reverse | 56 | -0.104 | -0.055 | 35% | 26 | -0.100 | -0.051 | 36% |
| M15 | 50 | Break of structure | 67 | +0.225 | +0.052 | 39% | 39 | +0.191 | +0.139 | 41% |
| M15 | 50 | Change of character | 36 | +0.103 | +0.087 | 42% | 26 | +0.110 | +0.054 | 39% |
| M15 | 50 | Liquidity sweep, then reverse | 10 | -0.145 | -0.004 | 37% | 7 | -0.105 | -0.168 | 34% |
