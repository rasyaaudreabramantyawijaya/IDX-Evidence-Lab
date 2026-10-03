import re
from pathlib import Path

import pytest

from idx_evidence_lab.studies_registry import catalog, parse_study_request
from idx_evidence_lab.studies_types import request_fingerprint


def parse(payload):
    return parse_study_request(payload, known_tickers=['BBCA', 'BBRI', 'AADI'],
                               sectors={'Financials': ['BBCA', 'BBRI']})


def test_catalog_matches_all_16_ui_ids():
    html = (Path(__file__).resolve().parents[1] / 'docs/prototypes/idx-evidence-lab-user-journey.html').read_text()
    section = html.split('const studyCatalog=[')[1].split('];')[0]
    ids = re.findall(r"id:'([^']+)'", section)
    assert len(ids) == 16
    for widget in ids:
        assert parse({'widget_id': widget, 'targets': ['BBCA']}).widget_id == widget
    assert {item['id'] for item in catalog()} == set(ids)


def test_sector_members_resolved_server_side():
    request = parse({'widget_id': 'price_risk', 'target_kind': 'sector', 'targets': ['Financials']})
    assert request.entities == ('BBCA', 'BBRI')
    with pytest.raises(ValueError):
        parse({'widget_id': 'price_risk', 'target_kind': 'sector', 'targets': ['Financials', 'AADI']})


@pytest.mark.parametrize('payload', [
    {'widget_id': 'invented'},
    {'widget_id': 'price_risk', 'params': {'code': 'print(1)'}},
    {'widget_id': 'price_risk', 'targets': ['ZZZZ']},
    {'widget_id': 'price_risk', 'target_kind': 'universe', 'targets': ['BBCA']},
    {'widget_id': 'price_risk', 'window': True},
    {'widget_id': 'custom_engineering', 'params': {'field': 'operating_cash_flow'}},
    {'widget_id': 'price_risk', 'cutoff': '2026-02-30'},
    {'widget_id': 'portfolio_risk', 'params': {'risk_free_annual': float('inf')}},
    {'widget_id': 'price_risk', 'members': ['AADI']},
])
def test_unknown_widget_and_code_params_rejected(payload):
    with pytest.raises(ValueError):
        parse(payload)


def test_fingerprint_is_canonical_and_changes_with_source():
    a = parse({'widget_id': 'price_risk', 'targets': ['BBRI', 'BBCA']})
    b = parse({'targets': ['BBCA', 'BBRI'], 'widget_id': 'price_risk'})
    assert request_fingerprint(a, ['b', 'a']) == request_fingerprint(b, ['a', 'b'])
    assert request_fingerprint(a, ['a']) != request_fingerprint(a, ['b'])
    assert request_fingerprint(a, ['a']) != request_fingerprint(parse({'widget_id': 'price_risk', 'targets': ['BBCA']}), ['a'])
    assert request_fingerprint(a,['a'],formula_version='v1') != request_fingerprint(a,['a'],formula_version='v2')
