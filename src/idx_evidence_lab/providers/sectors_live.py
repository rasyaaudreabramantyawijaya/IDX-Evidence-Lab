"""Approval-gated Sectors API client.

Only Sectors.app is allowed as a source-data host. The client reads the API key
from ``SECTORS_API_KEY`` and never prints or persists it. It is intentionally
limited to an explicit command so importing this module cannot make a request.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import ssl
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlencode, urljoin, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..core.schemas import SourceClass
from .source_policy import SourcePolicy


BASE_URL = "https://api.sectors.app/"
ALLOWED_HOST = "api.sectors.app"


class SectorsClientError(RuntimeError):
    pass


@dataclass
class RequestBudget:
    maximum: int = 300
    used: int = 0

    def consume(self, count: int = 1) -> None:
        if count < 1:
            raise ValueError("Request count must be positive")
        if self.used + count > self.maximum:
            raise SectorsClientError(
                f"Request budget exceeded: {self.used + count}>{self.maximum}"
            )
        self.used += count


class SectorsClient:
    def __init__(self, api_key: str, *, budget: RequestBudget | None = None, timeout: int = 30):
        if not api_key or not api_key.strip():
            raise SectorsClientError("SECTORS_API_KEY is missing")
        self._api_key = api_key.strip()
        self.budget = budget or RequestBudget()
        self.timeout = timeout
        try:
            import certifi
            self._ssl_context = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            self._ssl_context = ssl.create_default_context()
        SourcePolicy().validate(SourceClass.SECTORS_SOURCE_DATA, "Sectors.app", network=True)

    @staticmethod
    def _url(path: str, params: Dict[str, str] | None = None) -> str:
        url = urljoin(BASE_URL, path.lstrip("/"))
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise SectorsClientError("Only HTTPS requests to api.sectors.app are allowed")
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def get_json(self, path: str, params: Dict[str, str] | None = None) -> tuple[Any, Dict[str, Any]]:
        url = self._url(path, params)
        self.budget.consume()
        request = Request(
            url,
            method="GET",
            headers={
                "Authorization": self._api_key,
                "Accept": "application/json",
                "User-Agent": "IDX-Evidence-Lab/0.1",
            },
        )
        retrieved_at = datetime.now(timezone.utc).isoformat()
        try:
            with urlopen(request, timeout=self.timeout, context=self._ssl_context) as response:
                raw = response.read()
                status = getattr(response, "status", 200)
        except HTTPError as exc:  # sanitized; never includes the API key
            raise SectorsClientError(f"Sectors returned HTTP {exc.code}") from exc
        except URLError as exc:  # sanitized; never includes the API key
            reason_type = type(exc.reason).__name__ if exc.reason is not None else "UnknownReason"
            reason_text = str(exc.reason).replace(self._api_key, "<REDACTED>")[:160]
            raise SectorsClientError(f"Sectors request failed: URLError/{reason_type}: {reason_text}") from exc
        except Exception as exc:  # sanitized; never includes the API key
            raise SectorsClientError(f"Sectors request failed: {type(exc).__name__}") from exc
        if status != 200:
            raise SectorsClientError(f"Sectors returned HTTP {status}")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SectorsClientError("Sectors response was not valid UTF-8 JSON") from exc
        metadata = {
            "provider": "Sectors.app",
            "source_class": SourceClass.SECTORS_SOURCE_DATA.value,
            "endpoint": url,
            "retrieved_at": retrieved_at,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "http_status": status,
            "request_number": self.budget.used,
            "request_budget": self.budget.maximum,
        }
        return payload, metadata


def save_snapshot(payload: Any, metadata: Dict[str, Any], output_dir: Path, stem: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    data_path = output_dir / f"{stem}.json"
    metadata_path = output_dir / f"{stem}.metadata.json"
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return data_path, metadata_path


def fetch_lq45_universe(output_dir: Path) -> tuple[Path, Path, int]:
    key = os.environ.get("SECTORS_API_KEY", "")
    client = SectorsClient(key, budget=RequestBudget(maximum=300))
    # The former v1 index endpoint is retired (HTTP 410).  v2 exposes index
    # membership through the structured Companies Screener query.
    payload, metadata = client.get_json(
        "/v2/companies/",
        {
            "where": "indices in ['LQ45']",
            "order_by": "symbol",
            "limit": "100",
            "offset": "0",
            "include_query_values": "true",
        },
    )
    data_path, metadata_path = save_snapshot(
        payload, metadata, output_dir, "lq45-universe"
    )
    return data_path, metadata_path, client.budget.used


def _records(payload: Any) -> list[dict[str, Any]]:
    """Return row-like objects from a Sectors daily response."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _daily_first_observation(ticker: str, daily_dir: Path) -> date:
    dates: list[date] = []
    ticker_dir = daily_dir / ticker
    if not ticker_dir.is_dir():
        raise SectorsClientError(f"Daily source directory missing for {ticker}")
    for path in ticker_dir.glob("*.json"):
        if path.name.endswith("_meta.json"):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SectorsClientError(f"Cannot read daily snapshot for {ticker}") from exc
        for row in _records(payload):
            raw_date = row.get("date") or row.get("trading_date") or row.get("datetime")
            if raw_date:
                try:
                    dates.append(date.fromisoformat(str(raw_date)[:10]))
                except ValueError:
                    continue
    if not dates:
        raise SectorsClientError(f"No dated daily observations found for {ticker}")
    return min(dates)


def _read_universe_symbols(path: Path) -> list[str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SectorsClientError("Cannot read the approved LQ45 universe snapshot") from exc
    rows = payload.get("results", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise SectorsClientError("LQ45 universe snapshot has an unexpected schema")
    symbols = sorted({
        str(row.get("symbol", "")).removesuffix(".JK").strip().upper()
        for row in rows if isinstance(row, dict) and row.get("symbol")
    })
    if len(symbols) != 45:
        raise SectorsClientError(f"Expected 45 LQ45 symbols; found {len(symbols)}")
    return symbols


def _date_windows(start: date, end: date, window_days: int = 90) -> list[tuple[date, date]]:
    if window_days < 1 or end < start:
        raise ValueError("Invalid date range or window size")
    windows = []
    cursor = start
    while cursor <= end:
        window_end = min(cursor + timedelta(days=window_days - 1), end)
        windows.append((cursor, window_end))
        cursor = window_end + timedelta(days=1)
    return windows


def _snapshot_is_reusable(data_path: Path, metadata_path: Path, endpoint: str) -> bool:
    if not data_path.is_file() or not metadata_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        raw = data_path.read_bytes()
    except (OSError, json.JSONDecodeError):
        return False
    saved_endpoint = metadata.get("endpoint", "")
    return (
        metadata.get("provider") == "Sectors.app"
        and metadata.get("http_status") == 200
        and urlparse(saved_endpoint).path == endpoint
        and metadata.get("snapshot_sha256") == hashlib.sha256(raw).hexdigest()
    )


def fetch_filings(
    symbols: list[str],
    output_dir: Path,
    *,
    start: date,
    end: date,
    limit: int = 30,
    offset: int = 0,
    max_requests: int = 15,
    client: SectorsClient | None = None,
) -> tuple[int, int]:
    """Fetch one approved filings page per symbol; never paginate automatically."""
    normalized = [symbol.strip().upper().removesuffix(".JK") for symbol in symbols]
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError("Symbols must be non-empty and unique")
    if any(not symbol or len(symbol) != 4 or not symbol.isalnum() for symbol in normalized):
        raise ValueError("Each filings symbol must be a four-character IDX ticker")
    if end < start or not (1 <= limit <= 30) or offset < 0:
        raise ValueError("Invalid filings date range, limit, or offset")
    if max_requests < len(normalized):
        raise SectorsClientError(
            f"Approved request cap ({max_requests}) is below requested symbols ({len(normalized)})"
        )
    if client is None:
        client = SectorsClient(
            os.environ.get("SECTORS_API_KEY", ""),
            budget=RequestBudget(maximum=max_requests),
        )
    elif client.budget.maximum < max_requests:
        raise SectorsClientError("Injected client budget is below approved maximum")

    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "request_ledger.jsonl"
    successes = 0
    for symbol in normalized:
        params = {
            "symbol": symbol,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "limit": str(limit),
            "offset": str(offset),
        }
        with ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({
                "event": "attempt",
                "endpoint": "/v2/filings/",
                "symbol": symbol,
                "start": params["start"],
                "end": params["end"],
                "limit": limit,
                "offset": offset,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
        try:
            payload, metadata = client.get_json("/v2/filings/", params)
        except Exception as exc:
            with ledger_path.open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({
                    "event": "result",
                    "endpoint": "/v2/filings/",
                    "symbol": symbol,
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            raise
        metadata.update({
            "symbol": symbol,
            "requested_start": params["start"],
            "requested_end": params["end"],
            "limit": limit,
            "offset": offset,
            "pagination_followed": False,
        })
        data_path, metadata_path = save_snapshot(payload, metadata, output_dir / symbol, "filings")
        metadata["snapshot_sha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        with ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({
                "event": "result",
                "endpoint": "/v2/filings/",
                "symbol": symbol,
                "status": "success",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
        successes += 1
        print(f"Saved filings {symbol} ({successes}/{max_requests})")
    return successes, client.budget.used


def fetch_lq45_foreign_flow(
    universe_path: Path,
    daily_dir: Path,
    output_dir: Path,
    *,
    start: date,
    end: date,
    max_requests: int = 585,
    window_days: int = 90,
    request_delay_seconds: float = 0.0,
    client: SectorsClient | None = None,
) -> tuple[int, int, int]:
    """Fetch foreign-flow snapshots aligned to each ticker's available daily history.

    Each inclusive window is at most 90 calendar days. Completed, hash-verified
    snapshots are skipped, so interrupted runs can resume without duplicate calls.
    """
    symbols = _read_universe_symbols(universe_path)
    if request_delay_seconds < 0:
        raise ValueError("Request delay cannot be negative")
    if client is None:
        key = os.environ.get("SECTORS_API_KEY", "")
        ledger_path = output_dir / "request_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        prior_attempts = 0
        if ledger_path.is_file():
            for line in ledger_path.read_text(encoding="utf-8").splitlines():
                try:
                    if json.loads(line).get("event") == "attempt":
                        prior_attempts += 1
                except json.JSONDecodeError:
                    continue
        remaining_budget = max_requests - prior_attempts
        if remaining_budget < 0:
            raise SectorsClientError(
                f"Persisted request ledger already exceeds approved cap ({prior_attempts}>{max_requests})"
            )
        client = SectorsClient(key, budget=RequestBudget(maximum=remaining_budget))
    elif client.budget.maximum < max_requests:
        raise SectorsClientError("Injected client budget is below requested maximum")
    else:
        ledger_path = output_dir / "request_ledger.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)

    request_count = 0
    skipped_count = 0
    ledger_path = output_dir / "request_ledger.jsonl"
    for ticker in symbols:
        ticker_start = max(start, _daily_first_observation(ticker, daily_dir))
        if ticker_start > end:
            continue
        for window_start, window_end in _date_windows(ticker_start, end, window_days):
            stem = f"{ticker}_{window_start.isoformat()}_{window_end.isoformat()}"
            data_path = output_dir / ticker / f"{stem}.json"
            metadata_path = output_dir / ticker / f"{stem}.metadata.json"
            endpoint_path = f"/v2/foreign-flow/{ticker}/"
            if _snapshot_is_reusable(data_path, metadata_path, endpoint_path):
                skipped_count += 1
                continue
            if client.budget.used >= client.budget.maximum:
                raise SectorsClientError(
                    f"Foreign-flow request cap reached ({max_requests}); snapshots saved so far are resumable"
                )
            attempt = {
                "event": "attempt",
                "ticker": ticker,
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            with ledger_path.open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps(attempt, ensure_ascii=False) + "\n")
            try:
                if request_delay_seconds:
                    time.sleep(request_delay_seconds)
                payload, metadata = client.get_json(
                    endpoint_path,
                    {"start": window_start.isoformat(), "end": window_end.isoformat()},
                )
            except Exception as exc:
                with ledger_path.open("a", encoding="utf-8") as ledger:
                    ledger.write(json.dumps({
                        "event": "result",
                        "ticker": ticker,
                        "start": window_start.isoformat(),
                        "end": window_end.isoformat(),
                        "status": "error",
                        "error_type": type(exc).__name__,
                        "recorded_at": datetime.now(timezone.utc).isoformat(),
                    }, ensure_ascii=False) + "\n")
                raise
            metadata.update({
                "ticker": ticker,
                "requested_start": window_start.isoformat(),
                "requested_end": window_end.isoformat(),
                "window_days": window_days,
            })
            data_path, metadata_path = save_snapshot(payload, metadata, output_dir / ticker, stem)
            metadata["snapshot_sha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            with ledger_path.open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({
                    "event": "result",
                    "ticker": ticker,
                    "start": window_start.isoformat(),
                    "end": window_end.isoformat(),
                    "status": "success",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            request_count += 1
            print(f"Saved {ticker} {window_start}..{window_end} ({request_count}/{max_requests})")
    return request_count, skipped_count, client.budget.used


def fetch_index_daily(
    output_dir: Path,
    *,
    index_code: str,
    start: date,
    end: date,
    max_requests: int = 13,
    window_days: int = 90,
    request_delay_seconds: float = 0.0,
    ledger_name: str = "request_ledger.jsonl",
    client: SectorsClient | None = None,
) -> tuple[int, int, int]:
    """Fetch approved, non-overlapping daily index-close windows with provenance."""
    index_code = index_code.strip().lower()
    if not index_code.isalnum():
        raise ValueError("Index code must be alphanumeric")
    if request_delay_seconds < 0:
        raise ValueError("Request delay cannot be negative")
    if Path(ledger_name).name != ledger_name or not ledger_name.endswith(".jsonl"):
        raise ValueError("Ledger name must be a .jsonl filename without a directory")
    windows = _date_windows(start, end, window_days)
    if len(windows) > max_requests:
        raise SectorsClientError(
            f"Approved request cap ({max_requests}) is below required windows ({len(windows)})"
        )
    endpoint_path = f"/v2/index-daily/{index_code}/"
    ledger_path = output_dir / ledger_name
    output_dir.mkdir(parents=True, exist_ok=True)
    prior_attempts = 0
    if ledger_path.is_file():
        for line in ledger_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("event") == "attempt":
                prior_attempts += 1
    remaining_budget = max_requests - prior_attempts
    if remaining_budget < 0:
        raise SectorsClientError(
            f"Persisted request ledger already exceeds approved cap ({prior_attempts}>{max_requests})"
        )
    if client is None:
        client = SectorsClient(
            os.environ.get("SECTORS_API_KEY", ""),
            budget=RequestBudget(maximum=remaining_budget),
        )
    elif client.budget.maximum < remaining_budget:
        raise SectorsClientError("Injected client budget is below remaining approved maximum")

    fetched = 0
    reused = 0
    for window_start, window_end in windows:
        stem = f"{index_code}_{window_start.isoformat()}_{window_end.isoformat()}"
        data_path = output_dir / f"{stem}.json"
        metadata_path = output_dir / f"{stem}.metadata.json"
        if _snapshot_is_reusable(data_path, metadata_path, endpoint_path):
            reused += 1
            continue
        if client.budget.used >= client.budget.maximum:
            raise SectorsClientError(
                f"IHSG request cap reached ({max_requests}); saved windows are resumable"
            )
        request_details = {
            "event": "attempt",
            "index_code": index_code,
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        with ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps(request_details, ensure_ascii=False) + "\n")
        try:
            if request_delay_seconds:
                time.sleep(request_delay_seconds)
            payload, metadata = client.get_json(
                endpoint_path,
                {"start": window_start.isoformat(), "end": window_end.isoformat()},
            )
        except Exception as exc:
            with ledger_path.open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({
                    "event": "result",
                    "index_code": index_code,
                    "start": window_start.isoformat(),
                    "end": window_end.isoformat(),
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                }, ensure_ascii=False) + "\n")
            raise
        metadata.update({
            "index_code": index_code,
            "requested_start": window_start.isoformat(),
            "requested_end": window_end.isoformat(),
            "window_days": window_days,
            "window_inclusive_days": (window_end - window_start).days + 1,
        })
        data_path, metadata_path = save_snapshot(payload, metadata, output_dir, stem)
        metadata["snapshot_sha256"] = hashlib.sha256(data_path.read_bytes()).hexdigest()
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        with ledger_path.open("a", encoding="utf-8") as ledger:
            ledger.write(json.dumps({
                "event": "result",
                "index_code": index_code,
                "start": window_start.isoformat(),
                "end": window_end.isoformat(),
                "status": "success",
                "snapshot": data_path.name,
                "sha256": metadata["snapshot_sha256"],
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }, ensure_ascii=False) + "\n")
        fetched += 1
        print(f"Saved {index_code.upper()} {window_start}..{window_end} ({fetched}/{len(windows)})")
    return fetched, reused, client.budget.used


def fetch_ihsg_index_daily(
    output_dir: Path,
    *,
    start: date,
    end: date,
    max_requests: int = 13,
    window_days: int = 90,
    request_delay_seconds: float = 0.0,
    client: SectorsClient | None = None,
) -> tuple[int, int, int]:
    """Backward-compatible IHSG daily-close collection wrapper."""
    return fetch_index_daily(
        output_dir,
        index_code="ihsg",
        start=start,
        end=end,
        max_requests=max_requests,
        window_days=window_days,
        request_delay_seconds=request_delay_seconds,
        client=client,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Approval-gated Sectors API client")
    subparsers = parser.add_subparsers(dest="command", required=True)
    universe = subparsers.add_parser("universe", help="Fetch the current LQ45 universe")
    universe.add_argument(
        "--output-dir", default="data/raw/sectors", type=Path,
        help="Directory for raw JSON and provenance metadata",
    )
    foreign_flow = subparsers.add_parser(
        "foreign-flow", help="Fetch LQ45 foreign-flow windows aligned to daily history"
    )
    foreign_flow.add_argument("--universe", default="data/raw/sectors/lq45-universe.json", type=Path)
    foreign_flow.add_argument("--daily-dir", default="data/raw/sectors/daily", type=Path)
    foreign_flow.add_argument("--output-dir", default="data/raw/sectors/foreign_flow", type=Path)
    foreign_flow.add_argument("--start", default="2023-09-25")
    foreign_flow.add_argument("--end", default="2026-09-24")
    foreign_flow.add_argument("--window-days", type=int, default=90)
    foreign_flow.add_argument("--max-requests", type=int, default=585)
    foreign_flow.add_argument("--request-delay-seconds", type=float, default=0.0)
    filings = subparsers.add_parser("filings", help="Fetch one filings page for each explicitly approved symbol")
    filings.add_argument("--symbols", required=True, help="Comma-separated IDX symbols")
    filings.add_argument("--output-dir", default="data/raw/sectors/filings", type=Path)
    filings.add_argument("--start", required=True)
    filings.add_argument("--end", required=True)
    filings.add_argument("--limit", type=int, default=30)
    filings.add_argument("--offset", type=int, default=0)
    filings.add_argument("--max-requests", type=int, default=15)
    ihsg = subparsers.add_parser("ihsg", help="Fetch approved IHSG index-daily windows")
    ihsg.add_argument("--output-dir", default="data/raw/sectors/index_daily/ihsg", type=Path)
    ihsg.add_argument("--start", default="2023-09-25")
    ihsg.add_argument("--end", default="2026-09-24")
    ihsg.add_argument("--window-days", type=int, default=90)
    ihsg.add_argument("--max-requests", type=int, default=13)
    ihsg.add_argument("--request-delay-seconds", type=float, default=1.0)
    lq45 = subparsers.add_parser("lq45-index", help="Fetch approved LQ45 index-daily windows")
    lq45.add_argument("--output-dir", default="data/raw/sectors/index_daily/lq45", type=Path)
    lq45.add_argument("--start", default="2023-09-25")
    lq45.add_argument("--end", default="2026-09-24")
    lq45.add_argument("--window-days", type=int, default=90)
    lq45.add_argument("--max-requests", type=int, default=13)
    lq45.add_argument("--request-delay-seconds", type=float, default=1.0)
    lq45.add_argument(
        "--ledger-name",
        default="request_ledger_2026-09-29_approved_batch.jsonl",
        help="Separate request ledger for this explicitly approved batch",
    )
    args = parser.parse_args()
    if args.command == "universe":
        try:
            data_path, metadata_path, used = fetch_lq45_universe(args.output_dir)
        except SectorsClientError as exc:
            parser.exit(1, f"Blocked: {exc}\n")
        print(f"Saved data: {data_path}")
        print(f"Saved metadata: {metadata_path}")
        print(f"Requests used: {used}/300")
        return 0
    if args.command == "foreign-flow":
        try:
            request_count, skipped_count, used = fetch_lq45_foreign_flow(
                args.universe,
                args.daily_dir,
                args.output_dir,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                max_requests=args.max_requests,
                window_days=args.window_days,
                request_delay_seconds=args.request_delay_seconds,
            )
        except (SectorsClientError, ValueError) as exc:
            parser.exit(1, f"Blocked: {exc}\n")
        print(f"Foreign-flow requests used: {request_count}; verified snapshots reused: {skipped_count}; budget used: {used}/{args.max_requests}")
        return 0
    if args.command == "filings":
        try:
            symbols = [item for item in args.symbols.split(",") if item.strip()]
            fetched, used = fetch_filings(
                symbols,
                args.output_dir,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                limit=args.limit,
                offset=args.offset,
                max_requests=args.max_requests,
            )
        except (SectorsClientError, ValueError) as exc:
            parser.exit(1, f"Blocked: {exc}\n")
        print(f"Filings requests completed: {fetched}; budget used: {used}/{args.max_requests}")
        return 0
    if args.command == "ihsg":
        try:
            fetched, reused, used = fetch_ihsg_index_daily(
                args.output_dir,
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                max_requests=args.max_requests,
                window_days=args.window_days,
                request_delay_seconds=args.request_delay_seconds,
            )
        except (SectorsClientError, ValueError) as exc:
            parser.exit(1, f"Blocked: {exc}\n")
        print(
            f"IHSG windows fetched: {fetched}; verified snapshots reused: {reused}; "
            f"budget used: {used}/{args.max_requests}"
        )
        return 0
    if args.command == "lq45-index":
        try:
            fetched, reused, used = fetch_index_daily(
                args.output_dir,
                index_code="lq45",
                start=date.fromisoformat(args.start),
                end=date.fromisoformat(args.end),
                max_requests=args.max_requests,
                window_days=args.window_days,
                request_delay_seconds=args.request_delay_seconds,
                ledger_name=args.ledger_name,
            )
        except (SectorsClientError, ValueError) as exc:
            parser.exit(1, f"Blocked: {exc}\n")
        print(
            f"LQ45 windows fetched: {fetched}; verified snapshots reused: {reused}; "
            f"budget used: {used}/{args.max_requests}"
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
