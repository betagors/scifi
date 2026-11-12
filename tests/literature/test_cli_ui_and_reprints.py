"""
Tests for SciFi CLI commands (`sf ui`, `sf literature sync`, `sf literature reprint`,
`sf literature reprints`, `sf literature ingest-pdf`) and FastMCP server tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scifi.cli import create_parser, main
from scifi.literature.models import PaperRecord
from scifi.literature.store import LiteratureStore
from scifi.server import (
    mcp,
    scifi_draft_reprint_request,
    scifi_get_project_summary,
    scifi_ingest_paper_pdf,
    scifi_list_pending_reprints,
    scifi_list_projects,
)

# ---------------------------------------------------------------------------
# 1. FastMCP Tool Tests
# ---------------------------------------------------------------------------


def test_mcp_tools_registered():
    """Verify all 5 new literature and reprint tools are decorated and registered in FastMCP."""
    tool_names = [
        "scifi_list_projects",
        "scifi_get_project_summary",
        "scifi_draft_reprint_request",
        "scifi_list_pending_reprints",
        "scifi_ingest_paper_pdf",
    ]
    # FastMCP tools can be inspected via mcp.get_tools() or internal tool manager
    registered = {t.name for t in mcp._tool_manager._tools.values()}
    for name in tool_names:
        assert name in registered, f"FastMCP tool '{name}' is not registered."


def test_mcp_projects_and_reprints_tools(tmp_path: Path):
    """Verify scifi_list_projects, scifi_get_project_summary, scifi_draft_reprint_request."""
    db_path = tmp_path / "central_store.db"
    store = LiteratureStore(db_path)

    # Register sample project and papers
    proj = store.register_project("test-proj", str(tmp_path / "workspace"))
    p1 = PaperRecord(id="10.1016/j.neucom.2023.12345", title="Neural Computing Survey", year=2023)
    store.upsert_paper(p1)
    store.link_paper_to_project(proj.id, p1.id)

    with patch("scifi.server.get_literature_store", return_value=store):
        # 1. Projects listing
        projects = scifi_list_projects()
        assert isinstance(projects, list)
        assert len(projects) == 1
        assert projects[0]["name"] == "test-proj"
        assert projects[0]["id"] == proj.id

        # 2. Project summary
        summary = scifi_get_project_summary(project_name_or_path="test-proj")
        assert summary["status"] == "SUCCESS"
        assert summary["project"]["name"] == "test-proj"
        assert summary["total_papers"] == 1

        # 3. Draft reprint request tool
        draft = scifi_draft_reprint_request("10.1016/j.neucom.2023.12345", project_name="test-proj")
        assert draft["status"] in ("DRAFT_READY", "ERROR")
        if draft["status"] == "DRAFT_READY":
            assert "subject" in draft
            assert "body" in draft
            assert "mailto_url" in draft
            assert "Neural Computing Survey" in draft["subject"] or "10.1016/j.neucom.2023.12345" in draft["subject"]

        # 4. List pending reprints
        pending = scifi_list_pending_reprints(project_name="test-proj")
        assert isinstance(pending, list)
        assert len(pending) == 1
        assert pending[0]["paper_id"] == "10.1016/j.neucom.2023.12345"
        assert pending[0]["status"] == "DRAFT_READY"

        # 5. Ingest PDF tool
        sample_pdf = tmp_path / "sample.pdf"
        sample_pdf.write_bytes(b"%PDF-1.4 mock content for reprint test")
        storage_dir = tmp_path / "storage"

        with patch("scifi.literature.reprint.DEFAULT_STORAGE_DIR", storage_dir):
            ingest_res = scifi_ingest_paper_pdf(
                identifier="10.1016/j.neucom.2023.12345",
                pdf_path=str(sample_pdf),
                project_name="test-proj",
            )
            assert ingest_res["status"] == "SUCCESS"
            assert "sha256" in ingest_res
            assert Path(ingest_res["stored_path"]).exists()

            # Reprint status should now be RECEIVED
            reprints_now = store.get_reprint_requests(project_id=proj.id)
            assert reprints_now[0].status == "RECEIVED"

            # Pending reprints should now be empty
            pending_now = scifi_list_pending_reprints(project_name="test-proj")
            assert len(pending_now) == 0


def test_mcp_project_summary_not_found(tmp_path: Path):
    """Verify scifi_get_project_summary returns NOT_FOUND for non-existent project."""
    db_path = tmp_path / "central_store.db"
    store = LiteratureStore(db_path)

    with patch("scifi.server.get_literature_store", return_value=store):
        summary = scifi_get_project_summary("non_existent_project_xyz")
        assert summary["status"] == "NOT_FOUND"


# ---------------------------------------------------------------------------
# 2. CLI Parser & Command Tests
# ---------------------------------------------------------------------------


def test_cli_parser_ui_command():
    """Verify `sf ui` parser arguments and defaults."""
    parser = create_parser()
    args = parser.parse_args(["ui", "--port", "9090", "--no-browser", "--host", "0.0.0.0"])
    assert args.command == "ui"
    assert args.port == 9090
    assert args.no_browser is True
    assert args.host == "0.0.0.0"


def test_cli_cmd_ui_invocation(tmp_path: Path):
    """Verify `sf ui` invokes SciFiWebServer and handles no-browser flag."""
    parser = create_parser()
    parser.parse_args(["ui", "--no-browser", "--port", "8888", "--db", str(tmp_path / "ui.db")])

    with patch("scifi.cli.SciFiWebServer") as mock_server_cls, patch("webbrowser.open") as mock_browser_open:
        mock_instance = MagicMock()
        mock_instance.port = 8888
        mock_instance.serve_forever.side_effect = KeyboardInterrupt()
        mock_server_cls.return_value = mock_instance

        exit_code = main(["ui", "--no-browser", "--port", "8888", "--db", str(tmp_path / "ui.db")])
        assert exit_code == 0
        assert mock_server_cls.called
        assert not mock_browser_open.called
        assert mock_instance.server_close.called


def test_cli_literature_sync(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Verify `sf literature sync` synchronizes workspace and regenerates manifest and bib."""
    ws = tmp_path / "my_project"
    ws.mkdir()
    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)

    # Pre-populate store with a paper
    proj = store.register_project("my_project", ws)
    p = PaperRecord(id="10.1000/sync_test", title="Sync Paper", year=2024)
    store.upsert_paper(p)
    store.link_paper_to_project(proj.id, p.id)

    exit_code = main(["literature", "sync", "--workspace", str(ws), "--db", str(db_path)])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "[SUCCESS] Synchronized workspace" in captured.out
    assert (ws / ".scifi" / "literature_manifest.json").exists()
    assert (ws / ".scifi" / "references.bib").exists()


def test_cli_literature_reprint_and_reprints(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Verify `sf literature reprint` and `sf literature reprints` CLI workflows."""
    ws = tmp_path / "repo"
    ws.mkdir()
    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)

    proj = store.register_project("repo", ws)
    p = PaperRecord(id="10.1016/j.paywalled.2024", title="Paywalled Quantum ML", year=2024)
    store.upsert_paper(p)
    store.link_paper_to_project(proj.id, p.id)

    # 1. Draft reprint request via CLI
    code_reprint = main(
        [
            "literature",
            "reprint",
            "10.1016/j.paywalled.2024",
            "--project",
            str(ws),
            "--name",
            "Alice Physicist",
            "--email",
            "alice@lab.edu",
            "--db",
            str(db_path),
        ]
    )
    assert code_reprint == 0
    cap1 = capsys.readouterr()
    assert "[SUCCESS] Reprint draft ready" in cap1.out
    assert "Alice Physicist" in cap1.out
    assert "alice@lab.edu" in cap1.out

    # 2. List reprints via CLI table
    code_list = main(["literature", "reprints", "--project", str(ws), "--db", str(db_path)])
    assert code_list == 0
    cap2 = capsys.readouterr()
    assert "DRAFT_READY" in cap2.out
    assert "Alice Physicist" in cap2.out

    # 3. List reprints via CLI JSON
    code_json = main(["literature", "reprints", "--project", str(ws), "--db", str(db_path), "--json"])
    assert code_json == 0
    cap3 = capsys.readouterr()
    data = json.loads(cap3.out)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["author_email"] == "alice@lab.edu"


def test_cli_literature_ingest_pdf(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    """Verify `sf literature ingest-pdf` command."""
    ws = tmp_path / "repo"
    ws.mkdir()
    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)

    store.register_project("repo", ws)
    paper_pdf = tmp_path / "paper.pdf"
    paper_pdf.write_bytes(b"%PDF-1.4 test bytes")

    storage_dir = tmp_path / "pdf_storage"

    with patch("scifi.literature.reprint.DEFAULT_STORAGE_DIR", storage_dir):
        code = main(
            [
                "literature",
                "ingest-pdf",
                "--doi",
                "10.1000/ingested_paper",
                "--pdf",
                str(paper_pdf),
                "--project",
                str(ws),
                "--db",
                str(db_path),
            ]
        )
        assert code == 0

        cap = capsys.readouterr()
        assert "[SUCCESS] Ingested PDF for 10.1000/ingested_paper" in cap.out

        # Verify record in store
        locs = store.get_paper_locations("10.1000/ingested_paper")
        assert len(locs) >= 1
        assert locs[0].is_oa is True
        assert locs[0].is_accessible is True


def test_subdirectory_project_resolution_in_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify that _resolve_project_id walks up parent directories to match a workspace."""
    from scifi.literature.cli import _resolve_project_id

    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)
    workspace = tmp_path / "project_root"
    subdir = workspace / "subfolder" / "deep"
    subdir.mkdir(parents=True)

    proj = store.register_project("root_proj", workspace)

    monkeypatch.chdir(subdir)
    resolved_id = _resolve_project_id(store, project_name_or_path=None)
    assert resolved_id == proj.id


def test_subdirectory_project_resolution_with_scifi_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify that _resolve_project_id discovers an unindexed parent with .scifi/ folder."""
    from scifi.literature.cli import _resolve_project_id

    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)
    workspace = tmp_path / "unindexed_proj"
    scifi_dir = workspace / ".scifi"
    scifi_dir.mkdir(parents=True)
    subdir = workspace / "paper" / "sections"
    subdir.mkdir(parents=True)

    monkeypatch.chdir(subdir)
    resolved_id = _resolve_project_id(store, project_name_or_path=None)
    assert resolved_id is not None
    proj = store.get_project(resolved_id)
    assert proj is not None
    assert proj.name == "unindexed_proj"


def test_subdirectory_project_resolution_in_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verify that _resolve_project in server.py walks up parent directories."""
    from scifi.server import _resolve_project

    db_path = tmp_path / "central.db"
    store = LiteratureStore(db_path)
    workspace = tmp_path / "server_proj"
    subdir = workspace / "code" / "analysis"
    subdir.mkdir(parents=True)

    proj = store.register_project("server_proj", workspace)

    monkeypatch.chdir(subdir)
    resolved_proj = _resolve_project(store, project_name_or_path=None)
    assert resolved_proj is not None
    assert resolved_proj.id == proj.id
