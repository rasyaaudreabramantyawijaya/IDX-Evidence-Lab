import json
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer

from idx_evidence_lab import web_app
from idx_evidence_lab.security import RateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_bucket_allows_then_blocks_then_resets():
    clock = FakeClock()
    limiter = RateLimiter({"chat": 2}, window_seconds=60, clock=clock)
    assert limiter.check("1.1.1.1", "chat") == (True, 0)
    assert limiter.check("1.1.1.1", "chat") == (True, 0)
    allowed, retry = limiter.check("1.1.1.1", "chat")
    assert not allowed and 1 <= retry <= 61
    assert limiter.check("2.2.2.2", "chat") == (True, 0)
    clock.now += 61
    assert limiter.check("1.1.1.1", "chat") == (True, 0)


def test_zero_or_unknown_bucket_is_unlimited():
    limiter = RateLimiter({"chat": 0})
    for _ in range(500):
        assert limiter.check("x", "chat") == (True, 0)
        assert limiter.check("x", "other") == (True, 0)


@contextmanager
def server_at():
    server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
    server.search_index = web_app.build_local_index()
    server.tickers = web_app.load_tickers()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def post(base, path, payload):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.headers, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, json.loads(exc.read() or b"{}")


def test_costly_route_returns_429_with_retry_after(monkeypatch):
    monkeypatch.setenv("IDXEL_RL_CHAT_PER_MIN", "2")
    with server_at() as (_, base):
        for _ in range(2):
            status, _, _ = post(base, "/api/research-chat", {})
            assert status != 429
        status, headers, body = post(base, "/api/research-chat", {})
        assert status == 429
        assert body == {"error": "RATE_LIMITED"}
        assert int(headers["Retry-After"]) >= 1
        assert headers["X-Content-Type-Options"] == "nosniff"
        # The cheaper bucket is independent.
        status, _, _ = post(base, "/api/search", {"query": ""})
        assert status == 400


def test_limit_zero_disables_and_servers_do_not_share_state(monkeypatch):
    monkeypatch.setenv("IDXEL_RL_CHAT_PER_MIN", "0")
    with server_at() as (_, base):
        for _ in range(30):
            assert post(base, "/api/research-chat", {})[0] != 429
    monkeypatch.setenv("IDXEL_RL_CHAT_PER_MIN", "1")
    with server_at() as (_, base_a):
        assert post(base_a, "/api/research-chat", {})[0] != 429
        assert post(base_a, "/api/research-chat", {})[0] == 429
        with server_at() as (_, base_b):
            assert post(base_b, "/api/research-chat", {})[0] != 429
