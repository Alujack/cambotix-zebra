# Zebra ML: ICT model for XAUUSD — plan

Status: **all phases built and run (2026-11-21). Verdict: the gates failed, so nothing goes live; see the verdict below the roadmap table.**

## 1. Goal

Train a machine-learning model that is based on ICT concepts and learns which XAUUSD setups have historically
made money, then (after it passes the gates in section 8) run it through the existing Zebra pipeline as a
forward-tested signal source.

Design rule, the same one the repo already follows: **the rule engine says what happened, the model only decides
which setups to take.** The model never places orders; the analyzer, grader and ledger stay in charge.

```text
XAUUSD M1 history (Dukascopy, full)  ->  M5 bars
  -> ICT detection engine: liquidity pools, sweep, MSS, FVG, OB, breaker, OTE, sessions
  -> candidate setups (limit at FVG edge, stop beyond sweep, 2R target) + ~50 ICT features each
  -> labels from app.grader.simulate on M1 with spread (exactly how live trades are graded)
  -> LightGBM: P(win | setup) -> take / skip
  -> walk-forward test vs baselines and a shuffled-label control
  -> (only if it passes) ml/predict.py in the feeder -> analyzer -> Telegram "forward test"
```

## Roadmap phases vs this plan

The project roadmap uses seven phases. This plan was written with its own numbering (Phase 0–6), so the
table below is the translation, with where each phase stands on disk today (2026-11-21).

| Roadmap phase | This plan | State now |
|---|---|---|
| 1. Data collection — XAUUSD OHLCV, timestamp checks, multi-timeframe sets | §3 (Phase 0) | **Done 2026-11-21.** 8,010,604 M1 bars 2003-05-05 .. 2026-11-20 in `.local/history_dukascopy_full/` with m5/m15/h1/h4/d1/w1; `ml/check_history.py` PASSED. Usable range and spread caveats in §3 |
| 2. ICT detection engine — concepts as testable modules | §4 (Phase 1) | **Done 2026-11-21.** Each concept a tested function in `ml/ict_features.py`; full history: 28,493 candidates 2003–2026, all hard checks pass (`ml/reports/xauusd_ict_candidates.md`) |
| 3. Dataset generation — labeled samples, validated | §5 (Phase 2) | **Done 2026-11-21.** `ml/data/xauusd_ict.parquet`: 26,882 candidates 2008–2026, 16,826 filled; labels identical to `scripts/backtest.py` (129 of 129 comparable trades). Raw baseline −0.182R per filled trade (`ml/reports/xauusd_ict_dataset.md`) |
| 4. ML training — setup classification, outcome prediction | §6 (Phase 3) | **Done 2026-11-21.** `ml/train.py`: LightGBM P(win), 26 walk-forward folds 2014–2026, out-of-sample AUC 0.574 vs 0.498 for the shuffled control |
| 5. Backtesting — unseen periods, spread and slippage | §6 walk-forward, §7 report, §8 gates | **Done 2026-11-21: FAILED all five gates**, and so did all five pre-listed variants (`ml/reports/xauusd_variants.md`). Best: −0.028R per trade against the required +0.10R |
| 6. Live inference — live data, real-time signals | §9 (Phase 5) | **Built, locked.** `ml/predict.py` scores the latest bar and refuses any model that failed the gates; not wired into the feeder, because no model passed |
| 7. Monitoring — performance, drift, degradation | §10 (Phase 6) | **Built.** `ml/monitor.py` (live R vs walk-forward, feature drift), `ml/retrain.py` (monthly cycle; a failed model never replaces a passing one) |

Two roadmap items the plan did not cover before this mapping: **multi-timeframe datasets** (roadmap 1) are
only partly there, since the engine works on M5 resampled from M1 and the HTF bias uses M5 EMAs as a stand-in
for H1/H4; real H1/H4 resampling is listed under "Later" in §4. **Slippage** (roadmap 5) is now a test-time
assumption in §6.

## Verdict (2026-11-21): no tradable edge; the model stays off

The whole roadmap ran end to end. The model learns something real but not enough to pay for trading costs:

- **Skill is real but small.** Out-of-sample AUC 0.574 against 0.498 for the same model trained on shuffled
  labels, and well calibrated: the predicted win rate tracks the actual one decile by decile.
- **No subset makes money.** Even the model's most confident tenth of setups loses 0.046R per trade after spread
  and slippage. The final model found no profitable threshold on its own validation slice.
- **Every pre-listed variant fails every gate** (`ml/reports/xauusd_variants.md`): 1.5R and 3R targets, FVG
  midpoint entry, market entry, session/day pools only. Best: 1.5R target at −0.028R per trade; required +0.10R.
- **Spread is the main cost.** The model's top feature is spread/risk (26% of gain), and a plain spread/risk
  cut-off did as well as the model (−0.018R). On Exness's cheaper spread the same fold models still lost
  (−0.094R, 92 trades).
- **Drift worth watching.** In the last 90 days gold's ATR is about 1.7x its training average and spread/risk is
  less than half (PSI 1.8–2.0): setups are cheaper to trade than ever, and 2026 is the least bad year (−0.083R
  unfiltered). That is a reason to re-run `python -m ml.retrain` in a few months, not a reason to trade now.

As the plan says: report it plainly, no forward test, no more variants on this data. `ml/predict.py` refuses the
saved model; `ml/retrain.py` will promote a future model only if it passes all five gates.

## 2. Where we start

Already in the repo:

| Asset | Notes |
|---|---|
| `.local/history/XAUUSD_m1.csv` | Exness MT5, Nov 2023 – Nov 2026, ~1.06M M1 bars with spread |
| `scripts/ict_engine.py` | ICT 2022 model on M5 (killzone sweep → MSS → FVG limit) |
| `app/grader.py` | Deterministic M1 grader with spread, worst-case inside ambiguous candles |
| `scripts/backtest.py` | Replays engines through the live rules and grader |
| `scripts/pull_dukascopy.py` | Dukascopy downloader with cache (needs changes, see Phase 0) |

Evidence from the README: the ICT rules **lost money on gold in every variant and every year** (-5R to -25R),
and CRT on gold is +33.5R over 375 trades with losing years. So the honest starting hypothesis is: *raw ICT on
gold has no edge; the question is whether a model can find a profitable subset.*

**Draft code already written (paused at your request):** before you asked for a plan I had started an
`ml/` folder (`data.py`, `ict_features.py`, `labels.py`, `dataset.py`, `train.py`) and built a first dataset
from the 3-year Exness files. Training has **not** been run. A quick look at the gold slice of that dataset:

| Gold, Nov 2023 – Nov 2026 (draft dataset) | Value |
|---|---|
| ICT candidates found (any session, all pools) | 4,328 |
| Limits that filled | 2,833 |
| Win rate at 2R | 35.5% |
| Average result | **-0.055R per trade** (break-even at 2R needs ~34–36% after spread) |
| ict_engine-style subset (killzone, session pools) | 197 trades, -17.2R |

So the setups are close to break-even before filtering. That makes them a reasonable thing to try a filter on,
but there's no guarantee of an edge. You decide whether to keep that draft as the starting point (recommended)
or remove it.

## 3. Phase 0 — Download the full XAUUSD history (first step)

**Status 2026-11-21: done.** Pull finished in about 3.5 hours with no refused files; the check PASSED
(report: `ml/reports/xauusd_history_check.md`).

| Result | Value |
|---|---|
| M1 bars | 8,010,604, first 2003-05-05 00:01 UTC, last 2026-11-20 21:59 UTC |
| Frames | m5 1,679,641 · m15 567,203 · h1 142,817 · h4 37,814 · d1 7,334 · w1 1,229, all equal to resampled M1 |
| Bad timestamps / prices / Saturday bars | 0 / 0 / 0 |
| Missing trading hours | 1,207: 40 full days (Christmas, New Year, Good Friday, 2013 on) + 150 partial (US holiday early closes) |
| Overlap with Exness Nov 2023 – Nov 2026 | 1,063,220 shared minutes; median close difference 0.15 (p99 0.63) |

**What the check found that matters for Phase 2:**

1. **Use 2007 onward for the dataset.** 2003–2004 have only about 70–75% of London/NY minutes, 2005 about 88%,
   2006 about 95%; from 2007 every year is complete. Sparse minutes would fake sweeps and gaps. Keep 2003–2006 as
   indicator warm-up only. That still leaves about 20 years.
2. **Spread before 2011 is coarse.** 2003–2010 use under 600 distinct values and never exceed 0.706, so news
   spikes are missing; from 2011 it is a real spread (max 3–15). Grade 2003–2010 with a floor of the year's p99
   so those years are not flattered, or start the dataset at 2011 if the floor still looks optimistic.
3. **2012 has 8,145 zero spreads** (2.2% of bars, scattered). Replace with that hour's median spread when grading.
4. **Dukascopy is about 3× Exness on spread** in the overlap (2025: 0.58 vs 0.16; 2026: 0.66 vs 0.26), so labels
   graded here are conservative for your broker. Gate 5 still re-scores on Exness.
5. 2020 (Covid crash) and 2025–2026 have real spread spikes up to about 15; those are kept.

**Source:** Dukascopy (free; BID and ASK minute candles, so spread is real, not assumed). Gold history there starts
in May 2003; we pull everything it serves and record the real first date.

**Changes made to `scripts/pull_dukascopy.py`:**

1. **`--out DIR`.** Full history goes to `.local/history_dukascopy_full/`; the default `.local/history/` (the
   Exness files the backtests use) is untouched.
2. **`--from YYYY-MM-DD` and `--to`.** `--days` still works for short pulls and is unchanged in behaviour.
3. **Year by year.** Each year is downloaded, written to `years/XAUUSD_<frame>_<year>.csv` and released, so
   memory stays flat; the merge step streams the yearly files into `XAUUSD_<frame>.csv` and joins the one bar that
   can straddle New Year (W1). A rerun skips finished years; a year with refused files is not written and the merge
   is skipped, so a partial run never produces a half-filled merged file.
4. **Multi-timeframe output.** `m1, m5, m15, h1, h4, d1, w1` (m5 and h1 are new; the ML engine works on M5 and the
   HTF bias can later use real H1/H4 instead of EMA stand-ins). All built from the same M1, D1 at 00:00 UTC, W1 on
   Sunday, the same conventions as `scripts/pull_history.py`.
5. The on-disk cache (`.local/dukascopy/`) is kept, so reruns only fetch what is missing.

**Run (Windows, measured at about 1.3 s per file with 8 workers, 4–5 hours for 20 years):**

```powershell
python scripts\pull_dukascopy.py --symbol XAUUSD --from 2003-05-01 --out .local\history_dukascopy_full --workers 8
python ml\check_history.py --symbol XAUUSD --folder .local\history_dukascopy_full --compare .local\history
```

**Data checks (`ml/check_history.py`, tests in `tests/test_check_history.py`), must pass before Phase 1:**

- Reject: duplicate, out-of-order or off-minute timestamps; prices of zero, high < low, open/close outside the bar;
  any Saturday bar; a hole longer than 5 trading days; a saved frame that differs from pandas resampling of the M1.
- Report: missing trading hours (Mon–Fri 00:00–20:59 UTC) by date and by year, full missing days listed so
  holidays can be told from data loss; spread per year (median, 99th percentile, zeros, values over 20× the median).
- **Overlap vs Exness, Nov 2023 – Nov 2026:** minutes in both files, median and p99 close difference, median spread
  on each side, per year. On a five-day smoke test Dukascopy's gold spread was about 0.49 vs Exness's 0.16 and the
  median close difference 0.17, so Dukascopy-graded results will be *more* conservative than the broker's and
  gate 5 (re-score on Exness) stays necessary.

Output: `.local/history_dukascopy_full/XAUUSD_{m1,m5,m15,h1,h4,d1,w1}.csv`, `XAUUSD_meta.json` (source, range,
bars per frame, check summary), `XAUUSD_check.json` and `ml/reports/xauusd_history_check.md`.

## 4. Phase 1 — ICT detection engine (`ml/ict_features.py`)

**Status 2026-11-21: done.** On the full Dukascopy history the engine found 28,493 candidates in 11 seconds with no
rejects (no stop or target on the wrong side, no duplicates, no missing required feature), BUY share 49–51% every
year, killzone share about 30%. 2003–2006 run at 0.4–1.7 candidates a day against a median of 5.4, and 2007 at 3.0:
until mid-2007 Dukascopy's M5 bars are about twice as wide relative to price (17 vs 8 basis points), so the early
feed is built differently. Candidates are therefore used from 2008 on; earlier years are warm-up only.

- Each concept is its own function with its own tests: `session_of` / `in_killzone` (session clock),
  `trading_days` (17:00 New York roll), `pivots` (swings), `SessionRange` (session pools), `find_fvg` /
  `count_fvgs`, `order_block`, `retracement` (OTE), and `detect`, the sweep → MSS → FVG state machine.
- Tests (`tests/test_ict_features.py`): the hand-built London session from `tests/test_ict_engine.py` must give
  the same plan in both engines; the SELL mirror must give the same features; no candidate may change when the
  future is cut off or rewritten; every setup `scripts/ict_engine.py` finds on long random data must be a
  candidate with the same entry, stop and target. On the cached gold year all 65 of 65 killzone-engine setups
  matched.
- Three changes to the draft, found while testing:
  1. **Day roll on pandas 3.** The draft divided the timestamp by a fixed number of nanoseconds; pandas 3 stores
     seconds, so every bar got the same trading day and previous-day high/low pools never existed (no error,
     just missing pools). Fixed. The committed draft dataset was built on pandas 2 and has its PDH/PDL rows.
  2. **Pool naming across a sweep.** When a sweep took a session or day pool and then a minor swing pool
     deeper, the draft named it after the swing. 19 of the 65 killzone-engine setups on the cached year were
     labelled "swing" for that reason, which breaks the "killzone + session/day pools" baseline in §6. Now the
     most significant pool taken in the run keeps the name. Entry, stop and target are unchanged; the pool
     features of the draft dataset are stale and it gets rebuilt in Phase 2 anyway.
  3. **Stale session pools.** A session that began on one trading day and (after a data gap) ended on another
     is dropped instead of being published as today's pool.
- `python ml/check_candidates.py --symbol XAUUSD --folder .local/history_dukascopy_full` writes
  `ml/reports/xauusd_ict_candidates.md`: candidates per year, per trading day, BUY share, killzone share, pool
  mix, missing optional features. It rejects impossible plans and flags years far from the median rate.
- `pip install -r requirements-ml.txt` (numpy, pandas) for everything in `ml/`; CI installs it, the analyzer
  container does not and skips those tests.

Same geometry as `scripts/ict_engine.py`, so results are comparable, but broader so the model has thousands of
examples:

- **Liquidity pools:** previous day high/low (NY 17:00 roll), Asia (20:00–24:00 NY), London (02:00–05:00),
  NY AM (08:30–11:00), M5 swing highs/lows (6/6 fractal, fresh for one day). A pool is spent once traded through.
  The most significant pool taken (day, London, Asia, NY AM, swing) names the sweep.
- **Sweep → MSS → FVG:** price trades beyond a fresh pool; within 3 hours a close breaks the last 2/2 pivot formed
  before the extreme; the latest FVG of at least 0.1 ATR in that leg appears by the candle after the shift.
- **Plan:** limit at the FVG's near edge, stop beyond the sweep + 0.1 ATR, one target at 2R, at least 0.3 ATR risk.
- **Any session.** The killzone becomes a feature instead of a hard filter.

**Features (50), all computed from bars up to the signal bar only:**

| Group | Features |
|---|---|
| Setup identity | direction, pool kind, pools swept in one candle, pool age, killzone flag, session at sweep / now, NY hour, weekday |
| Sweep | depth beyond pool (ATR), wick share of the sweep candle, bars sweep → MSS |
| Displacement / MSS | MSS candle body and range (ATR), body ratio, close beyond the broken level, leg size, biggest body in the leg |
| PD arrays | FVG size, FVGs in the leg, FVG overlaps the order block, distance to the OB, breaker overlap (unicorn), OTE fib level and 62–79% flag |
| Plan and cost | risk in ATR, spread as a share of risk, distance of price from the limit, nearest opposing pool in R, is 2R before that pool |
| Volatility | ATR % of price, ATR vs its 1-day and 1-week averages |
| HTF bias | price vs M5 EMAs approximating H1 EMA20 / H1 EMA50 / H4 EMA50, H1 EMA50 slope |
| Premium / discount | position in the previous day's range and in the 1-week range (in the trade's direction) |
| Daily context | move since the day's open, day range, Asia range |
| Momentum | return over the last 1h / 4h / 1 day (ATR) |

Later (not in the first version): SMT divergence vs XAGUSD/DXY, news proximity (needs a historical calendar),
H1/H4 structure from real resampled bars.

## 5. Phase 2 — Dataset and labels (`ml/labels.py`, `ml/dataset.py`)

**Status 2026-11-21: done.** `python -m ml.dataset` builds `ml/data/xauusd_ict.parquet` (gitignored) with
`xauusd_ict.meta.json` beside it and the report `ml/reports/xauusd_ict_dataset.md`. Tests: `tests/test_labels.py`.

How it is built:

- Each candidate becomes the plan the analyzer would freeze for an ICT signal (limit, 120-minute entry expiry,
  360-minute hold, one 2R target) and is graded by **`app.grader.simulate` on M1 with spread**. A weekend inside
  the window gets the candles after the gap, as the live grader does. Unfilled limits score 0R.
- Spread first goes through `ml.data.repair_spread`: 8,145 zero spreads in 2012 get their hour's median, and every
  bar before 2011 is raised to at least its year's 99th-percentile spread (0.60–0.81), because that era's recorded
  spread has no news spikes. Rows carry `spread_coarse` = 1 for 2008–2010.
- Detection runs over the whole 2003–2026 history, so 2003–2007 is warm-up; candidates are kept from 2008-01-01.
- The builder refuses a history folder that `ml/check_history.py` has not passed.

**Validation against `scripts/backtest.py`:** the killzone ICT engine's setups on the Exness 3-year gold file were
graded through backtest.py (analyzer rules, `ledger.plan_record`, grader) and through `ml.labels`. All 129
comparable trades have the same R and the same exit; the 130th falls inside the detector's warm-up at the start of
the file. A test repeats this on 150 days of random data with the open-plan limit off.

**Result: the raw candidates lose in every year.**

| | Filled | Win rate | Expectancy | Total |
|---|---|---|---|---|
| All, 2008–2026 | 16,826 | 30.9% | −0.182R | −3,064R |
| 2011–2026 (real spread) | 14,302 | 32.0% | −0.152R | −2,174R |
| 2008–2010 (p99 spread floor) | 2,524 | 24.7% | −0.353R | −890R |
| Killzone + session/day pools (the ict_engine-style baseline) | 2,476 | 33.0% | −0.159R | −394R |

Spread is the biggest single driver. Median spread is 14% of the risk; by fifths of spread/risk the expectancy runs
−0.036R, −0.116R, −0.180R, −0.188R, −0.390R. On Exness's cheaper spread the same setups were about −0.055R
(the draft dataset, section 2). So:

1. **Train on 2011 on.** The p99 floor makes 2008–2010 cost about twice as much per trade; a model trained on them
   learns the floor, not the market. Keep 2008–2010 as a stress test only.
2. **Expect `spread_risk` and `risk_atr` to dominate** the model. That is legitimate (wider stops pay less spread),
   but it means the model mostly learns "take setups with room", which gate 2 has to show beats a simple
   spread/risk cut-off and not just the unfiltered baseline. Add that cut-off as baseline (d) in section 6.
3. Gate 5 (re-score on Exness) matters more than planned: Dukascopy costs about 0.1R a trade more than the broker.

## 6. Phase 3 — Model training (`ml/train.py`)

**Status 2026-11-21: done** (`python -m ml.train`, report `ml/reports/xauusd_walkforward.md`, tests
`tests/test_ml_model.py`). As below, with: training from 2011, test folds of 6 months from 2014 (26 folds), net R
with slippage, baselines (a)–(d), gates computed in code, the same fold models re-scored on Exness candidates
(gate 5), and the final model scored on 2008–2010 as a stress test. Variants: `--data` (a dataset built with
`--rr` or `--entry`), `--pools session`, `--tag`. Result: see the verdict at the top.

- **Model:** LightGBM binary classifier, P(win) for filled trades. Conservative settings (15 leaves, at least 150
  samples per leaf, L2, early stopping) because market data is noisy and small.
- **Walk-forward, chronological only.** Expanding window, test folds of 6 months (with 20 years there are
  ~30 out-of-sample folds). Train only on trades that **finished** before the fold starts, plus a one-day embargo.
  No random splits.
- **Threshold:** chosen on the last 20% of each training window only (best mean R × √trades, minimum 150 trades).
  If no threshold made money there, the model takes no trades in that fold.
- **Execution realism in tests:** one open plan per side at a time (the analyzer's limit), unfilled limits score 0R
  and still block the slot until they expire.
- **Slippage:** limit entries fill at the limit (or not at all), so slippage applies to the stop and to any market
  exit at hold expiry. Score every fold twice, with 0 and with a fixed slippage of 0.5 × median spread per side
  on those exits; the gates in §8 must hold with slippage on.
- **Baselines in every fold:** (a) every candidate, (b) ict_engine-style subset (killzone + session/day pools),
  (c) **the same model trained on shuffled labels**. Anything the shuffled model also "finds" is noise.
  (d) **a plain spread/risk cut-off** chosen on the same validation slice, since spread is the strongest single
  driver of the raw result (section 5).
- **Regime checks:** results by year, by session, by side, and pre/post 2020 (gold's volatility and price level
  changed a lot; features are ATR-normalised so they carry across years).
- Tracked runs: parameters, data range and results saved to `ml/reports/` (MLflow later, if wanted).

## 7. Phase 4 — Report

`ml/reports/xauusd_walkforward.md`: out-of-sample AUC vs the control, the results table for each policy (trades,
win rate, expectancy, total R, profit factor, max drawdown), per fold / year / session / side, equity curve,
feature importance, and the saved model's training range and threshold.

## 8. Go / no-go gates before any live use

The model moves to a demo forward test only if **all** of these hold on out-of-sample folds:

1. Expectancy > +0.10R per trade after spread, and profit factor > 1.2.
2. Beats both baselines and the shuffled control by a clear margin (control AUC ≈ 0.50, model meaningfully above).
3. Positive in at least 60% of folds and in the most recent 2 years, not only in old data.
4. Max drawdown no worse than 15R, and at least ~100 trades a year (enough to judge it).
5. Still holds when re-scored on the Exness 2023–2026 data (broker prices and spreads).

If it fails, the plan is to report it plainly and change one thing at a time (target R, entry at FVG midpoint
instead of edge, market entry, session pools only), never tuning on the test folds.

## 9. Phase 5 — Inference and integration (only after the gates)

**Status 2026-11-21: inference built, integration not done (the gates failed).** `python -m ml.predict` loads the
promoted model and scores the latest closed M5 bar; it raises `ModelRefused` for a model that failed the gates or
has no threshold (`--allow-failed-gates` for research). Its lookback is 15,000 M5 bars, not 3,000: the H4 EMA50
proxy spans 2,400 bars and would be about 8% unconverged on 3,000, so live features would differ from training
(a test checks they match). The feeder flag and `ict_ml` analyzer rules below are the remaining step for a model
that passes.

- `ml/predict.py`: loads `ml/models/xauusd_ict_lgbm.txt` + its JSON (features, threshold, training range),
  runs the detection engine on the latest ~3,000 M5 bars and returns setups on the just-closed bar with their
  probability.
- `scripts/mt5_feeder.py`: optional `--models ict_ml`, posts setups above the threshold.
- `app/domain.py`: a new model `ict_ml` with its own rule checks (stop beyond the sweep, entry at the FVG edge,
  minimum R:R), so it doesn't fall under ICT's killzone-only, EURUSD-only rules. Messages tagged
  *ICT ML · forward test* with the probability.
- Grader and ledger unchanged: the forward test is judged on the same graded record as everything else.
- Demo account only. Telegram signals stay manual-review.

## 10. Phase 6 — Monitoring and retraining

**Status 2026-11-21: built.** `python -m ml.monitor [--trades graded.csv]`: live R against the walk-forward
expectation saved with the model (alert below two standard errors or outside the 95% win-rate band, from 50
trades) and feature drift of the last 90 days against the training data (PSI, alert above 0.25 on the top-10
features); exit code 1 on an alert. `python -m ml.retrain`: pull → check → datasets → train → monitor; models are
versioned by training end date and the pointer moves only to a model that passes.

- Weekly: compare live graded results with what the walk-forward predicted (win rate, expectancy,
  probability calibration). Alert if 50 live trades fall outside the expected range.
- Retrain monthly with an expanding window; a new model replaces the old one only if it passes the same gates.
- Model files versioned by training end date; the ledger records which version produced each signal.

## 11. Later

- Other symbols (EURUSD 6y Dukascopy, the FX majors, indices) with results reported per symbol.
- A sequence model (TCN/LSTM in PyTorch on the RTX 3070 Ti) only after LightGBM is validated, and only kept if it
  beats LightGBM out of sample.
- Optional LLM explanation of each signal through the existing Ollama/OpenAI agent.

## 12. Risks

- **There may be no edge.** The ICT rules lost on gold in every backtest so far; ML can filter, it can't invent
  an edge that isn't in the data.
- **Overfitting.** Mitigated by walk-forward, embargo, thresholds chosen only on validation, the shuffled control
  and the gates. Never pick settings by looking at test results.
- **Broker difference.** Dukascopy prices and spreads differ from Exness; Phase 0's overlap check measures it and
  gate 5 re-tests on Exness data.
- **Account size.** At $1,000 and 0.25% risk ($2.50), gold's typical M5 stop (~2–3 ATR) often needs less than the
  0.01-lot minimum allows; sizing has to be checked per signal or the risk raised.

## 13. Decisions for you

1. Keep the draft `ml/` code as the starting point, or remove it and start clean from this plan?
2. Full history from Dukascopy (recommended), or keep only the Exness 3-year file?
3. Target and holding: keep the ICT engine's 2R / 120-min expiry / 6-hour hold, or also test 1.5R and 3R?
4. Gate thresholds in section 8: accept as written?

## Build order once approved

| Step | Deliverable | Done when |
|---|---|---|
| 0 | `pull_dukascopy.py` `--out`/`--from`/yearly files; `ml/check_history.py` | **Done 2026-11-21**: full XAUUSD M1 downloaded, checks pass |
| 1 | `ml/ict_features.py` + tests (no-lookahead, FVG/MSS cases); `ml/check_candidates.py` | **Done 2026-11-21**: tests pass; full-history counts sane from 2008 |
| 2 | `ml/labels.py`, `ml/dataset.py` | **Done 2026-11-21**: dataset built; labels match `scripts/backtest.py` (129/129) |
| 3 | `ml/train.py` | **Done 2026-11-21**: walk-forward, control, four baselines, gates, Exness re-score |
| 4 | Report | **Done 2026-11-21**: `ml/reports/xauusd_walkforward.md`, `xauusd_variants.md`: gates FAILED |
| 5 | `ml/predict.py`, feeder flag, `ict_ml` rules | `ml/predict.py` + `ml/monitor.py` + `ml/retrain.py` built and locked; feeder/analyzer wiring waits for a passing model |
