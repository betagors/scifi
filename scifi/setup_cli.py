"""
Automated Setup Installer for SciFi FastMCP Server.

Detects AI environments (Google Antigravity, Claude Desktop, and Cursor)
and installs the `scifi` FastMCP server definition into their respective
mcp configuration files.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.resources
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any


SCIFI_RULE_MARKER_START = "<!-- SCIFI-RULES:START -->"
SCIFI_RULE_MARKER_END = "<!-- SCIFI-RULES:END -->"

DEFAULT_CANONICAL_RULES = """# SciFi Academic & Scientific Writing Rules

These rules are active whenever the SciFi plugin is enabled to enforce academic standards across literature verification, mathematical rigor, peer review readiness, and LaTeX manuscript typesetting.

## 1. Citation & Bibliographic Integrity
- **Zero Hallucination:** Never fabricate or guess academic citations, DOIs, author names, venues, or publication dates.
- **Mandatory Verification:** Use the `alex` skill to cross-reference DOIs, literature links, and `.bib` entries against authoritative registries (Crossref, OpenAlex, arXiv, DataCite).
- **Attribution & Plagiarism Audit:** Use the `argus` skill to detect uncredited algorithms, models, and techniques, audit attribution gaps, and triage scientific literature from informal web articles.
- **Retraction & Errata Vigilance:** Actively flag retracted papers, publisher expressions of concern, or errata when auditing bibliographies.
- **Standard Formatting:** Output verified entries with consistent BibTeX keys (`[Author][Year][Word]`) or APA 7th edition formatting.

## 2. Academic Prose & LaTeX Source Humanization
- **Master Academic Humanizer Protocol:** Use the `human` skill (`sf human` / `scifi_audit_human`) to eradicate synthetic AI writing hallmarks, buzzwords, marketing fluff, and autoregressive LaTeX markup fingerprints.
- **Eliminate AI Tropes (Kobak et al. Markers):** Strip characteristic synthetic vocabulary (*delve*, *pivotal*, *intricate*, *crucial*, *notably*, *underscores*, *showcasing*, *testament*, *tapestry*, *beacon*, *groundbreaking*, *it is crucial to note*) and formulaic pre-equation transitions.
- **Punctuation & Burstiness Standards:** Avoid conversational em dashes (`—` or `---`); replace with parentheses, commas, or discrete clauses. Enforce high sentence-length burstiness ($B_{\\mathrm{length}} > 0.55$) by alternating concise empirical assertions with multi-clause analytical sentences.
- **LaTeX Source-Code Ergonomics:** Avoid `\\item \\textbf{...}:` list clones ($R_{\\mathrm{IB}} < 0.80$, item length $\\mathrm{CV} > 0.40$); define reusable semantic macros ($\\mu_{\\mathrm{macro}} > 0$) instead of repeating raw canonical expansions; place `where ...` explanations in body prose rather than inside display equations ($\\rho_{\\mathrm{math\\_text}} = 0$); scope multi-letter subscripts in upright font (`$W_{\\mathrm{loss}}$`); and insert thin spaces (`\\,`) before differentials.
- **Scholarly Register:** Enforce disciplined academic voice: passive constructions where standard in scientific disciplines, epistemic hedging (*results indicate*, *under assumption $\\mathcal{A}$*), and precise quantitative descriptions.

## 3. Mathematical & Theoretical Rigor
- **Symbolic Verification First:** Before asserting mathematical proofs, gradients, or optimality conditions in manuscript text, verify them symbolically via the `turing` skill (SymPy).
- **Dimensional Homogeneity:** Verify that all additive terms and equation equalities maintain consistent physical units (pint/SymPy).
- **Matrix & Tensor Shapes:** Verify that matrix products, vector inner/outer products, and tensor contractions have strictly compatible shapes.
- **Asymptotic & Boundary Conditions:** Check analytical limits ($x \\to 0$, $N \\to \\infty$) and convexity properties (positive semi-definite Hessian).
- **Theoretical vs. Numerical Alignment:** Verify that closed-form analytical equations match empirical numerical simulations using the `gauss` skill.

## 4. Adversarial Peer Review & Methodology
- **Unstated Assumptions:** Uncover and explicitly document hidden physical or computational assumptions in System Models (e.g., ideal feedback, negligible delay, infinite compute) using the `popper` skill.
- **Fair Baselines:** Validate that experimental comparisons evaluate against modern state of the art rather than outdated or weak baselines.
- **Failure Modes & Sensitivity:** Document boundary conditions and scenarios where proposed methods degrade or fail.

## 5. LaTeX Typesetting & Compilation
- **Notation Consistency:** Maintain uniform symbol definitions and formatting across all sections and equation environments.
- **Clean Compilation:** Use the `compiler` skill to run `latexmk` or `pdflatex`, locate build errors by file and line number, and resolve missing packages or undefined references.

## 6. Title, Abstract & Academic SEO Optimization
- **Keyphrase Front-Loading:** Always place the primary domain search keyphrase within the first 65 characters of the title to avoid search snippet truncation.
- **Citation Sweet-Spot Length:** Target title lengths of 10–14 words (70–110 characters) correlated with higher citation discovery.
- **5-Beat Dual-Audience Abstracts:** Structure abstracts strictly into 150–220 words balancing an accessible lead hook for non-technical/interdisciplinary readers with quantified empirical metrics for expert reviewers.
- **Rule of Three Keyphrase Anchoring:** Anchor primary search keyphrases across context (Beat 1), methodology (Beat 3), and conclusion (Beat 5).
- **Metadata Vocabulary Expansion:** Ensure author keywords share <35% word overlap with the title, broadening the paper's searchable footprint across indexing databases.
- **Empirical Validation:** Use the `shannon` skill (`test_keywords.py`) to verify the 100-point Reviewer Triage Score and search engine collision safety.

## 7. Visual & Scientific Figure Accessibility
- **Vector Over Raster:** Always use vector formats (`.pdf`, `.eps`, `.svg`) for loss curves, accuracy plots, schematics, and line charts.
- **Print Resolution (DPI):** Ensure all raster figures maintain $\\ge 300\\text{ DPI}$ print resolution.
- **Subfigure Parity:** Every subfigure tag `(a)`, `(b)`, `(c)` declared in captions or subfloats must be explicitly discussed in body text.
- **Colorblind Palettes:** Avoid ambiguous red-green combinations without secondary visual cues (line styles, markers); verify palettes using the `da-vinci` skill (`sf figures` / `scifi_audit_figures`).

## 8. Page Budget & Typographic Micro-Trimming
- **Zero Forbidden Squeeze Hacks:** Never resort to forbidden negative `\\vspace` or margin modifications to meet page ceilings.
- **Widow Line Pruning:** Prune 1–3 words from paragraphs ending in short orphan/widow lines to recover full vertical lines.
- **BibTeX Venue Condensation:** Condense verbose journal and conference names into standard ISO-4/IEEE abbreviations via the `layout` skill (`sf trim` / `scifi_trim_budget`).

## 9. Theorem–Proof & Appendix Completeness
- **Zero Orphan Claims:** Never leave a theorem, lemma, or proposition without an inline proof or an explicit verifiable pointer to an appendix derivation.
- **Appendix Label Resolution:** Verify that all deferred proofs resolve to defined LaTeX appendix anchors via the `euclid` skill (`sf proofs` / `scifi_audit_proofs`).

## 10. Conference Reproducibility & Open Science
- **Empirical Transparency:** Document explicit random evaluation seeds, trial repetitions, standard deviations, and confidence intervals.
- **Compute Disclosures:** Report hardware accelerators (e.g. GPU models, node counts) and total compute training hours.
- **Double-Blind Repository Sanitization:** Never include identifiable personal GitHub URLs under double-blind review; sanitize links via the `bacon` skill (`sf repro` / `scifi_audit_reproducibility`).

## 11. Author Rebuttal & Point-by-Point Revisions
- **4-Beat Rebuttal Architecture:** Structure every peer review response across: (1) Summary & Direct Answer, (2) Concrete Action Taken, (3) New Empirical/Theoretical Evidence, (4) Revised Manuscript Excerpt.
- **Objective Scholarly Etiquette:** Eliminate sycophantic praise and defensive argument; maintain disciplined academic register via the `rebuttal` skill (`sf rebuttal` / `scifi_format_rebuttal` / `scifi_diff_manuscript`).

## 12. Academic Paper Packaging & Submission Suite
- **Publisher Profile Fidelity:** Format cover letters, highlights, and title pages according to target venue profiles (`elsevier`, `ieee`, `springer`, `acm`, `openreview`).
- **Research Highlight Character Ceiling:** Strictly enforce venue-specific highlight lengths ($\\le 85$ characters including spaces for Elsevier, $\\le 100$ characters for IEEE/Springer) via `sf submission highlights` (`scifi_generate_highlights`).
- **Review Fairness via Standalone Title Pages:** When manuscripts are submitted under double-blind review, always generate a standalone unblinded title page (`title_page.tex`) via `sf submission title-page` (`scifi_generate_title_page`) containing complete author affiliations, correspondence, funding, and CRediT statements, preserving zero author leaks in `main.tex`.
- **Reproducible Anonymous Code Packaging:** Scrub all git histories, commit records, local user path traces (`C:\\Users\\...` or `/home/...`), credentials, and author names from supplementary code archives via `sf submission pack-code` (`scifi_package_anonymous_code`).
- **One-Shot Submission Bundling:** Aggregate all four submission artifacts into a unified verified package with `submission_manifest.json` via `sf submission bundle` (`scifi_prepare_submission_bundle`).
"""


def load_canonical_rules(project_root: Path | str | None = None) -> str:
    """
    Load canonical SciFi academic rules from rules/AGENTS.md, package resources, or fallback.

    Args:
        project_root: Optional root directory to search for rules/AGENTS.md.

    Returns:
        String content of the canonical academic rules.
    """
    # 1. Check explicitly provided project_root
    if project_root is not None:
        cand = Path(project_root) / "rules" / "AGENTS.md"
        if cand.exists():
            try:
                text = cand.read_text(encoding="utf-8").strip()
                if text:
                    return text
            except Exception:
                pass

    # 2. Check packaged resource in scifi.resources
    try:
        resource_ref = importlib.resources.files("scifi.resources").joinpath("AGENTS.md")
        if resource_ref.is_file():
            text = resource_ref.read_text(encoding="utf-8").strip()
            if text:
                return text
    except Exception:
        pass

    # 3. Check relative to current file (source checkout) or cwd
    candidates: list[Path] = [
        Path(__file__).resolve().parent.parent / "rules" / "AGENTS.md",
        Path.cwd() / "rules" / "AGENTS.md",
    ]

    for cand in candidates:
        if cand.exists():
            try:
                text = cand.read_text(encoding="utf-8").strip()
                if text:
                    return text
            except Exception:
                pass

    return DEFAULT_CANONICAL_RULES.strip()


def sync_rule_file(
    target_path: Path | str,
    rule_content: str,
    dry_run: bool = False,
) -> bool:
    """
    Synchronize SciFi scientific rules into a target instruction file non-destructively.

    If markers exist, replaces only the bounded section.
    If no markers exist, appends the marker-bounded section to existing content.
    If file does not exist, creates it with the bounded section.

    Args:
        target_path: Path to the target instruction file (e.g. CLAUDE.md, .clinerules).
        rule_content: String containing academic invariants to sync.
        dry_run: If True, do not modify files on disk.

    Returns:
        True if sync succeeded (or would succeed in dry_run), False on error.
    """
    target = Path(target_path).resolve()
    marker_block = (
        f"{SCIFI_RULE_MARKER_START}\n"
        f"<!-- Generated by SciFi (sf setup --rules). Do not edit between markers; edit rules/AGENTS.md -->\n\n"
        f"{rule_content.strip()}\n"
        f"{SCIFI_RULE_MARKER_END}\n"
    )

    if target.exists():
        try:
            content = target.read_text(encoding="utf-8")
            if SCIFI_RULE_MARKER_START in content and SCIFI_RULE_MARKER_END in content:
                start_idx = content.find(SCIFI_RULE_MARKER_START)
                end_marker_pos = content.find(SCIFI_RULE_MARKER_END)
                end_idx = end_marker_pos + len(SCIFI_RULE_MARKER_END)
                new_content = content[:start_idx] + marker_block + content[end_idx:]
            else:
                new_content = content.rstrip() + "\n\n" + marker_block
        except Exception as exc:
            print(f"Warning: Could not read {target}: {exc}. Writing fresh.", file=sys.stderr)
            new_content = marker_block
    else:
        new_content = marker_block

    if dry_run:
        print(f"[DRY-RUN] Planned rule sync for: {target}")
        return True

    temp_name: str | None = None
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent, delete=False) as tf:
            tf.write(new_content)
            temp_name = tf.name
        os.replace(temp_name, target)
        return True
    except Exception as exc:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
        print(f"Error synchronizing rules to {target}: {exc}", file=sys.stderr)
        return False


def sync_all_rules(
    project_root: Path | str | None = None,
    detected_tools_only: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """
    Synchronize SciFi scientific rules to all target instruction files in a repository.

    Targets:
    - AGENTS.md (OpenCode, general agents, Codex, Aider)
    - CLAUDE.md (Claude Code CLI, Claude Desktop)
    - .clinerules (VS Code Cline & Roo Code)
    - .cursorrules (Cursor)
    - .windsurfrules (Windsurf)
    - .github/copilot-instructions.md (GitHub Copilot in VS Code)

    Args:
        project_root: Target repository root (defaults to cwd).
        detected_tools_only: If True, only syncs if tool or file exists.
        dry_run: If True, preview sync without disk writes.

    Returns:
        List of Path objects that were synced.
    """
    root = Path(project_root or Path.cwd()).resolve()
    rules = load_canonical_rules(root)

    candidate_files = [
        root / "AGENTS.md",
        root / "CLAUDE.md",
        root / ".clinerules",
        root / ".cursorrules",
        root / ".windsurfrules",
        root / ".github" / "copilot-instructions.md",
    ]

    synced: list[Path] = []
    for target in candidate_files:
        if detected_tools_only and not target.exists():
            continue
        success = sync_rule_file(target, rules, dry_run=dry_run)
        if success:
            synced.append(target)

    return synced


@dataclass
class TargetEnvironment:
    """Represents a target AI editing / assistant environment."""

    name: str
    config_path: Path
    detected: bool = False
    installed: bool = False
    format_type: str = "standard"  # "standard" (mcpServers) or "opencode" (mcp)
    scope: str = "global"  # "global" or "workspace"


def validate_scifi_server() -> bool:
    """
    Validate that scifi.server can be successfully imported.

    Returns:
        True if scifi.server is importable, False otherwise.
    """
    try:
        import importlib

        importlib.import_module("scifi.server")
        return True
    except Exception as exc:
        print(f"Pre-flight check failed: 'scifi.server' cannot be loaded: {exc}", file=sys.stderr)
        return False


def is_mcp_installed(config_path: Path, format_type: str = "standard") -> bool:
    """
    Check if scifi server entry already exists in the given MCP config file.

    Args:
        config_path: Path to mcp JSON configuration file.
        format_type: "standard" for mcpServers or "opencode" for mcp.

    Returns:
        True if 'scifi' server is registered in mcpServers (or mcp for OpenCode).
    """
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return False
        if format_type == "opencode":
            return "scifi" in data.get("mcp", {}) or "scifi" in data.get("mcpServers", {})
        return "scifi" in data.get("mcpServers", {})
    except Exception:
        return False


def detect_environments(
    home_dir: Path | None = None,
    appdata_dir: Path | None = None,
    project_dir: Path | None = None,
    check_path: bool = True,
) -> list[TargetEnvironment]:
    """
    Detect supported AI environments on the host system.

    Checks:
    - Antigravity: ~/.gemini/config/mcp_config.json
    - Claude Desktop: %APPDATA%/Claude/claude_desktop_config.json (Windows),
      ~/Library/Application Support/Claude/... (macOS), ~/.config/Claude/... (Linux)
    - Claude Code (Global): ~/.claude.json
    - Claude Code (Workspace): .mcp.json in workspace
    - Cursor: .cursor/mcp.json in workspace
    - VS Code Cline: cline_mcp_settings.json (saoudrizwan.claude-dev)
    - VS Code Roo Code: cline_mcp_settings.json (rooveterinaryinc.roo-cline)
    - OpenCode (Global): ~/.config/opencode/opencode.json
    - OpenCode (Workspace): opencode.json in workspace
    - Windsurf: ~/.codeium/windsurf/mcp_config.json

    Args:
        home_dir: Optional override for user home directory.
        appdata_dir: Optional override for Windows APPDATA directory.
        project_dir: Optional override for workspace / repository root.

    Returns:
        List of TargetEnvironment objects with detection & installation status.
    """
    home = (home_dir or Path.home()).resolve()
    project = (project_dir or Path.cwd()).resolve()

    if appdata_dir is not None:
        appdata = Path(appdata_dir).resolve()
    elif "APPDATA" in os.environ and sys.platform == "win32":
        appdata = Path(os.environ["APPDATA"]).resolve()
    else:
        appdata = home / "AppData" / "Roaming"

    envs: list[TargetEnvironment] = []

    # 1. Antigravity: ~/.gemini/config/mcp_config.json
    antigravity_path = home / ".gemini" / "config" / "mcp_config.json"
    antigravity_detected = (home / ".gemini").exists() or antigravity_path.exists()
    envs.append(
        TargetEnvironment(
            name="Antigravity",
            config_path=antigravity_path,
            detected=antigravity_detected,
            installed=is_mcp_installed(antigravity_path),
            scope="global",
        )
    )

    # 2. Claude Desktop
    claude_detected = False
    claude_candidates: list[tuple[Path, Path]] = []

    if sys.platform == "win32" or appdata_dir is not None:
        claude_candidates.append((appdata / "Claude" / "claude_desktop_config.json", appdata / "Claude"))
    claude_candidates.append(
        (home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json", home / "Library" / "Application Support" / "Claude")
    )
    claude_candidates.append((home / ".config" / "Claude" / "claude_desktop_config.json", home / ".config" / "Claude"))
    claude_candidates.append((home / ".claude" / "claude_desktop_config.json", home / ".claude"))

    selected_claude: Path | None = None
    for cfg_p, dir_p in claude_candidates:
        if cfg_p.exists() or dir_p.exists():
            selected_claude = cfg_p
            claude_detected = True
            break

    if selected_claude is None:
        if sys.platform == "win32" or appdata_dir is not None:
            selected_claude = appdata / "Claude" / "claude_desktop_config.json"
        elif sys.platform == "darwin":
            selected_claude = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
        else:
            selected_claude = home / ".config" / "Claude" / "claude_desktop_config.json"

    envs.append(
        TargetEnvironment(
            name="Claude Desktop",
            config_path=selected_claude,
            detected=claude_detected,
            installed=is_mcp_installed(selected_claude),
            scope="global",
        )
    )

    # 3. Claude Code (Global): ~/.claude.json
    claude_code_global_path = home / ".claude.json"
    claude_code_global_detected = (
        claude_code_global_path.exists()
        or (home / ".claude").exists()
        or (check_path and shutil.which("claude") is not None)
    )
    envs.append(
        TargetEnvironment(
            name="Claude Code (Global)",
            config_path=claude_code_global_path,
            detected=claude_code_global_detected,
            installed=is_mcp_installed(claude_code_global_path),
            scope="global",
        )
    )

    # 4. Claude Code (Workspace): .mcp.json
    claude_code_ws_path = project / ".mcp.json"
    claude_code_ws_detected = claude_code_ws_path.exists() or (project / ".claude").exists()
    envs.append(
        TargetEnvironment(
            name="Claude Code (Workspace)",
            config_path=claude_code_ws_path,
            detected=claude_code_ws_detected,
            installed=is_mcp_installed(claude_code_ws_path),
            scope="workspace",
        )
    )

    # 5. Cursor: .cursor/mcp.json in workspace
    cursor_path = project / ".cursor" / "mcp.json"
    cursor_detected = (project / ".cursor").exists() or cursor_path.exists()
    envs.append(
        TargetEnvironment(
            name="Cursor",
            config_path=cursor_path,
            detected=cursor_detected,
            installed=is_mcp_installed(cursor_path),
            scope="workspace",
        )
    )

    # 6. VS Code Cline: cline_mcp_settings.json
    cline_candidates = [
        appdata / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
        home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
        home / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings" / "cline_mcp_settings.json",
    ]
    cline_path = cline_candidates[0]
    cline_detected = False
    for p in cline_candidates:
        if p.exists() or p.parent.parent.exists():
            cline_path = p
            cline_detected = True
            break
    envs.append(
        TargetEnvironment(
            name="VS Code Cline",
            config_path=cline_path,
            detected=cline_detected,
            installed=is_mcp_installed(cline_path),
            scope="global",
        )
    )

    # 7. VS Code Roo Code: cline_mcp_settings.json
    roo_candidates = [
        appdata / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
        home / "Library" / "Application Support" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
        home / ".config" / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
    ]
    roo_path = roo_candidates[0]
    roo_detected = False
    for p in roo_candidates:
        if p.exists() or p.parent.parent.exists():
            roo_path = p
            roo_detected = True
            break
    envs.append(
        TargetEnvironment(
            name="VS Code Roo Code",
            config_path=roo_path,
            detected=roo_detected,
            installed=is_mcp_installed(roo_path),
            scope="global",
        )
    )

    # 8. OpenCode (Global): ~/.config/opencode/opencode.json
    opencode_global_path = home / ".config" / "opencode" / "opencode.json"
    opencode_global_detected = (
        opencode_global_path.exists()
        or (home / ".config" / "opencode").exists()
        or (check_path and shutil.which("opencode") is not None)
    )
    envs.append(
        TargetEnvironment(
            name="OpenCode (Global)",
            config_path=opencode_global_path,
            detected=opencode_global_detected,
            installed=is_mcp_installed(opencode_global_path, format_type="opencode"),
            format_type="opencode",
            scope="global",
        )
    )

    # 9. OpenCode (Workspace): opencode.json
    opencode_ws_path = project / "opencode.json"
    opencode_ws_detected = opencode_ws_path.exists() or (project / ".opencode").exists()
    envs.append(
        TargetEnvironment(
            name="OpenCode (Workspace)",
            config_path=opencode_ws_path,
            detected=opencode_ws_detected,
            installed=is_mcp_installed(opencode_ws_path, format_type="opencode"),
            format_type="opencode",
            scope="workspace",
        )
    )

    # 10. Windsurf: ~/.codeium/windsurf/mcp_config.json
    windsurf_path = home / ".codeium" / "windsurf" / "mcp_config.json"
    windsurf_detected = windsurf_path.exists() or (home / ".codeium" / "windsurf").exists()
    envs.append(
        TargetEnvironment(
            name="Windsurf",
            config_path=windsurf_path,
            detected=windsurf_detected,
            installed=is_mcp_installed(windsurf_path),
            scope="global",
        )
    )

    return envs


def install_mcp_config(
    target: Path | str,
    scifi_root: Path | str | None = None,
    dry_run: bool = False,
    format_type: str = "standard",
) -> bool:
    """
    Install or update the SciFi FastMCP server entry in a target JSON config.

    Args:
        target: Path to target configuration file.
        scifi_root: Path to SciFi repository root (defaults to parent of scifi package).
        dry_run: If True, do not modify files, only print planned changes.
        format_type: "standard" for mcpServers or "opencode" for mcp.

    Returns:
        True if operation succeeded (or would succeed in dry_run), False on error.
    """
    target_path = Path(target)
    if scifi_root is None:
        scifi_root_path = Path(__file__).resolve().parent.parent
    else:
        scifi_root_path = Path(scifi_root).resolve()

    is_source_checkout = (
        (scifi_root_path / "pyproject.toml").exists()
        or (scifi_root_path / "scifi").exists()
        or (scifi_root is not None)
    )

    if format_type == "opencode":
        if is_source_checkout:
            server_entry = {
                "type": "local",
                "command": ["uv", "run", "python", "-m", "scifi.server"],
                "cwd": str(scifi_root_path),
            }
        else:
            server_entry = {
                "type": "local",
                "command": ["sf", "server"],
            }
    else:
        if is_source_checkout:
            server_entry = {
                "command": "uv",
                "args": ["run", "python", "-m", "scifi.server"],
                "cwd": str(scifi_root_path),
            }
        else:
            server_entry = {
                "command": "sf",
                "args": ["server"],
            }

    data: dict[str, Any] = {}
    if target_path.exists():
        try:
            content = target_path.read_text(encoding="utf-8")
            if content.strip():
                loaded = json.loads(content)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception as exc:
            print(f"Warning: Could not parse existing JSON in {target_path}: {exc}. Starting fresh.", file=sys.stderr)
            data = {}

    if format_type == "opencode":
        if "mcp" not in data or not isinstance(data["mcp"], dict):
            data["mcp"] = {}
        data["mcp"]["scifi"] = server_entry
    else:
        if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
            data["mcpServers"] = {}
        data["mcpServers"]["scifi"] = server_entry

    formatted_json = json.dumps(data, indent=2) + "\n"

    if dry_run:
        print(f"[DRY-RUN] Planned modification for: {target_path}")
        print(formatted_json)
        return True

    temp_name: str | None = None
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target_path.parent, delete=False) as tf:
            tf.write(formatted_json)
            temp_name = tf.name
        os.replace(temp_name, target_path)
        return True
    except Exception as exc:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
        print(f"Error writing configuration to {target_path}: {exc}", file=sys.stderr)
        return False


def cmd_setup(args: argparse.Namespace) -> int:
    """
    Execute setup installer command.

    Args:
        args: Parsed arguments with auto, dry_run, target, scifi_root.

    Returns:
        Exit code: 0 on success, non-zero on error.
    """
    if not validate_scifi_server():
        return 1

    dry_run = getattr(args, "dry_run", False)
    scifi_root = getattr(args, "scifi_root", None)
    target = getattr(args, "target", None)

    if target:
        target_path = Path(target)
        success = install_mcp_config(target_path, scifi_root=scifi_root, dry_run=dry_run)
        if success:
            action = "Simulated configuration of" if dry_run else "Successfully configured"
            print(f"{action} SciFi MCP in {target_path}")
            return 0
        else:
            return 1

    project_dir = getattr(args, "project_dir", None)
    project = Path(project_dir or Path.cwd()).resolve()

    workspace = getattr(args, "workspace", False)
    if workspace:
        cursor_mcp = project / ".cursor" / "mcp.json"
        claude_mcp = project / ".mcp.json"
        opencode_mcp = project / "opencode.json"

        ws_targets = [
            (cursor_mcp, "Cursor Workspace", "standard"),
            (claude_mcp, "Claude Code Workspace", "standard"),
            (opencode_mcp, "OpenCode Workspace", "opencode"),
        ]
        all_ok = True
        for cfg_p, name, fmt in ws_targets:
            ok = install_mcp_config(cfg_p, scifi_root=scifi_root, dry_run=dry_run, format_type=fmt)
            action = "[DRY-RUN] Would configure" if dry_run else "Configured"
            if ok:
                print(f"{action} {name} ({cfg_p})")
            else:
                print(f"Failed to configure {name} ({cfg_p})", file=sys.stderr)
                all_ok = False

        synced = sync_all_rules(project_root=project, dry_run=dry_run)
        action_rules = "[DRY-RUN] Would synchronize" if dry_run else "Synchronized"
        print(f"{action_rules} SciFi rules to {len(synced)} rule file(s) in {project}")
        return 0 if all_ok else 1

    rules = getattr(args, "rules", False)
    if rules:
        synced = sync_all_rules(project_root=project, dry_run=dry_run)
        action_rules = "[DRY-RUN] Would synchronize" if dry_run else "Synchronized"
        print(f"{action_rules} SciFi scientific rules to {len(synced)} rule file(s) in {project}:")
        for p in synced:
            print(f"  - {p.relative_to(project) if p.is_relative_to(project) else p}")
        return 0

    envs = detect_environments(project_dir=project)
    detected = [e for e in envs if e.detected]
    auto = getattr(args, "auto", False)

    list_only = getattr(args, "list", False)
    if list_only:
        print(f"Supported AI environments ({len(envs)} total):")
        for idx, e in enumerate(envs, 1):
            det_status = "DETECTED" if e.detected else "not detected"
            inst_status = ", configured" if e.installed else ""
            print(f"  [{idx}] {e.name} [{det_status}{inst_status}]: {e.config_path}")
        return 0

    if not detected:
        print("No installed AI environments (OpenCode, Claude Code, VS Code Cline/Roo, Cursor, Windsurf, Antigravity, Claude Desktop) were automatically detected.")
        if auto:
            print("Auto-setup exiting: no environments detected to configure.")
            return 0
        print("Supported environment paths:")
        for e in envs:
            print(f"  - {e.name}: {e.config_path}")
        return 0

    print(f"Detected {len(detected)} AI environment(s):")
    for idx, e in enumerate(detected, 1):
        status = " (already configured)" if e.installed else ""
        print(f"  [{idx}] {e.name}: {e.config_path}{status}")

    targets_to_install: list[TargetEnvironment] = []
    if auto:
        targets_to_install = detected
    else:
        if hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
            print("\nEnter environment numbers to configure (e.g. 1, 2) or 'all' [default: all]: ", end="", flush=True)
            choice = input().strip()
            if not choice or choice.lower() == "all":
                targets_to_install = detected
            else:
                for part in choice.split(","):
                    part = part.strip()
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(detected):
                            targets_to_install.append(detected[idx])
        else:
            targets_to_install = detected

    all_ok = True
    for env in targets_to_install:
        success = install_mcp_config(
            env.config_path,
            scifi_root=scifi_root,
            dry_run=dry_run,
            format_type=env.format_type,
        )
        if success:
            action = "[DRY-RUN] Would configure" if dry_run else "Configured"
            print(f"{action} SciFi MCP for {env.name} ({env.config_path})")
        else:
            print(f"Failed to configure SciFi MCP for {env.name} ({env.config_path})", file=sys.stderr)
            all_ok = False

    return 0 if all_ok else 1


def cmd_sync(args: argparse.Namespace) -> int:
    """
    Execute sf sync command to synchronize SciFi rules across all tool instruction files.
    """
    dry_run = getattr(args, "dry_run", False)
    project_dir = getattr(args, "project_dir", None)
    project = Path(project_dir or Path.cwd()).resolve()
    synced = sync_all_rules(project_root=project, dry_run=dry_run)
    action = "[DRY-RUN] Would synchronize" if dry_run else "Synchronized"
    print(f"{action} SciFi scientific rules to {len(synced)} rule file(s) in {project}:")
    for p in synced:
        rel = p.relative_to(project) if p.is_relative_to(project) else p
        print(f"  - {rel}")
    return 0

