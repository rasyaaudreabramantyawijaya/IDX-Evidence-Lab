"""Local API and atomic artifact boundaries for Factor Zoo."""

import hashlib
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import pytest

from idx_evidence_lab import web_app


ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def server_at(root):
    from unittest.mock import patch
    with patch.object(web_app, "ROOT", root):
        server = ThreadingHTTPServer(("127.0.0.1", 0), web_app.SearchHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield "http://127.0.0.1:{}".format(server.server_port)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


def get_json(base, route, origin=None):
    headers = {"Origin": origin} if origin else {}
    with urlopen(Request(base + route, headers=headers), timeout=20) as response:
        return response.status, json.loads(response.read()), response.headers


def test_factor_data_route_matches_atomically_written_artifact(tmp_path):
    payload = {"schema_version": "portfolio-factor-zoo.v1", "records": [], "sources": {"sha256": "abc"}}
    from unittest.mock import patch
    with patch.object(web_app, "build_factor_zoo_payload", return_value=payload):
        with server_at(tmp_path) as base:
            status, response, _ = get_json(base, "/api/portfolio-factor-zoo-data")
    artifact = json.loads((tmp_path / "docs/prototypes/portfolio-factor-zoo-data.json").read_text())
    assert status == 200
    assert response == artifact
    assert response["artifact_fingerprint"]
    assert not list((tmp_path / "docs/prototypes").glob("*.tmp"))


def test_factor_data_route_does_not_rewrite_an_unchanged_artifact(tmp_path):
    from unittest.mock import patch
    from idx_evidence_lab.portfolio_factors import _published_artifact
    earlier = {"schema_version": "portfolio-factor-zoo.v1", "as_of": {"computed_at_utc": "00:00"},
               "records": [], "sources": {"sha256": "same-source"}}
    current = _published_artifact(earlier)
    folder = tmp_path / "docs/prototypes"
    folder.mkdir(parents=True)
    path = folder / "portfolio-factor-zoo-data.json"
    path.write_text(json.dumps(current), encoding="utf-8")
    before = path.stat().st_mtime_ns
    later = {**earlier, "as_of": {"computed_at_utc": "00:01"}}
    with patch.object(web_app, "build_factor_zoo_payload", return_value=later), \
            patch.object(web_app, "write_factor_zoo_artifact") as write_artifact:
        with server_at(tmp_path) as base:
            status, response, _ = get_json(base, "/api/portfolio-factor-zoo-data")
    assert status == 200
    assert response == current
    assert path.stat().st_mtime_ns == before
    write_artifact.assert_not_called()


def test_live_web_payload_matches_python_and_matlab_shared_artifact_exactly():
    from idx_evidence_lab.portfolio_factors import build_factor_zoo_payload, _published_artifact
    python_payload = _published_artifact(build_factor_zoo_payload(ROOT))
    with server_at(ROOT) as base:
        status, web_payload, _ = get_json(base, "/api/portfolio-factor-zoo-data")
    matlab_input = json.loads((ROOT / "docs/prototypes/portfolio-factor-zoo-data.json").read_text(encoding="utf-8"))
    assert status == 200
    assert web_payload == matlab_input
    python_payload["as_of"].pop("computed_at_utc", None)
    web_payload["as_of"].pop("computed_at_utc", None)
    matlab_input["as_of"].pop("computed_at_utc", None)
    assert web_payload == python_payload == matlab_input
    assert web_payload["schema_version"] == "portfolio-factor-zoo.v1"
    assert web_payload["sources"]["sha256"]
    assert len(web_payload["records"]) == 45


def test_factor_view_route_defaults_to_waiting_for_matlab(tmp_path):
    with server_at(tmp_path) as base:
        status, response, headers = get_json(base, "/api/portfolio-factor-zoo-view")
    assert status == 200
    assert response["status"] == "WAITING_FOR_MATLAB"
    assert headers["Cache-Control"] == "no-store"


def test_factor_view_route_rejects_malformed_state(tmp_path):
    view = tmp_path / "docs/prototypes/portfolio-factor-zoo-view.json"
    view.parent.mkdir(parents=True)
    view.write_text('{"azimuth":"sideways"}', encoding="utf-8")
    with server_at(tmp_path) as base:
        with pytest.raises(HTTPError) as error:
            get_json(base, "/api/portfolio-factor-zoo-view")
    assert error.value.code == 409


def test_factor_view_route_rejects_state_for_a_different_artifact(tmp_path):
    folder = tmp_path / "docs/prototypes"
    folder.mkdir(parents=True)
    (folder / "portfolio-factor-zoo-data.json").write_text(json.dumps({
        "schema_version": "portfolio-factor-zoo.v1", "artifact_fingerprint": "current",
    }), encoding="utf-8")
    (folder / "portfolio-factor-zoo-view.json").write_text(json.dumps({
        "schema_version": "portfolio-factor-zoo.v1", "azimuth": 30, "elevation": 20,
        "updated_at_utc": "2026-10-01T00:00:00Z", "artifact_fingerprint": "stale",
    }), encoding="utf-8")
    with server_at(tmp_path) as base:
        with pytest.raises(HTTPError) as error:
            get_json(base, "/api/portfolio-factor-zoo-view")
    assert error.value.code == 409


def test_factor_routes_allow_only_prototype_origin(tmp_path):
    with server_at(tmp_path) as base:
        _, _, allowed = get_json(base, "/api/portfolio-factor-zoo-view", "http://127.0.0.1:5500")
        _, _, denied = get_json(base, "/api/portfolio-factor-zoo-view", "https://example.invalid")
    assert allowed["Access-Control-Allow-Origin"] == "http://127.0.0.1:5500"
    assert "Access-Control-Allow-Origin" not in denied


def test_factor_export_cli_writes_shared_artifact_without_touching_sources(tmp_path):
    source = ROOT / "data/raw/sectors/lq45-universe.json"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "factor-data.json"
    result = subprocess.run([sys.executable, str(ROOT / "scripts/export_portfolio_factor_zoo_data.py"),
                             "--root", str(ROOT), "--output", str(output)], capture_output=True, text=True,
                            env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text())
    assert payload["schema_version"] == "portfolio-factor-zoo.v1"
    assert payload["sources"]["sha256"]
    assert len(payload["records"]) == 45
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_factor_export_default_uses_the_canonical_shared_path(tmp_path):
    from unittest.mock import patch
    from idx_evidence_lab.portfolio_factors import export_factor_zoo_artifact
    payload = {"schema_version": "portfolio-factor-zoo.v1", "records": [], "sources": {"sha256": "abc"}}
    with patch("idx_evidence_lab.portfolio_factors.build_factor_zoo_payload", return_value=payload):
        manifest = export_factor_zoo_artifact(tmp_path)
    assert manifest["path"] == tmp_path / "docs/prototypes/portfolio-factor-zoo-data.json"
    assert json.loads(manifest["path"].read_text())["artifact_fingerprint"] == manifest["artifact_fingerprint"]


def test_artifact_fingerprint_is_stable_when_only_build_timestamp_changes():
    from idx_evidence_lab.portfolio_factors import _published_artifact
    first = {"schema_version": "portfolio-factor-zoo.v1", "as_of": {"computed_at_utc": "00:00", "price": "2026-09-24"}, "records": []}
    second = {**first, "as_of": {"computed_at_utc": "00:01", "price": "2026-09-24"}}
    assert _published_artifact(first)["artifact_fingerprint"] == _published_artifact(second)["artifact_fingerprint"]


def test_matlab_script_uses_shared_factor_artifact_and_separate_atomic_view_state():
    script = (ROOT / "scripts/build_portfolio_factor_zoo.m").read_text()
    assert "portfolio-factor-zoo-data.json" in script
    assert "portfolio-factor-zoo-view.json" in script
    assert "scatter3" in script and "Low Volatility" in script
    assert "Value" in script and "Momentum" in script and "Quality" in script
    assert "movefile" in script and "artifact_fingerprint" in script
    assert "https://" not in script
