# XAUUSD ICT model: every variant tested (2026-11-21)

Walk-forward 2014-2026 (26 six-month folds, 20 for session pools only), trained from 2011, one-day embargo,
thresholds chosen on validation only, one open plan per side, net R after Dukascopy spread and 0.5 x spread
slippage on stop and time exits. Each variant changes one thing from the plan's model; all six were fixed in
docs/ml-plan.md section 8 before any result was seen and each was run once. Details per variant:
`ml/reports/xauusd_walkforward*.md`.

| Variant | Model trades | Model exp. R | Model total R | Max DD R | AUC / shuffled control | All candidates exp. R | Spread cut-off exp. R | Gate 5 (Exness) | Gates passed |
|---|---|---|---|---|---|---|---|---|---|
| 2R target, limit at FVG edge, all pools (the plan) | 492 | -0.101 | -49.5 | 55.8 | 0.574 / 0.498 | -0.212 | -0.018 | 92 trades, -0.094R, PF 0.82 | 0 of 5 |
| 1.5R target | 407 | -0.028 | -11.4 | 24.4 | 0.546 / 0.503 | -0.192 | -0.090 | 191 trades, -0.013R, PF 0.97 | 0 of 5 |
| 3R target | 481 | -0.134 | -64.2 | 71.7 | 0.610 / 0.500 | -0.227 | -0.061 | 0 trades | 0 of 5 |
| limit at FVG midpoint | 204 | -0.105 | -21.4 | 25.6 | 0.574 / 0.498 | -0.227 | -0.100 | 0 trades | 0 of 5 |
| market entry on the next candle | 77 | -0.156 | -12.0 | 14.0 | 0.550 / 0.496 | -0.154 | -0.050 | 0 trades | 0 of 5 |
| session/day pools only | 173 | -0.041 | -7.0 | 15.2 | 0.576 / 0.489 | -0.231 | -0.086 | 0 trades | 0 of 5 |

**Verdict: no variant passes any gate.** The model does rank setups better than chance in every variant (AUC
0.55-0.61 against 0.49-0.50 for the shuffled control), and its probabilities are well calibrated, but even its most
confident tenth of setups loses money after costs. The required edge is +0.10R per trade; the best variant reaches
-0.028R. Following the plan, the model does not go to a forward test, and no further variants are tried on this data:
more trials would only find a lucky one.
