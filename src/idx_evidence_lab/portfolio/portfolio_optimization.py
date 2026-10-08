"""Local, long-only portfolio construction with explicit feasibility states."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import leaves_list, linkage
from scipy.optimize import minimize
from scipy.spatial.distance import squareform

from .portfolio_analytics import diversification_ratio


PROFILE_MULTIPLIERS = {"conservative": 0.75, "moderate": 1.0, "aggressive": 1.25}
METHODS = {"markowitz", "maximum_diversification", "hrp", "integrated"}


def black_litterman_estimates(values: np.ndarray, covariance: np.ndarray,
                             prior_weights: list[float], risk_free_annual: float = 0.0) -> tuple[np.ndarray, dict[str, Any]]:
    """BL with selected-universe capitalization prior and historical absolute views.

    Fixed research assumptions: delta=2.5, tau=1/T, P=I, Q=sample excess
    means, Omega=diag(Sigma)/T. No factor-score-to-return conversion or tuning.
    """
    prior = np.asarray(prior_weights, dtype=float)
    if prior.shape != (values.shape[1],) or not np.isfinite(prior).all() or np.any(prior <= 0):
        raise ValueError("BL prior requires positive finite capitalization for every selected asset")
    prior = prior / prior.sum()
    rf_daily = (1 + risk_free_annual) ** (1 / 252) - 1
    tau = 1 / len(values)
    equilibrium = 2.5 * covariance @ prior
    views = values.mean(axis=0) - rf_daily
    uncertainty = np.diag(np.diag(covariance)) / len(values)
    prior_cov = tau * covariance
    posterior = equilibrium + prior_cov @ np.linalg.solve(prior_cov + uncertainty, views - equilibrium)
    return posterior + rf_daily, {
        "status": "RESEARCH_ESTIMATE", "prior_weights": prior.tolist(),
        "prior_scope": "selected_universe_capitalization_proxy", "delta": 2.5, "tau": tau,
        "views_source": "trailing_sample_absolute_excess_means_P_identity",
        "omega_source": "diagonal_covariance_divided_by_sample_count",
        "equilibrium_excess_daily": equilibrium.tolist(), "views_excess_daily": views.tolist(),
        "posterior_return_daily": (posterior + rf_daily).tolist(),
        "validation": "fixed_assumptions_not_calibrated_or_proven_superior",
    }


def _inputs(returns: list[list[float]], tickers: list[str]) -> np.ndarray:
    if not isinstance(tickers, list) or not tickers or len(set(tickers)) != len(tickers):
        raise ValueError("tickers must be a nonempty unique list")
    try:
        values = np.asarray(returns, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("returns must be finite numbers") from exc
    if values.ndim != 2 or values.shape[1] != len(tickers) or values.shape[0] < 2:
        raise ValueError("returns shape must have at least two rows and one column per ticker")
    if not np.isfinite(values).all() or np.any(values <= -1):
        raise ValueError("returns must be finite and greater than -100%")
    return values


def _moments(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    observed_mean = values.mean(axis=0)
    mean = 0.5 * observed_mean + 0.5 * observed_mean.mean()
    covariance = np.atleast_2d(np.cov(values, rowvar=False, ddof=1))
    covariance = 0.9 * covariance + 0.1 * np.diag(np.diag(covariance))
    covariance = covariance + np.eye(values.shape[1]) * 1e-12
    return mean, covariance


def _portfolio_volatility(weights: np.ndarray, covariance: np.ndarray) -> float:
    return math.sqrt(max(0.0, float(weights @ covariance @ weights))) * math.sqrt(252)


def _constraints(tickers: list[str], constraints: dict[str, Any]) -> tuple[float, dict[str, list[int]], float | None]:
    size = len(tickers)
    if constraints.get("long_only", True) is not True or constraints.get("fully_invested", True) is not True:
        raise ValueError("Only long_only and fully_invested constraints are supported")
    # 1/n would freeze a small selected set at equal weights, defeating the
    # optimizer. This cap permits movement while remaining explicit.
    default_cap = max(0.20, min(1.0, 1.5 / size))
    max_weight = float(constraints.get("max_weight", default_cap))
    if not math.isfinite(max_weight) or not 0 < max_weight <= 1:
        raise ValueError("max_weight must be within (0, 1]")
    sector_cap_raw = constraints.get("sector_cap")
    sector_cap = float(sector_cap_raw) if sector_cap_raw is not None else None
    if sector_cap is not None and (not math.isfinite(sector_cap) or not 0 < sector_cap <= 1):
        raise ValueError("sector_cap must be within (0, 1]")
    sectors = constraints.get("sectors") or {}
    if not isinstance(sectors, dict):
        raise ValueError("sectors must map ticker to current sector label")
    groups: dict[str, list[int]] = {}
    for i, ticker in enumerate(tickers):
        label = sectors.get(ticker)
        if label:
            groups.setdefault(str(label), []).append(i)
    return max_weight, groups, sector_cap


def _failure(method: str, profile: str, status: str, reason: str, *, cap: float | None = None) -> dict[str, Any]:
    return {"method": method, "profile": profile, "status": status, "reason": reason,
            "weights": None, "constraints": {"max_weight": cap} if cap is not None else {},
            "estimated_return_annual": None, "estimated_volatility_annual": None,
            "diversification_ratio": None, "profile_risk_cap_annual": None,
            "risk_to_reference_ratio": None, "diagnostics": {}}


def _hrp_weights(values: np.ndarray, covariance: np.ndarray) -> tuple[np.ndarray, list[int]]:
    size = values.shape[1]
    if size == 1:
        return np.array([1.0]), [0]
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.corrcoef(values, rowvar=False)
    corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
    np.fill_diagonal(corr, 1.0)
    distance = np.sqrt(np.maximum(0.0, (1 - np.clip(corr, -1, 1)) / 2))
    tree = linkage(squareform(distance, checks=False), method="single", optimal_ordering=True)
    order = list(map(int, leaves_list(tree)))
    weights = np.ones(size)
    clusters = [order]
    while clusters:
        cluster = clusters.pop(0)
        if len(cluster) <= 1:
            continue
        split = len(cluster) // 2
        left, right = cluster[:split], cluster[split:]

        def cluster_variance(indices: list[int]) -> float:
            sub = covariance[np.ix_(indices, indices)]
            inverse = 1 / np.maximum(np.diag(sub), 1e-12)
            inverse /= inverse.sum()
            return float(inverse @ sub @ inverse)

        variance_left = cluster_variance(left)
        variance_right = cluster_variance(right)
        share_left = variance_right / (variance_left + variance_right) if variance_left + variance_right > 0 else 0.5
        weights[left] *= share_left
        weights[right] *= 1 - share_left
        clusters.extend([left, right])
    return weights / weights.sum(), order


def equal_weight_portfolio(returns: list[list[float]], tickers: list[str]) -> dict[str, Any]:
    values = _inputs(returns, tickers)
    mean, covariance = _moments(values)
    weights = np.full(len(tickers), 1 / len(tickers))
    return {
        "method": "equal_weight", "status": "BASELINE",
        "weights": dict(zip(tickers, map(float, weights))),
        "estimated_return_annual": float(weights @ mean) * 252,
        "estimated_volatility_annual": _portfolio_volatility(weights, covariance),
        "diversification_ratio": diversification_ratio(weights.tolist(), covariance.tolist()),
    }


def optimize_portfolio(
    returns: list[list[float]], tickers: list[str], method: str, profile: str,
    constraints: dict[str, Any], risk_free_annual: float | None = None,
) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError("Unsupported method")
    if profile not in PROFILE_MULTIPLIERS:
        raise ValueError("Unsupported profile")
    values = _inputs(returns, tickers)
    if not isinstance(constraints, dict):
        raise ValueError("constraints must be an object")
    max_weight, groups, sector_cap = _constraints(tickers, constraints)
    size = len(tickers)
    if size * max_weight < 1 - 1e-9:
        return _failure(method, profile, "INFEASIBLE", "max_weight cannot hold 100% across selected stocks", cap=max_weight)
    if sector_cap is not None and groups:
        if sum(min(sector_cap, len(indices) * max_weight) for indices in groups.values()) + (size - sum(len(g) for g in groups.values())) * max_weight < 1 - 1e-9:
            return _failure(method, profile, "INFEASIBLE", "sector_cap and max_weight cannot hold 100%", cap=max_weight)
    mean, covariance = _moments(values)
    equal = np.full(size, 1 / size)
    reference_risk = _portfolio_volatility(equal, covariance)
    multiplier = float(constraints.get("profile_multiplier", PROFILE_MULTIPLIERS[profile]))
    if not math.isfinite(multiplier) or multiplier <= 0:
        raise ValueError("profile_multiplier must be positive")
    risk_cap = reference_risk * multiplier
    bounds = [(0.0, max_weight) for _ in tickers]
    scipy_constraints: list[dict[str, Any]] = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    if sector_cap is not None:
        for indices in groups.values():
            scipy_constraints.append({"type": "ineq", "fun": lambda w, group=indices: sector_cap - np.sum(w[group])})

    def feasible(w: np.ndarray, *, check_risk: bool = False) -> bool:
        return (np.isfinite(w).all() and abs(float(w.sum()) - 1) <= 1e-6
                and np.min(w) >= -1e-7 and np.max(w) <= max_weight + 1e-6
                and (sector_cap is None or all(float(w[group].sum()) <= sector_cap + 1e-6 for group in groups.values()))
                and (not check_risk or _portfolio_volatility(w, covariance) <= risk_cap + 1e-6))

    def solve(objective, extra_constraints=None, starting=None):
        return minimize(objective, equal if starting is None else starting, method="SLSQP", bounds=bounds,
                        constraints=scipy_constraints + (extra_constraints or []),
                        options={"maxiter": 600, "ftol": 1e-9})

    diagnostics: dict[str, Any] = {"mean_shrinkage": 0.5, "covariance_diagonal_shrinkage": 0.1}
    if method == "integrated":
        risk_free_annual = constraints.get("risk_free_annual")
        prior_weights = constraints.get("prior_weights")
        if prior_weights is None:
            return _failure(method, profile, "UNAVAILABLE", "Verified capitalization prior is required", cap=max_weight)
        mean, bl = black_litterman_estimates(values, covariance, prior_weights,
                                             float(risk_free_annual or 0.0))
        bl["risk_free_policy"] = "manual_constant_proxy" if risk_free_annual is not None else "zero_rate_research_assumption"
        diagnostics["black_litterman"] = bl
    if size == 1:
        weights = np.array([1.0])
        diagnostics["solver"] = "closed_form_single_asset"
    elif method == "hrp":
        weights, order = _hrp_weights(values, covariance)
        diagnostics["cluster_order"] = [tickers[i] for i in order]
        diagnostics["solver"] = "hierarchical_recursive_bisection"
    elif method == "maximum_diversification":
        asset_vol = np.sqrt(np.diag(covariance))
        def objective(w):
            variance = float(w @ covariance @ w)
            return -float(w @ asset_vol) / math.sqrt(max(variance, 1e-15))
        candidate = solve(objective)
        if not candidate.success or not feasible(candidate.x):
            return _failure(method, profile, "FAILED", "Maximum-diversification solver did not converge to valid weights", cap=max_weight)
        weights = candidate.x
        diagnostics["solver"] = "SLSQP"
    else:
        min_variance = solve(lambda w: float(w @ covariance @ w) * 1e4)
        if not min_variance.success or not feasible(min_variance.x):
            return _failure(method, profile, "INFEASIBLE", "No feasible long-only minimum-variance allocation", cap=max_weight)
        minimum_risk = _portfolio_volatility(min_variance.x, covariance)
        if minimum_risk > risk_cap + 1e-6:
            return _failure(method, profile, "INFEASIBLE", "Profile risk cap below minimum feasible volatility", cap=max_weight)
        risk_constraint = {"type": "ineq", "fun": lambda w: 1 - 252 * float(w @ covariance @ w) / max(risk_cap ** 2, 1e-12),
                           "jac": lambda w: -504 * (covariance @ w) / max(risk_cap ** 2, 1e-12)}
        extra = [risk_constraint]
        if method == "integrated":
            asset_vol = np.sqrt(np.diag(covariance))
            dr = lambda w: float(w @ asset_vol) / math.sqrt(max(float(w @ covariance @ w), 1e-15))
            maxdiv = solve(lambda w: -dr(w), extra_constraints=extra, starting=min_variance.x)
            if not maxdiv.success or not feasible(maxdiv.x, check_risk=True):
                return _failure(method, profile, "FAILED", "Profile-constrained diversification solver failed", cap=max_weight)
            # Fixed fraction of feasible diversification improvement over min-var.
            fraction = {"conservative": 0.75, "moderate": 0.5, "aggressive": 0.25}[profile]
            floor = dr(min_variance.x) + fraction * max(0.0, dr(maxdiv.x) - dr(min_variance.x))
            extra.append({"type": "ineq", "fun": lambda w: dr(w) - floor + 1e-7})
            diagnostics["diversification"] = {"floor": floor, "maximum_feasible": dr(maxdiv.x),
                "minimum_variance_reference": dr(min_variance.x), "improvement_fraction": fraction,
                "policy_status": "FIXED_RESEARCH_POLICY_NOT_CALIBRATED"}
            start = maxdiv.x
        else:
            start = min_variance.x
        if profile == "conservative":
            if method == "integrated":
                candidate = solve(lambda w: float(w @ covariance @ w) * 1e4, extra_constraints=extra, starting=start)
                if not candidate.success or not feasible(candidate.x, check_risk=True):
                    return _failure(method, profile, "FAILED", "Integrated minimum-variance solver failed", cap=max_weight)
                weights = candidate.x
            else:
                weights = min_variance.x
        else:
            risk_constraint = {"type": "ineq", "fun": lambda w: 1 - 252 * float(w @ covariance @ w) / max(risk_cap ** 2, 1e-12),
                               "jac": lambda w: -504 * (covariance @ w) / max(risk_cap ** 2, 1e-12)}
            candidate = solve(lambda w: -float(w @ mean) * 1e3,
                              extra_constraints=extra, starting=start)
            if not candidate.success or not feasible(candidate.x, check_risk=True):
                return _failure(method, profile, "FAILED", "Markowitz solver did not converge within the profile risk budget", cap=max_weight)
            weights = candidate.x
        if method == "integrated" and dr(weights) < floor - 1e-5:
            return _failure(method, profile, "FAILED", "Diversification floor violated", cap=max_weight)
        diagnostics["solver"] = "SLSQP"
        diagnostics["minimum_feasible_volatility_annual"] = minimum_risk

    if not feasible(weights):
        return _failure(method, profile, "INFEASIBLE", "Method-native weights violate a hard position/sector constraint", cap=max_weight)
    volatility = _portfolio_volatility(weights, covariance)
    ratio = diversification_ratio(weights.tolist(), covariance.tolist())
    outside = volatility > risk_cap + 1e-6 and method in {"hrp", "maximum_diversification"}
    return {
        "method": method, "profile": profile,
        "status": "OUTSIDE_PROFILE_BUDGET" if outside else "READY",
        "reason": "Method-native allocation exceeds selected profile risk budget" if outside else None,
        "weights": dict(zip(tickers, map(float, weights))),
        "constraints": {"max_weight": max_weight, "sector_cap": sector_cap,
                        "long_only": True, "fully_invested": True},
        "estimated_return_annual": float(weights @ mean) * 252,
        "estimated_volatility_annual": volatility,
        "diversification_ratio": ratio,
        "profile_risk_cap_annual": risk_cap,
        "risk_to_reference_ratio": volatility / reference_risk if reference_risk > 0 else None,
        "equal_weight_reference_volatility_annual": reference_risk,
        "diagnostics": diagnostics,
        "risk_free_assumption_annual": risk_free_annual,
        "estimate_status": "IN_SAMPLE_ESTIMATE",
    }
