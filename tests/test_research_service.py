import importlib.util
import pytest
from idx_evidence_lab.search import LocalSearchIndex
from idx_evidence_lab.research_sessions import ResearchSessionStore
from idx_evidence_lab.openrouter_live import OpenRouterError
from idx_evidence_lab.schemas import SearchDocument, SourceClass


def service(tmp_path, adapter=None, clock=None):
    assert importlib.util.find_spec('idx_evidence_lab.research_service'), 'Missing research service'
    from idx_evidence_lab.research_service import ResearchService
    index = LocalSearchIndex([SearchDocument('news/a', 'BBCA', 'BBCA laba melemah', SourceClass.SECTORS_SOURCE_DATA,
                                           'data/raw/sectors/news/a', ticker='BBCA', metadata={'kind': 'news_record'})])
    return ResearchService(tmp_path, index, ResearchSessionStore(), adapter or (lambda: pytest.fail('Unapproved inference')), known_tickers=['BBCA'], **({'clock': clock} if clock else {}))


def test_no_network_when_use_model_false(tmp_path):
    svc = service(tmp_path); session = svc.store.create()
    reply = svc.answer(session.id, 0, 'berita BBCA', False, [])
    assert reply['reply']['status'] == 'LOCAL_EVIDENCE'
    assert reply['reply']['context']['entities'] == ['BBCA']


def test_repeated_turn_id_does_not_duplicate_messages(tmp_path):
    svc = service(tmp_path); session = svc.store.create()
    first = svc.answer(session.id, 0, 'berita BBCA', False, [], request_id='retry-1')
    assert svc.answer(session.id, 0, 'berita BBCA', False, [], request_id='retry-1') == first
    assert len(svc.store.get(session.id).messages) == 2
    with pytest.raises(ValueError):
        svc.answer(session.id, 0, 'berita lain', False, [], request_id='retry-1')


def test_retry_after_prevents_automatic_retries(tmp_path):
    class Limited:
        calls = 0
        def compose_chat(self, *args):
            self.calls += 1
            raise OpenRouterError('Rate limited', status_code=429, retry_after=50)
    adapter = Limited(); svc = service(tmp_path, lambda: adapter, clock=lambda: 100)
    session = svc.store.create()
    first = svc.answer(session.id, 0, 'berita BBCA', True, [])
    second = svc.answer(session.id, 1, 'berita BBCA', True, [])
    assert first['reply']['evidence'] and adapter.calls == 1
    assert second['reply']['model_status']['status'] == 'COOLDOWN'


def test_query_and_refs_validation_before_state_mutation(tmp_path):
    svc = service(tmp_path); s = svc.store.create()
    for query, refs in [('x' * 4001, []), ('BBCA', ['../../secret'])]:
        with pytest.raises(ValueError):
            svc.answer(s.id, 0, query, False, refs)
    assert svc.store.get(s.id).revision == 0


def test_tickerless_question_does_not_use_wifi(tmp_path):
    svc = service(tmp_path); s = svc.store.create()
    result = svc.answer(s.id, 0, 'Apa itu risiko portofolio?', False, [])
    assert result['reply']['context']['entities'] == []


def test_no_model_call_without_public_evidence(tmp_path):
    svc = service(tmp_path); s = svc.store.create()
    result = svc.answer(s.id, 0, 'akuisisi BBCA', True, [])
    assert result['reply']['model_status']['status'] == 'NO_PUBLIC_EVIDENCE'


def test_unexpected_model_failure_keeps_local_reply_and_allows_next_turn(tmp_path):
    class Broken:
        def compose_chat(self, *args):
            raise RuntimeError('secret must not be returned')
    svc = service(tmp_path, lambda: Broken()); s = svc.store.create()
    result = svc.answer(s.id, 0, 'berita BBCA', True, [])
    assert result['reply']['evidence']
    assert result['reply']['model_status']['status'] == 'UNAVAILABLE'
    assert 'secret' not in str(result)
    assert svc.answer(s.id, 1, 'berita BBCA', False, [])['revision'] == 2


def test_selected_target_applies_to_tickerless_query(tmp_path):
    svc = service(tmp_path); s = svc.store.create()
    result = svc.answer(s.id, 0, 'Apa risikonya?', False, [], target={'kind': 'issuer', 'value': 'BBCA'})
    assert result['reply']['context']['entities'] == ['BBCA']
    assert result['reply']['status'] != 'CLARIFICATION_REQUIRED'
    with pytest.raises(ValueError, match='TARGET_QUERY_CONFLICT'):
        svc.known_tickers = ['BBCA', 'TLKM']
        svc.answer(s.id, 1, 'risiko TLKM', False, [], target={'kind': 'issuer', 'value': 'BBCA'})
    assert svc.store.get(s.id).revision == 1


def test_sector_target_members_are_resolved_server_side(tmp_path):
    import json
    folder = tmp_path / 'docs/prototypes'; folder.mkdir(parents=True)
    (folder / 'market-overview-data.json').write_text(json.dumps({'sectorHeatmap': {'sectors': [
        {'sector': 'Banking', 'member_tickers': ['BBCA', 'TLKM']}]}}))
    svc = service(tmp_path); svc.known_tickers = ['BBCA', 'TLKM']; s = svc.store.create()
    result = svc.answer(s.id, 0, 'Analisis risiko', False, [], target={'kind': 'sector', 'value': 'Banking'})
    assert result['reply']['context']['entities'] == ['BBCA', 'TLKM']
    assert result['reply']['context']['scope'] == 'sector'
    with pytest.raises(ValueError):
        svc.answer(s.id, 1, 'Analisis risiko', False, [], target={'kind': 'sector', 'value': 'Fake', 'members': ['WIFI']})


def test_attachment_is_local_private_until_explicit_sharing(tmp_path):
    from idx_evidence_lab.research_attachments import read_attachment
    from idx_evidence_lab.research_context import public_model_context
    from idx_evidence_lab.research_types import EvidencePack, EvidenceItem
    import base64
    svc = service(tmp_path); s = svc.store.create()
    item = read_attachment({'name': 'notes.txt', 'mime': 'text/plain', 'data': base64.b64encode(b'User local evidence').decode()})
    svc.store.add_attachment(s.id, item)
    result = svc.answer(s.id, 0, 'Jelaskan catatan', False, [], attachment_ids=[item['id']])
    evidence = [EvidenceItem(**i) for i in result['reply']['evidence']]
    assert evidence[0].access_class == 'private'
    assert not public_model_context(EvidencePack(items=evidence))['items']
    with pytest.raises(ValueError, match='UNKNOWN_ATTACHMENT'):
        svc.answer(s.id, 1, 'Catatan', False, [], attachment_ids=['U:foreign'])


def test_full_sector_over_ten_members_is_not_silently_cut(tmp_path):
    import json
    tickers = ['EN' + chr(65 + i) for i in range(12)]
    folder = tmp_path / 'docs/prototypes'; folder.mkdir(parents=True)
    (folder / 'market-overview-data.json').write_text(json.dumps({'sectorHeatmap': {'sectors': [
        {'sector': 'Energy', 'member_tickers': tickers}]}}))
    svc = service(tmp_path); svc.known_tickers = tickers; s = svc.store.create()
    result = svc.answer(s.id, 0, 'Analisis risiko', False, [], target={'kind': 'sector', 'value': 'Energy'})
    assert result['reply']['context']['entities'] == tickers
    assert result['reply']['context']['scope'] == 'sector'
