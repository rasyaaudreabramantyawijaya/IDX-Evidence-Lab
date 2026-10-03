"""Transparent price-return portfolio risk metrics (252 sessions per year)."""

from __future__ import annotations

import math
import statistics
from typing import Any


ANNUAL_SESSIONS = 252


def _metric(value: float | None, status: str, reason: str | None = None) -> dict[str, Any]:
    return {"value": value, "status": status, "reason": reason}


def diversification_ratio(weights: list[float], covariance: list[list[float]]) -> float | None:
    """Weighted individual volatility divided by full portfolio volatility."""
    size = len(weights)
    if not size or len(covariance) != size or any(len(row) != size for row in covariance):
        raise ValueError("weights/covariance shape mismatch")
    values = [*weights, *(entry for row in covariance for entry in row)]
    if not all(math.isfinite(float(value)) for value in values):
        raise ValueError("weights/covariance must be finite")
    diagonal = [covariance[i][i] for i in range(size)]
    if any(value < 0 for value in diagonal):
        return None
    numerator = sum(float(weights[i]) * math.sqrt(diagonal[i]) for i in range(size))
    variance = sum(float(weights[i]) * float(weights[j]) * covariance[i][j]
                   for i in range(size) for j in range(size))
    if variance <= 0 or numerator <= 0:
        return None
    return numerator / math.sqrt(variance)


def calculate_portfolio_metrics(
    dates: list[str], portfolio_returns: list[float], benchmark_returns: list[float] | None = None,
    risk_free_annual: float | None = None, market_premium_annual: float | None = None,
    target_annual: float = 0.0, market_return_assumption_annual: float | None = None,
) -> dict[str, Any]:
    """Calculate descriptive metrics; optional rate inputs are user assumptions."""
    if len(dates) != len(portfolio_returns):
        raise ValueError("dates/portfolio return length mismatch")
    if benchmark_returns is not None and len(benchmark_returns) != len(portfolio_returns):
        raise ValueError("benchmark length mismatch")
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError("dates must be unique and increasing")
    try:
        returns = [float(value) for value in portfolio_returns]
        benchmark = [float(value) for value in benchmark_returns] if benchmark_returns is not None else None
    except (TypeError, ValueError) as exc:
        raise ValueError("returns must be finite numbers") from exc
    if any(not math.isfinite(value) or value <= -1 for value in returns):
        raise ValueError("portfolio returns must be finite and greater than -100%")
    if benchmark is not None and any(not math.isfinite(value) or value <= -1 for value in benchmark):
        raise ValueError("benchmark returns must be finite and greater than -100%")
    for label, value in (("risk_free_annual", risk_free_annual), ("market_premium_annual", market_premium_annual), ("target_annual", target_annual), ("market_return_assumption_annual", market_return_assumption_annual)):
        if value is not None and (not math.isfinite(float(value)) or (label != "market_premium_annual" and value <= -1)):
            raise ValueError(f"{label} must be finite and greater than -100%")
    risk_free_daily = (1 + risk_free_annual) ** (1 / ANNUAL_SESSIONS) - 1 if risk_free_annual is not None else None
    target_daily = (1 + target_annual) ** (1 / ANNUAL_SESSIONS) - 1
    assumptions = {
        "risk_free_annual": risk_free_annual, "risk_free_daily": risk_free_daily,
        "risk_free_source": "USER_INPUT" if risk_free_annual is not None else "UNAVAILABLE",
        "market_premium_annual": market_premium_annual, "target_annual": target_annual,
        "market_return_assumption_annual": market_return_assumption_annual,
        "target_daily": target_daily, "annualization_sessions": ANNUAL_SESSIONS,
        "return_basis": "unadjusted_close_price_return_provisional",
    }
    if len(returns) < 2:
        unavailable = _metric(None, "UNAVAILABLE", "At least two aligned returns required")
        return {
            "status": "INSUFFICIENT_HISTORY", "sample_count": len(returns), "as_of": dates[-1] if dates else None,
            "annualized_return": None, "cumulative_return": None, "volatility": None,
            "arithmetic_return_annualized": None, "sharpe_excess_return_annualized": None,
            "sortino_excess_return_annualized": None, "downside_deviation_annualized": None,
            "sharpe": dict(unavailable), "sortino": dict(unavailable), "calmar": dict(unavailable),
            "max_drawdown": {"value": None, "peak_date": None, "trough_date": None, "recovery_date": None},
            "beta": dict(unavailable), "capm_hurdle": dict(unavailable), "capm_alpha": dict(unavailable),
            "path": [], "assumptions": assumptions,
        }

    wealth = 1.0
    peak_wealth = 1.0
    peak_date = None
    deepest = 0.0
    deepest_peak = None
    deepest_trough = None
    trough_position = None
    path = []
    for position, (day, daily_return) in enumerate(zip(dates, returns)):
        wealth *= 1 + daily_return
        if wealth >= peak_wealth:
            peak_wealth = wealth
            peak_date = day
        drawdown = wealth / peak_wealth - 1
        path.append({"date": day, "wealth": wealth, "drawdown": drawdown})
        if drawdown < deepest:
            deepest = drawdown
            deepest_peak = peak_date
            deepest_trough = day
            trough_position = position
    recovery_date = None
    if trough_position is not None:
        peak_level = path[trough_position]["wealth"] / (1 + deepest)
        recovery_date = next((item["date"] for item in path[trough_position + 1:]
                              if item["wealth"] >= peak_level - 1e-12), None)
    annualized_return = wealth ** (ANNUAL_SESSIONS / len(returns)) - 1
    arithmetic_return_annualized = statistics.mean(returns) * ANNUAL_SESSIONS
    volatility_daily = statistics.stdev(returns)
    volatility = volatility_daily * math.sqrt(ANNUAL_SESSIONS)

    if risk_free_daily is None:
        sharpe = _metric(None, "UNAVAILABLE", "No observed risk-free series or explicit annual assumption")
        sharpe_excess_return_annualized = None
    elif volatility <= 0:
        sharpe = _metric(None, "UNDEFINED", "Zero return volatility")
        sharpe_excess_return_annualized = (statistics.mean(returns) - risk_free_daily) * ANNUAL_SESSIONS
    else:
        sharpe_excess_return_annualized = (statistics.mean(returns) - risk_free_daily) * ANNUAL_SESSIONS
        sharpe = _metric(sharpe_excess_return_annualized / volatility,
                         "ASSUMPTION_BASED", "Uses user-supplied annual risk-free assumption")
    excess_target = [value - target_daily for value in returns]
    downside_daily = math.sqrt(sum(min(0, value) ** 2 for value in excess_target) / len(excess_target))
    downside_deviation_annualized = downside_daily * math.sqrt(ANNUAL_SESSIONS)
    sortino_excess_return_annualized = statistics.mean(excess_target) * ANNUAL_SESSIONS
    if downside_daily <= 0:
        sortino = _metric(None, "UNDEFINED", "No downside observations below target")
    else:
        sortino = _metric(statistics.mean(excess_target) * math.sqrt(ANNUAL_SESSIONS) / downside_daily,
                          "DESCRIPTIVE" if target_annual == 0 else "ASSUMPTION_BASED")
    calmar = _metric(annualized_return / abs(deepest), "DESCRIPTIVE") if deepest < 0 else _metric(None, "UNDEFINED", "No historical drawdown")

    beta_value = None
    if benchmark is not None and len(benchmark) >= 3:
        benchmark_variance = statistics.variance(benchmark)
        if benchmark_variance > 0:
            beta_value = statistics.covariance(returns, benchmark) / benchmark_variance
    beta = _metric(beta_value, "DESCRIPTIVE" if beta_value is not None else "UNAVAILABLE",
                   None if beta_value is not None else "Aligned benchmark with nonzero variance and at least three observations required")
    # CAPM uses arithmetic annual market return minus the effective annual RF.
    # Sharpe retains its separate daily excess-return convention.
    market_return = statistics.mean(benchmark) * ANNUAL_SESSIONS if benchmark else None
    expected_market_return = market_return_assumption_annual if market_return_assumption_annual is not None else market_return
    if market_premium_annual is None and expected_market_return is not None and risk_free_annual is not None:
        market_premium_annual = expected_market_return - risk_free_annual
        assumptions["market_premium_source"] = "ATH_RECOVERY_ASSUMPTION" if market_return_assumption_annual is not None else "ALIGNED_HISTORICAL_BENCHMARK"
    else:
        assumptions["market_premium_source"] = "USER_INPUT" if market_premium_annual is not None else "UNAVAILABLE"
    assumptions["market_premium_annual"] = market_premium_annual
    assumptions["market_return_arithmetic_annual"] = market_return
    assumptions["market_return_expected_annual"] = expected_market_return
    assumptions["market_return_assumption_source"] = (
        "USER_ATH_RECOVERY_PROXY" if market_return_assumption_annual is not None else
        "ALIGNED_HISTORICAL_BENCHMARK" if market_return is not None else "UNAVAILABLE"
    )
    assumptions["market_sample_start"] = dates[0]
    assumptions["market_sample_end"] = dates[-1]
    assumptions["capm_convention"] = ("cumulative ATH upside used directly as Rm proxy in annual CAPM convention; horizon unspecified, not annualized, and not a forecast"
                                       if market_return_assumption_annual is not None
                                       else "252 * mean(market_daily_return) - manual_effective_annual_rf")
    if beta_value is None or risk_free_annual is None or market_premium_annual is None:
        capm_hurdle = _metric(None, "UNAVAILABLE", "CAPM requires beta, annual risk-free assumption, and market-premium assumption")
        capm_alpha = _metric(None, "UNAVAILABLE", "CAPM hurdle unavailable")
    else:
        hurdle = risk_free_annual + beta_value * market_premium_annual
        reason = ("Cumulative ATH upside is used directly as the Rm proxy in the annual CAPM convention; no horizon is specified, so this is a heuristic threshold, not an annualized forecast"
                  if market_return_assumption_annual is not None
                  else "Manual annual risk-free proxy plus beta times annual market premium; historical estimate")
        capm_hurdle = _metric(hurdle, "ASSUMPTION_BASED", reason)
        capm_alpha = _metric(arithmetic_return_annualized - hurdle, "ASSUMPTION_BASED", "Historical arithmetic annual return minus CAPM hurdle")
    return {
        "status": "DESCRIPTIVE", "sample_count": len(returns), "as_of": dates[-1],
        "annualized_return": annualized_return, "cumulative_return": wealth - 1,
        "arithmetic_return_annualized": arithmetic_return_annualized,
        "sharpe_excess_return_annualized": sharpe_excess_return_annualized,
        "sortino_excess_return_annualized": sortino_excess_return_annualized,
        "downside_deviation_annualized": downside_deviation_annualized,
        "volatility": volatility, "sharpe": sharpe, "sortino": sortino, "calmar": calmar,
        "max_drawdown": {"value": deepest, "peak_date": deepest_peak,
                         "trough_date": deepest_trough, "recovery_date": recovery_date},
        "beta": beta, "capm_hurdle": capm_hurdle, "capm_alpha": capm_alpha,
        "path": path, "assumptions": assumptions,
    }
