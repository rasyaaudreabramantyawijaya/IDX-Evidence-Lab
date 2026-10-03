import importlib.util
import pytest


def test_invalid_plan_enum_and_unknown_entities_rejected():
    assert importlib.util.find_spec('idx_evidence_lab.research_types'), 'Missing research schema'
    from idx_evidence_lab.research_types import ResearchContext
    with pytest.raises(ValueError):
        ResearchContext(scope='execute_code')
    with pytest.raises(ValueError):
        ResearchContext(entities=['https://external.example'])
    assert ResearchContext().to_dict()['entities'] == []
