"""Regression checks against the local, provenance-checked Sectors snapshots."""

from pathlib import Path

from idx_evidence_lab.market_data import load_lq45_universe
from idx_evidence_lab.market_overview_analytics import load_foreign_flow, load_valuation_snapshot


ROOT = Path(__file__).resolve().parents[1]


def test_foreign_flow_is_daily_and_does_not_score_open_month():
    symbols = [row["ticker"] for row in load_lq45_universe(ROOT)["symbols"]]
    result = load_foreign_flow(ROOT, symbols)
    assert result["data_quality"] == "VERIFIED"
    assert result["issue_count"] == 0
    assert len(result["daily"]) > 250
    assert all(row["buy"] >= 0 and row["sell"] >= 0 for row in result["daily"])
    assert all(abs(row["buy"] - row["sell"] - row["net"]) < 10 for row in result["daily"])
    assert result["monthly"][-1]["complete"] is False
    assert result["monthly"][-1]["z12"] is None
    assert all(row["z12"] is None or row["complete"] for row in result["monthly"])


def test_valuation_ratio_is_labeled_snapshot_not_historical_z_band():
    symbols = [row["ticker"] for row in load_lq45_universe(ROOT)["symbols"]]
    result = load_valuation_snapshot(ROOT, symbols)
    assert result["issue_count"] == 0
    assert result["market_cap_coverage"] == len(symbols)
    assert result["ocf_latest_coverage"] == len(symbols)
    assert result["cap_to_ocf"] > 0
    assert result["lq45_index_history_pulled"] is False
    assert result["forward_pe_history_pulled"] is False
    assert len(result["forward_pe_by_issuer"]) == len(symbols)
    assert result["forward_pe_coverage"] == 36
    assert result["forward_pe_negative_count"] == 1
    assert result["forward_pe_missing_count"] == 8
    goto = next(row for row in result["forward_pe_by_issuer"] if row["ticker"] == "GOTO")
    assert goto["status"] == "negative"
    assert goto["forward_pe"] < 0
