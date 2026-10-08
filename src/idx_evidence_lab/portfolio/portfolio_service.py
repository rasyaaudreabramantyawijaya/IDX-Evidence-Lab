"""Portfolio request validation and the analysis pipeline behind /api/portfolio-analysis."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ..core.paths import ROOT
from ..market.market_data import load_ihsg_snapshot, load_issuer_daily, load_lq45_universe
from .portfolio_amounts import allocate_amounts, allocate_lots
from .portfolio_analytics import calculate_portfolio_metrics
from .portfolio_data import _current_classifications, load_portfolio_inputs
from .portfolio_optimization import equal_weight_portfolio, optimize_portfolio
from .portfolio_scenarios import forecast_gbm, run_walk_forward, simulate_portfolio_scenarios


class PortfolioUnavailable(ValueError):
    """A valid portfolio request lacks trustworthy local calculation inputs."""


def portfolio_data_catalog(root: Path = ROOT) -> dict[str, Any]:
    universe = load_lq45_universe(root)
    tickers_in_universe = [item["ticker"] for item in universe.get("symbols", [])]
    _, sub_sectors, _, _ = _current_classifications(root, tickers_in_universe)
    tickers = []
    for item in universe.get("symbols", []):
        daily = load_issuer_daily(root, item["ticker"])
        tickers.append({"ticker": item["ticker"], "company": item["company"],
                        "sub_sector": sub_sectors.get(item["ticker"]),
                        "daily_quality": daily["data_quality"], "observations": daily["observation_count"],
                        "coverage_start": daily["coverage_start"], "coverage_end": daily["coverage_end"]})
    return {
        "status": "AVAILABLE_WITH_CAVEAT" if universe["data_quality"] == "PARTIAL" else universe["data_quality"],
        "provider": "Sectors.app", "tickers": tickers, "benchmarks": ["IHSG", "LQ45"],
        "universe_quality": universe["data_quality"], "universe_issues": universe["issues"],
        "universe_as_of": universe.get("retrieved_at"),
        "risk_free_rate": {"status": "UNAVAILABLE", "reason": "No approved local Indonesian risk-free series; user annual assumption only"},
        "factors": {
            "momentum": {"status": "PARTIAL", "reason": "Price-based characteristic only; corporate actions unverified"},
            "size": {"status": "PARTIAL", "reason": "Daily market cap exists, but point-in-time factor portfolio not validated"},
            "value": {"status": "UNAVAILABLE", "reason": "Book equity publication availability not audited"},
            "quality": {"status": "UNAVAILABLE", "reason": "Profitability availability and sector comparability not audited"},
            "apt": {"status": "UNAVAILABLE", "reason": "No validated multiple factor returns and premia"},
            "black_litterman": {"status": "RESEARCH_SUPPORTED", "reason": "Selected-universe capitalization prior and historical sample views; requires valid selected caps; parameters not calibrated"},
        },
    }


def _portfolio_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Portfolio request must be a JSON object")
    allowed = {"tickers", "benchmark", "profile", "method", "lookback", "constraints", "total_capital",
               "risk_free_annual", "market_premium_annual", "scenarios"}
    if set(payload) - allowed:
        raise ValueError("Unknown portfolio request fields")
    tickers = payload.get("tickers")
    if not isinstance(tickers, list) or not 1 <= len(tickers) <= 45 or any(not isinstance(t, str) or not t.isalnum() or len(t) > 10 for t in tickers):
        raise ValueError("Select 1–45 valid LQ45 ticker symbols")
    if len({t.upper() for t in tickers}) != len(tickers):
        raise ValueError("Duplicate tickers are not allowed")
    benchmark = payload.get("benchmark", "IHSG")
    profile = payload.get("profile")
    method = payload.get("method")
    lookback = payload.get("lookback", 252)
    if benchmark not in {"IHSG", "LQ45"}:
        raise ValueError("Unsupported benchmark")
    if profile not in {"conservative", "moderate", "aggressive"}:
        raise ValueError("Unsupported profile")
    if method not in {"markowitz", "maximum_diversification", "hrp", "integrated"}:
        raise ValueError("Unsupported method")
    if lookback not in (126, 252, 504, "all") or isinstance(lookback, bool):
        raise ValueError("lookback must be 126, 252, 504, or all")
    constraints = payload.get("constraints", {})
    if not isinstance(constraints, dict) or set(constraints) - {"max_weight", "sector_cap", "profile_multiplier"}:
        raise ValueError("Unsupported constraints")
    for key, value in constraints.items():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 < value <= 1.5:
            raise ValueError(f"Invalid {key}")
    scenarios = payload.get("scenarios", {})
    if not isinstance(scenarios, dict) or set(scenarios) - {"horizons", "simulations", "block_size", "seed", "drawdown_threshold"}:
        raise ValueError("Unsupported scenarios")
    horizons = scenarios.get("horizons", [20, 60, 120])
    simulations = scenarios.get("simulations", 2000)
    block_size = scenarios.get("block_size", 5)
    seed = scenarios.get("seed", 42)
    if (not isinstance(horizons, list) or not horizons or len(horizons) > 3
            or any(type(h) is not int or h < 2 or h > 252 for h in horizons)):
        raise ValueError("Scenario horizons must be 2–252 sessions")
    if type(simulations) is not int or not 1 <= simulations <= 10_000:
        raise ValueError("Scenario simulations must be 1–10,000")
    if type(block_size) is not int or not 1 <= block_size <= 20:
        raise ValueError("Scenario block_size must be 1–20")
    if type(seed) is not int or not 0 <= seed <= 2 ** 32 - 1:
        raise ValueError("Scenario seed must be a nonnegative 32-bit integer")
    for key in ("risk_free_annual", "market_premium_annual"):
        value = payload.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not -0.99 < value < 5):
            raise ValueError(f"Invalid {key} assumption")
    total_capital = payload.get("total_capital")
    if total_capital is not None and (isinstance(total_capital, bool) or not isinstance(total_capital, (int, float))
                                      or not math.isfinite(float(total_capital))
                                      or total_capital <= 0 or total_capital > 10**15):
        raise ValueError("total_capital must be a positive finite amount no greater than 1e15")
    threshold = scenarios.get("drawdown_threshold")
    if threshold is not None and (isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not -1 < threshold < 0):
        raise ValueError("drawdown_threshold must be a negative fraction")
    return {**payload, "tickers": [t.upper() for t in tickers], "benchmark": benchmark,
            "profile": profile, "method": method, "lookback": lookback,
            "constraints": constraints, "scenarios": {"horizons": horizons, "simulations": simulations,
                                             "block_size": block_size, "seed": seed,
                                             "drawdown_threshold": threshold}}


def build_portfolio_analysis(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    try:
        inputs = load_portfolio_inputs(root, request["tickers"], request["benchmark"])
    except ValueError as exc:
        if "universe snapshot is unavailable" in str(exc):
            raise PortfolioUnavailable(str(exc)) from exc
        raise
    if inputs["status"] != "READY":
        raise PortfolioUnavailable(f"Portfolio inputs: {inputs['status']}; {', '.join(inputs['issues'][:3])}")
    total = len(inputs["return_dates"])
    lookback = total if request["lookback"] == "all" else request["lookback"]
    if total < lookback:
        raise PortfolioUnavailable(f"Only {total} common eligible return sessions; requested {lookback}")
    window_returns = inputs["return_matrix"][-lookback:]
    window_dates = inputs["return_dates"][-lookback:]
    constraints = {**request["constraints"], "sectors": inputs["sectors"]}
    caps_by_date = dict(zip(inputs["dates"], inputs["market_cap_matrix"]))
    if request["method"] == "integrated":
        caps = caps_by_date.get(window_dates[-1])
        if not caps or any(v is None or not math.isfinite(v) or v <= 0 for v in caps):
            raise PortfolioUnavailable("Verified capitalization required for Black–Litterman prior")
        constraints.update(prior_weights=caps, risk_free_annual=request.get("risk_free_annual"))
    if constraints.get("sector_cap") is not None and any(value is None for value in inputs["sectors"].values()):
        raise PortfolioUnavailable("Sector cap requires verified sector labels for every selected ticker")
    baseline = equal_weight_portfolio(window_returns, inputs["tickers"])
    methods = {method: optimize_portfolio(window_returns, inputs["tickers"], method,
                                           request["profile"], constraints)
               for method in ("markowitz", "maximum_diversification", "hrp")}
    if request["method"] == "integrated":
        methods["integrated"] = optimize_portfolio(window_returns, inputs["tickers"], "integrated",
                                                  request["profile"], constraints)
    allocation = methods[request["method"]]
    if allocation["weights"] is None:
        raise PortfolioUnavailable(f"{request['method']}: {allocation['reason']}")
    weights = [allocation["weights"][ticker] for ticker in inputs["tickers"]]
    benchmark_returns = [inputs["benchmark_returns"][day] for day in window_dates]
    market = load_ihsg_snapshot(root) if request["benchmark"] == "IHSG" else None
    ath_recovery = None
    if market and market.get("data_quality") == "VERIFIED" and market.get("latest_price"):
        ath_recovery = 9174.0 / float(market["latest_price"]) - 1
    method_metrics = {}
    equal_weights = [baseline["weights"][ticker] for ticker in inputs["tickers"]]
    equal_returns = [sum(weight * value for weight, value in zip(equal_weights, row))
                     for row in window_returns]
    method_metrics["equal_weight"] = calculate_portfolio_metrics(
        window_dates, equal_returns, benchmark_returns,
        request.get("risk_free_annual"), request.get("market_premium_annual"),
        market_return_assumption_annual=ath_recovery,
    )
    for method, candidate in methods.items():
        if candidate["weights"] is None:
            method_metrics[method] = None
            continue
        candidate_weights = [candidate["weights"][ticker] for ticker in inputs["tickers"]]
        candidate_returns = [sum(weight * value for weight, value in zip(candidate_weights, row))
                             for row in window_returns]
        method_metrics[method] = calculate_portfolio_metrics(
            window_dates, candidate_returns, benchmark_returns,
            request.get("risk_free_annual"), request.get("market_premium_annual"),
            market_return_assumption_annual=ath_recovery,
        )
    metrics = method_metrics[request["method"]]
    historical_portfolio_returns = [
        sum(allocation["weights"][ticker] * value for ticker, value in zip(inputs["tickers"], row))
        for row in window_returns
    ]
    historical_metrics = calculate_portfolio_metrics(
        window_dates, historical_portfolio_returns, benchmark_returns,
        request.get("risk_free_annual"),
    )
    historical_capm = {
        "beta": historical_metrics["beta"],
        "capm_hurdle": historical_metrics["capm_hurdle"],
        "capm_alpha": historical_metrics["capm_alpha"],
        "risk_free_annual": historical_metrics["assumptions"]["risk_free_annual"],
        "market_return_arithmetic_annual": historical_metrics["assumptions"]["market_return_arithmetic_annual"],
        "market_premium_annual": historical_metrics["assumptions"]["market_premium_annual"],
        "sample_start": window_dates[0], "sample_end": window_dates[-1],
        "sample_count": len(window_dates), "benchmark": request["benchmark"],
        "source": "ALIGNED_HISTORICAL_BENCHMARK",
    }
    market_history = None
    if market and market["data_quality"] == "VERIFIED":
        series = market["series"]
        market_returns = [b["price"] / a["price"] - 1 for a, b in zip(series, series[1:])]
        market_history = calculate_portfolio_metrics([row["date"] for row in series[1:]], market_returns)
        market_history["coverage_start"] = market["coverage_start"]
        market_history["coverage_end"] = market["coverage_end"]
        market_history["all_time_high"] = 9174.0
        market_history["latest_index_level"] = market["latest_price"]
        market_history["ath_recovery_return"] = ath_recovery
        market_history["ath_recovery_as_of"] = market.get("as_of") or market.get("coverage_end")
        market_history["purpose"] = "ATH-recovery scenario input for CAPM; not an official target forecast"
    walk_forward = run_walk_forward(inputs["return_dates"], inputs["return_matrix"],
                                    inputs["tickers"], request["method"], request["profile"],
                                    estimation_window=min(252, lookback), constraints=constraints,
                                    capitalization_by_date=caps_by_date)
    scenario_config = request["scenarios"]
    scenarios = simulate_portfolio_scenarios(
        window_returns, weights, horizons=tuple(scenario_config["horizons"]),
        simulations=scenario_config["simulations"], block_size=scenario_config["block_size"],
        seed=scenario_config["seed"], drawdown_threshold=scenario_config["drawdown_threshold"],
        risk_free_annual=request.get("risk_free_annual"),
    )
    # Uses the full common history so the OOS check has folds before the selected lookback; only prior sessions fit each fold.
    forecast = forecast_gbm(
        inputs["return_dates"], inputs["return_matrix"], weights, horizons=tuple(scenario_config["horizons"]),
        simulations=scenario_config["simulations"], seed=scenario_config["seed"],
        estimation_window=min(252, lookback), drawdown_threshold=scenario_config["drawdown_threshold"],
    )
    return {
        "status": "READY", "calculation_state": "PROVISIONAL_PRICE_RETURNS",
        "selection": {"tickers": inputs["tickers"], "profile": request["profile"],
                      "method": request["method"], "benchmark": inputs["benchmark"],
                      "lookback": lookback, "sample_start": window_dates[0], "sample_end": window_dates[-1]},
        "allocation": allocation, "methods": methods, "method_metrics": method_metrics,
        "equal_weight": baseline,
        "metrics": metrics, "metrics_scope": "IN_SAMPLE_STATIC_TARGET_WEIGHTS_DAILY_REBALANCED",
        "historical_capm": historical_capm,
        "market_history": market_history,
        "walk_forward": walk_forward, "scenarios": scenarios, "forecast": forecast,
        "total_capital": request.get("total_capital"),
        "lot_allocation": allocate_lots(allocation["weights"], request["total_capital"],
            dict(zip(inputs["tickers"], inputs["close_matrix"][inputs["dates"].index(window_dates[-1])]))
        ) if request.get("total_capital") is not None else None,
        "capitalization_prior_as_of": window_dates[-1] if request["method"] == "integrated" else None,
        "amounts": allocate_amounts(allocation["weights"], request["total_capital"])["amounts"]
                   if request.get("total_capital") is not None else None,
        "sectors": inputs["sectors"], "sub_sectors": inputs["sub_sectors"], "coverage": inputs["coverage"],
        "factor_readiness": {**inputs["field_status"],
            "black_litterman": "RESEARCH_ESTIMATE" if request["method"] == "integrated" else "NOT_USED"},
        "provenance": {"provider": inputs["provider"], "universe": inputs["universe"],
                       "sources": inputs["sources"], "issues": inputs["issues"],
                       "universe_limitation": inputs["universe_limitation"],
                       "adjustment_policy": inputs["adjustment_policy"]},
    }
