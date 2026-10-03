import json
from unittest.mock import patch
import pytest
from idx_evidence_lab.openrouter_live import OpenRouterSearchAdapter, OpenRouterError
from idx_evidence_lab.research_types import EvidenceItem, EvidencePack, ResearchContext


class Response:
    def __init__(self, payload):
        self.payload = payload
    def read(self, *args):
        return json.dumps(self.payload).encode()
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


def adapter():
    value = OpenRouterSearchAdapter('test-not-a-real-key')
    assert callable(getattr(value, 'compose_chat', None)), 'Missing research chat inference'
    return value


def pack():
    return EvidencePack(items=[EvidenceItem('E1', 'news/a', 'sectors_source_data', 'BBCA', 'BBCA laba melemah'),
                               EvidenceItem('L1', 'private.pdf', 'private_legal_reference', 'Law', 'SECRET PRIVATE', access_class='private')])


def test_payload_contains_public_sources_and_bounded_history():
    captured = []
    def transport(request, **kwargs):
        captured.append(json.loads(request.data))
        return Response({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps({'blocks': [{'text': 'Laba melemah.', 'claim_kind': 'observation', 'evidence_ids': ['E1']}]})}}]})
    a = adapter()
    with patch('idx_evidence_lab.openrouter_live.urlopen', transport):
        result = a.compose_chat('Analisis BBCA', ResearchContext(entities=['BBCA']), pack(), [{'role': 'user', 'content': 'x' * 3000}] * 15)
    assert result.model_status['status'] == 'GENERATED'
    user = json.loads(captured[0]['messages'][1]['content'])
    assert len(user['history']) == 8 and len(user['history'][0]['content']) == 2000
    assert 'SECRET PRIVATE' not in json.dumps(captured)
    assert captured[0]['reasoning']['enabled'] is False
    assert 'provider' not in captured[0]


def test_truncated_output_is_not_generated_success():
    a = adapter()
    with patch('idx_evidence_lab.openrouter_live.urlopen', return_value=Response({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]})):
        with pytest.raises(OpenRouterError):
            a.compose_chat('BBCA', ResearchContext(), pack(), [])


def test_fabricated_forecast_rejected():
    a = adapter()
    payload = {'blocks': [{'text': 'Peluang naik 90%', 'claim_kind': 'predictive_probability', 'evidence_ids': ['E1']}]}
    with patch('idx_evidence_lab.openrouter_live.urlopen', return_value=Response({'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(payload)}}]})):
        with pytest.raises(OpenRouterError):
            a.compose_chat('BBCA', ResearchContext(), pack(), [])
