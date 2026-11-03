"""
Unit and integration tests for Literature CLI subcommands (scifi literature / lit)
and FastMCP server tools (scifi_map_literature, scifi_query_store, scifi_export_bibtex).
"""

from __future__ import annotations

from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

import pytest

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import scifi.cli
from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    GraphSessionRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
)
from scifi.literature.store import LiteratureStore


def _make_sample_paper(paper_id: str = "W123", title: str = "Attention Is All You Need", year: int = 2017) -> PaperRecord:
    return PaperRecord(
        id=paper_id,
        title=title,
        year=year,
        citation_count=1000,
        authors=[AuthorRecord(id="A1", name="Ashish Vaswani")],
        identifiers=[PaperIdentifierRecord(paper_id=paper_id, provider="openalex", external_id=paper_id, is_canonical=True)],
        locations=[PaperLocationRecord(id="L1", paper_id=paper_id, location_type="repository", is_oa=True, oa_status="gold")],
    )


class TestLiteratureCLISubcommands:
    """Verify CLI parsing, help output, and dispatching for 'scifi literature' / 'scifi lit'."""

    def test_top_level_help_lists_literature(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "literature" in captured

    def test_literature_help_shows_subcommands(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["literature", "--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "report" in captured
        assert "map" in captured
        assert "db" in captured

    def test_lit_alias_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["lit", "--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "report" in captured
        assert "map" in captured

    def test_report_subcommand_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["literature", "report", "--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "query" in captured
        assert "--depth" in captured
        assert "--max-papers" in captured
        assert "--output-dir" in captured
        assert "--open" in captured

    def test_map_subcommand_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["literature", "map", "--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "query" in captured
        assert "--output-dir" in captured
        assert "--open" in captured

    def test_db_subcommand_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["literature", "db", "--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "list-graphs" in captured
        assert "export-bib" in captured

    def test_db_export_bib_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["literature", "db", "export-bib", "--help"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "--graph-id" in captured
        assert "--output" in captured or "-o" in captured

    def test_literature_no_subcommand_shows_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        ret = scifi.cli.main(["literature"])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "report" in captured or "usage: scifi literature" in captured

    def test_literature_report_execution(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        sample_paper = _make_sample_paper()
        sample_cite = CitationRecord(source_paper_id="W123", target_paper_id="W000")

        with patch("scifi.literature.cli.LineageCrawler") as mock_crawler_cls:
            instance = mock_crawler_cls.return_value
            instance.crawl_lineage.return_value = ("graph-test-1", [sample_paper], [sample_cite])
            instance.compute_topological_depths.return_value = {"W123": 0}

            db_path = tmp_path / "test.db"
            out_dir = tmp_path / "report_out"

            ret = scifi.cli.main([
                "literature", "report", "Attention",
                "--output-dir", str(out_dir),
                "--db", str(db_path),
            ])
            assert ret == 0
            captured = capsys.readouterr().out
            assert "[SUCCESS]" in captured or "Literature report generated" in captured

            assert (out_dir / "literature_report.md").exists()
            assert (out_dir / "literature_map.html").exists()
            assert (out_dir / "references.bib").exists()

    def test_literature_map_execution(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        sample_paper = _make_sample_paper()

        with patch("scifi.literature.cli.LineageCrawler") as mock_crawler_cls:
            instance = mock_crawler_cls.return_value
            instance.crawl_lineage.return_value = ("graph-map-1", [sample_paper], [])
            instance.compute_topological_depths.return_value = {"W123": 0}

            db_path = tmp_path / "test.db"
            out_dir = tmp_path / "map_out"

            ret = scifi.cli.main([
                "literature", "map", "1706.03762",
                "--output-dir", str(out_dir),
                "--db", str(db_path),
            ])
            assert ret == 0
            assert (out_dir / "literature_map.html").exists()

    def test_literature_map_open_flag(self, tmp_path: Path) -> None:
        sample_paper = _make_sample_paper()

        with patch("scifi.literature.cli.LineageCrawler") as mock_crawler_cls, patch("webbrowser.open") as mock_wb_open:
            instance = mock_crawler_cls.return_value
            instance.crawl_lineage.return_value = ("graph-map-2", [sample_paper], [])
            instance.compute_topological_depths.return_value = {"W123": 0}

            out_dir = tmp_path / "map_open"
            ret = scifi.cli.main([
                "literature", "map", "Transformers",
                "--output-dir", str(out_dir),
                "--open",
                "--db", str(tmp_path / "db.sqlite"),
            ])
            assert ret == 0
            mock_wb_open.assert_called_once()

    def test_literature_report_seed_resolution_failure(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("scifi.literature.cli.LineageCrawler") as mock_crawler_cls:
            instance = mock_crawler_cls.return_value
            instance.crawl_lineage.return_value = ("graph-err", [], [])

            ret = scifi.cli.main([
                "literature", "report", "NonExistentPaperXYZ123",
                "--output-dir", str(tmp_path / "empty"),
                "--db", str(tmp_path / "db.sqlite"),
            ])
            assert ret != 0
            captured = capsys.readouterr().err + capsys.readouterr().out
            assert "Could not resolve" in captured or "No papers" in captured

    def test_db_list_graphs_empty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path = tmp_path / "store.db"
        # Initialized store without graphs
        LiteratureStore(db_path).close()

        ret = scifi.cli.main(["literature", "db", "list-graphs", "--db", str(db_path)])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "No literature graphs" in captured or "0 graph" in captured

    def test_db_list_graphs_populated(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path = tmp_path / "store.db"
        store = LiteratureStore(db_path)
        store.create_or_get_graph("g-101", "Attention Mechanisms in NLP", "W123")
        store.close()

        ret = scifi.cli.main(["literature", "db", "list-graphs", "--db", str(db_path)])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "g-101" in captured
        assert "Attention Mechanisms" in captured

    def test_db_export_bib(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path = tmp_path / "store.db"
        store = LiteratureStore(db_path)
        store.create_or_get_graph("g-202", "Graph Session 202")
        paper = _make_sample_paper("W123", "Attention Is All You Need", 2017)
        store.save_paper(paper, graph_id="g-202")
        store.close()

        out_bib = tmp_path / "exported.bib"
        ret = scifi.cli.main([
            "literature", "db", "export-bib",
            "--graph-id", "g-202",
            "-o", str(out_bib),
            "--db", str(db_path),
        ])
        assert ret == 0
        assert out_bib.exists()
        content = out_bib.read_text(encoding="utf-8")
        assert "@" in content
        assert "Vaswani" in content

    def test_db_export_bib_missing_graph(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        db_path = tmp_path / "store.db"
        LiteratureStore(db_path).close()

        out_bib = tmp_path / "missing.bib"
        ret = scifi.cli.main([
            "literature", "db", "export-bib",
            "--graph-id", "non-existent-graph",
            "-o", str(out_bib),
            "--db", str(db_path),
        ])
        assert ret != 0
        captured = capsys.readouterr().err + capsys.readouterr().out
        assert "No papers found" in captured or "ERROR" in captured


class TestFastMCPLiteratureTools:
    """Verify FastMCP server tool exposure, execution, and security guards."""

    def test_tools_registered_on_mcp_server(self) -> None:
        from scifi.server import mcp

        registered = set(mcp._tool_manager._tools.keys())
        assert "scifi_map_literature" in registered
        assert "scifi_query_store" in registered
        assert "scifi_export_bibtex" in registered

    def test_tools_have_documentation(self) -> None:
        from scifi.server import mcp

        for name in ("scifi_map_literature", "scifi_query_store", "scifi_export_bibtex"):
            tool = mcp._tool_manager._tools[name]
            assert bool(tool.description and tool.description.strip())
            assert tool.parameters is not None

    def test_scifi_map_literature_tool(self, tmp_path: Path) -> None:
        from scifi.server import scifi_map_literature

        sample_paper = _make_sample_paper()
        sample_cite = CitationRecord(source_paper_id="W123", target_paper_id="W000")

        with patch("scifi.server.LineageCrawler") as mock_crawler_cls:
            instance = mock_crawler_cls.return_value
            instance.crawl_lineage.return_value = ("graph-tool-1", [sample_paper], [sample_cite])
            instance.compute_topological_depths.return_value = {"W123": 0}

            out_dir = tmp_path / "mcp_map_out"
            res = scifi_map_literature(
                query="Attention",
                depth=2,
                max_papers=10,
                graph_id="custom-graph-id",
                output_dir=str(out_dir),
            )

            assert res["status"] == "SUCCESS"
            assert res["graph_id"] == "graph-tool-1"
            assert res["total_papers"] == 1
            assert res["total_citations"] == 1
            assert len(res["papers"]) == 1
            assert res["files"] is not None
            assert Path(res["files"]["html_map"]).exists()
            assert Path(res["files"]["report_markdown"]).exists()
            assert Path(res["files"]["bibtex"]).exists()

    def test_scifi_query_store_read_only(self, tmp_path: Path) -> None:
        from scifi.server import scifi_query_store

        # Create temporary store and query it
        db_path = tmp_path / ".scifi" / "literature_store.db"
        store = LiteratureStore(db_path)
        store.create_or_get_graph("g-query-1", "Query Test Graph")
        store.close()

        with patch("scifi.server.get_literature_store", return_value=LiteratureStore(db_path)):
            rows = scifi_query_store("SELECT id, title FROM graphs WHERE id = 'g-query-1'")
            assert len(rows) == 1
            assert rows[0]["id"] == "g-query-1"
            assert rows[0]["title"] == "Query Test Graph"

    def test_scifi_query_store_rejects_mutations(self, tmp_path: Path) -> None:
        from scifi.server import scifi_query_store

        db_path = tmp_path / ".scifi" / "literature_store.db"
        LiteratureStore(db_path).close()

        with patch("scifi.server.get_literature_store", return_value=LiteratureStore(db_path)):
            with pytest.raises(PermissionError):
                scifi_query_store("DROP TABLE papers;")

            with pytest.raises(PermissionError):
                scifi_query_store("INSERT INTO graphs (id, title) VALUES ('hack', 'hack');")

            with pytest.raises(PermissionError):
                scifi_query_store("DELETE FROM graphs;")

    def test_scifi_export_bibtex_tool(self, tmp_path: Path) -> None:
        from scifi.server import scifi_export_bibtex

        db_path = tmp_path / ".scifi" / "literature_store.db"
        store = LiteratureStore(db_path)
        store.create_or_get_graph("g-exp", "Graph Export")
        store.save_paper(_make_sample_paper("W123", "Deep Learning", 2015), graph_id="g-exp")
        store.close()

        out_file = tmp_path / "tool_export.bib"
        with patch("scifi.server.get_literature_store", return_value=LiteratureStore(db_path)):
            res = scifi_export_bibtex("g-exp", str(out_file))
            assert res["status"] == "SUCCESS"
            assert res["total_entries"] == 1
            assert out_file.exists()
            assert "Deep Learning" in out_file.read_text(encoding="utf-8")

    def test_scifi_export_bibtex_missing_graph_tool(self, tmp_path: Path) -> None:
        from scifi.server import scifi_export_bibtex

        db_path = tmp_path / ".scifi" / "literature_store.db"
        LiteratureStore(db_path).close()

        out_file = tmp_path / "tool_missing.bib"
        with patch("scifi.server.get_literature_store", return_value=LiteratureStore(db_path)):
            res = scifi_export_bibtex("missing-graph", str(out_file))
            assert res["status"] == "ERROR"
            assert "No papers found" in res["message"]
