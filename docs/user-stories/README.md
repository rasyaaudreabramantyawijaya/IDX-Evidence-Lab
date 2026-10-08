# User stories

Stories for IDX Evidence Lab, written to be checked in a browser and to feed the Graphic Standard Manual (GSM) and the
React rewrite in `frontend/`. Format follows `.github/ISSUE_TEMPLATE/user-story.yml`, so any story can be copied into an
issue. The UI text quoted in stories is the current Indonesian text.

## Personas
| ID | Who | Needs |
|---|---|---|
| **P1** | Retail investor researching an LQ45 issuer | Understand an issuer or the market quickly; know what the data does and does not prove |
| **P2** | Analyst or student doing deeper work | Run studies and portfolio calculations, trace every number to a source and a formula |
| **P3** | Reviewer (judge, teammate, maintainer) | Verify provenance, limits and safety claims without reading code |

## Rules every story inherits (cross-cutting, see `cross-cutting.md`)
1. **Evidence first.** Every number shows its source, date and limit. Nothing is presented as a prediction or advice.
2. **States are visible.** READY, PARTIAL, INSUFFICIENT_EVIDENCE, DATA REQUIRED (missing) and stale each look different and say why.
3. **Snapshot, not live.** The app reads local snapshots. Pages say "data lokal, bukan real-time" where it matters.
4. **No trade execution, no personal recommendation.**

## Files
| File | Workspaces | Stories |
|---|---|---|
| [cross-cutting.md](cross-cutting.md) | All screens | CC-01 to CC-07 |
| [market.md](market.md) | Dashboard, Market overview, News Universe | MKT-01 to MKT-07 |
| [research.md](research.md) | Screener, Watchlist, Riset emiten, Dossier emiten | RSC-01 to RSC-08 |
| [analysis.md](analysis.md) | Studies, Portfolio Lab | ANA-01 to ANA-06 |
| [evidence-and-settings.md](evidence-and-settings.md) | Sumber & metode, Settings | EVD-01 to EVD-04 |

Each story has: persona, want, so that, acceptance criteria (Given/When/Then), data limits and states, a design-standard
placeholder (`GSM §?`), and **Status**: `Exists` (behavior is in the app today, criteria describe how to verify it),
`Partial` (some of it works), or `Gap` (not built, or built wrongly).

> **How reliable are the statuses?** They come from reading the rendered text of every workspace, the code paths and the
> tests, and from one browser check (finding 1). They were not each exercised by hand. Treat `Exists` as "believed to
> exist, verify the acceptance criteria" and fix the wording of any story that turns out wrong.

## Findings from reading the live app (inputs to the stories and the GSM)
1. **Opening `http://127.0.0.1:5500/` degrades the Dashboard and Market overview.** The page loads
   `./market-overview-data.json` and `./ihsg-evt-tail-surface-data.json` relative to its own URL. At `/` those become
   `/market-overview-data.json` (404), so panels show "DATA REQUIRED" (2 on Dashboard, 4 on Market). Opening
   `/docs/prototypes/idx-evidence-lab-user-journey.html` shows none. The README, Docker and compose all point people to `/`.
   See MKT-01 and CC-02. This is a bug, not intended behavior.
2. **Settings shows a fake account** ("Rasya A • sesi lokal simulasi", a "Keluar" button and a logged-out screen) while the
   same screen says there is no authentication. See EVD-04.
3. **Mixed language.** Navigation groups and controls are English ("Workspace", "Research", "Market", "Evidence", "Back",
   "Forward", "Top 5 · You Must Know in 10 Minutes") while content is Indonesian. The GSM should fix one voice. See CC-05.
4. **Duplicate icon.** "Screener" and "Riset emiten" both use the same magnifier glyph in the sidebar. See CC-04.
5. **Empty states are plain.** Watchlist, Studies canvas and Riset emiten start empty; the copy is good but there is no
   guided first action beyond a button. See RSC-03, ANA-01.
6. **Dense, minified-style UI code** (13 JS chunks, shared global state) means design changes are risky until screens are
   rebuilt component by component. Not a user-facing finding, but it shapes the order in the GSM roadmap.
