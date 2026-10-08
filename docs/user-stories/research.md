# Research stories (Screener, Watchlist, Riset emiten, Dossier emiten)

### RSC-01 · Filter the LQ45 list by sector and regime
- **Workspace:** Screener · **As a** P1 · **Status:** Exists
- **I want** to filter 45 issuers by sector and by individual trend regime **so that** I can shortlist names to read
- **Acceptance**
  - Given the Screener, When I choose "Energy" and "Tren menguat", Then the table shows only matching issuers and the count line updates ("Menampilkan N dari 45 emiten").
  - Given I press Reset, Then both filters clear.
  - Given an issuer whose regime cannot be computed, Then it appears under "Belum dihitung", not under a guessed regime.
- **Data limits:** regime = close vs SMA50/SMA200 of that stock, not the IHSG label.

### RSC-02 · Read historical event results honestly
- **Workspace:** Screener · **As a** P2 · **Status:** Exists
- **I want** flow strength (Z20), sample sizes (n5/n20), 5D/20D outcome, hit rate and CI95 for each issuer **so that** I can judge how much evidence there is
- **Acceptance**
  - Given a row, Then Z20, `n5 / n20`, outcomes, hit rate and CI95 are shown with units and the event definition is visible above the table.
  - Given a small sample (low n), Then the row is visibly lower-confidence (wide CI shown, not hidden).
  - Given the table, Then columns sort ascending/descending by pressing their header, with a visible sort indicator and `aria-sort`.
  - The page says results are "return bruto historis ... bukan rekomendasi".

### RSC-03 · Keep a personal watchlist
- **Workspace:** Watchlist · **As a** P1 · **Status:** Exists
- **I want** to save issuers and see their summary **so that** I can come back to them
- **Acceptance**
  - Given an empty watchlist, Then I see "Watchlist kamu masih kosong" and a primary action "＋ Tambah emiten".
  - Given I add BBCA via the picker, When I reload the page, Then BBCA is still there (stored in this browser only; the page says so).
  - Given the list, Then I can sort by any column and remove an issuer.
  - The table carries the "DATA LOKAL · BUKAN REAL-TIME" label.
- **Data limits:** watchlist lives in the browser (`localStorage`), not on the server; clearing site data deletes it.

### RSC-04 · Open an issuer dossier
- **Workspace:** Dossier emiten · **As a** P1 · **Status:** Exists
- **I want** a per-issuer page with overview, price history, foreign flow, evidence, historical analogs, event study, outcomes, broker and disclosure sections **so that** I see everything known about the name in one place
- **Acceptance**
  - Given I open an issuer from Screener, Watchlist or search, Then the dossier loads from the local snapshot and shows the as-of date and coverage start for that issuer (some start later, e.g. AADI from 5 Dec 2024).
  - Given a section lacks data (for example broker activity at issuer level), Then it states that explicitly instead of hiding the section.
  - Given a price chart, When I hover or focus it, Then date and value appear, and the same series is available as a table.

### RSC-05 · Ask a question about an issuer or sector
- **Workspace:** Riset emiten · **As a** P1/P2 · **Status:** Exists
- **I want** a chat with a chosen target (issuer or sector) that answers from local evidence **so that** I can ask in plain language
- **Acceptance**
  - Given no target, Then the page says there is no default issuer and asks me to choose ("Fokuskan pertanyaanmu").
  - Given a target and a question, When I send it, Then the answer lists its evidence items with source, date and limits before the interpretation ("Bukti dahulu, interpretasi kemudian").
  - Given insufficient evidence, Then the answer says INSUFFICIENT_EVIDENCE and does not fill the gap.
  - Given I press cancel mid-request, Then the request stops and the session stays usable.

### RSC-06 · Choose Instant or Agent and know what is sent
- **Status:** Partial
- **As a** P2 · **I want** a clear switch between local-only (Instant) and model-assisted (Agent) answers **so that** I control what leaves my machine
- **Acceptance**
  - Given no API key is configured, Then Agent is disabled with the reason, and Instant works.
  - Given Agent is on, Then the UI states that only allowed snippets go to the provider and private legal PDFs never do.
  - Given the provider fails or rate-limits, Then the answer falls back to local with a visible notice (for example "Qwen tidak tersedia ...").
- **Data limits:** the model summarizes permitted evidence; it is not a source of facts.

### RSC-07 · Attach my own file to a question
- **Status:** Partial ("File upload belum tentu terbaca")
- **As a** P2 · **I want** to attach a PDF or text file to the session **so that** the answer can use it
- **Acceptance**
  - Given a readable text-layer PDF, Then its text is used and the attachment chip shows page count.
  - Given an unreadable or scanned file, Then the UI says it cannot be read (no OCR) instead of silently ignoring it.
  - Given a file over the size limit or with an unsupported type, Then upload is refused with the reason.
  - Given I remove an attachment, Then it is no longer used.

### RSC-08 · Resume context across workspaces
- **Status:** Gap ("executor chat lintas workspace ... belum selesai")
- **As a** P1 · **I want** the chat to open the right workspace and filters when I ask ("tampilkan sektor energi yang tren menurun") **so that** I do not navigate manually
- **Acceptance:** Given such a request, Then the app proposes the workspace and filters, applies them on confirm, and says when it cannot.
