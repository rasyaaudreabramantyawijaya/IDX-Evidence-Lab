"""Offline, provenance-checked market-overview calculations.

The current LQ45 list is a snapshot, not historical point-in-time membership.
These are descriptive calculations, not investment signals.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from .market_data import _read_snapshot


def load_foreign_flow(root: Path, symbols: list[str]) -> dict[str, Any]:
    """Deduplicate dated foreign-flow records; reject invalid provenance/conflicts."""
    by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
    issues: list[str] = []
    for symbol in symbols:
        folder = root / "data/raw/sectors/foreign_flow" / symbol
        observations: dict[str, dict[str, Any]] = {}
        paths = sorted(p for p in folder.glob(f"{symbol}_*.json") if not p.name.endswith(".metadata.json"))
        if not paths:
            issues.append(f"{symbol}: no foreign-flow snapshots")
        for path in paths:
            payload, metadata, problems = _read_snapshot(path, root)
            if problems:
                issues.extend(problems)
                continue
            if metadata.get("ticker") != symbol or f"/foreign-flow/{symbol}/" not in metadata.get("endpoint", ""):
                issues.append(f"{path.name}: ticker/endpoint mismatch")
                continue
            if not isinstance(payload, dict) or payload.get("symbol") != f"{symbol}.JK":
                issues.append(f"{path.name}: payload symbol mismatch")
                continue
            for row in payload.get("data", []):
                try:
                    day = str(row["date"])
                    date.fromisoformat(day)
                    buy = float(row["foreign_buy_idr"])
                    sell = float(row["foreign_sell_idr"])
                    net = float(row["net_foreign_inflow"])
                    if not all(map(math.isfinite, (buy, sell, net))) or min(buy, sell) < 0 or abs(buy - sell - net) > max(1, .0001 * max(buy, sell)):
                        raise ValueError("invalid amounts")
                except (KeyError, TypeError, ValueError):
                    issues.append(f"{path.name}: invalid dated flow row")
                    continue
                item = {"date": day, "buy": buy, "sell": sell, "net": net}
                if day in observations and observations[day] != item:
                    issues.append(f"{symbol}: conflicting duplicate {day}")
                    continue
                observations[day] = item
        by_symbol[symbol] = observations

    dates = sorted({day for rows in by_symbol.values() for day in rows})
    daily = []
    for day in dates:
        rows = [items[day] for items in by_symbol.values() if day in items]
        daily.append({"date": day, "buy": sum(r["buy"] for r in rows), "sell": sum(r["sell"] for r in rows), "net": sum(r["net"] for r in rows), "coverage": len(rows)})
    monthly = []
    for month in sorted({row["date"][:7] for row in daily}):
        rows = [row for row in daily if row["date"].startswith(month)]
        monthly.append({"month": month, "net": sum(row["net"] for row in rows), "coverage_min": min(row["coverage"] for row in rows), "coverage_max": max(row["coverage"] for row in rows), "sessions": len(rows)})
    # Strictly prior 12 FULL months: no leakage from the month being scored.
    for index, row in enumerate(monthly):
        row["complete"] = row["month"] != dates[-1][:7]
        baseline = [r["net"] for r in monthly[max(0, index - 12):index] if r["coverage_min"] == len(symbols)]
        deviation = pstdev(baseline) if len(baseline) == 12 else 0
        row["z12"] = (row["net"] - mean(baseline)) / deviation if row["complete"] and deviation > 0 and row["coverage_min"] == len(symbols) else None
    unusual = []
    latest_day = dates[-1] if dates else None
    for symbol, observations in by_symbol.items():
        if latest_day not in observations:
            continue
        days = sorted(day for day in observations if day < latest_day)
        baseline = [observations[day]["net"] for day in days[-20:]]
        if len(baseline) != 20 or pstdev(baseline) == 0:
            continue
        value = (observations[latest_day]["net"] - mean(baseline)) / pstdev(baseline)
        if abs(value) >= 2:
            unusual.append({"ticker": symbol, "z20": round(value, 2), "net": observations[latest_day]["net"]})
    unusual.sort(key=lambda item: abs(item["z20"]), reverse=True)
    return {
        "data_quality": "VERIFIED" if daily and not issues else "PARTIAL" if daily else "MISSING",
        "universe_count": len(symbols), "coverage_start": dates[0] if dates else None,
        "coverage_end": latest_day, "daily": daily, "monthly": monthly,
        "issuer_daily": {symbol: [observations[day] for day in sorted(observations)] for symbol, observations in by_symbol.items()},
        "unusual_foreign_flow": unusual, "unusual_definition": "absolute z-score >= 2 versus prior 20 issuer trading days, no current-day leakage",
        "issues": issues[:30], "issue_count": len(issues),
    }


def load_valuation_snapshot(root: Path, symbols: list[str]) -> dict[str, Any]:
    """Report current valuation/OCF field coverage, without inventing a time series."""
    forward = []
    negative_forward = []
    forward_rows = []
    ocf = []
    market_cap = []
    years = set()
    cap_total = 0
    ocf_total = 0
    issues = []
    for symbol in symbols:
        path = root / "data/raw/sectors/company_report" / symbol / "company_report.json"
        report, metadata, problems = _read_snapshot(path, root)
        if problems or not isinstance(report, dict) or report.get("symbol") != f"{symbol}.JK" or metadata.get("symbol") != symbol:
            issues.extend(problems or [f"{symbol}: company report mismatch"])
            continue
        cap = report.get("overview", {}).get("market_cap")
        pe = report.get("valuation", {}).get("forward_pe")
        forecasts = report.get("future", {}).get("company_value_forecasts") or []
        forecast_rows = [row for row in forecasts if isinstance(row, dict) and isinstance(row.get("estimate_year"), int)]
        latest_forecast = max(forecast_rows, key=lambda row: row["estimate_year"], default=None)
        if isinstance(cap, (int, float)) and cap > 0:
            market_cap.append(symbol)
            cap_total += cap
        if isinstance(pe, (int, float)) and math.isfinite(pe) and pe > 0:
            forward.append(symbol)
            pe_status, reason = "positive", "Forward P/E positif dilaporkan langsung oleh Sectors.app."
        elif isinstance(pe, (int, float)) and math.isfinite(pe) and pe < 0:
            negative_forward.append(symbol)
            pe_status, reason = "negative", "Forward P/E negatif dilaporkan sumber; kelipatan negatif tidak sebanding dengan P/E positif."
        elif isinstance(pe, (int, float)) and math.isfinite(pe):
            pe_status, reason = "zero", "Sumber melaporkan P/E nol; perlu pemeriksaan denominator dan definisi."
        elif latest_forecast is None:
            pe_status, reason = "missing", "Forward P/E dan estimasi EPS forward tidak tersedia pada snapshot laporan ini."
        elif latest_forecast.get("eps_estimate") == 0:
            pe_status, reason = "missing", f"Estimasi EPS {latest_forecast['estimate_year']} = 0; P/E tidak terdefinisi."
        else:
            pe_status, reason = "missing", f"Estimasi EPS {latest_forecast['estimate_year']} tersedia, tetapi forward P/E sumber kosong; basis harga, unit, dan formula belum diverifikasi."
        forward_rows.append({
            "ticker": symbol,
            "company": report.get("company_name") or symbol,
            "forward_pe": float(pe) if isinstance(pe, (int, float)) and math.isfinite(pe) else None,
            "status": pe_status,
            "reason": reason,
            "forecast_year": latest_forecast.get("estimate_year") if latest_forecast else None,
            "eps_estimate": latest_forecast.get("eps_estimate") if latest_forecast else None,
            "price_as_of": report.get("valuation", {}).get("latest_close_date") or report.get("overview", {}).get("latest_close_date"),
            "source_file": path.relative_to(root).as_posix(),
        })
        annual = [r for r in report.get("financials", {}).get("historical_financials", []) if isinstance(r, dict) and isinstance(r.get("year"), int)]
        if annual:
            latest = max(annual, key=lambda r: r["year"])
            years.add(latest["year"])
            if isinstance(latest.get("operating_cash_flow"), (int, float)):
                ocf.append(symbol)
                ocf_total += latest["operating_cash_flow"]
    return {
        "universe_count": len(symbols), "forward_pe_coverage": len(forward),
        "forward_pe_negative_count": len(negative_forward),
        "forward_pe_missing_count": sum(row["status"] == "missing" for row in forward_rows),
        "forward_pe_zero_count": sum(row["status"] == "zero" for row in forward_rows),
        "forward_pe_by_issuer": forward_rows,
        "market_cap_coverage": len(market_cap), "ocf_latest_coverage": len(ocf),
        "ocf_latest_years": sorted(years), "lq45_index_history_pulled": False,
        "forward_pe_history_pulled": False,
        "market_cap_idr": cap_total if len(market_cap) == len(symbols) else None,
        "ocf_idr": ocf_total if len(ocf) == len(symbols) and years == {2025} else None,
        "cap_to_ocf": cap_total / ocf_total if len(market_cap) == len(ocf) == len(symbols) and years == {2025} and ocf_total > 0 else None,
        "issues": issues[:20], "issue_count": len(issues),
        "note": "OCF is annual and market cap is one report snapshot; not an aligned historical or TTM ratio.",
    }
