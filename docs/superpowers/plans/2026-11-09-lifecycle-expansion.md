# SciFi Academic Lifecycle Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 5 missing lifecycle tools across Pre-Submission, Review, Rebuttal, and Camera-Ready publishing phases: `scifi_audit_figures`, `scifi_trim_budget`, `scifi_audit_proofs`, `scifi_audit_reproducibility`, and the Rebuttal Suite (`scifi_format_rebuttal` / `scifi_diff_manuscript`).

**Architecture:** 
- Modular domain engines under `scifi/figures/`, `scifi/layout/`, `scifi/proofs/`, `scifi/reproducibility/`, and `scifi/rebuttal/`.
- Zero mandatory external C-extensions: pure Python image header parsing for PNG/JPEG dimensions/DPI + `pypdf` for vector PDF figures; regex & AST LaTeX parsing; ISO-4 / IEEE abbreviation dictionaries for BibTeX shrinking.
- Unified FastMCP tool registrations in `scifi/server.py` and CLI subcommands in `scifi/cli.py` (`sf figures`, `sf trim`, `sf proofs`, `sf repro`, `sf rebuttal`).
- Corresponding skills in `skills/` (`da-vinci`, `layout`, `euclid`, `bacon`, `rebuttal`).

**Tech Stack:** Python 3.12+, `pypdf`, `bibtexparser`, `numpy`, `scipy`, `pytest`, standard library (`re`, `json`, `argparse`, `dataclasses`, `pathlib`).

## Global Constraints

- Python >= 3.12 compatibility.
- Zero mandatory external API keys or heavy binary dependencies.
- Zero tolerance for synthetic AI tropes or unescaped LaTeX errors.
- Fast execution (< 500ms per file audit offline).
- Full compatibility with existing multi-file project resolver (`scifi.latex.project.resolve_latex_project`).

---

### Task 1: Phase 1 — Figure, Plot & Visual Accessibility Auditor (`scifi_audit_figures`)

**Files:**
- Create: `scifi/figures/__init__.py`
- Create: `scifi/figures/models.py`
- Create: `scifi/figures/auditor.py`
- Create: `skills/da-vinci/SKILL.md`
- Create: `tests/test_figures.py`
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`

- [ ] **Step 1: Write failing test in `tests/test_figures.py`**
  - Test raster vs vector detection (flags .png/.jpg line plots, accepts .pdf/.eps).
  - Test DPI calculation from image headers and textwidth scaling.
  - Test subfigure parity detection: unreferenced subfigure (c) when caption has (a), (b), (c).
  - Test colorblind palette check heuristic (flags red-green only contrast).
- [ ] **Step 2: Implement `scifi/figures/models.py` and `scifi/figures/auditor.py`**
  - Implement pure Python PNG/JPEG header reader (dimensions, pHYs DPI chunk, JFIF density) + PDF box dimensions.
  - Implement LaTeX figure/subfigure reference parser.
  - Implement colorblind safety audit heuristic.
- [ ] **Step 3: Wire into `scifi/cli.py` (`sf figures`) and `scifi/server.py` (`@mcp.tool() scifi_audit_figures`)**
- [ ] **Step 4: Create skill `skills/da-vinci/SKILL.md`**
- [ ] **Step 5: Run tests and verify 100% pass**

---

### Task 2: Phase 1 — Page Budget & Micro-Trimming Assistant (`scifi_trim_budget`)

**Files:**
- Create: `scifi/layout/__init__.py`
- Create: `scifi/layout/models.py`
- Create: `scifi/layout/abbreviations.py`
- Create: `scifi/layout/trim.py`
- Create: `skills/layout/SKILL.md`
- Create: `tests/test_trim.py`
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`

- [ ] **Step 1: Write failing test in `tests/test_trim.py`**
  - Test widow/orphan paragraph slack detection (identifies paragraphs ending with 1-3 words).
  - Test BibTeX venue abbreviation (replaces verbose journal/conference titles with ISO-4/IEEE standard abbreviations).
  - Test float density suggestions (`\small` in tabular, tabcolsep adjustment recommendations).
- [ ] **Step 2: Implement `abbreviations.py` and `trim.py`**
  - Build comprehensive dictionary of conference & journal abbreviations (IEEE, ACM, CVPR, NeurIPS, ICML, Nature, Science, etc.).
  - Implement LaTeX paragraph tokenization & line slack estimation.
  - Implement `.bib` abbreviation rewrite function.
- [ ] **Step 3: Wire into `scifi/cli.py` (`sf trim`) and `scifi/server.py` (`@mcp.tool() scifi_trim_budget`)**
- [ ] **Step 4: Create skill `skills/layout/SKILL.md`**
- [ ] **Step 5: Run tests and verify 100% pass**

---

### Task 3: Phase 2 — Theorem–Proof & Appendix Completeness Sentinel (`scifi_audit_proofs`)

**Files:**
- Create: `scifi/proofs/__init__.py`
- Create: `scifi/proofs/models.py`
- Create: `scifi/proofs/auditor.py`
- Create: `skills/euclid/SKILL.md`
- Create: `tests/test_proofs.py`
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`

- [ ] **Step 1: Write failing test in `tests/test_proofs.py`**
  - Test detection of orphan theorems (theorem declared without proof or appendix pointer).
  - Test appendix proof pointer verification (ensures `\ref{app:proof_1}` resolves to valid label).
  - Test multi-file LaTeX project proof resolution (theorem in `main.tex`, proof in `sections/appendix.tex`).
- [ ] **Step 2: Implement `scifi/proofs/auditor.py`**
  - Extract all mathematical environments (`theorem`, `lemma`, `proposition`, `corollary`, `definition`).
  - Scan for inline proofs vs external appendix references.
  - Cross-check against label targets across multi-file documents via `resolve_latex_project`.
- [ ] **Step 3: Wire into `scifi/cli.py` (`sf proofs`) and `scifi/server.py` (`@mcp.tool() scifi_audit_proofs`)**
- [ ] **Step 4: Create skill `skills/euclid/SKILL.md`**
- [ ] **Step 5: Run tests and verify 100% pass**

---

### Task 4: Phase 2 — Conference Reproducibility & Open-Science Checklist (`scifi_audit_reproducibility`)

**Files:**
- Create: `scifi/reproducibility/__init__.py`
- Create: `scifi/reproducibility/models.py`
- Create: `scifi/reproducibility/checklists.py`
- Create: `scifi/reproducibility/auditor.py`
- Create: `skills/bacon/SKILL.md`
- Create: `tests/test_reproducibility.py`
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`

- [ ] **Step 1: Write failing test in `tests/test_reproducibility.py`**
  - Test seed & trial detection (identifies missing random seeds and small trial counts).
  - Test compute resource audit (flags missing GPU/hardware specifications and execution duration).
  - Test hyperparameter specification audit (verifies hyperparameter search table / appendix section).
  - Test double-blind repository sanitization (flags personal GitHub URLs under double-blind mode).
- [ ] **Step 2: Implement `checklists.py` and `auditor.py`**
  - Curate official NeurIPS 2024 / ICML / IEEE reproducibility rubrics.
  - Implement regex & heuristic analyzers for compute specs, seeds, error bars, and repo anonymization.
- [ ] **Step 3: Wire into `scifi/cli.py` (`sf repro`) and `scifi/server.py` (`@mcp.tool() scifi_audit_reproducibility`)**
- [ ] **Step 4: Create skill `skills/bacon/SKILL.md`**
- [ ] **Step 5: Run tests and verify 100% pass**

---

### Task 5: Phase 3 — Author Rebuttal & Point-by-Point Revision Suite (`scifi_diff_manuscript` / `scifi_format_rebuttal`)

**Files:**
- Create: `scifi/rebuttal/__init__.py`
- Create: `scifi/rebuttal/models.py`
- Create: `scifi/rebuttal/formatter.py`
- Create: `scifi/rebuttal/differ.py`
- Create: `skills/rebuttal/SKILL.md`
- Create: `tests/test_rebuttal.py`
- Modify: `scifi/cli.py`
- Modify: `scifi/server.py`

- [ ] **Step 1: Write failing test in `tests/test_rebuttal.py`**
  - Test review parsing & structured 4-beat rebuttal scaffold generation.
  - Test LaTeX manuscript diff ledger (section-by-section line & equation change tracking).
  - Test latexdiff invocation wrapper with graceful fallback if `latexdiff` executable is not installed.
- [ ] **Step 2: Implement `formatter.py` and `differ.py`**
  - Parse reviews (OpenReview, IEEE, markdown, plain text) into discrete Reviewer / Question items.
  - Scaffold disciplined academic rebuttal markdown with professional tone hedging.
  - Implement AST/line-level LaTeX diff analyzer + optional `latexdiff` system CLI wrapper.
- [ ] **Step 3: Wire into `scifi/cli.py` (`sf rebuttal format` & `sf rebuttal diff`) and `scifi/server.py` (`scifi_format_rebuttal`, `scifi_diff_manuscript`)**
- [ ] **Step 4: Create skill `skills/rebuttal/SKILL.md`**
- [ ] **Step 5: Run tests and verify 100% pass**

---

### Task 6: Full Integration & Verification

**Files:**
- Modify: `scifi/doctor.py` (integrate new audits into end-to-end readiness check)
- Modify: `tests/test_doctor.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_server.py`
- Modify: `README.md`
- Modify: `rules/AGENTS.md` and `AGENTS.md`

- [ ] **Step 1: Update `scifi/doctor.py` to optionally run figures, proofs, and repro checks**
- [ ] **Step 2: Update `test_cli.py` and `test_server.py` to verify all new CLI subcommands and MCP tools**
- [ ] **Step 3: Update documentation and rules**
- [ ] **Step 4: Run full `uv run pytest` test suite and ensure 100% pass rate**
