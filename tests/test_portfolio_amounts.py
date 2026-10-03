import pytest

from idx_evidence_lab.portfolio_amounts import allocate_amounts


def test_amounts_follow_optimizer_weights_without_changing_them():
    weights = {"BBCA": 0.6, "BMRI": 0.4}
    result = allocate_amounts(weights, 10_000_000)
    assert result["total_capital"] == 10_000_000
    assert result["amounts"] == {"BBCA": 6_000_000, "BMRI": 4_000_000}
    assert result["unallocated_rounding"] == 0
    assert weights == {"BBCA": 0.6, "BMRI": 0.4}


@pytest.mark.parametrize("capital", [0, -1, float("inf"), float("nan"), "100"])
def test_amounts_reject_invalid_capital(capital):
    with pytest.raises(ValueError):
        allocate_amounts({"BBCA": 1.0}, capital)


def test_amounts_use_largest_remainder_to_preserve_total_rupiah():
    result = allocate_amounts({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}, 100)
    assert sum(result["amounts"].values()) == 100
