import importlib.util
import json
import hashlib
from idx_evidence_lab.task_navigation import resolve_research_plan
from idx_evidence_lab.research_types import EvidenceItem, MetricRecord


def module():
    assert importlib.util.find_spec('idx_evidence_lab.research_context'), 'Missing context registry'
    from idx_evidence_lab import research_context
    return research_context


def fixture(root):
    folder = root / 'docs/prototypes/issuer-dossiers'; folder.mkdir(parents=True)
    raw = root / 'data/raw/sectors/BBCA.json'; raw.parent.mkdir(parents=True); raw.write_text('{}')
    source = {'file': 'data/raw/sectors/BBCA.json', 'sha256': hashlib.sha256(b'{}').hexdigest()}
    payload = {'ticker': 'BBCA', 'version': 'issuer-dossier-v1', 'source_fingerprint': 'abc', 'as_of': '2026-09-24',
               'analysis': {'data_quality': 'VERIFIED'}, 'documents': {'sources': [source]},
               'summary': {'volatility': 0.25, 'max_drawdown': None, 'price_start': '2025-01-01', 'price_end': '2026-09-24'}}
    (folder / 'BBCA.json').write_text(json.dumps(payload))
    (root / 'docs/prototypes/market-overview-data.json').write_text(json.dumps({'screener_analysis': {'source_fingerprint': 'abc'}}))
    return raw


def test_risk_query_loads_only_matching_issuer_metrics(tmp_path):
    fixture(tmp_path)
    rows = module().load_research_metrics(tmp_path, resolve_research_plan('risiko BBCA', None, ['BBCA']), [])
    assert [(m.name, m.value, m.unit) for m in rows] == [('volatility', 0.25, 'fraction/year')]
    assert rows[0].entities == ['BBCA']


def test_mismatched_artifact_fingerprint_is_unavailable(tmp_path):
    fixture(tmp_path).write_text('{"changed": true}')
    assert module().load_research_metrics(tmp_path, resolve_research_plan('risiko BBCA', None, ['BBCA']), []) == []


def test_client_numbers_do_not_override_server_artifact(tmp_path):
    fixture(tmp_path)
    import pytest
    with pytest.raises(ValueError):
        module().load_research_metrics(tmp_path, resolve_research_plan('risiko BBCA', None, ['BBCA']), ['../../secret'])


def test_private_pdf_excluded_from_model_context():
    pack = module().build_evidence_pack([EvidenceItem('L1', 'private.pdf', 'private_legal_reference', 'Law', 'SECRET PDF', access_class='private')], [])
    assert 'SECRET PDF' not in json.dumps(module().public_model_context(pack))
    assert module().public_model_context(pack)['private_evidence_omitted']


def test_large_pack_truncation_is_visible():
    items = [EvidenceItem(str(i), str(i), 'sectors_source_data', 'Title', 'x' * 5000) for i in range(30)]
    pack = module().build_evidence_pack(items, [])
    assert pack.truncated and len(pack.items) == 16
    assert all(len(i.excerpt) <= 1200 for i in pack.items)
    assert len(json.dumps(module().public_model_context(pack)).encode()) < 48 * 1024


def test_comparison_period_mismatch_is_reported():
    metrics = [MetricRecord('a', 'volatility', 0.2, 'fraction/year', ['BBCA'], {'end': '2026-09-24'}),
               MetricRecord('b', 'volatility', 0.3, 'fraction/year', ['BMRI'], {'end': '2026-09-20'})]
    assert 'periode_tidak_selaras' in module().build_evidence_pack([], metrics).missing_inputs


def test_market_metrics_require_raw_provenance_and_matching_published_series(tmp_path):
    folder = tmp_path / 'docs/prototypes'; folder.mkdir(parents=True)
    raw = tmp_path / 'data/raw/sectors/index_daily/ihsg/a.json'; raw.parent.mkdir(parents=True)
    series = [{'date': '2026-09-24', 'price': 123, 'index_code': 'IHSG'}]
    raw.write_text(json.dumps(series))
    raw.with_suffix('.metadata.json').write_text(json.dumps({'provider': 'Sectors.app', 'http_status': 200,
        'endpoint': 'https://api.sectors.app/v2/index-daily/ihsg/', 'snapshot_sha256': hashlib.sha256(raw.read_bytes()).hexdigest()}))
    (folder / 'market-overview-data.json').write_text(json.dumps({'ihsg': {'data_quality': 'VERIFIED',
        'source_files': [raw.relative_to(tmp_path).as_posix()], 'series': series, 'latest_price': 123,
        'coverage_end': '2026-09-24'}}))
    plan = resolve_research_plan('harga IHSG pasar', None, [])
    metrics = module().load_research_metrics(tmp_path, plan, ['market:current'])
    assert [(m.value, m.unit) for m in metrics] == [(123, 'index_points')]
    raw.write_text('[]')
    assert module().load_research_metrics(tmp_path, plan, ['market:current']) == []
