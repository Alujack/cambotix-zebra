"""The SMC engine (scripts/smc_engine.py) on a hand-built scenario: sweep -> MSS -> FVG -> retest -> confirmed close.
Every emitted payload must also pass the analyzer's own SMC rules, which is the parity that matters."""
import datetime as dt
import sys
from pathlib import Path

import pytest

from app.domain import Signal, technical_rules

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import smc_engine  # noqa: E402

UTC = dt.timezone.utc
# Bar 140 opens Friday 2026-09-04 06:30 UTC = 02:30 New York, inside the London killzone.
BAR_140 = int(dt.datetime(2026, 9, 4, 6, 30, tzinfo=UTC).timestamp())
START = BAR_140 - 140 * 900


def bar(i, o=3500.0, h=3503.0, l=3497.0, c=3500.0):
    return {'t': START + i * 900, 'o': o, 'h': h, 'l': l, 'c': c}


def m15(overrides=None, count=150):
    rows = [bar(i) for i in range(count)]
    for i, values in {110: dict(h=3524.0), 125: dict(h=3504.0), 130: dict(l=3495.0),
                      140: dict(o=3498.0, h=3498.5, l=3493.0, c=3497.0),        # sweep of the swing low, bearish candle
                      141: dict(o=3497.0, h=3509.0, l=3496.0, c=3508.0),        # displacement through the swing high
                      142: dict(o=3508.0, h=3508.5, l=3503.0, c=3507.0),        # fair value gap candle
                      143: dict(o=3502.0, h=3506.5, l=3500.0, c=3506.0),        # retest of the midpoint, close above the gap
                      **(overrides or {})}.items():
        rows[i] = bar(i, **values)
    return rows


def daily(bullish=True):
    day0 = dt.datetime(2026, 8, 25, tzinfo=UTC)
    highs = [3470, 3480, 3490, 3500, 3485, 3480, 3478, 3510, 3515, 3530]
    rows = []
    for k, high in enumerate(highs):
        rows.append({'t': int((day0 + dt.timedelta(days=k)).timestamp()), 'o': high - 15.0, 'h': float(high),
                     'l': high - 20.0 if k < 9 else 3480.0, 'c': high - 5.0})
    if not bullish:   # mirror: falling structure, closes below the pivot low
        rows = [{**r, 'h': 7000 - r['l'], 'l': 7000 - r['h'], 'o': 7000 - r['o'], 'c': 7000 - r['c']} for r in rows]
    return rows


def four_hour():
    first = dt.datetime(2026, 9, 1, tzinfo=UTC)
    highs = [3480, 3485, 3490, 3500, 3490, 3486, 3484, 3505, 3508, 3510, 3512, 3514, 3516, 3518, 3520, 3522, 3524, 3526]
    return [{'t': int((first + dt.timedelta(hours=4 * k)).timestamp()), 'o': h - 8.0, 'h': float(h), 'l': h - 12.0, 'c': h - 3.0}
            for k, h in enumerate(highs)]


def weekly():
    monday = dt.datetime(2026, 7, 13, tzinfo=UTC)
    return [{'t': int((monday + dt.timedelta(weeks=k)).timestamp()), 'o': 3480.0, 'h': 3540.0, 'l': 3470.0, 'c': 3500.0}
            for k in range(8)]


def run(overrides=None, bullish=True, count=150, **config):
    engine = smc_engine.Engine('XAUUSD', smc_engine.Config(**config))
    return engine, engine.run(m15(overrides, count), daily(bullish), four_hour(), weekly())


@pytest.fixture(autouse=True)
def analyzer_settings(monkeypatch):
    for key, value in {'NEWS_FILTER': 'false', 'FILTER_SESSIONS': 'true', 'KILLZONES': 'London,NY AM', 'REQUIRE_HTF_BIAS': 'true',
                       'REQUIRE_DISCOUNT': 'true', 'MIN_RR': '1.5', 'MIN_SMC_SCORE': '70', 'SYMBOLS': 'XAUUSD'}.items():
        monkeypatch.setenv(key, value)


def test_confirmed_entry_is_emitted_once_and_passes_the_analyzer():
    engine, emitted = run()
    assert len(emitted) == 1
    body = emitted[0]
    assert body['signal'] == 'BUY_SETUP' and body['bar_time'] == START + 144 * 900
    assert body['event_id'] == f'XAUUSD-15m-smc-{body["bar_time"]}-BUY_SETUP'
    assert body['entry_mode'] == 'confirmed_close' and body['entry'] == 3506.0 and body['setup_entry'] == 3500.75
    assert body['setup_bar_time'] == START + 143 * 900
    assert body['sweep_level'] == 3493.0 and body['swept_name'] == 'Swing low' and body['mss_level'] == 3504.0
    assert (body['fvg_bottom'], body['fvg_top']) == (3498.5, 3503.0)
    assert (body['ob_top'], body['ob_bottom']) == (3498.5, 3493.0)
    assert (body['range_low'], body['range_high']) == (3493.0, 3524.0)
    assert body['target_liquidity'] == 3530.0 and body['target_name'] == 'PDH'
    assert (body['pdh'], body['pdl'], body['pwh'], body['pwl']) == (3530.0, 3480.0, 3540.0, 3470.0)
    assert body['htf_bias'] == body['daily_bias'] == body['h4_bias'] == 1
    assert body['killzone'] == 'London' and body['score'] == 100
    assert body['hit_rate'] is None and body['samples'] == 0
    assert 3492.0 < body['stop'] < 3493.0 and body['stop'] == round(body['stop'], 2)
    signal = Signal.model_validate(body)
    assert technical_rules(signal, now=body['bar_time']) == []
    assert 'confirmed - reference entry at close' in engine.plan.message


def test_replay_is_deterministic_and_never_resends():
    _, first = run()
    _, second = run()
    assert first == second
    engine = smc_engine.Engine('XAUUSD', smc_engine.Config())
    longer = engine.run(m15(count=190), daily(), four_hour(), weekly())
    assert longer == first                       # 40 more flat bars: the same single entry, nothing new


def test_no_retest_means_no_entry():
    engine, emitted = run({143: {}})             # bar 143 is a plain flat bar again
    assert emitted == [] and engine.plan is not None and engine.plan.state == 1


def test_direction_disagreement_blocks_the_setup():
    engine, emitted = run(bullish=False)
    assert emitted == [] and engine.plan is None


def test_closing_through_the_gap_cancels_the_plan():
    engine, emitted = run({143: dict(o=3502.0, h=3503.0, l=3496.0, c=3497.0)})
    assert emitted == [] and engine.plan.message == 'CANCELLED - FVG closed through'


def test_outcome_memory_feeds_the_next_payload():
    overrides = {150: dict(o=3506.0, h=3531.0, l=3505.0, c=3528.0)}        # TP1 (PDH 3530) reached after entry
    engine, emitted = run(overrides, count=160)
    assert len(emitted) == 1 and engine.wins == 1 and engine.plan.message == 'TP1 REACHED - example finished'
    assert engine.status.startswith('bias D+1/4H+1')


def test_pivot_requires_a_strict_extreme():
    flat = [bar(i) for i in range(10)]
    assert smc_engine.pivot(flat, 6, 3) == (None, None)
    flat[3] = bar(3, h=3510.0, l=3490.0)
    assert smc_engine.pivot(flat, 6, 3) == (3510.0, 3490.0)
    assert smc_engine.round_tick(3492.336, 0.01, 'floor') == 3492.33
    assert smc_engine.round_tick(3492.331, 0.01, 'ceil') == 3492.34
    assert smc_engine.round_tick(3500.755, 0.01) == 3500.76
