# Zebra ML: ICT model for XAUUSD — plan

Status: **plan for review. Nothing below is implemented yet except the draft noted in section 2.**

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
| 1. Data collection — XAUUSD OHLCV, timestamp checks, multi-timeframe sets | §3 (Phase 0) | **In progress 2026-11-21:** `pull_dukascopy.py` rewritten (`--from/--to/--out`, yearly files, m5+h1), `ml/check_history.py` + tests written, both smoke-tested; full gold pull from 2003 running |
| 2. ICT detection engine — concepts as testable modules | §4 (Phase 1) | Draft `ml/ict_features.py` committed in `d7fbae8`, **no tests yet**; `scripts/ict_engine.py` + `tests/test_ict_engine.py` cover the killzone-only variant |
| 3. Dataset generation — labeled samples, validated | §5 (Phase 2) | Draft `ml/labels.py`, `ml/dataset.py`; `ml/data/ict_dataset.csv.gz` (20 MB) built from the 3-year file and **committed and pushed in `d7fbae8`**, which §5 says datasets should not be; not yet validated against `scripts/backtest.py` |
| 4. ML training — setup classification, outcome prediction | §6 (Phase 3) | `ml/train.py` drafted, never run |
| 5. Backtesting — unseen periods, spread and slippage | §6 walk-forward, §7 report, §8 gates | Not started. Spread is already in the grader; **slippage is not modelled anywhere yet** (added to §6 below) |
| 6. Live inference — live data, real-time signals | §9 (Phase 5) | Not started; only after the §8 gates |
| 7. Monitoring — performance, drift, degradation | §10 (Phase 6) | Not started |

Two roadmap items the plan did not cover before this mapping: **multi-timeframe datasets** (roadmap 1) are
only partly there, since the engine works on M5 resampled from M1 and the HTF bias uses M5 EMAs as a stand-in
for H1/H4; real H1/H4 resampling is listed under "Later" in §4. **Slippage** (roadmap 5) is now a test-time
assumption in §6.

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

**Status 2026-11-21: built and running.** `scripts/pull_dukascopy.py` has the changes below, `ml/check_history.py`
exists with tests, and the full gold pull was started (see the roadmap table at the top for the result).

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

Same geometry as `scripts/ict_engine.py`, so results are comparable, but broader so the model has thousands of
examples:

- **Liquidity pools:** previous day high/low (NY 17:00 roll), Asia (20:00–24:00 NY), London (02:00–05:00),
  NY AM (08:30–11:00), M5 swing highs/lows (6/6 fractal, fresh for one day). A pool is spent once traded through.
- **Sweep → MSS → FVG:** price trades beyond a fresh pool; within 3 hours a close breaks the last 2/2 pivot formed
  before the extreme; the latest FVG of at least 0.1 ATR in that leg appears by the candle after the shift.
- **Plan:** limit at the FVG's near edge, stop beyond the sweep + 0.1 ATR, one target at 2R, at least 0.3 ATR risk.
- **Any session.** The killzone becomes a feature instead of a hard filter.

**Features (about 50), all computed from bars up to the signal bar only:**

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

- Each candidate becomes the plan the analyzer would freeze for an ICT signal (limit, 120-minute entry expiry,
  360-minute hold, one 2R target) and is graded by **`app.grader.simulate` on M1 with spread**. The label means
  exactly what a live graded trade would mean.
- Stored per row: features, `outcome` (closed / not filled + reason), `r` (the grader's R; 0 if never filled),
  `win` (filled trades only), fill and end time.
- Weekends inside the trade window: give the grader the candles after the gap, as live would.
- Output: `ml/data/xauusd_ict.parquet` (gitignored: datasets are rebuilt, not committed).
- **Expected size with full history:** around 25,000–30,000 gold candidates (~1,400 a year), versus 4,328 from the
  3-year file.

## 6. Phase 3 — Model training (`ml/train.py`)

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
| 0 | `pull_dukascopy.py` `--out`/`--from`/yearly files; `ml/check_history.py` | Full XAUUSD M1 downloaded, all checks pass (code done; pull running) |
| 1 | `ml/ict_features.py` + tests (no-lookahead, FVG/MSS cases) | Tests pass; candidate counts look sane per year |
| 2 | `ml/labels.py`, `ml/dataset.py` | Dataset built; labels match `scripts/backtest.py` on the ICT subset |
| 3 | `ml/train.py` | Walk-forward + control + baselines run end to end |
| 4 | Report | `ml/reports/xauusd_walkforward.md` reviewed together |
| 5 | `ml/predict.py`, feeder flag, `ict_ml` rules | Only if section 8 gates pass |
