"""Contract tests for locally sourced, aligned portfolio inputs."""

import hashlib
import json
from pathlib import Path

import pytest

from idx_evidence_lab.portfolio_data import load_portfolio_inputs


ROOT = Path(__file__).resolve().parents[1]


def _save(path, payload, metadata):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, separators=(",", ":")).encode()
    path.write_bytes(raw)
    metadata["sha256" if "daily" in path.parts else "snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    meta_path = path.with_name(path.stem + "_meta.json") if "daily" in path.parts else path.with_suffix(".metadata.json")
    meta_path.write_text(json.dumps(metadata), encoding="utf-8")
    return path


def _fixture(root, a=(100, 102, 104), b=(200, 204, 208), *, bad_hash=False, conflict=False):
    days = ["2026-09-21", "2026-09-22", "2026-09-23"]
    universe = root / "data/raw/sectors/lq45-universe.json"
    _save(universe, {"results": [
        {"symbol": "AAA.JK", "company_name": "Alpha", "query_values": {"indices": ["LQ45"]}},
        {"symbol": "BBB.JK", "company_name": "Beta", "query_values": {"indices": ["LQ45"]}},
    ]}, {"provider": "Sectors.app", "http_status": 200, "endpoint": "https://api.sectors.app/v2/companies/?where=LQ45", "retrieved_at": "2026-09-24T00:00:00Z"})
    # Universe metadata uses the older sha256 key.
    metadata_path = universe.with_suffix(".metadata.json")
    metadata = json.loads(metadata_path.read_text())
    metadata["sha256"] = metadata.pop("snapshot_sha256")
    metadata_path.write_text(json.dumps(metadata))
    for ticker, closes in (("AAA", a), ("BBB", b)):
        rows = [{"symbol": ticker + ".JK", "date": day, "close": price, "volume": 100,
                 "market_cap": price * 1000} for day, price in zip(days, closes)]
        path = root / "data/raw/sectors/daily" / ticker / f"{ticker}_2026-09-21_2026-09-23.json"
        _save(path, rows, {"provider": "Sectors.app", "http_status": 200,
                          "ticker": ticker, "endpoint": f"/v2/daily/{ticker}/", "retrieved_at": "2026-09-24T00:00:00Z"})
        if ticker == "BBB" and bad_hash:
            meta = path.with_name(path.stem + "_meta.json")
            altered = json.loads(meta.read_text())
            altered["sha256"] = "invalid"
            meta.write_text(json.dumps(altered))
        if ticker == "BBB" and conflict:
            conflicting = [{**rows[1], "close": 999}]
            another = path.with_name(f"{ticker}_2026-09-22_2026-09-22.json")
            _save(another, conflicting, {"provider": "Sectors.app", "http_status": 200,
                                         "ticker": ticker, "endpoint": f"/v2/daily/{ticker}/"})
        report = root / "data/raw/sectors/company_report" / ticker / "company_report.json"
        _save(report, {"symbol": ticker + ".JK", "sector": "Financials", "sub_sector": "Banks",
                       "overview": {"sector": "Financials", "indices": ["LQ45"]}},
              {"provider": "Sectors.app", "http_status": 200, "symbol": ticker,
               "endpoint": f"https://api.sectors.app/v2/company/report/{ticker}/", "retrieved_at": "2026-09-24T00:00:00Z"})
    index = root / "data/raw/sectors/index_daily/ihsg/ihsg_2026-09-21_2026-09-23.json"
    _save(index, [{"index_code": "ihsg", "date": day, "price": price}
                  for day, price in zip(days, (6000, 6060, 6120))],
          {"provider": "Sectors.app", "http_status": 200, "index_code": "ihsg",
           "endpoint": "https://api.sectors.app/v2/index-daily/ihsg/", "retrieved_at": "2026-09-24T00:00:00Z"})


def test_portfolio_loader_rejects_unverified_or_conflicting_daily_rows(tmp_path):
    _fixture(tmp_path, bad_hash=True)
    result = load_portfolio_inputs(tmp_path, ["AAA", "BBB"], minimum_returns=1)
    assert result["status"] == "BLOCKED"
    assert result["return_matrix"] == []
    assert any("BBB" in issue and "hash" in issue.lower() for issue in result["issues"])
    _fixture(tmp_path, conflict=True)
    result = load_portfolio_inputs(tmp_path, ["AAA", "BBB"], minimum_returns=1)
    assert result["status"] == "BLOCKED"
    assert any("conflict" in issue.lower() for issue in result["issues"])


def test_portfolio_loader_reports_intersection_and_insufficient_history(tmp_path):
    _fixture(tmp_path, b=(200, 204))
    result = load_portfolio_inputs(tmp_path, ["AAA", "BBB"], minimum_returns=2)
    assert result["dates"] == ["2026-09-21", "2026-09-22"]
    assert result["return_dates"] == ["2026-09-22"]
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["coverage"]["common_price_sessions"] == 2


def test_portfolio_return_quality_flags_unexplained_price_jumps(tmp_path):
    _fixture(tmp_path, a=(100, 180, 182))
    result = load_portfolio_inputs(tmp_path, ["AAA", "BBB"], minimum_returns=1)
    assert result["return_dates"] == ["2026-09-23"]
    assert result["quality"] == "PROVISIONAL"
    assert any("2026-09-22" in issue and "AAA" in issue for issue in result["issues"])


def test_portfolio_loader_aligns_prices_caps_benchmark_and_reports_factor_gates(tmp_path):
    _fixture(tmp_path)
    result = load_portfolio_inputs(tmp_path, ["BBB", "AAA"], minimum_returns=2)
    assert result["status"] == "READY"
    assert result["tickers"] == ["BBB", "AAA"]
    assert result["close_matrix"] == [[200.0, 100.0], [204.0, 102.0], [208.0, 104.0]]
    assert result["market_cap_matrix"][0] == [200000.0, 100000.0]
    assert result["return_dates"] == ["2026-09-22", "2026-09-23"]
    assert result["return_matrix"][0] == pytest.approx([0.02, 0.02])
    assert result["benchmark_returns"]["2026-09-22"] == pytest.approx(0.01)
    assert result["sectors"] == {"BBB": "Financials", "AAA": "Financials"}
    assert result["sub_sectors"] == {"BBB": "Banks", "AAA": "Banks"}
    assert result["field_status"]["risk_free_rate"] == "UNAVAILABLE"
    assert result["field_status"]["value_factor"] == "UNAVAILABLE"
    assert "snapshot" in result["universe_limitation"].lower()


def test_portfolio_loader_validates_current_universe(tmp_path):
    _fixture(tmp_path)
    with pytest.raises(ValueError, match="LQ45"):
        load_portfolio_inputs(tmp_path, ["CCC"])
    with pytest.raises(ValueError, match="benchmark"):
        load_portfolio_inputs(tmp_path, ["AAA"], benchmark="SPX")


def test_local_lq45_universe_contains_45_symbols():
    result = load_portfolio_inputs(ROOT, ["BBCA"], minimum_returns=126)
    assert result["universe"]["symbol_count"] == 45
    assert result["universe"]["data_quality"] == "PARTIAL"
    assert any("hash" in issue.lower() for issue in result["issues"])
    assert result["coverage"]["common_price_sessions"] >= 126
