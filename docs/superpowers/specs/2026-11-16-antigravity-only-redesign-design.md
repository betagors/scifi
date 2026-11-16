# Antigravity-Only Redesign Specification

**Date:** 2026-11-16
**Status:** Draft (Pending User Approval)
**Approach Selected:** Approach 2 — Antigravity-Native Redesign

---

## 1. Intent & Why

The user primarily operates in **Google Antigravity**. Maintaining compatibility layers for 6+ external AI IDEs and CLIs (`.cursorrules`, `.windsurfrules`, `.clinerules`, `CLAUDE.md`, `.github/copilot-instructions.md`, `gemini-extension.json`, `commands/*.toml`, and multi-IDE setup/detection code in `scifi/setup_cli.py`) introduces constant maintenance overhead and prevents optimizing `scifi` around Antigravity's native plugin architecture.

### Key Codebase Findings Driving This Redesign

1. **Double-Injected Rules Leak (~31.4 KB / ~8,000 tokens per turn):**
   When working inside the `scifi` repository, Antigravity loads `rules/AGENTS.md` (15,702 bytes) via the enabled `scifi` plugin *and* loads root `AGENTS.md` (15,971 bytes) via workspace directory traversal. Because root `AGENTS.md` wraps the same text in `<!-- SCIFI-RULES:START -->` ... `<!-- SCIFI-RULES:END -->` comments, Antigravity's file-content/path deduplicator sees two distinct files and injects **both** copies into every conversation turn.
2. **Always-On Rule Bloat:**
   Even in external research workspaces, `rules/AGENTS.md` is 15.7 KB of dense per-skill checklists, numeric thresholds, and formula rules (e.g., Orwell's $B_{\mathrm{length}} > 0.55$, $R_{\mathrm{IB}} < 0.80$, Shannon's 65-char front-loading & 150–220 word beats, Elsevier 85-char highlights, 4-beat rebuttal structure). Antigravity inlines plugin `rules/AGENTS.md` unconditionally into the shared 20,000-token `defaultRulesBudget` every turn, whereas `skills/*/SKILL.md` files are lazy-loaded via progressive disclosure and already contain those details.
3. **Antigravity Lazy-Loads MCP Schemas:**
   All 63+ `scifi_*` tools in `scifi.server` are registered as `Lazy:` in Antigravity—their full JSON schemas live on disk under `<appDataDir>\mcp\scifi_scifi\` and are read on demand, costing only the short tool name list in the system prompt. Meanwhile, `FastMCP("scifi", instructions=...)` currently only says `"Scientific Research & Academic Writing Toolkit"`, missing an opportunity to steer Antigravity's 3-tier routing (`agents/` -> `skills/` -> `scifi_*` MCP / `sf` CLI).
4. **Legacy Multi-IDE Tool Names in Subagents:**
   `agents/scribe.md` explicitly lists non-Antigravity tool names (`view_file`, `replace_file_content`, `multi_replace_file_content`, `write_to_file`, `list_dir`, `grep_search`, `find_by_name`) alongside Antigravity tool names (`read_file`, `edit_file`, `write_file`, `run_command`).
5. **Missing Native Plugin `hooks.json`:**
   Antigravity native plugins (marked by root `plugin.json`) support a root `hooks.json` for lifecycle automation (`SessionStart`, `PreToolUse`, `PostToolUse`, `PreInvocation`, `PostInvocation`, `Stop`), which `scifi` does not yet ship or package.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
- Make `scifi` a clean, Antigravity-native plugin (`plugin.json`, `mcp_config.json`, `hooks.json`, `rules/AGENTS.md`, `skills/*/SKILL.md`, `agents/*.md`, `.agents/skills.json`).
- Eliminate all non-Antigravity IDE rule files, extension manifests, CLI command shims, and multi-IDE detection/installers.
- Eliminate the 31.4 KB duplicate rule injection and shrink `rules/AGENTS.md` (and `scifi/resources/AGENTS.md` + `DEFAULT_CANONICAL_RULES`) from ~15.7 KB to **under 4 KB** while retaining all 15 rule section headings (`## 1.`–`## 15.`) and non-negotiable always-on invariants.
- Tune `scifi.server` instructions, `agents/*.md`, and `hooks.json` specifically for Antigravity's progressive-disclosure and subagent execution model.

### Non-Goals
- Rewriting or changing the core scientific/LaTeX/Zotero/Zenodo/SymPy/KG Python engines (`scifi/citation_verifier/`, `scifi/orwell/`, `scifi/math/`, `scifi/latex/`, `scifi/literature/`, `scifi/doctor.py`, `scifi/submission/`, `scifi/zotero/`, `scifi/zenodo/`).
- Changing `scifi/scaffold.py` or `scifi/adapt.py` project structures (`paper/`, `code/`, `.scifi/`), which are already IDE-agnostic.

### Anti-Goals
- **Breaking Windows PowerShell Escaping:** Removing structured `@mcp.tool` endpoints for LaTeX, SymPy, BibTeX, Zotero, or Knowledge Graph payloads and forcing the agent to pass raw LaTeX/math strings through `run_command` CLI arguments.
- **Slow or Blocking Edit Hooks:** Installing `hooks.json` handlers that block or add noticeable latency to normal file edits or shell commands by default.
- **Rule Duplication in the `scifi` Repo:** Generating a root `AGENTS.md` inside the `scifi` plugin repository itself, which reintroduces double-injection alongside `rules/AGENTS.md`.

---

## 3. Constraints

- **Antigravity Rule Budget:** Individual rule files are capped at 24 KB (`24,000` bytes) and share a 20,000-token `defaultRulesBudget` across all always-on rules. Target for `rules/AGENTS.md` is `< 4,000` bytes (~1,000 tokens).
- **Antigravity Plugin Hook Placement:** Because `scifi` uses a root `plugin.json` (native plugin), `hooks.json` **must** live directly at `<plugin_root>/hooks.json` (not under `hooks/hooks.json`).
- **Package Resource Parity:** `rules/AGENTS.md` and `scifi/resources/AGENTS.md` must remain byte-for-byte identical (`tests/test_packaging.py::test_rules_file_parity`).
- **Rule 14 & 15 Compliance:** Source and test files should stay focused and under ~300 lines where practical; multi-chunk edits should be batched.
- **Global User Rule Compliance:** Never reference or invoke `rg` (ripgrep) in rules, skills, agents, or hooks; use `git grep` or PowerShell `Select-String`.

---

## 4. Approaches Considered

1. **Approach 1 — Lean Antigravity Plugin (Cleanup + Rule Diet):**
   Strip multi-IDE files and slim `rules/AGENTS.md`, leaving `scifi.server`, `agents/*.md`, and plugin packaging unchanged without `hooks.json`.
   *Tradeoff:* Lowest effort, but misses Antigravity-native MCP routing instructions, agent tool cleanup, and `hooks.json` support.
2. **Approach 2 — Antigravity-Native Redesign (Selected):**
   Strip all multi-IDE surface area, put `rules/AGENTS.md` on a strict <4 KB invariant-only diet, keep lazy-loaded MCP tools with 3-tier Antigravity routing instructions, clean up `agents/*.md` tool declarations, and add native `hooks.json` + Antigravity-only packaging/setup.
   *Tradeoff:* Requires updating `setup_cli.py`, `packaging.py`, `cli.py`, docs, and tests that expect multi-IDE files (`CLAUDE.md`, `.cursorrules`, `gemini-extension.json`, `commands/`), in exchange for maximal context savings and clean native Antigravity ergonomics.
3. **Approach 3 — Pure Skills + CLI (Minimal/No-MCP):**
   Delete most/all of `scifi/server/` and invoke `sf` CLI subcommands via `run_command` from `skills/*/SKILL.md`.
   *Tradeoff:* Rejected—Antigravity already lazy-loads MCP tool schemas (`Lazy:` mode), so keeping MCP costs minimal prompt tokens (~250 tokens for names) while protecting complex LaTeX/SymPy/BibTeX inputs from shell quoting/escaping bugs on Windows PowerShell.

---

## 5. Architecture & Design Decisions

### Pillar 1: Multi-IDE Surface Removal

1. **Delete Legacy Root Files & Directories:**
   - Remove `.clinerules`
   - Remove `.cursorrules`
   - Remove `.windsurfrules`
   - Remove `CLAUDE.md`
   - Remove `.github/copilot-instructions.md`
   - Remove `gemini-extension.json`
   - Remove root `AGENTS.md` (eliminates double-injection inside `scifi` repo since `rules/AGENTS.md` is loaded by the plugin)
   - Remove `commands/` directory (`commands/*.md` and `commands/*.toml` — Gemini CLI / Claude Code slash-command shims)

2. **Simplify `scifi/setup_cli.py`:**
   - **`detect_environments()`:** Detect only two Antigravity targets:
     1. `Antigravity (Global)`: `~/.gemini/config/mcp_config.json` (detected if `~/.gemini` or `mcp_config.json` exists, `scope="global"`)
     2. `Antigravity (Workspace)`: `<project>/.agents/mcp_config.json` (detected if `<project>/.agents` or `<project>/.agents/mcp_config.json` exists, `scope="workspace"`)
   - Remove Claude Desktop, Claude Code (Global & Workspace), Cursor, VS Code Cline, VS Code Roo Code, OpenCode (Global & Workspace), and Windsurf detection, along with `format_type="opencode"` branching in `is_mcp_installed()` and `install_mcp_config()`.
   - **`sync_all_rules()` and `check_rules_sync_status()`:**
     - Target only `<project>/AGENTS.md` (for external research paper repositories where the `scifi` plugin may or may not be mounted globally, or where workspace rules are desired).
     - **Self-Repo Guard:** If `<project>/rules/AGENTS.md` and `<project>/plugin.json` both exist (i.e., running inside the `scifi` plugin repository itself), `sync_all_rules()` must skip writing root `AGENTS.md` (and report that plugin rules are already provided via `rules/AGENTS.md`) so the double-injection bug cannot recur.
   - **`cmd_setup()`:**
     - `--workspace` installs `<project>/.agents/mcp_config.json` and syncs `<project>/AGENTS.md` (unless in the `scifi` plugin repo).
     - Remove multi-IDE messaging strings from `--help` and status output.

3. **Simplify `scifi/packaging.py`:**
   - In `build_plugin_bundle()`:
     - `root_files`: `["plugin.json", "mcp_config.json", "hooks.json", "LICENSE", "README.md", "CITATION.cff"]` (remove `"gemini-extension.json"`).
     - `include_dirs`: `["skills", "agents", "rules", "assets"]` (remove `"commands"`).
   - In `verify_plugin_bundle()`:
     - Require `plugin.json`, `mcp_config.json`, `hooks.json`, and `rules/AGENTS.md` in the archive, and verify `skills/` and `agents/` counts.

4. **Update `scifi/cli.py` and Docs:**
   - Update `--help` descriptions for `setup` and `sync` in `scifi/cli.py` to reference Antigravity (`~/.gemini/config/mcp_config.json`, `.agents/mcp_config.json`, `AGENTS.md`) instead of Cursor, Windsurf, Cline, Claude, or OpenCode.
   - Update `README.md`, `CONTRIBUTING.md`, `docs/index.md`, `docs/getting-started.md`, and `docs/cli-reference.md` to remove multi-IDE instructions and document the Antigravity plugin install (`plugin.json`, `hooks.json`, `mcp_config.json`, `sf setup`).

---

### Pillar 2: `rules/AGENTS.md` Context Diet & Skill Parity

1. **Condense `rules/AGENTS.md` (< 4 KB Target, ~75% Context Reduction):**
   - Preserve the exact 15 numbered section headings (`## 1.` through `## 15.`) so section semantics and downstream tests (`^## \d+\.`) remain intact and recognizable.
   - Retain **only**:
     - Universal always-on invariants (never fabricate DOIs/citations/data; check local Zotero before remote searches; verify proofs symbolically before asserting; never use negative `\vspace` hacks; never read raw large datasets >32 KB / >50 lines directly into context; keep files <300 lines; batch non-contiguous edits; never use `rg`).
     - Crisp 1-line routing pointers telling Antigravity which **skill** (`skills/<name>/SKILL.md`) or **subagent** (`@scholar`, `@argus`, `@scribe`, `@theorist`, `@auditor`, `@shannon`) owns the detailed thresholds, formulas, and workflows.
   - Strip all duplicated quantitative thresholds, LaTeX formatting recipes, Kobak marker lists, character ceilings, and beat-by-beat templates from `rules/AGENTS.md`—those already live in their respective `skills/*/SKILL.md` files.

2. **Skill Coverage Audit (No Lost Rules):**
   - Verify during implementation that every specific constraint removed from `rules/AGENTS.md` (e.g., Orwell $B_{\mathrm{length}} > 0.55$ and abbreviation hygiene; Popper theory-to-method certification alignment, no strawman critiques, cross-paper runtime caveat, invariant table columns; Shannon <35% overlap & acronym expansion; Euclid hypothesis/scope completeness; Bacon variance separation; Turing end-to-end bottleneck & solver fidelity) is present in its target `skills/*/SKILL.md` (`orwell`, `popper`, `shannon`, `euclid`, `bacon`, `turing`, `gauss`, `rebuttal`, `submission`, `da-vinci`, `layout`). Add any missing sentence to the owning `SKILL.md` before deleting it from `rules/AGENTS.md`.

3. **Keep Parity Across All Three Rule Sources:**
   - Update `rules/AGENTS.md`, copy byte-for-byte to `scifi/resources/AGENTS.md`, and update `DEFAULT_CANONICAL_RULES` in `scifi/setup_cli.py` to match.

---

### Pillar 3: MCP Server & 3-Tier Antigravity Routing *(Builder's Call)*

> **Decision made on user's behalf ("you decide if you have a really good reason"):**
> Keep the existing `@mcp.tool` endpoints in `scifi/server/routers/` rather than stripping half the server into shell-only CLI calls.
>
> **Reason:** Antigravity **already lazy-loads** all `scifi_*` MCP tool schemas (`Lazy:` list in `<mcp_servers>`, storing parameter schemas on disk and injecting them only when `call_mcp_tool` is needed). Keeping structured MCP tools costs minimal prompt tokens (~250 tokens for the tool index) while avoiding fragile Windows PowerShell quoting/escaping bugs on raw LaTeX equations, SymPy expressions, and BibTeX strings.

To optimize MCP usage specifically for Antigravity:
1. **Rich `FastMCP` Instructions (`scifi/server/app.py`):**
   Update `mcp = FastMCP("scifi", instructions=...)` with concise Antigravity routing guidance (surfaced via Antigravity's MCP `instructions.md` mechanism):
   - **Tier 1 — Native Subagents (`invoke_subagent`):** Delegate full-paper or multi-file tasks to `@scholar`, `@argus`, `@scribe`, `@theorist`, `@auditor`, or `@shannon` to isolate heavy reading/rewriting context.
   - **Tier 2 — Progressive Skills (`skills/<name>/SKILL.md`):** Read the domain `SKILL.md` before running multi-step workflows (`manuscript-audit`, `alex`, `orwell`, `turing`, `gauss`, `popper`, `hypatia`, `compiler`, `da-vinci`, `layout`, `euclid`, `bacon`, `rebuttal`, `submission`).
   - **Tier 3 — Structured MCP vs. Batch CLI:** Use `scifi_*` MCP tools for structured payloads (LaTeX snippets, SymPy math, BibTeX verification, Zotero SQLite/API, Zenodo depositions, Knowledge Graph queries) and `sf` CLI (`sf doctor`, `sf orwell`, `sf datasets inspect`, `sf compile`) for whole-workspace audits or large file inspection.
2. **Subagent Tool Alignment (`agents/*.md`):**
   - Clean up `agents/scribe.md` (and verify all 6 `agents/*.md` files) by dropping its legacy `tools:` YAML frontmatter list entirely—matching the other 5 `agents/*.md` files, which declare `name`, `description`, and `subagent: true` and inherit Antigravity's native tools cleanly—and replacing `replace_file_content` in its body text with `edit_file` / `write_file`.
   - Ensure subagent prompts align with Antigravity's `invoke_subagent` workflow (concise return receipts, direct in-place edits via `edit_file`).

---

### Pillar 4: Native Antigravity `hooks.json` & `plugin.json`

1. **Create Root `hooks.json`:**
   Place `hooks.json` at `<repo_root>/hooks.json` following Antigravity's native hook schema (where top-level keys are named hook blocks):
   - Note from `agy-customizations/docs/hooks.md`: `PostToolUse` expects `{}` on stdout and cannot inject text reminders into the model, whereas `PreToolUse` returns `{"decision": "allow"|"deny"|"ask"|"force_ask", "reason": "..."}`.
   - Ship `"scifi-dataset-guard"` on `PreToolUse` (`matcher: "read_file"`) with `"enabled": false` by default:
     ```json
     {
       "scifi-dataset-guard": {
         "enabled": false,
         "PreToolUse": [
           {
             "matcher": "read_file",
             "hooks": [
               {
                 "type": "command",
                 "command": "...",
                 "timeout": 10
               }
             ]
           }
         ]
       }
     }
     ```
   - *Builder's Call:* Keeping `"enabled": false` by default guarantees zero latency or process-spawn overhead on normal `read_file` edits while shipping a valid, opt-in native Antigravity hook template at the plugin root that users can toggle to `"enabled": true` when working on large raw datasets.
2. **Validate `plugin.json`:**
   - Keep `plugin.json` minimal and compliant with Antigravity's `plugins` schema (`name`, `displayName`, `version`, `description`, `logo`, `repository`, `suggestedPrompts`).

---

## 6. What's Left to the Builder

- Drafting the exact condensed prose of the 15 sections in `rules/AGENTS.md` (constraint: preserve all 15 `## N.` headers, keep `< 4,000` bytes, ensure zero lost rules by cross-checking against `skills/*/SKILL.md`).
- Choosing the exact cross-platform command/helper script for `"scifi-dataset-guard"` in `hooks.json` (returning `{"decision": "allow"}` or `{"decision": "deny", "reason": "..."}` on stdout).
- Updating affected tests and verifying CI compatibility:
  - `tests/test_cli.py` (Antigravity-only environment detection, workspace `.agents/mcp_config.json`, single-file `AGENTS.md` sync, and self-repo guard).
  - `tests/test_lifecycle.py::test_check_rules_sync_status` (update fixture from `CLAUDE.md` to `AGENTS.md`).
  - `tests/test_packaging.py::test_load_canonical_rules_from_packaged_resource` (update expected `^## \d+\.` section count from `12` to `15`, and remove `gemini-extension.json` / `commands/` expectations while asserting `hooks.json`).
  - `tests/test_server.py` (if `mcp.instructions` is checked).
  - Ensure `.github/workflows/ci.yml` (`uv run sf sync --dry-run` at repo root) continues exiting `0` when `sync_all_rules()` returns `[]` inside the `scifi` plugin repo, and verify the full `pytest` + `ruff` suite passes after edits.
