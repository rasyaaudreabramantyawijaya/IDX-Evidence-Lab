import pytest
from idx_evidence_lab.studies_indicators import technical_series


def rows(values):
    return [{'date':f'2026-01-{i+1:02}', 'close':v, 'high':v+1, 'low':v-1} for i,v in enumerate(values)]


def test_sma_ema_rsi_and_atr_independent_reference():
    out=technical_series(rows([10,11,12,13,14]), period=3)
    assert out['sma'] == [None,None,11,12,13]
    assert out['ema'] == [None,None,11,12,13]
    assert out['rsi'][-1] == 100
    assert out['atr'][-1] == 2


def test_flat_prices_and_gap_reset_warmup():
    out=technical_series(rows([10]*5), period=3)
    assert out['rsi'][-1] == 50
    data=rows([10,11,12,13,14]);data[2]['close']=None
    out=technical_series(data,period=3)
    assert out['sma'][-1] is None and out['ema'][-1] is None


def test_prefix_invariance_and_short_history():
    a=technical_series(rows([10,11,12]),period=3)
    b=technical_series(rows([10,11,12,13]),period=3)
    assert all(a[k] == b[k][:3] for k in a)
    assert a['rsi'] == [None]*3


def test_nonlinear_ema_wilder_reversal_and_variable_true_range_reference():
    actual=technical_series(rows([10,12,11,15,13,16]),period=3)
    expected={
        'sma':[None,None,11,12.666666666666666,13,14.666666666666666],
        'ema':[None,None,11,13,13,14.5],
        'rsi':[None,None,None,85.71428571428571,60,76.11940298507463],
        'atr':[None,None,2.3333333333333335,3.2222222222222223,3.1481481481481484,3.432098765432099]}
    for name,values in expected.items():
        for got,want in zip(actual[name],values):
            if want is None: assert got is None
            else: assert got==pytest.approx(want,abs=1e-10,rel=1e-8)
