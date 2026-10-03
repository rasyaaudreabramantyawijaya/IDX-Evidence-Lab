import pytest
from idx_evidence_lab.studies_transforms import transform_series

DATES = ['2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07']


def run(values, transform, window=2, field='close', calendar=None):
    rows = [{'date': day, field: value} for day, value in zip(DATES, values)]
    return transform_series(rows, field=field, transform=transform, window=window,
                            calendar=calendar or DATES[:len(values)], unit='IDR')


@pytest.mark.parametrize('transform,window,expected', [
    ('difference', 2, [None, 1., 1.]),
    ('pct_change', 2, [None, 1., .5]),
    ('rolling_mean', 2, [None, 1.5, 2.5]),
    ('rolling_std', 2, [None, .7071067811865476, .7071067811865476]),
    ('robust_z', 3, [None, None, .6744907594765952]),
])
def test_hand_calculated_linear_reference(transform, window, expected):
    actual = run([1, 2, 3], transform, window)['series']
    for row, want in zip(actual, expected):
        if want is None:
            assert row['value'] is None and row['reason']
        else:
            assert row['value'] == pytest.approx(want, abs=1e-10, rel=1e-8)


def test_gap_invalidates_trailing_window():
    result = transform_series([{'date': DATES[0], 'close': 1}, {'date': DATES[2], 'close': 3}],
                              field='close', transform='rolling_mean', window=2, calendar=DATES[:3], unit='IDR')
    assert [r['value'] for r in result['series']] == [None, None, None]
    assert result['series'][-1]['reason'] == 'MISSING_WINDOW'


def test_zero_mad_and_zero_denominator_are_null():
    assert run([2, 2, 2], 'robust_z', 3)['series'][-1]['reason'] == 'ZERO_MAD'
    assert run([0, 2], 'pct_change')['series'][-1]['reason'] == 'NONPOSITIVE_BASE'
    assert run([1, -2], 'pct_change')['series'][-1]['value'] is None


def test_signed_flow_pct_is_unsupported():
    with pytest.raises(ValueError):
        run([-2, 1], 'pct_change', field='foreign_net_flow')
    assert run([-2, 1], 'difference', field='foreign_net_flow')['series'][-1]['value'] == 3


@pytest.mark.parametrize('rows,calendar', [
    ([{'date': DATES[1], 'close': 2}, {'date': DATES[0], 'close': 1}], DATES[:2]),
    ([{'date': DATES[0], 'close': 1}, {'date': DATES[0], 'close': 2}], DATES[:2]),
    ([{'date': DATES[0], 'close': float('nan')}], DATES[:1]),
    ([{'date': DATES[0], 'close': float('inf')}], DATES[:1]),
    ([{'date': DATES[0], 'close': True}], DATES[:1]),
    ([{'date': DATES[0], 'close': 1}], [DATES[0], DATES[0]]),
])
def test_unsorted_duplicate_nonfinite_rejected(rows, calendar):
    with pytest.raises(ValueError):
        transform_series(rows, field='close', transform='difference', window=2, calendar=calendar, unit='IDR')


@pytest.mark.parametrize('transform', ['difference', 'pct_change', 'rolling_mean', 'rolling_std', 'robust_z'])
def test_prefix_invariance(transform):
    assert run([1, 2, 3], transform)['series'] == run([1, 2, 3, 100], transform)['series'][:3]


def test_std_window_one_rejected_and_empty_history_honest():
    with pytest.raises(ValueError):
        run([1, 2], 'rolling_std', 1)
    result = transform_series([], field='close', transform='rolling_mean', window=2, calendar=[], unit='IDR')
    assert result['series'] == []
    assert result['status'] == 'INSUFFICIENT_DATA'


def test_units_and_zero_std_and_outlier():
    assert run([2, 2], 'rolling_std')['series'][-1]['value'] == 0
    assert run([1, 2, 100], 'robust_z', 3)['series'][-1]['value'] == pytest.approx(66.10009442870633, abs=1e-10, rel=1e-8)
    assert run([1, 2], 'pct_change')['unit'] == 'fraction'
    assert run([1, 2], 'difference')['unit'] == 'IDR'
