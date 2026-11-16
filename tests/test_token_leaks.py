"""Regression tests for MCP payload compaction and persistent RegistryCache wiring."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from scifi.argus.models import AttributionCategory, AttributionFinding, SuggestedAction
from scifi.argus.searcher import ArgusSearcher
from scifi.cache import RegistryCache
from scifi.citation_verifier.bib_auditor import search_identifier_by_title
from scifi.citation_verifier.fetchers import resolve_citation
from scifi.citation_verifier.models import (
    Author,
    BibAuditReport,
    CitationMetadata,
    VerificationStatus,
)
from scifi.literature.extractor import extract_pdf_text
from scifi.literature.models import AuthorRecord, PaperRecord
from scifi.literature.store import LiteratureStore
from scifi.server import (
    scifi_audit_bib,
    scifi_audit_manuscript,
    scifi_audit_orwell,
    scifi_check_notation,
    scifi_compile_latex,
    scifi_extract_pdf_text,
    scifi_map_literature,
    scifi_query_store,
    scifi_search_literature,
)


class TestMCPPayloadCompaction(unittest.TestCase):
    """Verify MCP tools omit duplicate/bloated payloads by default."""

    def test_extract_pdf_text_deduplicates_sections(self):
        payload = {
            "status": "SUCCESS",
            "total_pages": 5,
            "abstract": "Abs",
            "system_model_or_method": "Method",
            "limitations_and_conclusion": "Limits",
            "raw_sample": "Sample",
            "sections": {
                "total_pages": 5,
                "abstract": "Abs",
                "system_model_or_method": "Method",
                "limitations_and_conclusion": "Limits",
                "raw_sample": "Sample",
            },
        }
        with patch("scifi.server.extract_pdf_text", return_value=payload):
            res = scifi_extract_pdf_text("paper.pdf")
        self.assertEqual(res["abstract"], "Abs")
        self.assertNotIn("sections", res)

    def test_compile_latex_strips_raw_log_by_default(self):
        payload = {
            "status": "SUCCESS",
            "pdf_generated": True,
            "log": "very long latexmk log...",
            "errors": [],
        }
        with patch("scifi.server.compile_latex", return_value=payload):
            compact_res = scifi_compile_latex("main.tex")
            full_res = scifi_compile_latex("main.tex", include_raw_log=True)
        self.assertNotIn("log", compact_res)
        self.assertIn("log", full_res)

    def test_audit_bib_omits_verified_and_summary_by_default(self):
        verified = CitationMetadata(
            identifier_type="doi",
            identifier_value="10.1000/v",
            status=VerificationStatus.VERIFIED,
            title="Verified Paper",
        )
        retracted = CitationMetadata(
            identifier_type="doi",
            identifier_value="10.1000/r",
            status=VerificationStatus.RETRACTED,
            title="Retracted Paper",
            is_retracted=True,
        )
        report = BibAuditReport(
            file_path="refs.bib",
            total_entries=2,
            verified_count=1,
            retracted_count=1,
            entries=[verified, retracted],
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            bib_path = Path(tmpdir) / "refs.bib"
            bib_path.write_text("@article{a, title={x}}", encoding="utf-8")
            with patch("scifi.server.audit_bib_file", return_value=report):
                res = scifi_audit_bib(str(bib_path))
                self.assertEqual(len(res["entries"]), 1)
                self.assertEqual(res["entries"][0]["status"], "RETRACTED")
                self.assertEqual(res["verified_entries_omitted"], 1)
                self.assertNotIn("summary", res)

                full_res = scifi_audit_bib(str(bib_path), include_verified=True, include_summary=True)
                self.assertEqual(len(full_res["entries"]), 2)
                self.assertIn("summary", full_res)

    def test_audit_orwell_and_manuscript_omit_markdown_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "paper.tex"
            tex_path.write_text(
                r"\documentclass{article}\begin{document}Hello world.\end{document}",
                encoding="utf-8",
            )
            orwell_res = scifi_audit_orwell(str(tex_path))
            self.assertNotIn("report_markdown", orwell_res)
            orwell_full = scifi_audit_orwell(str(tex_path), include_markdown=True)
            self.assertIn("report_markdown", orwell_full)

            doc_res = scifi_audit_manuscript(str(tex_path))
            self.assertNotIn("report_markdown", doc_res)

    def test_map_literature_compact_papers_by_default(self):
        paper = PaperRecord(
            id="p1",
            title="Seed Paper",
            year=2024,
            abstract="Long abstract " * 50,
            authors=[AuthorRecord(id="a1", name="Alice Smith")],
            venue_name="NeurIPS",
            citation_count=42,
        )
        mock_store = MagicMock()
        mock_store.get_graph_gaps.return_value = {}
        mock_store.get_graph_evidence.return_value = {}
        mock_store.get_graph_benchmark_results.return_value = {}
        mock_store.get_graph_benchmarks.return_value = {}
        mock_store.get_graph_metrics.return_value = {}
        mock_store.get_graph_conditions.return_value = {}

        mock_crawler = MagicMock()
        mock_crawler.crawl_lineage.return_value = ("g1", [paper], [])
        mock_crawler.compute_topological_depths.return_value = {"p1": 0}

        with (
            patch("scifi.server.get_literature_store", return_value=mock_store),
            patch("scifi.server.LineageCrawler", return_value=mock_crawler),
        ):
            res = scifi_map_literature("Seed Paper")
        self.assertEqual(len(res["papers"]), 1)
        self.assertNotIn("abstract", res["papers"][0])
        self.assertEqual(res["papers"][0]["authors"], ["Alice Smith"])

    def test_query_store_enforces_max_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "lit.db"
            store = LiteratureStore(db_path)
            with store._lock:
                for i in range(10):
                    store.conn.execute(
                        "INSERT INTO papers (id, title, year) VALUES (?, ?, ?)",
                        (f"p{i}", f"Title {i}", 2020 + i),
                    )
                store.conn.commit()
            rows = store.execute_read_query("SELECT id, title FROM papers", max_rows=3)
            self.assertEqual(len(rows), 3)
            store.close()

            with patch("scifi.server.get_literature_store") as mock_get_store:
                mock_store = LiteratureStore(db_path)
                mock_get_store.return_value = mock_store
                mcp_rows = scifi_query_store("SELECT id FROM papers", max_rows=4)
                mock_store.close()
            self.assertEqual(len(mcp_rows), 4)

    def test_check_notation_omits_symbol_manifest_by_default(self):
        tex = "\\section{Intro}\nLet $x$ and $y$ be scalars."
        compact_res = scifi_check_notation(tex)
        self.assertEqual(compact_res["status"], "VALID")
        self.assertNotIn("symbol_manifest", compact_res)
        full_res = scifi_check_notation(tex, include_manifest=True)
        self.assertEqual(full_res["status"], "VALID")
        self.assertIn("symbol_manifest", full_res)

    def test_audit_attribution_compacts_candidate_work_by_default(self):
        meta = CitationMetadata(
            identifier_type="doi",
            identifier_value="10.1000/test",
            status=VerificationStatus.VERIFIED,
            canonical_doi="10.1000/test",
            title="Test Method",
            authors=[Author(name=f"Author {i}", family=f"F{i}", given=f"G{i}") for i in range(7)],
            year=2024,
            venue="ICML",
        )
        finding = AttributionFinding(
            id="ARGUS-001",
            line_number=10,
            text_snippet="We use Test Method.",
            matched_entity="Test Method",
            category=AttributionCategory.CANONICAL_ACADEMIC,
            suggested_action=SuggestedAction.CITE,
            confidence=0.9,
            remediation_hint="Cite Test Method.",
            candidate_work=meta,
            bibtex_entry=meta.to_bibtex(key="Author2024Test"),
            cite_key="Author2024Test",
        )
        compact = finding.to_dict()
        self.assertIsInstance(compact["candidate_work"], dict)
        self.assertNotIn("bibtex", compact["candidate_work"])
        self.assertNotIn("apa", compact["candidate_work"])
        self.assertEqual(len(compact["candidate_work"]["authors"]), 5)

        full = finding.to_dict(compact_candidate=False)
        self.assertIn("bibtex", full["candidate_work"])
        self.assertIn("apa", full["candidate_work"])
        self.assertEqual(len(full["candidate_work"]["authors"]), 7)

    def test_search_literature_omits_duplicate_bibtex_and_caps_authors_by_default(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "title": "Many Author Paper",
                    "doi": "https://doi.org/10.1000/many",
                    "authorships": [{"author": {"display_name": f"Author {i}"}} for i in range(8)],
                    "publication_year": 2024,
                    "primary_location": {"source": {"display_name": "NeurIPS"}},
                    "cited_by_count": 50,
                }
            ]
        }
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        with (
            patch("scifi.server.get_cache", return_value=mock_cache),
            patch("scifi.server.requests.get", return_value=mock_resp),
        ):
            compact = scifi_search_literature("Many Author Paper", limit=1)
            self.assertEqual(len(compact), 1)
            self.assertNotIn("bibtex", compact[0])
            self.assertEqual(len(compact[0]["authors"]), 5)
            self.assertEqual(compact[0]["total_authors"], 8)

            full = scifi_search_literature("Many Author Paper", limit=1, include_bibtex=True)
            self.assertIn("bibtex", full[0])

    def test_orwell_omits_raw_list_and_table_inventories_by_default(self):
        tex = (
            "\\documentclass{article}\\begin{document}\n"
            "\\begin{itemize}\n"
            "\\item \\textbf{First:} A short item.\n"
            "\\item \\textbf{Second:} Another short item.\n"
            "\\end{itemize}\n"
            "\\begin{tabular}{ll} A & B \\\\ C & D \\\\ \\end{tabular}\n"
            "\\end{document}\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "paper.tex"
            tex_path.write_text(tex, encoding="utf-8")
            compact = scifi_audit_orwell(str(tex_path))
            self.assertNotIn("all_lists", compact["dimensions"]["list_environments"])
            self.assertNotIn("all_tables", compact["dimensions"]["tabular"])

            full = scifi_audit_orwell(str(tex_path), include_raw_inventory=True)
            self.assertIn("all_lists", full["dimensions"]["list_environments"])
            self.assertIn("all_tables", full["dimensions"]["tabular"])

    def test_doctor_disables_render_previews_by_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "main.tex"
            tex_path.write_text(
                r"\documentclass{article}\begin{document}Hello world.\end{document}",
                encoding="utf-8",
            )
            with (
                patch(
                    "scifi.doctor.audit_figure_accessibility",
                    return_value={"issues": [], "clean_score": 100},
                ) as mock_fig,
                patch("scifi.doctor.audit_trim_budget") as mock_trim,
            ):
                mock_trim.return_value.to_dict.return_value = {"suggestions": [], "total_potential_lines_saved": 0}
                scifi_audit_manuscript(str(tex_path))
                mock_fig.assert_called_once()
                mock_trim.assert_called_once()
                self.assertFalse(mock_fig.call_args.kwargs.get("render_previews"))
                self.assertFalse(mock_trim.call_args.kwargs.get("render_previews"))


class TestPersistentCaching(unittest.TestCase):
    """Verify RegistryCache is used across citation_verifier, argus, and extractor."""

    def test_resolve_citation_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = RegistryCache(db_path=Path(tmpdir) / "cache.db")
            meta = CitationMetadata(
                identifier_type="doi",
                identifier_value="10.1000/test",
                status=VerificationStatus.VERIFIED,
                canonical_doi="10.1000/test",
                title="Cached Paper",
                authors=[Author(name="Jane Doe")],
                year=2023,
            )
            with (
                patch(
                    "scifi.citation_verifier.fetchers.CrossRefFetcher.fetch", return_value={"title": ["Cached Paper"]}
                ) as mock_cr,
                patch("scifi.citation_verifier.fetchers.CrossRefFetcher.parse_metadata", return_value=meta),
                patch("scifi.citation_verifier.fetchers.OpenAlexFetcher.fetch", return_value=None),
            ):
                first = resolve_citation("doi", "10.1000/test", cache=cache)
                second = resolve_citation("doi", "10.1000/test", cache=cache)
                self.assertEqual(first.title, "Cached Paper")
                self.assertEqual(second.title, "Cached Paper")
                mock_cr.assert_called_once()

    def test_search_identifier_by_title_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = RegistryCache(db_path=Path(tmpdir) / "cache.db")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"results": [{"doi": "https://doi.org/10.1000/xyz"}]}
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp

            with patch("scifi.citation_verifier.bib_auditor.get_session", return_value=mock_session):
                r1 = search_identifier_by_title("Some Unique Paper Title", cache=cache)
                r2 = search_identifier_by_title("Some Unique Paper Title", cache=cache)
                self.assertEqual(r1, ("doi", "10.1000/xyz"))
                self.assertEqual(r2, ("doi", "10.1000/xyz"))
                mock_session.get.assert_called_once()

    def test_argus_searcher_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = RegistryCache(db_path=Path(tmpdir) / "cache.db")
            searcher = ArgusSearcher(cache=cache)
            meta = CitationMetadata(
                identifier_type="doi",
                identifier_value="10.1000/adam",
                status=VerificationStatus.VERIFIED,
                canonical_doi="10.1000/adam",
                title="Adam Optimizer",
                authors=[Author(name="Diederik Kingma")],
                year=2015,
            )
            with patch.object(searcher, "_search_openalex", return_value=(meta, 0.95)) as mock_oa:
                r1 = searcher.search_canonical_work("Adam optimizer")
                r2 = searcher.search_canonical_work("Adam optimizer")
                self.assertIsNotNone(r1)
                self.assertIsNotNone(r2)
                self.assertEqual(r2[0].title, "Adam Optimizer")
                mock_oa.assert_called_once()

    def test_extract_pdf_text_uses_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_file = Path(tmpdir) / "dummy.pdf"
            pdf_file.write_bytes(b"%PDF-1.4\n")
            cache = RegistryCache(db_path=Path(tmpdir) / "cache.db")

            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Abstract\nHello.\nI. Introduction\nWorld."
            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]

            with patch("scifi.literature.extractor.PdfReader", return_value=mock_reader) as mock_cls:
                r1 = extract_pdf_text(pdf_file, cache=cache)
                r2 = extract_pdf_text(pdf_file, cache=cache)
                self.assertEqual(r1["status"], "SUCCESS")
                self.assertEqual(r2["abstract"], r1["abstract"])
                mock_cls.assert_called_once()


if __name__ == "__main__":
    unittest.main()
