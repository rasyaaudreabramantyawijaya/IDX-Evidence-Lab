# Frontend handoff

For the teammate building the new UI in `frontend/` (Vite + React + TypeScript). Everything else in the repo is already
guarded, so you can work in `frontend/` without touching Python.

## Day one
```bash
git switch main && git pull && git switch -c feat/<screen-name>
make run            # terminal 1, Python server on http://127.0.0.1:5500
make web-install    # once
make web-dev        # terminal 2, http://127.0.0.1:5173/app/  (proxies /api to :5500)
```
Node 22 or newer. Before every push: `make web-check` (typecheck, lint, format, unit tests). CI repeats it.

## What to build against
- **API:** `docs/architecture/api-routes.md` lists every route, body limit and owner. Responses are pinned by
  `tests/golden/`; do not ask for shape changes casually, ask the backend owner and add a golden case together.
- **Behavior to match:** `docs/user-stories/` (acceptance criteria per screen). Open items marked `Gap` are
  improvements the new UI should include.
- **Design tokens:** `frontend/src/styles/tokens.css` (placeholder until the GSM lands). Never hard-code colors or sizes.
- **Current UI for reference:** `http://127.0.0.1:5500/` (source in `frontend/legacy/`, do not edit while porting).

## Rules that CI enforces
- No inline `<script>`, no `eval`, no external hosts: the server sends a strict CSP. Inline `style=` attributes are only
  tolerated for the old page; avoid them in new code (use classes and CSS variables).
- No images, SVG, PDF or zip files in git (hygiene job). Draw charts in code.
- Strict TypeScript, ESLint, Prettier, unit tests (Vitest) for logic, Testing Library for components.
- API keys never appear in frontend code (`VITE_*` variables are public).

## Porting one screen
1. Pick a workspace and its stories (for example `docs/user-stories/market.md`).
2. Build it under `frontend/src/` (one folder per workspace; typed calls through `src/api/client.ts`).
3. Add tests: logic in Vitest, one Playwright spec in `frontend/e2e/` for the main flow.
4. Compare with the old page side by side; list intended differences in the PR.
5. When the screen is accepted, the old workspace is retired in a separate PR (its fingerprints are updated or removed).

## Seeing your build served by Python
Not wired yet (planned under `/app/`, see `docs/architecture/open-decisions.md` section D). Until then use `make web-dev`.

## Getting help
Backend questions: Rasya. Design standard: the GSM owner. Failing checks: paste the CI log in the PR.
