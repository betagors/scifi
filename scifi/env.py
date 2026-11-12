"""
Environment and Prerequisite Self-Healing Manager.
Detects Zotero installations, uv runtime, and TeX compilers, providing
resilient fallback without interrupting the user.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def auto_detect_zotero_dir() -> Path | None:
    """
    Auto-detect the local Zotero data directory across platforms.
    Prioritizes directories containing zotero.sqlite.
    """
    candidates: list[Path] = []

    # Check explicit env var first
    env_dir = os.environ.get("ZOTERO_DATA_DIR")
    if env_dir:
        candidates.append(Path(env_dir))

    # Standard home directory lookup
    user_home = Path.home()
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "Zotero")
    candidates.append(user_home / "Zotero")

    system = platform.system()
    if system == "Darwin":
        candidates.append(user_home / "Library" / "Application Support" / "Zotero")
    elif system == "Linux":
        candidates.append(user_home / ".zotero")

    for candidate in candidates:
        if candidate.is_dir() and (candidate / "zotero.sqlite").is_file():
            return candidate.resolve()

    return None


def is_zotero_port_open(host: str = "127.0.0.1", port: int = 23119, timeout: float = 0.5) -> bool:
    """Check if Zotero local HTTP server port is open."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


def ensure_uv() -> dict[str, Any]:
    """
    Check if uv package manager is available, returning execution info.
    Falls back gracefully to sys.executable without failing.
    """
    uv_bin = shutil.which("uv")
    if uv_bin:
        try:
            ver = subprocess.run([uv_bin, "--version"], capture_output=True, text=True, timeout=3)
            version_str = ver.stdout.strip()
        except Exception:
            version_str = "uv (version query failed)"
        return {
            "available": True,
            "executable": uv_bin,
            "version": version_str,
            "fallback": False,
        }

    return {
        "available": False,
        "executable": sys.executable,
        "version": None,
        "fallback": True,
        "message": f"uv not found on PATH; falling back to {sys.executable}",
    }


def diagnose_environment(auto_fix: bool = False) -> dict[str, Any]:
    """
    Diagnose environment health across Python, uv, LaTeX toolchain, and Zotero.
    """
    # Python
    py_info = {
        "version": sys.version.split()[0],
        "executable": sys.executable,
        "status": "HEALTHY",
    }

    # uv
    uv_info = ensure_uv()

    # Zotero
    z_dir = auto_detect_zotero_dir()
    z_port = is_zotero_port_open() if z_dir else False
    zotero_info = {
        "detected": z_dir is not None,
        "data_dir": str(z_dir) if z_dir else None,
        "sqlite_exists": (z_dir / "zotero.sqlite").is_file() if z_dir else False,
        "port_23119_open": z_port,
        "status": "RUNNING" if z_port else ("INSTALLED_OFFLINE" if z_dir else "NOT_FOUND"),
    }

    # LaTeX
    latexmk_bin = shutil.which("latexmk")
    pdflatex_bin = shutil.which("pdflatex")
    xelatex_bin = shutil.which("xelatex")
    latex_info = {
        "latexmk": latexmk_bin,
        "pdflatex": pdflatex_bin,
        "xelatex": xelatex_bin,
        "available": any([latexmk_bin, pdflatex_bin, xelatex_bin]),
        "status": "HEALTHY" if any([latexmk_bin, pdflatex_bin]) else "MISSING",
    }

    return {
        "python": py_info,
        "uv": uv_info,
        "zotero": zotero_info,
        "latex": latex_info,
        "healthy": py_info["status"] == "HEALTHY",
    }
