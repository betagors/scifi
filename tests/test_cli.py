"""
Unit and integration tests for the unified SciFi CLI (scifi.cli) and automated setup installer (scifi.setup_cli).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

import scifi.cli
import scifi.setup_cli


def test_cli_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Test top-level CLI help displays usage and subcommands."""
    ret = scifi.cli.main(["--help"])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "usage: scifi" in captured
    for subcmd in ["verify", "audit", "search", "argus", "setup", "compile", "server"]:
        assert subcmd in captured


def test_cli_no_args_shows_help(capsys: pytest.CaptureFixture[str]) -> None:
    """Invoking scifi without arguments should print help and exit cleanly with 0."""
    ret = scifi.cli.main([])
    assert ret == 0
    captured = capsys.readouterr().out
    assert "usage: scifi" in captured


def test_cli_subcommand_helps(capsys: pytest.CaptureFixture[str]) -> None:
    """Test individual subcommand help screens."""
    # verify help
    ret_verify = scifi.cli.main(["verify", "--help"])
    assert ret_verify == 0
    assert "query" in capsys.readouterr().out

    # audit help
    ret_audit = scifi.cli.main(["audit", "--help"])
    assert ret_audit == 0
    assert "bib_file" in capsys.readouterr().out

    # search help
    ret_search = scifi.cli.main(["search", "--help"])
    assert ret_search == 0
    assert "title" in capsys.readouterr().out

    # argus help
    ret_argus = scifi.cli.main(["argus", "--help"])
    assert ret_argus == 0
    assert "file" in capsys.readouterr().out

    # setup help
    ret_setup = scifi.cli.main(["setup", "--help"])
    assert ret_setup == 0
    captured_setup = capsys.readouterr().out
    assert "--auto" in captured_setup
    assert "--dry-run" in captured_setup
    assert "--list" in captured_setup

    # compile help
    ret_compile = scifi.cli.main(["compile", "--help"])
    assert ret_compile == 0
    assert "tex_file" in capsys.readouterr().out

    # server help
    ret_server = scifi.cli.main(["server", "--help"])
    assert ret_server == 0
    assert "--transport" in capsys.readouterr().out


def test_setup_list_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """setup --list should display supported environments and exit 0."""
    code = scifi.cli.main(["setup", "--list"])
    assert code == 0
    captured = capsys.readouterr().out
    assert "Supported AI environments" in captured
    assert "OpenCode" in captured
    assert "Claude Code" in captured
    assert "VS Code Cline" in captured


def test_setup_validate_server() -> None:
    """Validate that scifi.server can be successfully imported by setup preflight."""
    assert scifi.setup_cli.validate_scifi_server() is True


def test_setup_detect_environments_when_present(tmp_path: Path) -> None:
    """Detect environments when target parent directories exist."""
    mock_home = tmp_path / "home"
    mock_appdata = tmp_path / "appdata"
    mock_project = tmp_path / "project"

    # Create directories indicating installed environments
    (mock_home / ".gemini").mkdir(parents=True)
    (mock_appdata / "Claude").mkdir(parents=True)
    (mock_project / ".cursor").mkdir(parents=True)
    (mock_home / ".claude").mkdir(parents=True)
    (mock_appdata / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev" / "settings").mkdir(parents=True)
    (mock_appdata / "Code" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings").mkdir(parents=True)
    (mock_home / ".config" / "opencode").mkdir(parents=True)
    (mock_home / ".codeium" / "windsurf").mkdir(parents=True)

    envs = scifi.setup_cli.detect_environments(
        home_dir=mock_home,
        appdata_dir=mock_appdata,
        project_dir=mock_project,
        check_path=False,
    )

    names = {e.name: e for e in envs}
    assert "Antigravity" in names
    assert names["Antigravity"].detected is True
    assert names["Antigravity"].config_path == mock_home / ".gemini" / "config" / "mcp_config.json"

    assert "Claude Desktop" in names
    assert names["Claude Desktop"].detected is True

    assert "Claude Code (Global)" in names
    assert names["Claude Code (Global)"].detected is True

    assert "Cursor" in names
    assert names["Cursor"].detected is True
    assert names["Cursor"].config_path == mock_project / ".cursor" / "mcp.json"

    assert "VS Code Cline" in names
    assert names["VS Code Cline"].detected is True

    assert "VS Code Roo Code" in names
    assert names["VS Code Roo Code"].detected is True

    assert "OpenCode (Global)" in names
    assert names["OpenCode (Global)"].detected is True
    assert names["OpenCode (Global)"].format_type == "opencode"

    assert "Windsurf" in names
    assert names["Windsurf"].detected is True


def test_setup_detect_environments_when_absent(tmp_path: Path) -> None:
    """Detect environments when target directories do not exist."""
    mock_home = tmp_path / "home"
    mock_appdata = tmp_path / "appdata"
    mock_project = tmp_path / "project"

    envs = scifi.setup_cli.detect_environments(
        home_dir=mock_home,
        appdata_dir=mock_appdata,
        project_dir=mock_project,
        check_path=False,
    )

    for e in envs:
        assert e.detected is False
        assert e.installed is False


def test_setup_install_mcp_config_creates_new_file(tmp_path: Path) -> None:
    """install_mcp_config should create missing directories and write configuration."""
    target_cfg = tmp_path / "config_dir" / "mcp_config.json"
    fake_scifi_root = tmp_path / "scifi_repo"
    fake_scifi_root.mkdir()

    assert not target_cfg.exists()

    success = scifi.setup_cli.install_mcp_config(
        target=target_cfg,
        scifi_root=fake_scifi_root,
        dry_run=False,
    )

    assert success is True
    assert target_cfg.exists()

    data = json.loads(target_cfg.read_text(encoding="utf-8"))
    assert "mcpServers" in data
    assert "scifi" in data["mcpServers"]
    entry = data["mcpServers"]["scifi"]
    assert entry["command"] == "uv"
    assert entry["args"] == ["run", "python", "-m", "scifi.server"]
    assert entry["cwd"] == str(fake_scifi_root.resolve())


def test_setup_install_mcp_config_preserves_existing_servers(tmp_path: Path) -> None:
    """install_mcp_config should preserve existing servers and custom properties."""
    target_cfg = tmp_path / "mcp_config.json"
    initial_data = {
        "theme": "dark",
        "mcpServers": {
            "existing-server": {
                "command": "node",
                "args": ["dist/index.js"],
            }
        },
    }
    target_cfg.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    fake_scifi_root = tmp_path / "scifi_repo"
    fake_scifi_root.mkdir()

    success = scifi.setup_cli.install_mcp_config(
        target=target_cfg,
        scifi_root=fake_scifi_root,
        dry_run=False,
    )

    assert success is True
    data = json.loads(target_cfg.read_text(encoding="utf-8"))
    assert data["theme"] == "dark"
    assert "existing-server" in data["mcpServers"]
    assert "scifi" in data["mcpServers"]


def test_setup_install_mcp_config_dry_run(tmp_path: Path) -> None:
    """install_mcp_config with dry_run=True must not modify disk."""
    target_cfg = tmp_path / "nonexistent" / "mcp_config.json"

    success = scifi.setup_cli.install_mcp_config(
        target=target_cfg,
        scifi_root=tmp_path,
        dry_run=True,
    )

    assert success is True
    assert not target_cfg.exists()
    assert not target_cfg.parent.exists()


def test_setup_install_opencode_schema(tmp_path: Path) -> None:
    """install_mcp_config with format_type='opencode' must format using 'mcp' dict and flat command."""
    target_cfg = tmp_path / "opencode.json"
    fake_scifi_root = tmp_path / "scifi_repo"
    fake_scifi_root.mkdir()

    success = scifi.setup_cli.install_mcp_config(
        target=target_cfg,
        scifi_root=fake_scifi_root,
        dry_run=False,
        format_type="opencode",
    )

    assert success is True
    assert target_cfg.exists()
    data = json.loads(target_cfg.read_text(encoding="utf-8"))
    assert "mcp" in data
    assert "scifi" in data["mcp"]
    entry = data["mcp"]["scifi"]
    assert entry["type"] == "local"
    assert entry["command"] == ["uv", "run", "python", "-m", "scifi.server"]
    assert entry["cwd"] == str(fake_scifi_root.resolve())


def test_setup_install_opencode_preserves_existing(tmp_path: Path) -> None:
    """install_mcp_config for OpenCode must preserve existing properties and tools."""
    target_cfg = tmp_path / "opencode.json"
    initial_data = {
        "model": "claude-3-5-sonnet",
        "mcp": {
            "custom-tool": {
                "type": "local",
                "command": ["echo", "hello"],
            }
        },
    }
    target_cfg.write_text(json.dumps(initial_data, indent=2), encoding="utf-8")

    success = scifi.setup_cli.install_mcp_config(
        target=target_cfg,
        scifi_root=tmp_path,
        dry_run=False,
        format_type="opencode",
    )

    assert success is True
    data = json.loads(target_cfg.read_text(encoding="utf-8"))
    assert data["model"] == "claude-3-5-sonnet"
    assert "custom-tool" in data["mcp"]
    assert "scifi" in data["mcp"]



def test_setup_cmd_setup_target_flag(tmp_path: Path) -> None:
    """cmd_setup with --target should configure specific file directly."""
    target_cfg = tmp_path / "custom" / "mcp.json"
    args = argparse.Namespace(
        target=str(target_cfg),
        auto=False,
        dry_run=False,
        scifi_root=str(tmp_path),
    )

    code = scifi.setup_cli.cmd_setup(args)
    assert code == 0
    assert target_cfg.exists()
    data = json.loads(target_cfg.read_text(encoding="utf-8"))
    assert "scifi" in data["mcpServers"]


def test_setup_cmd_setup_auto_flow(tmp_path: Path) -> None:
    """cmd_setup with --auto should install to all detected environments."""
    mock_home = tmp_path / "home"
    (mock_home / ".gemini").mkdir(parents=True)

    mock_envs = [
        scifi.setup_cli.TargetEnvironment(
            name="Antigravity",
            config_path=mock_home / ".gemini" / "config" / "mcp_config.json",
            detected=True,
            installed=False,
        )
    ]

    with patch("scifi.setup_cli.detect_environments", return_value=mock_envs):
        args = argparse.Namespace(
            target=None,
            auto=True,
            dry_run=False,
            scifi_root=str(tmp_path),
        )
        code = scifi.setup_cli.cmd_setup(args)
        assert code == 0
        assert (mock_home / ".gemini" / "config" / "mcp_config.json").exists()


def test_cli_routes_to_verify() -> None:
    """scifi verify routes to scifi.citation_verifier.cli.cmd_verify."""
    with patch("scifi.citation_verifier.cli.cmd_verify", return_value=0) as mock_verify:
        code = scifi.cli.main(["verify", "10.1038/nature12373"])
        assert code == 0
        mock_verify.assert_called_once()
        args = mock_verify.call_args[0][0]
        assert args.query == "10.1038/nature12373"


def test_cli_routes_to_audit() -> None:
    """scifi audit routes to scifi.citation_verifier.cli.cmd_audit."""
    with patch("scifi.citation_verifier.cli.cmd_audit", return_value=0) as mock_audit:
        code = scifi.cli.main(["audit", "references.bib", "--no-search"])
        assert code == 0
        mock_audit.assert_called_once()
        args = mock_audit.call_args[0][0]
        assert args.bib_file == "references.bib"
        assert args.no_search is True


def test_cli_routes_to_search() -> None:
    """scifi search routes to scifi.citation_verifier.cli.cmd_search."""
    with patch("scifi.citation_verifier.cli.cmd_search", return_value=0) as mock_search:
        code = scifi.cli.main(["search", "Attention Is All You Need", "--verify"])
        assert code == 0
        mock_search.assert_called_once()
        args = mock_search.call_args[0][0]
        assert args.title == "Attention Is All You Need"
        assert args.verify is True


def test_cli_routes_to_argus() -> None:
    """scifi argus routes to scifi.argus.cli.cmd_audit."""
    with patch("scifi.argus.cli.cmd_audit", return_value=0) as mock_argus:
        code = scifi.cli.main(["argus", "paper.tex", "--fix"])
        assert code == 0
        mock_argus.assert_called_once()
        args = mock_argus.call_args[0][0]
        assert args.file == "paper.tex"
        assert args.fix is True


def test_cli_routes_to_setup() -> None:
    """scifi setup routes to scifi.setup_cli.cmd_setup."""
    with patch("scifi.setup_cli.cmd_setup", return_value=0) as mock_setup:
        code = scifi.cli.main(["setup", "--auto", "--dry-run"])
        assert code == 0
        mock_setup.assert_called_once()
        args = mock_setup.call_args[0][0]
        assert args.auto is True
        assert args.dry_run is True


def test_cli_routes_to_server() -> None:
    """scifi server routes to mcp.run()."""
    with patch("scifi.server.mcp.run") as mock_run:
        code = scifi.cli.main(["server"])
        assert code == 0
        mock_run.assert_called_once_with(transport="stdio")


def test_cli_subcommand_aliases(capsys: pytest.CaptureFixture[str]) -> None:
    """Test subcommand aliases: v, a, s, c, mcp, init, cite."""
    # verify alias: v
    assert scifi.cli.main(["v", "--help"]) == 0
    assert "query" in capsys.readouterr().out

    # audit alias: a
    assert scifi.cli.main(["a", "--help"]) == 0
    assert "bib_file" in capsys.readouterr().out

    # search alias: s
    assert scifi.cli.main(["s", "--help"]) == 0
    assert "title" in capsys.readouterr().out

    # compile alias: c
    assert scifi.cli.main(["c", "--help"]) == 0
    assert "tex_file" in capsys.readouterr().out

    # server alias: mcp
    assert scifi.cli.main(["mcp", "--help"]) == 0
    assert "--transport" in capsys.readouterr().out

    # setup alias: init
    assert scifi.cli.main(["init", "--help"]) == 0
    assert "--auto" in capsys.readouterr().out

    # route alias test: v routes to verify
    with patch("scifi.cli.citation_cli.cmd_verify", return_value=0) as mock_verify:
        assert scifi.cli.main(["v", "10.1038/s41586-020-2649-2"]) == 0
        mock_verify.assert_called_once()
        assert mock_verify.call_args[0][0].query == "10.1038/s41586-020-2649-2"
