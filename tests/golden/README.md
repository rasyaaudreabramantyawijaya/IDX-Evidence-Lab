# Golden-master API snapshots

Recorded HTTP behavior of the API (status, contract headers, parsed body) for 94 requests: every route, plus
validation errors, CORS, oversized bodies and unsupported methods. The Phase 3 refactor must keep these identical.

```bash
python tests/golden_master.py check      # compare a fresh server with these files (also runs in pytest)
python tests/golden_master.py capture    # rewrite the files, only after an intentional change
GOLDEN_BASE_URL=http://127.0.0.1:8000 pytest tests/test_golden_master.py   # check another server (e.g. FastAPI)
GOLDEN_REL_TOL=1e-12 GOLDEN_ABS_TOL=1e-12 python tests/golden_master.py check   # strict, same machine only
```

`capture` and `check` run the server from a throwaway copy of the runtime files (`src`, `configs`, `reports`,
`docs/prototypes`, `data`), so they never modify your working tree. Some GET endpoints rewrite tracked files
(for example `/api/portfolio-factor-zoo-data`), which is why a copy is used.

## What is compared
- Status code and an allowlist of headers (content type, cache, CORS, `Retry-After`, security headers).
- JSON bodies field by field. Key order is ignored. Floats may differ by a relative 1e-6 (absolute 1e-8 near zero)
  because numpy/scipy releases change optimizer output slightly across Python versions.
- Static files and non-JSON responses by SHA-256 of the exact bytes. Stdlib HTML error pages (404/501) are compared
  by status and headers only, since their text changes between Python versions.

## What is normalized (varies without any code change)
- Random ids (`uuid4`): session, request and artifact ids.
- `computed_at_utc`, machine-specific values (`local_root`, `local_documents`, `openrouter_configured`).
- `artifact_fingerprint`, and the hash of `docs/prototypes/portfolio-factor-zoo-data.json` (plus request
  fingerprints derived from it): hashes of numerically computed content.

## Not covered
- Calls to OpenRouter. No request here ever sets `use_model` to true, and the server starts without a key.
- Rate limiting (429) is covered by `tests/test_rate_limit.py`; limits are switched off while recording.
- Upload size limit for attachments (7 MB) and timing/performance.
- Behavior with different local data. These snapshots describe the committed `data/` snapshot.

Review any diff in these files like code: a changed snapshot means the API's behavior changed.
