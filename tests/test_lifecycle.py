"""Tests for SciFi installation, upgrade, and migration lifecycle."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import scifi
from scifi.cache import RegistryCache
from scifi.cli import main as cli_main
from scifi.config import CONFIG_SCHEMA_VERSION, load_global_config, migrate_global_config, migrate_global_config_file
from scifi.lifecycle import check_for_update, detect_install_mode, ensure_migrated_on_startup, perform_upgrade
from scifi.literature.store import LiteratureStore
from scifi.setup_cli import check_rules_sync_status, install_mcp_config, sync_rule_file


def test_store_forward_migration_creates_backup_and_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "literature_store.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE papers (id TEXT PRIMARY KEY, title TEXT NOT NULL, year INTEGER)")
    conn.execute("INSERT INTO papers (id, title, year) VALUES ('p1', 'Legacy Paper', 2020)")
    conn.execute("CREATE TABLE benchmarks (id TEXT PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE benchmark_results (id TEXT PRIMARY KEY, benchmark_id TEXT)")
    conn.execute("PRAGMA user_version = 0")
    conn.commit()
    conn.close()

    store = LiteratureStore(db_path)
    try:
        ver = store.conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver == LiteratureStore.LATEST_SCHEMA_VERSION
        cols = {row[1] for row in store.conn.execute("PRAGMA table_info(papers)").fetchall()}
        assert "venue_name" in cols
        assert "venue_tier" in cols
        row = store.conn.execute("SELECT title, year FROM papers WHERE id = 'p1'").fetchone()
        assert tuple(row) == ("Legacy Paper", 2020)
        bcols = {row[1] for row in store.conn.execute("PRAGMA table_info(benchmarks)").fetchall()}
        assert "canonical_url" in bcols
    finally:
        store.conn.close()

    backup = tmp_path / "literature_store.db.bak.v0"
    assert backup.is_file()


def test_global_config_migration_preserves_keys_and_stamps_version(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"email": "user@example.edu", "default-venue": "ieee"}),
        encoding="utf-8",
    )

    migrated, changed = migrate_global_config({"email": "user@example.edu", "default-venue": "ieee"})
    assert changed is True
    assert migrated["config_version"] == CONFIG_SCHEMA_VERSION
    assert migrated["default_venue"] == "ieee"
    assert migrated["email"] == "user@example.edu"

    assert migrate_global_config_file(cfg_path) is True
    loaded = load_global_config(cfg_path)
    assert loaded["config_version"] == CONFIG_SCHEMA_VERSION
    assert loaded["default_venue"] == "ieee"


def test_cache_invalidates_on_version_bump(tmp_path: Path) -> None:
    db_path = tmp_path / "cache.db"
    cache = RegistryCache(db_path)
    cache.set("doi:10.1000/test", {"title": "Old Cached"})
    assert cache.get("doi:10.1000/test") == {"title": "Old Cached"}

    with patch.object(scifi, "__version__", "9.9.9"):
        cache2 = RegistryCache(db_path)
        assert cache2.get("doi:10.1000/test") is None


def test_detect_install_mode_variants(tmp_path: Path) -> None:
    uvx_info = detect_install_mode(
        prefix="C:/Users/u/AppData/Local/uv/cache/archive-v0/abc",
        executable="C:/Users/u/AppData/Local/uv/cache/archive-v0/abc/Scripts/python.exe",
        package_root=tmp_path,
    )
    assert uvx_info["mode"] == "uvx"
    assert uvx_info["upgrade_command"] is None

    uv_tool_info = detect_install_mode(
        prefix="C:/Users/u/AppData/Roaming/uv/tools/scifi",
        executable="C:/Users/u/AppData/Roaming/uv/tools/scifi/Scripts/python.exe",
        package_root=tmp_path,
    )
    assert uv_tool_info["mode"] == "uv_tool"
    assert uv_tool_info["upgrade_command"] == ["uv", "tool", "upgrade", "scifi"]

    (tmp_path / "pyproject.toml").write_text("[project]\nname='scifi'\n", encoding="utf-8")
    (tmp_path / "scifi").mkdir()
    editable_info = detect_install_mode(
        prefix=str(tmp_path / ".venv"),
        executable=str(tmp_path / ".venv" / "python.exe"),
        package_root=tmp_path,
    )
    assert editable_info["mode"] == "editable"
    assert editable_info["upgrade_command"] == ["git", "pull", "--ff-only"]

    pip_root = tmp_path / "site_pkg"
    pip_root.mkdir()
    pip_info = detect_install_mode(
        prefix="/usr/local",
        executable="/usr/local/bin/python",
        package_root=pip_root,
    )
    assert pip_info["mode"] == "pip"
    assert pip_info["upgrade_command"] == ["/usr/local/bin/python", "-m", "pip", "install", "--upgrade", "scifi"]


def test_ensure_migrated_on_startup_tracks_version(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"email": "a@b.com"}), encoding="utf-8")

    assert ensure_migrated_on_startup(state_path=state_path, config_path=cfg_path) is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["last_run_version"] == scifi.__version__
    assert json.loads(cfg_path.read_text(encoding="utf-8"))["config_version"] == CONFIG_SCHEMA_VERSION
    assert ensure_migrated_on_startup(state_path=state_path, config_path=cfg_path) is False


def test_cli_version_and_upgrade_commands(capsys: pytest.CaptureFixture[str]) -> None:
    rc_ver = cli_main(["--version"])
    assert rc_ver == 0
    assert scifi.__version__ in capsys.readouterr().out

    rc = cli_main(["upgrade", "--dry-run"])
    assert rc == 0
    assert "[DRY-RUN]" in capsys.readouterr().out

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"info": {"version": "99.0.0"}}
    mock_resp.raise_for_status.return_value = None
    with patch("scifi.lifecycle.requests.get", return_value=mock_resp):
        res = check_for_update()
        assert res["update_available"] is True
        assert res["latest"] == "99.0.0"
        assert perform_upgrade(check_only=True) == 0


def test_install_mcp_config_preserves_corrupt_and_bak_files(tmp_path: Path) -> None:
    corrupt_cfg = tmp_path / "corrupt.json"
    corrupt_cfg.write_text("{not valid json", encoding="utf-8")
    assert install_mcp_config(corrupt_cfg, use_uvx=True) is True
    assert list(tmp_path.glob("corrupt.json.corrupt.*"))
    assert json.loads(corrupt_cfg.read_text(encoding="utf-8"))["mcpServers"]["scifi"]["command"] == "uvx"

    # Modify again with a different command to trigger .bak
    assert install_mcp_config(corrupt_cfg, use_uvx=False, scifi_root=tmp_path) is True
    assert (tmp_path / "corrupt.json.bak").is_file()


def test_check_rules_sync_status(tmp_path: Path) -> None:
    agents_md = tmp_path / "AGENTS.md"
    sync_rule_file(agents_md, "Canonical rules text")
    # Default load_canonical_rules falls back to DEFAULT_CANONICAL_RULES when rules/AGENTS.md isn't in tmp_path
    status_stale = check_rules_sync_status(tmp_path)
    assert status_stale["total_marked"] == 1
    assert status_stale["out_of_sync"] == ["AGENTS.md"]

    from scifi.setup_cli import load_canonical_rules

    sync_rule_file(agents_md, load_canonical_rules(tmp_path))
    status_ok = check_rules_sync_status(tmp_path)
    assert status_ok["in_sync"] == ["AGENTS.md"]
    assert status_ok["out_of_sync"] == []
