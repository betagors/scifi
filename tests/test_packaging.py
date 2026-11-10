"""
Tests for SciFi packaging, resource bundling, and version consistency.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import pytest

import scifi
from scifi.setup_cli import load_canonical_rules


def test_version_consistency():
    """Verify that Python package, plugin.json, and gemini-extension.json versions match."""
    root = Path(__file__).resolve().parent.parent
    py_version = scifi.__version__

    plugin_file = root / "plugin.json"
    if plugin_file.exists():
        data = json.loads(plugin_file.read_text(encoding="utf-8"))
        assert data.get("version") == py_version, f"plugin.json version mismatch: {data.get('version')} != {py_version}"

    gemini_file = root / "gemini-extension.json"
    if gemini_file.exists():
        data = json.loads(gemini_file.read_text(encoding="utf-8"))
        assert data.get("version") == py_version, f"gemini-extension.json version mismatch: {data.get('version')} != {py_version}"


def test_rules_file_parity():
    """Verify rules/AGENTS.md and scifi/resources/AGENTS.md exist and are strictly identical."""
    root = Path(__file__).resolve().parent.parent
    source_rules = root / "rules" / "AGENTS.md"
    packaged_rules = root / "scifi" / "resources" / "AGENTS.md"

    assert source_rules.exists(), "rules/AGENTS.md must exist in repository root"
    assert packaged_rules.exists(), "scifi/resources/AGENTS.md must exist as a packaged resource"

    source_text = source_rules.read_text(encoding="utf-8").strip()
    packaged_text = packaged_rules.read_text(encoding="utf-8").strip()
    assert source_text == packaged_text, "scifi/resources/AGENTS.md must be identical to rules/AGENTS.md"


def test_load_canonical_rules_from_packaged_resource(monkeypatch, tmp_path):
    """Verify load_canonical_rules loads all 12 rules even without any repository root."""
    monkeypatch.chdir(tmp_path)
    rules_text = load_canonical_rules(project_root=tmp_path)

    # Must contain full 12 rules, not the 4-rule stub
    assert "## 12. Academic Paper Packaging & Submission Suite" in rules_text
    assert "Master Academic Humanizer Protocol" in rules_text

    rule_headers = re.findall(r"^## \d+\.", rules_text, flags=re.MULTILINE)
    assert len(rule_headers) == 12, f"Expected 12 rules, got {len(rule_headers)}"


def test_wheel_package_hygiene():
    """Verify built wheel does not leak top-level skills/ and contains scifi/resources/AGENTS.md."""
    import zipfile
    root = Path(__file__).resolve().parent.parent
    dist_dir = root / "dist"
    wheels = list(dist_dir.glob("*.whl"))
    if not wheels:
        pytest.skip("No wheel built in dist/ to inspect")

    latest_wheel = sorted(wheels, key=lambda p: p.stat().st_mtime)[-1]
    with zipfile.ZipFile(latest_wheel, "r") as zf:
        namelist = zf.namelist()
        skills_entries = [n for n in namelist if n.startswith("skills/") or n.startswith("skills\\")]
        assert len(skills_entries) == 0, f"Found rogue skills entries in wheel: {skills_entries}"
        assert "scifi/resources/AGENTS.md" in namelist, "scifi/resources/AGENTS.md missing in wheel"


def test_build_and_verify_plugin_bundle(tmp_path):
    """Verify build_plugin_bundle creates a valid scifi-plugin-v*.zip archive."""
    from scifi.packaging import build_plugin_bundle, verify_plugin_bundle

    root = Path(__file__).resolve().parent.parent
    bundle_path = build_plugin_bundle(repo_root=root, output_dir=tmp_path)

    assert bundle_path.exists(), f"Bundle file {bundle_path} was not created"
    assert bundle_path.name.startswith("scifi-plugin-v")
    assert bundle_path.name.endswith(".zip")

    # Verify sha256 checksum file was generated
    checksum_file = bundle_path.with_name(bundle_path.name + ".sha256")
    assert checksum_file.exists()
    assert len(checksum_file.read_text(encoding="utf-8").strip().split()) >= 1

    # Verify archive content
    verification = verify_plugin_bundle(bundle_path)
    assert verification["valid"] is True
    assert verification["skills_count"] >= 17
    assert verification["agents_count"] >= 6
    assert "plugin.json" in verification["files"]
    assert "rules/AGENTS.md" in verification["files"]
    assert "assets/logo.svg" in verification["files"]
