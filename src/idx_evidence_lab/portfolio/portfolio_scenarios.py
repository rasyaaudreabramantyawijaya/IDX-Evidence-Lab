"""Timestamp-safe walk-forward replay and exploratory block-bootstrap paths."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .portfolio_analytics import calculate_portfolio_metrics
from .portfolio_optimization import optimize_portfolio


def _validate_matrix(dates: list[str] | None, returns: list[list[float]], size: int) -> np.ndarray:
    try:
        values = np.asarray(returns, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("returns must be finite") from exc
    if values.ndim != 2 or values.shape[1] != size or values.shape[0] < 2:
        raise ValueError("returns must have at least two rows and one column per asset")
    if not np.isfinite(values).all() or np.any(values <= -1):
        raise ValueError("returns must be finite and greater than -100%")
    if dates is not None and (len(dates) != len(values) or dates != sorted(set(dates))):
        raise ValueError("dates must be aligned, sorted and unique")
    return values


def run_walk_forward(
    dates: list[str], returns: list[list[float]], tickers: list[str], method: str, profile: str,
    estimation_window: int = 252, rebalance_frequency: str = "monthly",
    constraints: dict[str, Any] | None = None,
    capitalization_by_date: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Fit on trailing data through t-1, then hold from t; gross of costs."""
    values = _validate_matrix(dates, returns, len(tickers))
    if not isinstance(estimation_window, int) or estimation_window < 2:
        raise ValueError("estimation_window must be at least two sessions")
    if rebalance_frequency != "monthly":
        raise ValueError("Only monthly rebalance_frequency is supported")
    empty = {
        "path": [], "baseline_path": [], "rebalance_events": [],
        "metrics": None, "baseline_metrics": None, "cost_status": "GROSS_OF_COSTS",
        "evaluation_type": "OUT_OF_SAMPLE_WALK_FORWARD",
        "policy": "monthly_rebalance_close_to_close; weights estimated from prior sessions only",
    }
    if len(values) <= estimation_window:
        return {**empty, "status": "INSUFFICIENT_HISTORY", "reason": "No holdout session after estimation window"}

    portfolio_wealth = 1.0
    baseline_asset_wealth = np.ones(len(tickers))
    weights = None
    path = []
    baseline_path = []
    events = []
    previous_month = None
    out_returns: list[float] = []
    baseline_returns: list[float] = []
    for position in range(estimation_window, len(values)):
        day = dates[position]
        month = day[:7]
        if weights is None or month != previous_month:
            training = values[position - estimation_window:position]
            fold_constraints = dict(constraints or {})
            if method == "integrated":
                # A current capitalization must never leak into an earlier fold.
                fold_constraints["prior_weights"] = (capitalization_by_date or {}).get(dates[position - 1])
            allocation = optimize_portfolio(training.tolist(), tickers, method, profile, fold_constraints)
            if allocation["status"] not in {"READY", "OUTSIDE_PROFILE_BUDGET"}:
                return {**empty, "status": allocation["status"], "reason": allocation["reason"],
                        "failed_at": day, "test_sessions_attempted": len(path)}
            weights = np.array([allocation["weights"][ticker] for ticker in tickers], dtype=float)
            previous_month = month
            events.append({"apply_from": day, "train_start": dates[position - estimation_window],
                           "train_end": dates[position - 1], "weights": allocation["weights"],
                           "allocation_status": allocation["status"]})
        daily_asset_returns = values[position]
        strategy_return = float(weights @ daily_asset_returns)
        portfolio_wealth *= 1 + strategy_return
        weights = weights * (1 + daily_asset_returns) / (1 + strategy_return)
        baseline_before = float(baseline_asset_wealth.mean())
        baseline_asset_wealth *= 1 + daily_asset_returns
        baseline_after = float(baseline_asset_wealth.mean())
        baseline_return = baseline_after / baseline_before - 1
        path.append({"date": day, "return": strategy_return, "wealth": portfolio_wealth})
        baseline_path.append({"date": day, "return": baseline_return, "wealth": baseline_after})
        out_returns.append(strategy_return)
        baseline_returns.append(baseline_return)
    holdout_dates = dates[estimation_window:]
    return {
        **empty, "status": "READY", "reason": None, "path": path,
        "baseline_path": baseline_path, "rebalance_events": events,
        "metrics": calculate_portfolio_metrics(holdout_dates, out_returns),
        "baseline_metrics": calculate_portfolio_metrics(holdout_dates, baseline_returns),
        "holdout_sessions": len(holdout_dates), "estimation_window": estimation_window,
        "baseline_method": "equal_weight_fixed_share_buy_and_hold",
    }


def _quantiles(values: np.ndarray, *, status: str = "EXPLORATORY") -> dict[str, Any]:
    finite = values[np.isfinite(values)]
    if len(finite) == 0:
        return {"status": "UNDEFINED", "p10": None, "p50": None, "p90": None, "valid_paths": 0}
    p10, p50, p90 = np.quantile(finite, [0.1, 0.5, 0.9])
    return {"status": status, "p10": float(p10), "p50": float(p50),
            "p90": float(p90), "valid_paths": int(len(finite))}


def simulate_portfolio_scenarios(
    returns: list[list[float]], weights: list[float], horizons: tuple[int, ...] = (20, 60, 120),
    simulations: int = 2000, block_size: int = 5, seed: int = 42,
    drawdown_threshold: float | None = None, risk_free_annual: float | None = None,
    *, batch_size: int = 256,
) -> dict[str, Any]:
    """Resample joint asset-return blocks, then let initial shares drift."""
    values = _validate_matrix(None, returns, len(weights))
    weights_array = np.asarray(weights, dtype=float)
    if not np.isfinite(weights_array).all() or np.any(weights_array < 0) or abs(float(weights_array.sum()) - 1) > 1e-8:
        raise ValueError("weights must be nonnegative and sum to 1")
    if not isinstance(simulations, int) or not 1 <= simulations <= 10000:
        raise ValueError("simulations must be between 1 and 10,000")
    if not isinstance(batch_size, int) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer")
    if not isinstance(block_size, int) or not 1 <= block_size <= len(values):
        raise ValueError("block_size must fit the observed sample")
    if not isinstance(horizons, (tuple, list)) or not horizons or any(not isinstance(h, int) or h < 2 or h > 252 for h in horizons):
        raise ValueError("horizons must contain 2–252 session lengths")
    if drawdown_threshold is not None and (not -1 < drawdown_threshold < 0):
        raise ValueError("drawdown_threshold must be a negative fraction above -1")
    if risk_free_annual is not None and (not math.isfinite(risk_free_annual) or risk_free_annual <= -1):
        raise ValueError("risk_free_annual must be finite and greater than -100%")

    max_horizon = max(horizons)
    generator = np.random.default_rng(seed)
    blocks = math.ceil(max_horizon / block_size)
    starts = generator.integers(0, len(values), size=(simulations, blocks, 1))
    portfolio_wealth = np.empty((simulations, max_horizon), dtype=float)
    portfolio_returns = np.empty_like(portfolio_wealth)
    drawdowns = np.empty_like(portfolio_wealth)
    block_offsets = np.arange(block_size).reshape(1, 1, -1)
    for first in range(0, simulations, batch_size):
        last = min(first + batch_size, simulations)
        sample_indices = (starts[first:last] + block_offsets) % len(values)
        sample_indices = sample_indices.reshape(last - first, -1)[:, :max_horizon]
        sampled_returns = values[sample_indices]
        asset_wealth = np.cumprod(1 + sampled_returns, axis=1)
        wealth = asset_wealth @ weights_array
        portfolio_wealth[first:last] = wealth
        previous = np.concatenate((np.ones((last - first, 1)), wealth[:, :-1]), axis=1)
        portfolio_returns[first:last] = wealth / previous - 1
        running_peak = np.maximum.accumulate(
            np.concatenate((np.ones((last - first, 1)), wealth), axis=1), axis=1,
        )[:, 1:]
        drawdowns[first:last] = wealth / running_peak - 1
    fan = [{"session": i + 1, **{key: value for key, value in _quantiles(portfolio_wealth[:, i] - 1).items()
                                    if key in {"p10", "p50", "p90"}}} for i in range(max_horizon)]
    rf_daily = (1 + risk_free_annual) ** (1 / 252) - 1 if risk_free_annual is not None else None
    by_horizon: dict[str, Any] = {}
    for horizon in sorted(set(horizons)):
        sample = portfolio_returns[:, :horizon]
        annual_cagr = portfolio_wealth[:, horizon - 1] ** (252 / horizon) - 1
        downside = np.sqrt(np.mean(np.minimum(sample, 0) ** 2, axis=1)) * math.sqrt(252)
        sortino = np.divide(sample.mean(axis=1) * 252, downside,
                            out=np.full(simulations, np.nan), where=downside > 0)
        maximum_drawdown = np.min(drawdowns[:, :horizon], axis=1)
        calmar = np.divide(annual_cagr, np.abs(maximum_drawdown),
                           out=np.full(simulations, np.nan), where=maximum_drawdown < 0)
        if rf_daily is not None:
            volatility = sample.std(axis=1, ddof=1) * math.sqrt(252)
            sharpe = np.divide((sample.mean(axis=1) - rf_daily) * 252, volatility,
                               out=np.full(simulations, np.nan), where=volatility > 0)
            sharpe_quantiles = _quantiles(sharpe, status="ASSUMPTION_BASED_EXPLORATORY")
        else:
            sharpe_quantiles = {"status": "UNAVAILABLE", "reason": "No observed risk-free input or explicit assumption",
                                "p10": None, "p50": None, "p90": None, "valid_paths": 0}
        by_horizon[str(horizon)] = {
            "cumulative_return": _quantiles(portfolio_wealth[:, horizon - 1] - 1),
            "annualized_return": _quantiles(annual_cagr),
            "sharpe": sharpe_quantiles, "sortino": _quantiles(sortino),
            "calmar": _quantiles(calmar), "max_drawdown": _quantiles(maximum_drawdown),
        }
    first_passage = None
    if drawdown_threshold is not None:
        hits = drawdowns <= drawdown_threshold
        first_indices = np.where(hits.any(axis=1), hits.argmax(axis=1) + 1, 0)
        first_passage = {
            "threshold": drawdown_threshold,
            "probability_by_horizon": {str(h): float(np.mean((first_indices > 0) & (first_indices <= h)))
                                       for h in sorted(set(horizons))},
            "hit_session_indices": [int(index) for index in first_indices if index > 0],
            "interpretation": "distribution_not_date_prediction",
        }
    return {
        "status": "EXPLORATORY", "method": "multivariate_circular_block_bootstrap",
        "holding_policy": "fixed_share_buy_and_hold", "cost_status": "GROSS_OF_COSTS",
        "sample_sessions": int(len(values)), "simulations": simulations, "block_size": block_size,
        "seed": seed, "horizons": by_horizon, "fan": fan, "first_passage": first_passage,
        "assumptions": {"risk_free_annual": risk_free_annual, "annualization_sessions": 252},
        "limitation": "Historical joint return blocks; not a calibrated prediction or exact future drawdown date.",
    }
