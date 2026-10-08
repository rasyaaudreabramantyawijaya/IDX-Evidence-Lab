# Contributing

## Workflow
1. Branch from `main`: `feat/<topic>`, `fix/<topic>` or `chore/<topic>`.
2. Keep PRs small and say in the PR template whether any output changes.
3. Open a PR. CI (`ci` and `security`) must pass and CODEOWNERS must review. No direct pushes to `main`.

## Local setup
```bash
make setup     # venv + dependencies + dev tools
make test      # pytest
make lint      # ruff
make cov       # tests with coverage
make run       # local server on http://127.0.0.1:5500
```
Python 3.10+ is required.

Frontend (`frontend/`, Node 22+): `make web-install`, `make web-dev` (http://127.0.0.1:5173/app/, proxies `/api` to the Python server on :5500), `make web-check` (typecheck, lint, format, unit tests). See `frontend/README.md`.

The current UI's CSS/JS are built from `frontend/legacy/` (`make legacy-build`); never edit `docs/prototypes/app.js` or `app.css` by hand, CI checks they match the chunks.

## Rules
- Do not commit keys, `.env*`, provider data outside `data/raw/sectors/`, screenshots, PDFs or private corpora.
- Do not change calculation output silently. If a number or API field changes, say so in the PR.
- Tests are offline (fixtures and mocks). Do not add tests that call external services.
- Lint currently enforces syntax errors and real bugs only. Stricter rules will be introduced in dedicated PRs.
