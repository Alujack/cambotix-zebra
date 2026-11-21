"""Machine-learning layer for ICT setups: candidate detection, features, labels, training and inference.

    ml/data.py          load saved broker history (.local/history*) as numpy arrays; M1 -> M5
    ml/check_history.py CLI: validate a saved M1 history before anything is built from it
    ml/ict_features.py  the ICT concepts as small functions, and broad ICT candidates (liquidity sweep -> MSS ->
                        FVG limit) with 50 features each
    ml/check_candidates.py  CLI: candidates per year for a saved history, with sanity checks
    ml/labels.py        grade every candidate with app.grader.simulate on M1 with spread (the live grader)
    ml/dataset.py       CLI: build the labelled dataset for many symbols
    ml/train.py         CLI: walk-forward LightGBM, four baselines, shuffled-label control, the go/no-go gates,
                        Exness re-score, final model (promoted only if it passes) + report
    ml/predict.py       CLI: score the latest closed M5 bar with the promoted model; refuses a failed model
    ml/monitor.py       CLI: live results vs the walk-forward, and feature drift (PSI) vs the training data
    ml/retrain.py       CLI: the monthly cycle: pull, check, datasets, train, monitor

Verdict 2026-11-21 (docs/ml-plan.md): the gold model and all five pre-listed variants failed the gates; it is not
used for signals.

The rule engine decides *what happened* (deterministic, testable); the model only learns *which* of those setups
have historically paid. Nothing here places orders.
"""
