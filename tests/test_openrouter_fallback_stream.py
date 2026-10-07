"""Model fallback, repair turns and validated block streaming for the live OpenRouter adapter."""
import io
import json
from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

import pytest

from idx_evidence_lab.openrouter_live import OpenRouterError, OpenRouterSearchAdapter, _StreamedBlocks
from idx_evidence_lab.research_types import EvidenceItem, EvidencePack, ResearchContext
from idx_evidence_lab.search import LocalSearchIndex
from idx_evidence_lab.web_app import SearchHandler


class Response:
    def __init__(self, payload=None, lines=()):
        self.payload, self.lines = payload, list(lines)
    def read(self, *args):
        return json.dumps(self.payload).encode()
    def __iter__(self):
        return iter(self.lines)
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


def completion(content, finish='stop'):
    return Response({'choices': [{'finish_reason': finish, 'message': {'content': json.dumps(content)}}]})


def sse(content, finish='stop'):
    """Split a JSON answer into several SSE delta chunks like OpenRouter streaming does."""
    text = json.dumps(content)
    chunks = [text[i:i + 7] for i in range(0, len(text), 7)]
    lines = [b': OPENROUTER PROCESSING\n']
    lines += [b'data: ' + json.dumps({'choices': [{'delta': {'content': c}}]}).encode() + b'\n' for c in chunks]
    lines += [b'data: ' + json.dumps({'choices': [{'delta': {}, 'finish_reason': finish}]}).encode() + b'\n', b'data: [DONE]\n']
    return Response(lines=lines)


def http_error(code):
    return HTTPError('https://openrouter.ai', code, 'error', {}, io.BytesIO(b'{}'))


def pack():
    return EvidencePack(items=[EvidenceItem('E1', 'news/a', 'sectors_source_data', 'BBCA', 'Laba BBCA naik 8%')])


def adapter():
    return OpenRouterSearchAdapter('test-not-a-real-key', model='first:free', fallback_models=['second:free'])


GOOD = {'blocks': [{'text': 'Laba BBCA naik 8%.', 'claim_kind': 'observation', 'evidence_ids': ['E1']},
                   {'text': 'Kenaikan laba belum membuktikan tren.', 'claim_kind': 'inference', 'evidence_ids': ['E1']}]}
NUMBER_IN_INFERENCE = {'blocks': [{'text': 'Laba naik 8% sehingga tren kuat.', 'claim_kind': 'inference', 'evidence_ids': ['E1']}]}


def test_retired_model_falls_back_to_next_model():
    calls = []
    def transport(request, **kwargs):
        calls.append(json.loads(request.data)['model'])
        if len(calls) == 1:
            raise http_error(404)
        return completion({'search_query': 'BBCA', 'intent': 'FIND_EVIDENCE', 'entities': ['BBCA']})
    with patch('idx_evidence_lab.openrouter_live.urlopen', transport):
        plan = adapter().interpret('BBCA', ['BBCA'])
    assert calls == ['first:free', 'second:free']
    assert plan['provider'] == 'OpenRouter' and plan['model'] == 'second:free'


def test_rejected_key_is_not_retried_on_other_models():
    with patch('idx_evidence_lab.openrouter_live.urlopen', side_effect=http_error(401)) as transport:
        with pytest.raises(OpenRouterError) as caught:
            adapter().compose_chat('BBCA', ResearchContext(), pack(), [])
    assert caught.value.status_code == 401 and transport.call_count == 1


def test_rejected_answer_gets_one_repair_turn_with_rejection_code():
    bodies = []
    def transport(request, **kwargs):
        bodies.append(json.loads(request.data))
        return completion(NUMBER_IN_INFERENCE if len(bodies) == 1 else GOOD)
    with patch('idx_evidence_lab.openrouter_live.urlopen', transport):
        reply = adapter().compose_chat('BBCA', ResearchContext(), pack(), [])
    assert reply.model_status['status'] == 'GENERATED' and reply.model_status['model'] == 'first:free'
    repair = bodies[1]['messages']
    assert repair[-2]['role'] == 'assistant' and 'UNSUPPORTED_NUMBER' in repair[-1]['content']
    assert bodies[1]['model'] == 'first:free'


def test_all_models_rejected_reports_rejection_code():
    with patch('idx_evidence_lab.openrouter_live.urlopen', return_value=completion(NUMBER_IN_INFERENCE)) as transport:
        with pytest.raises(OpenRouterError) as caught:
            adapter().compose_chat('BBCA', ResearchContext(), pack(), [])
    assert transport.call_count == 4  # two models x (answer + repair)
    assert caught.value.diagnostics == {'rejection': 'UNSUPPORTED_NUMBER'}


def test_scanner_finds_blocks_across_chunks_and_ignores_braces_in_strings():
    text = json.dumps({'note': '{not a block}', 'blocks': [{'text': 'a } " { b', 'rows': [['x']]}, {'text': '[c]'}]})
    scanner, found = _StreamedBlocks(), []
    for char in text:
        found += scanner.feed(char)
    assert [json.loads(raw)['text'] for raw in found] == ['a } " { b', '[c]']


def test_streaming_forwards_only_validated_blocks_and_resets_on_rejection():
    events = []
    responses = [sse(NUMBER_IN_INFERENCE), sse(GOOD)]
    with patch('idx_evidence_lab.openrouter_live.urlopen', side_effect=lambda *a, **k: responses.pop(0)):
        reply = adapter().compose_chat('BBCA', ResearchContext(), pack(), [], on_event=lambda name, data: events.append((name, data)))
    names = [name for name, _ in events]
    assert names == ['status', 'reset', 'status', 'block', 'block']
    assert events[1][1]['rejection'] == 'UNSUPPORTED_NUMBER'
    assert [data['text'] for name, data in events if name == 'block'] == [b.text for b in reply.blocks]


def test_mid_stream_provider_error_moves_to_next_model():
    failing = Response(lines=[b'data: ' + json.dumps({'error': {'code': 429, 'message': 'busy'}, 'choices': [{'delta': {}, 'finish_reason': 'error'}]}).encode() + b'\n'])
    responses = [failing, sse(GOOD)]
    models = []
    def transport(request, **kwargs):
        models.append(json.loads(request.data)['model'])
        return responses.pop(0)
    with patch('idx_evidence_lab.openrouter_live.urlopen', transport):
        reply = adapter().compose_chat('BBCA', ResearchContext(), pack(), [], on_event=lambda *a: None)
    assert models == ['first:free', 'second:free'] and reply.model_status['model'] == 'second:free'


def test_research_chat_stream_endpoint_ends_with_done_payload():
    server = ThreadingHTTPServer(('127.0.0.1', 0), SearchHandler)
    server.search_index = LocalSearchIndex(); server.tickers = ['BBCA']
    Thread(target=server.serve_forever, daemon=True).start()
    def post(route, value):
        request = Request(f'http://127.0.0.1:{server.server_port}{route}', data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
        return urlopen(request)
    try:
        with post('/api/research-sessions', {}) as response:
            session = json.load(response)
        with post('/api/research-chat', {'session_id': session['session_id'], 'expected_revision': 0, 'query': 'BBCA',
                                         'use_model': False, 'artifact_refs': [], 'stream': True}) as response:
            assert response.headers['Content-Type'].startswith('text/event-stream')
            events = response.read().decode().strip().split('\n\n')
        assert events[-1].startswith('event: done\ndata: ')
        assert json.loads(events[-1].split('data: ', 1)[1])['revision'] == 1
        with post('/api/research-chat', {'session_id': 'expired', 'expected_revision': 0, 'query': 'BBCA',
                                         'use_model': False, 'artifact_refs': [], 'stream': True}) as response:
            assert response.read().decode() == 'event: error\ndata: {"error": "SESSION_EXPIRED"}\n\n'
    finally:
        server.shutdown()
