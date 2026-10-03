from pathlib import Path
from unittest.mock import patch
import pytest
from idx_evidence_lab.studies_registry import parse_study_request, WIDGETS
from idx_evidence_lab.studies_service import run_study

ROOT = Path(__file__).resolve().parents[1]


def req(widget, targets=None, **kwargs):
    return parse_study_request({'widget_id':widget, 'targets':targets or ['BBCA'], **kwargs},
        known_tickers=['BBCA','BBRI','AADI'], sectors={'Financials':['BBCA','BBRI']})


@pytest.mark.parametrize('widget', WIDGETS)
def test_every_catalog_widget_has_real_executor(widget):
    result = run_study(ROOT, req(widget))
    assert result['status'] in ('READY','PARTIAL','INSUFFICIENT_DATA')
    assert not any('PENDING' in w['reason'] or 'NOT_YET' in w['reason'] for w in result['warnings'])
    if widget not in ('capm_benchmark','portfolio_risk'):
        assert result['sources']
        assert result['metrics'] or result['tables'] or result['series']


def test_report_after_cutoff_is_not_historical_input():
    result = run_study(ROOT, req('quality_valuation', cutoff='2025-01-01'))
    assert result['status'] == 'INSUFFICIENT_DATA'
    assert result['metrics'] == []
    assert any(w['reason'] == 'SNAPSHOT_AFTER_CUTOFF' for w in result['warnings'])


def test_bank_ratio_not_compared_to_nonbank():
    result = run_study(ROOT, req('issuer_compare', targets=['BBCA','AADI']))
    assert any(w['reason'] == 'NONCOMPARABLE_PEER_GROUPS' for w in result['warnings'])
    assert not any(m['id'].endswith('.roe_delta') for m in result['metrics'])


def test_foreign_flow_custom_transform_runs_locally():
    result = run_study(ROOT, req('custom_engineering', params={'field':'foreign_net_flow','transform':'difference'}))
    assert result['series'] and result['series'][0]['unit'] == 'IDR'
    assert result['series'][0]['points'][-1]['value'] is not None


def test_event_counts_retain_immature_distinction():
    from idx_evidence_lab.studies_adapters import summarize_events
    data={'event_count':10, 'sample_5d':10,'sample_20d':9,'excluded':{'immature_20d':1},'events':[]}
    result=summarize_events(data)
    assert result['detected'] == 10 and result['mature_20d'] == 9
    assert result['immature_20d'] == 1


def test_portfolio_artifact_mismatch_no_default_weights():
    result=run_study(ROOT, req('portfolio_risk'), portfolio_artifact={'selection':{'tickers':['AADI']}})
    assert result['status'] == 'STALE'
    assert result['metrics'] == []


def test_event_excursions_explicitly_unavailable_without_validated_path_formula():
    result=run_study(ROOT, req('event_outcomes'))
    metrics={m['id']:m for m in result['metrics']}
    for name in ('mae','mfe'):
        assert metrics['BBCA.'+name]['value'] is None
        assert metrics['BBCA.'+name]['reason'] == 'EXCURSION_FORMULA_NOT_REFERENCE_VERIFIED'


def test_timeline_never_exceeds_effective_cutoff_and_window():
    result=run_study(ROOT, req('event_timeline',window='5'))
    assert all(not row.get('date') or result['period']['start']<=row['date']<=result['cutoff']
               for row in result['tables'])


def test_event_outcomes_window_limits_event_dates_not_indicator_warmup():
    short=run_study(ROOT,req('event_outcomes',window='5'))
    full=run_study(ROOT,req('event_outcomes',window='available'))
    assert short['period']['start']>full['period']['start']
    events=[r for r in short['tables'] if 'event_date' in r]
    assert all(short['period']['start']<=e['event_date']<=short['cutoff'] for e in events)
    assert short['tables'][0]['detected']==len(events)
    assert short['tables'][0]['detected']<=full['tables'][0]['detected']


def test_portfolio_reused_assumptions_and_window_are_not_silently_changed(tmp_path):
    from idx_evidence_lab.studies_adapters import source
    (tmp_path/'daily.json').write_text('[]')
    artifact={'selection':{'tickers':['BBCA'],'sample_start':'2026-01-01','sample_end':'2026-01-06'},
              'studies_sources':[source(tmp_path,'daily.json')],
              'allocation':{'weights':{'BBCA':1}}, 'metrics_scope':'assumption scenario',
              'metrics':{'sample_count':3,'sharpe':{'value':1.25,'status':'ASSUMPTION_BASED','reason':'MANUAL_RF'},
                         'assumptions':{'risk_free_annual':.05}}}
    result=run_study(tmp_path,req('portfolio_risk',window='available'),portfolio_artifact=artifact)
    assert result['metrics'][0]['status']=='ASSUMPTION_BASED'
    assert result['metrics'][0]['reason']=='MANUAL_RF'
    assert result['tables'][0]['weights']=={'BBCA':1}
    assert result['tables'][0]['assumptions']['risk_free_annual']==.05
    result=run_study(tmp_path,req('portfolio_risk',window='5'),portfolio_artifact=artifact)
    assert result['status']=='STALE' and result['metrics']==[]


def test_comparability_checks_each_ratio_year_and_keeps_comparable_fields(tmp_path):
    import json
    records=[{'ticker':t,'peer_group':'bank','report_as_of':'2026-09-24',
              'financial_ratio_years':{'roe':2025,'debt_to_equity':year},
              'components':{'roe':{'value':.2},'debt_to_equity':{'value':.4}}}
             for t,year in [('BBCA',2025),('BBRI',2024)]]
    (tmp_path/'daily.json').write_text('[]')
    path=tmp_path/'docs/prototypes/portfolio-factor-zoo-data.json';path.parent.mkdir(parents=True)
    path.write_text(json.dumps({'records':records,'sources':{'files':['daily.json'],'sha256':'x'},
                    'artifact_fingerprint':'x','formula_version':'test-v1','as_of':{'price':'2026-09-24'}}))
    with patch('idx_evidence_lab.studies_adapters._artifact_fingerprint',return_value='x'), \
         patch('idx_evidence_lab.studies_adapters._source_fingerprint',return_value='x'):
        result=run_study(tmp_path,req('issuer_compare',targets=['BBCA','BBRI']))
    metrics={m['id']:m for m in result['metrics']}
    assert metrics['BBCA.roe']['value']==.2
    assert metrics['BBCA.debt_to_equity']['value'] is None
    assert metrics['BBCA.debt_to_equity']['reason']=='NONCOMPARABLE_FISCAL_YEAR'
