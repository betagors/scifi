# Cross-AI Tools Support Design Document

**Date:** 2026-11-03  
**Status:** In Review (Post Builder Check)  
**Topic:** Universal AI Coding Tools Support (OpenCode, Claude Code, VS Code / Cline / Roo Code, Cursor, Windsurf, Antigravity)

---

## 1. Intent & The Why

SciFi is a scientific research and academic writing toolkit built to transform AI coding agents into rigorous, peer-review-grade research partners. Currently, SciFi is primarily packaged as an Antigravity plugin with a FastMCP server and a setup installer (`sf setup` / `scifi setup`) that only checks Antigravity, Claude Desktop, and Cursor workspace files.

Modern researchers and developers write LaTeX papers and computational science code across multiple AI assistants:
- **Claude Code CLI** in the terminal
- **VS Code** with autonomous agent extensions like **Cline** and **Roo Code**
- **OpenCode** CLI / environment
- **Cursor** and **Windsurf** AI editors
- **GitHub Copilot** in VS Code
- **Antigravity** / Gemini CLI

To make SciFi universally accessible regardless of the researcher's preferred AI assistant, SciFi must provide seamless auto-discovery, MCP registration, and scientific rule synchronization across all these tools without forcing manual configuration.

---

## 2. Goals, Non-Goals, and Anti-Goals

### Goals
1. **Multi-Environment MCP Discovery & Registration**:
   - Detect and register SciFi's FastMCP server across all target environments:
     - **OpenCode**: `~/.config/opencode/opencode.json` and workspace `opencode.json` (using OpenCode's native `"mcp"` schema adapter)
     - **Claude Code CLI**: `~/.claude.json` (global user storage) and repository `.mcp.json`
     - **VS Code Cline**: Extension global storage `cline_mcp_settings.json` (`saoudrizwan.claude-dev`) across Windows, macOS, and Linux
     - **VS Code Roo Code**: Extension global storage `cline_mcp_settings.json` (`rooveterinaryinc.roo-cline`) across Windows, macOS, and Linux
     - **Cursor**: Workspace `.cursor/mcp.json`
     - **Windsurf**: `~/.codeium/windsurf/mcp_config.json`
     - **Claude Desktop**: Standard desktop configs across Windows, macOS, and Linux
     - **Antigravity**: `~/.gemini/config/mcp_config.json`
2. **Atomic & Non-Destructive Configuration**:
   - Safely update existing JSON configuration files, preserving existing servers, keys, and indentation.
   - Use atomic writes (temp file + replace) to prevent corruption.
3. **Scientific Invariants & Rule Synchronization**:
   - Support syncing SciFi's core standards (`rules/AGENTS.md`) into tool-specific instruction files:
     - `CLAUDE.md` (for Claude Code CLI / Claude Desktop)
     - `.clinerules` (for Cline & Roo Code)
     - `.cursorrules` (for Cursor)
     - `AGENTS.md` (at repo root for OpenCode and generic agents)
     - `.github/copilot-instructions.md` (for GitHub Copilot)
     - `.windsurfrules` (for Windsurf)
   - Preserve existing user content using delimited marker blocks (`<!-- SCIFI-RULES:START -->` ... `<!-- SCIFI-RULES:END -->`).
4. **Two-Tier Setup CLI Experience (`sf setup`)**:
   - `sf setup --auto`: Global auto-discovery and registration for all detected tools.
   - `sf setup --workspace`: Local workspace manifest creation (`.cursor/mcp.json`, `.mcp.json`, `opencode.json`).
   - `sf setup --rules` (and alias `sf sync`): Syncs/exports rule files to the current workspace root.
   - `sf setup --list`: Displays all supported tools, detection status, and installation paths.
   - `sf setup --dry-run`: Non-destructive preview.
5. **Comprehensive Verification & Documentation**:
   - Expand unit and integration test suite to cover all new environment paths, OpenCode schema adaptation, and rule syncing logic.
   - Update README and command references to reflect universal tool support.

### Non-Goals
- Modifying closed-source extension binaries or injecting code into running extension processes.
- Forcing users to install tools they do not use (only detected environments are configured during `--auto`).
- Re-implementing MCP protocol parsers; existing FastMCP server over stdio remains the single unified backend.

### Anti-Goals
- Overwriting user custom instructions in `CLAUDE.md`, `.cursorrules`, or `.clinerules` without clear delimited markers.
- Breaking backward compatibility with Antigravity plugin conventions or the existing `sf` CLI commands.

---

## 3. Constraints

- **Cross-Platform Path Resolution**:
  - Windows: `%APPDATA%`, `%USERPROFILE%`
  - macOS: `~/Library/Application Support/`
  - Linux: `~/.config/`
- **Python Version**: Python >= 3.12, strict type annotations.
- **Dependency Invariant**: No new external dependencies; use Python standard library (`pathlib`, `json`, `tempfile`, `sys`, `os`, `shutil`) for setup and syncing.

---

## 4. Approaches Considered

1. **Option 1: Universal Auto-Installer with Implicit Rule Syncing**
   - Automatically modifies both global app settings and local workspace rule files on every `--auto` run.
   - *Trade-off*: Can clutter repositories with multiple rule files when a user only wanted global MCP registration.
2. **Option 2: Workspace Manifests Only**
   - Only creates files inside the current working directory (`.cursor/`, `.mcp.json`, etc.).
   - *Trade-off*: Fails to make SciFi tools globally accessible across multiple projects for tools like Claude Code or Cline.
3. **Option 3: Hybrid Two-Tier Installer (Chosen Approach)**
   - Clear separation:
     - Global tier: Registers the FastMCP server in tool config files so agents have the tools everywhere.
     - Workspace tier (`--workspace` / `--rules` / `sf sync`): Syncs instructions and repository-local configurations on demand.
   - Selected by the user for flexibility and complete coverage across both global agents and team workspaces.

---

## 5. Architectural & Implementation Details (Settled Builder Decisions)

### 5.1 Environment Detection Specs & Schemas

| Environment | Scope | Path Resolution | Config Schema |
|---|---|---|---|
| **Antigravity** | Global | `~/.gemini/config/mcp_config.json` | Standard `{"mcpServers": {"scifi": ...}}` |
| **Claude Desktop** | Global | Win: `%APPDATA%/Claude/claude_desktop_config.json`<br>Mac: `~/Library/Application Support/Claude/...`<br>Linux: `~/.config/Claude/...` | Standard `{"mcpServers": {"scifi": ...}}` |
| **Claude Code (Global)** | Global | `~/.claude.json` | Standard `{"mcpServers": {"scifi": ...}}` |
| **Claude Code (Workspace)** | Local | Repository `.mcp.json` | Standard `{"mcpServers": {"scifi": ...}}` |
| **Cursor** | Local | Workspace `.cursor/mcp.json` | Standard `{"mcpServers": {"scifi": ...}}` |
| **VS Code Cline** | Global | Win: `%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`<br>Mac: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/...`<br>Linux: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/...` | Standard `{"mcpServers": {"scifi": ...}}` |
| **VS Code Roo Code** | Global | Win: `%APPDATA%/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`<br>Mac: `~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/...`<br>Linux: `~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/...` | Standard `{"mcpServers": {"scifi": ...}}` |
| **OpenCode** | Global / Local | Global: `~/.config/opencode/opencode.json`<br>Local: `opencode.json` | Native OpenCode schema:<br>`{"mcp": {"scifi": {"type": "local", "command": [...]}}}` |
| **Windsurf** | Global | `~/.codeium/windsurf/mcp_config.json` | Standard `{"mcpServers": {"scifi": ...}}` |

### 5.2 Server Entry Execution Resolution
- **Source Checkout Mode**: When running within a clone of SciFi repository:
  ```json
  {
    "command": "uv",
    "args": ["run", "python", "-m", "scifi.server"],
    "cwd": "<ABSOLUTE_PATH_TO_SCIFI_ROOT>"
  }
  ```
- **Installed Package Mode**: When running from an installed CLI binary (`sf` or `scifi` on PATH):
  ```json
  {
    "command": "sf",
    "args": ["server"]
  }
  ```
- **OpenCode Adapter Format**:
  In OpenCode, arguments are flattened into a single list in `"command"` and `"type": "local"` is added.

### 5.3 Non-Destructive Rule Synchronization
- Delimited marker block:
  ```markdown
  <!-- SCIFI-RULES:START -->
  <!-- Generated by SciFi (sf setup --rules). Do not edit between markers; edit rules/AGENTS.md -->
  <SciFi Rules Content>
  <!-- SCIFI-RULES:END -->
  ```
- If the target file exists:
  - If markers exist: replace only content between the markers.
  - If no markers exist: append the marker block to the end of the file, preserving existing user rules and comments.
- If target file does not exist: create the file with the marker block.
- Canonical source fallback:
  - If running in SciFi repo: read `rules/AGENTS.md`.
  - If running in external user repo: read packaged default rules via package resources (`importlib.resources`).

### 5.4 Detection Heuristics for Unconfigured / Fresh Installs
- A tool is detected as present if:
  1. The target config file exists, OR
  2. The parent application directory exists (e.g. `~/.gemini`, `~/.claude`, `%APPDATA%/Code/User/globalStorage/saoudrizwan.claude-dev`, `~/.codeium/windsurf`, `.cursor/`), OR
  3. The tool's CLI binary is found on system PATH (`claude`, `opencode`).

---

## 6. What's Left to the Builder (Settled Decisions)

- Implemented in `scifi/setup_cli.py`:
  - `detect_environments()` updated with all 9 targets (Antigravity, Claude Desktop, Claude Code Global, Claude Code Workspace, Cursor, Cline, Roo Code, OpenCode Global, Windsurf).
  - OpenCode-specific JSON serializer adapter.
  - Marker-based rule injector function `sync_rule_file(target_path, rule_content)`.
  - `sync_all_rules(project_root, detected_tools_only=True)`.
  - CLI parser flags: `--rules`, `--workspace`, `--list`, `--all-rules`.
- Implemented in `scifi/cli.py`:
  - Register `sync` as a top-level command shortcut for `sf setup --rules`.
