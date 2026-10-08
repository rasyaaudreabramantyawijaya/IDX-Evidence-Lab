# Open decisions (for Rasya, the code owner)

Everything else from the hardening plan is merged. These items need her decision or her GitHub admin rights.
Each has today's behavior, the options, and a recommendation. Reply on the PR or tick the box.

## A. GitHub settings (admin only, 10 minutes)
- [ ] **Branch protection on `main`** following `docs/security/branch-protection.md`: required checks `ci` and `security`,
  1 review, Code Owners review, no force-push. (The API reports no protection rule today, so merges are not gated yet.)
- [ ] **Dependabot alerts and security updates**, and secret scanning with push protection if the plan offers it.
- [ ] **Packages:** confirm the container package `hackathon_sectors` is **private**, and who gets `read:packages`
  (image contains prototype data JSON; `data/` itself is never in the image).
- [ ] **CODEOWNERS:** add the frontend teammate for `frontend/` and the GSM owner for `docs/design-system/` and
  `docs/user-stories/` (needs their GitHub handles; edit `.github/CODEOWNERS`).
- [ ] Optional: set repository variable `ENABLE_ADVANCED_SECURITY=true` if GitHub Advanced Security is available (turns on CodeQL and dependency review).

## B. API behavior before any FastAPI migration
Today's behavior is pinned by `tests/golden/`. A new framework would change these unless decided otherwise.

| Topic | Today | Options | Recommendation |
|---|---|---|---|
| Unknown route (404) | Python's HTML error page | Keep HTML; or JSON `{"error":"NOT_FOUND"}` | JSON for `/api/*`, HTML elsewhere |
| `HEAD` requests | `501` (not supported) | Support HEAD on GET routes | Support it (health checks and proxies use it) |
| Unsupported method (`PUT`, `DELETE`) | `501` HTML | `405` JSON with `Allow` header | `405` JSON |
| Validation errors | Different shape per route (`{"error": "..."}` vs `{"status":"INVALID_REQUEST","error":...}`) | Keep per route; or one shape `{"status","error"}` | Keep until the new frontend needs one shape; document in `api-routes.md` |
| Move to FastAPI at all? | Stdlib server works and is covered by the golden master | Stay; or migrate for OpenAPI docs, typed requests | Stay until there is a concrete need (typed API for the React client is the main one) |

## C. Data and files
- [ ] **`GET /api/portfolio-factor-zoo-data` rewrites a tracked file** (`docs/prototypes/portfolio-factor-zoo-data.json`) when
  the numeric fingerprint differs (it dirties the working tree and a read-only container filesystem cannot support it).
  Options: leave; write to an untracked cache path; serve read-only and regenerate through the export script.
  Recommendation: serve read-only and regenerate through the existing export script.
- [ ] **Frozen studies files.** `reports/studies-reference-manifest.json` pins SHA-256 of `studies_indicators.py`,
  `studies_service.py`, `studies_transforms.py`, so they stay unmoved at the top level. To move them: re-run the
  reference tests, regenerate the XML and manifest (no generator script is in the repo), then move. Who owns that script?
- [ ] **Pinned test**: `test_nonlegal_query_skips_pdf_extraction` patches a name that no longer reaches the code after the
  package split, so it passes but guards less. Repoint it to `research.research_retrieval.search_legal_corpus`.

## D. Frontend
- [ ] Retire the old page per workspace or all at once? (Recommendation: per workspace, keep the fingerprint test for what remains.)
- [ ] Serve `frontend/dist` from the Python server under `/app/` (small backend change, golden case, Docker build stage),
  or host the static build separately (for example Vercel) and proxy `/api`? Recommendation: `/app/` first, same origin, no CORS.
- [ ] `style-src-attr 'unsafe-inline'` stays while the old page exists (per-data-point style attributes). Remove it when
  the old page is retired.

## E. Release
- [ ] Pin Docker dependencies to `uv.lock` (reproducible images). Image is `linux/amd64` only; add `arm64` if a host needs it.
- [ ] Choose a host for a demo deployment (see `docs/runbooks/deploy.md`). The app has no authentication, so put login in front of it or keep it private.
- [ ] Promote the report-only checks (`frontend-e2e`, Trivy) to required once they have run green a few times.
