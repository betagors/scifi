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


def test_setup_install_mcp_config_uvx_mode(tmp_path: Path) -> None:
    """install_mcp_config with use_uvx=True must emit zero-install uvx scifi server command."""
    # Standard format
    std_cfg = tmp_path / "claude_desktop_config.json"
    ok = scifi.setup_cli.install_mcp_config(
        target=std_cfg,
        use_uvx=True,
    )
    assert ok is True
    data = json.loads(std_cfg.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["scifi"]
    assert entry["command"] == "uvx"
    assert entry["args"] == ["scifi", "server"]

    # OpenCode format
    oc_cfg = tmp_path / "opencode.json"
    ok = scifi.setup_cli.install_mcp_config(
        target=oc_cfg,
        format_type="opencode",
        use_uvx=True,
    )
    assert ok is True
    oc_data = json.loads(oc_cfg.read_text(encoding="utf-8"))
    oc_entry = oc_data["mcp"]["scifi"]
    assert oc_entry["command"] == ["uvx", "scifi", "server"]


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


def test_setup_cmd_setup_use_uvx_flag(tmp_path: Path) -> None:
    """sf setup with --use-uvx should write uvx scifi server."""
    target_cfg = tmp_path / "custom" / "mcp.json"
    code = scifi.cli.main(["setup", "--target", str(target_cfg), "--use-uvx"])
    assert code == 0
    assert target_cfg.exists()
    data = json.loads(target_cfg.read_text(encoding="utf-8"))
    entry = data["mcpServers"]["scifi"]
    assert entry["command"] == "uvx"
    assert entry["args"] == ["scifi", "server"]


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


def test_rule_sync_new_file(tmp_path: Path) -> None:
    """sync_rule_file on a non-existent file should create it with marker bounds."""
    target = tmp_path / "CLAUDE.md"
    rule_content = "# SciFi Rules\nAlways verify DOIs."

    success = scifi.setup_cli.sync_rule_file(target, rule_content)
    assert success is True
    assert target.exists()

    content = target.read_text(encoding="utf-8")
    assert "<!-- SCIFI-RULES:START -->" in content
    assert "<!-- SCIFI-RULES:END -->" in content
    assert "# SciFi Rules" in content
    assert "Always verify DOIs." in content


def test_rule_sync_preserves_existing_user_instructions(tmp_path: Path) -> None:
    """sync_rule_file on an existing file without markers must append rules without destroying user text."""
    target = tmp_path / "CLAUDE.md"
    user_header = "# Custom User Instructions\n\nAlways use 2 spaces indentation."
    target.write_text(user_header, encoding="utf-8")

    rule_content = "# SciFi Invariants\nNever hallucinate citations."
    success = scifi.setup_cli.sync_rule_file(target, rule_content)

    assert success is True
    content = target.read_text(encoding="utf-8")
    assert "# Custom User Instructions" in content
    assert "Always use 2 spaces indentation." in content
    assert "<!-- SCIFI-RULES:START -->" in content
    assert "Never hallucinate citations." in content
    assert "<!-- SCIFI-RULES:END -->" in content


def test_rule_sync_idempotent_update(tmp_path: Path) -> None:
    """sync_rule_file on a file with existing markers must update between markers only."""
    target = tmp_path / ".clinerules"
    initial_text = (
        "# Custom Instructions\n\n"
        "<!-- SCIFI-RULES:START -->\n"
        "Old rules content\n"
        "<!-- SCIFI-RULES:END -->\n\n"
        "Footer note."
    )
    target.write_text(initial_text, encoding="utf-8")

    new_rule_content = "Updated new rules content"
    success = scifi.setup_cli.sync_rule_file(target, new_rule_content)

    assert success is True
    content = target.read_text(encoding="utf-8")
    assert "# Custom Instructions" in content
    assert "Footer note." in content
    assert "Old rules content" not in content
    assert "Updated new rules content" in content
    assert content.count("<!-- SCIFI-RULES:START -->") == 1
    assert content.count("<!-- SCIFI-RULES:END -->") == 1


def test_sync_all_rules(tmp_path: Path) -> None:
    """sync_all_rules should generate canonical rule files in the given project."""
    rule_files = scifi.setup_cli.sync_all_rules(project_root=tmp_path)
    file_names = {p.name for p in rule_files}

    assert "AGENTS.md" in file_names
    assert "CLAUDE.md" in file_names
    assert ".clinerules" in file_names
    assert ".cursorrules" in file_names
    assert ".windsurfrules" in file_names
    assert (tmp_path / ".github" / "copilot-instructions.md").exists()


def test_setup_cmd_rules_flag(tmp_path: Path) -> None:
    """setup --rules should trigger sync_all_rules in workspace."""
    args = argparse.Namespace(
        rules=True,
        workspace=False,
        auto=False,
        dry_run=False,
        target=None,
        scifi_root=None,
        list=False,
        project_dir=tmp_path,
    )
    code = scifi.setup_cli.cmd_setup(args)
    assert code == 0
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".clinerules").exists()


def test_setup_cmd_workspace_flag(tmp_path: Path) -> None:
    """setup --workspace should configure local MCP files and sync rules."""
    args = argparse.Namespace(
        rules=False,
        workspace=True,
        auto=False,
        dry_run=False,
        target=None,
        scifi_root=None,
        list=False,
        project_dir=tmp_path,
    )
    code = scifi.setup_cli.cmd_setup(args)
    assert code == 0
    assert (tmp_path / ".cursor" / "mcp.json").exists()
    assert (tmp_path / ".mcp.json").exists()
    assert (tmp_path / "opencode.json").exists()
    assert (tmp_path / "CLAUDE.md").exists()


def test_cli_routes_to_sync(tmp_path: Path) -> None:
    """sf sync should route to cmd_sync."""
    with patch("scifi.setup_cli.cmd_sync", return_value=0) as mock_sync:
        code = scifi.cli.main(["sync"])
        assert code == 0
        mock_sync.assert_called_once()



def test_cli_figures_subcommand(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}\begin{document}\end{document}", encoding="utf-8")
    code = scifi.cli.main(["figures", str(tex), "--json"])
    assert code == 0


def test_cli_trim_subcommand(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}\begin{document}\end{document}", encoding="utf-8")
    code = scifi.cli.main(["trim", str(tex), "--json"])
    assert code == 0


def test_cli_proofs_subcommand(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}\begin{document}\end{document}", encoding="utf-8")
    code = scifi.cli.main(["proofs", str(tex), "--json"])
    assert code == 0


def test_cli_repro_subcommand(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}\begin{document}\end{document}", encoding="utf-8")
    code = scifi.cli.main(["repro", str(tex), "--json"])
    assert code in (0, 1)


def test_cli_rebuttal_subcommand(tmp_path: Path) -> None:
    out = tmp_path / "rebuttal.md"
    code = scifi.cli.main(["rebuttal", "format", "--text", "Reviewer 1:\nGood work.", "--output", str(out)])
    assert code == 0
    assert out.exists()


def test_cli_submission_subcommands(tmp_path: Path) -> None:
    tex = tmp_path / "paper.tex"
    tex.write_text(r"\documentclass{article}\title{Test Paper}\begin{document}\end{document}", encoding="utf-8")
    
    # sf submission highlights
    hl_out = tmp_path / "highlights.md"
    code = scifi.cli.main(["submission", "highlights", "--bullets", "First major contribution.; Second empirical result.; Third analytical proof.", "--output", str(hl_out)])
    assert code == 0
    assert hl_out.exists()

    # sf submission title-page
    tp_out = tmp_path / "title_page.tex"
    code = scifi.cli.main(["submission", "title-page", "--target", str(tex), "--output", str(tp_out)])
    assert code == 0
    assert tp_out.exists()

    # sf submission letter
    let_out = tmp_path / "cover_letter.md"
    code = scifi.cli.main(["submission", "letter", "--target", str(tex), "--journal", "IEEE TPAMI", "--output", str(let_out)])
    assert code == 0
    assert let_out.exists()

    # sf submission bundle
    bundle_out = tmp_path / "dist" / "submission"
    code = scifi.cli.main(["submission", "bundle", "--target", str(tex), "--no-code", "--output", str(bundle_out)])
    assert code == 0
    assert (bundle_out / "submission_manifest.json").exists()


def test_cli_package_subcommand(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Test sf package CLI execution for plugin-only artifact generation."""
    out_dir = tmp_path / "pkg_dist"
    code = scifi.cli.main(["package", "--plugin-only", "--output-dir", str(out_dir)])
    assert code == 0

    captured = capsys.readouterr().out
    assert "SciFi Release Packager" in captured
    assert "Build succeeded!" in captured
    assert "Plugin Bundle Metrics:" in captured

    zips = list(out_dir.glob("scifi-plugin-*.zip"))
    assert len(zips) == 1
    assert zips[0].exists()
    assert (out_dir / f"{zips[0].name}.sha256").exists()

