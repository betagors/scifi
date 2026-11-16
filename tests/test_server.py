"""
Unit tests for FastMCP Server Daemon (scifi.server) and mcp_config.json.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scifi.cache import RegistryCache
from scifi.server import (
    mcp,
    scifi_audit_attribution,
    scifi_audit_bib,
    scifi_audit_claims,
    scifi_audit_statistics,
    scifi_check_convexity,
    scifi_check_limits,
    scifi_check_matrix_shapes,
    scifi_check_notation,
    scifi_check_units,
    scifi_compile_latex,
    scifi_extract_pdf_text,
    scifi_fetch_paper_pdf,
    scifi_search_literature,
    scifi_verify_citation,
    scifi_verify_curve,
    scifi_verify_derivation_step,
    scifi_verify_derivative,
)

EXPECTED_TOOLS = {
    "scifi_verify_citation",
    "scifi_audit_bib",
    "scifi_search_literature",
    "scifi_audit_attribution",
    "scifi_audit_claim_entailment",
    "scifi_verify_derivative",
    "scifi_verify_derivation_step",
    "scifi_check_units",
    "scifi_check_matrix_shapes",
    "scifi_check_limits",
    "scifi_check_convexity",
    "scifi_check_notation",
    "scifi_compile_latex",
    "scifi_compiler_info",
    "scifi_render_pdf",
    "scifi_verify_curve",
    "scifi_audit_statistics",
    "scifi_audit_claims",
    "scifi_fetch_paper_pdf",
    "scifi_fetch_structured_paper",
    "scifi_fetch_openreview_gaps",
    "scifi_synthesize_gaps",
    "scifi_extract_pdf_text",
    "scifi_map_literature",
    "scifi_query_store",
    "scifi_export_bibtex",
    "scifi_query_sota_benchmarks",
    "scifi_audit_manuscript",
    "scifi_evaluate_title_abstract",
    "scifi_generate_latex_table",
    "scifi_check_venue_compliance",
    "scifi_audit_orwell",
    "scifi_calibrate_orwell",
    "scifi_verify_edit_invariants",
    "scifi_audit_figures",
    "scifi_trim_budget",
    "scifi_audit_proofs",
    "scifi_audit_reproducibility",
    "scifi_format_rebuttal",
    "scifi_diff_manuscript",
    "scifi_generate_highlights",
    "scifi_generate_title_page",
    "scifi_generate_cover_letter",
    "scifi_package_anonymous_code",
    "scifi_prepare_submission_bundle",
    "scifi_list_projects",
    "scifi_get_project_summary",
    "scifi_draft_reprint_request",
    "scifi_list_pending_reprints",
    "scifi_ingest_paper_pdf",
    "scifi_zotero_status",
    "scifi_zotero_sync",
    "scifi_zotero_get_collection_papers",
    "scifi_zotero_search",
    "scifi_zotero_get_annotations",
    "scifi_zotero_push_audit_note",
    "scifi_kg_status",
    "scifi_kg_rebuild",
    "scifi_kg_query",
    "scifi_kg_trace_assumptions",
    "scifi_kg_delta_novelty",
    "scifi_kg_find_contradictions",
    "scifi_kg_upsert_fact",
    "scifi_datasets_dir",
    "scifi_datasets_list",
    "scifi_datasets_inspect",
    "scifi_datasets_search",
    "scifi_datasets_download",
    "scifi_kaggle_status",
    "scifi_kaggle_push_dataset",
    "scifi_kaggle_competition_list",
    "scifi_kaggle_competition_download",
    "scifi_kaggle_competition_submit",
    "scifi_kaggle_kernel_list",
    "scifi_kaggle_kernel_pull",
    "scifi_kaggle_kernel_push",
    "scifi_kaggle_kernel_status",
    "scifi_kaggle_kernel_output",
    "scifi_zenodo_status",
    "scifi_zenodo_list_depositions",
    "scifi_zenodo_get_deposition",
    "scifi_zenodo_create_deposition",
    "scifi_zenodo_update_metadata",
    "scifi_zenodo_upload_file",
    "scifi_zenodo_reserve_doi",
    "scifi_zenodo_publish_deposition",
    "scifi_zenodo_push_submission",
}


class TestFastMCPServerRegistry(unittest.TestCase):
    """Verify tool registration, schemas, and docstrings on FastMCP server."""

    def test_all_tools_registered(self):
        registered_tools = set(mcp._tool_manager._tools.keys())
        self.assertEqual(
            registered_tools,
            EXPECTED_TOOLS,
            f"Missing or unexpected tools: {EXPECTED_TOOLS ^ registered_tools}",
        )
        self.assertEqual(len(registered_tools), len(EXPECTED_TOOLS))

    def test_tools_have_docstrings_and_parameters(self):
        for tool_name in EXPECTED_TOOLS:
            tool = mcp._tool_manager._tools[tool_name]
            self.assertTrue(
                bool(tool.description and tool.description.strip()),
                f"Tool '{tool_name}' lacks a descriptive docstring.",
            )
            self.assertIsNotNone(
                tool.parameters,
                f"Tool '{tool_name}' lacks parameter schema.",
            )


class TestDirectToolExecution(unittest.TestCase):
    """Verify executing tool functions directly in Python."""

    def test_verify_derivative(self):
        res = scifi_verify_derivative("x**3 + 2*x", "x", "3*x**2 + 2")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_verify_derivation_step(self):
        res = scifi_verify_derivation_step("sin(x)**2 + cos(x)**2", "1")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_units(self):
        res = scifi_check_units("10 * meter", "1000 * centimeter")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_matrix_shapes(self):
        res = scifi_check_matrix_shapes("A * B", {"A": [3, 4], "B": [4, 5]})
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])
        self.assertEqual([str(x) for x in res["result_shape"]], ["3", "5"])

    def test_check_limits(self):
        res = scifi_check_limits(r"\sin(x)/x", "x", "0", "1")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_convexity(self):
        res = scifi_check_convexity("x**2 + 4", "x", claimed="convex")
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_check_notation(self):
        snippet = "Let $x$ be a scalar and $y$ be a scalar."
        res = scifi_check_notation(snippet)
        self.assertEqual(res["status"], "VALID")

    def test_audit_claims(self):
        text = "Our technique completely eliminates synchronization overhead."
        res = scifi_audit_claims(text)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["total_flags"], 1)

    def test_audit_statistics(self):
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        res = scifi_audit_statistics(samples)
        self.assertEqual(res["status"], "VALID")
        self.assertEqual(res["sample_size"], 5)
        self.assertFalse(res["is_statistically_sound"])
        self.assertIsNotNone(res.get("warning"))

    def test_verify_curve(self):
        res = scifi_verify_curve(
            formula_latex="2 * x + 1",
            var_name="x",
            x_vals=[0.0, 1.0, 2.0, 3.0],
            y_vals=[1.0, 3.0, 5.0, 7.0],
        )
        self.assertEqual(res["status"], "VALID")
        self.assertTrue(res["is_correct"])

    def test_compile_latex_mock(self):
        with patch("scifi.server.compile_latex") as mock_compile:
            mock_compile.return_value = {"status": "SUCCESS", "pdf_generated": True}
            res = scifi_compile_latex("main.tex")
            self.assertEqual(res["status"], "SUCCESS")
            mock_compile.assert_called_once_with(entrypoint="main.tex", engine="auto", clean=True)

    def test_fetch_paper_pdf_mock(self):
        with patch("scifi.server.fetch_paper_pdf") as mock_fetch:
            mock_fetch.return_value = {"status": "SUCCESS", "file_path": "workspace/paper.pdf"}
            res = scifi_fetch_paper_pdf("1706.03762", output_dir="workspace")
            self.assertEqual(res["status"], "SUCCESS")
            mock_fetch.assert_called_once_with(
                identifier="1706.03762", output_dir="workspace", email="researcher@scifi.org"
            )

            mock_fetch.reset_mock()
            res_default = scifi_fetch_paper_pdf("1706.03762")
            self.assertEqual(res_default["status"], "SUCCESS")
            self.assertEqual(mock_fetch.call_args.kwargs["identifier"], "1706.03762")
            self.assertNotEqual(mock_fetch.call_args.kwargs["output_dir"], "workspace")

    def test_extract_pdf_text_mock(self):
        with patch("scifi.server.extract_pdf_text") as mock_extract:
            mock_extract.return_value = {"status": "SUCCESS", "text": "Paper text"}
            res = scifi_extract_pdf_text("workspace/paper.pdf")
            self.assertEqual(res["status"], "SUCCESS")
            mock_extract.assert_called_once_with(pdf_path="workspace/paper.pdf", max_pages=20)


class TestCitationAndAttributionTools(unittest.TestCase):
    """Verify citation caching, literature search, bib audit, and Argus autofix."""

    def test_verify_citation_caching(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = Path(tmpdir) / "test_cache.db"
            cache = RegistryCache(db_path=cache_db)

            # Seed cache
            cached_data = {
                "identifier_type": "doi",
                "identifier_value": "10.1038/nature14539",
                "status": "VERIFIED",
                "canonical_doi": "10.1038/nature14539",
                "title": "Deep learning",
                "authors": [{"name": "Yann LeCun"}, {"name": "Yoshua Bengio"}, {"name": "Geoffrey Hinton"}],
                "year": 2015,
                "venue": "Nature",
                "discrepancies": [],
            }
            cache.set("citation:10.1038/nature14539", cached_data)

            with patch("scifi.server.get_cache", return_value=cache):
                with patch("scifi.server.verify_citation") as mock_verify:
                    res = scifi_verify_citation("10.1038/nature14539")
                    # Should return from cache without network verification
                    self.assertEqual(res["status"], "VERIFIED")
                    self.assertEqual(res["title"], "Deep learning")
                    mock_verify.assert_not_called()

    def test_verify_citation_stores_to_cache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = Path(tmpdir) / "test_cache.db"
            cache = RegistryCache(db_path=cache_db)

            from scifi.citation_verifier.models import CitationMetadata, VerificationStatus

            mock_meta = CitationMetadata(
                identifier_type="doi",
                identifier_value="10.1000/182",
                status=VerificationStatus.VERIFIED,
                title="Example DOI Title",
                year=2020,
            )

            with patch("scifi.server.get_cache", return_value=cache):
                with patch("scifi.server.verify_citation", return_value=mock_meta):
                    res = scifi_verify_citation("10.1000/182")
                    self.assertEqual(res["status"], "VERIFIED")
                    # Check that cache was populated
                    in_cache = cache.get("citation:10.1000/182")
                    self.assertIsNotNone(in_cache)
                    self.assertEqual(in_cache["title"], "Example DOI Title")

    def test_verify_citation_dynamic_discrepancy_does_not_pollute_cache(self):
        """Verify that dynamic discrepancy audit does not write MISMATCH into shared cache (Finding 1)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = Path(tmpdir) / "test_cache.db"
            cache = RegistryCache(db_path=cache_db)

            from scifi.citation_verifier.models import Author, CitationMetadata, VerificationStatus

            canonical_meta = CitationMetadata(
                identifier_type="doi",
                identifier_value="10.1000/canonical",
                status=VerificationStatus.VERIFIED,
                title="Canonical Title",
                authors=[Author(name="Alice Walker")],
                year=2021,
                venue="Nature",
            )

            with patch("scifi.server.get_cache", return_value=cache):
                with patch("scifi.server.verify_citation", return_value=canonical_meta):
                    # Call 1: Claimed year 1990 produces MISMATCH
                    res1 = scifi_verify_citation("10.1000/canonical", claimed_year=1990)
                    self.assertEqual(res1["status"], "MISMATCH")
                    self.assertTrue(len(res1["discrepancies"]) > 0)

                    # Verify that cache only stored canonical VERIFIED status with empty discrepancies
                    cached_record = cache.get("citation:10.1000/canonical")
                    self.assertIsNotNone(cached_record)
                    self.assertEqual(cached_record["status"], "VERIFIED")
                    self.assertEqual(cached_record.get("discrepancies", []), [])

                    # Call 2: Naked call without claimed fields gets canonical VERIFIED
                    res2 = scifi_verify_citation("10.1000/canonical")
                    self.assertEqual(res2["status"], "VERIFIED")
                    self.assertEqual(res2.get("discrepancies", []), [])

                    # Call 3: Call with correct claimed year gets VERIFIED
                    res3 = scifi_verify_citation("10.1000/canonical", claimed_year=2021)
                    self.assertEqual(res3["status"], "VERIFIED")
                    self.assertEqual(res3.get("discrepancies", []), [])

    def test_search_literature_cached_or_openalex(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_db = Path(tmpdir) / "test_cache.db"
            cache = RegistryCache(db_path=cache_db)

            with patch("scifi.server.get_cache", return_value=cache):
                with patch("scifi.server.requests.get") as mock_get:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {
                        "results": [
                            {
                                "title": "Attention Is All You Need",
                                "doi": "https://doi.org/10.48550/arxiv.1706.03762",
                                "publication_year": 2017,
                                "authorships": [{"author": {"display_name": "Ashish Vaswani"}}],
                                "primary_location": {"source": {"display_name": "NeurIPS"}},
                                "cited_by_count": 120000,
                            }
                        ]
                    }
                    mock_get.return_value = mock_resp

                    results = scifi_search_literature("Attention Is All You Need", limit=1)
                    self.assertEqual(len(results), 1)
                    self.assertEqual(results[0]["title"], "Attention Is All You Need")
                    self.assertEqual(results[0]["year"], 2017)
                    self.assertEqual(results[0]["doi"], "10.48550/arxiv.1706.03762")

    def test_audit_bib(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bib_path = Path(tmpdir) / "test.bib"
            out_bib = Path(tmpdir) / "sanitized.bib"
            bib_path.write_text(
                "@article{Sample2020,\n  title = {Sample Title},\n  author = {Smith, John},\n  year = {2020}\n}\n",
                encoding="utf-8",
            )
            with patch("scifi.server.audit_bib_file") as mock_audit:
                from scifi.citation_verifier.models import BibAuditReport

                report = BibAuditReport(file_path=str(bib_path), total_entries=1, verified_count=1)
                mock_audit.return_value = report
                with patch("scifi.server.generate_sanitized_bib", return_value="% sanitized bib"):
                    res = scifi_audit_bib(str(bib_path), output_bib=str(out_bib))
                    self.assertEqual(res["total_entries"], 1)
                    self.assertEqual(res["verified_count"], 1)
                    self.assertTrue(out_bib.exists())
                    self.assertEqual(out_bib.read_text(encoding="utf-8"), "% sanitized bib")

    def test_audit_bib_file_not_found(self):
        """Verify scifi_audit_bib returns ERROR if file does not exist (Finding 5)."""
        res = scifi_audit_bib("nonexistent_test_bib_file.bib")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("File not found", res["error_message"])

    def test_audit_attribution_file_not_found(self):
        """Verify scifi_audit_attribution returns ERROR if file does not exist (Finding 5)."""
        res = scifi_audit_attribution("nonexistent_test_latex_file.tex")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("File not found", res["error_message"])

    def test_audit_attribution_with_autofix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = Path(tmpdir) / "paper.tex"
            bib_file = Path(tmpdir) / "references.bib"
            tex_file.write_text("We trained an Adam optimizer to optimize parameters.\n", encoding="utf-8")
            bib_file.write_text("", encoding="utf-8")

            # Run with autofix=False first
            res_no_fix = scifi_audit_attribution(
                str(tex_file), bib_path=str(bib_file), autofix=False, enable_search=False
            )
            self.assertEqual(res_no_fix["total_findings"], 1)
            self.assertFalse(res_no_fix["autofix"]["applied"])

            # Run with autofix=True
            res_fix = scifi_audit_attribution(str(tex_file), bib_path=str(bib_file), autofix=True, enable_search=False)
            self.assertTrue(res_fix["autofix"]["applied"])
            self.assertEqual(res_fix["autofix"]["fixed_count"], 1)
            # Verify tex and bib were patched
            tex_content = tex_file.read_text(encoding="utf-8")
            self.assertIn(r"\cite{", tex_content)
            bib_content = bib_file.read_text(encoding="utf-8")
            self.assertIn("@", bib_content)
            self.assertIn("AdamOptimizerRef", bib_content)


class TestMCPConfigFile(unittest.TestCase):
    """Verify repository root mcp_config.json configuration."""

    def test_mcp_config_exists_and_valid(self):
        repo_root = Path(__file__).resolve().parent.parent
        config_path = repo_root / "mcp_config.json"
        self.assertTrue(config_path.exists(), "mcp_config.json not found in repository root.")

        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("mcpServers", data)
        self.assertIn("scifi", data["mcpServers"])
        scifi_cfg = data["mcpServers"]["scifi"]
        self.assertEqual(scifi_cfg.get("command"), "uv")
        self.assertEqual(scifi_cfg.get("args"), ["run", "python", "-m", "scifi.server"])


if __name__ == "__main__":
    unittest.main()
