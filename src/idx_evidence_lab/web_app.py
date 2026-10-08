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
from .core.paths import ROOT
from .research.local_index import APPLICATION_PAGES, MAX_INDEX_DOCUMENTS, MAX_INDEX_FILE_BYTES, TOKEN_RE, load_tickers, build_local_index, _snippet, _searchable_text, _news_documents
from .research.issuer_research import QUERY_EXPANSIONS, build_issuer_research
from .portfolio.portfolio_service import PortfolioUnavailable, portfolio_data_catalog, _portfolio_request, build_portfolio_analysis
from .research.source_report import build_source_report
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


OPENROUTER_ENV_FILE = ROOT / ".env.local"
PROTOTYPE = ROOT / "docs" / "prototypes" / "idx-evidence-lab-user-journey.html"
PUBLIC_PROTOTYPE_ASSETS = {
    "/docs/prototypes/studies-ui.js": (PROTOTYPE.parent / "studies-ui.js", "text/javascript; charset=utf-8"),
    "/docs/prototypes/app.js": (PROTOTYPE.parent / "app.js", "text/javascript; charset=utf-8"),
    "/docs/prototypes/app.css": (PROTOTYPE.parent / "app.css", "text/css; charset=utf-8"),
    "/docs/prototypes/idx-evidence-lab-user-journey.html": (PROTOTYPE, "text/html; charset=utf-8"),
    "/docs/prototypes/ihsg-evt-tail-surface-data.json": (PROTOTYPE.parent / "ihsg-evt-tail-surface-data.json", "application/json; charset=utf-8"),
    "/docs/prototypes/market-overview-data.json": (PROTOTYPE.parent / "market-overview-data.json", "application/json; charset=utf-8"),
    "/docs/prototypes/news-universe.json": (PROTOTYPE.parent / "news-universe.json", "application/json; charset=utf-8"),
    "/docs/prototypes/ihsg-evt-tail-surface.fig": (PROTOTYPE.parent / "ihsg-evt-tail-surface.fig", "application/octet-stream"),
}
MAX_BODY_BYTES = 4096
MAX_PORTFOLIO_BODY_BYTES = 16_384














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

    GET_ROUTES = {
        "/api/studies-catalog": "_get_studies_catalog",
        "/api/portfolio-factor-zoo-data": "_get_factor_zoo_data",
        "/api/portfolio-factor-zoo-view": "_get_factor_zoo_view",
        "/api/portfolio-data": "_get_portfolio_data",
        "/api/issuer-daily": "_get_issuer_daily",
        "/api/dashboard-data": "_get_dashboard_data",
        "/api/screener-analysis": "_get_screener_analysis",
        "/api/sector-heatmap": "_get_sector_heatmap",
        "/api/news-universe": "_get_news_universe",
        "/api/health": "_get_health",
        "/api/research-targets": "_get_research_targets",
        "/api/source-report": "_get_source_report",
    }

    def do_GET(self) -> None:
        route = urlparse(self.path).path
        handler = self.GET_ROUTES.get(route)
        if handler:
            getattr(self, handler)()
            return
        self._serve_prototype(route)

    def _get_studies_catalog(self) -> None:
        tickers=[item['ticker'] for item in load_lq45_universe(ROOT)['symbols']]
        classifications,_,_,verified=_current_classifications(ROOT,tickers)
        sectors={}
        for ticker in verified:
            if classifications.get(ticker): sectors.setdefault(classifications[ticker],[]).append(ticker)
        self._send_json(200, {'widgets': studies_catalog(), 'tickers':tickers,
            'sectors':[{'value':s,'members':sorted(m)} for s,m in sorted(sectors.items())]})

    def _get_factor_zoo_data(self) -> None:
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

    def _get_factor_zoo_view(self) -> None:
        try:
            self._send_json(200, read_factor_zoo_view(ROOT))
        except (OSError, ValueError) as exc:
            self._send_json(409, {"status": "SYNC_ERROR", "error": str(exc)})

    def _get_portfolio_data(self) -> None:
        self._send_json(200, portfolio_data_catalog(ROOT))

    def _get_issuer_daily(self) -> None:
        requested = parse_qs(urlparse(self.path).query).get("ticker", [""])[0]
        payload = load_issuer_daily(ROOT, requested)
        self._send_json(200 if payload["ok"] else 404, payload)

    def _get_dashboard_data(self) -> None:
        self._send_json(200, {
            "ihsg": load_ihsg_snapshot(ROOT),
            "news": load_local_news(ROOT),
            "universe": load_lq45_universe(ROOT),
        })

    def _get_screener_analysis(self) -> None:
        self._send_json(200, build_screener_analysis(ROOT))

    def _get_sector_heatmap(self) -> None:
        self._send_json(200, load_sector_heatmap(ROOT))

    def _get_news_universe(self) -> None:
        self._send_json(200, load_news_universe(ROOT))

    def _get_health(self) -> None:
        openrouter_configured = load_local_openrouter_config(OPENROUTER_ENV_FILE)
        self._send_json(200, {
            "ok": True,
            "openrouter_configured": openrouter_configured,
            "openrouter_last_request": getattr(self.server, 'openrouter_last_request', {'status': 'NOT_TESTED'}),
            "research_model_status": getattr(getattr(self.server, 'research_service', None), 'last_model_status', {'status': 'NOT_TESTED'}),
            "local_documents": len(self.server.search_index.as_records()),
        })

    def _get_research_targets(self) -> None:
        from .research.research_service import ResearchService
        from .research.research_sessions import ResearchSessionStore
        service = ResearchService(ROOT, self.server.search_index, ResearchSessionStore(), OpenRouterSearchAdapter,
                                  known_tickers=list(self.server.tickers))
        self._send_json(200, service.targets())

    def _get_source_report(self) -> None:
        self._send_json(200, build_source_report(ROOT))

    def _serve_prototype(self, route: str) -> None:
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

    POST_ROUTES = {
        "/api/studies-run": "_post_studies_run",
        "/api/research-sessions": "_post_research",
        "/api/research-chat": "_post_research",
        "/api/research-cancel": "_post_research",
        "/api/research-attachments": "_post_research",
        "/api/portfolio-analysis": "_post_portfolio_analysis",
        "/api/search": "_post_search",
        "/api/issuer-research": "_post_search",
    }

    def do_POST(self) -> None:
        route = urlparse(self.path).path
        if self._rate_limited(route):
            return
        handler = self.POST_ROUTES.get(route)
        if handler is None:
            self.send_error(404)
            return
        getattr(self, handler)()

    def _post_studies_run(self) -> None:
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

    def _post_research(self) -> None:
        route = urlparse(self.path).path
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

    def _post_portfolio_analysis(self) -> None:
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

    def _post_search(self) -> None:
        route = urlparse(self.path).path
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
