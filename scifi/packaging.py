"""
Release & Distribution Packaging Engine for SciFi.

Handles building:
1. Python wheel and sdist distributions for PyPI via uv/build.
2. Standalone AI Agent Plugin bundles (scifi-plugin-vX.Y.Z.zip) for Antigravity,
   Claude Code, Cursor, Windsurf, Cline, and Gemini CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import scifi


def compute_sha256(file_path: Path) -> str:
    """Compute the SHA256 hexadecimal hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def write_sha256_file(file_path: Path) -> Path:
    """Generate a standard .sha256 checksum file alongside the target file."""
    checksum = compute_sha256(file_path)
    checksum_file = file_path.with_name(f"{file_path.name}.sha256")
    checksum_file.write_text(f"{checksum}  {file_path.name}\n", encoding="utf-8")
    return checksum_file


def build_plugin_bundle(repo_root: Path, output_dir: Path) -> Path:
    """
    Build a standalone AI Agent Plugin distribution archive (.zip).

    Includes plugin.json, gemini-extension.json, mcp_config.json, skills/,
    agents/, commands/, rules/, assets/, LICENSE, and README.md.

    Args:
        repo_root: Path to the repository root.
        output_dir: Destination directory for the archive.

    Returns:
        Path to the generated .zip file.
    """
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    version = scifi.__version__
    zip_name = f"scifi-plugin-v{version}.zip"
    bundle_path = output_dir / zip_name

    # Files to include directly at the root of the archive if present
    root_files = [
        "plugin.json",
        "gemini-extension.json",
        "mcp_config.json",
        "LICENSE",
        "README.md",
        "CITATION.cff",
    ]

    # Directories to include recursively
    include_dirs = [
        "skills",
        "agents",
        "commands",
        "rules",
        "assets",
    ]

    # Patterns to exclude from the archive
    exclude_patterns = {
        "__pycache__",
        ".pytest_cache",
        ".git",
        ".venv",
        "*.pyc",
        "*.pyo",
        ".DS_Store",
    }

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # Add root files
        for rf in root_files:
            file_path = repo_root / rf
            if file_path.is_file():
                zf.write(file_path, arcname=rf)

        # Add directory contents
        for d in include_dirs:
            dir_path = repo_root / d
            if not dir_path.is_dir():
                continue
            for item in dir_path.rglob("*"):
                if item.is_file():
                    # Check exclusions
                    if any(part in exclude_patterns for part in item.parts):
                        continue
                    if item.name.endswith((".pyc", ".pyo")):
                        continue
                    arcname = item.relative_to(repo_root).as_posix()
                    zf.write(item, arcname=arcname)

    # Generate checksum file
    write_sha256_file(bundle_path)

    return bundle_path


def verify_plugin_bundle(bundle_path: Path) -> dict[str, Any]:
    """
    Verify the integrity and contents of an AI Agent Plugin zip bundle.

    Args:
        bundle_path: Path to the .zip archive.

    Returns:
        Dict with validation status, counts, and errors.
    """
    if not bundle_path.exists():
        return {"valid": False, "error": f"Bundle file does not exist: {bundle_path}"}

    errors: list[str] = []
    files: list[str] = []
    skills: list[str] = []
    agents: list[str] = []

    try:
        with zipfile.ZipFile(bundle_path, "r") as zf:
            files = zf.namelist()
            for name in files:
                # Track skills
                if name.startswith("skills/") and name.endswith("SKILL.md"):
                    parts = name.split("/")
                    if len(parts) >= 3:
                        skills.append(parts[1])
                # Track agents
                elif name.startswith("agents/") and name.endswith(".md"):
                    agents.append(Path(name).stem)
    except Exception as exc:
        return {"valid": False, "error": f"Invalid zip archive: {exc}"}

    if "plugin.json" not in files:
        errors.append("Missing plugin.json manifest")
    if "rules/AGENTS.md" not in files:
        errors.append("Missing rules/AGENTS.md")

    return {
        "valid": len(errors) == 0,
        "bundle": str(bundle_path),
        "files": files,
        "total_files": len(files),
        "skills_count": len(skills),
        "skills": sorted(skills),
        "agents_count": len(agents),
        "agents": sorted(agents),
        "errors": errors,
    }


def build_python_distributions(repo_root: Path, output_dir: Path) -> list[Path]:
    """
    Build wheel and sdist distributions using uv or the build package.

    Args:
        repo_root: Path to the repository root.
        output_dir: Destination directory.

    Returns:
        List of generated distribution paths.
    """
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = ["uv", "build", "--out-dir", str(output_dir)]
    try:
        subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        # Fallback to python -m build if uv is not on PATH
        cmd = [sys.executable, "-m", "build", "--outdir", str(output_dir)]
        subprocess.run(cmd, cwd=repo_root, check=True, capture_output=True, text=True)

    generated: list[Path] = []
    for pattern in ("*.whl", "*.tar.gz"):
        for p in output_dir.glob(pattern):
            write_sha256_file(p)
            generated.append(p)

    return generated


def build_all(
    repo_root: Path,
    output_dir: Path,
    plugin_only: bool = False,
    python_only: bool = False,
) -> dict[str, Any]:
    """
    Build release artifacts according to configuration flags.

    Args:
        repo_root: Repository root path.
        output_dir: Target output directory.
        plugin_only: If True, only build the AI Agent Plugin zip.
        python_only: If True, only build Python wheel and sdist.

    Returns:
        Summary dict of created artifacts.
    """
    results: dict[str, Any] = {
        "output_dir": str(output_dir),
        "artifacts": [],
    }

    if not python_only:
        plugin_zip = build_plugin_bundle(repo_root, output_dir)
        verification = verify_plugin_bundle(plugin_zip)
        results["plugin_bundle"] = str(plugin_zip)
        results["plugin_verification"] = verification
        results["artifacts"].append(plugin_zip)

    if not plugin_only:
        py_dists = build_python_distributions(repo_root, output_dir)
        results["python_distributions"] = [str(p) for p in py_dists]
        results["artifacts"].extend(py_dists)

    return results


def cmd_package(args: argparse.Namespace) -> int:
    """CLI handler for sf package."""
    root = Path.cwd()
    output_dir = Path(getattr(args, "output_dir", "dist")).resolve()
    plugin_only = getattr(args, "plugin_only", False)
    python_only = getattr(args, "python_only", False)

    print(f"📦 SciFi Release Packager v{scifi.__version__}")
    print(f"   Root: {root}")
    print(f"   Output: {output_dir}")

    try:
        results = build_all(
            repo_root=root,
            output_dir=output_dir,
            plugin_only=plugin_only,
            python_only=python_only,
        )

        print("\n✅ Build succeeded! Generated artifacts:")
        for artifact in results.get("artifacts", []):
            art_path = Path(artifact)
            size_kb = art_path.stat().st_size / 1024.0
            print(f"   - {art_path.name} ({size_kb:.1f} KB)")
            sha_file = art_path.with_name(art_path.name + ".sha256")
            if sha_file.exists():
                hash_val = sha_file.read_text(encoding="utf-8").strip().split()[0]
                print(f"     SHA256: {hash_val[:16]}...{hash_val[-8:]}")

        pv = results.get("plugin_verification")
        if pv:
            print("\n🧩 Plugin Bundle Metrics:")
            print(f"   Skills packaged: {pv.get('skills_count')}")
            print(f"   Agents packaged: {pv.get('agents_count')}")
            print(f"   Total bundle entries: {pv.get('total_files')}")

        return 0
    except Exception as exc:
        print(f"\n❌ Packaging failed: {exc}", file=sys.stderr)
        return 1
