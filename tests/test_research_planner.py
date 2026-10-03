import pytest
from idx_evidence_lab import task_navigation as navigation


def plan(query, previous=None):
    resolver = getattr(navigation, 'resolve_research_plan', None)
    assert callable(resolver), 'Research planner has not been implemented'
    return resolver(query, previous, ['BBCA', 'BMRI', 'TLKM', 'WIFI'])


def test_finance_without_ticker_does_not_default_wifi():
    result = plan('Apa itu risiko portofolio?')
    assert result.context.entities == []
    assert result.context.scope in {'concept', 'portfolio', 'market'}


def test_compare_inherits_then_switch_replaces_entities():
    initial = plan('Risiko BBCA selama 30 hari')
    compared = plan('bandingkan dengan BMRI', initial.context)
    assert compared.context.entities == ['BBCA', 'BMRI']
    assert compared.context.scope == 'comparison'
    assert compared.context.period == {'horizon': 30, 'unit': 'hari'}
    switched = plan('risiko TLKM', compared.context)
    assert switched.context.entities == ['TLKM']
    assert switched.context.period == {}


def test_ambiguous_pronoun_requests_clarification():
    assert plan('Bagaimana risikonya?').clarification


def test_followup_inherits_topic_and_entity():
    first = plan('Risiko BBCA')
    result = plan('Apa yang bisa membatalkan kesimpulan itu?', first.context)
    assert result.context.entities == ['BBCA']
    assert 'price_risk' in result.categories


def test_unknown_ticker_requests_clarification():
    assert plan('Risiko ZZZZ').clarification


def test_forecast_flags_do_not_claim_method_exists():
    result = plan('probabilitas harga BBCA naik bulan depan')
    assert result.wants_probability
    assert result.wants_forecast
