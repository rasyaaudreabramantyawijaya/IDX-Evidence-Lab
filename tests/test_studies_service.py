from pathlib import Path
from unittest.mock import patch
import pytest
from idx_evidence_lab.studies_registry import parse_study_request
from idx_evidence_lab.studies_service import run_study


def request(widget='custom_engineering', targets=None, **kwargs):
    return parse_study_request({'widget_id': widget, 'targets': targets or ['BBCA'], **kwargs},
                              known_tickers=['BBCA', 'BBRI'], sectors={})


def snapshot(root):
    file = root / 'daily.json'
    file.write_text('[1,2,3]')
    return {'ok': True, 'data_quality': 'VERIFIED', 'source_files': ['daily.json'],
            'series': [{'date': day, 'close': value, 'volume': 100}
                       for day, value in zip(['2026-01-02', '2026-01-05', '2026-01-06'], [1,2,3])], 'issues': []}


def test_custom_result_uses_verified_source_and_cutoff(tmp_path):
    data = snapshot(tmp_path)
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', return_value=data):
        result = run_study(tmp_path, request(window='5', cutoff='2026-01-05', params={'transform': 'difference'}))
    assert [r['value'] for r in result['series'][0]['points']] == [None, 1]
    assert result['period']['end'] == '2026-01-05'
    assert result['sources'][0]['sha256'] and result['request_fingerprint']
    assert result['verification'] == 'NOT_TESTED'


def test_corrupt_hash_never_ready(tmp_path):
    data = snapshot(tmp_path)
    data['data_quality'] = 'PARTIAL'
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', return_value=data):
        result = run_study(tmp_path, request())
    assert result['status'] == 'INSUFFICIENT_DATA'
    assert result['series'] == []


def test_partial_sector_preserves_denominator(tmp_path):
    data = snapshot(tmp_path)
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', side_effect=[data, {'ok': False}]):
        result = run_study(tmp_path, request(targets=['BBCA','BBRI'], params={'transform': 'difference'}))
    assert result['coverage']['requested_issuers'] == 2
    assert result['coverage']['usable_issuers'] == 1
    assert result['status'] == 'PARTIAL'
    assert {'ticker': 'BBRI', 'reason': 'VERIFIED_DAILY_REQUIRED'} in result['warnings']


@pytest.mark.parametrize('widget', ['portfolio_risk', 'capm_benchmark'])
def test_portfolio_missing_artifact_no_default_weights(tmp_path, widget):
    result = run_study(tmp_path, request(widget))
    assert result['status'] == 'INSUFFICIENT_DATA'
    assert result['metrics'] == []
    assert result['warnings'][0]['reason'] == 'MATCHING_PORTFOLIO_ARTIFACT_REQUIRED'


def test_price_returns_and_drawdown_reference(tmp_path):
    data = snapshot(tmp_path)
    data['series'][2]['close'] = 1
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', return_value=data):
        result = run_study(tmp_path, request('price_risk', window='available'))
    metrics = {r['id']: r['value'] for r in result['metrics']}
    assert metrics['BBCA.cumulative_return'] == 0
    assert metrics['BBCA.max_drawdown'] == -.5
    assert metrics['BBCA.volatility_annualized'] == pytest.approx(16.837458240482736)
    assert metrics['BBCA.downside_deviation_annualized']==pytest.approx(5.612486080160912,abs=1e-10,rel=1e-8)


def test_custom_warmup_only_is_insufficient(tmp_path):
    data = snapshot(tmp_path)
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', return_value=data):
        result = run_study(tmp_path, request(window='20', params={'transform': 'rolling_std'}))
    assert result['status'] == 'INSUFFICIENT_DATA'


def test_trend_warmup_only_is_insufficient(tmp_path):
    data=snapshot(tmp_path);data['series']=data['series'][:1]
    with patch('idx_evidence_lab.studies_service.load_issuer_daily',return_value=data):
        result=run_study(tmp_path,request('trend_momentum'))
    assert result['status']=='INSUFFICIENT_DATA'
    assert result['coverage']['usable_issuers']==0


@pytest.mark.parametrize('transform',['rolling_mean','rolling_std','robust_z'])
def test_available_service_prefix_invariance(tmp_path,transform):
    data=snapshot(tmp_path)
    with patch('idx_evidence_lab.studies_service.load_issuer_daily',return_value=data):
        first=run_study(tmp_path,request(window='available',params={'transform':transform}))
        data['series'].append({'date':'2026-01-07','close':4,'volume':100})
        second=run_study(tmp_path,request(window='available',params={'transform':transform}))
    assert first['series'][0]['points']==second['series'][0]['points'][:3]


@pytest.mark.parametrize('widget',['liquidity_proxy','custom_engineering'])
def test_missing_raw_volume_is_not_loader_default_zero(tmp_path,widget):
    import json
    data=snapshot(tmp_path)
    raw=[{'date':r['date'],'close':r['close']} for r in data['series']]
    (tmp_path/'daily.json').write_text(json.dumps(raw))
    for row in data['series']: row['volume']=0
    params={'field':'volume','transform':'difference'} if widget=='custom_engineering' else {}
    with patch('idx_evidence_lab.studies_service.load_issuer_daily',return_value=data):
        result=run_study(tmp_path,request(widget,params=params))
    assert not any(p['value'] is not None for s in result['series'] for p in s['points'])
    assert any(w['reason']=='MISSING_RAW_VOLUME_NOT_ZERO_FILLED' for w in result['warnings'])


def test_verified_calendar_source_changes_fingerprint(tmp_path):
    data = snapshot(tmp_path)
    benchmark_file = tmp_path / 'ihsg.json'
    benchmark_file.write_text('calendar-v1')
    benchmark = {'data_quality': 'VERIFIED', 'source_files': ['ihsg.json'],
                 'series': [{'date':r['date']} for r in data['series']]}
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', return_value=data), \
         patch('idx_evidence_lab.studies_service.load_ihsg_snapshot', return_value=benchmark):
        a = run_study(tmp_path, request(params={'transform': 'difference'}))
        benchmark_file.write_text('calendar-v2')
        b = run_study(tmp_path, request(params={'transform': 'difference'}))
    assert a['request_fingerprint'] != b['request_fingerprint']
    assert any(source['id'] == 'ihsg.json' for source in a['sources'])


def test_issuer_sessions_missing_from_benchmark_not_dropped(tmp_path):
    data = snapshot(tmp_path)
    benchmark = {'data_quality': 'VERIFIED', 'source_files': [],
                 'series': [{'date': data['series'][0]['date']}, {'date': data['series'][-1]['date']}]}
    with patch('idx_evidence_lab.studies_service.load_issuer_daily', return_value=data), \
         patch('idx_evidence_lab.studies_service.load_ihsg_snapshot', return_value=benchmark):
        result = run_study(tmp_path, request(params={'transform': 'difference'}))
    assert len(result['series'][0]['points']) == 3
    assert result['series'][0]['points'][1]['value'] == 1
    assert any(w['reason'] == 'ISSUER_SESSIONS_ABSENT_FROM_IHSG' for w in result['warnings'])
