"""Offline tests for the Dukascopy pull: aggregation, the yearly merge and frame building (no network)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import pull_dukascopy as pd_  # noqa: E402

SUNDAY_2024_12_29 = 1735430400          # 00:00 UTC, a W1 bucket start
NEW_YEAR_2025 = 1735689600              # 2025-01-01 00:00 UTC


def bar(t, o, h, l, c, spread=0.5):
    return {'t': t, 'o': o, 'h': h, 'l': l, 'c': c, 'spread': spread}


def test_aggregate_m5_from_m1_keeps_first_open_last_close_and_extremes():
    m1 = [bar(600 + 60 * k, 10 + k, 20 + k, 5 - k, 11 + k) for k in range(5)] + [bar(900, 1, 2, 0.5, 1.5)]
    out = pd_.aggregate(m1, pd_.bucket_of('m5'))
    assert [b['t'] for b in out] == [600, 900]
    assert out[0] == bar(600, 10, 24, 1, 15)
    assert out[1] == bar(900, 1, 2, 0.5, 1.5)


def test_w1_bucket_starts_on_sunday():
    assert pd_.bucket_of('w1')(NEW_YEAR_2025) == SUNDAY_2024_12_29
    assert pd_.bucket_of('w1')(SUNDAY_2024_12_29 + 6 * 86400 + 5) == SUNDAY_2024_12_29


def test_merge_joins_a_bar_split_across_two_yearly_files(tmp_path):
    """The week over New Year appears in both the 2024 and the 2025 file and must become one W1 bar."""
    a = tmp_path / 'w1_2024.csv'
    b = tmp_path / 'w1_2025.csv'
    pd_.write(a, [bar(SUNDAY_2024_12_29 - pd_.WEEK, 1, 2, 0.5, 1.5), bar(SUNDAY_2024_12_29, 10, 12, 9, 11)])
    pd_.write(b, [bar(SUNDAY_2024_12_29, 11, 15, 8, 14, spread=0.7), bar(SUNDAY_2024_12_29 + pd_.WEEK, 14, 16, 13, 15)])
    out = tmp_path / 'w1.csv'
    count, first, last = pd_.merge([a, b], out)
    rows = list(pd_.read(out))
    assert (count, first, last) == (3, SUNDAY_2024_12_29 - pd_.WEEK, SUNDAY_2024_12_29 + pd_.WEEK)
    assert rows[1] == bar(SUNDAY_2024_12_29, 10, 15, 8, 14, spread=0.5)     # open+spread from 2024, close from 2025


def test_frames_from_uses_hourly_context_only_for_h4_d1_w1():
    context = [bar(NEW_YEAR_2025 - 3600 * k, 100, 101, 99, 100, spread=0.0) for k in range(1, 25)]
    minute = [bar(NEW_YEAR_2025 + 60 * k, 50, 51, 49, 50) for k in range(120)]
    frames = pd_.frames_from(minute, context)
    assert set(frames) == set(pd_.FRAMES)
    assert frames['m1'] is minute
    assert len(frames['m5']) == 24 and len(frames['m15']) == 8 and len(frames['h1']) == 2
    assert frames['h1'][0]['t'] == NEW_YEAR_2025                        # the M1 range only
    assert frames['d1'][0]['t'] == NEW_YEAR_2025 - 86400                # the context day before
    assert frames['d1'][-1] == bar(NEW_YEAR_2025, 50, 51, 49, 50)
    assert frames['h4'][-1]['t'] == NEW_YEAR_2025 and frames['w1'][-1]['t'] == SUNDAY_2024_12_29
