"""Map target portfolio weights to nominal whole-rupiah allocations."""

from __future__ import annotations

import math
from typing import Any


def allocate_lots(weights: dict[str, float], total_capital: float,
                  prices: dict[str, float], *, lot_size: int = 100) -> dict[str, Any]:
    """Conservative floor rounding per target; leave unused funds as cash."""
    targets = allocate_amounts(weights, total_capital)
    if type(lot_size) is not int or lot_size < 1:
        raise ValueError("lot_size must be a positive integer")
    rows = {}
    for ticker, target in targets["amounts"].items():
        price = prices.get(ticker)
        if price is None or not math.isfinite(price) or price <= 0:
            raise ValueError(f"Verified positive close required for {ticker}")
        lots = math.floor(target / (price * lot_size))
        amount = lots * lot_size * price
        rows[ticker] = {"target_amount": target, "price": price, "lots": lots,
                        "shares": lots * lot_size, "amount": amount,
                        "realized_weight": amount / targets["total_capital"]}
    invested = sum(row["amount"] for row in rows.values())
    return {"rows": rows, "invested": invested, "cash": targets["total_capital"] - invested,
            "lot_size": lot_size, "fee_assumption": 0,
            "status": "ILLUSTRATIVE_LOT_ROUNDING_FEES_EXCLUDED"}


def allocate_amounts(weights: dict[str, float], total_capital: Any) -> dict[str, Any]:
    """Allocate integer rupiah with largest-remainder rounding, preserving weights."""
    if isinstance(total_capital, bool) or not isinstance(total_capital, (int, float)):
        raise ValueError("total_capital must be a positive finite number")
    if not math.isfinite(float(total_capital)) or total_capital <= 0 or total_capital > 10**15:
        raise ValueError("total_capital must be a positive finite number no greater than 1e15")
    if not isinstance(weights, dict) or not weights:
        raise ValueError("weights must be a non-empty mapping")
    clean = {str(ticker): float(weight) for ticker, weight in weights.items()}
    if any(not math.isfinite(weight) or weight < 0 for weight in clean.values()):
        raise ValueError("weights must be finite and nonnegative")
    if not math.isclose(sum(clean.values()), 1.0, rel_tol=0, abs_tol=1e-8):
        raise ValueError("weights must sum to 1")
    capital = int(round(total_capital))
    exact = {ticker: capital * weight for ticker, weight in clean.items()}
    amounts = {ticker: math.floor(value) for ticker, value in exact.items()}
    remaining = capital - sum(amounts.values())
    order = sorted(clean, key=lambda ticker: (exact[ticker] - amounts[ticker], ticker), reverse=True)
    for ticker in order[:remaining]:
        amounts[ticker] += 1
    return {"total_capital": capital, "amounts": amounts, "unallocated_rounding": capital - sum(amounts.values())}
