# Getting Started

## Installation

SciFi requires Python >= 3.12 and is optimized for the modern `uv` Python package manager.

### Using `uv` (Recommended)

```bash
# Clone the repository
git clone https://github.com/scifi-toolkit/scifi.git
cd scifi

# Install scifi and its dependencies
uv sync

# Run the health diagnostic
uv run sf doctor --env
```

---

## Configuring Google Antigravity & MCP

SciFi automatically detects and configures Google Antigravity with a single command:

```bash
uv run sf setup --auto
```

This registers the FastMCP server in:
- **Antigravity (Global)**: `~/.gemini/config/mcp_config.json`
- **Antigravity (Workspace)**: `.agents/mcp_config.json` (plus `AGENTS.md` via `sf setup --workspace` or `sf sync`)

Or install the repository directly as a native Antigravity plugin (`plugin.json`, `mcp_config.json`, `hooks.json`, `rules/AGENTS.md`, `skills/`, `agents/`).

### Manual MCP Server Configuration

If you prefer manual configuration, add the following to your AI client's MCP configuration file:

```json
{
  "mcpServers": {
    "scifi": {
      "command": "uv",
      "args": ["run", "python", "-m", "scifi.server"],
      "env": {
        "SCIFI_LITERATURE_DB_PATH": "~/.scifi/literature_store.db"
      }
    }
  }
}
```

---

## Quick Tour

### 1. Audit a LaTeX Manuscript
Run the comprehensive 6-stage manuscript doctor:
```bash
uv run sf doctor main.tex --venue ieee
```

### 2. Verify Citations & BibTeX
Cross-reference your bibliography against Crossref, OpenAlex, and arXiv:
```bash
uv run sf audit references.bib --autofix sanitized.bib
```

### 3. Check Symbolic Mathematics
Verify derivatives and calculus steps:
```bash
uv run sf math derivative "x**3 + 2*x" x "3*x**2 + 2"
uv run sf math step "sin(x)**2 + cos(x)**2" "1"
```

### 4. Launch the Web Cockpit
Start the interactive research cockpit:
```bash
uv run sf ui --port 8080
```
Then navigate to `http://localhost:8080` in your browser.
