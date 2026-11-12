# SciFi Code Quality, Maintainability & Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the SciFi toolkit into a publication-grade, fully maintainable, type-safe, well-documented scientific codebase by fixing 5 latent bugs, resolving all 57 Mypy errors, replacing 65 silent exception swallows with structured logging, modularizing 2 monolithic god files (`scifi/server.py` and `scifi/cli.py`), achieving 100% class docstring coverage, setting up a full MkDocs Material documentation site, and adding CI quality gates.

**Architecture:** Maintain strict 100% backward compatibility across all 46 FastMCP tools and all CLI subcommands. Adopt a domain-router architecture for FastMCP tools (`scifi/server/routers/`) and a modular handler architecture for CLI commands (`scifi/commands/`). Introduce structured logging in place of bare `except Exception: pass`, enforce static type cleanliness (`mypy` clean), and generate searchable developer and user documentation via MkDocs Material.

**Tech Stack:** Python 3.12+, FastMCP, SymPy, NumPy, SciPy, Pint, BibTeXParser, Pytest, Mypy, Ruff, MkDocs Material, `mkdocstrings`.

**Spec:** [`scifi-code-quality-and-maintainability-report.md`](file:///C:/Users/Betagors/.gemini/antigravity/brain/497ec503-a658-4eba-94d3-267df44ea466/scifi-code-quality-and-maintainability-report.md)

## Global Constraints
- Target Python version floor: Python ≥ 3.12 (`requires-python = ">=3.12"`).
- All 565 existing unit tests in `tests/` must continue to pass without regression.
- FastMCP tool signatures and return dictionaries must maintain exact schema compatibility for Antigravity, Claude, Cursor, and VS Code plugins.
- CLI command names, aliases (`sf`, `scifi`, `alex`, `argus`), options, and JSON outputs must remain strictly backward compatible.
- Zero network dependencies during offline test runs.

## Review Focus
1. `sf doctor --live` with `.bib` files: Must execute `audit_bib_file(..., search_missing=True)` without raising `TypeError` or swallowing errors.
2. `crawl_lineage()` on papers with empirical results: Must call `extract_reported_results()` instead of non-existent `extract_benchmarks()` so benchmark evidence is preserved.
3. `sf stats curve` and `sf math units / limits`: Must parse CLI flags and pass valid keyword arguments matching target function signatures.
4. FastMCP tool registration: `from scifi.server import mcp` must continue to expose all 46 registered tools with identical names and docstrings.
5. MkDocs build: `mkdocs build --strict` must compile clean without broken cross-references or missing docstrings.

---

### Task 1: Fix Latent Runtime Bugs & CLI Parameter Mismatches

**Files:**
- Modify: `scifi/doctor.py:110`
- Modify: `scifi/literature/lineage.py:174-179`
- Modify: `scifi/rebuttal/differ.py:112-116`
- Modify: `scifi/cli.py:220, 229, 248`
- Modify: `scifi/human.py:632`
- Test: `tests/test_bug_regressions.py`

**Interfaces:**
- Consumes: `audit_bib_file`, `BenchmarkExtractor.extract_reported_results`, `compile_latex`, `check_units`, `check_limits`, `verify_curve`.
- Produces: Correct parameter bindings and non-broken execution across `doctor`, `lineage`, `differ`, `human`, and `cli`.

- [ ] **Step 1: Write regression tests for all 5 latent bugs in `tests/test_bug_regressions.py`**
  ```python
  import pytest
  from unittest.mock import MagicMock
  from pathlib import Path
  from scifi.doctor import audit_paper_readiness
  from scifi.literature.lineage import LineageCrawler
  from scifi.rebuttal.differ import diff_manuscripts
  from scifi.stats.curve_fit import verify_curve
  from scifi.human import audit_latex_human_patterns
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run pytest tests/test_bug_regressions.py -v`
  Expected: FAIL on parameter mismatches and method attributes.

- [ ] **Step 3: Fix bugs in source files**
  - In `scifi/doctor.py:110`: change `search_missing_doi=True` to `search_missing=True`.
  - In `scifi/literature/lineage.py:175`: change `bm_extractor.extract_benchmarks(paper)` to `bm_extractor.extract_reported_results(paper)`.
  - In `scifi/rebuttal/differ.py:113`: change `compile_res.status == "SUCCESS"` to `compile_res.get("status") == "SUCCESS" and compile_res.get("pdf_path")`.
  - In `scifi/cli.py:220`: pass `check_mode=args.mode`.
  - In `scifi/cli.py:229`: pass `point=args.tends_to, claimed=args.expected, direction=args.direction`.
  - In `scifi/cli.py:248`: pass `var_name=getattr(args, "var_name", "x") or "x", sim_data_path=args.data_path, rtol=getattr(args, "tolerance", 1e-2)`.
  - In `scifi/human.py:632`: fix expression to `(not after_char or after_char[0].isupper() or after_char[0].islower())`.

- [ ] **Step 4: Run regression tests to verify they pass**
  Run: `uv run pytest tests/test_bug_regressions.py -v`
  Expected: PASS

- [ ] **Step 5: Run full test suite**
  Run: `uv run pytest tests/ -q`
  Expected: PASS (all tests green)

- [ ] **Step 6: Commit**
  ```bash
  git add scifi/doctor.py scifi/literature/lineage.py scifi/rebuttal/differ.py scifi/cli.py scifi/human.py tests/test_bug_regressions.py
  git commit -m "fix: resolve latent parameter, method, and typing bugs across core modules"
  ```

---

### Task 2: Structured Logging & Mypy Type Resolution

**Files:**
- Create: `scifi/logging.py`
- Modify: `scifi/server.py`
- Modify: `scifi/literature/zotero/reader.py`
- Modify: `scifi/submission/models.py`
- Modify: `scifi/submission/title_page.py`
- Modify: `scifi/submission/cover_letter.py`
- Modify: `scifi/submission/bundler.py`
- Modify: `scifi/literature/store.py`
- Modify: `scifi/literature/reporter.py`
- Modify: `scifi/literature/manifest.py`
- Modify: `scifi/literature/gaps.py`
- Modify: `scifi/math/linear_algebra.py`
- Modify: `scifi/latex/project.py`
- Test: `uv run mypy scifi`

**Interfaces:**
- Consumes: Standard `logging` module.
- Produces: Centralized logger `scifi.logging.get_logger(__name__)`, eliminating silent `except Exception: pass` and passing `mypy scifi` with 0 errors.

- [ ] **Step 1: Create `scifi/logging.py`**
  Implement `get_logger(name: str) -> logging.Logger` with sensible default level (`INFO` or configured via `SCIFI_DEBUG=1`).

- [ ] **Step 2: Replace high-risk `except Exception: pass` blocks**
  In `scifi/doctor.py`, `scifi/server.py`, `scifi/adapt.py`, `scifi/literature/store.py`, and `scifi/cli.py`, replace bare passes with `logger.debug("...", exc_info=True)` or narrow down to expected exception classes (`KeyError`, `FileNotFoundError`, `ValueError`).

- [ ] **Step 3: Fix undefined imports & type errors**
  - Add `from typing import Tuple` in `scifi/literature/zotero/reader.py` (or use builtin `tuple`).
  - Add `from typing import Optional` in `scifi/server.py` (or use `| None`).
  - Add `from collections.abc import Sequence` in `scifi/submission/models.py`.
  - Type `self.db_path: Path | str` in `LiteratureStore.__init__`.
  - Annotate empty collections (`parsed: list[AuthorInfo] = []`).
  - Fix variable redefinition in `scifi/latex/project.py:237`.
  - Fix type annotations in `submission/bundler.py`, `literature/manifest.py`, and `literature/reporter.py`.

- [ ] **Step 4: Run Mypy to verify zero errors**
  Run: `uvx mypy --ignore-missing-imports scifi`
  Expected: `Success: no issues found in 94 source files`

- [ ] **Step 5: Run full test suite**
  Run: `uv run pytest tests/ -q`
  Expected: PASS

- [ ] **Step 6: Commit**
  ```bash
  git add scifi/logging.py scifi/ tests/
  git commit -m "refactor: introduce structured logging and resolve all mypy typing errors"
  ```

---

### Task 3: Ruff Modernization & CI Quality Gates

**Files:**
- Modify: `pyproject.toml`
- Modify: `.github/workflows/ci.yml`
- Modify: All `.py` files in `scifi/` and `tests/` via ruff auto-fix

**Interfaces:**
- Consumes: `ruff`, `mypy`.
- Produces: Modern Python 3.12 syntax across all files, clean imports, and CI gate enforcement.

- [ ] **Step 1: Add dev dependencies to `pyproject.toml`**
  Add `"ruff>=0.9.0"`, `"mypy>=1.14.0"`, `"pytest-cov>=6.0.0"` under `[project.optional-dependencies] dev`.

- [ ] **Step 2: Run ruff auto-fixes**
  Run: `uv run ruff check --fix scifi tests`
  Run: `uv run ruff format scifi tests`

- [ ] **Step 3: Verify ruff passes cleanly**
  Run: `uv run ruff check scifi tests`
  Expected: 0 errors remaining.

- [ ] **Step 4: Add lint and type check steps to `.github/workflows/ci.yml`**
  ```yaml
      - name: Lint with ruff
        run: uv run ruff check scifi tests

      - name: Check code formatting with ruff
        run: uv run ruff format --check scifi tests

      - name: Type check with mypy
        run: uv run mypy --ignore-missing-imports scifi
  ```

- [ ] **Step 5: Run tests and verify CI commands locally**
  Run: `uv run pytest tests/ -q`
  Expected: PASS

- [ ] **Step 6: Commit**
  ```bash
  git add pyproject.toml .github/workflows/ci.yml scifi/ tests/
  git commit -m "style: apply ruff formatting and add lint/typecheck gates to CI"
  ```

---

### Task 4: Modularize FastMCP Server Tools (`scifi/server.py`)

**Files:**
- Create: `scifi/server/`
- Create: `scifi/server/__init__.py`
- Create: `scifi/server/app.py`
- Create: `scifi/server/routers/literature.py`
- Create: `scifi/server/routers/citations.py`
- Create: `scifi/server/routers/math.py`
- Create: `scifi/server/routers/manuscript.py`
- Create: `scifi/server/routers/submission.py`
- Create: `scifi/server/routers/zotero.py`
- Modify: `scifi/server.py` (re-export `mcp` and all 46 tools for full backward compatibility)
- Test: `tests/test_server.py`, `tests/literature/test_cli_ui_and_reprints.py`

**Interfaces:**
- Consumes: Domain logic from `scifi.literature`, `scifi.citation_verifier`, `scifi.math`, `scifi.human`, etc.
- Produces: Modularized FastMCP router modules, with `scifi.server:mcp` preserving all 46 registered tools.

- [ ] **Step 1: Write a test verifying all 46 tool registrations and signatures**
  Verify in `tests/test_server.py` that all 46 tool names are registered on `mcp` and their input models match expected arguments.

- [ ] **Step 2: Create `scifi/server/routers/` structure**
  Group the 46 tools by domain:
  - `citations.py`: `scifi_verify_citation`, `scifi_audit_bib`, `scifi_search_literature`, `scifi_audit_attribution`
  - `math.py`: `scifi_verify_derivative`, `scifi_verify_derivation_step`, `scifi_check_units`, `scifi_check_matrix_shapes`, `scifi_check_limits`, `scifi_check_convexity`, `scifi_check_notation`, `scifi_verify_curve`, `scifi_audit_statistics`
  - `manuscript.py`: `scifi_audit_manuscript`, `scifi_compile_latex`, `scifi_generate_latex_table`, `scifi_check_venue_compliance`, `scifi_audit_human`, `scifi_audit_figures`, `scifi_trim_budget`, `scifi_audit_proofs`, `scifi_audit_reproducibility`, `scifi_audit_claims`, `scifi_evaluate_title_abstract`, `scifi_format_rebuttal`, `scifi_diff_manuscript`
  - `literature.py`: `scifi_map_literature`, `scifi_query_sota_benchmarks`, `scifi_query_store`, `scifi_export_bibtex`, `scifi_list_projects`, `scifi_get_project_summary`, `scifi_draft_reprint_request`, `scifi_list_pending_reprints`, `scifi_ingest_paper_pdf`, `scifi_fetch_paper_pdf`, `scifi_extract_pdf_text`
  - `submission.py`: `scifi_generate_highlights`, `scifi_generate_title_page`, `scifi_generate_cover_letter`, `scifi_package_anonymous_code`, `scifi_prepare_submission_bundle`
  - `zotero.py`: `scifi_zotero_status`, `scifi_zotero_get_collection_papers`, `scifi_zotero_get_annotations`, `scifi_zotero_push_audit_note`

- [ ] **Step 3: Update `scifi/server.py` to import and re-export `mcp`**
  Ensure any code calling `from scifi.server import mcp` or running `sf server` continues to run seamlessly.

- [ ] **Step 4: Run test suite**
  Run: `uv run pytest tests/test_server.py tests/ -q`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add scifi/server/ scifi/server.py tests/test_server.py
  git commit -m "refactor: modularize FastMCP server tools into domain routers"
  ```

---

### Task 5: Modularize CLI Command Handlers (`scifi/cli.py`)

**Files:**
- Create: `scifi/commands/`
- Create: `scifi/commands/__init__.py`
- Create: `scifi/commands/math_cmd.py`
- Create: `scifi/commands/stats_cmd.py`
- Create: `scifi/commands/submission_cmd.py`
- Create: `scifi/commands/rebuttal_cmd.py`
- Create: `scifi/commands/doctor_cmd.py`
- Modify: `scifi/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `argparse.Namespace`.
- Produces: Clean, isolated command execution functions returning exit code `int`.

- [ ] **Step 1: Write CLI subcommand execution tests in `tests/test_cli.py`**
  Add test cases verifying `sf math units`, `sf math limits`, `sf stats curve`, `sf submission letter`, etc.

- [ ] **Step 2: Extract command handlers into `scifi/commands/`**
  Move substantive business logic out of `scifi/cli.py` so `cli.py` focuses purely on argument definition and top-level error trapping.

- [ ] **Step 3: Run CLI test suite**
  Run: `uv run pytest tests/test_cli.py -v`
  Expected: PASS

- [ ] **Step 4: Run full test suite**
  Run: `uv run pytest tests/ -q`
  Expected: PASS

- [ ] **Step 5: Commit**
  ```bash
  git add scifi/commands/ scifi/cli.py tests/test_cli.py
  git commit -m "refactor: modularize CLI subcommand handlers into scifi.commands"
  ```

---

### Task 6: Class Docstrings & Typing Completeness

**Files:**
- Modify: `scifi/submission/models.py`
- Modify: `scifi/literature/models.py`
- Modify: `scifi/citation_verifier/models.py`
- Modify: `scifi/rebuttal/models.py`
- Modify: `scifi/latex/project.py`
- Modify: `scifi/latex/venue.py`
- Modify: `scifi/figures/models.py`
- Modify: `scifi/proofs/models.py`
- Modify: `scifi/reproducibility/models.py`
- Modify: `scifi/layout/models.py`
- Modify: `scifi/argus/models.py`
- Modify: `scifi/web/server.py`

**Interfaces:**
- Consumes: Domain knowledge.
- Produces: 100% Google-style docstrings across all public classes, documenting attributes, invariants, and serialization behaviors.

- [ ] **Step 1: Write automated docstring verification test in `tests/test_docstrings.py`**
  Verify that all public classes in `scifi` have non-empty docstrings.

- [ ] **Step 2: Add comprehensive docstrings to all 56 undocumented classes**
  Cover models in `submission`, `literature`, `rebuttal`, `figures`, `proofs`, `reproducibility`, `layout`, and `argus`.

- [ ] **Step 3: Run docstring test**
  Run: `uv run pytest tests/test_docstrings.py -v`
  Expected: PASS (class docstring coverage = 100%)

- [ ] **Step 4: Commit**
  ```bash
  git add scifi/ tests/test_docstrings.py
  git commit -m "docs: document all domain classes with Google-style docstrings"
  ```

---

### Task 7: MkDocs Material Documentation Site & README Synchronization

**Files:**
- Create: `mkdocs.yml`
- Create: `docs/index.md`
- Create: `docs/getting-started.md`
- Create: `docs/architecture.md`
- Create: `docs/cli-reference.md`
- Create: `docs/mcp-tools.md`
- Create: `docs/web-cockpit.md`
- Create: `docs/zotero.md`
- Modify: `README.md`
- Modify: `pyproject.toml` (add `mkdocs-material`, `mkdocstrings[python]` to optional dev)

**Interfaces:**
- Consumes: Codebase docstrings, markdown guides, FastMCP tool specs.
- Produces: Professional, searchable documentation site ready for GitHub Pages or local preview (`mkdocs serve`).

- [ ] **Step 1: Configure `mkdocs.yml`**
  Set up MkDocs with Material theme, navigation structure, search, code highlighting, and `mkdocstrings` Python handler.

- [ ] **Step 2: Write core documentation pages**
  - `docs/index.md`: Overview, feature highlights, install snippet.
  - `docs/getting-started.md`: Setup for Antigravity, Claude Code, Cursor, Windsurf, and CLI.
  - `docs/architecture.md`: Tripartite model, FastMCP protocol, SQLite schema, multi-file LaTeX resolver.
  - `docs/cli-reference.md`: Exhaustive guide to all 25+ subcommands, options, and sample outputs.
  - `docs/mcp-tools.md`: Complete reference of all 46 FastMCP tools.
  - `docs/web-cockpit.md`: Web UI cockpit, central literature hub, and PDF reprint requests.
  - `docs/zotero.md`: Local Zotero SQLite reader, live sync, and annotation integration.

- [ ] **Step 3: Update `README.md`**
  - Update test count badge to `565+ passed`.
  - Update tool count in text and headers to `46 FastMCP Tools`.
  - Add section on the Web UI cockpit (`sf ui`).
  - Add link to the new MkDocs documentation.

- [ ] **Step 4: Build MkDocs site to verify no errors**
  Run: `uv run mkdocs build --strict`
  Expected: `Documentation built in ... seconds` with 0 warnings/errors.

- [ ] **Step 5: Commit**
  ```bash
  git add mkdocs.yml docs/ README.md pyproject.toml
  git commit -m "docs: setup MkDocs Material documentation site and update README"
  ```
