# Analysis stories (Studies, Portfolio Lab)

### ANA-01 · Build a study from a target and a window
- **Workspace:** Studies · **As a** P2 · **Status:** Exists
- **I want** to pick sector(s) or issuers, a window (5, 20, 60 sessions or all available history) and a panel type **so that** I can compare features
- **Acceptance**
  - Given an empty canvas, Then I see "Canvas masih kosong" with how to add a panel or generate a layout.
  - Given I add "Volatility" for BBCA with a 20-session window and press "Jalankan semua panel", Then the panel shows a value, unit, coverage and a status (READY/PARTIAL/...).
  - Given a panel, Then its formula, window, dates and limits are inspectable.
  - READY is explained as "bisa dihitung", not "akurat".
- **Data limits:** widgets are an allowlist; calculations run locally without an LLM ("Perhitungan lokal · tanpa LLM").

### ANA-02 · Trust a formula because it was tested
- **Status:** Exists
- **As a** P3 · **I want** each panel to show whether its formula is verified against reference tests **so that** I can tell tested from untested
- **Acceptance:** Given a widget with a passing reference-test manifest, Then it shows the verification scope and case counts; Given the manifest is missing or the source hash no longer matches, Then it shows NOT_TESTED, never REFERENCE_VERIFIED.

### ANA-03 · Arrange and keep a study layout
- **Status:** Partial
- **As a** P2 · **I want** to move, zoom and save panels ("Simpan", "Dashboard tersimpan") **so that** I can return to my setup
- **Acceptance:** Given I arrange panels and save, When I reload, Then the layout returns; Given zoom controls (−, 100%, +, Reset), Then they work by mouse and keyboard.
- **Data limits:** layouts are stored in this browser only; say so near the save control.

### ANA-04 · Get an allocation for the issuers I choose
- **Workspace:** Portfolio Lab · **As a** P1/P2 · **Status:** Exists
- **I want** to select LQ45 issuers, a risk profile (Konservatif, Moderat, Agresif), a risk-free rate and optional capital, and get weights and lots **so that** I see a diversified long-only starting allocation
- **Acceptance**
  - Given fewer than the minimum issuers, Then the run button explains what is missing.
  - Given a valid selection, When I run the analysis, Then I get weights (summing to 100%), expected return, volatility, Sharpe, drawdown and the benchmark comparison, each with method and period.
  - Given capital is entered, Then lots are computed with a leftover amount; Given capital is empty, Then lot sizing is omitted (not zero).
  - The page says the factor and risk results are descriptive and not a recommendation; there is no trade button.
- **Data limits:** needs enough daily history per issuer; issuers with short history are flagged (for example AADI 424 sessions vs 712).
- **Design:** GSM §? selector list, profile cards, result cards, charts with tooltips.

### ANA-05 · Understand portfolio risk, not only return
- **Status:** Exists
- **As a** P2 · **I want** CAPM explanation, Sortino downside, drawdown paths and distribution, scenario simulations and walk-forward results **so that** I see how the allocation behaves in bad periods
- **Acceptance:** Given results, Then each chart has a title, units, a text explanation of how to read it, and a table or summary equivalent; Given an unavailable method, Then it is marked UNAVAILABLE with the reason.

### ANA-06 · Explore the factor map
- **Workspace:** Portfolio Lab (Factor Zoo) · **As a** P2 · **Status:** Partial
- **I want** a 3D factor explorer (Value, Momentum, Quality scores) with hover details and the snapshot dates **so that** I can see where each issuer sits
- **Acceptance**
  - Given the explorer, When I hover or focus a point, Then it shows issuer, X/Y/Z scores and the price/report/coverage dates.
  - Given I drag to rotate, Then the tooltip hides while dragging.
  - Given the published artifact is out of date, Then the page says so; it does not silently show stale data.
- **Note:** the data endpoint currently rewrites a tracked file when the fingerprint changes (backend decision pending).
