"""Shared test isolation: never touch the developer's real Zotero library or config."""

import pytest

from scifi.literature.zotero.writer import ZoteroLocalWriter


@pytest.fixture(autouse=True)
def _isolate_zotero_and_cwd(tmp_path, monkeypatch):
    monkeypatch.setattr(ZoteroLocalWriter, "is_server_available", lambda self: False)
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(tmp_path / "scifi_config.json"))
    monkeypatch.chdir(tmp_path)
