"""Machine-learning layer for ICT setups: candidate detection, features, labels, training and inference.

    ml/data.py          load saved broker history (.local/history*) as numpy arrays; M1 -> M5
    ml/ict_features.py  broad ICT candidates (liquidity sweep -> MSS -> FVG limit) with ~45 ICT features each
    ml/labels.py        grade every candidate with app.grader.simulate on M1 with spread (the live grader)
    ml/dataset.py       CLI: build the labelled dataset for many symbols
    ml/train.py         CLI: walk-forward LightGBM, baselines, shuffled-label control, final model + report
    ml/predict.py       load the saved model and score the latest closed M5 bar (for the feeder, later)

The rule engine decides *what happened* (deterministic, testable); the model only learns *which* of those setups
have historically paid. Nothing here places orders.
"""
