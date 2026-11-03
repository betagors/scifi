# Cross-AI Tools Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand SciFi's setup installer and rule syncing to support all major AI coding tools (OpenCode, Claude Code, VS Code with Cline & Roo Code, Cursor, Windsurf, Antigravity, and GitHub Copilot), non-destructively sync scientific rules, update documentation, and integrate the worktree.

**Architecture:** 
1. Enhance `scifi.setup_cli` to detect and configure MCP client settings across 9 distinct environments, using a specialized schema adapter for OpenCode (`"mcp"` format) and standard `"mcpServers"` format for all others.
2. Introduce a non-destructive, marker-bounded rule synchronization engine (`sync_rule_file`) that updates or appends `rules/AGENTS.md` invariants into `CLAUDE.md`, `.clinerules`, `.cursorrules`, `AGENTS.md`, `.windsurfrules`, and `.github/copilot-instructions.md`.
3. Wire new flags (`--rules`, `--workspace`, `--list`, `--all-rules`) into `scifi.setup_cli` and add the `sf sync` alias to `scifi.cli`.
4. Validate with thorough unit tests in `tests/test_cli.py`, update `README.md`, run the full test suite, and merge the worktree into main.

**Tech Stack:** Python 3.12+, `pytest`, `pathlib`, `json`, `tempfile`, Git.

**Spec:** `docs/superpowers/specs/2026-11-03-cross-ai-tools-support-design.md`

## Global Constraints

- Python version: Python >= 3.12, strict type annotations.
- Dependency Invariant: Standard library only for setup and syncing (`pathlib`, `json`, `tempfile`, `sys`, `os`, `shutil`).
- Anti-Goal: Never overwrite existing user instructions without delimited marker bounds (`<!-- SCIFI-RULES:START -->` ... `<!-- SCIFI-RULES:END -->`).
- Atomic Writes: All file modifications must use temporary file creation and atomic replacement to prevent file corruption.

## Review Focus

1. **OpenCode schema format mismatch**: If OpenCode config contains `mcpServers` instead of `"mcp": {"scifi": {"type": "local", "command": [...]}}`, OpenCode fails to load tools. Tested in Task 1.
2. **User custom instruction loss**: If an existing `CLAUDE.md` has custom directives and lacks SciFi markers, SciFi rules must append without replacing or deleting the existing content. Tested in Task 2.
3. **Repeated idempotency runs**: Running `sf sync` or `sf setup --rules` multiple times must not duplicate rule blocks or corrupt the marker boundaries. Tested in Task 2.
4. **Platform path resolution across Windows/macOS/Linux**: VS Code globalStorage and Claude desktop config paths must resolve correctly across OS platforms without raising exceptions. Tested in Task 1.
5. **Execution command detection**: When running from source repo, emit `uv run python -m scifi.server` with `cwd`; when running installed package, emit `sf server` without requiring a source `cwd`. Tested in Task 1.

---

### Task 1: Multi-Environment Detection & OpenCode Schema Adapter in `scifi/setup_cli.py`

**Files:**
- Modify: `scifi/setup_cli.py`
- Test: `tests/test_cli.py`

- [ ] Write failing unit tests in `tests/test_cli.py` for:
  - Detecting OpenCode (global `~/.config/opencode/opencode.json` and local `opencode.json`) with native `"mcp"` schema.
  - Detecting Claude Code global (`~/.claude.json`) and workspace (`.mcp.json`).
  - Detecting VS Code Cline (`saoudrizwan.claude-dev`) and Roo Code (`rooveterinaryinc.roo-cline`) in `globalStorage`.
  - Detecting Windsurf (`~/.codeium/windsurf/mcp_config.json`).
  - Correct schema formatting for standard tools vs OpenCode.
- [ ] Run `uv run pytest tests/test_cli.py -k "setup"` to confirm test failure.
- [ ] Implement expanded `detect_environments` and OpenCode schema serialization in `scifi/setup_cli.py`:
  - Add `format_type` field to `TargetEnvironment` (`"standard"` vs `"opencode"`).
  - Add path resolution helpers for VS Code globalStorage (`saoudrizwan.claude-dev`, `rooveterinaryinc.roo-cline`), Claude Code, OpenCode, and Windsurf across Windows, macOS, and Linux.
  - Update `install_mcp_config` to format OpenCode config using `"mcp": {"scifi": {"type": "local", "command": [...]}}` while preserving any existing `"mcp"` entries.
  - Add `--list` CLI display to print all detected vs undetected environments with their statuses.
- [ ] Run `uv run pytest tests/test_cli.py` to confirm all setup detection tests pass.
- [ ] Git commit: `feat(setup): add multi-environment detection and OpenCode schema adapter`.

---

### Task 2: Marker-Bounded Rule Synchronization Engine

**Files:**
- Modify: `scifi/setup_cli.py`
- Modify: `scifi/cli.py`
- Test: `tests/test_cli.py`

- [ ] Write failing unit tests in `tests/test_cli.py` for:
  - `sync_rule_file` creating new file with `<!-- SCIFI-RULES:START -->` and `<!-- SCIFI-RULES:END -->`.
  - `sync_rule_file` appending marker block to an existing file with existing user instructions.
  - `sync_rule_file` updating existing marker block idempotently without duplicating or touching outside text.
  - `sync_all_rules` syncing to `CLAUDE.md`, `.clinerules`, `.cursorrules`, `AGENTS.md`, `.windsurfrules`, `.github/copilot-instructions.md`.
  - CLI command `sf sync` and `sf setup --rules` and `sf setup --workspace`.
- [ ] Run `uv run pytest tests/test_cli.py -k "rule or sync"` to confirm tests fail.
- [ ] Implement rule synchronization in `scifi/setup_cli.py`:
  - `load_canonical_rules(project_root)`: reads `rules/AGENTS.md` from project root or falls back to package bundled rules.
  - `sync_rule_file(target_path, rule_content, dry_run=False)`: marker-bounded replacement/append with atomic writes.
  - `sync_all_rules(project_root, detected_tools_only=False, dry_run=False)`: syncs to target rule files.
  - Add `--rules`, `--workspace`, and `--all-rules` argument handlers in `cmd_setup`.
- [ ] Register `sync` command in `scifi/cli.py`:
  - Add `sync` subparser mapped to `cmd_sync` (which forwards to `sync_all_rules`).
- [ ] Run `uv run pytest tests/test_cli.py` to confirm all rule sync and CLI tests pass.
- [ ] Git commit: `feat(cli): implement marker-bounded rule synchronization engine and sf sync alias`.

---

### Task 3: Workspace Manifest Generation & Pre-Populated Rule Templates

**Files:**
- Create: `CLAUDE.md` (root link/marker for Claude Code)
- Create: `.clinerules` (root link/marker for Cline / Roo Code)
- Create: `.cursorrules` (root link/marker for Cursor)
- Create: `AGENTS.md` (root link/marker for OpenCode / universal agents)
- Modify: `scifi/setup_cli.py`
- Test: `tests/test_cli.py`

- [ ] Generate repository root instruction files using the newly implemented `sf sync` engine so anyone cloning the repo immediately benefits from SciFi rules in Claude Code, Cline, Roo Code, OpenCode, and Cursor.
- [ ] Verify that running `sf sync` again produces identical results (idempotency check).
- [ ] Write integration test verifying that `sf setup --workspace` creates `.mcp.json`, `.cursor/mcp.json`, `opencode.json`, and rule files in a temporary workspace.
- [ ] Run `uv run pytest tests/test_cli.py` to verify passing.
- [ ] Git commit: `feat(repo): generate universal root rule files and workspace manifest tests`.

---

### Task 4: Documentation & README Updates

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-11-03-cross-ai-tools-support-design.md`
- Test: `tests/test_cli.py`

- [ ] Update `README.md`:
  - Update badges and tool listings to explicitly mention OpenCode, Claude Code, VS Code (Cline & Roo Code), Cursor, Windsurf, and Antigravity.
  - Document `uv run sf setup --auto` (global registration across all detected AI tools).
  - Document `uv run sf setup --workspace` (local workspace MCP manifests).
  - Document `uv run sf sync` (syncing scientific invariants to `CLAUDE.md`, `.clinerules`, `.cursorrules`, etc.).
  - Document `uv run sf setup --list` to inspect detected environments.
- [ ] Run full test suite: `uv run pytest`.
- [ ] Git commit: `docs(readme): document universal AI coding tool support and sync command`.

---

### Task 5: Final Verification & Branch Integration / Merge

**Files:**
- Repository root & Git branches

- [ ] Run full test suite across the entire project (`uv run pytest`) and ensure all 168+ tests pass.
- [ ] Check git status and ensure working tree is clean.
- [ ] Switch to main branch, merge `support_all_ai_tools`, and verify everything is cleanly integrated.
