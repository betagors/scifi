"""
REA-Style Setup Installer for SciFi FastMCP Server.

Detects AI environments (Google Antigravity, Claude Desktop, and Cursor)
and installs the `scifi` FastMCP server definition into their respective
mcp configuration files.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any


@dataclass
class TargetEnvironment:
    """Represents a target AI editing / assistant environment."""

    name: str
    config_path: Path
    detected: bool = False
    installed: bool = False


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


def is_mcp_installed(config_path: Path) -> bool:
    """
    Check if scifi server entry already exists in the given MCP config file.

    Args:
        config_path: Path to mcp JSON configuration file.

    Returns:
        True if 'scifi' server is registered in mcpServers.
    """
    if not config_path.exists():
        return False
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return isinstance(data, dict) and "scifi" in data.get("mcpServers", {})
    except Exception:
        return False


def detect_environments(
    home_dir: Path | None = None,
    appdata_dir: Path | None = None,
    project_dir: Path | None = None,
) -> list[TargetEnvironment]:
    """
    Detect supported AI environments on the host system.

    Checks:
    - Antigravity: ~/.gemini/config/mcp_config.json
    - Claude Desktop: %APPDATA%/Claude/claude_desktop_config.json (Windows),
      ~/Library/Application Support/Claude/claude_desktop_config.json (macOS),
      ~/.config/Claude/claude_desktop_config.json or ~/.claude/... (Linux)
    - Cursor: .cursor/mcp.json (workspace)

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
        )
    )

    # 3. Cursor: .cursor/mcp.json in workspace
    cursor_path = project / ".cursor" / "mcp.json"
    cursor_detected = (project / ".cursor").exists() or cursor_path.exists()
    envs.append(
        TargetEnvironment(
            name="Cursor",
            config_path=cursor_path,
            detected=cursor_detected,
            installed=is_mcp_installed(cursor_path),
        )
    )

    return envs


def install_mcp_config(
    target: Path | str,
    scifi_root: Path | str | None = None,
    dry_run: bool = False,
) -> bool:
    """
    Install or update the SciFi FastMCP server entry in a target JSON config.

    Args:
        target: Path to target configuration file.
        scifi_root: Path to SciFi repository root (defaults to parent of scifi package).
        dry_run: If True, do not modify files, only print planned changes.

    Returns:
        True if operation succeeded (or would succeed in dry_run), False on error.
    """
    target_path = Path(target)
    if scifi_root is None:
        scifi_root_path = Path(__file__).resolve().parent.parent
    else:
        scifi_root_path = Path(scifi_root).resolve()

    server_entry = {
        "command": "uv",
        "args": ["run", "python", "-m", "scifi.server"],
        "cwd": str(scifi_root_path),
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

    envs = detect_environments()
    detected = [e for e in envs if e.detected]
    auto = getattr(args, "auto", False)

    if not detected:
        print("No installed AI environments (Antigravity, Claude Desktop, Cursor) were automatically detected.")
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
        success = install_mcp_config(env.config_path, scifi_root=scifi_root, dry_run=dry_run)
        if success:
            action = "[DRY-RUN] Would configure" if dry_run else "Configured"
            print(f"{action} SciFi MCP for {env.name} ({env.config_path})")
        else:
            print(f"Failed to configure SciFi MCP for {env.name} ({env.config_path})", file=sys.stderr)
            all_ok = False

    return 0 if all_ok else 1
