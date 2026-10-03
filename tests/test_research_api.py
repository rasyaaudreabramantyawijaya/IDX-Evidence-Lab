from http.server import ThreadingHTTPServer
from threading import Thread
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import json
from idx_evidence_lab.web_app import SearchHandler
from idx_evidence_lab.search import LocalSearchIndex


def test_session_endpoint_and_invalid_body():
    server = ThreadingHTTPServer(('127.0.0.1', 0), SearchHandler)
    server.search_index = LocalSearchIndex(); server.tickers = ['BBCA']
    thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    def post(route, value):
        request = Request(f'http://127.0.0.1:{server.server_port}{route}', data=json.dumps(value).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as exc:
            return exc.code, {}
    try:
        status, session = post('/api/research-sessions', {})
        assert status == 201
        with urlopen(f'http://127.0.0.1:{server.server_port}/api/research-targets') as response:
            targets = json.load(response)
        assert targets['tickers'] == ['BBCA']
        assert all(set(row['members']).issubset({'BBCA'}) for row in targets['sectors'])
        assert session['revision'] == 0 and session['history_persistent'] is False
        assert post('/api/research-chat', [1, 2])[0] == 400
        assert post('/api/research-chat', {'session_id': session['session_id'], 'expected_revision': 0, 'query': 'x' * 4001, 'use_model': False, 'artifact_refs': []})[0] == 400
        assert post('/api/research-chat', {'session_id': 'expired', 'expected_revision': 0, 'query': 'BBCA', 'use_model': False, 'artifact_refs': []})[0] == 404
    finally:
        server.shutdown(); server.server_close(); thread.join()
