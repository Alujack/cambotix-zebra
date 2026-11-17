import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
from ict_engine import IctConfig, detect, killzone  # noqa: E402
from app.domain import Signal, ict_rules  # noqa: E402

NY = dt.timezone(dt.timedelta(hours=-4))          # EDT, for building test timestamps
START = int(dt.datetime(2026, 9, 8, 19, 0, tzinfo=NY).timestamp())   # Tuesday 19:00 New York = Wednesday's session

FLAT = (100.0, 100.05, 99.95, 100.0)
# London killzone from 02:00 New York: a swing high at 100.15, a sweep of the Asia low (99.8) down to 99.7,
# then a displacement candle that closes above the swing (MSS) and leaves a gap over the 02:20 candle's high.
LONDON = [FLAT,
          (100.0, 100.15, 99.95, 100.0),          # 02:05 swing high (pivot 2/2)
          (100.0, 100.05, 99.85, 99.9),
          (99.9, 99.95, 99.75, 99.85),            # 02:15 trades below the Asia low: BUY armed
          (99.85, 99.9, 99.7, 99.8),              # 02:20 deeper: sweep extreme 99.7
          (99.8, 99.98, 99.78, 99.95),
          (99.95, 100.45, 99.94, 100.4)]          # 02:30 closes above 100.15; FVG 99.90-99.94


def session(london=LONDON):
    """Tuesday 19:00 -> Wednesday 02:00+ New York in M5 bars: quiet, the Asia range 99.8-100.2, quiet, then `london`."""
    shapes = [FLAT] * 12                                                        # 19:00-20:00
    shapes += [(100.0, 100.2, 99.9, 100.0)] + [(100.0, 100.1, 99.9, 100.0)] * 46 + [(100.0, 100.1, 99.8, 100.0)]
    shapes += [FLAT] * 24                                                       # 00:00-02:00
    shapes += london
    return [{'t': START + 300 * k, 'o': o, 'h': h, 'l': l, 'c': c} for k, (o, h, l, c) in enumerate(shapes)]


def mirror(bars):
    """The same bars upside down around 100, for the SELL side."""
    return [{'t': b['t'], 'o': 200 - b['o'], 'h': 200 - b['l'], 'l': 200 - b['h'], 'c': 200 - b['c']} for b in bars]


@pytest.fixture(autouse=True)
def eurusd(monkeypatch):
    monkeypatch.setenv('SYMBOLS', 'XAUUSD,EURUSD')
    monkeypatch.setenv('ICT_SYMBOLS', 'EURUSD')
    monkeypatch.delenv('ICT_MIN_RR', raising=False)


def test_killzones_follow_new_york_time():
    cfg = IctConfig()
    assert killzone(int(dt.datetime(2026, 9, 9, 2, 30, tzinfo=NY).timestamp()), cfg) == 'London'
    assert killzone(int(dt.datetime(2026, 9, 9, 8, 30, tzinfo=NY).timestamp()), cfg) == 'NY AM'
    assert killzone(int(dt.datetime(2026, 9, 9, 12, 0, tzinfo=NY).timestamp()), cfg) is None
    assert killzone(int(dt.datetime(2026, 9, 12, 2, 30, tzinfo=NY).timestamp()), cfg) is None      # Saturday


def test_buy_setup_after_asia_low_sweep_passes_the_analyzer():
    bars = session()
    setups = detect('EURUSD', bars, IctConfig())
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'BUY_SETUP' and body['model'] == 'ict' and body['timeframe'] == '5m'
    assert body['bar_time'] == bars[-1]['t'] + 300                         # the 02:30 candle's close
    assert body['swept_name'] == 'Asia low' and body['sweep_level'] == 99.7 and body['mss_level'] == 100.15
    assert (body['fvg_low'], body['fvg_high']) == (99.9, 99.94) and body['entry'] == 99.94
    risk = body['entry'] - body['stop']
    assert body['stop'] < 99.7 and body['target_liquidity'] == pytest.approx(body['entry'] + 2 * risk)
    assert ict_rules(Signal.model_validate(body)) == []


def test_sell_setup_is_the_mirror_image():
    setups = detect('EURUSD', mirror(session()), IctConfig())
    assert len(setups) == 1
    body = setups[0]
    assert body['signal'] == 'SELL_SETUP' and body['swept_name'] == 'Asia high'
    assert body['sweep_level'] == pytest.approx(100.3) and body['entry'] == pytest.approx(100.06)
    assert body['stop'] > 100.3 and body['target_liquidity'] < body['entry']
    assert ict_rules(Signal.model_validate(body)) == []


def test_no_setup_without_a_gap_or_outside_the_killzone():
    no_gap = LONDON[:-1] + [(99.95, 100.45, 99.85, 100.4), FLAT, FLAT]       # the shift candle overlaps 02:20's high
    assert detect('EURUSD', session(no_gap), IctConfig()) == []
    assert detect('EURUSD', session(), IctConfig(killzones=('NY AM',))) == []


def test_no_setup_without_a_structure_shift():
    weak = LONDON[:-1] + [(99.95, 100.12, 99.94, 100.1)] + [FLAT] * 40        # never closes above the 100.15 swing
    assert detect('EURUSD', session(weak), IctConfig()) == []
