# Zebra ML: ICT model for XAUUSD — plan

Status: **all phases built and run (2026-11-21). Version 1 failed the gates; version 2 (Plan v2 at the end of this file) failed its development gates the same day and its lockbox was never opened. Nothing goes live.**

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

**One-year out-of-sample backtest, 2025-11-20 .. 2026-11-20** (`python -m ml.backtest`, report
`ml/reports/xauusd_backtest_20251120_20261120.md`): the model, trained only on trades that ended before the year,
found no profitable threshold on validation and took **no trades**. The research-only policy "model's top 20%"
lost 22.3R (−0.067R per trade, 334 trades); every candidate lost 82.2R, the rule engine's killzone subset 26.5R. On
Exness prices: top 20% −23.9R, every candidate −53.5R. Staying out was the right call.

**Why the model never finds a profitable cut (found in the one-year backtest):** the label. `win` means the
trade ended above 0R, so the model learns to pick setups that drift up and close at the 6-hour limit with a small
gain. In validation before the test year, its top 10% hit the 2R target 8.2% of the time against 20.4% for all
trades, and 78% of its wins were time-limit wins (35% for all trades). Its win rate rises but its average winner
falls from +1.52R to +0.82R, so no cut pays. A model that targets profit would be trained on reaching the target
(`exit == 'final_target'`) or on R itself. That is a correction of the label, not a tuned setting, but it would
still be one more trial on the same data and has to pass the same gates.

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

## Plan v2 — a more accurate model (audited, built and run 2026-11-21: failed the development gates, see V2.9)

Version 1 failed for two proven reasons: the label rewarded small time-limit wins instead of reaching the target,
and trades were chosen by win probability instead of expected profit. Version 2 fixes those two causes and nothing
else that cannot be verified. Everything below is frozen now, before any v2 result exists. One configuration, one
development run, one final run.

### Audit of the first draft (what changed and why)

| Draft item | Audit finding | Amendment |
|---|---|---|
| Label costs with an Exness/Dukascopy spread ratio | The spread recorded in the Exness file is a floor, not the real spread: in 2025 its median and 99th percentile are both 0.16 (42 distinct values all year). Minute-by-minute correlation with Dukascopy is 0.15 and the yearly ratio swings 1.6–3.6. Two thirds of the overlap lies inside the lockbox. Passing gates on assumed cheaper costs would loosen the gates | **Dropped.** Gates stay on Dukascopy costs. A "spread halved" line is reported as sensitivity only and decides nothing |
| Lockbox enforced by a command-line flag | A flag can be forgotten; the lockbox must be unreadable by development code | **Physical split** into two files at build time; one script may read the lockbox, once |
| Demo forward test of 100 trades | The net R of one trade has a standard deviation of 1.28R. A model with no edge shows more than +0.10R by luck 22% of the time over 100 trades, 13% over 200, 6% over 400, 1% over 800 | **Forward test decision at 400 trades.** A lockbox pass is stated as weak evidence |
| No account-size rule | Gold stops have grown with price: median stop $11.90 in 2026, and 62% of 2026 stops risk more than $10 at the 0.01-lot minimum | **Account filter** applied before any scoring |
| "Average timeout R for similar setups"; two yes/no models | Undefined, and two separate models give probabilities that need not add up | **One three-outcome model plus a timeout-result model** |
| Silver and EURUSD divergence features | No silver history on disk; EURUSD starts 2020-11. Two more downloads the size of the gold pull for unproven features | **Cut from v2** |
| Settings tuned per fold | On a signal this weak (v1 AUC 0.57) tuning mostly fits noise and adds trials | **Fixed settings**, the v1 ones |

Known weakness that no amendment removes: the lockbox years were partly seen in v1 (the 2023–2025 validation
slice behind the label diagnosis, and the one-year backtest). They are the least-seen data available, not unseen
data. Only the forward test is truly new.

Side finding for v1: its gate 5 ("holds on Exness") and the "−0.056R on Exness" figure used that same floor
spread, so both were optimistic. v1 failed anyway; the verdict does not change.

### V2.0 Split the data before anything else

- `ml/dataset.py` writes two files: `xauusd_ict_dev.parquet` (candidates whose trade window ends before
  2024-11-20) and `xauusd_ict_lockbox.parquet` (2024-11-20 .. 2026-11-20).
- `ml/train.py`, `ml/backtest.py` and every test read the development file only.
- `ml/final_test.py` is the only code that opens the lockbox. It requires the frozen configuration recorded in
  this file, writes a dated result, and refuses to run a second time.
- Development walk-forward: test folds of 6 months from 2014-01-01 to 2024-11-20, training from 2011.

### V2.1 Account filter (applied first, to development and lockbox alike)

- Account $1,000, at most $10 risk per trade (1%), minimum position 0.01 lot = 1 oz.
- A candidate is tradable only if its stop distance is at most $10. Untradable candidates are removed before
  training, scoring and every statistic. Gate 4 (100 trades a year) is counted after this filter.

### V2.2 Label and model

- Each filled trade has one of three outcomes: **target** (`final_target`), **stop** (`sl`), **timeout**
  (`timeout`, and the rare `be`). Shares 2011 on: 20% / 61% / 18%.
- Model 1: one LightGBM three-class model giving P(target), P(stop), P(timeout), which sum to 1.
- Model 2: LightGBM regression of net R on timeout trades only (their mean is +0.23R, spread 0.80R).
- Expected net R of a setup = P(target) × mean net R of target exits in the training window
  + P(stop) × mean net R of stop exits in the training window + P(timeout) × the Model 2 prediction.
- Cross-check: a direct regression of net R (Huber loss). Reported only: if its rank correlation with the
  expected-R score on validation is under 0.5, the report says so. It is not a gate and selects nothing.

### V2.3 Selection

- Take a setup when its expected net R is at or above a cut chosen on the validation slice (last 20% of each
  training window): best mean net R × √trades, at least 150 trades, mean above zero; otherwise no trades.
- The report shows predicted against realised R by tenth, and how often each tenth reaches the target.

### V2.4 Inputs (one fixed batch)

Added to the 50 v1 features, all from bars closed at or before the signal bar:

- H1 and H4 structure from the resampled files: direction of the last confirmed swing break, distance to the
  nearest H1/H4 swing high and low, whether the entry sits inside an open H4 fair value gap. A higher-timeframe
  bar counts only once it has closed (the largest look-ahead risk in v2; each feature gets a truncation test).
- The high and low of the previous week, and the open of the day, as distances.
- Spread against its own trailing norm for that hour of day (trailing 20 days).

Not in v2: silver/EURUSD divergence, news proximity, any feature added after the first v2 result.

### V2.5 Training

- LightGBM with the v1 settings, unchanged. No tuning.
- Sample weights with a 4-year half-life; five seeds averaged; spread/risk constrained so a higher value can never
  raise the expected R; one-day embargo as in v1.

### V2.6 Gates and the path to a decision

Gates 1–4 as in section 8, on Dukascopy costs with slippage, counted after the account filter. Gate 5 becomes:
the same fold models on Exness **prices** with the Dukascopy spread for the same minute (the spread field of the
Exness file is not trusted), expectancy above zero.

1. Development walk-forward. Any gate fails: stop, report, no further v2 variants.
2. All pass: freeze, run `ml/final_test.py` once on the lockbox. Expect 200–400 trades there, so a pass is weak
   evidence (a no-edge model passes by luck roughly 6–13% of the time).
3. Lockbox pass: demo forward test. `ml/monitor.py` watches from 50 trades for alarm only; the go/no-go decision
   is at 400 graded trades. At 100–200 trades a year that is two to four years on demo, which is the real cost of
   a claim this small.

### Build order

| Step | Work | Done when |
|---|---|---|
| 1 | Dev/lockbox split in `ml/dataset.py`; `ml/final_test.py` with its run-once lock | Tests prove no development code path can open the lockbox |
| 2 | Account filter; three-outcome label columns | Labels still match `scripts/backtest.py`; filter counts reported by year |
| 3 | H1/H4, week/day and spread-norm features in `ml/ict_features.py` | A truncation (no-lookahead) test passes for every new feature |
| 4 | Three-class model, timeout model, expected-R selection, weights, seeds in `ml/train.py` | Development walk-forward report with gates |
| 5 | Decision on development folds | Fail: stop and report. Pass: freeze and run the lockbox once |
| 6 | Only on a lockbox pass: feeder wiring, demo forward test, monitor | 400 graded demo trades compared with expectation |

Honest expectation: on Dukascopy costs the unfiltered setups lose about 0.15R per trade (0.20R with slippage), and
gate 1 needs +0.10R, so v2 must find about +0.30R of real selection skill. v1 found about +0.11R. The label fix
makes a pass possible, not likely.

### V2.7 Implementation details fixed before the first v2 run (2026-11-21)

Details the sections above left open, written down before any v2 number existed:

1. **Split rule.** Development file: candidates whose trade window ends before 2024-11-20 00:00 UTC. Lockbox file:
   candidates from that moment on. Candidates that straddle it go in neither. `ml.train.load` also refuses any
   frame that contains a row from the lockbox period, so a wrong file cannot be trained on by accident.
2. **New features (11, total 61), each direction-relative and from closed bars only.** H1 and H4 bars are built
   from M5 on UTC boundaries and count once their period has ended. `h1_trend`, `h4_trend`: side of the last close
   beyond the most recent confirmed 2/2 swing (with the trade +1, against −1, none yet 0). `h1_swing_ahead_atr`,
   `h1_swing_behind_atr`, `h4_swing_ahead_atr`, `h4_swing_behind_atr`: distance from the entry to the nearest of the
   last 20 confirmed swing highs/lows in front of and behind the trade. `h4_fvg`: the entry sits inside an H4 fair
   value gap formed in the last 2,880 M5 bars and not yet traded through (with the trade +1, against −1, none 0).
   `pw_ahead_atr`, `pw_behind_atr`: signed distance to the previous trading week's extreme in front of and behind
   the trade. `day_open_entry_atr`: entry against the trading day's open. `spread_hour_norm`: spread divided by
   its mean for the same UTC hour over the previous 30 calendar days (corrected in V2.8 from "the previous 20
   days that hour traded").
3. **Models per fold.** Rounds come from early stopping on the validation slice (one seed); then five seeds are
   fitted on the fit part to score validation and choose the cut, and five on the whole window to score the test
   fold. Class means and the timeout model come from the same window. Weight of a training trade:
   0.5 ^ (age in years / 4), age measured from the end of the window.
4. **Monotone constraint.** LightGBM cannot give the classes of one three-class model opposite directions, so the
   spread/risk constraint is enforced where it can be exact: decreasing in the timeout-result model and in the
   cross-check regression. The three-class model is unconstrained in spread/risk.
5. **Shuffled control.** Same procedure with the outcome and net R of the training trades permuted together; the
   cut is still chosen on true validation results. AUC for gate 2 is P(target) against "reached the target" on
   filled test trades.
6. **Gate 3's recent period** is the last two years of the development test folds (2022-11-20 .. 2024-11-20).
7. **Gate 5 on development data** has one year of Exness prices (2023-11-24 .. 2024-11-20).
8. **Spread-halved line.** The development candidates are graded a second time with half the spread; the report
   shows what the model's chosen setups made there. It decides nothing.
9. **Final model and lockbox pass.** If the development gates pass, the model fitted on all development trades
   from 2011, with its validation cut, is frozen. `ml/final_test.py` trades the lockbox with it once. Lockbox pass
   = expectancy above +0.10R and profit factor above 1.2, max drawdown at most 15R, at least 100 trades a year,
   and at least +0.05R per trade better than taking every tradable setup. `ml/predict.py` refuses a model without
   a passed lockbox record.

### V2.8 Correction after the development run (2026-11-21), written before any rebuild

The development walk-forward ran once and **failed all five gates** (results in V2.9). That run is the decision.

A check made afterwards (replaying live scoring on 40 development setups) found one input that live scoring could
not always reproduce: `spread_hour_norm` was "the previous 20 days on which that hour traded". For the UTC hour
that only trades in summer time (22:00), that reaches back to the previous autumn, further than the 15,000-bar
lookback of `ml/predict.py`; 1 of 40 setups differed by 1.2%. The definition is corrected to "the previous 30
calendar days (about 20 trading days), at least five of them traded", which is bounded.

Rule for the rebuild that follows: the datasets and the development model are rebuilt so that files and code
agree, and the walk-forward is run again for that reason only. **The first run decides.** If the rebuilt run
differed in verdict, the difference would be reported as instability and the verdict would stay "failed"; a pass
appearing only after a correction is not a pass.

### V2.9 Result (2026-11-21): version 2 failed the development gates; the lockbox was never opened

Everything in the build order up to the decision was built and tested (steps 1–5). Step 6 does not happen.

| # | Gate | Required | Measured (deciding run) | Pass |
|---|---|---|---|---|
| 1 | Expectancy and profit factor | > +0.10R and PF > 1.2 | −0.034R, PF 0.94, on 29 trades in 11 years | no |
| 2 | Beats every baseline and the control | +0.05R over each; AUC +0.02 over control | best baseline −0.043R; AUC 0.596 vs 0.494 | no |
| 3 | Consistent and recent | 60% of folds positive; last 2 years positive | 0 of 1 traded folds; 21 of 22 folds had no cut | no |
| 4 | Drawdown and enough trades | ≤ 15R; ≥ 100 trades a year | 5.5R; 3 trades a year | no |
| 5 | Broker prices, Dukascopy spread | expectancy above zero | 0 trades | no |

The rebuild after the V2.8 correction gave the same verdict (all five failed, the same 21 of 22 folds without a
cut, AUC 0.597 vs 0.495). The one fold that traded moved from 29 trades at −0.034R to 54 trades at −0.229R, which
is what a cut sitting on noise looks like.

**What version 2 established, now that the label is right:**

- **Nothing in the 61 inputs predicts reaching the 2R target.** In the last development year's validation, 21.4%
  of all setups reached the target, and at every cut from the top 95% to the top 10% the rate stays between 18.8%
  and 21.7%. In the walk-forward the model's best tenth reached the target 19.8% of the time against 20.9% for
  its worst tenth.
- **What the model can sort is stop against timeout.** Its worst tenth is stopped out 74% of the time and its
  best tenth 50%, with timeouts rising from 5% to 30%. Timeouts average about +0.2R, which does not pay for the
  half that still stops out.
- **Its confidence is optimism.** Its top tenth expected +0.10R and made −0.07R; on validation its top 10%
  expected +0.14R and made −0.12R.
- **The new inputs did not help.** The best of the eleven (distance to the H4 swing behind the entry) carries 2%
  of the model's gain; stop size, session and spread/risk still carry most of it.
- **Cost is not the whole story.** With the spread halved the deciding run's 30 trades made +0.04R each, and
  every tradable setup still loses.

**Conclusion.** Two models, six variants and one corrected label agree: on M5 gold, the sweep → structure shift →
fair value gap setup does not carry information about which trades reach their target, at least none that these
inputs capture. The strategy family is the limit, not the model. By the plan there is no further v2 variant, no
lockbox run and no forward test. The lockbox (2,915 candidates, 2024-11-20 on) remains unread and can serve a
genuinely different idea later.

What exists and works: `ml/lockbox.py`, `ml/dataset.py` (split, account filter, three outcomes),
`ml/ict_features.py` (61 inputs), `ml/train.py` (v2 model, gates), `ml/backtest.py`, `ml/final_test.py` (refuses:
gates failed), `ml/predict.py` (refuses: gates failed), `ml/monitor.py` (waits for a final test), `ml/retrain.py`.
Reports: `ml/reports/xauusd_v2_walkforward.md`, `ml/reports/xauusd_v2_backtest_20231120_20241119.md`.

### V2.10 Why it loses (review of 2026-11-21): the setup has no edge before costs

The same candidates were graded a third time with the spread set to zero
(`python -m ml.dataset --name xauusd_ict_zerospread --spread-scale 0`, development data only, sensitivity only).
Filled trades 2011 to 2024-11-19, the setups that pass the account filter:

| Spread | Filled | Target | Stop | Timeout | Mean R per trade | Total R |
|---|---|---|---|---|---|---|
| Dukascopy (real) | 12,110 | 20.4% | 62.3% | 17.2% | -0.164 | -1,982 |
| halved | 12,434 | 22.7% | 58.9% | 18.2% | -0.078 | -973 |
| zero | 12,774 | 24.9% | 55.8% | 19.1% | +0.006 (standard error 0.012) | +71 |

- **Before costs the setup is a coin flip.** +0.006R on 12,774 trades is zero; no year is beyond +/-0.07R, no
  session beyond +/-0.04R, buys and sells are the same. Sweep, structure shift and fair value gap do not tilt
  the odds on M5 gold; they only choose where the entry and stop sit.
- **The whole loss is the cost.** The median stop is $2.28 and the median spread $0.32, so each trade pays about
  14% of its risk to get in and out. That is the -0.164R.
- **Why the model looked skilful and was not.** With nothing to predict about direction, it learned geometry:
  wide stops are hit less often (44% against 75%) but reach the target less often (12% against 21%) and pay a
  smaller share in spread. That sorts stop against timeout (AUC 0.60) and cannot produce profit.
- **A cheaper broker shrinks the loss, it does not create a profit.** The best the cost side can do is the zero
  line above.

Lessons for the next idea, in the order they would have saved time:

1. Grade the raw setup at zero cost first. If it is near zero there, stop: a filter model cannot create an edge
   that the setup does not have. This one check takes a minute and would have replaced both model versions.
2. Check cost against stop size before anything else. A setup whose stop is only 7 times the spread needs a large
   edge just to break even.
3. A model that separates outcomes (AUC above 0.5) is not a model that makes money. Judge by net R only.
4. What worked and stays: gates written before the run, the shuffled control, the lockbox, and "the first run
   decides". They are why this result can be trusted and why two years of data are still clean.

## Idea screen (2026-11-21): 57 scalping and intraday ideas, none passed

Built from lesson 1 of V2.10: `ml/screen.py` walks any list of entries through M1 at zero, half and the recorded
spread, with a discovery period (2011 to 2018) and a confirmation period (2019 to 2024-11-19), one position at a
time, and one pass rule written before the run. `python -m ml.ideas` runs every idea in about 30 seconds.
Development data only; the lockbox period is not loaded. Full table: `ml/reports/xauusd_idea_screen.md`.

| Family | Ideas | Result |
|---|---|---|
| Move of 5, 15, 60 or 240 minutes, then follow or fade | 16 | zero before costs at every horizon (within +/-0.03R) |
| Channel break on M15 (5 hour, 24 hour), follow or fade | 4 | 24 hour follow +0.06R / +0.02R before costs, loses after |
| Squeeze then band break | 2 | does not repeat in confirmation |
| Round numbers ($10, $50): breakout or rejection | 4 | breakouts +0.06R to +0.16R before costs in both periods; lose after |
| Previous day high/low: follow or fade | 2 | follow +0.05R / +0.04R before costs; loses after |
| News clock (08:30, 10:00 range break) | 2 | zero |
| One session predicts the next | 8 | zero |
| Daily trend pullback (RSI) | 1 | zero |
| Hour of the day | 6 | does not repeat; the 16:00 to 18:00 "drift" is the bid moving as the spread widens |
| EURUSD leads gold | 4 | flips sign between periods |
| Round 2: level breaks with stops 2x and 4x wider (exploratory) | 8 | edge shrinks as fast as the cost share |

Findings:

- **Gold is a coin flip at 5 minutes to 4 hours.** Following a move and fading it both make zero before costs.
- **The one repeatable effect is that a break of a level tends to continue a little** ($50 and $10 round numbers,
  previous day's high/low, 24 hour channel), and fading a break loses. This is the opposite of the sweep-and-
  reverse idea behind the ICT setup. It is worth about $0.10 to $0.20 per oz against a spread of $0.34.
- **A model does no better** (`python -m ml.forecast_check`, `ml/reports/xauusd_forecast_check.md`): LightGBM on
  39 generic inputs, trained 2011 to 2017, judged 2019 to 2024. Rank correlation +0.04 (30 minutes) and +0.03
  (60 minutes). Its best tenth of forecasts moves $0.08 and $0.14 per oz before costs: 25% and 41% of the spread.
- **Cost decides.** With a 1.5 ATR stop on M5 the recorded spread is about 0.3R per trade. At half the spread
  the $50 breakout makes +0.07R on about 90 trades a year in confirmation: too little to matter and not a pass.

Nothing here goes to the lockbox, and no model is built on these ideas.

### The v2 model at zero spread (2026-11-21, sensitivity only)

The v2 walk-forward was repeated on the zero-spread dataset (`xauusd_ict_zerospread_dev.parquet`, same folds and
settings, nothing saved over the real model or reports). It found a cut in 19 of 22 folds and took 3,739 trades
in ten years: +0.038R per trade (t = 1.8), profit factor 1.07, +143R in total, 7 of 10 years positive, maximum
drawdown 37R. Every tradable setup taken blindly made -0.007R. The share reaching the target is the same as for
all setups (24.9% against 24.4%); the gain comes from fewer stops and more timeouts. So even with no cost at all
the model stays under the +0.10R gate, and its edge is not clearly different from zero.

## smart-money-concepts library test (2026-11-21): 48 live tests, none passed

`ml/smc_test.py` tests github.com/joshyattridge/smart-money-concepts v0.0.27 (its own code, unchanged) on
development gold through `ml/screen.py`. The library is an indicator set with no strategy and no backtest of
its own. Its swings need `swing_length` later candles and its liquidity range uses the whole chart, so the
library was replayed bar by bar seeing only candles up to "now" (M5 with swing 5 and 20, M15 with swing 20 and
the default 50; about 105 minutes on 12 processes). Report: `ml/reports/xauusd_smc_library_test.md`.

- Signals traded: break of structure, change of character, order block retest, liquidity sweep then reverse,
  fair value gap forming, fair value gap retest, and the two retests filtered by the last structure break. Each
  as the concept says and the opposite way. Stop 2 ATR, target 2R, hold 48 bars.
- 41 of 48 have no edge before costs, 3 have too few trades, 1 has an edge smaller than the spread, 3 failed
  confirmation. Nothing on M5 has an edge even at zero spread.
- Closest: break of structure on M15 with the default swing 50. +0.19R / +0.14R before costs, +0.09R / +0.05R at
  the recorded spread, profit factor 1.08, 3 of 6 confirmation years positive, 39 trades a year. That is the same
  "a break continues" effect the idea screen found, and it is about +2R a year.
- Liquidity sweep then reverse loses in every setting, like the ICT setup.
- Trading the signals at the bar where a finished chart draws them (hindsight) gives about the same result as
  live, so the break signals are honest; they just carry almost no edge.

## Intraday screen (2026-11-22): 47 ideas held for hours, none passed

`ml/intraday.py` puts intraday (not scalping) ideas through `ml/screen.py` with the same pass rule. Signals come
from closed M15 or H1 bars, stops are 2 to 3 ATR of H1 or half a session's range (median $5 to $24 per oz), and a
trade is held for hours: up to 12 or 24 hours, or from 19:00 until flat at 16:00 New York. `python -m ml.intraday`
runs in about 20 seconds; `--check` proves that no idea reads a later candle (signals from history cut at a random
minute equal the signals from the full history). Development data only. Full table:
`ml/reports/xauusd_intraday_screen.md`.

| Family | Ideas | Result |
|---|---|---|
| Session range break on M15 (Asia, London, Asia + London, New York first 90 minutes) | 8 | follow or fade: zero to slightly negative after the spread |
| Volatility breakout: open +/- 0.5 or 1 x yesterday's range, follow or fade | 4 | follow +0.07R / +0.01R and +0.12R / +0.03R at the recorded spread; failed confirmation |
| Narrow day (inside day, NR7), then the break | 4 | follow +0.14R / +0.04R and +0.11R / +0.03R, but about 33 trades a year and t under 2 |
| Channel break on H1 (24 hours, 3 days, 5 days) | 6 | follow about zero after the spread, fade loses |
| Moving averages on H1 (EMA 20/50 cross, pullback in the 50/200 trend) | 3 | zero; the pullback flips sign in confirmation |
| Stretched on H1 (RSI 30/70, Bollinger band), follow or fade | 4 | zero |
| Round numbers on H1 ($50, $100) | 4 | follow about zero after the spread, fade loses |
| Last 24 hours at the London or New York open | 4 | zero |
| Day trade from a daily rule (yesterday's direction, 20/50 day average, always buy) | 9 | zero in discovery; confirmation follows gold's own rise |
| Session or weekday drift | 1 | London sell worked in discovery only |

Findings:

- **The spread is no longer the problem.** It costs 0.02R to 0.08R per trade here, against about 0.3R in the
  scalping screen. The ideas fail because there is almost nothing before costs either.
- **The same single effect again: a break continues a little, and fading a break loses.** Every "follow the
  break" row is positive before costs in both periods; every fade of a level or channel is negative.
- **It has faded.** The best family, the volatility breakout, made +0.12R to +0.15R before costs in 2011 to 2018
  and +0.04R to +0.05R in 2019 to 2024. After the spread that is +0.01R to +0.03R a trade: about +2R a year on
  the 1 x range version (61 trades a year, profit factor 1.12, 4 of 6 years positive). Not a pass.
- **Being long explains the good-looking confirmation rows.** "Always buy at 19:00, flat at 16:00" makes +0.02R a
  trade in confirmation and loses in discovery; "follow yesterday after a big day" (+0.06R, 5 of 6 years) made
  zero in discovery.
- **A model does no better at these horizons** (`python -m ml.forecast_check --horizons 48 96`,
  `ml/reports/xauusd_forecast_check_intraday.md`): rank correlation +0.002 for the next 4 hours and +0.003 for
  the next 8 hours, which is no skill at all.

Nothing here goes to the lockbox, and no model is built on these ideas.

## ATR Trend Confluence screen (2026-11-25): 90 tests, none passed

The indicator added to the website's broker chart on the same day (`web/trend.py`, source in
`tradingview/atr_trend_confluence.pine`): EMA50 baseline, Supertrend stop ATR 14 x 2.8, a label where the stop
flips, kept only when the filters agree (baseline, 1h EMA50/200, Choppiness, ADX/DMI, sessions, distance from the
baseline, optional break of structure). `ml/atr_trend.py` puts it through `ml/screen.py` with the same pass rule.
`python -m ml.atr_trend` runs in about 2.5 minutes; `--check` proves that no rule reads a later candle and that the
screen marks exactly what the website engine marks (60 days of M5: 367 flips, 181,482 filter states, 0 differences).
Development data only. Full tables: `ml/reports/xauusd_atr_trend_screen.md`.

The indicator has no exits, so the trade was fixed before the run: enter at the M1 open after the signal bar, stop
at the stop line (at least 1 ATR), and either a 2R target or "trail" (out when the stop flips back). Script
defaults, nothing tuned. M1, M5 and M15; the filter ladder one filter at a time, and each filter alone on top of
every flip.

| What | Result (mean R per trade, discovery / confirmation) |
|---|---|
| Every stop flip, zero cost | M1 +0.02 / -0.03, M5 +0.00 / +0.01, M15 +0.05 / -0.01: a coin flip, as every earlier screen found |
| Every stop flip, recorded spread | M1 -0.36 / -0.32, M5 -0.12 / -0.11, M15 -0.04 / -0.06 |
| Adding the filters (ladder A0 to F) | no rung reaches +0.03R with t >= 2 at zero cost in discovery; the filters remove trades, they do not add edge |
| Everything on, as on the website | M1 143 trades a year, -0.20 / -0.22; M5 24 a year, -0.26 / -0.07; M15 6 a year: too few to judge |
| Best single filter: London / New York mornings only, M5, 2R target | +0.06 / +0.06 at zero cost (t 2.7), -0.07 / -0.06 at the recorded spread: an edge smaller than the spread |

79 tests have no edge before costs, 8 have too few trades (M15 with four or more filters), 3 have an edge smaller
than the spread. The session effect is the "breaks continue in active hours" effect already seen in the idea
screen; Dukascopy's spread is about three times Exness's, but a third of the cost still leaves it near +0.02R,
under the +0.05R bar. The indicator stays on the chart as a description of trend and stop; it is not a model, and
nothing here goes to the lockbox.
