"""Contract test: the API must keep answering exactly as recorded in tests/golden/.

If this fails after an intentional change, review the differences, then refresh the snapshots with
`python tests/golden_master.py capture` and commit them together with the change that caused them.
Point it at another server (e.g. the FastAPI app in Phase 3) with GOLDEN_BASE_URL=http://127.0.0.1:PORT.
"""
import os

import pytest

import golden_master as golden


@pytest.fixture(scope="module")
def live_cases():
    base_url = os.environ.get("GOLDEN_BASE_URL")
    if base_url:
        return golden.scenario(base_url)
    with golden.local_server() as base:
        return golden.scenario(base)


def test_api_matches_golden_master(live_cases):
    problems = golden.compare(golden.read_snapshots(), live_cases)
    assert not problems, "API behavior changed:\n" + "\n".join(problems[:40])


def test_snapshots_cover_the_whole_api(live_cases):
    stored = golden.read_snapshots()
    assert len(stored) >= 90
    # Every route the server defines is exercised at least once.
    paths = {rec["request"]["path"].split("?")[0] for rec in stored.values()}
    for route in ("/api/health", "/api/studies-catalog", "/api/studies-run", "/api/portfolio-analysis", "/api/search",
                  "/api/issuer-research", "/api/issuer-daily", "/api/dashboard-data", "/api/screener-analysis",
                  "/api/sector-heatmap", "/api/news-universe", "/api/research-targets", "/api/source-report",
                  "/api/portfolio-data", "/api/portfolio-factor-zoo-data", "/api/portfolio-factor-zoo-view",
                  "/api/research-sessions", "/api/research-chat", "/api/research-cancel", "/api/research-attachments"):
        assert route in paths, route


def test_compare_detects_real_changes_and_ignores_float_noise():
    base = {"x": {"status": 200, "headers": {"a": "1"}, "body": {"v": [1.0, "s", None], "n": 3}}}
    noisy = {"x": {"status": 200, "headers": {"a": "1"}, "body": {"v": [1.0000000000000002, "s", None], "n": 3}}}
    assert golden.compare(base, noisy) == []
    for change in ({"status": 500}, {"headers": {"a": "2"}}, {"body": {"v": [1.01, "s", None], "n": 3}},
                   {"body": {"v": [1.0, "s", None], "n": 4}}, {"body": {"v": [1.0, "s", None]}},
                   {"body": {"v": [1.0, "s", None], "n": 3, "extra": 1}}):
        assert golden.compare(base, {"x": {**base["x"], **change}}), change
    assert golden.compare(base, {}) and golden.compare({}, base)
