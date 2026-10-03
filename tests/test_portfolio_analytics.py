"""Hand-checked portfolio metric contracts and unavailable states."""

import math

import pytest

from idx_evidence_lab.portfolio_analytics import calculate_portfolio_metrics, diversification_ratio


def test_metrics_mark_undefined_and_rf_dependent_values():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    result = calculate_portfolio_metrics(dates, [0.01, -0.02, 0.01], [0.005, -0.01, 0.005])
    assert result["sharpe"]["status"] == "UNAVAILABLE"
    assert result["sharpe"]["value"] is None
    assert result["capm_hurdle"]["status"] == "UNAVAILABLE"
    assert result["beta"]["value"] == pytest.approx(2.0)
    constant = calculate_portfolio_metrics(dates, [0.01, 0.01, 0.01], risk_free_annual=0.05)
    assert constant["sharpe"]["status"] == "UNDEFINED"
    assert constant["sortino"]["status"] == "UNDEFINED"
    assert constant["calmar"]["status"] == "UNDEFINED"


def test_metrics_compound_path_and_drawdown_dates_are_exact():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    result = calculate_portfolio_metrics(dates, [0.1, -0.2, 0.3], target_annual=0)
    assert result["sample_count"] == 3
    assert result["cumulative_return"] == pytest.approx(0.144)
    assert result["max_drawdown"]["value"] == pytest.approx(-0.2)
    assert result["max_drawdown"]["peak_date"] == "2026-01-02"
    assert result["max_drawdown"]["trough_date"] == "2026-01-05"
    assert result["max_drawdown"]["recovery_date"] == "2026-01-06"
    assert result["annualized_return"] == pytest.approx(1.144 ** (252 / 3) - 1)
    assert result["calmar"]["value"] == pytest.approx(result["annualized_return"] / 0.2)
    assert result["path"][-1]["wealth"] == pytest.approx(1.144)


def test_drawdown_metadata_does_not_invent_recovery_outside_sample():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    result = calculate_portfolio_metrics(dates, [0.10, -0.20, 0.02, 0.01], target_annual=0)
    drawdown = result["max_drawdown"]
    assert drawdown["peak_date"] == "2026-01-02"
    assert drawdown["trough_date"] == "2026-01-05"
    assert drawdown["recovery_date"] is None


def test_explicit_annual_risk_free_converts_to_daily_and_labels_assumption():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06"]
    result = calculate_portfolio_metrics(dates, [0.01, -0.02, 0.03],
                                         benchmark_returns=[0.005, -0.01, 0.015],
                                         risk_free_annual=0.10, market_premium_annual=0.06)
    assert result["assumptions"]["risk_free_daily"] == pytest.approx(1.1 ** (1 / 252) - 1)
    assert result["sharpe"]["status"] == "ASSUMPTION_BASED"
    assert result["capm_hurdle"]["status"] == "ASSUMPTION_BASED"
    assert result["capm_hurdle"]["value"] == pytest.approx(0.10 + 2 * 0.06)
    assert result["capm_alpha"]["value"] == pytest.approx(result["arithmetic_return_annualized"] - 0.22)


def test_capm_uses_explicit_ath_recovery_market_return_assumption_over_historical_mean():
    dates = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07"]
    result = calculate_portfolio_metrics(
        dates, [0.01, -0.02, 0.03, 0.01],
        benchmark_returns=[-0.01, -0.02, -0.01, -0.03],
        risk_free_annual=0.07129, market_return_assumption_annual=0.4565125272937334,
    )
    assumptions = result["assumptions"]
    assert assumptions["market_return_assumption_annual"] == pytest.approx(0.4565125272937334)
    assert assumptions["market_premium_annual"] == pytest.approx(0.3852225272937334)
    assert assumptions["market_premium_source"] == "ATH_RECOVERY_ASSUMPTION"
    assert result["capm_hurdle"]["value"] == pytest.approx(
        0.07129 + result["beta"]["value"] * (0.4565125272937334 - 0.07129)
    )
    assert "not annualized" in assumptions["capm_convention"]
    assert "heuristic threshold" in result["capm_hurdle"]["reason"]


def test_metric_input_alignment_and_short_series_abstain():
    with pytest.raises(ValueError, match="length"):
        calculate_portfolio_metrics(["2026-01-02"], [0.01, 0.02])
    with pytest.raises(ValueError, match="benchmark"):
        calculate_portfolio_metrics(["2026-01-02", "2026-01-05"], [0.01, 0.02], [0.01])
    short = calculate_portfolio_metrics(["2026-01-02"], [0.01])
    assert short["status"] == "INSUFFICIENT_HISTORY"
    assert short["volatility"] is None
    with pytest.raises(ValueError, match="finite"):
        calculate_portfolio_metrics(["2026-01-02", "2026-01-05"], [0.01, math.nan])


def test_diversification_ratio_uses_asset_and_portfolio_volatility():
    cov = [[0.04, 0.0], [0.0, 0.09]]
    assert diversification_ratio([0.5, 0.5], cov) == pytest.approx(0.25 / math.sqrt(0.0325))
    assert diversification_ratio([1.0, 0.0], cov) == pytest.approx(1.0)
    assert diversification_ratio([0.5, 0.5], [[0.0, 0.0], [0.0, 0.0]]) is None
