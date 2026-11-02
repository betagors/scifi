# SciFi REA-Style MCP + Skills Realignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform SciFi into a unified Python engine with a persistent `FastMCP` server daemon, lean skill playbooks, an REA-style auto-setup installer, and a focused human-facing CLI.

**Architecture:** Consolidate 14 loose scripts into clean submodules under `scifi.*` (`math`, `stats`, `latex`, `literature`, `review`). Expose all deterministic verification engines via an in-memory `FastMCP` server with SQLite caching and native `mcp_config.json` plugin integration, while refactoring `skills/*/SKILL.md` into lean cognitive playbooks.

**Tech Stack:** Python >= 3.12, `uv`, `mcp>=1.0.0` (FastMCP), `sympy`, `pint`, `scipy`, `numpy`, `bibtexparser`, `requests`, `pypdf`, `sqlite3`, `pytest`.

**Spec:** [`docs/superpowers/specs/2026-11-02-scifi-rea-mcp-design.md`](file:///c:/Users/Betagors/Code/scifi/docs/superpowers/specs/2026-11-02-scifi-rea-mcp-design.md)

---

## Global Constraints

- Python version floor: `>=3.12`.
- Package manager: `uv`.
- Protocol: Model Context Protocol (MCP) using official Python `mcp` SDK with `FastMCP`.
- Platform support: Fully compatible with Windows (PowerShell/cmd), macOS, and Linux with zero platform-specific shell quirks.
- Invariants: Preserve zero-hallucination citation integrity, mathematical rigor, and LaTeX notation consistency defined in `rules/AGENTS.md`.
- CLI Scope: Option A (Human-facing CLI: `scifi verify`, `scifi audit`, `scifi search`, `scifi argus`, `scifi setup`, `scifi server`).

---

## Review Focus

1. **LaTeX syntax & macro resilience:** Malformed LaTeX or unsupported custom macros passed to SymPy parser must return structured error dicts (`{"status": "ERROR", "error_message": "..."}`) rather than crashing the MCP server.
2. **Missing data files / invalid keys:** In `scifi_verify_curve` and `scifi_audit_statistics`, non-existent CSV/JSON files, missing columns, or lists with $<2$ elements must return informative error payloads.
3. **Network resilience & rate-limiting:** Offline mode or HTTP timeouts when querying Crossref/OpenAlex/arXiv must fall back gracefully to the SQLite cache or return a clear status (`NETWORK_ERROR` or `UNRESOLVED`).
4. **Missing host TeX compilers:** When `latexmk` and `pdflatex` are not on `PATH`, `scifi_compile_latex` must return `{"status": "COMPILER_NOT_FOUND", "hint": "..."}` with installation instructions.
5. **CLI backward compatibility:** Existing commands (`scifi verify ...`, `scifi audit ...`, `scifi search ...`, `scifi argus ...`) must preserve their exact argument flags and output formatting.

---

## Task Decomposition

### Task 1: Add Dependencies & Project Packaging

**Files:**
- Modify: `pyproject.toml`
- Test: Run `uv sync` and check import of `mcp`

**Interfaces:**
- Consumes: None
- Produces: `mcp>=1.0.0` and `pytest>=8.0.0` available in virtual environment

- [ ] **Step 1: Add `mcp` and `pytest` dependencies to `pyproject.toml`**
  Add `"mcp>=1.0.0"` to `project.dependencies` and add `pytest>=8.0.0` to dev dependencies / dependencies.
- [ ] **Step 2: Sync dependencies with `uv sync`**
  Run: `uv sync`
  Expected: Success, lockfile updated.
- [ ] **Step 3: Verify import in Python**
  Run: `uv run python -c "import mcp; from mcp.server.fastmcp import FastMCP; print('MCP imported successfully')"`
  Expected: "MCP imported successfully"
- [ ] **Step 4: Commit**
  ```bash
  git add pyproject.toml uv.lock
  git commit -m "build: add mcp and pytest dependencies"
  ```

---

### Task 2: SQLite Registry & Query Caching (`scifi.cache`)

**Files:**
- Create: `scifi/cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: Standard library `sqlite3`, `json`, `pathlib`
- Produces: `RegistryCache` class with `get(key: str) -> dict | None`, `set(key: str, data: dict, ttl_seconds: int = 604800) -> None`, `clear() -> None`

- [ ] **Step 1: Write failing tests in `tests/test_cache.py`**
  Test `get` on missing key (returns `None`), `set` then `get` (returns cached dict), and expired TTL (returns `None`).
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_cache.py`
  Expected: FAIL (module `scifi.cache` does not exist).
- [ ] **Step 3: Implement `scifi/cache.py`**
  Create `RegistryCache` managing a SQLite database at `~/.cache/scifi/cache.db` (or custom path for testing). Store `(key, value_json, expires_at)`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_cache.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add scifi/cache.py tests/test_cache.py
  git commit -m "feat(cache): implement SQLite registry cache"
  ```

---

### Task 3: Consolidate Math & Physics Submodules (`scifi.math`)

**Files:**
- Create: `scifi/math/__init__.py`
- Create: `scifi/math/calculus.py` (migrated from `skills/turing/scripts/verify_derivation.py` & `verify_limits.py`)
- Create: `scifi/math/units.py` (migrated from `skills/turing/scripts/verify_units.py`)
- Create: `scifi/math/linear_algebra.py` (migrated from `skills/turing/scripts/verify_matrix_shapes.py`)
- Create: `scifi/math/convexity.py` (migrated from `skills/turing/scripts/verify_convexity.py`)
- Create: `scifi/math/notation.py` (migrated from `skills/turing/scripts/verify_notation.py`)
- Test: `tests/test_math.py`

**Interfaces:**
- Consumes: `sympy`, `pint`, `re`
- Produces:
  - `verify_derivative(expr: str, var: str, claimed: str) -> dict`
  - `verify_derivation_step(lhs: str, rhs: str, assumptions: list[str] | None = None) -> dict`
  - `check_limits(expr: str, var: str, point: str, claimed: str, direction: str = "+-") -> dict`
  - `check_units(lhs: str, rhs: str | None = None, check_mode: str = "eq") -> dict`
  - `check_matrix_shapes(operation: str, dimensions: dict[str, list[int]]) -> dict`
  - `check_convexity(expr: str, var: str) -> dict`
  - `check_notation(tex_content_or_path: str, sections: list[str] | None = None) -> dict`

- [ ] **Step 1: Write comprehensive failing tests in `tests/test_math.py`**
  Cover derivative verification (valid vs invalid), unit equality (5 watt * second == 5 joule), matrix shape compatibility ($A_{2\times 3} B_{3\times 4}$), and limit verification ($\lim_{x\to 0} \frac{\sin x}{x} = 1$). Include test for malformed LaTeX handling.
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_math.py`
  Expected: FAIL (`scifi.math` not found).
- [ ] **Step 3: Implement `scifi/math/` submodules**
  Extract logic cleanly from `skills/turing/scripts/` into pure, typed Python functions without `argparse`. Ensure all exceptions return structured `{"status": "ERROR", ...}` dicts.
- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_math.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add scifi/math/ tests/test_math.py
  git commit -m "feat(math): consolidate Turing mathematical engines into scifi.math"
  ```

---

### Task 4: Consolidate Statistics & Numerical Submodules (`scifi.stats`)

**Files:**
- Create: `scifi/stats/__init__.py`
- Create: `scifi/stats/curve_fit.py` (migrated from `skills/gauss/scripts/verify_curve_match.py` & `skills/turing/scripts/verify_numerical.py`)
- Create: `scifi/stats/hypothesis.py` (migrated from `skills/gauss/scripts/audit_statistics.py`)
- Test: `tests/test_stats.py`

**Interfaces:**
- Consumes: `numpy`, `scipy`, `sympy`
- Produces:
  - `verify_curve(formula_latex: str, var_name: str, sim_data_path: str | None = None, x_vals: list[float] | None = None, y_vals: list[float] | None = None, rtol: float = 1e-2, atol: float = 1e-3) -> dict`
  - `audit_statistics(samples: list[float], confidence: float = 0.95) -> dict`

- [ ] **Step 1: Write failing tests in `tests/test_stats.py`**
  Test `verify_curve` with inline `x_vals`/`y_vals` and matching formula (e.g. $y = 2x$), test with diverging data (flags mismatch), test `audit_statistics` with $N \ge 30$ vs $N < 30$, and test empty/small sample error handling.
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_stats.py`
  Expected: FAIL (`scifi.stats` not found).
- [ ] **Step 3: Implement `scifi/stats/curve_fit.py` and `scifi/stats/hypothesis.py`**
  Support both CSV/JSON file paths and inline lists for data points. Ensure robust error handling when files or arrays are missing.
- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_stats.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add scifi/stats/ tests/test_stats.py
  git commit -m "feat(stats): consolidate Gauss numerical and statistical engines into scifi.stats"
  ```

---

### Task 5: Consolidate LaTeX Compiler & Adversarial Claims Scanner

**Files:**
- Create: `scifi/latex/__init__.py`
- Create: `scifi/latex/compiler.py` (migrated from `skills/compiler/scripts/compile_latex.py`)
- Create: `scifi/review/__init__.py`
- Create: `scifi/review/claims.py` (migrated from `skills/popper/scripts/audit_claims.py`)
- Test: `tests/test_latex_and_review.py`

**Interfaces:**
- Consumes: `subprocess`, `re`, `pathlib`
- Produces:
  - `compile_latex(entrypoint: str, engine: str = "latexmk", clean: bool = True) -> dict`
  - `audit_claims(tex_content_or_path: str) -> dict`

- [ ] **Step 1: Write failing tests in `tests/test_latex_and_review.py`**
  Test `audit_claims` against sample text containing sweeping words ("drastically improves", "completely eliminates", "optimal"), ensuring it flags line numbers and critiques. Test `compile_latex` with non-existent file or simulated missing compiler.
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_latex_and_review.py`
  Expected: FAIL.
- [ ] **Step 3: Implement `scifi/latex/compiler.py` and `scifi/review/claims.py`**
  Support both file paths and direct text strings. Parse LaTeX compilation log files into structured errors (`file`, `line`, `message`, `error_type`).
- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_latex_and_review.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add scifi/latex/ scifi/review/ tests/test_latex_and_review.py
  git commit -m "feat(latex,review): consolidate LaTeX compiler and Popper claims auditor"
  ```

---

### Task 6: Consolidate Literature & PDF Extraction (`scifi.literature`)

**Files:**
- Create: `scifi/literature/__init__.py`
- Create: `scifi/literature/fetcher.py` (migrated from `skills/hypatia/scripts/fetch_oa_pdf.py`)
- Create: `scifi/literature/extractor.py` (migrated from `skills/hypatia/scripts/extract_paper_text.py`)
- Test: `tests/test_literature.py`

**Interfaces:**
- Consumes: `pypdf`, `requests`, `pathlib`
- Produces:
  - `fetch_paper_pdf(identifier: str, output_dir: str = "workspace") -> dict`
  - `extract_pdf_text(pdf_path: str, max_pages: int = 20) -> dict`

- [ ] **Step 1: Write failing tests in `tests/test_literature.py`**
  Test `extract_pdf_text` on existing sample PDF in `assets/` or `workspace/test.pdf`, asserting extracted text length and page metadata. Test invalid PDF path handling.
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_literature.py`
  Expected: FAIL (`scifi.literature` not found).
- [ ] **Step 3: Implement `fetcher.py` and `extractor.py`**
  Support arXiv direct PDFs, Unpaywall/OpenAlex OA URLs, and clean text extraction with `pypdf`.
- [ ] **Step 4: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_literature.py`
  Expected: PASS
- [ ] **Step 5: Commit**
  ```bash
  git add scifi/literature/ tests/test_literature.py
  git commit -m "feat(literature): consolidate Hypatia OA paper fetcher and text extractor"
  ```

---

### Task 7: FastMCP Server Daemon (`scifi.server`) & `mcp_config.json`

**Files:**
- Create: `scifi/server.py`
- Create: `mcp_config.json`
- Test: `tests/test_server.py`

**Interfaces:**
- Consumes: `mcp.server.fastmcp.FastMCP`, all `scifi.*` submodules
- Produces: FastMCP server `mcp` with 15 registered tools:
  - `scifi_verify_citation`
  - `scifi_audit_bib`
  - `scifi_search_literature`
  - `scifi_audit_attribution`
  - `scifi_verify_derivative`
  - `scifi_verify_derivation_step`
  - `scifi_check_units`
  - `scifi_check_matrix_shapes`
  - `scifi_check_limits`
  - `scifi_check_convexity`
  - `scifi_check_notation`
  - `scifi_compile_latex`
  - `scifi_verify_curve`
  - `scifi_audit_statistics`
  - `scifi_audit_claims`
  - `scifi_fetch_paper_pdf`
  - `scifi_extract_pdf_text`

- [ ] **Step 1: Write failing tests in `tests/test_server.py`**
  Instantiate `mcp` from `scifi.server` and assert that all 15+ tool names are properly registered with docstrings and typed parameters.
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_server.py`
  Expected: FAIL (`scifi.server` not found).
- [ ] **Step 3: Implement `scifi/server.py`**
  Define `mcp = FastMCP("scifi", instructions="Scientific Research & Academic Writing Toolkit")`. Register all tools with docstrings and typed arguments. Connect citation lookups to `RegistryCache`.
- [ ] **Step 4: Create `mcp_config.json` in plugin root**
  ```json
  {
    "mcpServers": {
      "scifi": {
        "command": "uv",
        "args": ["run", "python", "-m", "scifi.server"]
      }
    }
  }
  ```
- [ ] **Step 5: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_server.py`
  Expected: PASS
- [ ] **Step 6: Commit**
  ```bash
  git add scifi/server.py mcp_config.json tests/test_server.py
  git commit -m "feat(mcp): implement FastMCP server and plugin mcp_config.json"
  ```

---

### Task 8: Unified Human-Facing CLI (`scifi.cli`) & REA Setup Installer (`scifi.setup_cli`)

**Files:**
- Create: `scifi/cli.py`
- Create: `scifi/setup_cli.py`
- Modify: `pyproject.toml` (update `[project.scripts]`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `scifi.citation`, `scifi.argus`, `scifi.server`, `scifi.setup_cli`
- Produces: CLI commands: `scifi verify`, `scifi audit`, `scifi search`, `scifi argus`, `scifi setup`, `scifi server`

- [ ] **Step 1: Write failing tests in `tests/test_cli.py`**
  Test CLI parser for `verify`, `audit`, `search`, `argus`, `setup`, `server` verbs. Test help text and argument handling.
- [ ] **Step 2: Run test to verify it fails**
  Run: `uv run python -m unittest tests/test_cli.py`
  Expected: FAIL.
- [ ] **Step 3: Implement `scifi/setup_cli.py`**
  Detect Antigravity (`~/.gemini/config/mcp_config.json`), Claude Desktop (`~/.claude/claude_desktop_config.json`), Cursor (`.cursor/mcp.json`). Offer interactive prompt or `--auto` flag to register `scifi` with absolute path.
- [ ] **Step 4: Implement `scifi/cli.py`**
  Route subcommands to existing verifiers and new server/setup commands. Update `pyproject.toml` `[project.scripts]` to point `scifi = "scifi.cli:main"`.
- [ ] **Step 5: Run test to verify it passes**
  Run: `uv run python -m unittest tests/test_cli.py`
  Expected: PASS
- [ ] **Step 6: Commit**
  ```bash
  git add scifi/cli.py scifi/setup_cli.py pyproject.toml tests/test_cli.py
  git commit -m "feat(cli): implement unified CLI and REA-style setup installer"
  ```

---

### Task 9: Refactor Skill Playbooks & Deprecate Standalone Scripts

**Files:**
- Modify: `skills/alex/SKILL.md`
- Modify: `skills/turing/SKILL.md`
- Modify: `skills/gauss/SKILL.md`
- Modify: `skills/compiler/SKILL.md`
- Modify: `skills/hypatia/SKILL.md`
- Modify: `skills/popper/SKILL.md`
- Modify: `skills/argus/SKILL.md`
- Remove: `skills/*/scripts/` (after confirming all modules are functional)

**Interfaces:**
- Consumes: MCP tool definitions from `scifi.server`
- Produces: Clean, token-efficient cognitive playbooks for AI agents

- [ ] **Step 1: Refactor `skills/alex/SKILL.md`**
  Remove bash snippets and CLI flags. Instruct agent to invoke `scifi_verify_citation`, `scifi_audit_bib`, or `scifi_search_literature`.
- [ ] **Step 2: Refactor `skills/turing/SKILL.md`**
  Direct agent to call `scifi_verify_derivative`, `scifi_verify_derivation_step`, `scifi_check_units`, `scifi_check_matrix_shapes`, `scifi_check_notation`.
- [ ] **Step 3: Refactor `skills/gauss/SKILL.md`, `skills/compiler/SKILL.md`, `skills/hypatia/SKILL.md`, `skills/popper/SKILL.md`, `skills/argus/SKILL.md`**
  Update each playbook to focus on methodology, interpretation, and invoking their respective `scifi_*` tools.
- [ ] **Step 4: Clean up obsolete standalone script files in `skills/*/scripts/`**
  Remove deprecated scripts now consolidated into `scifi.*`.
- [ ] **Step 5: Commit**
  ```bash
  git add skills/
  git commit -m "docs(skills): refactor skill playbooks to use MCP tools and remove legacy scripts"
  ```

---

### Task 10: Full Test Suite & End-to-End Verification

**Files:**
- Test: All tests in `tests/`
- Verify: Direct FastMCP tool execution via Python test harness
- Verify: CLI commands (`scifi --help`, `scifi verify --help`)

- [ ] **Step 1: Run complete test suite**
  Run: `uv run python -m unittest discover -s tests -v`
  Expected: All tests pass (including citation, argus, math, stats, latex, literature, cache, server, and cli).
- [ ] **Step 2: Verify FastMCP server startup & ping**
  Run: `uv run python -c "from scifi.server import mcp; print(f'Registered tools: {len(mcp._tool_manager._tools)} tools')"`
  Expected: Successfully displays count of registered tools (17 tools).
- [ ] **Step 3: Verify CLI entrypoint**
  Run: `uv run scifi --help`
  Expected: Clean help output listing `verify`, `audit`, `search`, `argus`, `setup`, `server`.
- [ ] **Step 4: Final commit**
  ```bash
  git add -A
  git commit -m "chore: complete REA-style MCP realignment verification"
  ```
