# SciFi Production Release & Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a robust dual-channel release and packaging pipeline for SciFi v1.0.0, fixing site-packages namespace pollution, embedding canonical academic rules into packaged resources, providing an automated `sf package` plugin bundler, enabling zero-install `uvx scifi server` MCP client configuration, and automating CI/CD PyPI + GitHub Releases.

**Architecture:**
- **Dual-Channel Distribution**:
  1. *PyPI Python Package*: Clean wheel and source distribution containing only `scifi` and its packaged resources (`scifi.resources`), preventing rogue `site-packages/skills` namespace collisions. Dynamic versioning via `scifi/__init__.py`.
  2. *AI Agent Plugin Bundle*: Standalone `scifi-plugin-vX.Y.Z.zip` packaging `plugin.json`, `gemini-extension.json`, `skills/`, `agents/`, `commands/`, `rules/`, `assets/`, and `mcp_config.json` for Antigravity, Claude Code, Cursor, Windsurf, Cline, and Gemini CLI.
- **Embedded Package Resources**: Ship canonical `AGENTS.md` inside `scifi/resources/` via package data so `sf setup --rules` and `sf sync` deliver the complete 12 academic rules even in pip/wheel installations without repository source checkouts.
- **MCP Client Zero-Install Ergonomics**: Enhance `sf setup` to emit `uvx scifi server` as the preferred global client configuration outside of source repositories.
- **Automated CI/CD**: Matrix testing (Python 3.12 & 3.13), build verification, and tag-triggered GitHub Actions release workflow publishing wheels to PyPI via OIDC Trusted Publishing and attaching the plugin zip to GitHub Releases.

**Tech Stack:** Python >= 3.12, Hatchling (`hatchling.build`), Astral `uv`, GitHub Actions (OIDC Trusted Publishing), `zipfile`, `hashlib`, Pytest.

**Spec:** [docs/superpowers/specs/2026-11-10-release-and-packaging-design.md](file:///c:/Users/Betagors/Code/scifi/docs/superpowers/specs/2026-11-10-release-and-packaging-design.md)

## Global Constraints
- **Zero Namespace Pollution**: Wheels must never install a top-level `skills/` module into `site-packages/`. Only `scifi` (and its subpackages/resources) may be installed.
- **Zero Rule Degradation**: In a wheel/pip installation, `load_canonical_rules()` must return the full 12 academic rules from packaged resources, never dropping down to an outdated 4-rule stub.
- **Single Source of Version Truth**: `scifi/__init__.py::__version__` is the primary version source. Hatchling dynamic versioning reads directly from this attribute, and tests must verify consistency across `plugin.json` and `gemini-extension.json`.
- **Zero-Crash Packaging**: `sf package` must run offline (no mandatory network access required to build local archives).
- **Security & Integrity**: GitHub Actions publishing to PyPI must use OIDC Trusted Publishing without static credentials or secrets.

## Review Focus
1. **Site-packages collision**: Verify `python -m zipfile -l dist/*.whl` contains no entries starting with `skills/` directly at the root.
2. **Pip-installed rule sync**: Verify `load_canonical_rules()` returns all 12 rules even when simulating an installed environment with no repository `rules/` folder in cwd or parents.
3. **Version drift**: Verify a test fails if `plugin.json` or `gemini-extension.json` version does not match `scifi.__version__`.
4. **Plugin zip structure**: Verify `dist/scifi-plugin-v*.zip` contains all 17 skills, 6 agents, commands, rules, and `plugin.json` at top-level of the zip archive.
5. **Setup MCP command**: Verify `sf setup` correctly emits `"command": "uvx", "args": ["scifi", "server"]` when invoked with `--use-uvx` or in non-source mode.

---

### Task 1: Clean Wheel Packaging, Embedded Resources & Version Synchronization

**Files:**
- Create: `scifi/resources/__init__.py`
- Create: `scifi/resources/AGENTS.md` (copied/synced from `rules/AGENTS.md`)
- Modify: `pyproject.toml`
- Modify: `scifi/setup_cli.py:22-75`
- Test: `tests/test_packaging.py`

**Interfaces:**
- Consumes: `importlib.resources`, `pathlib.Path`
- Produces: `scifi.setup_cli.load_canonical_rules(project_root=None) -> str` (now checking `scifi.resources`), dynamic Hatchling versioning in `pyproject.toml`.

- [ ] **Step 1: Write the failing tests in `tests/test_packaging.py`**

```python
# tests/test_packaging.py
import json
import re
from pathlib import Path
import pytest
import scifi
from scifi.setup_cli import load_canonical_rules

def test_version_consistency():
    """Verify all manifests share the exact same version string."""
    root = Path(__file__).resolve().parent.parent
    py_version = scifi.__version__
    
    plugin_path = root / "plugin.json"
    if plugin_path.exists():
        data = json.loads(plugin_path.read_text(encoding="utf-8"))
        assert data.get("version") == py_version, f"plugin.json version {data.get('version')} != {py_version}"
        
    gemini_path = root / "gemini-extension.json"
    if gemini_path.exists():
        data = json.loads(gemini_path.read_text(encoding="utf-8"))
        assert data.get("version") == py_version, f"gemini-extension.json version {data.get('version')} != {py_version}"

def test_load_canonical_rules_from_packaged_resource(monkeypatch, tmp_path):
    """Verify load_canonical_rules loads all 12 rules even without a repo root."""
    # Force cwd to an empty directory with no rules/
    monkeypatch.chdir(tmp_path)
    rules_text = load_canonical_rules(project_root=tmp_path)
    assert "## 12. Academic Paper Packaging & Submission Suite" in rules_text
    assert "Master Academic Humanizer Protocol" in rules_text
    # Verify it is not the 4-rule stub
    assert len(re.findall(r"^## \d+\.", rules_text, flags=re.MULTILINE)) == 12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_packaging.py -v`
Expected: FAIL (empty tmp_path returns 4-rule stub).

- [ ] **Step 3: Embed canonical rules in `scifi/resources/` and update `load_canonical_rules`**

1. Create `scifi/resources/__init__.py` and copy `rules/AGENTS.md` to `scifi/resources/AGENTS.md`.
2. Update `DEFAULT_CANONICAL_RULES` in `scifi/setup_cli.py` to contain the full 12-rule text as a true fallback.
3. In `load_canonical_rules()`, import via `importlib.resources.files("scifi.resources").joinpath("AGENTS.md")`.

- [ ] **Step 4: Update `pyproject.toml` for Hatchling wheel targets and dynamic versioning**

1. Set `[project]` dynamic version: `dynamic = ["version"]`.
2. Configure `[tool.hatch.version]` with `path = "scifi/__init__.py"`.
3. Configure `[tool.hatch.build.targets.wheel]` with `packages = ["scifi"]` (removing `skills`).
4. Include `scifi/resources/*` in wheel target.

- [ ] **Step 5: Run tests and verify wheel contents**

Run: `uv run pytest tests/test_packaging.py -v`
Run: `uv build`
Run: `uv run python -m zipfile -l dist/scifi-1.0.0-py3-none-any.whl` (verify NO `skills/` at root, and `scifi/resources/AGENTS.md` exists).
Expected: PASS.

- [ ] **Step 6: Commit changes**

```bash
git add pyproject.toml scifi/resources/ scifi/setup_cli.py tests/test_packaging.py
git commit -m "fix(packaging): isolate scifi package namespace, embed AGENTS.md resource, and sync dynamic versioning"
```

---

### Task 2: Standalone AI Agent Plugin Bundler (`sf package`)

**Files:**
- Create: `scifi/packaging.py`
- Modify: `scifi/cli.py` (add `package` command / alias `bundle`)
- Modify: `tests/test_packaging.py`

**Interfaces:**
- Consumes: `scifi.__version__`, `pathlib.Path`, `zipfile`, `subprocess` (for `uv build`)
- Produces: `scifi.packaging.build_plugin_bundle(repo_root: Path, output_dir: Path) -> Path`, `scifi.packaging.build_all_artifacts(repo_root: Path, output_dir: Path) -> dict[str, list[Path]]`.

- [ ] **Step 1: Write failing test in `tests/test_packaging.py`**

```python
# tests/test_packaging.py (continued)
from scifi.packaging import build_plugin_bundle, verify_plugin_bundle
import zipfile

def test_build_plugin_bundle(tmp_path):
    root = Path(__file__).resolve().parent.parent
    bundle_zip = build_plugin_bundle(repo_root=root, output_dir=tmp_path)
    assert bundle_zip.exists()
    assert bundle_zip.name.startswith("scifi-plugin-v")
    assert bundle_zip.name.endswith(".zip")
    
    with zipfile.ZipFile(bundle_zip, "r") as zf:
        namelist = zf.namelist()
        assert "plugin.json" in namelist
        assert "rules/AGENTS.md" in namelist
        assert "skills/alex/SKILL.md" in namelist
        assert "skills/shannon/SKILL.md" in namelist
        assert "agents/argus.md" in namelist
        assert "assets/logo.svg" in namelist
        assert "gemini-extension.json" in namelist
        
    validation = verify_plugin_bundle(bundle_zip)
    assert validation["valid"] is True
    assert validation["skills_count"] >= 17
    assert validation["agents_count"] >= 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_packaging.py::test_build_plugin_bundle -v`
Expected: FAIL (module `scifi.packaging` not found).

- [ ] **Step 3: Implement `scifi/packaging.py`**

Implement:
1. `build_plugin_bundle(repo_root: Path, output_dir: Path) -> Path`:
   - Reads `plugin.json` to verify name and version.
   - Archives `plugin.json`, `gemini-extension.json`, `mcp_config.json`, `rules/`, `skills/`, `agents/`, `commands/`, `assets/`, `LICENSE`, `README.md`.
   - Generates SHA256 checksum file alongside the zip.
2. `verify_plugin_bundle(bundle_path: Path) -> dict[str, Any]`:
   - Checks presence and structure of required manifest files and skill descriptors (`SKILL.md`).
3. `build_python_distributions(repo_root: Path, output_dir: Path) -> list[Path]`:
   - Invokes `uv build` or Python's `build` to generate `.whl` and `.tar.gz`.
4. `cmd_package(args: argparse.Namespace) -> int`:
   - CLI runner for `sf package [--plugin-only] [--python-only] [--dist-dir DIR]`.

- [ ] **Step 4: Register `p_package` in `scifi/cli.py`**

Add `package` subcommand (alias `bundle`) with flags:
- `--plugin-only`: Build only `scifi-plugin-v*.zip`.
- `--python-only`: Build only wheel and sdist.
- `--output-dir`, `-o`: Output directory (default: `dist`).

- [ ] **Step 5: Run tests and CLI verification**

Run: `uv run pytest tests/test_packaging.py -v`
Run: `uv run sf package --help`
Run: `uv run sf package --plugin-only --output-dir dist`
Expected: Successfully generates `dist/scifi-plugin-v1.0.0.zip` and checksum file.

- [ ] **Step 6: Commit changes**

```bash
git add scifi/packaging.py scifi/cli.py tests/test_packaging.py
git commit -m "feat(cli): add 'sf package' command for automated AI agent plugin bundling"
```

---

### Task 3: MCP Client Configuration with Zero-Install `uvx` Support

**Files:**
- Modify: `scifi/setup_cli.py:500-530`
- Modify: `scifi/cli.py` (add `--use-uvx` flag to `setup`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `scifi.setup_cli.install_server_config`, `scifi.setup_cli.detect_environments`
- Produces: Updated server JSON configurations with `uvx scifi server` when requested or outside source trees.

- [ ] **Step 1: Write test for `uvx` MCP entry generation in `tests/test_cli.py`**

```python
# tests/test_cli.py
from scifi.setup_cli import install_server_config

def test_install_server_config_uvx_mode(tmp_path):
    target_config = tmp_path / "claude_desktop_config.json"
    success = install_server_config(
        target_path=target_config,
        format_type="standard",
        scifi_root=None,
        use_uvx=True,
    )
    assert success is True
    data = json.loads(target_config.read_text(encoding="utf-8"))
    server = data["mcpServers"]["scifi"]
    assert server["command"] == "uvx"
    assert server["args"] == ["scifi", "server"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -k test_install_server_config_uvx_mode -v`
Expected: FAIL (`use_uvx` unexpected argument).

- [ ] **Step 3: Update `install_server_config` in `scifi/setup_cli.py`**

Add `use_uvx: bool = False` argument:
- When `use_uvx=True`:
  - Standard format: `{"command": "uvx", "args": ["scifi", "server"]}`
  - OpenCode format: `{"type": "local", "command": ["uvx", "scifi", "server"]}`
- Wire `--use-uvx` into `p_setup` in `scifi/cli.py` and pass through to `install_server_config`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_cli.py -k test_install_server_config -v`
Expected: PASS.

- [ ] **Step 5: Commit changes**

```bash
git add scifi/setup_cli.py scifi/cli.py tests/test_cli.py
git commit -m "feat(setup): support zero-install 'uvx scifi server' MCP configuration"
```

---

### Task 4: GitHub Actions CI Matrix & Automated Release Pipeline

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `.github/workflows/ci.yml`
- Create: `CHANGELOG.md`
- Test: Verify local workflow schema & commands.

**Interfaces:**
- Consumes: GitHub Actions runner, PyPI Trusted Publishing (OIDC), `uv run sf package`.
- Produces: Tag-driven releases on GitHub and PyPI.

- [ ] **Step 1: Enhance `.github/workflows/ci.yml`**

1. Expand Python version matrix to `["3.12", "3.13"]`.
2. Add build verification step:
   ```yaml
   - name: Verify package build and plugin bundling
     run: |
       uv run sf package --output-dir dist_test
       uv run python -m zipfile -l dist_test/scifi-plugin-*.zip
   ```
3. Add twine/packaging verification check.

- [ ] **Step 2: Create `.github/workflows/release.yml`**

Configure:
- Trigger: `push: tags: ['v*.*.*']`
- Permissions: `id-token: write` (for OIDC), `contents: write` (for GitHub Releases).
- Steps:
  1. `actions/checkout@v4` with `fetch-depth: 0`.
  2. Setup `uv` via `astral-sh/setup-uv@v4`.
  3. Install dependencies and build all artifacts (`uv run sf package --output-dir dist`).
  4. Publish to PyPI via `pypa/gh-action-pypi-publish@release/v1` (with `packages-dir: dist/` matching `*.whl` and `*.tar.gz`).
  5. Create GitHub Release via `softprops/action-gh-release@v2`:
     - Attach `dist/*.whl`, `dist/*.tar.gz`, `dist/scifi-plugin-*.zip`, `dist/*.sha256`.
     - Generate automatic changelog / release notes.

- [ ] **Step 3: Create initial `CHANGELOG.md`**

Document SciFi 1.0.0 features:
- Core academic skills (Alex citation verification, Argus attribution sentinel, Shannon SEO & title engineering, Human prose de-biasing, Turing symbolic math).
- FastMCP server integration across Claude Desktop, Cursor, Antigravity, OpenCode, Windsurf, and VS Code.
- Local Zotero 10 integration, project scaffolding (`sf init`), and 2-pillar architecture.
- Web Cockpit UI (`sf ui`).
- Packaging & release suite (`sf package`, `uvx` support, standalone plugin bundle).

- [ ] **Step 4: Run local verification of CI commands**

Run: `uv run sf package --output-dir dist`
Run: `uv run pytest tests/test_packaging.py tests/test_cli.py -v`
Expected: Clean pass with zero errors.

- [ ] **Step 5: Commit changes**

```bash
git add .github/workflows/ ci.yml release.yml CHANGELOG.md
git commit -m "ci: add tag-triggered PyPI OIDC release workflow and Python 3.13 CI matrix"
```

---

### Task 5: End-to-End Release Dry-Run & Verification Gate

**Files:**
- Test: All suites (`tests/`)

- [ ] **Step 1: Run complete test suite**

Run: `uv run pytest tests/ -v`
Expected: 100% pass across all tests.

- [ ] **Step 2: Inspect built artifacts**

Run: `uv run sf package --output-dir dist`
Verify:
1. `dist/scifi-1.0.0-py3-none-any.whl` contains no top-level `skills/`.
2. `dist/scifi-plugin-v1.0.0.zip` contains all 17 skills and manifests.
3. Checksums are created in `dist/`.

- [ ] **Step 3: Verification command outputs**

Confirm:
- `uv run sf --help` includes `package`.
- `uv run sf package --help` displays correct flags.
- `git status` clean.
