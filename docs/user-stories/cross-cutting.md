# Cross-cutting stories

### CC-01 · Status states are consistent
- **Workspace:** Cross-cutting · **As a** P1/P2/P3 · **Status:** Partial
- **I want** every panel to show one of READY, PARTIAL, INSUFFICIENT_EVIDENCE, DATA REQUIRED or stale with the same look and wording
- **So that** I never mistake a missing or partial number for a complete one
- **Acceptance**
  - Given a panel whose input snapshot is missing, When it renders, Then it shows "DATA REQUIRED" (never blank, never a zero) and names the missing input.
  - Given a calculation with partial coverage, When it renders, Then it shows PARTIAL plus coverage (for example "n5/n20") and the reason.
  - Given a READY result, Then the page also states that READY means "can be computed for this input", not accurate or predictive.
  - The five states have distinct color **and** text/icon (not color alone).
- **Data limits:** states come from the backend (`status`, `data_quality`) and must not be re-derived in the UI.
- **Design:** GSM §? status tokens and badge component.

### CC-02 · The app works from either entry URL
- **Status:** Exists (fixed; finding 1 in README.md, guarded by `entry-urls.spec.ts`)
- **I want** `http://127.0.0.1:5500/` and `/docs/prototypes/idx-evidence-lab-user-journey.html` to show the same data
- **So that** the URL in the README, Docker and compose gives a complete app
- **Acceptance**
  - Given the server is running, When I open `/`, Then Dashboard and Market overview show no "DATA REQUIRED" caused by a 404.
  - Given the browser network log, When I visit every workspace, Then no request to the app itself returns 404.
- **Data limits:** panels that are legitimately empty because a snapshot is absent may still say DATA REQUIRED, but the cause must be the data, not a wrong path.

### CC-03 · Loading, empty and error states exist for every screen
- **Status:** Partial
- **I want** a loading message, an empty state with a next action, and an error state that says what failed and how to retry
- **So that** I know whether to wait, act or report a problem
- **Acceptance**
  - Given a slow or failed API call, When a panel is waiting, Then it shows a labelled loading state (not an empty box) and announces it to assistive tech (`aria-live`).
  - Given the API is down, When a panel fails, Then the message names the local server ("Server lokal tidak terhubung") and offers retry.
  - Given a first visit with no data (Watchlist, Studies canvas), Then the empty state offers one clear first action.

### CC-04 · Navigation is predictable and accessible
- **Status:** Partial (skip link, Back/Forward and `aria-label`s exist)
- **I want** a sidebar with distinct icons, visible focus, keyboard operation and working Back/Forward
- **So that** I can move between workspaces without a mouse and without losing my place
- **Acceptance**
  - Given keyboard only, When I press Tab, Then focus is always visible and I can reach every nav item and the "Lewati ke konten utama" skip link first.
  - Given I visit Dashboard then Screener then press Back, Then I return to Dashboard with the same scroll/filters.
  - Given the nav, Then each workspace has a unique icon (today Screener and Riset emiten share one).
  - Given a 390 px wide screen, Then the sidebar collapses and every workspace remains usable.

### CC-05 · One language and voice
- **Status:** Gap (finding 3)
- **I want** all labels, headings and messages in Indonesian (or a defined bilingual rule for finance terms such as "Hit Rate", "Z-Score")
- **So that** the product reads as one product
- **Acceptance**
  - Given any screen, When I read navigation and controls, Then no label mixes languages without a rule written in the GSM glossary.
  - Numbers use Indonesian format (`6.298,607`, `-1,20%`) everywhere, including charts and tooltips.
  - Dates use one format (`2026-09-24` or `24 Sep 2026`), chosen once.

### CC-06 · Responsive and print
- **Status:** Partial (breakpoints and print CSS exist)
- **I want** every workspace to be usable at 390 px and 1440 px and the source report to print cleanly
- **So that** I can review on a phone or save a PDF
- **Acceptance**
  - Given 390 px width, When I open each workspace, Then there is no horizontal page scroll (tables scroll inside their own container).
  - Given "Cetak / simpan sebagai PDF", Then the printed report has no navigation chrome and keeps tables readable.
- **Verify with:** the legacy fingerprint spec runs every workspace at both widths (`frontend/e2e/legacy`).

### CC-07 · Safety and privacy are visible, not implied
- **Status:** Exists (Settings guardline) / Partial elsewhere
- **I want** the app to say, where relevant, that it gives no advice, that API keys never reach the browser, and that private legal PDFs are not sent to a model
- **So that** I can trust and explain its limits
- **Acceptance**
  - Given Riset emiten with the model option on, Then the UI states what is sent to the provider and that private PDFs are not.
  - Given any result with a historical outcome, Then the text says it is descriptive, not a recommendation.
  - Given the browser dev tools, Then no API key appears in any response, local/session storage or page source.
