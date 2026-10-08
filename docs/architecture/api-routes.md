# API routes

Source of truth: `SearchHandler.GET_ROUTES` and `SearchHandler.POST_ROUTES` in `src/idx_evidence_lab/web_app.py`.
`tests/test_route_table.py` fails if a route has no method or no golden-master snapshot.

Anything not listed returns the stdlib 404 page. `HEAD` and `PUT` return 501. Every response carries the security headers
from `docs/security/headers-and-rate-limits.md`.

## GET

| Route | Method | Owner | Notes |
|---|---|---|---|
| `/api/health` | `_get_health` | app | Used by the Docker health check |
| `/api/dashboard-data` | `_get_dashboard_data` | market | IHSG, news, LQ45 universe |
| `/api/screener-analysis` | `_get_screener_analysis` | market | |
| `/api/sector-heatmap` | `_get_sector_heatmap` | market | |
| `/api/news-universe` | `_get_news_universe` | market | |
| `/api/issuer-daily?ticker=` | `_get_issuer_daily` | market | 404 when the ticker has no data |
| `/api/source-report` | `_get_source_report` | research | |
| `/api/research-targets` | `_get_research_targets` | research | |
| `/api/portfolio-data` | `_get_portfolio_data` | portfolio | |
| `/api/portfolio-factor-zoo-data` | `_get_factor_zoo_data` | portfolio | **Rewrites `docs/prototypes/portfolio-factor-zoo-data.json` when the fingerprint changes** (open decision) |
| `/api/portfolio-factor-zoo-view` | `_get_factor_zoo_view` | portfolio | |
| `/api/studies-catalog` | `_get_studies_catalog` | studies | |
| `/`, `/index.html`, `/docs/prototypes/*` | `_serve_prototype` | app | Static files, fixed allowlist |

## POST

| Route | Method | Body limit | Rate-limit bucket | Owner |
|---|---|---|---|---|
| `/api/search` | `_post_search` | 4 KB | post | research |
| `/api/issuer-research` | `_post_search` | 4 KB | **chat** (can call OpenRouter) | research |
| `/api/research-sessions` | `_post_research` | 64 KB | post | research |
| `/api/research-chat` | `_post_research` | 64 KB | **chat** (can call OpenRouter) | research |
| `/api/research-cancel` | `_post_research` | 64 KB | post | research |
| `/api/research-attachments` | `_post_research` | 7 MB | post | research |
| `/api/portfolio-analysis` | `_post_portfolio_analysis` | 16 KB | post | portfolio |
| `/api/studies-run` | `_post_studies_run` | 16 KB | post | studies |

CORS: only `/api/portfolio-*` and `/api/studies-*` answer a cross-origin request, and only for `http://127.0.0.1:5500`
and `http://localhost:5500`. Preflight (`OPTIONS`) is accepted for `/api/portfolio-analysis` and `/api/studies-run`.
