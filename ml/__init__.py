"""Machine-learning layer for ICT setups: candidate detection, features, labels, training and inference.

    ml/data.py          load saved broker history (.local/history*) as numpy arrays; M1 -> M5; spread repair
    ml/check_history.py CLI: validate a saved M1 history before anything is built from it
    ml/ict_features.py  the ICT concepts as small functions, and broad ICT candidates (liquidity sweep -> MSS ->
                        FVG limit) with 61 features each (50 from v1, 11 higher-timeframe/week/spread ones in v2)
    ml/check_candidates.py  CLI: candidates per year for a saved history, with sanity checks
    ml/labels.py        grade every candidate with app.grader.simulate on M1 with spread (the live grader)
    ml/lockbox.py       the final two years of candidates: the split, the guard, the run-once lock
    ml/dataset.py       CLI: build the labelled dataset, mark the account filter and the three-outcome label, and
                        write a development file and an unread lockbox file
    ml/train.py         CLI: plan v2 model (three-outcome model + timeout model -> expected net R), walk-forward on
                        development data, four baselines, shuffled control, the five gates, development model
    ml/backtest.py      CLI: the model over one development period, with every cut it tried and why
    ml/final_test.py    CLI: the one run on the lockbox; only for a model that passed the development gates
    ml/predict.py       CLI: score the latest closed M5 bar; refuses a model without passed gates and lockbox
    ml/monitor.py       CLI: live results vs the walk-forward, and feature drift (PSI); after the final test only
    ml/retrain.py       CLI: the rebuild cycle: pull, check, datasets, train

Verdicts (docs/ml-plan.md): version 1 and its five pre-listed variants failed the gates (2026-11-21). Version 2
(label fixed to the three outcomes, selection by expected profit, real H1/H4 structure) also failed the
development gates the same day; the lockbox was never opened. Nothing here is used for signals.

The rule engine decides *what happened* (deterministic, testable); the model only learns *which* of those setups
have historically paid. Nothing here places orders.
"""
