"""Same-origin portfolio API contracts on saved local snapshots."""

import hashlib
import json
import threading
from types import SimpleNamespace
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from idx_evidence_lab import web_app


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server_at(root=ROOT):
    with patch.object(web_app, "ROOT", root):
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
        server.search_index = SimpleNamespace(as_records=lambda: [])
        server.tickers = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


def request_json(base, path, payload=None, *, body=None):
    if payload is not None or body is not None:
        raw = body if body is not None else json.dumps(payload).encode()
        request = Request(base + path, data=raw, method="POST", headers={"Content-Type": "application/json"})
    else:
        request = base + path
    try:
        with urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read()) if error.headers.get_content_type() == "application/json" else {}


def test_portfolio_data_endpoint_reports_local_universe_and_readiness():
    with server_at() as base:
        status, payload = request_json(base, "/api/portfolio-data")
    assert status == 200
    assert len(payload["tickers"]) == 45
    assert payload["tickers"][0]["sub_sector"]
    assert payload["benchmarks"] == ["IHSG", "LQ45"]
    assert payload["risk_free_rate"]["status"] == "UNAVAILABLE"
    assert payload["universe_quality"] == "PARTIAL"


def test_local_health_endpoint_reports_ready_for_the_live_server_proxy():
    with server_at() as base:
        request = base + "/api/health"
        with urlopen(request, timeout=5) as response:
            status, payload = response.status, json.loads(response.read())

    assert status == 200
    assert payload["ok"] is True


def test_portfolio_data_endpoint_allows_the_local_live_server_origin():
    with server_at() as base:
        request = Request(base + "/api/portfolio-data", headers={"Origin": "http://127.0.0.1:5500"})
        with urlopen(request, timeout=20) as response:
            assert response.status == 200
            assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5500"
        preflight = Request(base + "/api/portfolio-analysis", method="OPTIONS", headers={
            "Origin": "http://127.0.0.1:5500",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        with urlopen(preflight, timeout=20) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5500"
            assert "POST" in response.headers["Access-Control-Allow-Methods"]


def test_portfolio_analysis_uses_only_local_data_and_serializes_result():
    raw_path = ROOT / "data/raw/sectors/lq45-universe.json"
    before = hashlib.sha256(raw_path.read_bytes()).hexdigest()
    with patch.object(web_app, "OpenRouterSearchAdapter", side_effect=AssertionError("external model called")):
        with server_at() as base:
            status, payload = request_json(base, "/api/portfolio-analysis", {
                "tickers": ["BBCA"], "benchmark": "IHSG", "profile": "moderate",
                "method": "markowitz", "lookback": 126,
                "risk_free_annual": 0.07129,
                "scenarios": {"horizons": [20], "simulations": 12, "seed": 7},
            })
    assert status == 200
    assert payload["status"] == "READY"
    assert payload["allocation"]["weights"] == {"BBCA": 1.0}
    assert payload["sub_sectors"]["BBCA"]
    assert payload["method_metrics"]["hrp"]["sortino"]["status"] in {"DESCRIPTIVE", "UNDEFINED"}
    assert payload["method_metrics"]["equal_weight"]["sample_count"] == 126
    assert payload["metrics"]["sharpe"]["status"] == "ASSUMPTION_BASED"
    assert payload["metrics"]["assumptions"]["market_premium_source"] == "ATH_RECOVERY_ASSUMPTION"
    assert payload["metrics"]["assumptions"]["market_return_expected_annual"] == payload["market_history"]["ath_recovery_return"]
    assert payload["market_history"]["all_time_high"] == 9174.0
    assert payload["market_history"]["latest_index_level"] == 6298.607
    assert payload["market_history"]["ath_recovery_as_of"] == payload["market_history"]["coverage_end"]
    historical_capm = payload["historical_capm"]
    historical_market_return = payload["metrics"]["assumptions"]["market_return_arithmetic_annual"]
    assert historical_capm["market_return_arithmetic_annual"] == historical_market_return
    assert historical_capm["market_premium_annual"] == historical_market_return - 0.07129
    assert historical_capm["sample_start"] == payload["selection"]["sample_start"]
    assert historical_capm["sample_end"] == payload["selection"]["sample_end"]
    assert historical_capm["capm_hurdle"]["value"] == historical_capm["beta"]["value"] * historical_capm["market_premium_annual"] + 0.07129
    assert payload["scenarios"]["status"] == "EXPLORATORY"
    assert payload["provenance"]["provider"] == "Sectors.app"
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == before


def test_portfolio_analysis_reports_nominal_allocation_for_optional_capital():
    with server_at() as base:
        status, payload = request_json(base, "/api/portfolio-analysis", {
            "tickers": ["BBCA"], "profile": "moderate", "method": "markowitz",
            "lookback": 126, "total_capital": 25_000_000,
            "scenarios": {"horizons": [20], "simulations": 12, "seed": 7},
        })
    assert status == 200
    assert payload["total_capital"] == 25_000_000
    assert payload["amounts"] == {"BBCA": 25_000_000}


def test_portfolio_analysis_rejects_invalid_enums_and_unknown_ticker():
    base_payload = {"tickers": ["BBCA"], "profile": "moderate", "method": "hrp", "lookback": 126}
    with server_at() as base:
        for changed in ({"profile": "reckless"}, {"method": "black_litterman"},
                        {"tickers": ["FAKE"]}, {"benchmark": "SPX"}, {"lookback": 7}):
            status, payload = request_json(base, "/api/portfolio-analysis", {**base_payload, **changed})
            assert status in {400, 422}
            assert payload["status"] in {"INVALID_REQUEST", "UNAVAILABLE"}


def test_portfolio_api_rejects_oversize_body_and_simulation_cap():
    with server_at() as base:
        status, _ = request_json(base, "/api/portfolio-analysis", body=b"{" + b" " * 17000 + b"}")
        assert status == 413
        status, payload = request_json(base, "/api/portfolio-analysis", {
            "tickers": ["BBCA"], "profile": "moderate", "method": "hrp", "lookback": 126,
            "scenarios": {"simulations": 10001},
        })
        assert status == 400
        assert payload["status"] == "INVALID_REQUEST"


def test_portfolio_api_abstains_when_history_or_source_unavailable(tmp_path):
    with server_at(tmp_path) as base:
        status, payload = request_json(base, "/api/portfolio-analysis", {
            "tickers": ["BBCA"], "profile": "moderate", "method": "hrp", "lookback": 126,
        })
    assert status == 422
    assert payload["status"] == "UNAVAILABLE"


def test_unknown_portfolio_route_does_not_fall_back_to_search():
    with server_at() as base:
        status, _ = request_json(base, "/api/portfolio-unknown", {"tickers": ["BBCA"]})
    assert status == 404
