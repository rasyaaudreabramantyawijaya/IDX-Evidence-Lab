"""Portfolio inputs from locally saved and provenance-checked Sectors snapshots."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ..market.market_data import _read_snapshot, load_index_daily_snapshot, load_issuer_daily, load_lq45_universe


def _current_classifications(
    root: Path, tickers: list[str],
) -> tuple[dict[str, str | None], dict[str, str | None], list[str], set[str]]:
    sectors: dict[str, str | None] = {}
    sub_sectors: dict[str, str | None] = {}
    issues: list[str] = []
    verified_members: set[str] = set()
    for ticker in tickers:
        path = root / "data" / "raw" / "sectors" / "company_report" / ticker / "company_report.json"
        payload, metadata, report_issues = _read_snapshot(path, root)
        endpoint = urlparse(str(metadata.get("endpoint", ""))).path
        if endpoint != f"/v2/company/report/{ticker}/" or str(metadata.get("symbol", "")).replace(".JK", "").upper() != ticker:
            report_issues.append("company-report ticker or endpoint metadata mismatch")
        if not isinstance(payload, dict) or str(payload.get("symbol", "")).replace(".JK", "").upper() != ticker:
            report_issues.append("company-report symbol mismatch")
        company_report = payload if isinstance(payload, dict) else {}
        overview = company_report.get("overview", {})
        if not isinstance(overview, dict) or "LQ45" not in overview.get("indices", []):
            report_issues.append("company-report current LQ45 classification unavailable")
        sector = str(company_report.get("sector", "") or (overview.get("sector", "") if isinstance(overview, dict) else "")).strip()
        sub_sector = str(company_report.get("sub_sector", "") or (overview.get("sub_sector", "") if isinstance(overview, dict) else "")).strip()
        if not report_issues:
            verified_members.add(ticker)
        sectors[ticker] = sector if sector and not report_issues else None
        sub_sectors[ticker] = sub_sector if sub_sector and not report_issues else None
        issues.extend(f"{ticker}: {issue}" for issue in report_issues)
        if not sector:
            issues.append(f"{ticker}: current sector label missing")
    return sectors, sub_sectors, issues, verified_members


def load_portfolio_inputs(
    root: Path, tickers: list[str], benchmark: str = "IHSG", *, minimum_returns: int = 126,
) -> dict[str, Any]:
    """Align prices by shared market date; never impute or refresh source snapshots.

    Close-to-close returns are provisional price returns. A large unexplained
    jump is excluded, not called a split-adjusted economic return.
    """
    if not isinstance(tickers, list) or not tickers or len(tickers) > 45:
        raise ValueError("Select 1–45 LQ45 ticker symbols")
    normalized = [str(t).strip().upper() for t in tickers]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate LQ45 ticker selection")
    benchmark = str(benchmark).strip().upper()
    if benchmark not in {"IHSG", "LQ45"}:
        raise ValueError("Unsupported benchmark; choose IHSG or LQ45")
    if not isinstance(minimum_returns, int) or minimum_returns < 1:
        raise ValueError("minimum_returns must be a positive integer")

    universe = load_lq45_universe(root)
    valid = {item["ticker"] for item in universe.get("symbols", [])} if universe["data_quality"] in {"VERIFIED", "PARTIAL"} else set()
    if not valid:
        raise ValueError("LQ45 universe snapshot is unavailable")
    unknown = [ticker for ticker in normalized if ticker not in valid]
    if unknown:
        raise ValueError(f"Not in current verified LQ45 snapshot: {', '.join(unknown)}")

    index = load_index_daily_snapshot(root, benchmark)
    daily = {ticker: load_issuer_daily(root, ticker) for ticker in normalized}
    sectors, sub_sectors, classification_issues, verified_members = _current_classifications(root, normalized)
    issues: list[str] = [*universe.get("issues", []), *classification_issues]
    failed_sources = []
    if universe["data_quality"] != "VERIFIED":
        failed_sources.extend(ticker for ticker in normalized if ticker not in verified_members)
        for ticker in normalized:
            if ticker not in verified_members:
                issues.append(f"{ticker}: LQ45 membership cannot be cross-checked against a verified company report")
    for ticker, snapshot in daily.items():
        if snapshot["data_quality"] != "VERIFIED":
            failed_sources.append(ticker)
            issues.extend(f"{ticker}: {issue}" for issue in snapshot.get("issues", []))
            if not snapshot.get("issues"):
                issues.append(f"{ticker}: daily source is {snapshot['data_quality']}")
    if index["data_quality"] != "VERIFIED":
        failed_sources.append(benchmark)
        issues.extend(f"{benchmark}: {issue}" for issue in index.get("issues", []))
    index_price = {row["date"]: float(row["price"]) for row in index["series"]}
    index_dates = sorted(index_price)
    index_position = {day: position for position, day in enumerate(index_dates)}
    by_ticker = {ticker: {row["date"]: row for row in snapshot["series"]} for ticker, snapshot in daily.items()}
    date_sets = [set(index_dates), *(set(by_ticker[ticker]) for ticker in normalized)]
    dates = sorted(set.intersection(*date_sets)) if date_sets else []
    close_matrix = [[float(by_ticker[ticker][day]["close"]) for ticker in normalized] for day in dates]
    market_cap_matrix = [[by_ticker[ticker][day]["market_cap"] for ticker in normalized] for day in dates]

    return_dates: list[str] = []
    return_matrix: list[list[float]] = []
    benchmark_returns: dict[str, float] = {}
    dropped_jump_dates: list[str] = []
    for previous, current in zip(dates, dates[1:]):
        # Shared observations may skip market sessions; do not turn multi-day
        # moves into a single daily return.
        if index_position[current] != index_position[previous] + 1:
            issues.append(f"{current}: common-price gap since {previous}; daily return omitted")
            continue
        price_row = close_matrix[dates.index(current)]
        previous_row = close_matrix[dates.index(previous)]
        row_returns = [price / old - 1 for price, old in zip(price_row, previous_row)]
        jumps = [ticker for ticker, value in zip(normalized, row_returns) if abs(value) > 0.40]
        if jumps:
            issues.extend(f"{ticker}: unexplained price jump on {current} ({value:+.1%}); return excluded"
                          for ticker, value in zip(normalized, row_returns) if ticker in jumps)
            dropped_jump_dates.append(current)
            continue
        return_dates.append(current)
        return_matrix.append(row_returns)
        benchmark_returns[current] = index_price[current] / index_price[previous] - 1

    if failed_sources:
        # Even if individual valid rows exist, a compromised source is never
        # exposed as an optimizable portfolio sample.
        return_dates = []
        return_matrix = []
        benchmark_returns = {}
    status = "BLOCKED" if failed_sources else "READY" if len(return_dates) >= minimum_returns else "INSUFFICIENT_HISTORY"
    available_caps = sum(value is not None for row in market_cap_matrix for value in row)
    total_caps = sum(len(row) for row in market_cap_matrix)
    field_status = {
        "price_returns": "PROVISIONAL" if return_matrix else "UNAVAILABLE",
        "market_cap": "AVAILABLE" if total_caps and available_caps == total_caps else "PARTIAL" if available_caps else "UNAVAILABLE",
        "size_characteristic": "PARTIAL" if available_caps else "UNAVAILABLE",
        "momentum_characteristic": "PARTIAL" if return_matrix else "UNAVAILABLE",
        "value_factor": "UNAVAILABLE",
        "quality_factor": "UNAVAILABLE",
        "apt": "UNAVAILABLE",
        "risk_free_rate": "UNAVAILABLE",
        "black_litterman": "UNAVAILABLE",
    }
    return {
        "status": status,
        "quality": "PROVISIONAL" if return_matrix or dropped_jump_dates else "BLOCKED" if failed_sources else "INSUFFICIENT",
        "provider": "Sectors.app", "source_class": "sectors_source_data",
        "tickers": normalized, "benchmark": benchmark,
        "dates": dates, "close_matrix": close_matrix, "market_cap_matrix": market_cap_matrix,
        "return_dates": return_dates, "return_matrix": return_matrix,
        "benchmark_returns": benchmark_returns,
        "sectors": sectors,
        "sub_sectors": sub_sectors,
        "sector_label_limitation": "Current company-report labels only; no point-in-time sector membership reconstruction.",
        "sub_sector_label_limitation": "Current company-report sub-sector labels only; missing labels remain unmapped and historical classifications are not reconstructed.",
        "universe_limitation": "Current LQ45 snapshot, not historical index membership; survivorship bias is possible. Universe checksum mismatch is disclosed and selected membership is cross-checked against verified company reports.",
        "adjustment_policy": "Unadjusted close-to-close price returns; jumps above 40% excluded pending corporate-action review. Dividend/rights/split adjustments are unverified.",
        "field_status": field_status,
        "coverage": {
            "common_price_sessions": len(dates), "eligible_return_sessions": len(return_dates),
            "minimum_return_sessions": minimum_returns,
            "start": dates[0] if dates else None, "end": dates[-1] if dates else None,
            "excluded_jump_sessions": len(dropped_jump_dates),
            "market_cap_observations": available_caps, "market_cap_possible": total_caps,
        },
        "universe": {"symbol_count": universe["symbol_count"], "source_file": universe["source_file"],
                     "retrieved_at": universe["retrieved_at"], "data_quality": universe["data_quality"]},
        "sources": {"universe": universe["source_file"],
                    "daily": {ticker: daily[ticker].get("source_files", []) for ticker in normalized},
                    "benchmark": index.get("source_files", [])},
        "issues": issues,
    }
