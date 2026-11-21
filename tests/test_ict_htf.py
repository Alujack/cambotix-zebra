"""The plan v2 inputs of ml/ict_features.py: higher-timeframe bars and structure, H4 fair value gaps, the previous
week, the spread norm, and proof that none of them reads a bar that has not closed."""
import math

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('pandas')

from ml import ict_features as f  # noqa: E402
from ml.data import from_dicts  # noqa: E402
from tests.test_ict_features import walk  # noqa: E402

NEW = f.FEATURES[f.V1_FEATURES:]
MONDAY = 1735516800          # 2024-12-30 00:00 UTC


def m5_from_hours(hours, start=MONDAY, per_hour=12, seconds=3600):
    """M5 arrays where every higher-timeframe bar is `per_hour` identical candles with the given (high, low, close)."""
    t, h, l, c = [], [], [], []
    for k, (hi, lo, cl) in enumerate(hours):
        for j in range(per_hour):
            t.append(start + k * seconds + j * 300)
            h.append(hi), l.append(lo), c.append(cl)
    return np.array(t, dtype=np.int64), np.array(h, float), np.array(l, float), np.array(c, float)


def test_new_feature_list_is_the_frozen_eleven():
    assert len(f.FEATURES) == 61 and NEW == (
        'h1_trend', 'h4_trend', 'h1_swing_ahead_atr', 'h1_swing_behind_atr', 'h4_swing_ahead_atr',
        'h4_swing_behind_atr', 'h4_fvg', 'pw_ahead_atr', 'pw_behind_atr', 'day_open_entry_atr', 'spread_hour_norm')


def test_a_higher_timeframe_bar_is_available_only_when_its_period_has_ended():
    t = np.array([MONDAY + 300 * k for k in range(24)] + [MONDAY + 7200 + 300 * k for k in range(6)]
                 + [MONDAY + 4 * 3600], dtype=np.int64)          # hour 2 stops early, then a gap to hour 4
    one = np.ones(len(t))
    key, _, _, _, available = f.htf_bars(t, one, one, one, 3600)
    assert list(key - MONDAY) == [0, 3600, 7200, 14400]
    assert list(available) == [11, 23, 30, len(t)]                # last M5 bar of the hour; the bar after a gap;
    #                                                               the running hour is never available


def test_trend_turns_on_a_close_beyond_the_last_confirmed_swing():
    hours = [(10, 9, 9.5), (11, 10, 10.5), (12, 11, 11.5), (11, 10, 10.5), (10.8, 9.8, 10), (11.5, 10, 11),
             (13, 11, 12.5), (12.6, 11.5, 12), (12.4, 11.6, 12)]
    t, h, l, c = m5_from_hours(hours)
    H = f.htf_structure(t, h, l, c, 3600)
    assert H['hi_lvl'][0] == 12 and H['hi_idx'][0] == 5 * 12 - 1       # the swing at hour 2, known at hour 4's close
    assert (H['ev_idx'], H['ev_val']) == ([7 * 12 - 1], [1])           # hour 6 closed above it
    A, entry = 1.0, 11.0
    before, after = 6 * 12 - 1, 7 * 12 - 1
    assert f.htf_features(H, before, entry, 1, A)[0] == 0.0
    assert f.htf_features(H, after, entry, 1, A)[0] == 1.0 and f.htf_features(H, after, entry, -1, A)[0] == -1.0
    trend, ahead, behind = f.htf_features(H, after, entry, 1, A)
    assert ahead == pytest.approx(1.0) and behind == pytest.approx(1.2)        # swing high 12 above, swing low 9.8 below
    assert f.htf_features(H, after, entry, -1, A)[1:] == pytest.approx((1.2, 1.0))   # for a SELL they swap
    assert math.isnan(f.htf_features(H, after, 12.5, 1, A)[1])                 # nothing above 12.5 yet


def test_h4_gap_is_open_from_its_third_candle_until_price_trades_through_it():
    hours = [(10, 9, 9.5), (12, 10.5, 11.8), (13, 11, 12.5), (13.2, 11.5, 12), (13, 10.5, 11), (12, 9, 9.5)]
    t, h, l, c = m5_from_hours(hours, per_hour=48, seconds=14400)
    H = f.htf_structure(t, h, l, c, 14400, with_fvg=True)
    assert (H['fvg_lo'][0], H['fvg_hi'][0], H['fvg_dir'][0]) == (10, 11, 1)    # candle 0 high 10, candle 2 low 11
    opened = 3 * 48 - 1
    assert H['fvg_idx'][0] == opened and H['fvg_dead'][0] == 5 * 48           # candle 5 trades down through 10
    assert f.h4_fvg_state(H, opened - 1, 10.5, 1) == 0.0                       # third candle not closed yet
    assert f.h4_fvg_state(H, opened, 10.5, 1) == 1.0 and f.h4_fvg_state(H, opened, 10.5, -1) == -1.0
    assert f.h4_fvg_state(H, opened, 11.5, 1) == 0.0                           # entry outside the gap
    assert f.h4_fvg_state(H, 5 * 48 - 1, 10.5, 1) == 1.0 and f.h4_fvg_state(H, 5 * 48, 10.5, 1) == 0.0


def test_previous_week_and_spread_norm_use_only_earlier_days():
    days = np.repeat(np.arange(4, 25), 2)                 # trading days 4 (a Monday) to 24
    h = days.astype(float) + 100
    pwh, pwl = f.previous_week(days, h, h - 1)
    assert np.isnan(pwh[0]) and pwh[days == 11][0] == 110 and pwl[days == 11][0] == 103
    assert pwh[days == 18][0] == 117                      # last week's high, not the high so far
    t = np.array([MONDAY + d * 86400 + 3600 * 9 for d in range(8)], dtype=np.int64)
    spread = np.array([1, 1, 1, 1, 1, 1, 50, 1], float)
    norm = f.spread_hour_norm(t, spread)
    assert np.isnan(norm[:5]).all() and norm[5] == 1.0 and norm[6] == 1.0      # day 6's own spike is not in its norm
    assert norm[7] == pytest.approx((6 + 50) / 7)
    # An hour that last traded months ago (a summer-time-only hour) has no norm: the window is 30 calendar days.
    seasonal = np.array([MONDAY + d * 86400 + 3600 * 22 for d in list(range(6)) + [150, 151]], dtype=np.int64)
    assert np.isnan(f.spread_hour_norm(seasonal, np.ones(8))[-2:]).all()


def test_new_features_vary_on_random_data_and_are_direction_relative():
    bars = walk(20000, seed=5)
    for k, b in enumerate(bars):
        b['spread'] = 0.2 + 0.1 * ((k * 7) % 13) / 13             # the walk's spread is flat; give it some life
    rows = f.detect('XAUUSD', from_dicts(bars), f.CandidateConfig())
    assert len(rows) > 150
    for name in NEW:
        values = [r[name] for r in rows if not math.isnan(r[name])]
        assert len(values) > 0.5 * len(rows) and len(set(np.round(values, 6))) > 1, name
    assert {r['h4_fvg'] for r in rows} <= {-1.0, 0.0, 1.0} and {r['h1_trend'] for r in rows} <= {-1.0, 0.0, 1.0}
    assert all(r[k] > 0 for r in rows for k in NEW[2:6] if not math.isnan(r[k]))


def test_no_new_feature_reads_past_the_signal_bar():
    """Cut the history right after a candidate, and separately rewrite everything after it: its higher-timeframe,
    weekly and spread features must not move, even though its H1 and H4 candles are still forming."""
    bars = walk(20000, seed=9)
    rows = f.detect('XAUUSD', from_dicts(bars), f.CandidateConfig())
    rng = np.random.default_rng(1)
    picked = [rows[k] for k in rng.choice(len(rows), 12, replace=False)]
    for row in picked:
        i = row['bar_index']
        cut = [r for r in f.detect('XAUUSD', from_dicts(bars[:i + 1]), f.CandidateConfig()) if r['bar_index'] == i]
        wild = [dict(b) for b in bars]
        for b in wild[i + 1:]:
            b['h'], b['l'], b['c'], b['o'], b['spread'] = b['h'] + 500, b['l'] - 500, b['c'] + 300, b['o'], 9.0
        rewritten = [r for r in f.detect('XAUUSD', from_dicts(wild), f.CandidateConfig()) if r['bar_index'] == i]
        for other in (cut, rewritten):
            match = [r for r in other if r['side'] == row['side']]
            assert len(match) == 1
            for name in NEW:
                assert match[0][name] == pytest.approx(row[name], nan_ok=True), (name, i)
