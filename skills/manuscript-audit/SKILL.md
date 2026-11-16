---
name: manuscript-audit
description: End-to-end pre-submission pipeline for an academic manuscript. Use when the user asks to "audit", "check", "review", or "get ready to submit" a whole paper, or is unsure which SciFi skill to run. Orchestrates compile, citation, attribution, prose, math, theory, figure, reproducibility, layout and submission checks in a fixed order and returns one prioritized report.
---

# Manuscript Audit: Full Pre-Submission Pipeline

This skill does not implement checks itself. It sequences the specialist skills, collects their findings, and reports once. Run stages in order, because later stages assume earlier ones passed.

## Inputs
- Path to the main `.tex` file (and `.bib`).
- Target venue and review mode (single or double-blind). Ask if unknown.

## Pipeline

| # | Stage | Skill | Gate (stop and fix if failing) |
|---|-------|-------|--------------------------------|
| 1 | Clean compile | `compiler` | No errors, no undefined refs or citations; report compiler info |
| 2 | Bibliography integrity | `alex` | No fabricated, retracted or mismatched entries |
| 3 | Attribution gaps | `argus` | No uncredited methods or web-only sources |
| 4 | Math correctness | `turing`, then `gauss` | Symbolic and numerical claims verified |
| 5 | Theorem and proof completeness | `euclid` | No orphan theorems, all appendix labels resolve |
| 6 | Adversarial review | `popper` | Assumptions, baselines, failure modes documented |
| 7 | Figures & visual PDF check | `da-vinci` | Vector plots, 300+ DPI rasters, subfigure parity, colorblind-safe, **visual PNG inspection via `read_file`** |
| 8 | Reproducibility | `bacon` | Seeds, error bars, compute, blind-safe links |
| 9 | Title and abstract | `shannon` | Keyphrase in first 65 chars, 150-220 word abstract |
| 10 | Prose stylometry & craft | `orwell` | No AI tropes, em dashes, LaTeX clone patterns |
| 11 | Page budget | `layout` | Within limit, no negative `\vspace` hacks |
| 12 | Packaging | `submission` | Cover letter, highlights, title page, anonymous code |

## Rules
- Stages 1-3 are blocking: do not proceed on a broken build or unverified bibliography.
- Stages 4-8 may run in parallel via subagents when independent.
- Run `orwell` (10) and `layout` (11) late: earlier fixes change the text.
- Re-run `compiler` after any stage that edited source.
- Skip stages that do not apply (for example `euclid` with no theorems, `gauss` when no raw numeric/CSV/JSON simulation data is provided, or `submission` on an audit-only request) and mark them `SKIPPED` with the reason rather than `PENDING` or `WARN`.
- Stage 4 (`turing`, `gauss`): `sf math` and `sf stats` require subcommands (`sf math notation <tex>`, `sf math derivative|step|units|shapes|limits|convexity`, `sf stats audit <csv|json|values>`, `sf stats curve ...`); do not pass a `.tex` path to `sf stats audit`.
- Never invent citations to resolve a finding; report it instead.

## Forensic Cross-Checking Protocol (Reviewer Trajectory)
To catch rejection-level defects that single-stage regex or isolated section checks miss, cross-check across artifacts:
1. **Main-Text ↔ Appendix Joint Read:** Always read appendices alongside the main body to catch buried assumption caveats or analytical constants that contradict main-body claims.
2. **Proof ↔ Code Separation (`src/` / `scripts/`):** When project simulation or experimental code is present in the workspace, inspect the implementation to verify whether the executed algorithm matches the theorem's assumptions, solver class (e.g., generic quasi-Newton/SQP vs. specialized conic solver, approximate surrogate vs. exact oracle), and dominant end-to-end complexity.
3. **Cross-Section Constant & Plot Legend Reconciliation:** Cross-check numerical constants derived in theorems/appendices (e.g., analytical bound constants $B$) against curve-fit equations printed inside figure legends or captions.
4. **Substantive vs. Cosmetic Triage ("Fix Theory Before Polishing Prose"):** In the final report, strictly separate **Fatal / Substantive Rejection Risks** (theorem-to-algorithm certification gaps, analytical-bound vs. empirical-fit contradictions, unestablished novelty) from **Fixable Framing / Cosmetic Revisions**, and advise halting prose/figure polish until substantive gaps are resolved.

## Output
One report with:
1. Pass/fail table for all 12 stages.
2. Findings grouped as Blocking, Should fix, Optional, each with file:line.
3. Edits made versus edits recommended.
4. Remaining steps before submission.
