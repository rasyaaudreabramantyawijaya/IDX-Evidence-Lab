# Frontend workspace

Vite + React + TypeScript (strict). This is the environment for the new UI; the current UI is still
`docs/prototypes/idx-evidence-lab-user-journey.html` and keeps working untouched.

## Run

```bash
make run          # terminal 1: Python server on http://127.0.0.1:5500
make web-install  # once (npm ci)
make web-dev      # terminal 2: http://127.0.0.1:5173/app/
```

The dev server proxies `/api/*` to the Python server, so browser and API share one origin as in production.
Another backend address: `VITE_API_TARGET=http://127.0.0.1:5600 npm run dev`.

## Commands (run in `frontend/`)

| Command                           | What                                                        |
| --------------------------------- | ----------------------------------------------------------- |
| `npm run typecheck`               | TypeScript, strict, `noUncheckedIndexedAccess`              |
| `npm run lint`                    | ESLint (typescript-eslint, react-hooks)                     |
| `npm run format` / `format:check` | Prettier                                                    |
| `npm test`                        | Vitest + Testing Library (jsdom), files `src/**/*.test.tsx` |
| `npm run e2e`                     | Playwright smoke test (needs the backend running)           |
| `npm run build`                   | typecheck, then `dist/`                                     |

CI runs typecheck, lint, format, tests and build on every PR (`frontend` job). The browser smoke test
(`frontend-e2e`) is report-only for now.

## Layout

```
src/api/client.ts      typed fetch wrapper; routes are in docs/architecture/api-routes.md
src/styles/tokens.css  design tokens: placeholder values, replace with the Graphic Standard Manual
src/App.tsx            placeholder shell that calls /api/health
e2e/                   Playwright specs
```

## Rules

- **Do not change the backend response shapes** from here. The golden master (`tests/golden/`) pins them. If the UI needs
  a new field, add an endpoint or ask the backend owner.
- All colors, spacing and fonts come from `tokens.css`. No hard-coded values in components.
- No inline `<script>`, inline `style=` attributes or `eval`: the production CSP will block them
  (`docs/security/headers-and-rate-limits.md`). The build already emits external JS and CSS only.
- No images, SVG files or PDFs in git (CI `hygiene` job rejects them). Draw charts in code.
- Never put API keys in the frontend. Anything prefixed `VITE_` is public.
- Keep user-visible text in Indonesian, matching the existing app.

## The current (legacy) page

`docs/prototypes/idx-evidence-lab-user-journey.html` is now only markup. Its CSS and JavaScript live as ordered chunks in
`frontend/legacy/styles/` and `frontend/legacy/scripts/` and are built into `docs/prototypes/app.css` and `app.js`:

```bash
make legacy-build                       # or: python scripts/build_legacy_ui.py
python scripts/build_legacy_ui.py --check   # CI: committed output must match a fresh build
```

- **File order is behavior.** The chunks are slices of one closure and several functions are declared twice (the last
  one wins). Do not reorder or rename chunk files; edit inside them, rebuild, commit chunk and output together.
- Browser guard for this page (needs a backend; `python tests/golden_master.py serve` prints a throwaway one):
  `LEGACY_BASE_URL=<url> npm run e2e -- e2e/legacy`. It compares DOM, text and computed styles of every workspace at
  desktop and mobile width with `e2e/legacy/legacy-fingerprints.json`, and fails on any CSP violation.
  After an intentional UI change: `UPDATE_LEGACY=1 LEGACY_BASE_URL=<url> npm run e2e -- e2e/legacy/legacy.spec.ts`.
- Tests that assert on the page source read it through `tests/legacy_source.py` (markup + css + js).

## Not wired yet

- The backend does not serve `dist/` yet. `base` is already `/app/`; serving it needs a small backend change
  (a static route under `/app/` plus a golden-master case) and is a separate PR.
- The strict CSP is enforced (`style-src-attr 'unsafe-inline'` is the one deliberate exception, see `docs/security/headers-and-rate-limits.md`). The React build is already compatible.
- Visual regression for new screens: the legacy page has fingerprints (above); add the same kind of spec per new screen.
