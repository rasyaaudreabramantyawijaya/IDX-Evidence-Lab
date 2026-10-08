# Phase 3, step 3: slim down `web_app.py`

Status: plan, nothing implemented. Depends on the package split (step 2) being merged.

## Where `web_app.py` stands (1232 lines)

| Lines | What | Belongs to |
|---|---|---|
| 74-90, 319-390, 757-860 | `load_tickers`, `build_local_index`, text/snippet helpers | `research/` (search index for chat and issuer research) |
| 90-318 | `PortfolioUnavailable`, `portfolio_data_catalog`, `_portfolio_request`, `build_portfolio_analysis` | `portfolio/` |
| 864-925 | `build_issuer_research` | `research/` |
| 927-1204 | `build_source_report` | `research/` (it needs both `market` and `portfolio`, so it cannot sit in `market`) |
| 392-755 | `SearchHandler`: headers, rate limit, CORS, 15 GET and 8 POST routes | stays HTTP layer |
| 1206-1232 | `main()` | stays |

These builders depend only on a few constants (`ROOT`, `TOKEN_RE`, `MAX_INDEX_*`, `APPLICATION_PAGES`, `QUERY_EXPANSIONS`) and imports, so they move cleanly.

## Constraint that shapes the plan

Existing tests patch names inside `web_app`: `ROOT` (4 tests), `build_factor_zoo_payload`, `write_factor_zoo_artifact`, `load_news_universe`, `load_sector_heatmap`, `OpenRouterSearchAdapter`, `build_portfolio_analysis`, `SearchHandler.timeout`. The handler reads those names from `web_app` at call time. If the handler code moves to another module, the patches stop reaching it and the tests fail. So:

- Moving the **builders** out is safe: `web_app` re-exports them under the same names, and the handler still calls the `web_app` copies.
- Moving the **handler/route code** out requires changing those patch targets in about 8 test lines. That is an edit to existing tests and needs an explicit decision.

## Steps (each its own PR, each gated by `golden_master check` + full tests unedited)

**3a. Move builders out of `web_app` (no test edits).**
- `portfolio/portfolio_service.py`, `research/local_index.py`, `research/issuer_research.py`, `research/source_report.py`.
- `web_app` imports and re-exports every moved name, so `from idx_evidence_lab.web_app import build_local_index, _portfolio_request, ...` still works.
- Default argument `root=ROOT` is bound at definition time today; keep it by defining `ROOT` once in `core/paths.py` (same value: the repo root) so behavior is identical.
- Check by hand: `build_source_report` calls `build_factor_zoo_payload`; confirm no test relies on patching it through `web_app` for that path.
- Result: `web_app.py` goes from about 1230 to about 560 lines, all of it HTTP.

**3b. Make the handler readable (still no test edits).**
- Replace the long `if route == ...` chains in `do_GET` / `do_POST` with a route table (`{"/api/health": self._get_health, ...}`) and one small method per route, all still in `SearchHandler`.
- Pure refactor; the golden master covers all 94 request shapes.
- Adds `docs/architecture/api-routes.md`: route, method, body limit, rate-limit bucket, who owns it.

**3c. Optional: routes into `app/` modules.** Only if the team agrees to edit the 8 test patch targets (decision A below). Otherwise stop at 3b.

## Decisions for Rasya

1. **Stop at 3b, or do 3c?** Recommendation: stop at 3b and do routing properly as part of the FastAPI step, where the tests change anyway.
2. **`GET /api/portfolio-factor-zoo-data` rewrites a tracked file** (`docs/prototypes/portfolio-factor-zoo-data.json`) when numeric versions differ. Options: leave it; write to an untracked cache path; or serve the file read-only and regenerate through the existing export script. Needs her call because the file is also published in the repo.
3. **Before FastAPI:** HTML vs JSON 404 body, HEAD support (501 today), error-body shape. The golden master pins today's behavior, so each difference has to be approved explicitly and re-captured.
4. **Frozen studies files** (`studies_indicators/service/transforms`): schedule a PR to re-run the reference tests, regenerate `reports/studies-reference-manifest.json`, then move them.
5. **Leftover from step 2:** repoint `test_nonlegal_query_skips_pdf_extraction` to patch `research.research_retrieval.search_legal_corpus`, so it guards again.

## Risks and how they are covered

| Risk | Cover |
|---|---|
| A moved builder changes output | golden master (94 cases) and 415 existing tests |
| A patched name stops working | 3a keeps handler calls on `web_app` names; run the 8 patching tests first |
| Import cycles | `make arch` in CI |
| Default `root=ROOT` binding changes | same value, asserted by `test_global_search` and `test_openrouter_search` which call the builders with defaults |

## Outcome of 3a

- `web_app.py`: 1232 -> 468 lines. New modules: `portfolio/portfolio_service.py`, `research/local_index.py`, `research/issuer_research.py`, `research/source_report.py`, `core/paths.py` (shared `ROOT`).
- One test edited with approval: `test_portfolio_lab_has_weighted_subsector_circle_composition` greps `web_app.py` as text; it now reads `portfolio/portfolio_service.py`. Same assertion.
