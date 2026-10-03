"""Read-only, provenance-checked dashboard data from local Sectors snapshots."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _read_snapshot(path: Path, root: Path) -> tuple[Any, dict[str, Any], list[str]]:
    issues: list[str] = []
    metadata_path = path.with_suffix(".metadata.json")
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, {}, [f"{path.relative_to(root).as_posix()}: unreadable snapshot/metadata ({type(exc).__name__})"]

    if not isinstance(metadata, dict):
        return payload, {}, [f"{path.name}: metadata must be a JSON object"]

    digest = hashlib.sha256(raw).hexdigest()
    expected_digest = metadata.get("snapshot_sha256")
    if metadata.get("provider") != "Sectors.app":
        issues.append(f"{path.name}: provider metadata is not Sectors.app")
    if metadata.get("http_status") != 200:
        issues.append(f"{path.name}: source HTTP status is not 200")
    if not expected_digest or expected_digest != digest:
        issues.append(f"{path.name}: snapshot hash missing or mismatched")
    endpoint = urlparse(str(metadata.get("endpoint", "")))
    if endpoint.hostname != "api.sectors.app" or "/v2/" not in endpoint.path:
        issues.append(f"{path.name}: endpoint provenance is not a Sectors v2 endpoint")
    return payload, metadata, issues


def load_index_daily_snapshot(root: Path, index_code: str) -> dict[str, Any]:
    """Load and validate saved daily index snapshots without network access."""
    index_code = index_code.strip().casefold()
    if not index_code.isalnum():
        raise ValueError("Index code must be alphanumeric")
    index_label = index_code.upper()
    folder = root / "data" / "raw" / "sectors" / "index_daily" / index_code
    paths = sorted(
        path for path in folder.glob(f"{index_code}_*.json")
        if not path.name.endswith(".metadata.json")
    ) if folder.is_dir() else []
    records: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    retrieval_times: list[str] = []
    source_files: list[str] = []

    for path in paths:
        payload, metadata, snapshot_issues = _read_snapshot(path, root)
        issues.extend(snapshot_issues)
        if not isinstance(payload, list):
            issues.append(f"{path.name}: expected a list of daily observations")
            continue
        if str(metadata.get("index_code", "")).casefold() != index_code:
            issues.append(f"{path.name}: metadata index code is not {index_label}")
        metadata_endpoint = urlparse(str(metadata.get("endpoint", "")))
        if metadata_endpoint.path != f"/v2/index-daily/{index_code}/":
            issues.append(f"{path.name}: metadata endpoint does not match {index_label}")
        if metadata.get("retrieved_at"):
            retrieval_times.append(str(metadata["retrieved_at"]))
        source_files.append(path.relative_to(root).as_posix())
        for row in payload:
            if not isinstance(row, dict):
                issues.append(f"{path.name}: non-object observation")
                continue
            day = str(row.get("date", ""))
            try:
                date.fromisoformat(day)
                price = float(row.get("price"))
            except (TypeError, ValueError):
                issues.append(f"{path.name}: invalid date or index price")
                continue
            if str(row.get("index_code", "")).casefold() != index_code or not math.isfinite(price) or price <= 0:
                issues.append(f"{path.name}: invalid index code or non-positive price")
                continue
            observation = {"date": day, "price": price, "index_code": index_label}
            previous = records.get(day)
            if previous and previous != observation:
                issues.append(f"{path.name}: conflicting duplicate date {day}")
                continue
            records[day] = observation

    series = [records[day] for day in sorted(records)]
    latest = series[-1] if series else None
    previous = series[-2] if len(series) > 1 else None
    daily_change = None
    if latest and previous:
        daily_change = (latest["price"] / previous["price"] - 1) * 100
    return {
        "ok": bool(series),
        "data_quality": "VERIFIED" if series and not issues else "PARTIAL" if series else "MISSING",
        "provider": "Sectors.app",
        "source_class": "sectors_source_data",
        "endpoint": f"/v2/index-daily/{index_code}/",
        "source_files": source_files,
        "snapshot_count": len(source_files),
        "observation_count": len(series),
        "coverage_start": series[0]["date"] if series else None,
        "coverage_end": latest["date"] if latest else None,
        "retrieved_at": max(retrieval_times) if retrieval_times else None,
        "latest_price": latest["price"] if latest else None,
        "previous_price": previous["price"] if previous else None,
        "daily_change_pct": daily_change,
        "series": series,
        "issues": issues,
    }


def load_ihsg_snapshot(root: Path) -> dict[str, Any]:
    """Backward-compatible IHSG daily snapshot loader."""
    return load_index_daily_snapshot(root, "ihsg")


def load_lq45_index_snapshot(root: Path) -> dict[str, Any]:
    """Load the official Sectors-sourced LQ45 index daily series."""
    return load_index_daily_snapshot(root, "lq45")


def load_lq45_universe(root: Path) -> dict[str, Any]:
    """Return names/tickers from the saved, Sectors-sourced LQ45 universe."""
    path = root / "data" / "raw" / "sectors" / "lq45-universe.json"
    metadata_path = root / "data" / "raw" / "sectors" / "lq45-universe.metadata.json"
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"ok": False, "provider": "Sectors.app", "symbols": [], "issues": ["LQ45 universe snapshot or metadata is unavailable."], "data_quality": "MISSING"}
    issues: list[str] = []
    digest = hashlib.sha256(raw).hexdigest()
    if metadata.get("provider") != "Sectors.app" or metadata.get("http_status") != 200:
        issues.append("Universe source/provider metadata is not verified.")
    if metadata.get("sha256") != digest:
        issues.append("Universe snapshot hash is missing or mismatched.")
    endpoint = urlparse(str(metadata.get("endpoint", "")))
    if endpoint.hostname != "api.sectors.app" or "/v2/companies/" not in endpoint.path:
        issues.append("Universe endpoint is not the approved Sectors v2 companies endpoint.")
    results = payload.get("results", []) if isinstance(payload, dict) else []
    symbols: dict[str, str] = {}
    for row in results:
        if not isinstance(row, dict) or "LQ45" not in row.get("query_values", {}).get("indices", []):
            continue
        symbol = str(row.get("symbol", "")).replace(".JK", "").upper()
        if symbol:
            symbols[symbol] = str(row.get("company_name") or symbol)
    return {
        "ok": bool(symbols),
        "provider": "Sectors.app",
        "source_class": "sectors_source_data",
        "source_file": path.relative_to(root).as_posix(),
        "retrieved_at": metadata.get("retrieved_at"),
        "snapshot_count": 1 if symbols else 0,
        "symbol_count": len(symbols),
        "symbols": [{"ticker": ticker, "company": symbols[ticker]} for ticker in sorted(symbols)],
        "issues": issues,
        "data_quality": "VERIFIED" if symbols and not issues else "PARTIAL" if symbols else "MISSING",
    }


def load_issuer_daily(root: Path, ticker: str) -> dict[str, Any]:
    """Load a single issuer's saved Sectors.app OHLCV snapshots, read-only."""
    ticker = str(ticker or "").strip().upper()
    empty = {
        "ok": False, "ticker": ticker, "provider": "Sectors.app",
        "source_class": "sectors_source_data", "data_quality": "MISSING",
        "snapshot_count": 0, "observation_count": 0, "coverage_start": None,
        "coverage_end": None, "retrieved_at": None, "series": [], "issues": [],
    }
    if not ticker.isalnum() or len(ticker) > 10:
        return {**empty, "issues": ["Ticker format is invalid."]}

    folder = root / "data" / "raw" / "sectors" / "daily" / ticker
    paths = sorted(folder.glob(f"{ticker}_*.json")) if folder.is_dir() else []
    records: dict[str, dict[str, Any]] = {}
    issues: list[str] = []
    retrieval_times: list[str] = []
    source_files: list[str] = []

    for path in paths:
        if path.name.endswith(("_meta.json", ".metadata.json")):
            continue
        metadata_path = path.with_name(path.stem + "_meta.json")
        try:
            raw = path.read_bytes()
            payload = json.loads(raw)
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"{path.name}: unreadable snapshot/metadata ({type(exc).__name__})")
            continue
        if not isinstance(payload, list) or not isinstance(metadata, dict):
            issues.append(f"{path.name}: invalid daily snapshot or metadata structure")
            continue
        if metadata.get("provider") != "Sectors.app" or metadata.get("http_status") != 200:
            issues.append(f"{path.name}: provider or HTTP status is not verified")
        if metadata.get("ticker", "").upper() != ticker:
            issues.append(f"{path.name}: metadata ticker does not match requested ticker")
        if metadata.get("endpoint") != f"/v2/daily/{ticker}/":
            issues.append(f"{path.name}: endpoint metadata does not match ticker")
        if metadata.get("sha256") != hashlib.sha256(raw).hexdigest():
            issues.append(f"{path.name}: snapshot hash is missing or mismatched")
        if metadata.get("retrieved_at"):
            retrieval_times.append(str(metadata["retrieved_at"]))
        source_files.append(path.relative_to(root).as_posix())
        for row in payload:
            if not isinstance(row, dict):
                issues.append(f"{path.name}: observation is not an object")
                continue
            symbol = str(row.get("symbol", "")).replace(".JK", "").upper()
            if symbol != ticker:
                issues.append(f"{path.name}: observation symbol does not match {ticker}")
                continue
            day = str(row.get("date", ""))
            try:
                date.fromisoformat(day)
                close = float(row["close"])
                volume = float(row.get("volume", 0))
            except (KeyError, TypeError, ValueError):
                issues.append(f"{path.name}: invalid daily date, close, or volume")
                continue
            if not math.isfinite(close) or close <= 0 or not math.isfinite(volume) or volume < 0:
                issues.append(f"{path.name}: invalid daily close or volume")
                continue
            market_cap = row.get("market_cap")
            if market_cap is not None:
                try:
                    market_cap = float(market_cap)
                except (TypeError, ValueError):
                    issues.append(f"{path.name}: invalid daily market_cap on {day}")
                    market_cap = None
                else:
                    if not math.isfinite(market_cap) or market_cap < 0:
                        issues.append(f"{path.name}: invalid daily market_cap on {day}")
                        market_cap = None
            observation = {
                "date": day, "close": close, "volume": volume,
                "open": row.get("open"), "high": row.get("high"), "low": row.get("low"),
                "market_cap": market_cap,
            }
            previous = records.get(day)
            if previous and previous != observation:
                issues.append(f"{path.name}: conflicting duplicate date {day}")
                continue
            records[day] = observation

    series = [records[day] for day in sorted(records)]
    return {
        **empty,
        "ok": bool(series),
        "data_quality": "VERIFIED" if series and not issues else "PARTIAL" if source_files else "MISSING",
        "snapshot_count": len(source_files),
        "observation_count": len(series),
        "coverage_start": series[0]["date"] if series else None,
        "coverage_end": series[-1]["date"] if series else None,
        "retrieved_at": max(retrieval_times) if retrieval_times else None,
        "source_files": source_files,
        "series": series,
        "issues": issues,
    }


def load_sector_heatmap(root: Path, *, minimum_coverage: float = 0.70) -> dict[str, Any]:
    """Aggregate equal-weighted one-session LQ45 sector returns from saved Sectors snapshots."""
    if not 0 < minimum_coverage <= 1:
        raise ValueError("minimum_coverage must be greater than 0 and at most 1")

    report_root = root / "data" / "raw" / "sectors" / "company_report"
    report_paths = sorted(report_root.glob("*/company_report.json")) if report_root.is_dir() else []
    issues: list[str] = []
    source_files: list[str] = []
    retrieval_times: list[str] = []
    sector_members: dict[str, list[dict[str, str]]] = {}
    sector_candidate_counts: dict[str, int] = {}

    for path in report_paths:
        ticker = path.parent.name.upper()
        payload, metadata, snapshot_issues = _read_snapshot(path, root)
        report_issues = list(snapshot_issues)
        report_endpoint = urlparse(str(metadata.get("endpoint", "")))
        if report_endpoint.path != f"/v2/company/report/{ticker}/":
            report_issues.append(f"{path.name}: report endpoint does not match ticker folder")
        if str(metadata.get("symbol", "")).replace(".JK", "").upper() != ticker:
            report_issues.append(f"{path.name}: report metadata symbol does not match ticker folder")
        if not isinstance(payload, dict):
            report_issues.append(f"{path.name}: expected a company-report object")
        overview = payload.get("overview", {}) if isinstance(payload, dict) else {}
        if not isinstance(overview, dict):
            overview = {}
        if str(payload.get("symbol", "")).replace(".JK", "").upper() != ticker if isinstance(payload, dict) else True:
            report_issues.append(f"{path.name}: report symbol does not match ticker folder")
        if "LQ45" not in overview.get("indices", []):
            continue
        sector = str(overview.get("sector", "")).strip()
        if sector:
            sector_candidate_counts[sector] = sector_candidate_counts.get(sector, 0) + 1
        if not sector:
            report_issues.append(f"{path.name}: LQ45 report has no sector classification")
        if report_issues:
            issues.extend(report_issues)
            continue
        source_files.append(path.relative_to(root).as_posix())
        if metadata.get("retrieved_at"):
            retrieval_times.append(str(metadata["retrieved_at"]))
        sector_members.setdefault(sector, []).append({
            "ticker": ticker,
            "source_file": path.relative_to(root).as_posix(),
            "retrieved_at": str(metadata.get("retrieved_at", "")),
        })

    daily_cache: dict[str, dict[str, Any]] = {}
    all_dates: set[str] = set()
    for members in sector_members.values():
        for member in members:
            ticker = member["ticker"]
            if ticker in daily_cache:
                continue
            daily = load_issuer_daily(root, ticker)
            daily_cache[ticker] = daily
            if daily["data_quality"] == "VERIFIED":
                all_dates.update(row["date"] for row in daily["series"])
                source_files.extend(daily.get("source_files", []))
                if daily.get("retrieved_at"):
                    retrieval_times.append(str(daily["retrieved_at"]))
            else:
                issues.extend(f"{ticker}: {issue}" for issue in daily.get("issues", []))
                if not daily.get("issues"):
                    issues.append(f"{ticker}: daily source is {daily['data_quality'].casefold()}")

    aligned_dates = sorted(all_dates)
    as_of = aligned_dates[-1] if aligned_dates else None
    previous_date = aligned_dates[-2] if len(aligned_dates) >= 2 else None
    sectors: list[dict[str, Any]] = []
    daily_closes = {
        ticker: {row["date"]: float(row["close"]) for row in daily["series"]}
        for ticker, daily in daily_cache.items()
        if daily["data_quality"] == "VERIFIED"
    }

    for sector in sorted(sector_members, key=str.casefold):
        members = sector_members[sector]
        member_returns: list[float] = []
        sector_issues: list[str] = []
        if as_of and previous_date:
            for member in members:
                ticker = member["ticker"]
                daily = daily_cache[ticker]
                if daily["data_quality"] != "VERIFIED":
                    sector_issues.extend(f"{ticker}: {issue}" for issue in daily.get("issues", []))
                    continue
                closes = daily_closes.get(ticker, {})
                if as_of not in closes or previous_date not in closes:
                    sector_issues.append(f"{ticker}: no verified close pair for {previous_date} and {as_of}")
                    continue
                member_returns.append((closes[as_of] / closes[previous_date] - 1.0) * 100.0)
        else:
            sector_issues.append("At least two shared verified market dates are required.")

        universe_count = sector_candidate_counts.get(sector, len(members))
        coverage = len(member_returns) / universe_count if universe_count else 0.0
        coverage_ok = bool(member_returns) and coverage >= minimum_coverage
        sector_evidence = len(member_returns) >= 2 and coverage_ok
        single_issuer_proxy = universe_count == 1 and len(members) == 1 and coverage_ok
        if single_issuer_proxy:
            sector_issues.append("single-issuer proxy only; not a diversified sector return")
        result_quality = (
            "VERIFIED" if sector_evidence and coverage == 1.0
            else "PARTIAL" if coverage_ok
            else "INSUFFICIENT_EVIDENCE"
        )
        sectors.append({
            "sector": sector,
            "return_pct": sum(member_returns) / len(member_returns) if coverage_ok else None,
            "as_of": as_of,
            "previous_date": previous_date,
            "observation_count": len(member_returns),
            "universe_count": universe_count,
            "member_tickers": sorted(member["ticker"] for member in members),
            "coverage_pct": coverage,
            "data_quality": result_quality,
            "source_files": sorted({
                source
                for member in members
                for source in (member["source_file"], *daily_cache[member["ticker"]].get("source_files", []))
            }),
            "issues": sorted(set(sector_issues)),
        })

    monthly_heatmap = _build_sector_monthly_heatmap(
        sector_members=sector_members,
        sector_candidate_counts=sector_candidate_counts,
        daily_closes=daily_closes,
        aligned_dates=aligned_dates,
        as_of=as_of,
        minimum_coverage=minimum_coverage,
    )

    deduped_sources = sorted(set(source_files))
    has_measured_sector = any(row["return_pct"] is not None for row in sectors)
    all_verified = bool(sectors) and all(row["data_quality"] == "VERIFIED" for row in sectors) and not issues
    return {
        "ok": has_measured_sector,
        "provider": "Sectors.app",
        "source_class": "sectors_source_data",
        "methodology": "LQ45 equal-weighted one-session simple return proxy; not an official IDX sector index",
        "minimum_coverage": minimum_coverage,
        "as_of": as_of,
        "previous_date": previous_date,
        "sector_count": len(sectors),
        "snapshot_count": len(deduped_sources),
        "source_files": deduped_sources,
        "retrieved_at": max(retrieval_times) if retrieval_times else None,
        "sectors": sectors,
        "monthly_heatmap": monthly_heatmap,
        "issues": sorted(set(issues)),
        "data_quality": "VERIFIED" if all_verified else "PARTIAL" if sectors else "MISSING",
    }


def _build_sector_monthly_heatmap(
    *,
    sector_members: dict[str, list[dict[str, str]]],
    sector_candidate_counts: dict[str, int],
    daily_closes: dict[str, dict[str, float]],
    aligned_dates: list[str],
    as_of: str | None,
    minimum_coverage: float,
) -> dict[str, Any]:
    """Build 30-calendar-day equal-weighted daily sector returns from local closes."""
    if not as_of or len(aligned_dates) < 2:
        return {"start_date": None, "end_date": as_of, "dates": [], "sectors": [], "data_quality": "INSUFFICIENT_EVIDENCE"}

    end_date = date.fromisoformat(as_of)
    start_date = end_date - timedelta(days=29)
    first_index = next((index for index, day in enumerate(aligned_dates) if date.fromisoformat(day) >= start_date), len(aligned_dates))
    dates = aligned_dates[first_index:]
    rows: list[dict[str, Any]] = []
    all_returns: list[float] = []
    for sector in sorted(sector_members, key=str.casefold):
        members = sector_members[sector]
        universe_count = sector_candidate_counts.get(sector, len(members))
        cells: list[dict[str, Any]] = []
        for date_index in range(first_index, len(aligned_dates)):
            current_date = aligned_dates[date_index]
            previous_session = aligned_dates[date_index - 1] if date_index else None
            member_returns: list[tuple[str, float]] = []
            if previous_session:
                for member in members:
                    ticker = member["ticker"]
                    closes = daily_closes.get(ticker, {})
                    previous_close, current_close = closes.get(previous_session), closes.get(current_date)
                    if previous_close is not None and current_close is not None and previous_close > 0:
                        member_returns.append((ticker, (current_close / previous_close - 1.0) * 100.0))

            coverage = len(member_returns) / universe_count if universe_count else 0.0
            coverage_ok = bool(member_returns) and coverage >= minimum_coverage
            single_proxy = universe_count == 1 and len(member_returns) == 1 and coverage_ok
            eligible = (len(member_returns) >= 2 and coverage_ok) or single_proxy
            result_quality = "VERIFIED" if eligible and coverage == 1.0 and len(member_returns) >= 2 else "PARTIAL" if eligible else "INSUFFICIENT_EVIDENCE"
            sector_return = sum(value for _, value in member_returns) / len(member_returns) if eligible else None
            if sector_return is not None:
                all_returns.append(sector_return)
            cells.append({
                "date": current_date,
                "return_pct": sector_return,
                "observation_count": len(member_returns),
                "universe_count": universe_count,
                "coverage_pct": coverage,
                "data_quality": result_quality,
                "observed_tickers": sorted(ticker for ticker, _ in member_returns),
            })
        rows.append({
            "sector": sector,
            "universe_count": universe_count,
            "member_tickers": sorted(member["ticker"] for member in members),
            "single_issuer_proxy": universe_count == 1,
            "cells": cells,
        })

    return {
        "window_calendar_days": 30,
        "methodology": "Equal-weighted daily close-to-close return from locally saved Sectors.app snapshots; 30-calendar-day window ending on latest available date.",
        "start_date": dates[0] if dates else start_date.isoformat(),
        "end_date": as_of,
        "dates": dates,
        "sectors": rows,
        "color_scale_abs_pct": _nearest_rank_percentile([abs(value) for value in all_returns], 0.95) if all_returns else None,
        "data_quality": "PARTIAL" if any(cell["data_quality"] != "VERIFIED" for row in rows for cell in row["cells"]) else "VERIFIED",
    }


def _nearest_rank_percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def load_local_news(root: Path, *, limit: int = 6) -> dict[str, Any]:
    """Return recent, source-linked articles from saved Sectors news snapshots."""
    folder = root / "data" / "raw" / "sectors" / "news"
    paths = sorted(
        path for path in folder.glob("idx_lq45_*.json")
        if not path.name.endswith(".metadata.json")
    ) if folder.is_dir() else []
    articles: dict[tuple[str, str], dict[str, Any]] = {}
    issues: list[str] = []
    retrieval_times: list[str] = []
    coverage_ends: list[str] = []
    for path in paths:
        payload, metadata, snapshot_issues = _read_snapshot(path, root)
        issues.extend(snapshot_issues)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            issues.append(f"{path.name}: expected a news results object")
            continue
        if metadata.get("extension") != "idx":
            issues.append(f"{path.name}: news extension is not IDX")
        if metadata.get("retrieved_at"):
            retrieval_times.append(str(metadata["retrieved_at"]))
        if metadata.get("date_end"):
            coverage_ends.append(str(metadata["date_end"]))
        for row in payload["results"]:
            if not isinstance(row, dict) or not row.get("title") or not row.get("timestamp"):
                continue
            source = str(row.get("source", ""))
            if urlparse(source).scheme != "https":
                issues.append(f"{path.name}: article missing an https source link")
                continue
            key = (str(row["timestamp"]), str(row["title"]))
            articles[key] = {
                "title": str(row["title"]),
                "timestamp": str(row["timestamp"]),
                "source": source,
                "symbols": [str(symbol).replace(".JK", "") for symbol in row.get("symbols", [])[:4]],
                "sector": str(row.get("sector", "")),
            }
    latest = sorted(articles.values(), key=lambda row: row["timestamp"], reverse=True)[:limit]
    return {
        "ok": bool(latest),
        "provider": "Sectors.app",
        "source_class": "sectors_source_data",
        "snapshot_count": len(paths),
        "coverage_end": max(coverage_ends) if coverage_ends else None,
        "retrieved_at": max(retrieval_times) if retrieval_times else None,
        "articles": latest,
        "issues": issues,
        "data_quality": "VERIFIED" if latest and not issues else "PARTIAL" if latest else "MISSING",
    }


def load_news_universe(root: Path) -> dict[str, Any]:
    """Return all source-linked articles from locally saved, verified IDX news snapshots."""
    from .news_analysis import analyze_news_article

    folder = root / "data" / "raw" / "sectors" / "news"
    paths = sorted(
        path for path in folder.glob("idx_lq45_*.json")
        if not path.name.endswith(".metadata.json")
    ) if folder.is_dir() else []
    articles: dict[tuple[str, str, str], dict[str, Any]] = {}
    issues: list[str] = []
    retrieval_times: list[str] = []
    coverage_ends: list[str] = []
    verified_snapshot_count = 0

    for path in paths:
        payload, metadata, snapshot_issues = _read_snapshot(path, root)
        if snapshot_issues:
            issues.extend(snapshot_issues)
            continue
        endpoint = urlparse(str(metadata.get("endpoint", "")))
        if metadata.get("extension") != "idx" or endpoint.path != "/v2/news/":
            issues.append(f"{path.name}: snapshot is not an IDX news response")
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            issues.append(f"{path.name}: expected a news results object")
            continue
        verified_snapshot_count += 1
        if metadata.get("retrieved_at"):
            retrieval_times.append(str(metadata["retrieved_at"]))
        date_end = str(metadata.get("date_end", ""))
        if date_end:
            coverage_ends.append(date_end)
        relative = path.relative_to(root).as_posix()

        for row in payload["results"]:
            if not isinstance(row, dict):
                issues.append(f"{path.name}: skipped non-object article")
                continue
            title = str(row.get("title", "")).strip()
            timestamp = str(row.get("timestamp", "")).strip()
            source = str(row.get("source", "")).strip()
            parsed_source = urlparse(source)
            if not title or not timestamp or parsed_source.scheme != "https" or not parsed_source.hostname:
                issues.append(f"{path.name}: skipped article missing title, timestamp, or HTTPS source")
                continue
            key = (timestamp, title.casefold(), source)
            stable_id = hashlib.sha256("\x1f".join(key).encode("utf-8")).hexdigest()[:24]
            body = str(row.get("body") or "")[:6000]
            symbols_value = row.get("symbols")
            symbols = [str(value).replace(".JK", "").upper() for value in symbols_value if value] if isinstance(symbols_value, list) else []
            tags_value = row.get("tags")
            tags = [str(value) for value in tags_value if value] if isinstance(tags_value, list) else []
            sub_sector_value = row.get("sub_sector")
            sub_sector = [str(value) for value in sub_sector_value if value] if isinstance(sub_sector_value, list) else []
            dimension = row.get("dimension")
            dimensions = dimension if isinstance(dimension, dict) else {}
            record = articles.get(key)
            if record is None:
                articles[key] = {
                    "news_id": stable_id,
                    "title": title,
                    "body": body,
                    "timestamp": timestamp,
                    "source": source,
                    "sector": str(row.get("sector") or ""),
                    "sub_sector": sub_sector,
                    "symbols": symbols,
                    "tags": tags,
                    "dimensions": dimensions,
                    "source_file": relative,
                    "source_files": [relative],
                    "data_quality": "VERIFIED" if body else "PARTIAL",
                    "provenance": {
                        "provider": "Sectors.app",
                        "snapshot_sha256": metadata.get("snapshot_sha256"),
                        "retrieved_at": metadata.get("retrieved_at"),
                    },
                }
            elif relative not in record["source_files"]:
                record["source_files"].append(relative)

    ordered_articles = sorted(articles.values(), key=lambda item: (item["timestamp"], item["news_id"]), reverse=True)
    for article in ordered_articles:
        article["offline_analysis"] = analyze_news_article(article)
    timestamps = [str(article["timestamp"]) for article in ordered_articles]
    return {
        "ok": bool(ordered_articles),
        "provider": "Sectors.app",
        "source_class": "sectors_source_data",
        "snapshot_count": verified_snapshot_count,
        "coverage_end": max(coverage_ends) if coverage_ends else None,
        "article_date_start": min(timestamps)[:10] if timestamps else None,
        "article_date_end": max(timestamps)[:10] if timestamps else None,
        "analysis_method": "offline_keyword_heuristic_v1",
        "analysis_scope": "All deduplicated articles in verified local snapshots; source text only; not causal proof or market-impact ranking.",
        "retrieved_at": max(retrieval_times) if retrieval_times else None,
        "articles": ordered_articles,
        "issues": sorted(set(issues)),
        "data_quality": "VERIFIED" if ordered_articles and not issues and all(row["data_quality"] == "VERIFIED" for row in ordered_articles) else "PARTIAL" if ordered_articles else "MISSING",
    }
