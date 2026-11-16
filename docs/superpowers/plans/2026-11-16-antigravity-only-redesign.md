# Antigravity-Only Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip multi-IDE scaffolding from `scifi` and optimize rules, MCP routing, subagents, hooks, setup, and packaging exclusively for Google Antigravity.

**Architecture:** Replace 6+ IDE adapters and the 15.7 KB duplicated `AGENTS.md` rule file with a sub-4 KB invariant-only `rules/AGENTS.md`, a native root `hooks.json`, Antigravity-only setup/packaging (`~/.gemini/config/mcp_config.json` and `.agents/mcp_config.json`), and explicit 3-tier Antigravity routing (`agents/` -> `skills/` -> lazy `scifi_*` MCP / `sf` CLI).

**Tech Stack:** Python 3.12+, `uv`, FastMCP, `pytest`, `ruff`, Google Antigravity plugin specification.

**Spec:** [2026-11-16-antigravity-only-redesign-design.md](file:///c:/Users/Betagors/Code/scifi/docs/superpowers/specs/2026-11-16-antigravity-only-redesign-design.md)

## Global Constraints
- `rules/AGENTS.md` and `scifi/resources/AGENTS.md` must be `< 4,000` bytes and byte-for-byte identical.
- Preserve all 15 `## N.` section headings in canonical rules.
- `hooks.json` must sit directly at the plugin root (`<repo_root>/hooks.json`) with `"enabled": false` by default on `"scifi-dataset-guard"`.
- Never write root `AGENTS.md` inside the `scifi` plugin repository itself (prevent double-injection alongside `rules/AGENTS.md`).
- Never use `rg` (ripgrep).

---

## Tasks

- [x] **Task 1:** Save implementation plan at `docs/superpowers/plans/2026-11-16-antigravity-only-redesign.md`.
- [x] **Task 2:** Delete `.clinerules`, `.cursorrules`, `.windsurfrules`, `CLAUDE.md`, `.github/copilot-instructions.md`, `gemini-extension.json`, root `AGENTS.md`, and `commands/`; create native root `hooks.json` and `scifi/datasets/hook_guard.py`.
- [x] **Task 3:** Rewrite `rules/AGENTS.md` and `scifi/resources/AGENTS.md` to `< 4 KB` of always-on invariants + skill/subagent routing pointers while maintaining byte parity across all 15 sections.
- [x] **Task 4:** Refactor `scifi/setup_cli.py`, `scifi/packaging.py`, `scifi/cli.py`, `scifi/server/app.py`, and `agents/scribe.md` for Antigravity-only discovery, self-repo rule guard, bundle verification, 3-tier MCP routing, and native agent tools.
- [x] **Task 5:** Update `tests/test_packaging.py`, `tests/test_lifecycle.py`, `tests/test_cli.py`, and docs (`README.md`, `CONTRIBUTING.md`, `docs/getting-started.md`, `docs/cli-reference.md`, `docs/index.md`), then run `pytest` and `ruff check`.
