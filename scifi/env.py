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

    # LaTeX (uses smart cached toolchain discovery, including off-PATH MiKTeX/TeX Live)
    from scifi.figures.renderer import detect_pdf_renderer
    from scifi.latex.compiler import discover_tex_toolchain

    tc = discover_tex_toolchain()
    avail = tc.get("available_engines", {})
    renderer_info = detect_pdf_renderer(extra_bin_dir=tc.get("bin_dir"))
    latex_info = {
        "ready": tc.get("ready", False),
        "distribution": tc.get("distribution"),
        "primary_engine": tc.get("engine"),
        "engine_path": tc.get("engine_path"),
        "bin_dir": tc.get("bin_dir"),
        "version": tc.get("version"),
        "cached": tc.get("cached", False),
        "latexmk": avail.get("latexmk"),
        "pdflatex": avail.get("pdflatex"),
        "xelatex": avail.get("xelatex"),
        "lualatex": avail.get("lualatex"),
        "pdftoppm": avail.get("pdftoppm"),
        "pdf_renderer": renderer_info,
        "available": tc.get("ready", False),
        "status": "HEALTHY" if tc.get("ready") else "MISSING",
        "hint": tc.get("hint"),
    }

    import sqlite3

    import scifi
    from scifi.lifecycle import detect_install_mode
    from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH
    from scifi.setup_cli import check_rules_sync_status

    install_info = detect_install_mode()
    store_info: dict[str, Any] = {
        "path": str(DEFAULT_CENTRAL_STORE_PATH),
        "exists": DEFAULT_CENTRAL_STORE_PATH.is_file(),
        "schema_version": None,
        "integrity": None,
    }
    if DEFAULT_CENTRAL_STORE_PATH.is_file():
        try:
            conn = sqlite3.connect(str(DEFAULT_CENTRAL_STORE_PATH), timeout=2.0)
            try:
                store_info["schema_version"] = int(conn.execute("PRAGMA user_version").fetchone()[0])
                qc = conn.execute("PRAGMA quick_check").fetchone()
                store_info["integrity"] = qc[0] if qc else "unknown"
            finally:
                conn.close()
        except Exception as exc:
            store_info["integrity"] = f"error: {exc}"

    scifi_info = {
        "version": scifi.__version__,
        "install_mode": install_info["mode"],
        "store": store_info,
        "rules": check_rules_sync_status(Path.cwd()),
    }

    # Datasets & Kaggle
    from scifi.config import get_datasets_dir
    from scifi.datasets.kaggle import resolve_kaggle_credentials

    ds_dir = get_datasets_dir()
    if auto_fix and not ds_dir.exists():
        try:
            ds_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
    ds_exists = ds_dir.is_dir()
    ds_writable = os.access(ds_dir, os.W_OK) if ds_exists else os.access(ds_dir.parent, os.W_OK)
    datasets_info = {
        "default_dir": str(ds_dir),
        "exists": ds_exists,
        "writable": ds_writable,
        "status": "HEALTHY" if (ds_exists and ds_writable) else ("READY" if ds_writable else "UNWRITABLE"),
    }

    kg_creds = resolve_kaggle_credentials()
    kg_auth = kg_creds.get("mode") in ("basic", "bearer")
    kaggle_info = {
        "authenticated": kg_auth,
        "auth_mode": kg_creds.get("mode"),
        "username": kg_creds.get("username"),
        "credential_source": kg_creds.get("source"),
        "status": "HEALTHY" if kg_auth else "MISSING_CREDENTIALS",
        "hint": None if kg_auth else "Run 'sf kaggle login' or place kaggle.json in ~/.kaggle/kaggle.json",
    }

    return {
        "scifi": scifi_info,
        "python": py_info,
        "uv": uv_info,
        "zotero": zotero_info,
        "latex": latex_info,
        "datasets": datasets_info,
        "kaggle": kaggle_info,
        "healthy": py_info["status"] == "HEALTHY",
    }
