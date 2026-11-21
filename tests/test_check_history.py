"""ml/check_history.py on small synthetic histories: each reject class is counted, holidays are gaps not rejects."""
import pytest

np = pytest.importorskip('numpy')          # the ML layer is optional: requirements-ml.txt
pd = pytest.importorskip('pandas')

from ml import check_history as ch  # noqa: E402

MONDAY = 1735516800        # 2024-12-30 00:00 UTC


def week(start=MONDAY, days=(0, 1, 2, 3, 4), hours=range(0, 21), spread=0.5):
    """One M1 bar per minute on the given weekdays and UTC hours, flat prices."""
    t = np.array([start + d * 86400 + h * 3600 + m * 60 for d in days for h in hours for m in range(60)], dtype=np.int64)
    return pd.DataFrame({'t': t, 'o': 2000.0, 'h': 2001.0, 'l': 1999.0, 'c': 2000.5, 'spread': spread})


def test_clean_week_passes_everything():
    df = week()
    assert ch.check_timestamps(df)['duplicates'] == 0
    assert ch.check_prices(df)['high_below_low'] == 0
    assert ch.check_weekend(df)['saturday_bars'] == 0
    gaps = ch.check_gaps(df, max_hole_days=5)
    assert gaps['missing_hours'] == 0 and gaps['holes'] == []


def test_duplicates_bad_prices_and_saturday_are_counted():
    df = week()
    df = pd.concat([df, df.iloc[[10]]]).sort_values('t', kind='stable').reset_index(drop=True)   # one duplicate
    df.loc[20, 'h'], df.loc[20, 'l'] = 1990.0, 1995.0                                               # high < low
    df.loc[30, 'c'] = 2050.0                                                                        # close above high
    df.loc[40, 'o'] = 0.0
    saturday = pd.DataFrame({'t': [MONDAY + 5 * 86400 + 3600], 'o': 1.0, 'h': 2.0, 'l': 0.5, 'c': 1.5, 'spread': 0.1})
    df = pd.concat([df, saturday]).reset_index(drop=True)
    assert ch.check_timestamps(df)['duplicates'] == 1
    prices = ch.check_prices(df)
    # the inverted bar and the zero open also put open/close outside [low, high]
    assert (prices['high_below_low'], prices['open_close_outside_range'], prices['non_positive']) == (1, 3, 1)
    assert ch.check_weekend(df)['saturday_bars'] == 1


def test_missing_day_is_a_gap_and_long_hole_is_a_reject():
    df = week(days=(0, 1, 3, 4))                     # Wednesday is a holiday
    gaps = ch.check_gaps(df, max_hole_days=5)
    assert gaps['missing_days'] == 1 and gaps['days'] == ['2025-01-01'] and gaps['holes'] == []
    assert gaps['by_year'] == {'2025': {'missing_hours': 21, 'full_days': 1, 'partial_days': 0}}
    two_weeks = pd.concat([week(), week(start=MONDAY + 14 * 86400)])       # a whole trading week missing
    gaps = ch.check_gaps(two_weeks, max_hole_days=3)
    assert gaps['holes'] == [{'from': '2025-01-06', 'to': '2025-01-10', 'trading_days': 5}]
    assert ch.check_gaps(two_weeks, max_hole_days=5)['holes'] == []


def test_partial_hours_and_spread_outliers():
    df = week(hours=range(0, 20))                    # hour 20 missing every day
    gaps = ch.check_gaps(df, max_hole_days=5)
    assert gaps['missing_hours'] == 5 and gaps['partial_days'] == 5 and gaps['missing_days'] == 0
    df.loc[0, 'spread'] = 0.0
    df.loc[1, 'spread'] = 50.0
    spread = ch.check_spread(df)
    assert spread['2024']['zero'] == 1 and spread['2024']['outliers'] == 1 and spread['2024']['median'] == 0.5


def test_frames_match_resampled_m1(tmp_path):
    df = week()
    (tmp_path / 'XAUUSD_m1.csv').write_text(df.to_csv(index=False))
    ch.resample(df, 300).to_csv(tmp_path / 'XAUUSD_m5.csv', index=False)
    broken = ch.resample(df, 3600)
    broken.loc[3, 'h'] = 9999.0
    broken.to_csv(tmp_path / 'XAUUSD_h1.csv', index=False)
    frames = ch.check_frames(df, tmp_path, 'XAUUSD')
    assert frames['m5']['matches_m1'] is True
    assert frames['h1']['matches_m1'] is False and '1 bars differ' in frames['h1']['mismatch']
    assert frames['d1'] == {'present': False}


def test_run_checks_reports_rejects(tmp_path):
    df = week()
    df.loc[5, 'l'] = 5000.0                          # low above high
    (tmp_path / 'XAUUSD_m1.csv').write_text(df.to_csv(index=False))
    result = ch.run_checks(tmp_path, 'XAUUSD', compare=None, max_hole_days=5)
    assert result['passed'] is False
    assert result['rejects'] == ['1 bars with high_below_low', '1 bars with open_close_outside_range']
    assert '**FAILED**' in ch.markdown(result)
