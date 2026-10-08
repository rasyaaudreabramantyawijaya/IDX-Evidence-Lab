"""Fixed, causal IHSG regime replay against the identical IHSG market path.

No forecasting, tuning, constituent selection or external calls. The index is
a research proxy, not a tradable instrument. Execution uses a full session
delay because the input contains closes only, not verified open/VWAP fills.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
import math
import random
from statistics import mean, stdev
from typing import Any


VERSION = "ihsg-regime-baseline.v1"


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def paired_block_interval(pairs: list[tuple[float, float]], *, seed: int = 42,
                          simulations: int = 500, block: int = 20) -> dict[str, Any]:
    """95% interval for annualized arithmetic excess, resampling paired blocks.

    Conditional on this realized fixed-rule path. Does not refit/replay signals
    on synthetic prices and does not estimate future strategy performance.
    """
    if len(pairs) < block * 5:
        return {"status": "INSUFFICIENT_SAMPLE", "lower": None, "upper": None}
    rng = random.Random(seed)
    differences = [strategy - market for strategy, market in pairs]
    sampled_means = []
    for _ in range(simulations):
        sample = []
        while len(sample) < len(pairs):
            start = rng.randrange(len(pairs) - block + 1)
            sample.extend(differences[start:start + block])
        sampled_means.append(mean(sample[:len(pairs)]) * 252)
    return {"status": "EXPLORATORY", "estimate": mean(differences) * 252,
            "lower": _quantile(sampled_means, .025), "upper": _quantile(sampled_means, .975),
            "seed": seed, "simulations": simulations, "block_sessions": block,
            "sample_count": len(pairs), "metric": "annualized_arithmetic_excess_return",
            "interpretation": "Conditional paired-block interval on the observed path, not a forecast or proof of alpha."}


def _metrics(returns: list[float], wealth: float, mdd: float) -> dict[str, float]:
    return {"cumulative_return": wealth - 1,
            "annualized_return": wealth ** (252 / len(returns)) - 1,
            "annualized_volatility": stdev(returns) * math.sqrt(252) if len(returns) > 1 else 0,
            "max_drawdown": mdd}


def _replay(series: list[dict[str, Any]], cost_bps: float) -> dict[str, Any]:
    prices = [row["price"] for row in series]
    # First rule observation is close index 199 (200 completed sessions).
    # Observe at s, establish the hypothetical position at close s+1,
    # earn close s+1 -> close s+2. Never fill at the observation close.
    start = 200
    path = [{"date": series[start]["date"], "signal_wealth": 1.0,
             "market_wealth": 1.0, "position": None, "signal_date": None,
             "signal_drawdown": 0.0, "market_drawdown": 0.0}]
    strategy_wealth = market_wealth = signal_peak = market_peak = 1.0
    signal_mdd = market_mdd = 0.0
    previous_position = 0
    switches = 0
    paired_returns: list[tuple[float, float]] = []
    signal_returns, market_returns, rows = [], [], []
    fee = cost_bps / 10_000
    prefix = [0.0]
    for value in prices:
        prefix.append(prefix[-1] + value)
    for t in range(start + 1, len(series)):
        signal_index = t - 2
        sma50 = (prefix[signal_index + 1] - prefix[signal_index - 49]) / 50
        sma200 = (prefix[signal_index + 1] - prefix[signal_index - 199]) / 200
        position = int(prices[signal_index] > sma200 and sma50 > sma200)
        turnover = abs(position - previous_position)
        switches += turnover
        market_return = prices[t] / prices[t - 1] - 1
        # Cost is paid on each 0/1 exposure change, including first entry.
        # Benchmark pays the same one-way entry cost, once, at evaluation start.
        signal_net = (1 + position * market_return) * (1 - fee * turnover) - 1
        market_net = (1 + market_return) * (1 - fee * int(t == start + 1)) - 1
        strategy_wealth *= 1 + signal_net
        market_wealth *= 1 + market_net
        signal_peak = max(signal_peak, strategy_wealth)
        market_peak = max(market_peak, market_wealth)
        signal_dd, market_dd = strategy_wealth / signal_peak - 1, market_wealth / market_peak - 1
        signal_mdd, market_mdd = min(signal_mdd, signal_dd), min(market_mdd, market_dd)
        row = {"date": series[t]["date"], "signal_date": series[signal_index]["date"],
               "position_date": series[t - 1]["date"], "position": position,
               "turnover": turnover, "signal_return": signal_net, "market_return": market_net,
               "signal_wealth": strategy_wealth, "market_wealth": market_wealth,
               "signal_drawdown": signal_dd, "market_drawdown": market_dd}
        rows.append(row)
        path.append(row)
        signal_returns.append(signal_net)
        market_returns.append(market_net)
        paired_returns.append((signal_net, market_net))
        previous_position = position
    quarterly = []
    quarters = sorted({f"{row['date'][:4]}-Q{(int(row['date'][5:7]) - 1) // 3 + 1}" for row in rows})
    for quarter in quarters:
        subset = [row for row in rows if f"{row['date'][:4]}-Q{(int(row['date'][5:7]) - 1) // 3 + 1}" == quarter]
        sr = math.prod(1 + row["signal_return"] for row in subset) - 1
        mr = math.prod(1 + row["market_return"] for row in subset) - 1
        quarterly.append({"period": quarter, "start": subset[0]["date"], "end": subset[-1]["date"],
                          "sessions": len(subset), "signal_return": sr, "market_return": mr,
                          "excess": sr - mr})
    return {"cost_bps": cost_bps, "path": path,
            "signal": _metrics(signal_returns, strategy_wealth, signal_mdd),
            "market": _metrics(market_returns, market_wealth, market_mdd),
            "excess_cumulative": strategy_wealth - market_wealth,
            "exposure_share": mean(row["position"] for row in rows),
            "position_changes": switches, "sessions": len(rows),
            "interval": paired_block_interval(paired_returns), "quarterly": quarterly,
            "negative_periods": sum(row["excess"] < 0 for row in quarterly)}


def build_signal_baseline(ihsg: dict[str, Any]) -> dict[str, Any]:
    """Require verified, unique, ordered, positive index closes; fail visibly."""
    blocked = {"ok": False, "schema_version": VERSION, "status": "INSUFFICIENT_EVIDENCE", "cases": []}
    if not ihsg.get("ok") or ihsg.get("data_quality") != "VERIFIED":
        return {**blocked, "reason": "Snapshot IHSG belum lolos pemeriksaan provenance."}
    try:
        series = [{"date": row["date"], "price": float(row["price"])} for row in ihsg["series"]]
        for row in series:
            date.fromisoformat(row["date"])
            if not math.isfinite(row["price"]) or row["price"] <= 0:
                raise ValueError("invalid price")
        dates = [row["date"] for row in series]
        if dates != sorted(set(dates)):
            raise ValueError("dates must be unique and ordered")
    except (KeyError, ValueError, TypeError, OverflowError):
        return {**blocked, "reason": "Tanggal/harga IHSG tidak valid, berulang, atau tidak berurutan."}
    if len(series) < 301:
        return {**blocked, "reason": "Perlu 200 sesi pemanasan, satu sesi jeda, dan setidaknya 100 return evaluasi."}
    fingerprint = hashlib.sha256(json.dumps(series, separators=(",", ":"), sort_keys=True).encode()).hexdigest()
    return {"ok": True, "schema_version": VERSION, "status": "EXPLORATORY_HISTORICAL_REPLAY",
            "source_class": "derived_metric", "provider": "Sectors.app",
            "source_fingerprint": fingerprint, "source_files": ihsg.get("source_files", []),
            "source_retrieved_at": ihsg.get("retrieved_at"), "observation_count": len(series),
            "source_coverage_start": dates[0], "source_coverage_end": dates[-1],
            "source_latest_price": series[-1]["price"], "warmup_sessions": 200,
            "rule": "IHSG close > SMA200 and SMA50 > SMA200; otherwise cash",
            "signal_lag_sessions": 2, "execution_delay_sessions": 1,
            "cash_return_annual": 0.0, "default_cost_bps": 10,
            "cases": [_replay(series, cost) for cost in (0, 10, 25)],
            "limits": ["Fixed-rule rolling historical replay; no fitted model or untouched holdout. Parameters were not searched.",
                       "IHSG is a price-index research proxy, not a directly tradable asset; actual fills, dividends and fund tracking are not modeled.",
                       "Costs of 0/10/25 bps per one-way exposure change are assumptions, not a broker fee schedule. Cash earns 0%; no terminal liquidation.",
                       "Paired-block interval conditions on the observed path; it does not replay a strategy on simulated markets or guarantee future returns."]}
