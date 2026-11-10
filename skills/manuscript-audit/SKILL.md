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
| 1 | Clean compile | `compiler` | No errors, no undefined refs or citations |
| 2 | Bibliography integrity | `alex` | No fabricated, retracted or mismatched entries |
| 3 | Attribution gaps | `argus` | No uncredited methods or web-only sources |
| 4 | Math correctness | `turing`, then `gauss` | Symbolic and numerical claims verified |
| 5 | Theorem and proof completeness | `euclid` | No orphan theorems, all appendix labels resolve |
| 6 | Adversarial review | `popper` | Assumptions, baselines, failure modes documented |
| 7 | Figures | `da-vinci` | Vector plots, 300+ DPI rasters, subfigure parity, colorblind-safe |
| 8 | Reproducibility | `bacon` | Seeds, error bars, compute, blind-safe links |
| 9 | Title and abstract | `shannon` | Keyphrase in first 65 chars, 150-220 word abstract |
| 10 | Prose humanization | `human` | No AI tropes, em dashes, LaTeX clone patterns |
| 11 | Page budget | `layout` | Within limit, no negative `\vspace` hacks |
| 12 | Packaging | `submission` | Cover letter, highlights, title page, anonymous code |

## Rules
- Stages 1-3 are blocking: do not proceed on a broken build or unverified bibliography.
- Stages 4-8 may run in parallel via subagents when independent.
- Run `human` (10) and `layout` (11) late: earlier fixes change the text.
- Re-run `compiler` after any stage that edited source.
- Skip stages that do not apply (for example `euclid` with no theorems) and say so.
- Never invent citations to resolve a finding; report it instead.

## Output
One report with:
1. Pass/fail table for all 12 stages.
2. Findings grouped as Blocking, Should fix, Optional, each with file:line.
3. Edits made versus edits recommended.
4. Remaining steps before submission.
