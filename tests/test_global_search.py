"""Global search must resolve issuers and product pages without model availability."""
from idx_evidence_lab.web_app import build_local_index
import io
import json
import ssl
from unittest.mock import patch
from idx_evidence_lab.openrouter_live import OpenRouterSearchAdapter


def test_model_transport_explicitly_verifies_https_certificates():
    response = io.BytesIO(json.dumps({'choices': [{'message': {'content': '{"search_query":"BBCA","entities":[]}'}}]}).encode())
    with patch('idx_evidence_lab.openrouter_live.urlopen', return_value=response) as transport:
        OpenRouterSearchAdapter('test-key').interpret('BBCA', ['BBCA'])
    context = transport.call_args.kwargs.get('context')
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


def test_exact_ticker_opens_issuer_before_document_hits():
    matches = build_local_index().search('BBCA', limit=8)
    assert matches
    issuer = matches[0][0]
    assert issuer.ticker == 'BBCA'
    assert issuer.metadata.get('page') == 'issuer'
    assert 'Central Asia' in issuer.title


def test_feature_query_finds_navigable_product_page():
    matches = build_local_index().search('portfolio optimasi', limit=8)
    assert any(item.metadata.get('page') == 'portfolio-lab' for item, _ in matches)


def test_snapshot_larger_than_excerpt_remains_parseable(tmp_path):
    folder = tmp_path / 'data/raw/sectors/daily/BBCA'
    folder.mkdir(parents=True)
    rows = [{'symbol': 'BBCA.JK', 'date': f'2026-01-{day:02}', 'close': 9000, 'note': 'x' * 600} for day in range(1,20)]
    (folder / 'BBCA.json').write_text(json.dumps(rows))
    document = build_local_index(tmp_path).search('BBCA')[0][0]
    assert '19 observasi' in document.text
