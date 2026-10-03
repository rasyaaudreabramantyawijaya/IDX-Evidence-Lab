"""Behavior contracts for descriptive LQ45 factor scoring."""

import pytest
from pathlib import Path

from idx_evidence_lab.portfolio_factors import (
    combine_factor_components,
    earnings_yield_from_forward_pe,
    momentum_components,
    score_cross_section,
    score_peer_groups,
    _regression_components,
    build_factor_zoo_payload,
)


ROOT = Path(__file__).resolve().parents[1]


def test_score_cross_section_direction_winsorization_and_clip():
    result = score_cross_section({"A": -2, "B": -1, "C": 0, "D": 1, "E": 2})
    assert result["status"] == "AVAILABLE"
    assert result["scores"]["A"] == pytest.approx(-1.382, abs=0.002)
    assert result["scores"]["E"] == pytest.approx(1.382, abs=0.002)
    assert result["scores"]["C"] == pytest.approx(0)
    assert max(abs(value) for value in result["scores"].values()) <= 3


def test_score_cross_section_abstains_for_small_or_constant_peer_set():
    small = score_cross_section({"A": 1, "B": 2, "C": 3, "D": 4})
    constant = score_cross_section({"A": 1, "B": 1, "C": 1, "D": 1, "E": 1})
    assert small["status"] == "UNAVAILABLE"
    assert all(value is None for value in small["scores"].values())
    assert constant["status"] == "UNAVAILABLE"
    assert all(value is None for value in constant["scores"].values())


def test_composite_uses_equal_weight_and_marks_partial():
    result = combine_factor_components({
        "a": {"score": 1.0, "status": "AVAILABLE"},
        "b": {"score": -0.5, "status": "AVAILABLE"},
    })
    assert result == {"score": 0.25, "status": "AVAILABLE", "available_components": 2}
    partial = combine_factor_components({
        "a": {"score": 1.0, "status": "AVAILABLE"},
        "b": {"score": None, "status": "UNAVAILABLE"},
    })
    assert partial["score"] == 1.0
    assert partial["status"] == "PARTIAL"
    assert combine_factor_components({"a": {"score": None, "status": "UNAVAILABLE"}})["status"] == "UNAVAILABLE"


def test_reverse_component_scores_lower_raw_values_higher():
    result = score_cross_section({"A": 1, "B": 2, "C": 3, "D": 4, "E": 5}, reverse=True)
    assert result["scores"]["A"] > result["scores"]["E"]


def test_nonpositive_forward_pe_is_not_inverted():
    assert earnings_yield_from_forward_pe(-9.4) == {
        "value": None, "status": "NOT_COMPARABLE", "reason": "Forward P/E is non-positive; not inverted."
    }
    assert earnings_yield_from_forward_pe(0)["value"] is None
    assert earnings_yield_from_forward_pe(10)["value"] == pytest.approx(0.1)


def test_quality_components_are_scored_within_financial_peer_group():
    values = {"B1": 1, "B2": 2, "B3": 3, "B4": 4, "B5": 5,
              "N1": 101, "N2": 102, "N3": 103, "N4": 104, "N5": 105}
    groups = {ticker: "financial" if ticker.startswith("B") else "non_financial" for ticker in values}
    scores = score_peer_groups(values, groups)
    assert scores["B1"] == pytest.approx(scores["N1"])
    assert scores["B5"] == pytest.approx(scores["N5"])


def test_momentum_uses_12_1_return_and_ma200():
    closes = [float(value) for value in range(1, 254)]
    result = momentum_components(closes)
    assert result["momentum_12_1"] == pytest.approx(232 / 1 - 1)
    assert result["price_vs_ma200"] == pytest.approx(253 / (sum(range(54, 254)) / 200) - 1)


def test_low_volatility_requires_aligned_ihsg_returns():
    too_short = [(str(i), i / 10000, (i % 7) / 10000) for i in range(125)]
    beta, residual, reason = _regression_components(too_short)
    assert beta is None and residual is None
    assert "126 required" in reason
    sufficient = [(str(i), (i % 11) / 10000, (i % 7) / 10000) for i in range(126)]
    beta, residual, reason = _regression_components(sufficient)
    assert beta is not None and residual is not None and reason is None


def test_unverified_source_or_missing_field_remains_unavailable():
    assert earnings_yield_from_forward_pe(10, verified=False)["status"] == "UNAVAILABLE"
    assert earnings_yield_from_forward_pe(None)["status"] == "UNAVAILABLE"
    assert earnings_yield_from_forward_pe(float("nan"))["status"] == "UNAVAILABLE"


def test_local_snapshot_audit_keeps_all_lq45_and_reports_real_coverage():
    payload = build_factor_zoo_payload(ROOT)
    assert len(payload["records"]) == 45
    assert payload["coverage"]["factors"]["quality"]["AVAILABLE"] == 45
    assert payload["coverage"]["factors"]["momentum"]["AVAILABLE"] == 45
    assert payload["coverage"]["factors"]["low_volatility"]["AVAILABLE"] == 45
    goto = next(row for row in payload["records"] if row["ticker"] == "GOTO")
    assert goto["components"]["earnings_yield"]["status"] == "NOT_COMPARABLE"
    assert goto["components"]["earnings_yield"]["source_value"] < 0
    cuan = next(row for row in payload["records"] if row["ticker"] == "CUAN")
    assert cuan["components"]["dividend_yield"]["value"] == 0
