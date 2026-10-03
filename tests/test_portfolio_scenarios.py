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
