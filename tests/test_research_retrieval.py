import importlib.util
from idx_evidence_lab.schemas import SearchDocument, SourceClass
from idx_evidence_lab.search import LocalSearchIndex
from idx_evidence_lab.task_navigation import resolve_research_plan


def retrieve(tmp_path, query, docs):
    assert importlib.util.find_spec('idx_evidence_lab.research_retrieval'), 'Missing evidence retrieval'
    from idx_evidence_lab.research_retrieval import retrieve_research_evidence
    return retrieve_research_evidence(tmp_path, LocalSearchIndex(docs), resolve_research_plan(query, None, ['BBCA', 'TLKM']))


def doc(id, text, ticker='BBCA', kind='json'):
    return SearchDocument(id, id, text, SourceClass.SECTORS_SOURCE_DATA, id, ticker=ticker, metadata={'kind': kind})


def test_navigation_never_counts_as_evidence(tmp_path):
    docs = [doc('app/issuer/BBCA', 'BBCA laba', kind='navigation'), doc('data/raw/sectors/company_report/BBCA.json', 'BBCA laba tumbuh')]
    assert [e.source_id for e in retrieve(tmp_path, 'laba BBCA', docs)] == ['data/raw/sectors/company_report/BBCA.json']


def test_ticker_alone_does_not_prove_acquisition(tmp_path):
    assert retrieve(tmp_path, 'akuisisi BBCA', [doc('data/raw/sectors/daily/BBCA.json', 'BBCA harga naik')]) == []


def test_roundup_excerpt_is_ticker_specific(tmp_path):
    result = retrieve(tmp_path, 'berita BBCA', [doc('data/raw/sectors/news/a#BBCA', 'BBCA membagikan dividen. TLKM mengakuisisi perusahaan.', kind='news_record')])
    assert len(result) == 1
    assert 'TLKM' not in result[0].excerpt
    assert result[0].source_date is None


def test_roundup_other_entity_event_is_not_support(tmp_path):
    assert retrieve(tmp_path, 'akuisisi BBCA', [doc('data/raw/sectors/news/a#BBCA', 'BBCA membagikan dividen. TLKM mengakuisisi perusahaan.', kind='news_record')]) == []


def test_duplicate_content_has_one_supporting_record(tmp_path):
    result = retrieve(tmp_path, 'berita BBCA', [doc('data/raw/sectors/news/a', 'BBCA dividen', kind='news_record'), doc('data/raw/sectors/news/b', 'BBCA dividen', kind='news_record')])
    assert len(result) == 1


def test_no_match_does_not_substitute_other_issuer(tmp_path):
    assert retrieve(tmp_path, 'berita BBCA', [doc('data/raw/sectors/news/b', 'TLKM berita BBCA sekilas', 'TLKM', 'news_record')]) == []


def test_event_date_in_body_is_not_publication_date(tmp_path):
    result = retrieve(tmp_path, 'berita BBCA', [doc('data/raw/sectors/news/a', 'BBCA akan bertemu 2026-12-01.', kind='news_record')])
    assert result[0].source_date is None


def test_nonlegal_query_skips_pdf_extraction(tmp_path, monkeypatch):
    from idx_evidence_lab import web_app
    def forbidden(*args, **kwargs):
        raise AssertionError('Private PDF read for unrelated question')
    monkeypatch.setattr(web_app, 'search_legal_corpus', forbidden)
    assert retrieve(tmp_path, 'harga BBCA', []) == []


def test_legal_tokenization_matches_words_not_separators(tmp_path):
    import pytest
    fitz = pytest.importorskip('fitz')
    from idx_evidence_lab.web_app import search_legal_corpus
    folder = tmp_path / 'Business & Corporate Law'
    folder.mkdir()
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((40, 40), 'Aturan akuisisi perusahaan dan persetujuan pemegang saham.')
    pdf.save(folder / 'local.pdf')
    pdf.close()
    result = search_legal_corpus(tmp_path, 'akuisisi')
    assert result and 'akuisisi' in result[0]['excerpt']
