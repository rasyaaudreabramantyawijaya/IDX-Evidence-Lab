# Evidence and settings stories

### EVD-01 · See where every dataset comes from
- **Workspace:** Sumber & metode · **As a** P3 · **Status:** Exists
- **I want** a lineage table (dataset, status, count, coverage window, which features use it, limits, hash count) **so that** I can verify provenance
- **Acceptance**
  - Given the report, Then each dataset row shows status, snapshot count, entities, coverage window, last pull time and the features that depend on it.
  - Given a dataset with known gaps (for example "membership historis LQ45 tidak direkonstruksi"), Then the limit is stated in that row.
  - Given the summary counts (Universe, Daily OHLCV, Laporan emiten, Hash SHA-256), Then they match the inventory below them.

### EVD-02 · Save the report as a PDF
- **Status:** Exists
- **As a** P3 · **I want** "Cetak / simpan sebagai PDF" **so that** I can attach it to a review
- **Acceptance:** Given I press it, Then the browser print dialog opens with a clean layout (CC-06), tables are not clipped, and manifests are expanded.

### EVD-03 · Know what the app cannot claim
- **Status:** Exists
- **As a** P3 · **I want** explicit limits (snapshot, not live; not a recommendation; membership not historical) next to the data they affect **so that** I do not over-read results
- **Acceptance:** Given any workspace with computed results, Then a visible limit sentence exists within the same panel or its header, not only on a separate page.

### EVD-04 · Settings that tell the truth
- **Workspace:** Settings · **As a** P3 · **Status:** Gap (README finding 2)
- **I want** Settings to show only real settings and real guardrails **so that** nothing implies an account or login that does not exist
- **Acceptance**
  - Given the Settings screen, Then it does not show a named user, "sesi lokal simulasi" or a logout action unless authentication exists.
  - Given it lists the security guardline (keys server-side only, private legal corpus, LLM not a source of facts, no trading), Then each line is true of the current build.
  - Given the OpenRouter configuration, Then it shows whether a key is configured (yes/no) and never the key.
- **Data limits:** the page states that there is no authentication layer yet.
