"""
scifi.lifecycle — Installation Mode Detection, State Tracking, and Safe Upgrades.

Handles:
1. Detecting whether SciFi is running as `uv tool`, `uvx` (ephemeral), `pip`, or an editable checkout.
2. Lazy post-upgrade migration tracking in `~/.scifi/state.json`.
3. Explicit PyPI update checks (`sf upgrade --check`) and mode-appropriate upgrades (`sf upgrade`).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import requests

import scifi
from scifi.config import migrate_global_config_file
from scifi.setup_cli import check_rules_sync_status

PYPI_JSON_URL = "https://pypi.org/pypi/scifi/json"


def get_state_path() -> Path:
    """Return path to ~/.scifi/state.json (or SCIFI_STATE_PATH override)."""
    env_override = os.environ.get("SCIFI_STATE_PATH")
    if env_override:
        return Path(env_override)
    return Path.home() / ".scifi" / "state.json"


def load_state(state_path: Path | str | None = None) -> dict[str, Any]:
    """Load lifecycle state dictionary from ~/.scifi/state.json."""
    path = Path(state_path) if state_path else get_state_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_state(data: dict[str, Any], state_path: Path | str | None = None) -> Path:
    """Persist lifecycle state dictionary atomically."""
    path = Path(state_path) if state_path else get_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    formatted = json.dumps(data, indent=2) + "\n"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tf:
            tf.write(formatted)
            temp_name = tf.name
        os.replace(temp_name, path)
    except Exception:
        if temp_name and os.path.exists(temp_name):
            try:
                os.remove(temp_name)
            except OSError:
                pass
        raise
    return path


def detect_install_mode(
    prefix: str | None = None,
    executable: str | None = None,
    package_root: Path | None = None,
) -> dict[str, Any]:
    """
    Detect how SciFi is installed and return the appropriate upgrade strategy.
    """
    eff_prefix = prefix if prefix is not None else sys.prefix
    eff_exe = executable if executable is not None else sys.executable
    eff_root = package_root if package_root is not None else Path(__file__).resolve().parent.parent

    norm_prefix = eff_prefix.replace("\\", "/").lower()
    norm_exe = eff_exe.replace("\\", "/").lower()

    if "archive-v0" in norm_prefix or "archive-v0" in norm_exe:
        return {
            "mode": "uvx",
            "prefix": eff_prefix,
            "executable": eff_exe,
            "repo_root": None,
            "upgrade_command": None,
        }

    if "uv/tools" in norm_prefix or "uv/tools" in norm_exe:
        return {
            "mode": "uv_tool",
            "prefix": eff_prefix,
            "executable": eff_exe,
            "repo_root": None,
            "upgrade_command": ["uv", "tool", "upgrade", "scifi"],
        }

    if (eff_root / "pyproject.toml").is_file() and (eff_root / "scifi").is_dir():
        return {
            "mode": "editable",
            "prefix": eff_prefix,
            "executable": eff_exe,
            "repo_root": str(eff_root),
            "upgrade_command": ["git", "pull", "--ff-only"],
        }

    return {
        "mode": "pip",
        "prefix": eff_prefix,
        "executable": eff_exe,
        "repo_root": None,
        "upgrade_command": [eff_exe, "-m", "pip", "install", "--upgrade", "scifi"],
    }


def ensure_migrated_on_startup(
    state_path: Path | str | None = None,
    config_path: Path | str | None = None,
) -> bool:
    """
    Run lightweight global config migration once when scifi.__version__ changes.
    Returns True if a version transition was recorded.
    """
    state = load_state(state_path)
    current_version = scifi.__version__
    if state.get("last_run_version") == current_version:
        return False

    migrate_global_config_file(config_path)
    state["last_run_version"] = current_version
    save_state(state, state_path)
    return True


def _parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Parse numeric semver prefix into a comparable tuple."""
    parts: list[int] = []
    for segment in version_str.strip().lstrip("v").split("."):
        digits = ""
        for ch in segment:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def check_for_update(timeout: float = 2.0) -> dict[str, Any]:
    """Query PyPI for the latest released version of scifi."""
    current = scifi.__version__
    try:
        resp = requests.get(PYPI_JSON_URL, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
        latest = str(payload.get("info", {}).get("version", "")).strip()
        if not latest:
            return {
                "current": current,
                "latest": None,
                "update_available": False,
                "error": "Empty version in PyPI response",
            }
        update_available = _parse_version_tuple(latest) > _parse_version_tuple(current)
        return {
            "current": current,
            "latest": latest,
            "update_available": update_available,
            "error": None,
        }
    except Exception as exc:
        return {
            "current": current,
            "latest": None,
            "update_available": False,
            "error": str(exc),
        }


def perform_upgrade(dry_run: bool = False, check_only: bool = False) -> int:
    """Execute `sf upgrade` or `sf upgrade --check`."""
    if check_only:
        res = check_for_update()
        if res["error"]:
            print(f"[WARNING] Could not check PyPI for updates: {res['error']}", file=sys.stderr)
            return 1
        if res["update_available"]:
            print(f"Update available: scifi {res['current']} -> {res['latest']}")
        else:
            print(f"scifi {res['current']} is up to date.")
        return 0

    info = detect_install_mode()
    mode = info["mode"]

    if mode == "uvx":
        print("SciFi is running in an ephemeral uvx environment.")
        print("Run `uvx scifi@latest` for the newest release, or install persistently via:")
        print("  uv tool install scifi")
        return 0

    cmd = info["upgrade_command"]
    assert cmd is not None

    commands: list[tuple[list[str], str | None]] = [(cmd, info.get("repo_root"))]
    if mode == "editable" and shutil.which("uv"):
        commands.append((["uv", "sync"], info.get("repo_root")))

    if dry_run:
        print(f"[DRY-RUN] Detected install mode: {mode}")
        for c, cwd in commands:
            loc = f" (in {cwd})" if cwd else ""
            print(f"[DRY-RUN] Would run: {' '.join(c)}{loc}")
        return 0

    for c, cwd in commands:
        print(f"Running ({mode}): {' '.join(c)}")
        proc = subprocess.run(c, cwd=cwd)
        if proc.returncode != 0:
            print(f"[ERROR] Upgrade command failed with exit code {proc.returncode}.", file=sys.stderr)
            return proc.returncode

    rule_status = check_rules_sync_status(Path.cwd())
    if rule_status["total_marked"] > 0:
        print("Tip: Run `sf sync` in your workspace to update SciFi rule markers if needed.")

    return 0
