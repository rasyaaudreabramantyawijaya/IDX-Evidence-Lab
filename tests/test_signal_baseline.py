"""Causal timing, aligned benchmark, and cost checks for the fixed rule."""
from datetime import date, timedelta
import copy
import math

from idx_evidence_lab.signal_baseline import build_signal_baseline


def snapshot(prices):
    return {"ok": True, "data_quality": "VERIFIED", "series": [
        {"date": (date(2024, 1, 1) + timedelta(days=i)).isoformat(), "price": value}
        for i, value in enumerate(prices)]}


def test_one_full_session_delay_and_prefix_invariance():
    data = snapshot([100 + i * .2 for i in range(340)])
    original = build_signal_baseline(data)["cases"][0]["path"]
    mutated = copy.deepcopy(data)
    mutated["series"][320]["price"] = 1
    changed = build_signal_baseline(mutated)["cases"][0]["path"]
    assert original[:120] == changed[:120]
    for i, row in enumerate(changed[1:], 201):
        assert row["signal_date"] == data["series"][i - 2]["date"]
        assert row["position_date"] == data["series"][i - 1]["date"]
    # The shock at 320 cannot change the exposure taken for 320 or 321.
    assert original[120]["position"] == changed[120]["position"]
    assert original[121]["position"] == changed[121]["position"]


def test_all_exposed_matches_buy_hold_and_cost_once():
    result = build_signal_baseline(snapshot([100 + i for i in range(320)]))
    for case in result["cases"]:
        assert case["position_changes"] == 1
        assert case["exposure_share"] == 1
        assert math.isclose(case["excess_cumulative"], 0, abs_tol=1e-12)
        expected = 419 / 300 * (1 - case["cost_bps"] / 10_000)
        assert math.isclose(case["path"][-1]["market_wealth"], expected)
        assert case["interval"]["lower"] == case["interval"]["upper"] == 0


def test_cash_zero_yield_and_initial_peak_drawdown():
    result = build_signal_baseline(snapshot([600 - i for i in range(320)]))
    net = result["cases"][1]
    assert net["signal"]["cumulative_return"] == 0
    assert net["signal"]["max_drawdown"] == 0
    assert net["market"]["max_drawdown"] < 0
    assert net["position_changes"] == 0
    assert result == build_signal_baseline(snapshot([600 - i for i in range(320)]))


def test_invalid_sources_are_blocked():
    data = snapshot([100] * 320)
    assert not build_signal_baseline({**data, "data_quality": "PARTIAL"})["ok"]
    assert not build_signal_baseline(snapshot([100] * 300))["ok"]
    data["series"][250]["date"] = data["series"][249]["date"]
    assert not build_signal_baseline(data)["ok"]


def test_compounding_and_quarterly_deltas_match_path():
    result = build_signal_baseline(snapshot([200 + 30 * math.sin(i / 24) + .1 * i for i in range(420)]))
    for case in result["cases"]:
        path = case["path"]
        assert math.isclose(math.prod(1 + row["signal_return"] for row in path[1:]), path[-1]["signal_wealth"])
        assert math.isclose(math.prod(1 + q["signal_return"] for q in case["quarterly"]), path[-1]["signal_wealth"])
        assert case["signal"]["max_drawdown"] == min(row["signal_drawdown"] for row in path)
