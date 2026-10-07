"""Temporal separation and bounded scenario-distribution tests."""

import pytest

from idx_evidence_lab.portfolio_scenarios import run_walk_forward, simulate_portfolio_scenarios


DATES = ["2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07",
         "2026-02-02", "2026-02-03", "2026-03-02", "2026-03-03"]
RETURNS = [[0.01, 0.005], [-0.01, 0.008], [0.02, -0.004],
           [0.005, 0.002], [0.003, 0.02], [-0.004, 0.01],
           [0.01, -0.01], [0.005, 0.002]]


def test_walk_forward_applies_prior_window_weights_to_next_session_only():
    result = run_walk_forward(DATES, RETURNS, ["AAA", "BBB"], "hrp", "aggressive", estimation_window=3,
                              constraints={"max_weight": 1.0})
    assert result["status"] == "READY"
    assert result["path"][0]["date"] == "2026-01-07"
    assert result["rebalance_events"][0]["train_end"] == "2026-01-06"
    assert result["rebalance_events"][0]["apply_from"] == "2026-01-07"
    assert result["baseline_path"][0]["date"] == result["path"][0]["date"]
    assert [x["date"] for x in result["path"]] == [x["date"] for x in result["baseline_path"]]
    changed_future = [*RETURNS[:3], *[[0.9, -0.9] for _ in RETURNS[3:]]]
    another = run_walk_forward(DATES, changed_future, ["AAA", "BBB"], "hrp", "aggressive", estimation_window=3,
                               constraints={"max_weight": 1.0})
    assert another["rebalance_events"][0]["weights"] == result["rebalance_events"][0]["weights"]


def test_walk_forward_rebalances_only_at_month_boundaries():
    result = run_walk_forward(DATES, RETURNS, ["AAA", "BBB"], "hrp", "aggressive", estimation_window=3,
                              constraints={"max_weight": 1.0})
    assert [item["apply_from"] for item in result["rebalance_events"]] == [
        "2026-01-07", "2026-02-02", "2026-03-02",
    ]
    assert result["cost_status"] == "GROSS_OF_COSTS"


def test_walk_forward_abstains_without_holdout():
    result = run_walk_forward(DATES[:3], RETURNS[:3], ["AAA", "BBB"], "markowitz", "moderate", estimation_window=3)
    assert result["status"] == "INSUFFICIENT_HISTORY"
    assert result["path"] == []


def test_scenarios_are_seeded_and_return_fan_and_horizon_quantiles():
    arguments = dict(horizons=(2, 3), simulations=30, block_size=2, seed=17)
    first = simulate_portfolio_scenarios(RETURNS, [0.6, 0.4], **arguments)
    second = simulate_portfolio_scenarios(RETURNS, [0.6, 0.4], **arguments)
    assert first == second
    assert first["status"] == "EXPLORATORY"
    assert len(first["fan"]) == 3
    assert set(first["horizons"]) == {"2", "3"}
    assert first["horizons"]["3"]["max_drawdown"]["p50"] <= 0
    assert first["holding_policy"] == "fixed_share_buy_and_hold"
    assert "future_mdd_date" not in first


def test_scenarios_report_first_passage_distribution_not_exact_date():
    result = simulate_portfolio_scenarios(RETURNS, [0.5, 0.5], horizons=(2, 4),
                                          simulations=50, block_size=2, drawdown_threshold=-0.01)
    assert 0 <= result["first_passage"]["probability_by_horizon"]["4"] <= 1
    assert all(isinstance(item, int) for item in result["first_passage"]["hit_session_indices"])
    assert result["first_passage"]["interpretation"] == "distribution_not_date_prediction"


def test_scenarios_enforce_bounds_and_valid_portfolio_weights():
    with pytest.raises(ValueError, match="10,000"):
        simulate_portfolio_scenarios(RETURNS, [0.5, 0.5], simulations=10001)
    with pytest.raises(ValueError, match="weights"):
        simulate_portfolio_scenarios(RETURNS, [0.6, 0.6], simulations=10)


def test_scenario_batching_preserves_seeded_output():
    kwargs = dict(horizons=(20, 60), simulations=80, block_size=5, seed=23,
                  drawdown_threshold=-0.02, risk_free_annual=0.04)
    small = simulate_portfolio_scenarios(RETURNS, [0.5, 0.5], batch_size=7, **kwargs)
    large = simulate_portfolio_scenarios(RETURNS, [0.5, 0.5], batch_size=128, **kwargs)
    assert small == large


def test_scenario_mdd_includes_initial_capital_and_first_session_loss():
    result = simulate_portfolio_scenarios([[-.1]] * 8, [1.0], horizons=(2,), simulations=10)
    for percentile in ('p10', 'p50', 'p90'):
        assert result['horizons']['2']['max_drawdown'][percentile] == pytest.approx(-.19)


def test_scenario_mdd_is_zero_only_when_path_never_falls():
    result = simulate_portfolio_scenarios([[.1]] * 8, [1.0], horizons=(2,), simulations=10)
    for percentile in ('p10', 'p50', 'p90'):
        assert result['horizons']['2']['max_drawdown'][percentile] == 0


def _gbm_sample(sessions=800, seed=1):
    import numpy as np
    generator = np.random.default_rng(seed)
    log_returns = generator.multivariate_normal([0.0003, 0.0003], [[0.0003, 0.0001], [0.0001, 0.0003]], size=sessions)
    return [f"d{i:05d}" for i in range(sessions)], np.expm1(log_returns).tolist()


def test_gbm_forecast_is_bounded_reproducible_and_carries_forecast_metadata():
    from idx_evidence_lab.portfolio_scenarios import forecast_gbm
    dates, returns = _gbm_sample()
    first = forecast_gbm(dates, returns, [0.5, 0.5], (20, 120), 300, 7, 252, -0.1, oos_simulations=200)
    assert first == forecast_gbm(dates, returns, [0.5, 0.5], (20, 120), 300, 7, 252, -0.1, oos_simulations=200)
    for horizon in ("20", "120"):
        mdd = first["horizons"][horizon]["max_drawdown"]
        assert -1 < mdd["p10"] <= mdd["p50"] <= mdd["p90"] <= 0
        meta = mdd["forecast_metadata"]
        assert all(meta[field] for field in ("target", "horizon", "input_cutoff", "method_version", "baseline", "diagnostics", "validation_status"))
        assert meta["input_cutoff"] == dates[-1]
    # 120-session windows overlap heavily on 800 sessions, so they must not pass as predictive.
    assert first["horizons"]["120"]["max_drawdown"]["forecast_metadata"]["validation_status"] == "INSUFFICIENT_OOS_FOLDS"
    assert first["horizons"]["20"]["max_drawdown"]["forecast_metadata"]["diagnostics"]["effective_folds"] >= 10


def test_gbm_oos_folds_only_fit_on_prior_sessions():
    from idx_evidence_lab.portfolio_scenarios import forecast_gbm
    dates, returns = _gbm_sample()
    base = forecast_gbm(dates, returns, [0.5, 0.5], (20,), 50, 3, 252, oos_simulations=100)
    shocked = forecast_gbm(dates, [*returns[:400], *[[-0.2, -0.2]] * 400], [0.5, 0.5], (20,), 50, 3, 252, oos_simulations=100)
    folds, changed = (r["horizons"]["20"]["cumulative_return"]["oos_folds"] for r in (base, shocked))
    # Folds whose window ends before the shock are identical: no future session leaked into fitting or scoring.
    early = [i for i, fold in enumerate(folds) if dates.index(fold["origin"]) + 20 <= 400]
    assert early and all(folds[i] == changed[i] for i in early)


def test_gbm_oos_coverage_is_roughly_nominal_on_true_gbm_data():
    from idx_evidence_lab.portfolio_scenarios import forecast_gbm
    coverage = []
    for seed in range(8):
        dates, returns = _gbm_sample(seed=100 + seed)
        result = forecast_gbm(dates, returns, [0.5, 0.5], (20,), 50, seed, 252, oos_simulations=300)
        coverage.append(result["horizons"]["20"]["cumulative_return"]["forecast_metadata"]["diagnostics"]["coverage"])
    assert 0.65 <= sum(coverage) / len(coverage) <= 0.9
