"""The established port-5500 prototype URL and its local assets stay usable."""

import json
import shutil
import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from idx_evidence_lab import web_app


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_established_prototype_path_is_served_by_app_server(local_server):
    with urlopen(local_server + "/docs/prototypes/idx-evidence-lab-user-journey.html") as response:
        assert response.status == 200
        assert response.headers.get_content_type() == "text/html"
        assert b"IDX Evidence Lab" in response.read()


def test_only_required_public_prototype_artifacts_are_served(local_server):
    for name in ("ihsg-evt-tail-surface-data.json", "market-overview-data.json", "news-universe.json"):
        with urlopen(local_server + "/docs/prototypes/" + name) as response:
            assert response.status == 200
            assert response.headers.get_content_type() == "application/json"
            assert isinstance(json.load(response), dict)
    with pytest.raises(HTTPError) as error:
        urlopen(local_server + "/docs/prototypes/../../AGENTS.md")
    assert error.value.code == 404


def test_portfolio_requests_use_the_page_origin_on_port_5500():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed for the embedded browser-JavaScript contract")
    source = (ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
    function = source.split("function portfolioApiUrl(path)", 1)[1].split("\n", 1)[0]
    script = "const location={port:'5500'};function portfolioApiUrl(path)" + function + "\nprocess.stdout.write(portfolioApiUrl('/api/portfolio-data'))"
    result = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
    assert result.stdout == "/api/portfolio-data"


def test_all_portfolio_api_routes_stay_relative_for_the_live_server_proxy():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed for the embedded browser-JavaScript contract")
    source = (ROOT / "docs/prototypes/idx-evidence-lab-user-journey.html").read_text(encoding="utf-8")
    function = source.split("function portfolioApiUrl(path)", 1)[1].split("\n", 1)[0]
    paths = [
        "/api/health",
        "/api/portfolio-data",
        "/api/portfolio-analysis",
        "/api/portfolio-factor-zoo-data",
        "/api/portfolio-factor-zoo-view",
    ]
    script = (
        "const location={port:'5500'};function portfolioApiUrl(path)" + function
        + "\nprocess.stdout.write(JSON.stringify(" + json.dumps(paths)
        + ".map(portfolioApiUrl)))"
    )
    result = subprocess.run([node, "-e", script], check=True, capture_output=True, text=True)
    assert json.loads(result.stdout) == paths


def test_readme_explains_go_live_and_local_api_sidecar_startup():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "IDX Evidence Lab: Local API (5501)" in readme
    assert "Go Live" in readme
    assert "127.0.0.1:5500" in readme
    assert "127.0.0.1:5501" in readme
    assert "/api" in readme
