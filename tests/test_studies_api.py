from test_portfolio_api import server_at, request_json


def test_studies_catalog_and_local_bbca_calculation():
    with server_at() as base:
        status, data = request_json(base, '/api/studies-catalog')
        assert status == 200 and len(data['widgets']) == 16
        status, data = request_json(base, '/api/studies-run', {
            'widget_id': 'custom_engineering', 'targets': ['BBCA'], 'window': '20',
            'params': {'field': 'close', 'transform': 'rolling_mean'}})
    assert status == 200
    assert data['status'] in ('READY', 'PARTIAL')
    assert data['series'][0]['points'][-1]['value'] > 0
    assert data['sources'] and data['request_fingerprint']


def test_studies_rejects_unknown_and_oversize():
    with server_at() as base:
        assert request_json(base, '/api/studies-run', {'widget_id':'code'})[0] == 400
        assert request_json(base, '/api/studies-run', body=b'x'*16385)[0] == 413


def test_studies_reuses_real_server_owned_portfolio_without_reoptimizing():
    from unittest.mock import patch
    from idx_evidence_lab import web_app
    with server_at() as base:
        status,portfolio=request_json(base,'/api/portfolio-analysis',{
            'tickers':['BBCA'],'benchmark':'IHSG','profile':'moderate','method':'markowitz','lookback':126,
            'risk_free_annual':.07129,'scenarios':{'horizons':[20],'simulations':12,'seed':7}})
        assert status==200
        with patch.object(web_app,'build_portfolio_analysis',side_effect=AssertionError('Studies must not optimize')):
            for widget in ('portfolio_risk','capm_benchmark'):
                status,result=request_json(base,'/api/studies-run',{
                    'widget_id':widget,'targets':['BBCA'],'window':'available',
                    'portfolio_artifact_ref':portfolio['studies_artifact_ref']})
                assert status==200 and result['status'] in ('READY','PARTIAL')
                assert result['metrics'][0]['value'] is not None
                assert result['tables'][0]['weights']==portfolio['allocation']['weights']
                assert result['period']['end']==portfolio['selection']['sample_end']
                if widget=='capm_benchmark':
                    assert result['tables'][0]['assumptions']['source']=='ALIGNED_HISTORICAL_BENCHMARK'
