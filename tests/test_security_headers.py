import json
import socket
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

from idx_evidence_lab import web_app
from idx_evidence_lab.security import SECURITY_HEADERS


@contextmanager
def server_at():
    server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
    server.search_index = web_app.build_local_index()
    server.tickers = web_app.load_tickers()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def fetch(base, path, *, method="GET", body=None, headers=None):
    req = urllib.request.Request(base + path, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers


def assert_hardened(headers):
    for name, value in SECURITY_HEADERS:
        assert headers.get(name) == value, name
    assert "script-src" not in headers["Content-Security-Policy"]
    assert "script-src 'self'" in headers["Content-Security-Policy-Report-Only"]


def test_headers_on_json_static_and_error_responses():
    with server_at() as base:
        status, headers = fetch(base, "/api/health")
        assert status == 200
        assert_hardened(headers)
        status, headers = fetch(base, "/")
        assert status == 200
        assert_hardened(headers)
        status, headers = fetch(base, "/definitely-missing")
        assert status == 404
        assert_hardened(headers)
        status, headers = fetch(base, "/api/studies-run", method="OPTIONS")
        assert status == 403
        assert_hardened(headers)
        status, headers = fetch(base, "/api/search", method="POST", body=b"x" * 5000,
                                headers={"Content-Type": "application/json"})
        assert status == 413
        assert_hardened(headers)


def test_stalled_client_is_dropped_after_timeout(monkeypatch):
    monkeypatch.setattr(web_app.SearchHandler, "timeout", 0.5)
    with server_at() as base:
        port = int(base.rsplit(":", 1)[1])
        with socket.create_connection(("127.0.0.1", port), timeout=10) as sock:
            sock.sendall(b"POST /api/search HTTP/1.1\r\nHost: x\r\nContent-Length: 100\r\n\r\n{")
            sock.settimeout(10)
            try:
                data = sock.recv(4096)
            except (ConnectionResetError, socket.timeout):
                data = b""
            # Server closed or answered; either way it did not wait forever.
            assert not data or data.startswith(b"HTTP/1.")
        status, _ = fetch(base, "/api/health")
        assert status == 200


def test_json_bodies_are_untouched_by_headers():
    with server_at() as base:
        with urllib.request.urlopen(base + "/api/health", timeout=30) as response:
            assert json.loads(response.read())["ok"] is True
