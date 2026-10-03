"""Descriptive, point-in-time-limited LQ45 factor characteristics from local Sectors snapshots."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .market_data import _read_snapshot, load_issuer_daily, load_index_daily_snapshot, load_lq45_universe
from .portfolio_data import _current_classifications

SCHEMA_VERSION = "portfolio-factor-zoo.v1"
FORMULA_VERSION = "cross-sectional-zscore.v1"
MIN_PEERS = 5
MIN_ALIGNED_RETURNS = 126


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def score_cross_section(values: dict[str, float | None], *, reverse: bool = False) -> dict[str, Any]:
    """Winsorize p5/p95, population-z-score and clip; abstain on weak peer sets."""
    clean = {ticker: _finite(value) for ticker, value in values.items()}
    eligible = {ticker: value for ticker, value in clean.items() if value is not None}
    scores: dict[str, float | None] = {ticker: None for ticker in values}
    if len(eligible) < MIN_PEERS:
        return {"scores": scores, "status": "UNAVAILABLE", "valid_peer_count": len(eligible),
                "reason": f"Minimum {MIN_PEERS} valid peers required; found {len(eligible)}."}

    low, high = _quantile(list(eligible.values()), 0.05), _quantile(list(eligible.values()), 0.95)
    winsorized = {ticker: min(high, max(low, value)) for ticker, value in eligible.items()}
    mean = sum(winsorized.values()) / len(winsorized)
    variance = sum((value - mean) ** 2 for value in winsorized.values()) / len(winsorized)
    std = math.sqrt(variance)
    if std <= 0 or not math.isfinite(std):
        return {"scores": scores, "status": "UNAVAILABLE", "valid_peer_count": len(eligible),
                "reason": "Cross-sectional standard deviation is zero or invalid."}
    direction = -1 if reverse else 1
    for ticker, value in winsorized.items():
        scores[ticker] = max(-3.0, min(3.0, direction * (value - mean) / std))
    return {"scores": scores, "status": "AVAILABLE", "valid_peer_count": len(eligible),
            "winsor_limits": [low, high], "mean": mean, "population_std": std,
            "reason": None}


def combine_factor_components(components: dict[str, dict[str, Any]]) -> dict[str, Any]:
    valid = [float(value["score"]) for value in components.values()
             if isinstance(value, dict) and value.get("status") == "AVAILABLE"
             and _finite(value.get("score")) is not None]
    total = len(components)
    if not valid:
        return {"score": None, "status": "UNAVAILABLE", "available_components": 0}
    score = max(-3.0, min(3.0, sum(valid) / len(valid)))
    status = "AVAILABLE" if len(valid) == total else "PARTIAL"
    return {"score": score, "status": status, "available_components": len(valid)}


def earnings_yield_from_forward_pe(forward_pe: float | None, *, verified: bool = True) -> dict[str, Any]:
    """Invert only a verified positive forward P/E; preserve all other states."""
    pe = _finite(forward_pe)
    if not verified:
        return {"value": None, "status": "UNAVAILABLE", "reason": "Company-report source is not verified."}
    if pe is None:
        return {"value": None, "status": "UNAVAILABLE", "reason": "Forward P/E missing or invalid in company report."}
    if pe <= 0:
        return {"value": None, "status": "NOT_COMPARABLE", "reason": "Forward P/E is non-positive; not inverted."}
    return {"value": 1.0 / pe, "status": "AVAILABLE", "reason": None}


def momentum_components(closes: list[float], *, verified: bool = True) -> dict[str, Any]:
    """Return 12-1 price momentum and distance to MA200 from ordered closes."""
    prices = [_finite(value) for value in closes]
    if not verified:
        return {"momentum_12_1": None, "price_vs_ma200": None, "status": "UNAVAILABLE",
                "reason": "Issuer daily snapshot is not fully verified."}
    if any(value is None or value <= 0 for value in prices):
        return {"momentum_12_1": None, "price_vs_ma200": None, "status": "UNAVAILABLE",
                "reason": "Price series contains missing or non-positive closes."}
    if len(prices) < 253:
        return {"momentum_12_1": None, "price_vs_ma200": None, "status": "UNAVAILABLE",
                "reason": f"Only {len(prices)} closes; 253 required for 12-1 return and MA200."}
    values = [float(value) for value in prices]
    gaps = [b - a for a, b in zip(values, values[1:])]
    if not all(math.isfinite(value) for value in gaps):
        return {"momentum_12_1": None, "price_vs_ma200": None, "status": "UNAVAILABLE", "reason": "Invalid price intervals."}
    ma200 = sum(values[-200:]) / 200
    return {"momentum_12_1": values[-22] / values[-253] - 1,
            "price_vs_ma200": values[-1] / ma200 - 1, "status": "AVAILABLE", "reason": None}


def score_peer_groups(values: dict[str, float | None], groups: dict[str, str], *, reverse: bool = False) -> dict[str, float | None]:
    """Standardize each peer group independently (e.g. financial vs non-financial)."""
    result = {ticker: None for ticker in values}
    labels = sorted({groups.get(ticker, "unclassified") for ticker in values})
    for label in labels:
        members = [ticker for ticker in values if groups.get(ticker, "unclassified") == label]
        result.update(score_cross_section({ticker: values[ticker] for ticker in members}, reverse=reverse)["scores"])
    return result


def _company_report(root: Path, ticker: str) -> tuple[dict[str, Any], list[str], str | None]:
    path = root / "data/raw/sectors/company_report" / ticker / "company_report.json"
    payload, metadata, issues = _read_snapshot(path, root)
    if not isinstance(payload, dict):
        return {}, issues or ["Company report is missing or malformed."], None
    if str(payload.get("symbol", "")).replace(".JK", "").upper() != ticker:
        issues.append("Company report symbol does not match ticker.")
    if str(metadata.get("symbol", "")).replace(".JK", "").upper() != ticker:
        issues.append("Company report metadata symbol does not match ticker.")
    return payload, issues, path.relative_to(root).as_posix()


def _latest_ratio(report: dict[str, Any], section: str, field: str) -> tuple[float | None, str | None]:
    ratios = report.get("financials", {}).get("historical_financial_ratio", [])
    candidates: list[tuple[int, float]] = []
    if isinstance(ratios, list):
        for row in ratios:
            if not isinstance(row, dict):
                continue
            year = str(row.get("year", ""))
            value = _finite(row.get(section, {}).get(field)) if isinstance(row.get(section), dict) else None
            if value is not None and year.isdigit():
                candidates.append((int(year), value))
    if not candidates:
        return None, None
    year, value = max(candidates)
    return value, str(year)


def _daily_returns(snapshot: dict[str, Any], index_returns: dict[str, float]) -> tuple[list[tuple[str, float, float]], str | None]:
    if snapshot.get("data_quality") != "VERIFIED":
        return [], "Issuer daily snapshot is not fully verified: " + ("; ".join(snapshot.get("issues", [])) or snapshot.get("data_quality", "unknown"))
    rows = snapshot.get("series", [])
    by_date = {row["date"]: _finite(row.get("close")) for row in rows if isinstance(row, dict)}
    ordered = sorted((day, value) for day, value in by_date.items() if value is not None)
    index_dates = sorted(index_returns)
    index_pos = {day: position for position, day in enumerate(index_dates)}
    aligned: list[tuple[str, float, float]] = []
    for (previous_day, previous), (day, current) in zip(ordered, ordered[1:]):
        if previous <= 0 or day not in index_returns or previous_day not in index_pos:
            continue
        if index_pos[day] != index_pos[previous_day] + 1 or (date.fromisoformat(day) - date.fromisoformat(previous_day)).days > 7:
            continue
        aligned.append((day, current / previous - 1, index_returns[day]))
    return aligned, None


def _regression_components(aligned: list[tuple[str, float, float]]) -> tuple[float | None, float | None, str | None]:
    if len(aligned) < MIN_ALIGNED_RETURNS:
        return None, None, f"Only {len(aligned)} aligned daily returns; {MIN_ALIGNED_RETURNS} required."
    ys = [row[1] for row in aligned]
    xs = [row[2] for row in aligned]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    var_x = sum((value - mean_x) ** 2 for value in xs)
    if var_x <= 0:
        return None, None, "IHSG return variance is zero."
    beta = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / var_x
    alpha = mean_y - beta * mean_x
    residuals = [y - alpha - beta * x for x, y in zip(xs, ys)]
    residual_std = math.sqrt(sum(value * value for value in residuals) / len(residuals))
    return beta, residual_std, None


def _source_fingerprint(root: Path, files: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(set(files)):
        path = root / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _artifact_fingerprint(payload: dict[str, Any]) -> str:
    core = {key: value for key, value in payload.items() if key != "artifact_fingerprint"}
    # Build time is operational metadata, not a content change. Stable identity
    # lets the MATLAB camera remain bound to unchanged snapshot-derived scores.
    if isinstance(core.get("as_of"), dict):
        core["as_of"] = {key: value for key, value in core["as_of"].items() if key != "computed_at_utc"}
    encoded = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _published_artifact(payload: dict[str, Any]) -> dict[str, Any]:
    published = {key: value for key, value in payload.items() if key != "artifact_fingerprint"}
    published["artifact_fingerprint"] = _artifact_fingerprint(published)
    return published


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def write_factor_zoo_artifact(root: Path, payload: dict[str, Any]) -> Path:
    """Atomically publish the single factor-data artifact MATLAB and web share."""
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported Factor Zoo payload schema")
    published = _published_artifact(payload)
    target = root / "docs/prototypes/portfolio-factor-zoo-data.json"
    _write_json_atomic(target, published)
    return target


def export_factor_zoo_artifact(root: Path, output: Path | None = None) -> dict[str, Any]:
    """Build from saved source snapshots and atomically export shared JSON."""
    payload = build_factor_zoo_payload(root)
    if output is None:
        path = write_factor_zoo_artifact(root, payload)
        published = _published_artifact(payload)
    else:
        published = _published_artifact(payload)
        path = output
        _write_json_atomic(path, published)
    return {"path": path, "schema_version": payload["schema_version"],
            "artifact_fingerprint": published.get("artifact_fingerprint", payload.get("artifact_fingerprint")),
            "source_fingerprint": payload["sources"]["sha256"], "issuer_count": len(payload["records"])}


def read_factor_zoo_view(root: Path) -> dict[str, Any]:
    """Read validated MATLAB camera state or return a safe waiting state."""
    artifact_path = root / "docs/prototypes/portfolio-factor-zoo-data.json"
    view_path = root / "docs/prototypes/portfolio-factor-zoo-view.json"
    artifact_fingerprint = None
    if artifact_path.is_file():
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("Factor Zoo data artifact is unreadable") from exc
        if not isinstance(artifact, dict) or artifact.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Factor Zoo data artifact schema is invalid")
        artifact_fingerprint = artifact.get("artifact_fingerprint")
    if not view_path.is_file():
        return {"schema_version": SCHEMA_VERSION, "status": "WAITING_FOR_MATLAB",
                "azimuth": -37.5, "elevation": 28.0, "updated_at_utc": None,
                "artifact_fingerprint": artifact_fingerprint}
    try:
        state = json.loads(view_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("MATLAB camera-state JSON is unreadable") from exc
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("MATLAB camera-state schema is invalid")
    azimuth, elevation = _finite(state.get("azimuth")), _finite(state.get("elevation"))
    if azimuth is None or elevation is None or not -90 <= elevation <= 90:
        raise ValueError("MATLAB camera-state angles are invalid")
    if not isinstance(state.get("updated_at_utc"), str) or not state["updated_at_utc"].strip():
        raise ValueError("MATLAB camera-state timestamp is missing")
    if not artifact_fingerprint or state.get("artifact_fingerprint") != artifact_fingerprint:
        raise ValueError("MATLAB camera state belongs to a different or missing data artifact")
    return {"schema_version": SCHEMA_VERSION, "status": "AVAILABLE", "azimuth": azimuth,
            "elevation": elevation, "updated_at_utc": state["updated_at_utc"],
            "artifact_fingerprint": artifact_fingerprint}


def build_factor_zoo_payload(root: Path) -> dict[str, Any]:
    """Read current LQ45 local snapshots and build transparent descriptive scores."""
    universe = load_lq45_universe(root)
    symbols = universe.get("symbols", []) if universe.get("data_quality") in {"VERIFIED", "PARTIAL"} else []
    tickers = [str(item["ticker"]).upper() for item in symbols if item.get("ticker")]
    if not tickers:
        raise ValueError("No saved LQ45 universe is available.")

    sectors, sub_sectors, classification_issues, verified_members = _current_classifications(root, tickers)
    reports: dict[str, dict[str, Any]] = {}
    report_issues: dict[str, list[str]] = {}
    report_files: dict[str, str | None] = {}
    for ticker in tickers:
        report, issues, source = _company_report(root, ticker)
        if ticker not in verified_members:
            issues.extend(issue for issue in classification_issues if issue.startswith(f"{ticker}:"))
        reports[ticker], report_issues[ticker], report_files[ticker] = report, sorted(set(issues)), source

    ihsg = load_index_daily_snapshot(root, "ihsg")
    index_rows = ihsg.get("series", []) if ihsg.get("data_quality") == "VERIFIED" else []
    index_prices = {row["date"]: float(row["price"]) for row in index_rows}
    index_dates = sorted(index_prices)
    index_returns: dict[str, float] = {}
    for old_day, day in zip(index_dates, index_dates[1:]):
        index_returns[day] = index_prices[day] / index_prices[old_day] - 1
    index_position = {day: i for i, day in enumerate(index_dates)}

    raw: dict[str, dict[str, Any]] = {}
    issuer_sources: dict[str, list[str]] = {}
    component_values: dict[str, dict[str, float | None]] = {
        "earnings_yield": {}, "dividend_yield": {}, "roe": {}, "debt_to_equity": {},
        "momentum_12_1": {}, "price_vs_ma200": {}, "beta_ihsg": {}, "idiosyncratic_volatility": {},
    }
    daily_snapshots: dict[str, dict[str, Any]] = {}
    aligned_returns: dict[str, list[tuple[str, float, float]]] = {}
    for ticker in tickers:
        report = reports[ticker]
        is_verified = not report_issues[ticker]
        valuation = report.get("valuation", {}) if isinstance(report.get("valuation"), dict) else {}
        pe = _finite(valuation.get("forward_pe"))
        div = report.get("dividend", {}) if isinstance(report.get("dividend"), dict) else {}
        dividend_yield = _finite(div.get("yield_ttm"))
        roe, roe_year = _latest_ratio(report, "profitability", "roe")
        der, der_year = _latest_ratio(report, "leverage", "debt_to_equity_ratio")
        if not is_verified:
            pe = dividend_yield = roe = der = None
        ey = earnings_yield_from_forward_pe(pe, verified=is_verified)
        earnings_yield = ey["value"]
        if dividend_yield is not None and dividend_yield < 0:
            dividend_yield = None
        daily = load_issuer_daily(root, ticker)
        daily_snapshots[ticker] = daily
        issuer_sources[ticker] = daily.get("source_files", [])
        rows = daily.get("series", []) if daily.get("data_quality") == "VERIFIED" else []
        closes = [(row["date"], _finite(row.get("close"))) for row in rows]
        closes = [(day, close) for day, close in closes if close is not None and close > 0]
        momentum = ma_distance = None
        momentum_reason = None
        close_values = [value for _, value in closes]
        momentum_result = momentum_components(close_values, verified=daily.get("data_quality") == "VERIFIED")
        momentum, ma_distance = momentum_result["momentum_12_1"], momentum_result["price_vs_ma200"]
        momentum_reason = momentum_result["reason"]
        aligned, align_reason = _daily_returns(daily, index_returns) if index_returns else ([], "IHSG daily snapshot is not fully verified.")
        aligned_returns[ticker] = aligned
        beta, residual_std, regression_reason = _regression_components(aligned)
        reasons = [reason for reason in (momentum_reason, align_reason, regression_reason if regression_reason and aligned else None) if reason]

        component_values["earnings_yield"][ticker] = earnings_yield if is_verified else None
        component_values["dividend_yield"][ticker] = dividend_yield if is_verified else None
        component_values["roe"][ticker] = roe if is_verified else None
        component_values["debt_to_equity"][ticker] = der if is_verified else None
        component_values["momentum_12_1"][ticker] = momentum
        component_values["price_vs_ma200"][ticker] = ma_distance
        component_values["beta_ihsg"][ticker] = beta
        component_values["idiosyncratic_volatility"][ticker] = residual_std
        raw[ticker] = {
            "ticker": ticker, "company": next((item.get("company") for item in symbols if item.get("ticker") == ticker), ticker),
            "sector": sectors.get(ticker), "sub_sector": sub_sectors.get(ticker),
            "report_as_of": valuation.get("latest_close_date"),
            "financial_ratio_years": {"roe": roe_year, "debt_to_equity": der_year},
            "components": {
                "earnings_yield": {**ey, "source_value": pe},
                "dividend_yield": {"value": dividend_yield, "source_value": _finite(div.get("yield_ttm")),
                                   "status": "AVAILABLE" if dividend_yield is not None else "UNAVAILABLE",
                                   "reason": None if dividend_yield is not None else "TTM dividend yield missing in verified company report."},
                "roe": {"value": roe, "status": "AVAILABLE" if roe is not None else "UNAVAILABLE", "reason": None if roe is not None else "No valid ROE in historical financial ratios."},
                "debt_to_equity": {"value": der, "status": "AVAILABLE" if der is not None else "UNAVAILABLE", "reason": None if der is not None else "No valid debt-to-equity ratio in historical financial ratios."},
                "momentum_12_1": {"value": momentum, "status": "AVAILABLE" if momentum is not None else "UNAVAILABLE", "reason": momentum_reason},
                "price_vs_ma200": {"value": ma_distance, "status": "AVAILABLE" if ma_distance is not None else "UNAVAILABLE", "reason": momentum_reason},
                "beta_ihsg": {"value": beta, "status": "AVAILABLE" if beta is not None else "UNAVAILABLE", "reason": regression_reason or align_reason},
                "idiosyncratic_volatility": {"value": residual_std, "status": "AVAILABLE" if residual_std is not None else "UNAVAILABLE", "reason": regression_reason or align_reason},
            },
            "data_quality": {"company_report": "VERIFIED" if is_verified else "UNVERIFIED",
                             "daily": daily.get("data_quality"), "daily_issues": daily.get("issues", []),
                             "daily_observation_count": daily.get("observation_count", 0),
                             "daily_coverage_start": daily.get("coverage_start"),
                             "daily_coverage_end": daily.get("coverage_end"),
                             "aligned_ihsg_returns": len(aligned), "feature_notes": reasons},
            "scores": {}, "source_files": {"company_report": report_files[ticker], "daily": issuer_sources[ticker]},
        }

    raw_scores: dict[str, dict[str, float | None]] = {}
    for component_name, values in component_values.items():
        raw_scores[component_name] = score_cross_section(values, reverse=component_name in {"debt_to_equity", "beta_ihsg", "idiosyncratic_volatility"})["scores"]
        for ticker in tickers:
            raw[ticker]["components"][component_name]["score"] = raw_scores[component_name][ticker]
            if raw_scores[component_name][ticker] is None and raw[ticker]["components"][component_name]["value"] is not None:
                raw[ticker]["components"][component_name]["status"] = "INSUFFICIENT_PEERS"

    groups: dict[str, list[str]] = {"financial": [], "non_financial": []}
    for ticker in tickers:
        group = "financial" if "financial" in str(sectors.get(ticker, "")).casefold() or "bank" in str(sectors.get(ticker, "")).casefold() else "non_financial"
        raw[ticker]["peer_group"] = group
        groups[group].append(ticker)
    peer_groups = {ticker: group for group, members in groups.items() for ticker in members}
    quality_scores: dict[str, dict[str, float | None]] = {
        metric: score_peer_groups(component_values[metric], peer_groups, reverse=metric == "debt_to_equity")
        for metric in ("roe", "debt_to_equity")
    }
    for ticker in tickers:
        for metric in quality_scores:
            raw[ticker]["components"][metric]["score"] = quality_scores[metric][ticker]
            if quality_scores[metric][ticker] is None and raw[ticker]["components"][metric]["value"] is not None:
                raw[ticker]["components"][metric]["status"] = "INSUFFICIENT_PEERS"
        factor_component_map = {
            "value": {"earnings_yield": raw[ticker]["components"]["earnings_yield"], "dividend_yield": raw[ticker]["components"]["dividend_yield"]},
            "quality": {"roe": raw[ticker]["components"]["roe"], "debt_to_equity": raw[ticker]["components"]["debt_to_equity"]},
            "momentum": {"momentum_12_1": raw[ticker]["components"]["momentum_12_1"], "price_vs_ma200": raw[ticker]["components"]["price_vs_ma200"]},
            "low_volatility": {"beta_ihsg": raw[ticker]["components"]["beta_ihsg"], "idiosyncratic_volatility": raw[ticker]["components"]["idiosyncratic_volatility"]},
        }
        for factor, components in factor_component_map.items():
            result = combine_factor_components(components)
            raw[ticker]["scores"][factor] = result

    leaderboards: dict[str, list[dict[str, Any]]] = {}
    for factor in ("value", "quality", "momentum", "low_volatility"):
        eligible = [record for record in raw.values() if record["scores"][factor]["status"] == "AVAILABLE"]
        eligible.sort(key=lambda record: (-record["scores"][factor]["score"], record["ticker"]))
        leaderboards[factor] = [{"ticker": record["ticker"], "score": record["scores"][factor]["score"],
                                 "components": record["scores"][factor]["available_components"], "as_of": record["report_as_of"]}
                                for record in eligible[:5]]

    source_files = [universe.get("source_file", ""), *[file for file in report_files.values() if file],
                    *[file for files in issuer_sources.values() for file in files], *ihsg.get("source_files", [])]
    source_files = [name for name in source_files if name]
    index_daily_status = ihsg.get("data_quality")
    latest_index_date = ihsg.get("coverage_end")
    coverage = {factor: {status: sum(row["scores"][factor]["status"] == status for row in raw.values())
                         for status in ("AVAILABLE", "PARTIAL", "UNAVAILABLE")} for factor in leaderboards}
    return {
        "schema_version": SCHEMA_VERSION, "formula_version": FORMULA_VERSION,
        "provider": "Sectors.app", "source_class": "derived_metric",
        "universe": {"name": "LQ45", "count": len(tickers), "membership": "current snapshot only; historical membership is unavailable",
                     "quality": universe.get("data_quality"), "issues": universe.get("issues", [])},
        "as_of": {"price": latest_index_date, "company_report_dates": sorted({row["report_as_of"] for row in raw.values() if row["report_as_of"]}),
                  "computed_at_utc": datetime.now(timezone.utc).isoformat()},
        "sources": {"files": source_files, "sha256": _source_fingerprint(root, source_files),
                    "ihsg_quality": index_daily_status, "ihsg_sessions": len(index_dates),
                    "ihsg_issues": ihsg.get("issues", [])},
        "method": {"standardization": "cross-sectional p5/p95 winsorized population z-score; clipped to [-3, 3]",
                   "minimum_peers": MIN_PEERS, "minimum_aligned_returns": MIN_ALIGNED_RETURNS,
                   "momentum": "close[t-21] / close[t-252] - 1 and close[t] / mean(last 200 closes) - 1",
                   "risk_model": "aligned daily simple returns; beta and intercept OLS residual population standard deviation versus IHSG",
                   "quality_peers": "financial and non-financial sectors scored separately",
                   "limitations": ["Current LQ45 membership only; survivorship bias is possible.",
                                   "Raw closing prices may not be adjusted for dividends, splits, or rights issues.",
                                   "Company-report snapshot dates can differ from price as-of dates.",
                                   "Scores are descriptive cross-sectional characteristics, not return forecasts or validated alpha."]},
        "records": list(raw.values()), "leaderboards": leaderboards,
        "coverage": {"issuer_count": len(tickers), "index_daily_status": index_daily_status, "factors": coverage,
                     "quality_groups": {name: len(members) for name, members in groups.items()}},
        "chart": {"type": "scatter3", "x": "value", "y": "momentum", "z": "quality", "color": "low_volatility",
                  "axis_domain": [-3, 3], "plottable_status": "AVAILABLE"},
    }
