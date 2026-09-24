# IDX Evidence Lab

**Sectors Hackathon Indonesia 2026 — Track 03: Market Intelligence**
**Status per 25 September 2026:** source snapshots and offline building blocks exist; the complete dashboard, integrated feature engine, chatbot, and validated signals are **not yet production-ready**.

IDX Evidence Lab is designed to help Indonesian-market users move from “I heard this stock may rise / be acquired” to a traceable review of the available evidence: what supports the thesis, what contradicts it, what is missing, and what the data cannot establish. It is a research and decision-support concept—not an automated trading system, investment recommendation, identification of a beneficial owner, or legal opinion.

> **Important status distinction:** the product specification and interactive HTML are design/prototype artifacts. The Python package currently implements offline schemas, mocks, local lexical search, query planning, source-policy checks, evidence-state rules, and a preliminary acquisition checklist. It does not yet calculate or serve every dashboard feature described below. “Data exists” also does not mean “feature validated.”

## Team

- Rasya Audrea Bramantya Wijaya
- Fardan
- Thariq
- Seva

Roles can be assigned by the team; this README does not infer individual ownership of code or research.

## Why build this?

The product addresses a practical market-research problem: issuer reports, prices, broker/foreign-flow observations, disclosures, news, and legal rules are difficult to compare in one auditable workflow. A raw-data dashboard or AI summary alone is not enough. The product is intended to derive comparable measures and show their provenance, counter-evidence, uncertainty, historical outcomes, and data gaps.

The main workflow is:

```text
Approved Sectors.app snapshots + private local legal documents
  -> validate symbols, timestamps, fields, coverage, and provenance
  -> normalize and construct point-in-time features
  -> calculate transparent peer scores, flow context, and risk states
  -> compare against historical analogs and simple baselines
  -> expose uncertainty, contradictions, falsifiers, and missing evidence
  -> present an issuer dossier, screener, and searchable evidence trail
```

## Product surfaces and use cases

These are the intended surfaces from the product specification and mockup. Only the offline components listed later in this README are implemented in the current Python package.

| Surface / feature | What a user does | Why it is useful | Intended evidence / output |
|---|---|---|---|
| **Dashboard** | Starts with current market context and items needing attention | Answers “what changed, and what should I inspect?” without duplicating the market page | Market regime snapshot, evidence screener, unusual-flow watch, evidence health, watchlist changes, recent outcomes, data-quality state, relevant Sectors news when available |
| **Market** | Reviews IHSG, breadth, sectors, flow, and market events | Separates broad market conditions from a single-stock thesis | Index and sector context, breadth, volatility/liquidity context, timestamps and missingness |
| **Evidence Screener** | Filters issuers by evidence state, flow, financial fragility, readiness, and sample coverage | Narrows a large universe using explicit criteria rather than a narrative ranking | Ticker, peer group, score/state, sample size, completeness, horizon, and update time |
| **Issuer dossier** | Opens one ticker and reviews its financials, price, flow, events, legal checklist, and provenance | Puts the strongest supporting and opposing facts together for one issuer | Thesis, counter-thesis, measured evidence, invalidation conditions, analogs, limitations, sources |
| **Sector-relative Quality–Valuation–Risk (QVR)** | Compares an issuer with suitable peers | Avoids comparing structurally different businesses using one universal metric scale | Sector/subsector percentiles or robust standardized metrics, with applicability and missing-data handling |
| **Financial Fragility Monitor** | Inspects deterioration in cash flow, leverage, liquidity, profitability, and asset quality | Surfaces pressure on capital preservation; does not predict failure with certainty | Metric changes, peer context, period and report availability timestamps, fragility state, counter-evidence |
| **Flow Context / Broker Flow** | Examines broker-channel activity, persistence, concentration, foreign flow, turnover, and price response | Adds transaction-channel context to price and fundamentals | Net-flow proxies, buyer/seller concentration, persistence, flow-price divergence, data coverage |
| **Event & Governance Risk** | Reviews filings, corporate actions, ownership disclosures, suspensions, and catalysts | Tests whether a market narrative has a dated, documentable event behind it | Event type, event/publication time, source record, linked evidence and unresolved questions |
| **Evidence Dossier & Ledger** | Saves or exports a claim with its inputs and outcome | Lets the team audit how a conclusion was formed and record claims that failed | Snapshot IDs, formula/version, citations, supporting and contradicting records, confidence/evidence state, outcomes |
| **Historical Analogs / Regime-Conditioned Outcomes** | Compares similar past contexts across market, sector, volatility, and liquidity states | Tests whether a pattern was historically distinguishable from a baseline | Sample count, forward-return distribution, hit rate, interval, baseline delta, false alarms and failures |
| **Anomaly & Divergence** | Looks for outlying volume/turnover, flow-price mismatch, valuation-price mismatch, or peer outliers | Helps direct review to unusual observations, not label them as manipulation | Transparent feature contributions, peer distribution, anomaly score/state, alternative explanations |
| **Suspension / ARB / Liquidity Risk** | Reviews known suspension history and liquidity/downside proxies | Helps avoid interpreting thin or disrupted trading as a robust signal | Verified event records where available; otherwise proxy or `INSUFFICIENT_EVIDENCE`. ARB is not assumed to be an API field |
| **Portfolio Impact View** | Adds user-owned holdings and tests concentration, drawdown, covariance, and liquidity scenarios | Shows how issuer risk may interact with an existing portfolio | Exposure and scenario views; no automated rebalancing or order placement |
| **News — “Top 5 You Must Know in 15 Minutes”** | Gets a short, ranked briefing and opens each underlying item | Helps users prioritize material items instead of scrolling an unranked feed | Sectors-only news, event/entity relevance, recency, evidence links and “why it matters”; no live news feed is currently connected |
| **Unified Search / AI Analyst** | Searches tickers, metrics, product pages, evidence, reports, and local legal references in Indonesian | Gives one entry point to product navigation and evidence retrieval | Local retrieval results, a query plan, citations and abstention when evidence is missing; OpenRouter is inference only |
| **Acquisition / Corporate-Action Readiness** | Checks whether the available documents address transaction, ownership, approvals, disclosure, licensing, and liabilities | Replaces a simplistic “will it be acquired?” prediction with an evidence checklist and explicit blockers | `GREEN` / `AMBER` / `RED` / `UNKNOWN` preliminary readiness with missing documents, relevant rule references, and legal disclaimer |
| **Data Library** | Inspects approved snapshots, data dictionary, freshness, provenance, and private-document metadata | Helps users understand what evidence is actually available | Snapshot registry, source class, hash, retrieval time, coverage, document access class and quality state |

### Intended user value

- **Beginner:** understand a ticker’s evidence and limitations without needing to interpret every raw field.
- **Active retail investor:** compare a thesis with counter-evidence, flow context, risk, and material events.
- **Analyst/researcher:** inspect provenance, formula versions, peer definitions, historical analogs, missingness, and failed signals.

User modes and community evidence cards are later-stage ideas (P2), not delivered capabilities.

## Data policy and where data comes from

### Permitted sources

1. **Market, issuer, broker, price, fundamentals, filings, corporate actions, and news:** Sectors.app only, through approved Sectors API/MCP snapshots. If Sectors does not provide a required field, show it as missing/unavailable; do not substitute Yahoo Finance, a web search, another market API, or another news API.
2. **Indonesian business/capital-market regulations:** files manually collected and curated by the team and stored in the private local `Business & Corporate Law/` corpus. They are not downloaded from an API by this application. The folder is a private research reference, not proof that the legal corpus is exhaustive or current.
3. **OpenRouter:** optional language inference only—for intent parsing, constrained query rewriting, and grounded summarization of retrieved evidence. It is not a source of market or legal facts. The current `MockOpenRouterAdapter` is offline and makes no OpenRouter request.
4. **User content:** private watchlists, holdings, notes, and studies, subject to access controls if/when those product features are implemented.

Never put API keys in notebooks, browser code, commits, screenshots, or logs. Keep credentials server-side and out of Git. Do not send an entire private law corpus to an LLM; if live inference is later approved, retrieve and send only the minimum relevant excerpt under an explicit privacy policy.

### Local data snapshot audit

The figures below describe files and logs currently in this workspace, not an assertion that all fields have been independently reconciled against the provider. The daily manifest is a local artifact and says its records are Sectors.app responses; retain the manifest and per-window metadata when using those files.

| Data | Planned/observed Sectors endpoint | What is in the workspace now | Readiness |
|---|---|---|---|
| LQ45 universe | `GET /v2/companies/` with an LQ45 `where` filter | One saved universe response with 45 symbols and retrieval metadata/hash | **FOUND** — snapshot and metadata are present |
| Issuer/company report | `GET /v2/company/report/{symbol}/` | 45 cached report objects, but only 35 symbols overlap the current 45-name universe; 10 current constituents lack a matching report and 10 report symbols are from the older universe. Cache manifest marks endpoint provenance partial; usage history contains 53 report requests and needs reconciliation | **PARTIAL** — do not describe as complete for the current universe |
| Daily price/volume | `GET /v2/daily/{ticker}/?start=...&end=...` | Daily manifest lists 45 tickers, 585 90-day windows, all HTTP 200, from 2023-09-25 to 2026-09-24. Forty-four tickers have 712 observations; AADI has 424 observations from 2024-12-05. Earlier usage logs contain fewer calls than the current manifest, so reconcile acquisition ledger before treating provenance as fully audited | **DATA PRESENT, LEDGER RECONCILIATION NEEDED** |
| Foreign flow | `GET /v2/foreign-flow/{symbol}/` | Historical usage logs show requests for 8 symbols (40 calls); no corresponding raw foreign-flow dataset was found in the current `data/raw/sectors` snapshot | **PARTIAL / RAW ARTIFACT MISSING** |
| Broker flow | Actual cached format corresponds to broker-wide activity, e.g. `GET /v2/broker-activity/{broker}/`; planned per-issuer endpoint is `GET /v2/broker-summary/{symbol}/` | Cache manifest has 228 broker-flow snapshots plus 6 cohort snapshots, across four broker codes (AK, XL, YP, ZP). Usage logs show 229 calls. Endpoint is broker-oriented, not the planned per-symbol summary; cache payloads do not always identify the original endpoint | **ALTERNATIVE DATA PRESENT, PROVENANCE PARTIAL** — supports only observed broker channels, not all brokers or beneficial-owner identity |
| IHSG benchmark | `GET /v2/index-daily/ihsg/` | Usage logs show 5 calls; no corresponding benchmark raw artifact was found in the current data directory | **REQUEST LOGGED, USABLE SNAPSHOT NOT FOUND** |
| Filings / disclosures | Planned `GET /v2/filings/` (exact filters/schema must be checked against approved current docs) | No request in the checked usage logs and no local raw filing dataset found | **MISSING** |
| Sectors news | Planned `GET /v1/news/` (exact filters/schema must be checked against approved current docs) | No request in the checked usage logs and no local raw news dataset found | **MISSING** |
| Corporate actions and suspensions | Sectors endpoint/schema must be established from the approved Sectors reference; do not infer endpoint or field availability | No separately reconciled local corporate-action/suspension dataset found; an issuer report may contain limited context but is not a substitute for a dedicated event history | **MISSING / UNVERIFIED** |
| Legal and business rules | No API; local private files only | 49 local PDF files across folders for capital markets, takeovers, material/affiliate transactions, issuer disclosures/ownership, RUPS, company shares/corporate actions, and BEI/KSEI/KPEI rules; repeated copies may exist | **LOCAL FILES FOUND; applicability, completeness, supersession and ingestion are not validated** |

The daily manifest's 45-symbol set matches the stored current LQ45 snapshot. However, this is a current snapshot, not a point-in-time history of every LQ45 constituent and rebalance throughout the full three-year window. Survivorship bias therefore remains a research risk.


## Feature engineering and analytical workflow

Feature engineering turns approved observations into consistent, timestamp-aware fields. It is not simply asking an LLM to invent a score.

### 1. Ingest and preserve source records

- Save the original Sectors response as an immutable local snapshot.
- Attach provider, endpoint, retrieval time, HTTP status, request number/budget, SHA-256, and schema/source class.
- Keep raw inputs separate from normalized tables and derived metrics.
- Never overwrite a missing field with data from another provider.

### 2. Normalize and quality-check

- Normalize ticker aliases and date formats; verify ticker against the selected universe.
- Check duplicate rows, window overlaps, missing values, data types, outliers, price jumps, and date continuity.
- Keep event time (when something happened) separate from availability time (when it became knowable).
- Mark stale, partial, unverified, or missing records. A current LQ45 membership list must not be backfilled as the historical universe.

### 3. Construct candidate features

The specification proposes these families, subject to fields actually available from Sectors:

| Feature family | Example derived fields | Why |
|---|---|---|
| Price and liquidity | 1D/5D/20D returns, realized volatility, drawdown, volume/turnover shocks, rolling liquidity | Describe movement and tradability; not stand-alone forecasts |
| Sector-relative fundamentals | growth, margins, profitability, cash conversion, leverage, valuation ratios; sector/subsector percentile or robust z-score | Compare like businesses and show metric applicability |
| Fragility | deterioration in leverage, liquidity, cash-flow coverage, profitability, and asset quality | Highlight balance-sheet and earnings vulnerability |
| Broker/foreign flow context | net value, flow-to-turnover, cumulative flow, persistence/reversal, concentration, price response | Characterize observed transaction channels; not investor identity or intent |
| Events and governance | dated filing/corporate-action/suspension records, report-period changes, ownership-disclosure evidence | Tie claims to dated records and expose missing coverage |
| Historical outcome | forward return, excess vs baseline, MAE/MFE, hit rate, confidence intervals, sample size | Test historical behavior and uncertainty rather than promise future outcomes |
| Legal readiness | document metadata, applicable rule/citation, required-document status, approval/disclosure/license checklist | Track evidence completeness; never give legal clearance |

Financial ratio families must be sector-aware (for example, bank metrics are not blindly scored with industrial-company leverage metrics). Altman/Piotroski are optional only where their assumptions fit. “Five years of financial history” is not hard-coded as a universal legal rule; each requested period must have a specific documented basis and be reviewed.

### 4. Form a transparent evidence state

The offline `classify_evidence` function currently applies simple rules using sample size, completeness, supporting/contradicting counts, invalidation, and a minimum sample. It can return `SUPPORTED`, `MIXED`, `WEAK`, `INSUFFICIENT`, or `INVALIDATED`. These rules are implemented and unit-tested as a software component, but thresholds have not been empirically calibrated for investment outcomes. Evidence state is not the same as bullish/bearish direction or legal readiness.

The preliminary acquisition checker returns `GREEN`, `AMBER`, or `RED` from the presence of checklist evidence. It is a scaffold: it does **not** determine that a transaction is legally permitted, predict an acquisition, or replace counsel. Missing information should lead to `UNKNOWN`/insufficient evidence in the product rather than a false clearance.

### 5. Validate before presenting a signal

- Establish simple references first: buy-and-hold/equal-weight, simple trend or flow rules, and random/no-signal checks where relevant.
- Use point-in-time splits, walk-forward validation, purging/embargo for overlapping forward labels, and realistic cost assumptions.
- Report sample size, uncertainty, coverage, false alarms, failures, and benchmark deltas by regime, sector, and liquidity.
- Keep development folds separate from a truly untouched confirmation period. A model is not validated because it fits or because a chart looks persuasive.

Search and chatbot design

The offline search prototype tokenizes local text, resolves a small issuer dictionary, ranks title/body lexical matches, and constructs deterministic intents such as `NAVIGATE`, `FILTER_SCREEN`, `FIND_RULE`, and `ASSESS_EVENT`. The current demo uses three mock issuers only. The local index is not yet a production index of every report, news item, or legal document.

Planned query flow:

```text
Query -> ticker/entity resolution -> structured intent plan
  -> access/source policy -> local retrieval and approved deterministic tools
  -> optional OpenRouter inference on the minimum retrieved context
  -> answer + source citations + contradictions + evidence state + abstention

Legal and acquisition evidence

The local `Business & Corporate Law/` folder contains 49 manually collected PDF files (some may be duplicate copies), grouped into:

- market/securities offering and market conduct;
- takeover of public companies;
- material, affiliated, and conflict-of-interest transactions;
- issuer reporting and ownership disclosures;
- RUPS/shareholder meetings;
- company shares and corporate actions;
- BEI, KSEI, and KPEI rules.
