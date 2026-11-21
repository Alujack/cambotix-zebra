"""ml/screen.py: the walk through M1, the costs and the one-position rule."""
import numpy as np
import pandas as pd
import pytest

from ml import screen
from ml.data import Bars


def bars(rows, spread=0.2, start=1_600_000_000):
    """rows = (o, h, l, c) per minute."""
    a = np.array(rows, dtype=float)
    t = start + 60 * np.arange(len(a))
    return Bars(t.astype(np.int64), a[:, 0], a[:, 1], a[:, 2], a[:, 3], np.full(len(a), spread))


FLAT = (100.0, 100.2, 99.8, 100.0)


def test_buy_target_pays_the_spread_once():
    m1 = bars([FLAT, FLAT, (100, 102.1, 99.9, 102), FLAT, FLAT])
    out = screen.simulate(m1, [0], 1, 1.0, 2.0, 4, cost=1.0)
    assert out.kind[0] == screen.TARGET
    assert out.r[0] == pytest.approx((102.0 - 100.2) / 1.0)
    assert out.exit_t[0] == m1.t[2] + 60
    assert screen.simulate(m1, [0], 1, 1.0, 2.0, 4, cost=0.0).r[0] == pytest.approx(2.0)


def test_sell_stop_is_hit_by_the_ask():
    # The bid only reaches 100.85; with a 0.2 spread the ask reaches 101.05 and stops the sell at 101.
    m1 = bars([FLAT, (100, 100.85, 99.9, 100.5), FLAT, FLAT])
    out = screen.simulate(m1, [0], -1, 1.0, 2.0, 3, cost=1.0)
    assert out.kind[0] == screen.STOP and out.r[0] == pytest.approx(-1.0)
    assert screen.simulate(m1, [0], -1, 1.0, 2.0, 3, cost=0.0).kind[0] == screen.TIMEOUT


def test_both_in_one_bar_counts_as_the_stop_and_gaps_fill_at_the_open():
    m1 = bars([FLAT, (100, 102.5, 98.5, 100), FLAT, FLAT])
    assert screen.simulate(m1, [0], 1, 1.0, 2.0, 3, cost=0.0).kind[0] == screen.STOP
    gap = bars([FLAT, (98.0, 98.2, 97.9, 98.0), FLAT, FLAT])
    out = screen.simulate(gap, [0], 1, 1.0, 2.0, 3, cost=0.0)
    assert out.kind[0] == screen.STOP and out.r[0] == pytest.approx(-2.0)


def test_timeout_closes_at_the_last_bar_inside_the_hold_and_stops_at_a_gap():
    m1 = bars([FLAT, FLAT, (100, 100.6, 99.9, 100.5), (100.5, 100.9, 100.4, 100.8), FLAT])
    out = screen.simulate(m1, [0], 1, 1.0, 2.0, 3, cost=0.0)
    assert out.kind[0] == screen.TIMEOUT and out.r[0] == pytest.approx(0.5)
    # A weekend after the second bar: the hold ends by the clock, so the trade closes at the last bar before it.
    t = m1.t.copy()
    t[2:] += 2 * 86_400
    gapped = Bars(t, m1.o, m1.h, m1.l, m1.c, m1.spread)
    out = screen.simulate(gapped, [0], 1, 1.0, 2.0, 3, cost=0.0)
    assert out.r[0] == pytest.approx(0.0) and out.exit_t[0] == t[1] + 60


def test_unresolved_when_the_hold_passes_the_end_of_the_data():
    m1 = bars([FLAT] * 5)
    out = screen.simulate(m1, [0, 3], 1, 1.0, 2.0, 3, cost=0.0)
    assert list(out.resolved) == [True, False]


def test_one_position_at_a_time():
    keep = screen.non_overlapping(np.array([0, 60, 120, 300]), np.array([180, 240, 200, 400]))
    assert list(keep) == [True, False, False, True]
    m1 = bars([FLAT] * 30)
    signals = pd.DataFrame({'i': [0, 1, 6], 'side': 1.0, 'stop': 1.0, 'target': 2.0, 'hold': 5})
    assert len(screen.run(m1, signals, 0.0)) == 2


def test_verdict_follows_the_rule():
    good = {'n': 900, 'mean': 0.12, 't': 3.0, 'pf': 1.3, 'years': 6, 'years_positive': 5, 'per_year': 150}
    result = {0.0: {'discovery': good, 'confirm': good}, 1.0: {'discovery': good, 'confirm': good}}
    assert screen.verdict(result) == 'PASSED'
    flat = dict(good, mean=0.0, t=0.1)
    assert screen.verdict({0.0: {'discovery': flat, 'confirm': good}, 1.0: result[1.0]}) == 'no edge before costs'
    costly = dict(good, mean=-0.05)
    assert screen.verdict({0.0: result[0.0], 1.0: {'discovery': costly, 'confirm': good}}) == 'edge smaller than the spread'
    weak = dict(good, mean=0.01)
    assert screen.verdict({0.0: result[0.0], 1.0: {'discovery': good, 'confirm': weak}}) == 'failed confirmation'
