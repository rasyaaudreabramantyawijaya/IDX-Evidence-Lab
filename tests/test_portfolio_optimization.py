"""Allocation methods must never disguise infeasible constraints."""

import math

import pytest

from idx_evidence_lab.portfolio_optimization import equal_weight_portfolio, optimize_portfolio


RETURNS = [
    [0.001, 0.020, -0.008], [0.002, -0.015, 0.009],
    [0.001, 0.022, -0.006], [0.002, -0.010, 0.008],
    [0.001, 0.018, -0.007], [0.002, -0.009, 0.010],
    [0.001, 0.021, -0.005], [0.002, -0.011, 0.009],
]
TICKERS = ["AAA", "BBB", "CCC"]


def test_optimizer_returns_infeasible_status_without_partial_weights():
    result = optimize_portfolio(RETURNS, TICKERS, "markowitz", "moderate", {"max_weight": 0.30})
    assert result["status"] == "INFEASIBLE"
    assert result["weights"] is None
    assert "max_weight" in result["reason"]
    sectors = {"AAA": "Bank", "BBB": "Bank", "CCC": "Energy"}
    result = optimize_portfolio(RETURNS, TICKERS, "markowitz", "moderate",
                                {"max_weight": 0.8, "sector_cap": 0.2, "sectors": sectors})
    assert result["status"] == "INFEASIBLE"
    assert result["weights"] is None


@pytest.mark.parametrize("method", ["markowitz", "maximum_diversification", "hrp"])
@pytest.mark.parametrize("profile", ["conservative", "moderate", "aggressive"])
def test_all_methods_and_profiles_are_deterministic_and_fully_invested(method, profile):
    first = optimize_portfolio(RETURNS, TICKERS, method, profile, {"max_weight": 0.8})
    second = optimize_portfolio(RETURNS, TICKERS, method, profile, {"max_weight": 0.8})
    assert first == second
    if first["status"] in {"READY", "OUTSIDE_PROFILE_BUDGET"}:
        assert sum(first["weights"].values()) == pytest.approx(1.0, abs=1e-7)
        assert all(0 <= value <= 0.8 + 1e-7 for value in first["weights"].values())
        assert first["estimated_volatility_annual"] >= 0
        assert first["diversification_ratio"] is not None
    else:
        assert first["status"] == "INFEASIBLE"
        assert first["weights"] is None


def test_default_weight_cap_allows_selection_to_move_away_from_equal_weight():
    result = optimize_portfolio(RETURNS, TICKERS, "markowitz", "aggressive", {})
    assert result["constraints"]["max_weight"] > 1 / 3
    assert result["status"] == "READY"
    assert any(abs(value - 1 / 3) > 0.01 for value in result["weights"].values())


def test_equal_weight_baseline_and_single_stock():
    baseline = equal_weight_portfolio(RETURNS, TICKERS)
    assert baseline["weights"] == {"AAA": pytest.approx(1 / 3), "BBB": pytest.approx(1 / 3), "CCC": pytest.approx(1 / 3)}
    single = optimize_portfolio([[row[0]] for row in RETURNS], ["AAA"], "hrp", "aggressive", {})
    assert single["weights"] == {"AAA": 1.0}
    assert single["status"] == "READY"


def test_hard_sector_cap_and_weakly_conditioned_covariance():
    sectors = {"AAA": "Bank", "BBB": "Bank", "CCC": "Energy"}
    result = optimize_portfolio(RETURNS, TICKERS, "markowitz", "aggressive",
                                {"max_weight": 0.8, "sector_cap": 0.65, "sectors": sectors})
    assert result["status"] == "READY"
    assert result["weights"]["AAA"] + result["weights"]["BBB"] <= 0.65 + 1e-6
    near_constant = [[0.01 + (i % 2) * 1e-8, 0.01 + (i % 2) * 1e-8] for i in range(12)]
    stabilized = optimize_portfolio(near_constant, ["AAA", "BBB"], "markowitz", "aggressive", {})
    assert stabilized["status"] == "READY"
    assert all(math.isfinite(value) for value in stabilized["weights"].values())


def test_invalid_method_profile_or_return_input_is_rejected():
    with pytest.raises(ValueError, match="method"):
        optimize_portfolio(RETURNS, TICKERS, "black_litterman", "moderate", {})
    with pytest.raises(ValueError, match="profile"):
        optimize_portfolio(RETURNS, TICKERS, "markowitz", "unknown", {})
    with pytest.raises(ValueError, match="finite"):
        optimize_portfolio([[0.01, math.nan, 0.0], [0.01, 0.02, 0.0]], TICKERS, "hrp", "moderate", {})
