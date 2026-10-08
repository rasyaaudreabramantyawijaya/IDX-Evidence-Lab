# Market stories (Dashboard, Market overview, News Universe)

### MKT-01 · See today's market state on one screen
- **Workspace:** Dashboard · **As a** P1 · **Status:** Partial (works at the long URL, degraded at `/`, see CC-02)
- **I want** the Dashboard to show IHSG close and daily change, market regime, breadth, unusual foreign flow and latest news
- **So that** I can decide which area to research first
- **Acceptance**
  - Given the snapshot is loaded, When I open Dashboard, Then I see IHSG (for example `6.298,607`, `-1,20%`), the as-of date (`2026-09-24`), observation count and source line.
  - Given the regime panel, Then it shows "Tren menguat/melemah/campuran" from SMA 50 vs SMA 200 and says it is a descriptive baseline, not a forecast.
  - Given a panel lacks its snapshot, Then it shows DATA REQUIRED with the missing input named (CC-01).
  - Given I press "Segarkan data lokal", Then data reloads from the local server and the loading state is announced.
- **Data limits:** snapshots end on the stated date; nothing is real-time.
- **Design:** GSM §? KPI card, regime badge, panel header with "Detail pasar" link.

### MKT-02 · Jump from a summary to its detail
- **Status:** Exists
- **As a** P1 · **I want** each Dashboard panel to link to its detailed view ("Detail pasar", "Buka Market Overview") **so that** I can drill down without searching
- **Acceptance:** Given any Dashboard panel with a detail link, When I activate it (mouse or Enter), Then the matching workspace opens and Back returns to the Dashboard.

### MKT-03 · Judge market stress without being told a prediction
- **Workspace:** Market overview · **As a** P2 · **Status:** Exists
- **I want** the EVT tail-risk explorer (empirical P95 loss, GPD shape with bootstrap interval, threshold sensitivity, 3D surface) with clear caveats
- **So that** I understand historical tail behavior of IHSG
- **Acceptance**
  - Given the surface data matches the active snapshot, Then I can rotate/zoom the 3D chart and read the axis explanation.
  - Given the surface grid does not match the snapshot, Then the page says "GRID BELUM TERSEDIA" and how to rebuild it, instead of drawing stale data.
  - Given any EVT number, Then the page states it is "BUKAN PROBABILITAS CRASH".
- **Design:** GSM §? 3D chart controls, color scale legend, caveat callout.

### MKT-04 · Compare sectors at a glance
- **Workspace:** Market overview · **As a** P1 · **Status:** Exists
- **I want** a sector heatmap with hover details **so that** I can see which sectors drive the market
- **Acceptance:** Given the heatmap, When I hover or focus a cell, Then a tooltip shows sector, values and period; the same data is available as a table for keyboard and screen-reader users.

### MKT-05 · Read foreign flow and valuation context
- **Status:** Partial
- **As a** P2 · **I want** daily foreign buy/sell, monthly Z-score, market cap / operating cash flow and forward P/E coverage **so that** I can see positioning and valuation breadth
- **Acceptance:** Given each panel, Then it shows period, unit (Rp, %), coverage ("45 saham snapshot") and its state; Given missing aggregates, Then it says which snapshot is required (not an empty chart).

### MKT-06 · Scan news without a feed
- **Workspace:** News Universe · **As a** P1 · **Status:** Exists
- **I want** a "Top 5" and per-article analysis marked "Offline heuristic · bukan model" **so that** I can see what is material without trusting a black box
- **Acceptance**
  - Given the news snapshot, When I open News Universe, Then each item shows date, linked ticker, the material terms found, and that it is offline analysis, not a real-time feed.
  - Given I select an article, Then its detail and the relation graph update, and the graph has keyboard-reachable controls.
  - Given an article with no ticker match, Then it is shown without a ticker rather than guessed.
- **Data limits:** news is a snapshot window; sentiment/materiality is heuristic.

### MKT-07 · Search everything from one box
- **Workspace:** Cross-cutting (top bar) · **As a** P1 · **Status:** Exists
- **I want** one search box to find issuers, sectors, news, filings and features **so that** I do not need to know the menu
- **Acceptance**
  - Given I type a ticker (for example `BBCA`), When I submit, Then results list matching documents with source class and snippet, and an option to open the issuer.
  - Given a query with no evidence, Then the result says INSUFFICIENT_EVIDENCE rather than returning unrelated items.
  - Given the model option is off, Then the notice says the search is local and no LLM or web search was used.
