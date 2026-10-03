"""Behavior contracts for historical CAPM and the integrated research allocation."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from idx_evidence_lab.portfolio_analytics import calculate_portfolio_metrics
from idx_evidence_lab.portfolio_optimization import black_litterman_estimates, optimize_portfolio
from idx_evidence_lab.portfolio_amounts import allocate_lots
from idx_evidence_lab.portfolio_scenarios import run_walk_forward
from idx_evidence_lab.web_app import build_portfolio_analysis, _portfolio_request


def test_historical_capm_preserves_negative_premium_and_aligned_beta():
    market = [-.01, .005, -.02, .01]
    portfolio = [2 * v for v in market]
    result = calculate_portfolio_metrics([f"2026-01-0{i}" for i in range(1, 5)], portfolio, market, .07129)
    premium = np.mean(market) * 252 - .07129
    assert result["assumptions"]["market_premium_annual"] == pytest.approx(premium)
    assert result["beta"]["value"] == pytest.approx(2)
    assert result["capm_hurdle"]["value"] == pytest.approx(.07129 + 2 * premium)
    assert result["assumptions"]["market_premium_source"] == "ALIGNED_HISTORICAL_BENCHMARK"


def test_bl_posterior_matches_scalar_bayesian_update():
    values = np.array([[.01], [-.005], [.02]])
    covariance = np.array([[.001]])
    posterior, meta = black_litterman_estimates(values, covariance, [1], .07129)
    rf = (1.07129)**(1/252) - 1
    assert posterior[0] == pytest.approx((.0025 + values.mean() - rf) / 2 + rf)
    assert meta["prior_weights"] == [1]


def test_integrated_respects_caps_risk_and_diversification_floor():
    rng = np.random.default_rng(42)
    values = rng.normal(.001, .015, (252, 5))
    result = optimize_portfolio(values.tolist(), list("ABCDE"), "integrated", "moderate",
                                {"prior_weights": [1,2,3,4,5], "risk_free_annual": .07129})
    assert result["status"] == "READY"
    assert sum(result["weights"].values()) == pytest.approx(1)
    assert max(result["weights"].values()) <= result["constraints"]["max_weight"] + 1e-6
    assert result["estimated_volatility_annual"] <= result["profile_risk_cap_annual"] + 1e-6
    assert result["diversification_ratio"] >= result["diagnostics"]["diversification"]["floor"] - 1e-5


def test_walk_forward_prior_is_from_previous_day_never_current_end():
    dates = [f"2026-01-{i:02d}" for i in range(1, 7)]
    caps = {day: [i + 1] for i, day in enumerate(dates)}
    seen = []
    def optimizer(returns, tickers, method, profile, constraints):
        seen.append(constraints["prior_weights"])
        return {"status": "READY", "weights": {"AAA": 1}}
    with patch("idx_evidence_lab.portfolio_scenarios.optimize_portfolio", optimizer):
        run_walk_forward(dates, [[.001]]*6, ["AAA"], "integrated", "moderate",
                         estimation_window=3, capitalization_by_date=caps)
    assert seen == [caps[dates[2]]]


def test_lots_keep_budget_and_leave_cash_without_overallocating():
    result = allocate_lots({"AAA": .6, "BBB": .4}, 10000, {"AAA": 50, "BBB": 30})
    assert result["rows"]["AAA"]["lots"] == 1
    assert result["rows"]["BBB"]["lots"] == 1
    assert result["invested"] + result["cash"] == 10000
    assert result["cash"] == 2000


def test_local_integrated_api_computes_capm_and_lots():
    request = _portfolio_request({"tickers": ["BBCA", "BBRI", "BMRI", "TLKM", "ASII"],
        "method": "integrated", "profile": "moderate", "lookback": 126,
        "risk_free_annual": .07129, "total_capital": 10000000,
        "scenarios": {"simulations": 4, "horizons": [20]}})
    result = build_portfolio_analysis(Path(__file__).resolve().parents[1], request)
    assert result["selection"]["benchmark"] == "IHSG"
    assert result["metrics"]["capm_hurdle"]["value"] is not None
    assert result["lot_allocation"]["cash"] >= 0
    assert result["market_history"]["sample_count"] == 707
