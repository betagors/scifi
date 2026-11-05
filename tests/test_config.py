"""
Unit tests for centralized configuration manager (scifi.config).
"""

from __future__ import annotations

from pathlib import Path
import pytest

from scifi.config import (
    generate_scifi_toml_template,
    get_user_agent,
    load_global_config,
    resolve_config,
    set_global_config_value,
)


def test_global_and_workspace_config_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    global_cfg_file = tmp_path / "global_config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(global_cfg_file))

    set_global_config_value("email", "alice@mit.edu")
    set_global_config_value("default_venue", "neurips")
    set_global_config_value("author_whitelist", "Alice Smith, Bob Jones")

    loaded = load_global_config()
    assert loaded["email"] == "alice@mit.edu"
    assert loaded["author_whitelist"] == ["Alice Smith", "Bob Jones"]

    # Create workspace with scifi.toml overriding venue and adding an author
    ws = tmp_path / "paper_repo"
    ws.mkdir()
    toml_content = generate_scifi_toml_template(
        main_tex="ms.tex",
        bib_file="refs.bib",
        target_venue="ieee",
        double_blind=True,
    )
    (ws / "scifi.toml").write_text(toml_content, encoding="utf-8")

    resolved = resolve_config(workspace_dir=ws)
    assert resolved.email == "alice@mit.edu"
    assert resolved.main_tex == "ms.tex"
    assert resolved.bib_file == "refs.bib"
    assert resolved.target_venue == "ieee"
    assert resolved.double_blind is True
    assert "Alice Smith" in resolved.author_whitelist

    ua = get_user_agent(workspace_dir=ws)
    assert "mailto:alice@mit.edu" in ua
