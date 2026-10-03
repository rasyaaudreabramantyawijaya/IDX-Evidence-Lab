"""Offline acceptance; fixtures are not market observations or model-quality evidence."""
import pytest
from idx_evidence_lab.research_types import EvidencePack, MetricRecord, ResearchContext
from idx_evidence_lab.research_validation import validate_research_reply
from test_research_service import service


def test_followup_switch_and_two_session_isolation(tmp_path):
    svc = service(tmp_path); svc.known_tickers = ['BBCA', 'TLKM']
    first, second = svc.store.create(), svc.store.create()
    assert svc.answer(first.id, 0, 'berita BBCA', False, [])['reply']['context']['entities'] == ['BBCA']
    assert svc.answer(first.id, 1, 'Apa risikonya?', False, [])['reply']['context']['entities'] == ['BBCA']
    assert svc.answer(first.id, 2, 'berita TLKM', False, [])['reply']['context']['entities'] == ['TLKM']
    assert svc.store.get(second.id).context.entities == []


def test_no_acquisition_evidence_is_not_negative_event_certainty(tmp_path):
    svc = service(tmp_path); session = svc.store.create()
    reply = svc.answer(session.id, 0, 'akuisisi BBCA', False, [])['reply']
    assert reply['status'] == 'INSUFFICIENT_EVIDENCE'
    assert 'tidak membuktikan' in reply['blocks'][0]['text']


def test_provisional_forecast_requires_explicit_registered_method_fixture():
    metadata = {k: 'MOCK method metadata' for k in
                ['target', 'horizon', 'input_cutoff', 'method_version', 'baseline', 'diagnostics', 'validation_status']}
    pack = EvidencePack(metrics=[MetricRecord('M1', 'fixture forecast', 0.1, 'fraction',
        validation_status='PROVISIONAL', claim_kind='forecast', forecast_metadata=metadata)])
    reply = validate_research_reply({'blocks': [{'text': 'Skenario metode fixture: 10%.', 'claim_kind': 'forecast',
        'metric_ids': ['M1'], 'numeric_claims': [{'metric_id': 'M1', 'value': 0.1, 'unit': 'fraction', 'display': '10%'}]}]}, pack, ResearchContext())
    assert reply.metrics[0].validation_status == 'PROVISIONAL'
    assert reply.model_status['semantic_validation'] == 'NOT_GUARANTEED'


def test_cancelled_model_reply_cannot_update_connection_status(tmp_path):
    from idx_evidence_lab.research_validation import compose_local_reply
    from idx_evidence_lab.task_navigation import resolve_research_plan
    class Late:
        def compose_chat(self, query, context, pack, history):
            svc.cancel(session.id, 1)
            reply = compose_local_reply(resolve_research_plan(query, context, ['BBCA']), pack)
            reply.model_status = {'provider': 'OpenRouter', 'status': 'GENERATED'}
            return reply
    svc = service(tmp_path, lambda: Late()); session = svc.store.create()
    with pytest.raises(ValueError, match='STALE_RESPONSE'):
        svc.answer(session.id, 0, 'berita BBCA', True, [])
    assert svc.last_model_status['status'] == 'NOT_TESTED'
    assert len(svc.store.get(session.id).messages) == 1
