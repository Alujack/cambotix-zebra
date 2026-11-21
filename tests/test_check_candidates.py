"""ml/check_candidates.py on random-walk M5 bars: clean candidates pass, each reject class is counted."""
import pytest

pytest.importorskip('numpy')               # the ML layer is optional: requirements-ml.txt
pytest.importorskip('pandas')

from ml import check_candidates as cc  # noqa: E402
from ml.data import from_dicts  # noqa: E402
from ml.ict_features import POOL_KINDS, CandidateConfig, detect  # noqa: E402
from tests.test_ict_features import walk  # noqa: E402

CFG = CandidateConfig(warmup_bars=300)
CHRISTMAS = 1798156800                     # 2026-12-25 00:00 UTC: the walk below crosses into 2027


def test_clean_candidates_pass_and_the_year_table_adds_up():
    m5 = from_dicts(walk(6000, seed=11, start=CHRISTMAS))
    result = cc.run_checks('XAUUSD', m5, CFG)
    assert result['passed'] and not any(result['rejects'].values())
    assert [y['year'] for y in result['years']] == [2026, 2027]
    assert sum(y['candidates'] for y in result['years']) == result['candidates'] > 60
    assert sum(y['m5_bars'] for y in result['years']) == 6000
    for y in result['years']:
        assert sum(y['pools'].values()) == y['candidates'] and set(y['pools']) == set(POOL_KINDS)
        assert 0 < y['trading_days'] <= 16 and 0 <= y['buy_share'] <= 1
    assert set(result['missing']) <= cc.MAY_BE_MISSING
    assert '| 2027 |' in cc.markdown(result) and '**pass**' in cc.markdown(result)


def test_each_reject_class_is_counted():
    m5 = from_dicts(walk(3000))
    rows = detect('XAUUSD', m5, CFG)
    assert not any(cc.check_rows(rows, CFG).values())
    broken = [dict(r) for r in rows[:6]]
    broken[0]['stop'] = broken[0]['entry'] + (1 if broken[0]['side'] == 'BUY' else -1)     # stop beyond the entry
    broken[1]['target'] = broken[1]['entry']                                                # no reward
    broken[2]['risk_atr'] = 0.1
    broken[3]['mss_body_atr'] = float('nan')                                                # a required feature
    broken[4]['opp_pool_r'] = float('nan')                                                  # optional: allowed
    broken.append(dict(broken[5]))                                                          # the same bar twice
    broken.append(dict(rows[0]))                                                            # and one out of order
    bad = cc.check_rows(broken, CFG)
    assert bad == {'stop_wrong_side': 1, 'target_wrong_side': 1, 'target_not_rr': 2, 'risk_too_small': 1,
                   'duplicates': 2, 'out_of_order': 1, 'feature_missing': 1}


def test_a_thin_year_and_a_one_sided_history_are_flagged():
    def year(name, per_day, days=250):
        return {'year': name, 'trading_days': days, 'per_day': per_day}
    rows = [{'side': 'BUY'}] * 7 + [{'side': 'SELL'}] * 3
    flags = cc.find_flags([year(2004, 1.0), year(2005, 5.0), year(2006, 5.5), year(2007, 12.0), year(2008, 0.2, days=40)],
                          rows)
    assert len(flags) == 3 and flags[0].startswith('2004') and flags[1].startswith('2007') and 'BUY share' in flags[2]
    assert cc.find_flags([year(2005, 5.0), year(2006, 5.5)], [{'side': 'BUY'}, {'side': 'SELL'}]) == []
