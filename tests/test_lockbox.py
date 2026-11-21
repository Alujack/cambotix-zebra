"""The lockbox rules of plan v2: the split, the guard on development code, and the run-once final test."""
import re
from pathlib import Path

import pytest

np = pytest.importorskip('numpy')
pd = pytest.importorskip('pandas')
pytest.importorskip('lightgbm')
pytest.importorskip('sklearn')

from ml import dataset, final_test, lockbox, predict, train  # noqa: E402
from tests.synthetic_ml import YEAR, candidates  # noqa: E402

ML = Path(lockbox.__file__).resolve().parent


def spanning(n=9000, seed=1):
    """Five development years and one lockbox year of synthetic candidates with a real signal."""
    return candidates(n, seed=seed, start=lockbox.LOCK_EPOCH - 5 * YEAR, years=6.0)


def test_lock_start_is_the_frozen_date():
    assert lockbox.LOCK_START == '2024-11-20' and lockbox.LOCK_EPOCH == 1732060800


def test_split_puts_each_candidate_in_one_file_or_neither():
    lock = lockbox.LOCK_EPOCH
    df = pd.DataFrame({'bar_time': [lock - 9000, lock - 3600, lock, lock + 60],
                       'end_time': [lock - 1.0, lock + 600.0, lock + 900.0, lock + 5000.0]})
    dev, locked, dropped = lockbox.split(df)
    assert list(dev.index) == [0] and list(locked.index) == [2, 3] and dropped == 1     # row 1 straddles the date
    assert lockbox.guard(dev) is dev
    for frame in (locked, df.iloc[[1]]):
        with pytest.raises(lockbox.LockboxError):
            lockbox.guard(frame)


def test_development_code_refuses_a_file_with_lockbox_rows(tmp_path):
    df = spanning(600)
    dev_path, locked_path, counts = lockbox.write(df, 'x_ict', tmp_path)
    assert counts['development'] + counts['lockbox'] + counts['straddling_dropped'] == len(df)
    assert counts['lockbox'] > 50 and locked_path.parent.name == 'lockbox'
    assert len(train.load(dev_path)) > 0                                    # the development file loads
    for reader in (train.load, train.filter_counts):
        with pytest.raises(lockbox.LockboxError):
            reader(locked_path)                                             # the lockbox file never does
    mixed = tmp_path / 'mixed.parquet'
    df.to_parquet(mixed, index=False)
    with pytest.raises(lockbox.LockboxError):
        train.load(mixed)
    with pytest.raises(lockbox.LockboxError):
        dataset.summary(df, {'symbol': 'XAUUSD'})                           # reports describe development rows only


def test_only_the_final_test_can_reach_the_lockbox_reader():
    """No module under ml/ except lockbox.py and final_test.py names the lockbox reader or its file."""
    for path in ML.glob('*.py'):
        if path.name in ('lockbox.py', 'final_test.py'):
            continue
        source = path.read_text(encoding='utf-8')
        assert not re.search(r'open_once|locked_file|read_parquet\([^)]*lockbox', source), path.name
    assert 'open_once' in (ML / 'final_test.py').read_text(encoding='utf-8')


def saved_model(tmp_path, dev, passed, threshold='from validation'):
    bundle, meta = train.train_final(dev, 150, 0)
    if threshold != 'from validation':
        meta['threshold'] = threshold
    meta.update({'gates': [{'gate': 1, 'passed': passed}], 'gates_passed': passed, 'expected': {}})
    return train.save_model(bundle, meta, tmp_path / 'models', 'XAUUSD')


def test_final_test_stays_closed_for_a_failed_or_cutless_model(tmp_path):
    df = spanning(4000)
    dev_path, _, _ = lockbox.write(df, 'x_ict', tmp_path)
    dev = train.load(dev_path)
    saved_model(tmp_path, dev, passed=False)
    with pytest.raises(final_test.NotAllowed, match='failed development gates'):
        final_test.run('XAUUSD', 'x_ict', tmp_path / 'models', tmp_path)
    assert lockbox.record('XAUUSD', tmp_path / 'models') is None             # nothing was opened or sealed
    (tmp_path / 'models' / 'xauusd_ict_v2.json').unlink()
    saved_model(tmp_path, dev, passed=True, threshold=None)
    with pytest.raises(final_test.NotAllowed, match='no cut'):
        final_test.run('XAUUSD', 'x_ict', tmp_path / 'models', tmp_path)
    assert lockbox.record('XAUUSD', tmp_path / 'models') is None


def test_final_test_runs_once_and_its_result_unlocks_or_blocks_prediction(tmp_path):
    df = spanning()
    dev_path, _, counts = lockbox.write(df, 'x_ict', tmp_path)
    saved = saved_model(tmp_path, train.load(dev_path), passed=True)
    models = tmp_path / 'models'
    with pytest.raises(predict.ModelRefused, match='has not run'):
        predict.load_model('XAUUSD', models)

    result = final_test.run('XAUUSD', 'x_ict', models, tmp_path)
    assert result['model'] == saved['version'] and result['tradable_candidates'] > 0.9 * counts['lockbox'] - 5
    assert result['passed'] and all(c['passed'] for c in result['criteria'])    # the synthetic signal is strong
    assert result['model_stats']['expectancy_r'] > result['all_tradable_stats']['expectancy_r'] + 0.3
    assert lockbox.record('XAUUSD', models)['passed'] is True
    assert '**PASSED**' in final_test.markdown(result)
    assert predict.load_model('XAUUSD', models)[1]['version'] == saved['version']

    with pytest.raises(lockbox.LockboxError, match='not opened twice'):
        final_test.run('XAUUSD', 'x_ict', models, tmp_path)
    with pytest.raises(lockbox.LockboxError, match='never overwritten'):
        lockbox.seal('XAUUSD', models, {'passed': False})


def test_final_test_criteria_fail_a_model_that_is_not_good_enough():
    model = {'trades': 150, 'expectancy_r': 0.08, 'profit_factor': 1.15, 'max_drawdown_r': 22.0}
    everything = {'trades': 900, 'expectancy_r': 0.06, 'profit_factor': 1.1, 'max_drawdown_r': 60.0}
    rows = final_test.criteria(model, everything, years=2.0)
    assert [r['passed'] for r in rows] == [False, False, False]              # edge too small, drawdown, 75 a year
    good = {'trades': 260, 'expectancy_r': 0.2, 'profit_factor': 1.5, 'max_drawdown_r': 9.0}
    assert all(r['passed'] for r in final_test.criteria(good, everything, years=2.0))
