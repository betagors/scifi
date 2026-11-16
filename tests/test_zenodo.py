"""
Tests for SciFi Zenodo integration (config, dataset auth, deposit client, CLI, MCP tools).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scifi.cli import main
from scifi.config import resolve_config, set_global_config_value
from scifi.datasets.providers import ZenodoClient
from scifi.server import (
    scifi_zenodo_create_deposition,
    scifi_zenodo_list_depositions,
    scifi_zenodo_publish_deposition,
    scifi_zenodo_push_submission,
    scifi_zenodo_status,
)
from scifi.zenodo import ZenodoDepositClient


def _mock_response(payload: object, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    resp.raise_for_status.return_value = None
    return resp


def test_zenodo_token_config_and_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)

    set_global_config_value("zenodo-token", "tok_from_config", config_path=cfg_path)
    cfg = resolve_config(workspace_dir=tmp_path, global_config_path=cfg_path)
    assert cfg.zenodo_token == "tok_from_config"

    monkeypatch.setenv("ZENODO_TOKEN", "tok_from_env")
    cfg_env = resolve_config(workspace_dir=tmp_path, global_config_path=cfg_path)
    assert cfg_env.zenodo_token == "tok_from_env"


def test_datasets_zenodo_client_sends_bearer_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZENODO_TOKEN", "zen_secret_123")
    session = MagicMock()
    session.get.return_value = _mock_response(
        {
            "id": 999,
            "metadata": {"title": "Private Dataset", "creators": [{"name": "Doe, Jane"}]},
            "files": [{"key": "data.csv", "size": 12, "links": {"self": "https://zenodo.org/api/files/1/data.csv"}}],
        }
    )

    client = ZenodoClient(workspace_dir=tmp_path, session=session)
    info = client.get_record("999")
    assert info.title == "Private Dataset"
    _, kwargs = session.get.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer zen_secret_123"


def test_deposit_client_requires_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "empty_config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)

    client = ZenodoDepositClient(workspace_dir=tmp_path)
    st = client.status()
    assert st["configured"] is False
    assert st["connected"] is False
    with pytest.raises(RuntimeError, match="Zenodo API token is not configured"):
        client.list_depositions()


def test_deposit_client_full_workflow(tmp_path: Path) -> None:
    session = MagicMock()
    deposition_payload = {
        "id": 12345,
        "state": "unsubmitted",
        "submitted": False,
        "metadata": {
            "title": "Test Artifact",
            "upload_type": "software",
            "prereserve_doi": {"doi": "10.5281/zenodo.12345"},
            "creators": [{"name": "Doe, Jane"}],
        },
        "links": {
            "html": "https://zenodo.org/deposit/12345",
            "bucket": "https://zenodo.org/api/files/bucket-abc",
        },
        "files": [],
    }
    session.post.side_effect = [
        _mock_response(deposition_payload),  # create_deposition
        _mock_response(
            {**deposition_payload, "state": "done", "submitted": True, "doi": "10.5281/zenodo.12345"}
        ),  # publish
    ]
    session.get.return_value = _mock_response(deposition_payload)
    session.put.return_value = _mock_response(
        {
            "key": "code.zip",
            "size": 11,
            "checksum": "md5:abc",
            "links": {"self": "https://zenodo.org/api/files/bucket-abc/code.zip"},
        }
    )

    artifact = tmp_path / "code.zip"
    artifact.write_bytes(b"hello world")

    client = ZenodoDepositClient(token="zen_tok", workspace_dir=tmp_path, session=session)
    res = client.push_submission_artifacts(
        files=[artifact],
        title="Test Artifact",
        creators="Doe, Jane",
        publish=True,
    )
    assert res.deposition_id == 12345
    assert res.uploaded_files == ["code.zip"]
    assert res.published is True
    assert res.doi == "10.5281/zenodo.12345"


def test_cli_zenodo_login_and_publish_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)

    rc = main(["zenodo", "login", "--token", "tok_cli_1", "--no-verify", "--json"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["configured"] is True

    # Publish without --yes must fail safely
    rc_pub = main(["zenodo", "publish", "12345"])
    assert rc_pub == 1
    assert "--yes" in capsys.readouterr().err


def test_mcp_zenodo_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("ZENODO_TOKEN", raising=False)

    st = scifi_zenodo_status()
    assert st["configured"] is False

    with pytest.raises(ValueError, match="confirm=True"):
        scifi_zenodo_publish_deposition(12345, confirm=False)

    assert callable(scifi_zenodo_list_depositions)
    assert callable(scifi_zenodo_create_deposition)
    assert callable(scifi_zenodo_push_submission)
