# Legacy UI chunks

`docs/prototypes/app.css` and `app.js` are generated from these files by `python scripts/build_legacy_ui.py`
(`make legacy-build`). Do not edit the generated files; CI and `tests/test_legacy_build.py` fail if they drift.

## Order is behavior
- `scripts/*.js` are consecutive slices of **one closure** `(()=>{ ... })()`. Variables are shared across chunks and
  several functions are declared twice (for example `dashboard`, `screener`, `market`): the **last** declaration wins.
  Reordering, merging or renaming chunk files can silently change which version runs.
- `styles/*.css` are joined in order; later rules override earlier ones.
- Files are joined in file-name order. Numeric prefixes are unique and step by 10: to insert a chunk, pick a number
  between its neighbours (e.g. `065-...`). The test suite rejects duplicate or unordered prefixes.

## Changing something
1. Edit inside a chunk.
2. `make legacy-build`.
3. Run `LEGACY_BASE_URL=<url from "python tests/golden_master.py serve"> npm run e2e -- e2e/legacy` in `frontend/`.
   If the change is intentional, refresh the fingerprints with `UPDATE_LEGACY=1` and review the diff.
4. Commit chunk, generated files and fingerprints together.
