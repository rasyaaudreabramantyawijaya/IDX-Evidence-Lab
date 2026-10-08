# Phase 4: frontend (done for the current UI; new UI is the frontend teammate's)

## Decision
The new frontend and its logic are built by a teammate in **Vite + React + TypeScript** (`frontend/`). This repo provides
the environment and guard rails. For the current UI, Phase 4 splits the single file, adds browser guards and enforces CSP,
without changing what users see.

## What was done
1. **Browser guard (4a).** `frontend/e2e/legacy/`: for every workspace (10) at desktop and mobile width, a fingerprint of the
   rendered DOM, visible text and computed styles, plus failed requests, committed in `legacy-fingerprints.json`.
   Hashes are platform independent. A second spec opens every workspace under the enforced CSP and fails on any violation.
2. **Split (4b).** The 94 KB inline CSS and 364 KB inline JavaScript moved into 17 CSS and 13 JS chunks in
   `frontend/legacy/`. `scripts/build_legacy_ui.py` joins them into `docs/prototypes/app.css` and `app.js`; CI fails if the
   committed files are stale. Proof of no change: inlining the built files back into the HTML reproduces the old file
   byte for byte; all 20 fingerprints are identical; 18 of 20 screenshots are pixel-identical (the other two differ between
   two runs of the same code, so they are non-deterministic and not a regression).
3. **CSP (4c).** The HTML has no inline script or `<style>`. `Content-Security-Policy` is enforced:
   `default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'`.
   The Report-Only header is gone. A test confirmed an injected inline script is blocked and the app raises no violations.
4. **Tests.** 13 test files that asserted on the page source now read it through `tests/legacy_source.py`
   (markup + css + js). Assertions are unchanged. `tests/test_security_headers.py` was updated for the new policy.
5. **Golden master** recaptured on purpose: only the CSP header changed (all cases), the HTML body, and two new cases
   (`app.js`, `app.css`). No API response body changed.
6. **React workspace** in `frontend/` with CI (`frontend` job), unchanged from the earlier step.

## Not done (by design)
- The 92 inline `style=` attributes stay: many are per-data-point widths and colors and cannot be static classes.
- The old page is not rewritten in React. The teammate replaces it workspace by workspace; retire the old page when done.
- Serving `frontend/dist` from the backend under `/app/` (small backend change, golden case, Docker build stage).
- Pixel baselines in CI (fonts differ between macOS and Linux); fingerprints cover CI.

## Questions for Rasya
1. CODEOWNER for `frontend/` (needs the teammate's GitHub handle)?
2. When is the old page retired: per workspace or all at once?
3. OK with `style-src-attr 'unsafe-inline'`?
