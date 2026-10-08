"""Local same-origin web server for the IDX Evidence Lab search prototype."""

from __future__ import annotations

import json
import math
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .config import Settings, load_settings
from .research.legal_corpus import search_legal_corpus
from .research.openrouter_live import OpenRouterError, OpenRouterSearchAdapter, load_local_openrouter_config
from .security import SECURITY_HEADERS, RateLimiter
from .market.market_data import load_ihsg_snapshot, load_issuer_daily, load_local_news, load_lq45_universe, load_sector_heatmap, load_news_universe
from .portfolio.portfolio_analytics import calculate_portfolio_metrics
from .portfolio.portfolio_amounts import allocate_amounts, allocate_lots
from .portfolio.portfolio_data import _current_classifications, load_portfolio_inputs
from .portfolio.portfolio_optimization import equal_weight_portfolio, optimize_portfolio
from .portfolio.portfolio_scenarios import run_walk_forward, simulate_portfolio_scenarios
from .portfolio.portfolio_factors import _published_artifact, build_factor_zoo_payload, read_factor_zoo_view, write_factor_zoo_artifact
from .core.schemas import SearchDocument, SourceClass
from .core.search import LocalSearchIndex
from .research.task_navigation import build_navigation, CAPABILITIES
from .market.screener_analysis import build_screener_analysis
from .studies.studies_registry import catalog as studies_catalog, parse_study_request
from .studies_service import run_study
from .studies.studies_artifacts import StudyArtifactStore


ROOT = Path(__file__).resolve().parents[2]
OPENROUTER_ENV_FILE = ROOT / ".env.local"
PROTOTYPE = ROOT / "docs" / "prototypes" / "idx-evidence-lab-user-journey.html"
PUBLIC_PROTOTYPE_ASSETS = {
    "/docs/prototypes/studies-ui.js": (PROTOTYPE.parent / "studies-ui.js", "text/javascript; charset=utf-8"),
    "/docs/prototypes/idx-evidence-lab-user-journey.html": (PROTOTYPE, "text/html; charset=utf-8"),
    "/docs/prototypes/ihsg-evt-tail-surface-data.json": (PROTOTYPE.parent / "ihsg-evt-tail-surface-data.json", "application/json; charset=utf-8"),
    "/docs/prototypes/market-overview-data.json": (PROTOTYPE.parent / "market-overview-data.json", "application/json; charset=utf-8"),
    "/docs/prototypes/news-universe.json": (PROTOTYPE.parent / "news-universe.json", "application/json; charset=utf-8"),
    "/docs/prototypes/ihsg-evt-tail-surface.fig": (PROTOTYPE.parent / "ihsg-evt-tail-surface.fig", "application/octet-stream"),
}
MAX_BODY_BYTES = 4096
MAX_PORTFOLIO_BODY_BYTES = 16_384
MAX_INDEX_DOCUMENTS = 3000
MAX_INDEX_FILE_BYTES = 200_000
TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)
APPLICATION_PAGES = (
    ("dashboard", "Dashboard", "Ringkasan pasar IHSG berita emiten"),
    ("screener", "Screener", "Filter saham ticker sektor metrik valuasi"),
    ("watchlist", "Watchlist", "Daftar pantauan saham"),
    ("studies", "Studies", "Studi riset evidence dossier"),
    ("research", "Riset emiten", "Pertanyaan akuisisi aksi korporasi HMETD OpenRouter"),
    ("portfolio-lab", "Portfolio Lab", "Portofolio portfolio optimasi alokasi risiko Sharpe drawdown faktor simulasi"),
    ("market", "Market overview", "IHSG pasar sektor heatmap volatilitas EVT"),
    ("news-universe", "News Universe", "Berita news emiten"),
    ("sources", "Sumber & metode PDF", "Provenance snapshot dokumen hukum sumber metodologi"),
    ("settings", "Settings", "Pengaturan koneksi API key OpenRouter"),
)
QUERY_EXPANSIONS = {
    "right issue": "right issue HMETD penambahan modal hak memesan efek terlebih dahulu",
    "rights issue": "rights issue HMETD penambahan modal hak memesan efek terlebih dahulu",
    "akuisisi": "akuisisi pengambilalihan perusahaan pengendali tender offer merger",
    "merger": "merger penggabungan usaha akuisisi pengambilalihan",
    "buyback": "buyback pembelian kembali saham",
    "aksi korporasi": "corporate action rights issue buyback dividend merger acquisition",
    "pengambilalihan": "acquisition takeover tender offer",
}


def load_tickers(root: Path = ROOT) -> tuple[str, ...]:
    universe_path = root / "data" / "raw" / "sectors" / "lq45-universe.json"
    try:
        payload = json.loads(universe_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    results = payload.get("results", []) if isinstance(payload, dict) else []
    return tuple(sorted({
        str(item.get("symbol", "")).split(".")[0].upper()
        for item in results
        if isinstance(item, dict)
        and "LQ45" in item.get("query_values", {}).get("indices", [])
        and item.get("symbol")
    }))


class PortfolioUnavailable(ValueError):
    """A valid portfolio request lacks trustworthy local calculation inputs."""


def portfolio_data_catalog(root: Path = ROOT) -> dict[str, Any]:
    universe = load_lq45_universe(root)
    tickers_in_universe = [item["ticker"] for item in universe.get("symbols", [])]
    _, sub_sectors, _, _ = _current_classifications(root, tickers_in_universe)
    tickers = []
    for item in universe.get("symbols", []):
        daily = load_issuer_daily(root, item["ticker"])
        tickers.append({"ticker": item["ticker"], "company": item["company"],
                        "sub_sector": sub_sectors.get(item["ticker"]),
                        "daily_quality": daily["data_quality"], "observations": daily["observation_count"],
                        "coverage_start": daily["coverage_start"], "coverage_end": daily["coverage_end"]})
    return {
        "status": "AVAILABLE_WITH_CAVEAT" if universe["data_quality"] == "PARTIAL" else universe["data_quality"],
        "provider": "Sectors.app", "tickers": tickers, "benchmarks": ["IHSG", "LQ45"],
        "universe_quality": universe["data_quality"], "universe_issues": universe["issues"],
        "universe_as_of": universe.get("retrieved_at"),
        "risk_free_rate": {"status": "UNAVAILABLE", "reason": "No approved local Indonesian risk-free series; user annual assumption only"},
        "factors": {
            "momentum": {"status": "PARTIAL", "reason": "Price-based characteristic only; corporate actions unverified"},
            "size": {"status": "PARTIAL", "reason": "Daily market cap exists, but point-in-time factor portfolio not validated"},
            "value": {"status": "UNAVAILABLE", "reason": "Book equity publication availability not audited"},
            "quality": {"status": "UNAVAILABLE", "reason": "Profitability availability and sector comparability not audited"},
            "apt": {"status": "UNAVAILABLE", "reason": "No validated multiple factor returns and premia"},
            "black_litterman": {"status": "RESEARCH_SUPPORTED", "reason": "Selected-universe capitalization prior and historical sample views; requires valid selected caps; parameters not calibrated"},
        },
    }


def _portfolio_request(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Portfolio request must be a JSON object")
    allowed = {"tickers", "benchmark", "profile", "method", "lookback", "constraints", "total_capital",
               "risk_free_annual", "market_premium_annual", "scenarios"}
    if set(payload) - allowed:
        raise ValueError("Unknown portfolio request fields")
    tickers = payload.get("tickers")
    if not isinstance(tickers, list) or not 1 <= len(tickers) <= 45 or any(not isinstance(t, str) or not t.isalnum() or len(t) > 10 for t in tickers):
        raise ValueError("Select 1–45 valid LQ45 ticker symbols")
    if len({t.upper() for t in tickers}) != len(tickers):
        raise ValueError("Duplicate tickers are not allowed")
    benchmark = payload.get("benchmark", "IHSG")
    profile = payload.get("profile")
    method = payload.get("method")
    lookback = payload.get("lookback", 252)
    if benchmark not in {"IHSG", "LQ45"}:
        raise ValueError("Unsupported benchmark")
    if profile not in {"conservative", "moderate", "aggressive"}:
        raise ValueError("Unsupported profile")
    if method not in {"markowitz", "maximum_diversification", "hrp", "integrated"}:
        raise ValueError("Unsupported method")
    if lookback not in (126, 252, 504, "all") or isinstance(lookback, bool):
        raise ValueError("lookback must be 126, 252, 504, or all")
    constraints = payload.get("constraints", {})
    if not isinstance(constraints, dict) or set(constraints) - {"max_weight", "sector_cap", "profile_multiplier"}:
        raise ValueError("Unsupported constraints")
    for key, value in constraints.items():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 < value <= 1.5:
            raise ValueError(f"Invalid {key}")
    scenarios = payload.get("scenarios", {})
    if not isinstance(scenarios, dict) or set(scenarios) - {"horizons", "simulations", "block_size", "seed", "drawdown_threshold"}:
        raise ValueError("Unsupported scenarios")
    horizons = scenarios.get("horizons", [20, 60, 120])
    simulations = scenarios.get("simulations", 2000)
    block_size = scenarios.get("block_size", 5)
    seed = scenarios.get("seed", 42)
    if (not isinstance(horizons, list) or not horizons or len(horizons) > 3
            or any(type(h) is not int or h < 2 or h > 252 for h in horizons)):
        raise ValueError("Scenario horizons must be 2–252 sessions")
    if type(simulations) is not int or not 1 <= simulations <= 10_000:
        raise ValueError("Scenario simulations must be 1–10,000")
    if type(block_size) is not int or not 1 <= block_size <= 20:
        raise ValueError("Scenario block_size must be 1–20")
    if type(seed) is not int or not 0 <= seed <= 2 ** 32 - 1:
        raise ValueError("Scenario seed must be a nonnegative 32-bit integer")
    for key in ("risk_free_annual", "market_premium_annual"):
        value = payload.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not -0.99 < value < 5):
            raise ValueError(f"Invalid {key} assumption")
    total_capital = payload.get("total_capital")
    if total_capital is not None and (isinstance(total_capital, bool) or not isinstance(total_capital, (int, float))
                                      or not math.isfinite(float(total_capital))
                                      or total_capital <= 0 or total_capital > 10**15):
        raise ValueError("total_capital must be a positive finite amount no greater than 1e15")
    threshold = scenarios.get("drawdown_threshold")
    if threshold is not None and (isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not -1 < threshold < 0):
        raise ValueError("drawdown_threshold must be a negative fraction")
    return {**payload, "tickers": [t.upper() for t in tickers], "benchmark": benchmark,
            "profile": profile, "method": method, "lookback": lookback,
            "constraints": constraints, "scenarios": {"horizons": horizons, "simulations": simulations,
                                             "block_size": block_size, "seed": seed,
                                             "drawdown_threshold": threshold}}


def build_portfolio_analysis(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    try:
        inputs = load_portfolio_inputs(root, request["tickers"], request["benchmark"])
    except ValueError as exc:
        if "universe snapshot is unavailable" in str(exc):
            raise PortfolioUnavailable(str(exc)) from exc
        raise
    if inputs["status"] != "READY":
        raise PortfolioUnavailable(f"Portfolio inputs: {inputs['status']}; {', '.join(inputs['issues'][:3])}")
    total = len(inputs["return_dates"])
    lookback = total if request["lookback"] == "all" else request["lookback"]
    if total < lookback:
        raise PortfolioUnavailable(f"Only {total} common eligible return sessions; requested {lookback}")
    window_returns = inputs["return_matrix"][-lookback:]
    window_dates = inputs["return_dates"][-lookback:]
    constraints = {**request["constraints"], "sectors": inputs["sectors"]}
    caps_by_date = dict(zip(inputs["dates"], inputs["market_cap_matrix"]))
    if request["method"] == "integrated":
        caps = caps_by_date.get(window_dates[-1])
        if not caps or any(v is None or not math.isfinite(v) or v <= 0 for v in caps):
            raise PortfolioUnavailable("Verified capitalization required for Black–Litterman prior")
        constraints.update(prior_weights=caps, risk_free_annual=request.get("risk_free_annual"))
    if constraints.get("sector_cap") is not None and any(value is None for value in inputs["sectors"].values()):
        raise PortfolioUnavailable("Sector cap requires verified sector labels for every selected ticker")
    baseline = equal_weight_portfolio(window_returns, inputs["tickers"])
    methods = {method: optimize_portfolio(window_returns, inputs["tickers"], method,
                                           request["profile"], constraints)
               for method in ("markowitz", "maximum_diversification", "hrp")}
    if request["method"] == "integrated":
        methods["integrated"] = optimize_portfolio(window_returns, inputs["tickers"], "integrated",
                                                  request["profile"], constraints)
    allocation = methods[request["method"]]
    if allocation["weights"] is None:
        raise PortfolioUnavailable(f"{request['method']}: {allocation['reason']}")
    weights = [allocation["weights"][ticker] for ticker in inputs["tickers"]]
    benchmark_returns = [inputs["benchmark_returns"][day] for day in window_dates]
    market = load_ihsg_snapshot(root) if request["benchmark"] == "IHSG" else None
    ath_recovery = None
    if market and market.get("data_quality") == "VERIFIED" and market.get("latest_price"):
        ath_recovery = 9174.0 / float(market["latest_price"]) - 1
    method_metrics = {}
    equal_weights = [baseline["weights"][ticker] for ticker in inputs["tickers"]]
    equal_returns = [sum(weight * value for weight, value in zip(equal_weights, row))
                     for row in window_returns]
    method_metrics["equal_weight"] = calculate_portfolio_metrics(
        window_dates, equal_returns, benchmark_returns,
        request.get("risk_free_annual"), request.get("market_premium_annual"),
        market_return_assumption_annual=ath_recovery,
    )
    for method, candidate in methods.items():
        if candidate["weights"] is None:
            method_metrics[method] = None
            continue
        candidate_weights = [candidate["weights"][ticker] for ticker in inputs["tickers"]]
        candidate_returns = [sum(weight * value for weight, value in zip(candidate_weights, row))
                             for row in window_returns]
        method_metrics[method] = calculate_portfolio_metrics(
            window_dates, candidate_returns, benchmark_returns,
            request.get("risk_free_annual"), request.get("market_premium_annual"),
            market_return_assumption_annual=ath_recovery,
        )
    metrics = method_metrics[request["method"]]
    historical_portfolio_returns = [
        sum(allocation["weights"][ticker] * value for ticker, value in zip(inputs["tickers"], row))
        for row in window_returns
    ]
    historical_metrics = calculate_portfolio_metrics(
        window_dates, historical_portfolio_returns, benchmark_returns,
        request.get("risk_free_annual"),
    )
    historical_capm = {
        "beta": historical_metrics["beta"],
        "capm_hurdle": historical_metrics["capm_hurdle"],
        "capm_alpha": historical_metrics["capm_alpha"],
        "risk_free_annual": historical_metrics["assumptions"]["risk_free_annual"],
        "market_return_arithmetic_annual": historical_metrics["assumptions"]["market_return_arithmetic_annual"],
        "market_premium_annual": historical_metrics["assumptions"]["market_premium_annual"],
        "sample_start": window_dates[0], "sample_end": window_dates[-1],
        "sample_count": len(window_dates), "benchmark": request["benchmark"],
        "source": "ALIGNED_HISTORICAL_BENCHMARK",
    }
    market_history = None
    if market and market["data_quality"] == "VERIFIED":
        series = market["series"]
        market_returns = [b["price"] / a["price"] - 1 for a, b in zip(series, series[1:])]
        market_history = calculate_portfolio_metrics([row["date"] for row in series[1:]], market_returns)
        market_history["coverage_start"] = market["coverage_start"]
        market_history["coverage_end"] = market["coverage_end"]
        market_history["all_time_high"] = 9174.0
        market_history["latest_index_level"] = market["latest_price"]
        market_history["ath_recovery_return"] = ath_recovery
        market_history["ath_recovery_as_of"] = market.get("as_of") or market.get("coverage_end")
        market_history["purpose"] = "ATH-recovery scenario input for CAPM; not an official target forecast"
    walk_forward = run_walk_forward(inputs["return_dates"], inputs["return_matrix"],
                                    inputs["tickers"], request["method"], request["profile"],
                                    estimation_window=min(252, lookback), constraints=constraints,
                                    capitalization_by_date=caps_by_date)
    scenario_config = request["scenarios"]
    scenarios = simulate_portfolio_scenarios(
        window_returns, weights, horizons=tuple(scenario_config["horizons"]),
        simulations=scenario_config["simulations"], block_size=scenario_config["block_size"],
        seed=scenario_config["seed"], drawdown_threshold=scenario_config["drawdown_threshold"],
        risk_free_annual=request.get("risk_free_annual"),
    )
    return {
        "status": "READY", "calculation_state": "PROVISIONAL_PRICE_RETURNS",
        "selection": {"tickers": inputs["tickers"], "profile": request["profile"],
                      "method": request["method"], "benchmark": inputs["benchmark"],
                      "lookback": lookback, "sample_start": window_dates[0], "sample_end": window_dates[-1]},
        "allocation": allocation, "methods": methods, "method_metrics": method_metrics,
        "equal_weight": baseline,
        "metrics": metrics, "metrics_scope": "IN_SAMPLE_STATIC_TARGET_WEIGHTS_DAILY_REBALANCED",
        "historical_capm": historical_capm,
        "market_history": market_history,
        "walk_forward": walk_forward, "scenarios": scenarios,
        "total_capital": request.get("total_capital"),
        "lot_allocation": allocate_lots(allocation["weights"], request["total_capital"],
            dict(zip(inputs["tickers"], inputs["close_matrix"][inputs["dates"].index(window_dates[-1])]))
        ) if request.get("total_capital") is not None else None,
        "capitalization_prior_as_of": window_dates[-1] if request["method"] == "integrated" else None,
        "amounts": allocate_amounts(allocation["weights"], request["total_capital"])["amounts"]
                   if request.get("total_capital") is not None else None,
        "sectors": inputs["sectors"], "sub_sectors": inputs["sub_sectors"], "coverage": inputs["coverage"],
        "factor_readiness": {**inputs["field_status"],
            "black_litterman": "RESEARCH_ESTIMATE" if request["method"] == "integrated" else "NOT_USED"},
        "provenance": {"provider": inputs["provider"], "universe": inputs["universe"],
                       "sources": inputs["sources"], "issues": inputs["issues"],
                       "universe_limitation": inputs["universe_limitation"],
                       "adjustment_policy": inputs["adjustment_policy"]},
    }


def build_local_index(root: Path = ROOT) -> LocalSearchIndex:
    """Build a bounded index from local docs, approved snapshot files, and legal filenames."""
    documents: list[SearchDocument] = []
    tickers = load_tickers(root)
    pages = APPLICATION_PAGES if (root / "docs/prototypes/idx-evidence-lab-user-journey.html").exists() else ()
    for page, title, description in pages:
        documents.append(SearchDocument(
            document_id=f"app/page/{page}", title=title, text=description,
            source_class=SourceClass.PRODUCT_METADATA, source_id=f"app/page/{page}",
            scopes=["PRODUCT"], metadata={"page": page, "kind": "navigation"}))
    for issuer in load_lq45_universe(root).get("symbols", []):
        symbol = issuer["ticker"]
        documents.append(SearchDocument(
            document_id=f"app/issuer/{symbol}", title=f"{symbol} · {issuer['company']}",
            text=f"{symbol} {issuer['company']} · Buka profil emiten, harga historis, berita dan dossier snapshot lokal.",
            source_class=SourceClass.SECTORS_SOURCE_DATA,
            source_id="data/raw/sectors/lq45-universe.json", ticker=symbol,
            scopes=["EMITEN"], metadata={"page": "issuer", "kind": "navigation"}))
    for folder in (root / "docs", root / "data" / "raw" / "sectors"):
        if not folder.exists():
            continue
        for path in sorted(folder.rglob("*")):
            if len(documents) >= MAX_INDEX_DOCUMENTS:
                break
            if not path.is_file() or path.name.endswith((".metadata.json", "_meta.json")):
                continue
            if path.suffix.casefold() not in {".json", ".md", ".txt", ".html"}:
                continue
            try:
                if path.stat().st_size > MAX_INDEX_FILE_BYTES:
                    continue
                raw_text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            text = _searchable_text(path, raw_text)[:8000]
            relative = path.relative_to(root).as_posix()
            ticker = next((t for t in tickers if re.search(rf"\b{re.escape(t)}\b", relative.upper())), None)
            source_class = SourceClass.PRODUCT_METADATA if relative.startswith("docs/") else SourceClass.SECTORS_SOURCE_DATA
            scopes = ["PRODUCT"] if source_class is SourceClass.PRODUCT_METADATA else ["EVIDENCE", "EMITEN"]
            if "ihsg" in relative.casefold():
                scopes.extend(["MARKET", "IHSG"])
            documents.append(SearchDocument(
                document_id=relative,
                title=path.stem.replace("_", " "),
                text=text,
                source_class=source_class,
                source_id=relative,
                ticker=ticker,
                scopes=scopes,
                metadata={"path": relative, "kind": path.suffix.lstrip(".")},
            ))
            if relative.startswith("data/raw/sectors/news/"):
                documents.extend(_news_documents(path, root, tickers))

    # The legal corpus remains local: index filenames only, never PDF contents.
    legal_root = root / "Business & Corporate Law"
    if legal_root.exists():
        for path in sorted(legal_root.rglob("*.pdf")):
            if len(documents) >= MAX_INDEX_DOCUMENTS:
                break
            relative = path.relative_to(root).as_posix()
            documents.append(SearchDocument(
                document_id=relative,
                title=path.stem.replace("_", " "),
                text=f"Dokumen hukum lokal; folder {path.parent.name}; nama berkas {path.name}",
                source_class=SourceClass.PRIVATE_LEGAL_REFERENCE,
                source_id=relative,
                scopes=["LEGAL_CORPUS", "FIND_RULE"],
                metadata={"path": relative, "kind": "private_pdf_filename_only"},
            ))
    return LocalSearchIndex(documents)


COSTLY_POST_ROUTES = frozenset({"/api/research-chat", "/api/issuer-research"})


class SearchHandler(BaseHTTPRequestHandler):
    server_version = "IDXEvidenceLab/0.1"
    # Drop stalled or slow clients instead of pinning a handler thread forever.
    timeout = 30

    def end_headers(self) -> None:
        # Single choke point: covers JSON, static assets and send_error() responses alike.
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        super().end_headers()

    def _rate_limited(self, route: str) -> bool:
        """Send 429 and return True when this client exceeded its POST budget."""
        limiter = getattr(self.server, "rate_limiter", None)
        if limiter is None:
            with RESEARCH_SERVICE_LOCK:
                if not hasattr(self.server, "rate_limiter"):
                    try:
                        settings = load_settings()
                    except ValueError:
                        settings = Settings()
                    self.server.rate_limiter = RateLimiter(
                        {"chat": settings.chat_per_min, "post": settings.post_per_min})
                limiter = self.server.rate_limiter
        bucket = "chat" if route in COSTLY_POST_ROUTES else "post"
        allowed, retry_after = limiter.check(self.client_address[0], bucket)
        if allowed:
            return False
        encoded = json.dumps({"error": "RATE_LIMITED"}).encode("utf-8")
        self.send_response(429)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Retry-After", str(retry_after))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)
        return True

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        origin = self.headers.get("Origin", "")
        if urlparse(self.path).path.startswith(("/api/portfolio-", "/api/studies-")) and origin in {
            "http://127.0.0.1:5500", "http://localhost:5500",
        }:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(encoded)

    def do_OPTIONS(self) -> None:
        route = urlparse(self.path).path
        origin = self.headers.get("Origin", "")
        if (route in {"/api/portfolio-analysis", "/api/studies-run"}
                and origin in {"http://127.0.0.1:5500", "http://localhost:5500"}
                and self.headers.get("Access-Control-Request-Method") == "POST"):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Vary", "Origin")
            self.end_headers()
            return
        self.send_error(403)

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        if route == '/api/studies-catalog':
            tickers=[item['ticker'] for item in load_lq45_universe(ROOT)['symbols']]
            classifications,_,_,verified=_current_classifications(ROOT,tickers)
            sectors={}
            for ticker in verified:
                if classifications.get(ticker): sectors.setdefault(classifications[ticker],[]).append(ticker)
            self._send_json(200, {'widgets': studies_catalog(), 'tickers':tickers,
                'sectors':[{'value':s,'members':sorted(m)} for s,m in sorted(sectors.items())]})
            return
        if route == "/api/portfolio-factor-zoo-data":
            try:
                payload = build_factor_zoo_payload(ROOT)
                published = _published_artifact(payload)
                artifact_path = ROOT / "docs/prototypes/portfolio-factor-zoo-data.json"
                current = None
                if artifact_path.is_file():
                    try:
                        current = json.loads(artifact_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        current = None
                if (isinstance(current, dict)
                        and current.get("artifact_fingerprint") == published.get("artifact_fingerprint")):
                    # Avoid touching a watched prototype file on every browser GET.
                    # Live Server reloads clients when this JSON is rewritten, which
                    # otherwise creates a reload → API → rewrite loop.
                    published = current
                else:
                    write_factor_zoo_artifact(ROOT, payload)
                    published = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                self._send_json(503, {"status": "UNAVAILABLE", "error": str(exc)})
                return
            self._send_json(200, published)
            return
        if route == "/api/portfolio-factor-zoo-view":
            try:
                self._send_json(200, read_factor_zoo_view(ROOT))
            except (OSError, ValueError) as exc:
                self._send_json(409, {"status": "SYNC_ERROR", "error": str(exc)})
            return
        if route == "/api/portfolio-data":
            self._send_json(200, portfolio_data_catalog(ROOT))
            return
        if route == "/api/issuer-daily":
            requested = parse_qs(urlparse(self.path).query).get("ticker", [""])[0]
            payload = load_issuer_daily(ROOT, requested)
            self._send_json(200 if payload["ok"] else 404, payload)
            return
        if route == "/api/dashboard-data":
            self._send_json(200, {
                "ihsg": load_ihsg_snapshot(ROOT),
                "news": load_local_news(ROOT),
                "universe": load_lq45_universe(ROOT),
            })
            return
        if route == "/api/screener-analysis":
            self._send_json(200, build_screener_analysis(ROOT))
            return
        if route == "/api/sector-heatmap":
            self._send_json(200, load_sector_heatmap(ROOT))
            return
        if route == "/api/news-universe":
            self._send_json(200, load_news_universe(ROOT))
            return
        if route == "/api/health":
            openrouter_configured = load_local_openrouter_config(OPENROUTER_ENV_FILE)
            self._send_json(200, {
                "ok": True,
                "openrouter_configured": openrouter_configured,
                "openrouter_last_request": getattr(self.server, 'openrouter_last_request', {'status': 'NOT_TESTED'}),
                "research_model_status": getattr(getattr(self.server, 'research_service', None), 'last_model_status', {'status': 'NOT_TESTED'}),
                "local_documents": len(self.server.search_index.as_records()),
            })
            return
        if route == '/api/research-targets':
            from .research.research_service import ResearchService
            from .research.research_sessions import ResearchSessionStore
            service = ResearchService(ROOT, self.server.search_index, ResearchSessionStore(), OpenRouterSearchAdapter,
                                      known_tickers=list(self.server.tickers))
            self._send_json(200, service.targets())
            return
        if route == "/api/source-report":
            self._send_json(200, build_source_report(ROOT))
            return
        if route in PUBLIC_PROTOTYPE_ASSETS:
            asset_path, content_type = PUBLIC_PROTOTYPE_ASSETS[route]
        elif route in {"/", "/index.html"}:
            asset_path, content_type = PROTOTYPE, "text/html; charset=utf-8"
        else:
            self.send_error(404)
            return
        try:
            content = asset_path.read_bytes()
        except OSError:
            self.send_error(404, "Berkas prototype tidak ditemukan")
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if self._rate_limited(route):
            return
        if route == '/api/studies-run':
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length < 1 or length > MAX_PORTFOLIO_BODY_BYTES:
                    self._send_json(413, {'error': 'INVALID_STUDIES_BODY_SIZE'})
                    return
                payload = json.loads(self.rfile.read(length))
                tickers = [item['ticker'] for item in load_lq45_universe(ROOT)['symbols']]
                classification, _, _, verified = _current_classifications(ROOT, tickers)
                sectors = {}
                for ticker in verified:
                    sector = classification.get(ticker)
                    if sector:
                        sectors.setdefault(sector, []).append(ticker)
                request = parse_study_request(payload, known_tickers=tickers, sectors=sectors)
                store=getattr(self.server,'studies_artifacts',None)
                artifact=store.get(request.portfolio_artifact_ref) if store and request.portfolio_artifact_ref else None
                result = run_study(ROOT, request, portfolio_artifact=artifact)
            except (ValueError, TypeError, KeyError):
                self._send_json(400, {'error': 'INVALID_STUDIES_REQUEST'})
                return
            except Exception:
                self._send_json(500, {'error': 'STUDIES_PROCESSING_FAILED'})
                return
            self._send_json(200, result)
            return
        if route in {'/api/research-sessions', '/api/research-chat', '/api/research-cancel', '/api/research-attachments'}:
            try:
                from .research.research_service import ResearchService
                from .research.research_sessions import ResearchSessionStore
                # Server attribute creation is protected across handler threads.
                from threading import RLock
                with RESEARCH_SERVICE_LOCK:
                    if not hasattr(self.server, 'research_service'):
                        self.server.research_service = ResearchService(ROOT, self.server.search_index,
                            ResearchSessionStore(), OpenRouterSearchAdapter, known_tickers=list(self.server.tickers))
                service = self.server.research_service
                length = int(self.headers.get('Content-Length', '0'))
                limit = 7 * 1024 * 1024 if route == '/api/research-attachments' else 64 * 1024
                if not 1 <= length <= limit:
                    raise ValueError('INVALID_BODY_SIZE')
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict):
                    raise ValueError('INVALID_BODY')
                if route == '/api/research-attachments':
                    from .research.research_attachments import read_attachment
                    service.store.get(body.get('session_id'))
                    if 'remove_id' in body:
                        service.store.remove_attachment(body.get('session_id'), body['remove_id'])
                        self._send_json(200, {'status': 'REMOVED'})
                    else:
                        item = service.store.add_attachment(body.get('session_id'), read_attachment(body.get('file')))
                        self._send_json(201, {k: v for k, v in item.items() if k != 'text'})
                elif route == '/api/research-sessions':
                    session = service.store.create()
                    self._send_json(201, {'session_id': session.id, 'revision': 0, 'context': session.context.to_dict(), 'history_persistent': False})
                elif route == '/api/research-cancel':
                    self._send_json(200, service.cancel(body.get('session_id'), body.get('expected_revision')))
                else:
                    load_local_openrouter_config(OPENROUTER_ENV_FILE)
                    result = service.answer(body.get('session_id'), body.get('expected_revision'), body.get('query'),
                        body.get('use_model', False), body.get('artifact_refs', []), request_id=body.get('request_id'), target=body.get('target'),
                        attachment_ids=body.get('attachment_ids'), share_attachments=body.get('share_attachments', False))
                    self._send_json(200, result)
            except KeyError:
                self._send_json(404, {'error': 'SESSION_EXPIRED'})
            except (ValueError, TypeError) as exc:
                code = str(exc)
                self._send_json(409 if code in {'REVISION_CONFLICT', 'REQUEST_PENDING', 'STALE_RESPONSE'} else 400, {'error': code if code.isupper() else 'INVALID_REQUEST'})
            except Exception:
                self._send_json(502, {'error': 'RESEARCH_PROCESSING_FAILED'})
            return
        if route == "/api/portfolio-analysis":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > MAX_PORTFOLIO_BODY_BYTES:
                    self._send_json(413, {"status": "INVALID_REQUEST", "error": "Portfolio request exceeds 16 KB or is empty"})
                    return
                request = _portfolio_request(json.loads(self.rfile.read(length)))
                result = build_portfolio_analysis(ROOT, request)
                with RESEARCH_SERVICE_LOCK:
                    if not hasattr(self.server,'studies_artifacts'):
                        self.server.studies_artifacts=StudyArtifactStore()
                result['studies_artifact_ref']=self.server.studies_artifacts.save(ROOT,result)
            except PortfolioUnavailable as exc:
                self._send_json(422, {"status": "UNAVAILABLE", "error": str(exc)})
                return
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self._send_json(400, {"status": "INVALID_REQUEST", "error": str(exc)})
                return
            self._send_json(200, result)
            return
        if route not in {"/api/search", "/api/issuer-research"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY_BYTES:
                self._send_json(413, {"error": "Ukuran permintaan pencarian tidak valid."})
                return
            request_body = json.loads(self.rfile.read(length))
            query = request_body.get("query", "")
            if not isinstance(query, str) or not query.strip() or len(query) > 500:
                self._send_json(400, {"error": "Pertanyaan harus berisi 1–500 karakter."})
                return
            if route == "/api/issuer-research":
                ticker = str(request_body.get("ticker", "")).strip().upper()
                if ticker not in self.server.tickers:
                    self._send_json(400, {"error": "Pilih emiten yang termasuk snapshot universe LQ45."})
                    return
                result = build_issuer_research(ROOT, ticker, query, self.server.search_index)
                result["inference"] = {"provider": "local", "status": "NOT_REQUESTED"}
                if request_body.get("use_model") is True:
                    load_local_openrouter_config(OPENROUTER_ENV_FILE)
                    try:
                        result["inference"] = OpenRouterSearchAdapter().compose_research(
                            ticker, query, result["evidence"])
                        result["inference"]["status"] = "GENERATED"
                        result["analysis_boundary"] = (
                            "Interpretasi model dari cuplikan snapshot, bukan fakta terverifikasi atau prediksi. "
                            "Rujukan sumber dicek; isi jawaban tetap perlu dibandingkan dengan kutipan. "
                            "PDF hukum privat tidak dikirim ke OpenRouter.")
                    except OpenRouterError as exc:
                        result["inference"] = {"provider": "local", "status": "UNAVAILABLE", "notice": str(exc), "http_status": exc.status_code, "retry_after": exc.retry_after, "diagnostics": exc.diagnostics}
                self._send_json(200, result)
                return
            try:
                load_local_openrouter_config(OPENROUTER_ENV_FILE)
                if request_body.get("use_model") is False or query.strip().upper() in self.server.tickers:
                    plan = {"intent": "SEARCH_LOCAL", "search_query": query, "entities": [],
                            "provider": "local", "model": None, "needs_clarification": False}
                    notice = "Pencarian lokal seluruh indeks prototype; tidak memanggil LLM atau web search."
                else:
                    adapter = OpenRouterSearchAdapter()
                    plan = adapter.interpret(query, list(self.server.tickers),
                                             CAPABILITIES if request_body.get('navigate') else APPLICATION_PAGES,
                                             request_body.get('history', []))
                    self.server.openrouter_last_request = {'status': 'SUCCESS' if plan.get('provider') == 'OpenRouter' else 'INVALID_FORMAT', 'model': adapter.model}
                    notice = ("OpenRouter menafsirkan query dan katalog fitur; hasil tetap dari indeks lokal."
                              if plan.get("provider") == "OpenRouter" else
                              "Format jawaban model tidak valid; hasil memakai pencarian lokal.")
            except OpenRouterError as exc:
                self.server.openrouter_last_request = {'status': 'RATE_LIMIT' if exc.status_code == 429 else 'UNAVAILABLE', 'http_status': exc.status_code, 'retry_after': exc.retry_after, 'notice': str(exc), 'diagnostics': exc.diagnostics}
                plan = {
                    "intent": "SEARCH_LOCAL",
                    "search_query": query,
                    "entities": [],
                    "needs_clarification": False,
                    "provider": "local-fallback",
                    "model": None,
                    "source_class": "model_inference",
                }
                notice = f"Qwen tidak tersedia ({exc}); hasil berikut memakai pencarian lokal tanpa model."
            search_text = " ".join([query, plan["search_query"], *plan["entities"]])
            matches = self.server.search_index.search(search_text, limit=8)
            self._send_json(200, {
                "plan": plan,
                "navigation": build_navigation(query, self.server.tickers, plan.get('navigation')),
                "results": [
                    {
                        "title": item.title,
                        "snippet": _snippet(item.text, search_text),
                        "source_id": item.source_id,
                        "source_class": item.source_class.value,
                        "ticker": item.ticker,
                        "scopes": item.scopes,
                        "page": item.metadata.get("page") or ("issuer" if item.ticker else None),
                    }
                    for item, _score in matches
                ],
                "evidence_state": "FOUND" if matches else "INSUFFICIENT_EVIDENCE",
                "notice": notice,
            })
        except (json.JSONDecodeError, AttributeError, TypeError):
            self._send_json(400, {"error": "Format permintaan pencarian tidak valid."})
        except Exception:
            # Do not return provider bodies, request headers, or secrets to the browser.
            self._send_json(502, {"error": "Pencarian gagal diproses. Coba lagi atau periksa server lokal."})

    def log_message(self, _format: str, *_args: Any) -> None:
        # Search strings and request bodies are intentionally never written to logs.
        return


def _snippet(text: str, query: str, limit: int = 420) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    query_tokens = [t for t in TOKEN_RE.split(query.casefold()) if len(t) > 2]
    lower = compact.casefold()
    offset = next((lower.find(token) for token in query_tokens if lower.find(token) >= 0), 0)
    start = max(0, offset - 100)
    return ("…" if start else "") + compact[start:start + limit].strip() + ("…" if start + limit < len(compact) else "")


def _searchable_text(path: Path, raw_text: str) -> str:
    """Return a compact, human-readable search representation; never expose JSON dumps."""
    if path.suffix.casefold() != ".json":
        return raw_text
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return f"{path.stem.replace('_', ' ')} JSON document; content could not be parsed"

    records = payload if isinstance(payload, list) else []
    if isinstance(payload, dict):
        for key in ("results", "data", "observations", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = candidate
                break
    rows = [row for row in records if isinstance(row, dict)]
    if rows and all("date" in row and "close" in row for row in rows):
        ticker = next((str(row.get("symbol", "")).replace(".JK", "") for row in rows if row.get("symbol")), path.parent.name)
        dates = [str(row["date"]) for row in rows if row.get("date")]
        recent = sorted(rows, key=lambda row: str(row.get("date", "")))[-3:]
        observations = "; ".join(
            f"{row.get('date')}: close {row.get('close')}"
            + (f", volume {row.get('volume')}" if row.get("volume") is not None else "")
            for row in recent
        )
        date_range = f"{min(dates)}–{max(dates)}" if dates else "tanggal tidak tersedia"
        return (f"Daily OHLCV {ticker} • {len(rows)} observasi • {date_range}. "
                f"Contoh observasi terbaru: {observations}. Field: symbol, date, close, open, high, low, volume, market_cap.")

    # Keep useful metadata/record values searchable but bounded and readable.
    values: list[str] = []
    skipped = {"sha256", "raw", "payload", "content", "authorization", "api_key", "token"}

    def collect(value: Any, depth: int = 0) -> None:
        if len(values) >= 50 or depth > 2:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).casefold() in skipped:
                    continue
                if isinstance(item, (str, int, float, bool)) and len(str(item)) < 180:
                    values.append(f"{key}: {item}")
                elif isinstance(item, (dict, list)):
                    collect(item, depth + 1)
                if len(values) >= 50:
                    break
        elif isinstance(value, list):
            values.append(f"records: {len(value)}")
            for item in value[:3]:
                collect(item, depth + 1)

    collect(payload)
    return f"{path.stem.replace('_', ' ')} • " + ("; ".join(values) if values else "JSON document")


def _news_documents(path: Path, root: Path, tickers: tuple[str, ...]) -> list[SearchDocument]:
    """Index bounded news rows individually so issuer research can retrieve them."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    relative = path.relative_to(root).as_posix()
    documents = []
    for index, row in enumerate(rows[:500]):
        if not isinstance(row, dict):
            continue
        symbols = row.get("symbols") or row.get("symbol") or row.get("tickers") or []
        if isinstance(symbols, str):
            symbols = [symbols]
        normalized = {str(value).upper().replace(".JK", "") for value in symbols if value}
        title = str(row.get("title") or row.get("headline") or row.get("news_title") or "Berita Sectors")
        body = str(row.get("content") or row.get("body") or row.get("description") or row.get("summary") or "")
        if not normalized:
            haystack = f"{title} {body}".upper()
            normalized = {symbol for symbol in tickers if re.search(rf"\b{re.escape(symbol)}\b", haystack)}
        if not normalized:
            continue
        article_text = " ".join((
            f"title: {title}", f"date: {row.get('published_at') or row.get('date') or row.get('timestamp') or 'tanggal tidak tersedia'}",
            f"symbols: {', '.join(sorted(normalized))}", f"description: {body[:2400]}",
        ))
        for symbol in sorted(normalized & set(tickers)):
            documents.append(SearchDocument(
                document_id=f"{relative}#news-{index}-{symbol}", title=title,
                text=article_text, source_class=SourceClass.SECTORS_SOURCE_DATA,
                source_id=relative, ticker=symbol, scopes=["EVIDENCE", "EMITEN", "NEWS"],
                metadata={"path": relative, "record_index": index, "kind": "news_record",
                          "published_at": row.get('published_at') or row.get('date') or row.get('timestamp')},
            ))
    return documents


def build_issuer_research(root: Path, ticker: str, question: str,
                          index: LocalSearchIndex) -> dict[str, Any]:
    """Retrieve only matching local issuer snapshots and concise private-PDF excerpts."""
    query = question.strip()[:500]
    expanded = query.casefold()
    for phrase, expansion in QUERY_EXPANSIONS.items():
        if phrase in expanded:
            query += " " + expansion
    matches = index.search(query, ticker=ticker, limit=12)
    evidence = []
    seen = set()
    for document, score in matches:
        if document.metadata.get("kind") == "navigation":
            continue
        source_id = document.document_id if document.metadata.get("kind") == "news_record" else document.source_id
        if source_id in seen:
            continue
        seen.add(source_id)
        lower_path = source_id.casefold()
        category = (
            "filing" if "/filings/" in lower_path else
            "aksi_korporasi" if "/corporate_actions/" in lower_path else
            "berita" if "/news/" in lower_path else
            "laporan_emiten" if "/company_report/" in lower_path else
            "data_lokal"
        )
        evidence.append({
            "title": document.title,
            "excerpt": _snippet(document.text, query, 380),
            "source_id": source_id,
            "source_class": document.source_class.value,
            "category": category,
            "score": score,
        })
    legal = search_legal_corpus(root, query, limit=5) if re.search(r'hukum|aturan|pasal|pojk|regulasi', query, re.I) else []
    evidence.extend(legal)
    evidence.sort(key=lambda item: (-item.get("score", 0), item["source_id"]))
    sectors_count = sum(item["source_class"] == SourceClass.SECTORS_SOURCE_DATA.value for item in evidence)
    legal_count = sum(item["source_class"] == SourceClass.PRIVATE_LEGAL_REFERENCE.value for item in evidence)
    if sectors_count == 0 and legal_count == 0:
        synthesis = "Belum ditemukan sumber lokal yang cocok dengan pertanyaan ini. Tidak ada kesimpulan atau perkiraan yang dibuat. Coba sebut ticker, nama aksi korporasi, atau istilah peraturan yang lebih spesifik."
        status = "INSUFFICIENT_EVIDENCE"
    else:
        synthesis = (
            f"Retrieval lokal menemukan {sectors_count} potongan snapshot Sectors dan {legal_count} rujukan korpus hukum yang cocok. "
            "Baca tanggal dan kutipan tiap sumber di bawah. Kecocokan kata bukan bukti bahwa aksi korporasi akan terjadi. "
            "Penilaian prospektif perlu filing terbaru yang spesifik, dokumen aturan yang berlaku, serta verifikasi applicability; "
            "tanpa itu statusnya tetap belum cukup untuk memperkirakan kejadian."
        )
        status = "PROVISIONAL_EVIDENCE_REVIEW"
    return {
        "ticker": ticker,
        "question": question.strip(),
        "answer": synthesis,
        "evidence_state": status,
        "evidence": evidence,
        "retrieval": {"sectors_snapshots": sectors_count, "private_legal_documents": legal_count},
        "as_of": "2026-09-24 for daily/index snapshots; each event/report retains its own source date",
        "source_boundary": "Sectors.app snapshots and manually curated local legal PDFs only; no web search or model-generated facts.",
        "analysis_boundary": "This prototype retrieves evidence; it does not estimate event probabilities or provide legal clearance.",
    }


def build_source_report(root: Path) -> dict[str, Any]:
    """Describe dataset use, coverage, and local provenance for the in-app PDF."""
    sectors = root / "data" / "raw" / "sectors"
    dashboard_summary: list[dict[str, str]] = []
    bundle_path = root / "docs" / "prototypes" / "market-overview-data.json"
    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        bundle = {}

    universe = bundle.get("universe", {})
    ihsg = bundle.get("ihsg", {})
    dashboard_summary.append({
        "topic": "Universe LQ45",
        "status": str(universe.get("data_quality", "TIDAK TERSEDIA")),
        "coverage": f"{universe.get('symbol_count', 0)}/{universe.get('expected_count', 45)} emiten",
        "details": "; ".join(universe.get("issues", [])) or "Snapshot universe lokal.",
    })
    dashboard_summary.append({
        "topic": "Sumber IHSG",
        "status": str(ihsg.get("data_quality", "TIDAK TERSEDIA")),
        "coverage": f"{ihsg.get('observation_count', 0)} observasi · {ihsg.get('coverage_start', '—')}–{ihsg.get('coverage_end', '—')}",
        "details": "; ".join(ihsg.get("issues", [])) or f"{ihsg.get('snapshot_count', 0)} snapshot lokal Sectors.app.",
    })

    baseline = bundle.get("signal_baseline", {})
    baseline_case = next((case for case in baseline.get("cases", []) if case.get("cost_bps") == 10), None)
    baseline_interval = baseline_case.get("interval", {}) if baseline_case else {}
    dashboard_summary.append({
        "topic": "Signal vs Market Baseline",
        "status": "UJI HISTORIS · EKSPLORATORIS" if baseline.get("ok") else "BELUM TERSEDIA",
        "coverage": f"{baseline.get('source_coverage_start', '—')}–{baseline.get('source_coverage_end', '—')} · {baseline_case.get('sessions', 0)} return" if baseline_case else "—",
        "details": (f"Aturan close>SMA200 dan SMA50>SMA200, jeda satu sesi, biaya 10 bps; sinyal {baseline_case.get('signal', {}).get('cumulative_return', 0):.1%} vs IHSG {baseline_case.get('market', {}).get('cumulative_return', 0):.1%}; MDD {baseline_case.get('signal', {}).get('max_drawdown', 0):.1%} vs {baseline_case.get('market', {}).get('max_drawdown', 0):.1%}. Interval 95% selisih tahunan {baseline_interval.get('lower', 0):.1%}–{baseline_interval.get('upper', 0):.1%}; melintasi nol, jadi keunggulan belum jelas." if baseline_case else "Artefak hitungan tidak tersedia atau tidak cocok."),
    })

    prices = [float(row["price"]) for row in ihsg.get("series", []) if row.get("price") is not None]
    if len(prices) >= 200:
        latest, sma50, sma200 = prices[-1], sum(prices[-50:]) / 50, sum(prices[-200:]) / 200
        regime = "Tren menguat" if latest > sma200 and sma50 > sma200 else "Tren melemah" if latest < sma200 and sma50 < sma200 else "Tren campuran"
        dashboard_summary.append({
            "topic": "Regime IHSG",
            "status": "DESKRIPTIF",
            "coverage": str(ihsg.get("coverage_end", "—")),
            "details": f"{regime}; close {latest:,.2f}, SMA50 {sma50:,.2f}, SMA200 {sma200:,.2f}. Aturan teknikal deskriptif, bukan prediksi.",
        })
    else:
        dashboard_summary.append({"topic": "Regime IHSG", "status": "DATA TIDAK CUKUP", "coverage": "—", "details": "Memerlukan minimal 200 observasi harian."})

    daily, index_series = bundle.get("lq45_daily", {}), bundle.get("lq45_index", {}).get("series", [])
    index_dates = sorted(row.get("date") for row in index_series if row.get("date"))
    if len(index_dates) >= 2:
        prior_date, current_date = index_dates[-2:]
        changes = []
        for source in daily.values():
            closes = {row.get("date"): float(row["close"]) for row in source.get("series", []) if row.get("close") and float(row["close"]) > 0}
            if prior_date in closes and current_date in closes:
                changes.append(closes[current_date] / closes[prior_date] - 1)
        advancers, decliners = sum(value > 0 for value in changes), sum(value < 0 for value in changes)
        dashboard_summary.append({
            "topic": "Market Breadth LQ45",
            "status": "DESKRIPTIF" if len(changes) >= 32 else "CAKUPAN DI BAWAH 70%",
            "coverage": f"{len(changes)}/45 · {prior_date}–{current_date}",
            "details": f"{advancers} naik · {len(changes) - advancers - decliners} tetap · {decliners} turun. Snapshot universe saat ini, bukan membership historis.",
        })
    else:
        dashboard_summary.append({"topic": "Market Breadth LQ45", "status": "DATA TIDAK CUKUP", "coverage": "—", "details": "Memerlukan dua tanggal indeks dan harga konstituen selaras."})

    valuation = bundle.get("valuation_readiness", {})
    dashboard_summary.append({
        "topic": "Kapitalisasi pasar LQ45",
        "status": "SNAPSHOT",
        "coverage": f"{valuation.get('market_cap_coverage', 0)}/{valuation.get('universe_count', 45)} emiten",
        "details": f"Rp {float(valuation.get('market_cap_idr') or 0) / 1e12:,.1f} triliun; harga laporan dapat berbeda tanggal dari data harian, dan bukan kapitalisasi seluruh IDX.",
    })

    foreign = bundle.get("foreign_flow", {})
    unusual = foreign.get("unusual_foreign_flow", [])
    dashboard_summary.append({
        "topic": "Unusual foreign flow",
        "status": "DESKRIPTIF",
        "coverage": f"{foreign.get('coverage_end', '—')} · {len(unusual)} emiten melewati ambang",
        "details": "Anomali arus asing |Z| ≥ 2 terhadap 20 sesi; bukan broker issuer-level atau rekomendasi.",
    })

    factor_report: dict[str, Any] = {
        "status": "NOT_AVAILABLE",
        "reason": "Factor Zoo tidak dapat dihitung dari snapshot lokal yang tersedia.",
        "issuer_rows": [],
    }
    try:
        factor_payload = build_factor_zoo_payload(root)
        factor_labels = {
            "value": "Value", "quality": "Quality", "momentum": "Momentum",
            "low_volatility": "Low Volatility",
        }
        factor_rows = []
        for record in factor_payload.get("records", []):
            component_gaps = []
            for component_name, component in record.get("components", {}).items():
                if component.get("status") != "AVAILABLE":
                    reason = component.get("reason") or component.get("status") or "Tidak tersedia"
                    component_gaps.append(f"{component_name}: {reason}")
            daily_quality = record.get("data_quality", {})
            factor_rows.append({
                "ticker": record.get("ticker", "—"),
                "company": record.get("company", "—"),
                "peer_group": record.get("peer_group", "—"),
                "company_report_status": daily_quality.get("company_report", "—"),
                "report_price_as_of": record.get("report_as_of") or "—",
                "daily_status": daily_quality.get("daily", "—"),
                "daily_observation_count": daily_quality.get("daily_observation_count", 0),
                "daily_coverage_start": daily_quality.get("daily_coverage_start") or "—",
                "daily_coverage_end": daily_quality.get("daily_coverage_end") or "—",
                "aligned_ihsg_returns": daily_quality.get("aligned_ihsg_returns", 0),
                "factors": {
                    key: {
                        "label": factor_labels[key],
                        "status": record.get("scores", {}).get(key, {}).get("status", "UNAVAILABLE"),
                        "score": record.get("scores", {}).get(key, {}).get("score"),
                    }
                    for key in factor_labels
                },
                "missing_components": component_gaps,
                "daily_issues": daily_quality.get("daily_issues", []),
            })
        factor_report = {
            "status": "AVAILABLE",
            "schema_version": factor_payload.get("schema_version"),
            "formula_version": factor_payload.get("formula_version"),
            "provider": factor_payload.get("provider"),
            "universe": factor_payload.get("universe", {}),
            "as_of": factor_payload.get("as_of", {}),
            "sources": factor_payload.get("sources", {}),
            "method": factor_payload.get("method", {}),
            "coverage": factor_payload.get("coverage", {}),
            "issuer_rows": factor_rows,
        }
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        factor_report["reason"] = f"{type(exc).__name__}: {exc}"

    def response_json_files(folder: Path) -> list[Path]:
        return [
            path for path in folder.rglob("*.json")
            if not path.name.endswith((".metadata.json", "_meta.json"))
            and "collection_summary" not in path.name.casefold()
            and "manifest" not in path.name.casefold()
        ] if folder.exists() else []

    counts = {
        "universe": 1 if (sectors / "lq45-universe.json").exists() else 0,
        "company_reports": len(list((sectors / "company_report").glob("*/company_report.json"))),
        "daily_snapshots": len(response_json_files(sectors / "daily")),
        "index_daily_snapshots": len(response_json_files(sectors / "index_daily")),
        "filing_snapshots": len(response_json_files(sectors / "filings")),
        "foreign_flow_snapshots": len(response_json_files(sectors / "foreign_flow")),
        "corporate_action_snapshots": len(response_json_files(sectors / "corporate_actions")),
        "news_snapshots": len(response_json_files(sectors / "news")),
        "suspension_snapshots": len(response_json_files(sectors / "suspensions")),
        "private_legal_pdfs": len(list((root / "Business & Corporate Law").rglob("*.pdf"))),
    }
    endpoints = {
        "Universe LQ45": "/v2/companies/ (filter index=LQ45)",
        "Daily OHLCV": "/v2/daily/{ticker}/",
        "Indeks harian IHSG & LQ45": "/v2/index-daily/{index_code}/",
        "Laporan perusahaan": "/v2/company/report/{ticker}/",
        "Foreign flow": "/v2/foreign-flow/{ticker}/",
        "Filings": "/v2/filings/?symbol={ticker}&start=...&end=...",
        "Aksi korporasi": "/v2/company/corporate-actions/{ticker}/",
        "Suspensions": "/v2/suspensions/?symbol={ticker}&start=...&end=...",
        "News snapshots": "/v2/news/?extension=idx&symbols=...&start=...&end=...",
    }
    definitions = [
        ("universe", "LQ45 universe", "universe", "Menentukan emiten pada screener, Riset emiten, dan Portfolio Lab.", "Snapshot anggota saat ini; bukan keanggotaan historis."),
        ("daily", "Daily OHLCV", "daily_snapshots", "Return, RSI, tren harga, risiko portofolio, momentum Factor Zoo, dan heatmap sektor.", "Data harian; histori tiap emiten berbeda. AADI mulai 5 Des 2024."),
        ("index_daily", "Indeks IHSG & LQ45", "index_daily_snapshots", "Konteks pasar, benchmark portofolio, Signal vs Market Baseline (regime SMA 50/200), dan surface tail-loss IHSG.", "708 observasi per indeks; membership historis LQ45 tidak direkonstruksi. Baseline regime memakai jeda satu sesi penuh, kas 0%, dan sensitivitas biaya; bukan sinyal terverifikasi untuk trading."),
        ("company_report", "Laporan perusahaan", "company_reports", "Rasio fundamental, coverage forward P/E, dan sumbu Value/Quality Factor Zoo.", "Snapshot laporan; field bervariasi. Tanggal laporan/harga dapat berbeda dari daily."),
        ("foreign_flow", "Foreign flow", "foreign_flow_snapshots", "Konteks transaksi asing harian dan anomali deskriptif Market Overview.", "Histori provider mulai 2 Jan 2025; bukan data intraday atau total semua broker."),
        ("filings", "Filings", "filing_snapshots", "Timeline peristiwa dan bahan retrieval Riset emiten.", "Arsip mengikuti jendela pengambilan; filing bukan bukti dampak harga."),
        ("corporate_actions", "Corporate actions", "corporate_action_snapshots", "Timeline aksi korporasi dan konteks penyesuaian emiten.", "Cakupan mengikuti respons dan snapshot tersimpan."),
        ("suspensions", "Suspensions", "suspension_snapshots", "Riwayat suspensi pada konteks emiten.", "Deskriptif; bukan prediksi suspensi."),
        ("news", "News", "news_snapshots", "Konteks berita berticker pada News Universe dan Riset emiten.", "Jendela query terpilih; bukan arsip berita lengkap."),
    ]
    datasets: list[dict[str, Any]] = []
    snapshot_manifest: list[dict[str, Any]] = []
    for folder_name, label, count_key, usage, limitation in definitions:
        folder = sectors if folder_name == "universe" else sectors / folder_name
        universe_snapshot = sectors / "lq45-universe.json"
        snapshots = [universe_snapshot] if folder_name == "universe" and universe_snapshot.is_file() else response_json_files(folder)
        metadata_rows = []
        endpoint_example = None
        for snapshot in snapshots:
            metadata_candidates = (
                snapshot.with_name(snapshot.stem + ".metadata.json"),
                snapshot.with_name(snapshot.stem + "_meta.json"),
            )
            metadata_path = next((path for path in metadata_candidates if path.is_file()), None)
            metadata: dict[str, Any] = {}
            if metadata_path:
                try:
                    loaded = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata = loaded if isinstance(loaded, dict) else {}
                except (OSError, json.JSONDecodeError):
                    metadata = {}
            endpoint_example = endpoint_example or metadata.get("endpoint")
            ticker = metadata.get("ticker") or metadata.get("symbol") or metadata.get("index_code")
            if not ticker and snapshot.parent != folder:
                ticker = snapshot.parent.name
            start = metadata.get("start") or metadata.get("requested_start") or metadata.get("coverage_start")
            end = metadata.get("end") or metadata.get("requested_end") or metadata.get("coverage_end")
            retrieved = metadata.get("retrieved_at")
            digest = metadata.get("sha256") or metadata.get("snapshot_sha256")
            row = {
                "dataset": label,
                "file": snapshot.relative_to(root).as_posix(),
                "ticker": str(ticker) if ticker else "—",
                "period_start": str(start) if start else "—",
                "period_end": str(end) if end else "—",
                "retrieved_at": str(retrieved) if retrieved else "—",
                "http_status": metadata.get("http_status", "—"),
                "sha256": str(digest) if digest else "—",
            }
            metadata_rows.append(row)
            snapshot_manifest.append(row)
        starts = [row["period_start"] for row in metadata_rows if row["period_start"] != "—"]
        ends = [row["period_end"] for row in metadata_rows if row["period_end"] != "—"]
        latest = max((row["retrieved_at"] for row in metadata_rows if row["retrieved_at"] != "—"), default="—")
        tickers = {row["ticker"] for row in metadata_rows if row["ticker"] != "—"}
        if folder_name == "universe" and snapshots:
            try:
                universe_payload = json.loads(snapshots[0].read_text(encoding="utf-8"))
                universe_rows = universe_payload.get("results", []) if isinstance(universe_payload, dict) else universe_payload
                if isinstance(universe_rows, list):
                    tickers.update(str(item.get("symbol") or item.get("ticker")) for item in universe_rows if isinstance(item, dict) and (item.get("symbol") or item.get("ticker")))
            except (OSError, json.JSONDecodeError):
                pass
        endpoint_key = {"LQ45 universe": "Universe LQ45", "Indeks IHSG & LQ45": "Indeks harian IHSG & LQ45"}.get(label, label)
        datasets.append({
            "name": label,
            "status": "TERSEDIA" if snapshots else "TIDAK TERSEDIA",
            "snapshot_count": counts[count_key],
            "entity_count": len(tickers),
            "coverage_start": min(starts, default="—"),
            "coverage_end": max(ends, default="—"),
            "latest_retrieved_at": latest,
            "hash_count": sum(row["sha256"] != "—" for row in metadata_rows),
            "endpoint": str(endpoint_example or endpoints.get(endpoint_key, "—")),
            "used_for": usage,
            "limitations": limitation,
        })
    datasets.extend([
        {"name": "Broker activity per emiten", "status": "BELUM TERSEDIA", "snapshot_count": 0, "entity_count": 0, "coverage_start": "—", "coverage_end": "—", "latest_retrieved_at": "—", "hash_count": 0, "endpoint": "—", "used_for": "Belum dipakai sebagai metrik issuer-level.", "limitations": "Arsip empat broker tidak mewakili cakupan transaksi seluruh emiten LQ45."},
        {"name": "PDF hukum lokal", "status": "KOLEKSI LOKAL", "snapshot_count": counts["private_legal_pdfs"], "entity_count": 0, "coverage_start": "—", "coverage_end": "—", "latest_retrieved_at": "—", "hash_count": 0, "endpoint": "Koleksi manual lokal · bukan API Sectors.app", "used_for": "Rujukan dokumen pada Riset emiten; tidak menjadi fakta pasar.", "limitations": "Status berlaku dan relevansi dokumen memerlukan review manusia."},
    ])
    verified_hashes = sum(row["sha256"] != "—" for row in snapshot_manifest)
    return {
        "track": "Sectors Hackathon 2026 · Track 03 Market Intelligence",
        "provider": "Sectors.app",
        "local_root": "data/raw/sectors/",
        "counts": counts,
        "endpoints": endpoints,
        "datasets": datasets,
        "dashboard_summary": dashboard_summary,
        "factor_report": factor_report,
        "screener_analysis": build_screener_analysis(root),
        "snapshot_manifest": snapshot_manifest,
        "provenance_summary": {"snapshot_files": len(snapshot_manifest), "sha256_records": verified_hashes},
        "external_source_policy": "Semua snapshot pasar dan emiten berasal dari Sectors.app v2. Tidak ada API data pasar alternatif.",
        "legal_corpus_policy": "PDF hukum adalah koleksi lokal privat yang terpisah dari Sectors.app; keberlakuan dan applicability belum dipastikan.",
        "storage_note": "Sidecar metadata lokal mencatat endpoint, jendela request, waktu pengambilan, status HTTP, dan SHA-256 bila tersedia.",
        "limits": [
            "Cakupan mengikuti snapshot yang berhasil disimpan dan universe LQ45 saat ini; keanggotaan indeks historis tidak direkonstruksi.",
            "Broker activity issuer-level belum tersedia; arsip empat broker tidak dipakai sebagai pengganti data seluruh LQ45.",
            "News hanya mencakup jendela query yang dipilih. Foreign flow adalah harian dan histori provider mulai 2 Jan 2025.",
            "Daftar input dan snapshot tidak berarti fitur sudah dihitung atau divalidasi untuk keputusan investasi.",
        ],
    }


from threading import RLock
RESEARCH_SERVICE_LOCK = RLock()


def main() -> None:
    load_local_openrouter_config(OPENROUTER_ENV_FILE)
    try:
        settings = load_settings()
    except ValueError as exc:
        raise SystemExit(f"Konfigurasi tidak valid: {exc}") from None
    if not settings.is_loopback:
        print(f"PERINGATAN: server mendengarkan di {settings.host}. Aplikasi belum memiliki autentikasi; "
              "jangan buka ke jaringan publik.", file=sys.stderr)
    server = ThreadingHTTPServer((settings.host, settings.port), SearchHandler)
    server.search_index = build_local_index()
    server.tickers = load_tickers()
    print(f"IDX Evidence Lab lokal: http://{settings.host}:{settings.port}")
    print(f"Indeks lokal: {len(server.search_index.as_records())} dokumen; API key {'tersedia' if os.environ.get('OPENROUTER_API_KEY') else 'belum disetel'}.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer dihentikan.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
