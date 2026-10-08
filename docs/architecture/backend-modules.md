# Backend modules: current dependencies and proposed packages

Status: step 2 done (packages created, old import paths kept as aliases). `app/`, routers and FastAPI are later steps. Generated from the imports in `src/idx_evidence_lab/` (50 modules, 7.5k lines).

## Proposed packages (dependencies point downward only)

| Package | Modules that would move in | Depends on |
|---|---|---|
| `app/` (HTTP edge) | `web_app`, `security`, `config` | everything below |
| `research/` | `research_service`, `research_context`, `research_retrieval`, `research_sessions`, `research_types`, `research_validation`, `research_attachments`, `task_navigation`, `openrouter_live`, `legal_corpus` | `providers`, `market`, `portfolio`, `core` |
| `studies/` | `studies_adapters`, `studies_artifacts`, `studies_registry`, `studies_types`, `studies_verification` (`studies_service`, `studies_transforms`, `studies_indicators` stay frozen at top level, see below) | `market`, `portfolio`, `core` |
| `portfolio/` | `portfolio_data`, `portfolio_factors`, `portfolio_analytics`, `portfolio_optimization`, `portfolio_scenarios`, `portfolio_amounts` | `market`, `core` |
| `market/` | `market_data`, `market_overview_analytics`, `screener_analysis`, `issuer_dossier`, `news_analysis`, `signal_baseline`, `broker_archive` | `core` |
| `providers/` | `openrouter_mock`, `sectors_live`, `mock_sectors`, `source_policy`, `query_plan` | `core` |
| `core/` | `schemas`, `evidence`, `search`, `acquisition` | nothing |

## Findings that need a decision

1. (Fixed in step 2) `research_retrieval` imported `web_app`. A domain module depends on the HTTP layer, so `web_app` can never be split cleanly until that import is removed (likely one helper that should live in `core/` or `research/`).
2. `web_app.py` is 1270 lines and imports 20 modules. It is the only place that knows every route; moving routes into per-area routers is step 3.
3. `portfolio_factors` depends on `market_data` (659 lines, the largest shared module). `market/` is the real foundation; split it last.
4. Leaf modules with no internal imports (`news_analysis`, `signal_baseline`, `portfolio_analytics`, `studies_indicators`, `research_types`, ...) are safe to move first.

## Rules to enforce with import-linter once the layout is agreed

- `core` imports nothing from the other packages.
- `market`, `providers` import only `core`.
- `portfolio` imports `market`, `core`.
- `studies`, `research` import `portfolio`, `market`, `providers`, `core`, never each other except `research -> studies` if needed.
- Nothing imports `app`.

## Safety

Every step must pass `python tests/golden_master.py check` and the existing tests unedited. Old import paths (`idx_evidence_lab.market_data`, ...) stay as re-export shims so tests need no edits.

## What was done in step 2

- Modules moved into `core/ market/ portfolio/ providers/ studies/ research/`; imports inside them are relative to the new layout. `web_app`, `security`, `config`, `demo` stay at the top level for now (the `app` layer).
- Every old path (for example `idx_evidence_lab.market_data`) is a small alias module that points to the same module object, so existing imports and `monkeypatch` calls keep working.
- `search_legal_corpus` moved out of `web_app` into `research/legal_corpus.py`, removing the `research_retrieval -> web_app` import. `web_app` still exposes the same name.
- The layering rule is enforced by `make arch` (`lint-imports`) and in CI.
- **Frozen on purpose:** `studies_indicators.py`, `studies_service.py` and `studies_transforms.py` stay unmoved and byte-identical. `reports/studies-reference-manifest.json` pins their SHA-256; changing or moving them turns every verified widget into `NOT_TESTED`. Moving them needs the reference tests re-run and the manifest regenerated, as its own reviewed PR.
- `scripts/export_portfolio_lab_notebook_data.py` now also bundles the real module files, because the old-path aliases alone would not import in the notebook bundle.
