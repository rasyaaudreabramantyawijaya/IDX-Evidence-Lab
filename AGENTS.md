# Hackathon Sectors Workspace Rules

## Canonical Knowledge Base

This workspace uses the following file as its canonical project knowledge base and operating policy:

`/Users/rasyaaudreabramantyawijaya/Documents/quant-lab/AGENTS.md`

Before performing any task in this workspace, read and apply that canonical `AGENTS.md`. Its governance, HOTL approval gates, quant-research-lab routing, Sectors Hackathon 2026 Track 03 priorities, TA/diffusion preservation rules, evaluation standards, and model boundaries apply here in full.

## Workspace Boundary

- The active implementation workspace is `/Users/rasyaaudreabramantyawijaya/Documents/Hackathon_Sectors`.
- Put all Hackathon Sectors source code, notebooks, experiments, reports, tests, and generated artifacts in this workspace unless the user explicitly requests another location.
- Use `/Users/rasyaaudreabramantyawijaya/Documents/quant-lab` as the canonical knowledge, governance, and reference project; do not silently move Hackathon work into it.
- Do not overwrite or modify the canonical `quant-lab/AGENTS.md` when working on Hackathon files unless the user explicitly asks for that change.

## Skills and Instructions

- Use the globally available `quant-research-lab` skill for quant research, market intelligence, data analysis, modeling, validation, and related mathematical work.
- If a task changes shared skills, governance, or reusable knowledge, clearly identify whether the change belongs in this workspace or in the canonical `quant-lab` project before editing it.
- Preserve the full Sectors Hackathon 2026 Track 03 (Market Intelligence) priority and all additive TA/diffusion work described by the canonical knowledge base.

## Notebook-First Output Contract

Every prompting result that performs analysis, data work, modeling, market
intelligence, visualization, or experimentation MUST be delivered as a
visible, executable notebook compatible with Google Colab or Kaggle Notebook.
The canonical deliverable is the notebook itself, not a generator script,
hidden runner, JSON-only report, opaque subprocess, or screenshot-only result.
Supporting Python modules are allowed for reusable implementation, but the
notebook must expose and execute the complete research path.

### Required notebook order

Use visible Markdown and code cells in this order unless the task has a clear,
documented reason to differ:

1. **Title, objective, and research question** — state the hypothesis, target,
   scope, expected output, and whether the task is supervised, unsupervised,
   generative, descriptive, or diagnostic.
2. **Imports and environment configuration** — import only required libraries,
   set display options, configure warnings, define a deterministic seed, and
   print Python/library versions when reproducibility matters.
3. **Runtime and data-source guard** — detect Colab/Kaggle/local runtime,
   declare required attachments or input paths, fail clearly when data is
   missing, and never depend on an unspoken absolute local path.
4. **Data loading and one-by-one inspection** — load each source explicitly,
   print its path/identifier, shape, date range, ticker count, sample rows, and
   provenance before combining sources.
5. **Schema and data-quality audit** — inspect dtypes, duplicates, missingness,
   timestamp order/timezone, outliers, corporate actions, survivorship, and
   source conflicts; show a compact audit table.
6. **EDA** — present distributions, summary statistics, time-series plots,
   volume/liquidity views, correlations, class balance, and regime views that
   answer the research question. Explain each chart in Markdown.
7. **Preprocessing and feature engineering** — document cleaning, joins,
   resampling, labels, technical features, and availability timestamps; show
   before/after shapes and retain leakage checks.
8. **Split and normalization** — define train/validation/test or walk-forward
   boundaries before fitting transformations; fit scalers and selectors on
   train only; print the boundaries and guard results.
9. **Baseline** — run a naive/statistical/simple ML baseline before advanced
   models and explain what it establishes.
10. **Model definition** — explain inputs, target, architecture/algorithm,
    loss, hyperparameters, and alternatives not used; then display the actual
    model summary or parameter table.
11. **Training** — show the training configuration, seed, epoch/batch progress,
    train/validation curves, checkpoints, and any early-stopping rule. Ask for
    approval before GPU-heavy or long runs.
12. **Validation and diagnostics** — evaluate only with timestamp-safe data;
    show per-horizon, per-ticker, and regime/liquidity slices where relevant,
    uncertainty/coverage for probabilistic models, and failure examples.
13. **Final result** — show measured tables and legible figures with units,
    dates, horizon labels, cutoff markers, and explicit `final`, `partial`,
    `provisional`, or `blocked` status. Never present illustrative values as
    measured output.
14. **Decision or paper-replay section, if in scope** — keep model output
    separate from any Buy/Sell/Hold decision head and from paper-trading
    replay; show assumptions, costs, PnL/journal, and limitations.
15. **Conclusion and limitations** — answer the research question, compare
    against the baseline, state uncertainty and failure modes, list what the
    evidence does not prove, and identify the next approved experiment.
16. **Reproducibility manifest** — record data identifiers/snapshots, code
    version, package versions, seeds, split dates, parameters, output paths,
    checksums when available, and a final artifact/guard checklist.

### Notebook acceptance rules

- Each major section MUST have a Markdown explanation followed by executable
  code and a visible output; do not hide essential work in a separate runner.
- The notebook MUST run top-to-bottom in a fresh Colab or Kaggle session, or
  stop with an explicit, actionable attachment/setup message.
- Kaggle notebooks MUST state the exact Dataset/attachment slug or artifact
  requirement. Colab notebooks MUST state the upload, Drive, or URL requirement.
- Do not silently fall back from Kaggle/Colab paths to a developer's local
  machine. Use platform-aware configuration cells instead.
- Outputs MUST distinguish research/model decisions from financial advice or
  live execution. No broker credentials, live orders, or deployment promotion
  without explicit HOTL approval.
- Before delivery, inspect notebook cell order, execute a fresh smoke test,
  verify that generated source and visible outputs agree, and report missing,
  stale, partial-horizon, provisional, or development-only artifacts.
- If the user asks for “hasil prompting”, return the notebook path/link plus a
  short cell-by-cell map explaining what each section does; do not return only
  prose, a code generator, or a JSON summary.

## Chat and VS Code Context

The Codex chat titled `Fokus PKT & Quantitative` may be used for prompting and continuity. The open VS Code workspace remains the execution context: file edits and commands for this project must target this `Hackathon_Sectors` directory.
