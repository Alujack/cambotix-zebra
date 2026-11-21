"""ml/ict_features.py: each ICT concept on its own, candidates on the hand-built sessions of test_ict_engine.py
(both engines must agree on them), the liquidity pools, and proof that no candidate uses a future bar."""
import datetime as dt
import math
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

np = pytest.importorskip('numpy')          # the ML layer is optional: requirements-ml.txt
pytest.importorskip('pandas')

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import ict_engine  # noqa: E402
from ml import ict_features as f  # noqa: E402
from ml.data import from_dicts  # noqa: E402
from tests.test_ict_engine import FLAT, LONDON, START, mirror, session  # noqa: E402

NY = ZoneInfo('America/New_York')
CFG = f.CandidateConfig(warmup_bars=0)
GEOMETRY = (('entry', 'entry'), ('stop', 'stop'), ('target_liquidity', 'target'), ('sweep_level', 'sweep_level'),
            ('mss_level', 'mss_level'), ('fvg_high', 'fvg_high'), ('fvg_low', 'fvg_low'))


def detect(dicts, cfg=CFG, symbol='EURUSD', **kwargs):
    return f.detect(symbol, from_dicts(dicts), cfg, **kwargs)


def ny_epoch(*args) -> int:
    return int(dt.datetime(*args, tzinfo=NY).timestamp())


def walk(n, seed=7, start=1788732000):
    """A fat-tailed random walk in M5 bars from Sunday 2026-09-06 22:00 UTC (weekends included, as crypto has)."""
    rng = np.random.default_rng(seed)
    path = 2000 + np.cumsum(rng.standard_t(3, size=n * 5) * 0.25).reshape(n, 5)
    opens = np.concatenate([[2000.0], path[:-1, -1]])
    return [{'t': start + 300 * k, 'o': float(opens[k]), 'h': float(max(opens[k], path[k].max())),
             'l': float(min(opens[k], path[k].min())), 'c': float(path[k, -1]), 'spread': 0.2} for k in range(n)]


def same_rows(a, b) -> bool:
    def same(x, y):
        return x == y or (isinstance(x, float) and isinstance(y, float) and math.isnan(x) and math.isnan(y))
    return len(a) == len(b) and all(r.keys() == q.keys() and all(same(r[k], q[k]) for k in r) for r, q in zip(a, b))


# -- concepts ------------------------------------------------------------------------------------------------
def test_session_clock_and_killzones():
    names = [f.SESSIONS[f.session_of(h * 60 + m)] for h, m in
             ((20, 0), (1, 59), (2, 0), (4, 59), (5, 0), (8, 30), (10, 59), (11, 0), (13, 30), (16, 0), (19, 59))]
    assert names == ['asia', 'asia', 'london_kz', 'london_kz', 'london_mid', 'ny_am_kz', 'ny_am_kz', 'ny_mid',
                     'ny_pm', 'close', 'close']
    assert f.in_killzone(2 * 60, 2) and f.in_killzone(10 * 60 + 55, 4)
    assert not f.in_killzone(5 * 60, 2) and not f.in_killzone(12 * 60, 2)
    assert not f.in_killzone(2 * 60 + 30, 5)                                    # Saturday


def test_trading_day_rolls_at_17_new_york_in_summer_and_winter():
    for date in ((2026, 9, 8), (2026, 1, 13)):                                  # a Tuesday in EDT and one in EST
        stamps = [ny_epoch(*date, 16, 55), ny_epoch(*date, 17, 0), ny_epoch(*date, 23, 55),
                  ny_epoch(date[0], date[1], date[2] + 1, 16, 55), ny_epoch(date[0], date[1], date[2] + 1, 17, 0)]
        minute, weekday, day = f.trading_days(np.array(stamps))
        assert list(minute) == [16 * 60 + 55, 17 * 60, 23 * 60 + 55, 16 * 60 + 55, 17 * 60]
        assert list(weekday) == [1, 1, 1, 2, 2]
        assert list(day - day[0]) == [0, 1, 1, 1, 2]
    # Sunday evening already belongs to Monday's trading day.
    _, weekday, day = f.trading_days(np.array([ny_epoch(2026, 9, 6, 18, 0), ny_epoch(2026, 9, 7, 10, 0)]))
    assert list(weekday) == [6, 0] and day[0] == day[1]


def test_pivots_are_strict_fractals():
    high = np.array([1, 2, 5, 2, 1, 3, 3, 1, 1.0])
    low = np.array([9, 8, 4, 8, 9, 7, 7, 9, 9.0])
    ph, pl = f.pivots(high, low, 2)
    assert list(np.flatnonzero(ph)) == [2] and list(np.flatnonzero(pl)) == [2]   # the equal pair at 5/6 is no pivot
    assert not f.pivots(high[:4], low[:4], 2)[0].any()                           # too short to confirm anything


def test_find_fvg_takes_the_latest_gap_of_enough_size():
    #             0     1     2     3     4     5
    h = np.array([10.0, 10.5, 11.5, 11.6, 12.6, 12.4])
    l = np.array([9.5, 9.9, 10.4, 10.45, 11.7, 11.5])
    atr = np.full(6, 1.0)
    # bullish gaps: candle 2 over candle 0 (10.0-10.4) and candle 4 over candle 2 (11.5-11.7)
    assert f.find_fvg(h, l, atr, 1, 0, 5) == (4, 11.5, 11.7)
    assert f.find_fvg(h, l, atr, 1, 0, 5, min_atr=0.3) == (2, 10.0, 10.4)        # the later gap is too small
    assert f.find_fvg(h, l, atr, 1, 0, 3) == (2, 10.0, 10.4)                     # the leg ends before the later gap
    assert f.find_fvg(h, l, atr, 1, 1, 3) is None                               # candle 0 is outside the leg
    assert f.find_fvg(h, l, atr, -1, 0, 5) is None
    assert f.count_fvgs(h, l, 1, 0, 5) == 2 and f.count_fvgs(h, l, 1, 0, 1) == 0
    # the same candles upside down give the bearish gaps
    assert f.find_fvg(20 - l, 20 - h, atr, -1, 0, 5) == pytest.approx((4, 8.3, 8.5))
    assert f.count_fvgs(20 - l, 20 - h, -1, 0, 5) == 2


def test_order_block_is_the_last_candle_against_the_trade():
    o = np.array([10.0, 10.2, 10.1, 10.3, 10.8])
    c = np.array([10.2, 10.1, 10.3, 10.8, 11.5])      # up, down, up, up, up
    h, l = np.maximum(o, c) + 0.1, np.minimum(o, c) - 0.1
    assert f.order_block(o, h, l, c, 1, 0, 4) == pytest.approx((1, 10.0, 10.3))
    assert f.order_block(o, h, l, c, 1, 2, 4) is None                           # only up candles in the leg
    assert f.order_block(o, h, l, c, -1, 0, 4)[0] == 4                          # for a SELL the last up candle


def test_retracement_is_measured_back_from_the_leg_end():
    assert f.retracement(entry=107.0, extreme=100.0, leg_end=110.0) == pytest.approx(0.3)
    assert f.retracement(entry=93.0, extreme=100.0, leg_end=90.0) == pytest.approx(0.3)      # SELL leg
    assert 0.62 <= f.retracement(103.0, 100.0, 110.0) <= 0.79                                # inside the OTE zone
    assert math.isnan(f.retracement(100.0, 100.0, 100.0))


def test_session_range_publishes_once_and_drops_a_stale_session():
    london = f.SessionRange(f.LONDON)
    assert london.update(119, 1, 5.0, 4.0) is None                              # 01:59, before the window
    assert london.update(120, 1, 10.0, 9.0) is None
    assert london.update(295, 1, 12.0, 9.5) is None
    assert london.update(300, 1, 99.0, 1.0) == (12.0, 9.0)                      # 05:00: the range, without this bar
    assert london.update(305, 1, 99.0, 1.0) is None
    # Data stops inside the window and resumes on another trading day: nothing is published late, and the new
    # day's session starts clean.
    assert london.update(120, 2, 20.0, 19.0) is None
    assert london.update(125, 3, 30.0, 29.0) is None
    assert london.update(300, 3, 99.0, 1.0) == (30.0, 29.0)
    assert london.update(130, 4, 40.0, 39.0) is None
    assert london.update(600, 5, 50.0, 49.0) is None


# -- candidates on the hand-built London session ------------------------------------------------------------
def test_buy_candidate_has_the_ict_engine_plan():
    bars = session()
    rows = detect(bars)
    assert len(rows) == 1
    row = rows[0]
    assert row['side'] == 'BUY' and row['bar_index'] == len(bars) - 1 and row['bar_time'] == bars[-1]['t'] + 300
    assert row['swept_name'] == 'Asia low' and row['sweep_level'] == 99.7 and row['mss_level'] == 100.15
    assert (row['fvg_low'], row['fvg_high'], row['entry']) == (99.9, 99.94, 99.94)
    assert row['stop'] == pytest.approx(99.7 - 0.1 * row['atr'])
    assert row['target'] == pytest.approx(row['entry'] + 2 * row['risk'])
    engine = ict_engine.detect('EURUSD', bars, ict_engine.IctConfig())[0]
    for theirs, ours in GEOMETRY + (('bar_time', 'bar_time'), ('swept_name', 'swept_name'), ('atr', 'atr')):
        assert row[ours] == pytest.approx(engine[theirs]), ours
    assert f.payload(row, 0.61)['ml_probability'] == 0.61 and f.payload(row)['signal'] == 'BUY_SETUP'


def test_buy_candidate_features_describe_the_setup():
    row = detect(session())[0]
    atr = row['atr']
    assert set(f.FEATURES) <= set(row) and all(isinstance(row[k], float) for k in f.FEATURES)
    assert row['direction'] == 1 and f.POOL_KINDS[int(row['pool_kind'])] == 'asia'
    assert row['n_pools_swept'] == 2                    # the Asia low and the M5 swing low at the same price
    assert row['in_killzone'] == 1 and f.SESSIONS[int(row['session_sweep'])] == 'london_kz'
    assert row['ny_hour'] == pytest.approx(2.5) and row['weekday'] == 2
    assert row['sweep_depth_atr'] == pytest.approx(0.1 / atr)                 # 99.7 under the 99.8 pool
    assert row['bars_sweep_to_mss'] == 2 and row['leg_bars'] == 2 and row['fvg_age_bars'] == 0
    assert row['mss_body_atr'] == pytest.approx(0.45 / atr) and row['mss_close_beyond_atr'] == pytest.approx(0.25 / atr)
    assert row['fvg_size_atr'] == pytest.approx(0.04 / atr) and row['fvg_count_leg'] == 1
    assert row['ob_overlap'] == 1 and row['ob_dist_atr'] == pytest.approx(0.04 / atr)   # the 02:20 down candle
    assert row['ote_fib'] == pytest.approx((100.45 - 99.94) / (100.45 - 99.7)) and row['in_ote'] == 1
    assert row['risk_atr'] == pytest.approx(row['risk'] / atr) and row['entry_dist_atr'] == pytest.approx(0.46 / atr)
    assert math.isnan(row['pd_prev_day'])               # no earlier trading day in this history


def test_sell_candidate_is_the_mirror_image_with_the_same_features():
    buy, sell = detect(session())[0], detect(mirror(session()))[0]
    assert sell['side'] == 'SELL' and sell['swept_name'] == 'Asia high' and sell['direction'] == -1
    assert sell['entry'] == pytest.approx(200 - buy['entry']) and sell['stop'] == pytest.approx(200 - buy['stop'])
    assert sell['target'] == pytest.approx(200 - buy['target']) and sell['stop'] > sell['entry'] > sell['target']
    for name in f.FEATURES:
        if name not in ('direction', 'atr_pct'):        # atr_pct divides by the price, which the mirror changes
            assert sell[name] == pytest.approx(buy[name], nan_ok=True), name


def test_any_session_is_a_candidate_and_the_killzone_is_only_a_feature():
    bars = session([FLAT] * 120 + LONDON)                # the same sweep and shift at noon New York
    assert ict_engine.detect('EURUSD', bars, ict_engine.IctConfig()) == []
    rows = detect(bars)
    assert len(rows) == 1
    assert rows[0]['in_killzone'] == 0 and f.SESSIONS[int(rows[0]['session_now'])] == 'ny_mid'
    assert rows[0]['entry'] == 99.94 and rows[0]['sweep_level'] == 99.7
    # By noon the quiet London and NY AM ranges are pools too. The run takes them first (99.95) and the Asia low
    # after (99.8); the most significant pool taken keeps the name while the extreme moves on.
    assert rows[0]['swept_name'] == 'London low' and rows[0]['n_pools_swept'] == 2
    assert rows[0]['sweep_depth_atr'] == pytest.approx(0.25 / rows[0]['atr'])


def test_no_candidate_without_gap_shift_or_room():
    no_gap = LONDON[:-1] + [(99.95, 100.45, 99.85, 100.4), FLAT, FLAT]          # the shift candle fills the gap
    assert detect(session(no_gap)) == []
    weak = LONDON[:-1] + [(99.95, 100.12, 99.94, 100.1)] + [FLAT] * 40          # never closes above the swing
    assert detect(session(weak)) == []
    assert detect(session(), f.CandidateConfig(warmup_bars=0, min_risk_atr=5.0)) == []   # stop tighter than allowed
    assert detect(session(), f.CandidateConfig(warmup_bars=0, min_fvg_atr=2.0)) == []    # gap smaller than allowed


def test_weekend_bars_never_arm_except_for_crypto():
    saturday = [{**b, 't': b['t'] + 3 * 86400} for b in session()]              # the London pattern on Saturday
    assert detect(saturday) == []
    assert len(detect(saturday, f.CandidateConfig(warmup_bars=0, crypto=True))) == 1


def test_gap_may_come_one_candle_after_the_shift_but_the_shift_must_come_within_three_hours():
    quiet = (99.95, 100.0, 99.85, 99.95)                 # overlaps the 02:20 candle, so the drift leaves no gap
    shift, follow = (99.95, 100.45, 99.94, 100.4), (100.4, 100.6, 100.3, 100.5)
    late = session(LONDON[:-1] + [quiet] * 30 + [shift, follow])
    rows = detect(late)
    assert len(rows) == 1 and rows[0]['bar_index'] == len(late) - 1
    assert (rows[0]['fvg_low'], rows[0]['fvg_high']) == (100.0, 100.3)          # over the quiet candle before the shift
    assert rows[0]['bars_sweep_to_mss'] == 32 and rows[0]['fvg_age_bars'] == 0
    assert detect(session(LONDON[:-1] + [quiet] * 36 + [shift, follow])) == []  # 38 bars after the extreme
    assert detect(late, start_index=len(late)) == []                            # asked only for newer bars
    # A gap left earlier in the leg is used when the shift candle makes none: flat candles sit above the 02:20 high.
    older = detect(session(LONDON[:-1] + [FLAT] * 30 + [shift, follow]))
    assert len(older) == 1 and older[0]['bar_index'] == len(late) - 2
    assert (older[0]['fvg_low'], older[0]['fvg_high']) == (99.9, 99.95) and older[0]['fvg_age_bars'] == 30


# -- liquidity pools ------------------------------------------------------------------------------------------
def previous_day_then(london):
    """Monday 19:00 -> Tuesday 19:00 New York with one spike to 99.5 / 100.5, then the usual Wednesday session."""
    monday = [FLAT] * 288
    monday[150] = (100.0, 100.5, 99.5, 100.0)                                   # Tuesday 07:30
    first = [{'t': START - 86400 + 300 * k, 'o': o, 'h': h, 'l': l, 'c': c} for k, (o, h, l, c) in enumerate(monday)]
    return first + session(london)


def test_previous_day_low_is_a_pool_after_the_17_new_york_roll():
    deep = LONDON[:4] + [(99.85, 99.9, 99.4, 99.8)] + LONDON[5:]                # 02:20 trades under 99.5
    rows = detect(previous_day_then(deep))
    row = rows[-1]
    assert row['side'] == 'BUY' and row['swept_name'] == 'PDL' and f.POOL_KINDS[int(row['pool_kind'])] == 'day'
    assert row['sweep_level'] == 99.4 and row['sweep_depth_atr'] == pytest.approx(0.1 / row['atr'])
    assert row['n_pools_swept'] == 2                    # PDL and the swing low that the spike left
    assert row['pool_age_bars'] == 376 - 264            # created at the roll (Tuesday 17:00), swept Wednesday 02:20
    assert 0 <= row['pd_prev_day'] <= 1                 # the previous day's range is known
    # Without that deeper candle the previous day's low is untouched and the Asia low names the sweep.
    assert detect(previous_day_then(LONDON))[-1]['swept_name'] == 'Asia low'


def test_a_pool_counts_once():
    early = [FLAT] * 12 + [(100.0, 100.05, 99.75, 100.0)] + [FLAT] * 11         # 01:00 takes the Asia low, no shift
    shapes = [FLAT] * 12 + [(100.0, 100.2, 99.9, 100.0)] + [(100.0, 100.1, 99.9, 100.0)] * 46
    shapes += [(100.0, 100.1, 99.8, 100.0)] + early + LONDON
    bars = [{'t': START + 300 * k, 'o': o, 'h': h, 'l': l, 'c': c} for k, (o, h, l, c) in enumerate(shapes)]
    # With a one-hour wait the 01:00 sweep has lapsed by London. The Asia low is spent, so what London sweeps is
    # the swing low that the 01:00 wick left behind.
    rows = detect(bars, f.CandidateConfig(warmup_bars=0, mss_wait_bars=10))
    assert len(rows) == 1
    assert rows[0]['swept_name'] == 'swing low 72' and f.POOL_KINDS[int(rows[0]['pool_kind'])] == 'swing'
    assert rows[0]['n_pools_swept'] == 1 and rows[0]['pool_age_bars'] == 88 - 78  # known six bars after its pivot
    # With the normal three hours it is still the same run, and the Asia low it took first keeps the name.
    rows = detect(bars)
    assert len(rows) == 1 and rows[0]['swept_name'] == 'Asia low' and rows[0]['sweep_level'] == 99.7


def test_swing_pool_expires():
    assert detect(session())[0]['n_pools_swept'] == 2
    short = f.CandidateConfig(warmup_bars=0, swing_life_bars=20)                # the swing low is 22 bars old
    assert detect(session(), short)[0]['n_pools_swept'] == 1


# -- no lookahead, and agreement with the killzone engine on long random data ----------------------------------
def test_truncating_the_future_never_changes_a_candidate():
    bars = walk(4000)
    cfg = f.CandidateConfig(warmup_bars=300)
    full = detect(bars, cfg, symbol='XAUUSD')
    assert len(full) > 40
    cuts = sorted({r['bar_index'] + 1 for r in full} | {301, 1000, 2500, 3999})
    for n in cuts:
        assert same_rows(detect(bars[:n], cfg, symbol='XAUUSD'), [r for r in full if r['bar_index'] < n]), n


def test_rewriting_the_future_never_changes_a_candidate():
    bars, other = walk(4000), walk(4000, seed=99)
    cfg = f.CandidateConfig(warmup_bars=300)
    full = detect(bars, cfg, symbol='XAUUSD')
    for n in (1500, 2777):
        shift = bars[n - 1]['c'] - other[n]['o']
        future = [{**b, **{k: b[k] + shift for k in 'ohlc'}} for b in other[n:]]
        mixed = detect(bars[:n] + future, cfg, symbol='XAUUSD')
        assert same_rows([r for r in mixed if r['bar_index'] < n], [r for r in full if r['bar_index'] < n])


def test_start_index_only_hides_older_candidates():
    bars = walk(3000)
    cfg = f.CandidateConfig(warmup_bars=300)
    full = detect(bars, cfg, symbol='XAUUSD')
    assert same_rows(detect(bars, cfg, symbol='XAUUSD', start_index=2000), [r for r in full if r['bar_index'] >= 2000])


def test_candidates_are_well_formed_on_random_data():
    cfg = f.CandidateConfig(warmup_bars=300)
    rows = detect(walk(6000, seed=11), cfg, symbol='XAUUSD')
    assert len(rows) > 60 and {r['side'] for r in rows} == {'BUY', 'SELL'}
    assert [r['bar_index'] for r in rows] == sorted(r['bar_index'] for r in rows)
    assert len({(r['bar_index'], r['side']) for r in rows}) == len(rows)
    for r in rows:
        d = r['direction']
        assert d == (1 if r['side'] == 'BUY' else -1)
        assert d * (r['entry'] - r['sweep_level']) > 0 and d * (r['sweep_level'] - r['stop']) > 0
        assert r['target'] == pytest.approx(r['entry'] + d * cfg.rr * r['risk'])
        assert r['entry'] == (r['fvg_high'] if d == 1 else r['fvg_low']) and r['fvg_high'] > r['fvg_low']
        assert r['risk_atr'] >= cfg.min_risk_atr and r['fvg_size_atr'] > 0
        assert r['entry_dist_atr'] >= 0 and r['sweep_depth_atr'] > 0 and r['weekday'] < 5
        assert 0 <= r['bars_sweep_to_mss'] <= cfg.mss_wait_bars and 0 <= r['ote_fib'] <= 1
        assert 0 <= r['sweep_wick_ratio'] <= 1 and 0 <= r['mss_body_ratio'] <= 1
        assert r['in_killzone'] in (0, 1) and 0 <= r['pool_kind'] < len(f.POOL_KINDS)
        assert 0 <= r['session_now'] < len(f.SESSIONS) and r['asset'] == f.ASSETS.index('metal')
        for name in f.FEATURES:
            assert math.isfinite(r[name]) or (name in f.MAY_BE_MISSING and math.isnan(r[name])), name


def test_every_killzone_engine_setup_is_a_candidate_with_the_same_plan():
    bars = walk(30000, seed=5)
    by_key = {(r['bar_time'], r['side']): r for r in detect(bars, symbol='XAUUSD')}
    setups = ict_engine.detect('XAUUSD', [{k: b[k] for k in 'tohlc'} for b in bars], ict_engine.IctConfig())
    assert len(setups) >= 8
    for body in setups:
        row = by_key[(body['bar_time'], 'BUY' if body['signal'] == 'BUY_SETUP' else 'SELL')]
        assert row['in_killzone'] == 1 and row['pool_kind'] < f.POOL_KINDS.index('swing')
        for theirs, ours in GEOMETRY:
            assert row[ours] == pytest.approx(body[theirs], abs=1e-6), (body['event_id'], ours)
