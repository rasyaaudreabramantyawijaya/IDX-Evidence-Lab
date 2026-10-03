import importlib.util
import pytest
from idx_evidence_lab.research_types import EvidencePack, MetricRecord, ResearchContext


def validate(block, pack=None):
    assert importlib.util.find_spec('idx_evidence_lab.research_validation'), 'Missing reply validation'
    from idx_evidence_lab.research_validation import validate_research_reply
    return validate_research_reply({'blocks': [block]}, pack or EvidencePack(), ResearchContext())


def test_unknown_citation_and_unsupported_numeric_claim_rejected():
    with pytest.raises(ValueError):
        validate({'text': 'Laba meningkat', 'claim_kind': 'observation', 'evidence_ids': ['Efake']})
    with pytest.raises(ValueError):
        validate({'text': 'Peluang akuisisi 90%', 'claim_kind': 'inference'})


def test_indonesian_decimal_and_date_tokens_keep_units():
    pack = EvidencePack(metrics=[MetricRecord('M1', 'yield', 0.125, 'fraction', period={'end': '2026-09-24'})])
    result = validate({'text': 'Yield 12,5% pada 2026-09-24.', 'claim_kind': 'derived_metric', 'metric_ids': ['M1'],
                       'numeric_claims': [{'metric_id': 'M1', 'value': 0.125, 'unit': 'fraction', 'display': '12,5%'}]}, pack)
    assert result.blocks[0].text.startswith('Yield 12,5%')


def test_percent_and_percentage_points_are_not_interchangeable():
    pack = EvidencePack(metrics=[MetricRecord('M1', 'yield', 0.125, 'fraction')])
    with pytest.raises(ValueError):
        validate({'text': '12,5 pp', 'claim_kind': 'derived_metric', 'metric_ids': ['M1'],
                  'numeric_claims': [{'metric_id': 'M1', 'value': 0.125, 'unit': 'fraction', 'display': '12,5 pp'}]}, pack)


@pytest.mark.parametrize('name,kind', [('p90', 'derived_metric'), ('hit_rate', 'historical_frequency')])
def test_historical_metrics_cannot_be_prediction_probability(name, kind):
    pack = EvidencePack(metrics=[MetricRecord('M1', name, 0.6, 'fraction', claim_kind=kind)])
    with pytest.raises(ValueError):
        validate({'text': 'Peluang masa depan', 'claim_kind': 'predictive_probability', 'metric_ids': ['M1']}, pack)


def test_scenario_without_numeric_weight_allowed():
    from idx_evidence_lab.research_types import EvidenceItem
    pack = EvidencePack(items=[EvidenceItem('E1', 'news/a', 'sectors_source_data', 'BBCA', 'Laba melemah')])
    result = validate({'text': 'Jika laba terus melemah, tekanan valuasi mungkin berlanjut.', 'claim_kind': 'scenario', 'evidence_ids': ['E1']}, pack)
    assert result.blocks[0].claim_kind == 'scenario'


def test_unsupported_table_cell_numeric_claim_rejected():
    with pytest.raises(ValueError):
        validate({'kind': 'table', 'claim_kind': 'concept', 'text': '', 'columns': ['Peluang'], 'rows': [['90%']]})


def test_forecast_requires_complete_method_metadata():
    pack = EvidencePack(metrics=[MetricRecord('M1', 'return', 0.1, 'fraction', claim_kind='forecast')])
    with pytest.raises(ValueError):
        validate({'text': 'Forecast', 'claim_kind': 'forecast', 'metric_ids': ['M1']}, pack)


def test_unsupported_probability_returns_gap_not_fake_zero():
    assert importlib.util.find_spec('idx_evidence_lab.research_validation'), 'Missing local composer'
    from idx_evidence_lab.research_validation import compose_local_reply
    from idx_evidence_lab.task_navigation import resolve_research_plan
    reply = compose_local_reply(resolve_research_plan('probabilitas BBCA naik', None, ['BBCA']), EvidencePack())
    assert reply.missing_inputs and not any('0%' in b.text for b in reply.blocks)


def test_numeric_display_cannot_remove_substring_of_unsupported_number():
    pack = EvidencePack(metrics=[MetricRecord('M1', 'beta', 1, 'ratio')])
    with pytest.raises(ValueError, match='UNSUPPORTED_NUMBER'):
        validate({'text': 'Beta 111', 'claim_kind': 'derived_metric', 'metric_ids': ['M1'],
                  'numeric_claims': [{'metric_id': 'M1', 'value': 1, 'unit': 'ratio', 'display': '1'}]}, pack)
