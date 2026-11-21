# XAUUSD ICT model monitor (2026-11-21 11:11 UTC)

Model `xauusd_ict_lgbm_20261120`, trained 2011-01-03 .. 2026-11-20, gates FAILED (not used for signals). Result: **ALERT**.

Alerts:

- atr_pct: PSI 1.97
- spread_risk: PSI 1.80

## Performance against the walk-forward

No graded trades given (--trades).

## Feature drift: last 90 days (356 candidates) vs training (22670 candidates)

PSI above 0.1 is a warning and above 0.25 an alert, judged on the model's 10 most important features.

| Feature | Top | PSI | Level | Training median | Recent median |
|---|---|---|---|---|---|
| atr_pct | yes | 1.966 | ALERT | 0.061 | 0.103 |
| spread_risk | yes | 1.796 | ALERT | 0.134 | 0.057 |
| atr_ratio_day | yes | 0.158 | warn | 0.906 | 0.948 |
| atr_ratio_week | yes | 0.123 | warn | 0.896 | 0.954 |
| ny_hour | yes | 0.043 |  | 9.583 | 10.167 |
| ob_dist_atr | yes | 0.042 |  | 0.272 | 0.233 |
| leg_atr | yes | 0.037 |  | 3.644 | 3.520 |
| opp_pool_r | yes | 0.036 |  | 1.330 | 1.429 |
| ret_1h_atr | yes | 0.025 |  | 1.687 | 1.575 |
| risk_atr | yes | 0.015 |  | 2.465 | 2.409 |
| spread_atr |  | 2.985 |  | 0.333 | 0.131 |
| asia_range_atr |  | 0.514 |  | 5.823 | 8.391 |
| day_range_atr |  | 0.091 |  | 9.545 | 10.633 |
| mss_range_atr |  | 0.082 |  | 1.433 | 1.281 |
| leg_max_body_atr |  | 0.064 |  | 1.414 | 1.318 |
| mss_body_atr |  | 0.061 |  | 1.020 | 0.902 |
| pd_week |  | 0.043 |  | 0.503 | 0.518 |
| entry_dist_atr |  | 0.041 |  | 1.132 | 1.041 |
| mss_close_beyond_atr |  | 0.040 |  | 0.375 | 0.346 |
| bars_sweep_to_mss |  | 0.033 |  | 7.000 | 7.000 |
| sweep_depth_atr |  | 0.032 |  | 1.008 | 0.969 |
| ema_h4_50_atr |  | 0.031 |  | 0.160 | 1.036 |
| ema_h1_50_atr |  | 0.029 |  | 0.485 | -0.025 |
| fvg_size_atr |  | 0.029 |  | 0.425 | 0.404 |
| ret_1d_atr |  | 0.028 |  | 0.406 | -0.687 |
| ret_4h_atr |  | 0.025 |  | 0.416 | 0.036 |
| ema_h1_50_slope_atr |  | 0.024 |  | -0.110 | -0.161 |
| ema_h1_20_atr |  | 0.024 |  | 0.638 | 0.393 |
| sweep_wick_ratio |  | 0.024 |  | 0.291 | 0.264 |
| day_move_atr |  | 0.023 |  | 0.663 | 0.632 |
| bars_extreme_to_now |  | 0.020 |  | 8.000 | 7.000 |
| leg_bars |  | 0.020 |  | 8.000 | 7.000 |
| pd_prev_day |  | 0.019 |  | 0.522 | 0.475 |
| mss_body_ratio |  | 0.015 |  | 0.737 | 0.711 |
| pool_age_bars |  | 0.014 |  | 13.000 | 12.500 |
| pool_kind |  | 0.013 |  | 4.000 | 4.000 |
| ote_fib |  | 0.011 |  | 0.376 | 0.366 |
| session_sweep |  | 0.010 |  | 2.000 | 2.000 |
| session_now |  | 0.008 |  | 2.000 | 2.000 |
| n_pools_swept |  | 0.006 |  | 1.000 | 1.000 |
| weekday |  | 0.005 |  | 2.000 | 2.000 |
| fvg_age_bars |  | 0.004 |  | 0.000 | 0.000 |
| target_before_pool |  | 0.001 |  | 0.000 | 0.000 |
| fvg_count_leg |  | 0.001 |  | 2.000 | 2.000 |
| direction |  | 0.000 |  | -1.000 | 1.000 |
| in_killzone |  | 0.000 |  | 0.000 | 0.000 |
| asset |  | 0.000 |  | 1.000 | 1.000 |
| ob_overlap |  | 0.000 |  | 1.000 | 0.000 |
| breaker_overlap |  | 0.000 |  | 1.000 | 1.000 |
| in_ote |  | 0.000 |  | 0.000 | 0.000 |
