# SciFi REA-Style MCP + Skills Architecture Design

- **Date:** 2026-11-02
- **Status:** Approved / Ready for Planning
- **Owner:** Pair Programming with User
- **Topic:** Architectural realignment of SciFi to the REA (Reverse Engineer Anything) model (FastMCP server daemon + modular skill playbooks + unified Python library + environment auto-setup).

---

## 1. Intent & The Why

SciFi is an Antigravity plugin for scientific research, academic manuscript auditing, and mathematical verification. Currently, its implementation is fragmented:
1. Core features are split between `scifi/` modules and 14 standalone Python scripts located in `skills/*/scripts/`.
2. When agents use tools, they invoke subprocesses via shell commands (`uv run python skills/...` or `uv run scifi ...`). This causes:
   - **Severe Shell Escaping & Syntax Bugs:** LaTeX math strings (e.g. `\frac{\partial f}{\partial x}`) get mangled or stripped by PowerShell and Bash quote parsing.
   - **High Latency:** Every single verification call cold-boots Python 3.12 and re-imports heavy libraries (`sympy`, `scipy`, `pint`, `bibtexparser`, `requests`), taking 1.5–3.0 seconds per call.
   - **Context Window Bloat:** Skill descriptions (`SKILL.md`) spend the majority of their token budget explaining CLI flags, arguments, and bash commands rather than focusing on scientific methodology and cognitive workflows.

Following the design pattern popularized by **REA (`morluto/rea` - Reverse Engineer Anything)**, this design transitions SciFi to a tripartite architecture:
- **MCP Server Engine (`FastMCP`):** Persistent, in-memory daemon executing deterministic math, verification, registry lookups, and TeX compilation via typed JSON-RPC tools.
- **Skill Playbooks (`SKILL.md`):** Modular, token-efficient playbooks focused strictly on reasoning, judgment, rubrics, and tool-call strategies.
- **Unified Core Package (`scifi.*`):** A single Python library that powers both the MCP server and terminal CLI seamlessly.
- **Automated Setup (`scifi setup`):** An REA-style environment installer that auto-configures MCP server entries across Antigravity, Claude Code, and Cursor.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- Consolidate all 14 standalone scripts in `skills/*/scripts/` into first-class `scifi` Python submodules (`scifi.citation`, `scifi.math`, `scifi.latex`, `scifi.stats`, `scifi.literature`, `scifi.argus`, `scifi.review`).
- Provide an in-memory `FastMCP` server (`scifi.server`) exposing structured tools with strict schemas.
- Implement an Antigravity-native `mcp_config.json` at the plugin root so Antigravity loads the server automatically when the plugin is active.
- Refactor all `skills/*/SKILL.md` files to be lean cognitive playbooks referencing MCP tools instead of terminal commands.
- Provide a `scifi setup` CLI command to auto-detect and register the MCP server in agent environments.
- Maintain a focused, human-facing CLI (Option A: `scifi verify`, `scifi audit`, `scifi search`, `scifi argus`, `scifi setup`, `scifi server`), leaving fine-grained step-by-step checks to MCP tools.
- Introduce an in-memory + SQLite caching layer for external API calls (Crossref, OpenAlex, arXiv) to prevent rate limits and speed up repeat queries.
- Ensure 100% backward compatibility for existing user CLI workflows.

### Non-Goals
- We are not changing the core scientific rules in `rules/AGENTS.md` (the strict zero-hallucination and mathematical rigor rules remain intact).
- We are not replacing LaTeX engines (`latexmk`, `pdflatex`); the MCP compiler tool orchestrates the local TeX installation.
- We are not converting purely qualitative LLM skills (like `human` prose rewriting and `popper` hostile peer-review heuristics) into deterministic code; they remain prompt-based skills.
- We are not mirroring every single granular MCP tool (e.g. `check_units`, `verify_derivative`) into separate terminal CLI commands; those belong in MCP.

### Anti-Goals
- Do not keep duplicate logic between CLI commands and MCP tools: both must invoke the exact same underlying `scifi.*` functions.
- Do not require users to run manual background processes; the MCP server must launch on-demand via standard stdio JSON-RPC.

---

## 3. Constraints
- **Python Version:** Python >= 3.12 managed with `uv`.
- **Dependencies:** Add `mcp>=1.0.0` to `pyproject.toml`.
- **Operating Systems:** Must work seamlessly cross-platform on Windows (PowerShell/cmd), macOS, and Linux without platform-dependent shell quirks.
- **MCP Protocol:** Must adhere to the standard Model Context Protocol (using the official Python `mcp` package with `FastMCP`).
- **Antigravity Customization Standards:** Must adhere to Antigravity plugin structure (`plugin.json`, `mcp_config.json`, `rules/`, `skills/`, `agents/`).

---

## 4. Evaluated Approaches & Selection

1. **Approach 1: Full REA Architectural Realignment (SELECTED)**
   - Consolidate all scripts into `scifi.*`, implement the `FastMCP` server daemon, write `mcp_config.json`, slim down skills to cognitive playbooks, and add `scifi setup`.
   - *Why chosen:* Solves all friction points (LaTeX escaping, cold-boot latency, script duplication, context bloat) and produces a clean, professional, production-grade toolkit.

2. **Approach 2: Two-Phase Progressive Realignment**
   - Phase 1 (Alex citation + Turing math) followed by Phase 2 (remaining tools + setup).
   - *Trade-off:* Leaves temporary fragmentation during the migration.

3. **Approach 3: Thin MCP Wrapper around Existing Scripts**
   - Leave `skills/*/scripts/*.py` as-is and wrap them in a server.
   - *Trade-off:* Preserves code debt, slow subprocess invocations, and duplicate CLI parsers.

---

## 5. Detailed Architecture

```
scifi/
├── plugin.json                    # Plugin manifest
├── mcp_config.json                # Plugin MCP configuration
├── pyproject.toml                 # Dependencies: mcp, sympy, pint, bibtexparser, etc.
├── rules/
│   └── AGENTS.md                  # Scientific rigor & citation invariants
├── agents/                        # Subagents (scholar, theorist, scribe, auditor, argus)
├── skills/                        # Lean skill playbooks (alex, turing, human, gauss, etc.)
│   ├── alex/SKILL.md
│   ├── turing/SKILL.md
│   ├── human/SKILL.md
│   ├── gauss/SKILL.md
│   ├── compiler/SKILL.md
│   ├── hypatia/SKILL.md
│   ├── popper/SKILL.md
│   ├── argus/SKILL.md
│   └── uv/SKILL.md
└── scifi/                         # Consolidated Python package
    ├── __init__.py
    ├── server.py                  # FastMCP server entrypoint
    ├── cli.py                     # Unified CLI entrypoint (Option A)
    ├── cache.py                   # SQLite registry & query cache
    ├── setup_cli.py               # REA-style setup installer
    ├── citation/                  # Alex: DOIs, Crossref, OpenAlex, arXiv, BibTeX
    │   ├── verifier.py
    │   ├── bib_auditor.py
    │   ├── registries.py
    │   └── models.py
    ├── math/                      # Turing: SymPy calculus & algebraic checks
    │   ├── calculus.py            # Derivatives, limits, integrals
    │   ├── units.py               # Pint dimensional analysis
    │   ├── linear_algebra.py      # Matrix & tensor shape checks
    │   ├── convexity.py           # Hessian & convexity proofs
    │   ├── numerical.py           # Closed-form vs simulation comparison
    │   └── notation.py            # Manuscript symbol consistency
    ├── stats/                     # Gauss: numerical & curve verification
    │   ├── curve_fit.py           # Empirical curve vs formula comparison
    │   └── hypothesis.py          # Sample size, CLT (N >= 30), and confidence interval audits
    ├── latex/                     # Compiler engine
    │   └── compiler.py            # Subprocess runner & structured log error parser
    ├── literature/                # Hypatia: OA papers
    │   ├── fetcher.py             # Open-access PDF retrieval
    │   └── extractor.py           # PyPDF text extraction
    ├── argus/                     # Argus: Attribution & plagiarism engine (modular)
    │   ├── detector.py
    │   ├── engine.py
    │   ├── models.py
    │   ├── patcher.py
    │   └── searcher.py
    └── review/                    # Popper & Adversarial Review tools
        └── claims.py              # Overclaim & sweeping statement regex scanner
```

---

### 5.1 MCP Tool Surface (`scifi/server.py`)

All tools use `FastMCP` with descriptive docstrings and typed arguments:

#### Literature & Citations (Alex)
- `scifi_verify_citation(identifier: str, claimed_title: str | None = None, claimed_author: str | None = None, claimed_year: int | None = None) -> dict`
- `scifi_audit_bib(bib_path: str, output_bib: str | None = None) -> dict`
- `scifi_search_literature(query: str, limit: int = 5) -> list[dict]`

#### Attribution & Plagiarism (Argus)
- `scifi_audit_attribution(file_path: str, bib_path: str | None = None, autofix: bool = False, enable_search: bool = True) -> dict`:
  Audits uncredited algorithms, models, and techniques. If `autofix=False`, returns structured findings and suggested citations; if `autofix=True`, mutates LaTeX files and appends clean BibTeX entries.

#### Symbolic Math & Physics (Turing)
- `scifi_verify_derivative(expr: str, var: str, claimed: str) -> dict`
- `scifi_verify_derivation_step(lhs: str, rhs: str, assumptions: list[str] | None = None) -> dict`
- `scifi_check_units(lhs: str, rhs: str | None = None, check_mode: str = "eq") -> dict`
- `scifi_check_matrix_shapes(operation: str, dimensions: dict[str, list[int]]) -> dict`
- `scifi_check_limits(expr: str, var: str, point: str, claimed: str, direction: str = "+-") -> dict`
- `scifi_check_convexity(expr: str, var: str) -> dict`

#### LaTeX & Manuscript (Compiler & Notation)
- `scifi_check_notation(tex_path: str, sections: list[str] | None = None) -> dict`
- `scifi_compile_latex(entrypoint: str, engine: str = "latexmk") -> dict`

#### Numerical & Statistics (Gauss)
- `scifi_verify_curve(formula_latex: str, var_name: str, sim_data_path: str | None = None, x_vals: list[float] | None = None, y_vals: list[float] | None = None, rtol: float = 1e-2, atol: float = 1e-3) -> dict`:
  Validates that theoretical closed-form LaTeX formulas align with empirical simulation curves (either loaded from a CSV/JSON file or passed directly as lists).
- `scifi_audit_statistics(samples: list[float], confidence: float = 0.95) -> dict`:
  Computes sample mean, standard error, confidence intervals, and flags violations of the Central Limit Theorem ($N < 30$).

#### Adversarial Review & Methodology (Popper)
- `scifi_audit_claims(file_path: str) -> dict`:
  Scans manuscript text for unhedged impact statements, unproven optimality claims, or unjustified idealizations.

#### Open-Access Retrieval (Hypatia)
- `scifi_fetch_paper_pdf(identifier: str, output_dir: str = "workspace") -> dict`
- `scifi_extract_pdf_text(pdf_path: str, max_pages: int = 20) -> dict`

---

### 5.2 Unified Human-Facing CLI (`scifi/cli.py`)

Under Option A, the terminal CLI provides a clean user interface:
- `scifi verify <identifier>`: Verify DOI, arXiv link, or PubMed ID against registries.
- `scifi audit <bib_file>`: Audit and sanitize a `.bib` file.
- `scifi search "<title>"`: Search OpenAlex and Crossref.
- `scifi argus <file>`: Run attribution and plagiarism checks.
- `scifi setup`: Run the interactive REA-style MCP installer.
- `scifi server`: Run the FastMCP server over stdio.

---

### 5.3 SQLite Caching Layer (`scifi/cache.py`)
- Caches DOI metadata, OpenAlex records, and arXiv query responses in a local SQLite database (`~/.cache/scifi/cache.db` or `.scifi/cache.db`).
- Configurable TTL (7 days for verified records, 24 hours for preprints).

---

### 5.4 Automated Setup CLI (`scifi setup`)
Modeled directly after `npx rea-agents setup`:
- Running `uv run scifi setup` (or `scifi setup` when installed):
  1. Detects available agent environments:
     - Antigravity: `~/.gemini/config/mcp_config.json` or local `.agents/`
     - Claude Code: `~/.claude/claude_desktop_config.json`
     - Cursor: `.cursor/mcp.json`
  2. Registers the SciFi MCP server entry with absolute directory resolution.
  3. Validates connection by pinging the server via stdio.

---

### 5.5 Antigravity Native Integration (`mcp_config.json`)
The plugin root will contain `mcp_config.json`:
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
Whenever the user enables the SciFi plugin in Antigravity, Antigravity launches the server automatically.

---

### 5.6 Refactored Skill Playbooks
Each `skills/*/SKILL.md` is transformed from a CLI flag manual into a lean cognitive playbook:
1. Explains the methodology, scientific criteria, and interpretation of results.
2. Directs the agent to invoke the corresponding `scifi_*` MCP tool.
3. Completely removes verbose CLI syntax, argparse flags, and bash examples.

---

## 6. What's Left to the Builder (Settled Calls)
- **CLI Scope:** Option A selected. Terminal CLI is focused on human workflows (`verify`, `audit`, `search`, `argus`, `setup`, `server`).
- **Gauss / Turing Numerical verification:** Retain full LaTeX formula parsing and simulation comparison (both via file path and inline array lists).
- **Argus Package Architecture:** Retain the full 5-module structure under `scifi.argus` rather than collapsing into a single file. Expose `scifi_audit_attribution` with an `autofix` parameter.
- **Popper Claims Script (#14):** Preserved and consolidated under `scifi.review.claims`, exposed via `scifi_audit_claims`.
- **Working Directory Strategy:** MCP server uses standard stdio with `scifi.server` entrypoint; `setup` CLI resolves absolute directory paths when writing configs for third-party clients.
