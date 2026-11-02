"""
Unit tests for FastMCP Server Daemon (scifi.server) and mcp_config.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
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
    "scifi_verify_derivative",
    "scifi_verify_derivation_step",
    "scifi_check_units",
    "scifi_check_matrix_shapes",
    "scifi_check_limits",
    "scifi_check_convexity",
    "scifi_check_notation",
    "scifi_compile_latex",
    "scifi_verify_curve",
    "scifi_audit_statistics",
    "scifi_audit_claims",
    "scifi_fetch_paper_pdf",
    "scifi_extract_pdf_text",
}


class TestFastMCPServerRegistry(unittest.TestCase):
    """Verify tool registration, schemas, and docstrings on FastMCP server."""

    def test_all_17_tools_registered(self):
        registered_tools = set(mcp._tool_manager._tools.keys())
        self.assertEqual(
            registered_tools,
            EXPECTED_TOOLS,
            f"Missing or unexpected tools: {EXPECTED_TOOLS ^ registered_tools}",
        )
        self.assertEqual(len(registered_tools), 17)

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
            mock_compile.assert_called_once_with(entrypoint="main.tex", engine="latexmk", clean=True)

    def test_fetch_paper_pdf_mock(self):
        with patch("scifi.server.fetch_paper_pdf") as mock_fetch:
            mock_fetch.return_value = {"status": "SUCCESS", "file_path": "workspace/paper.pdf"}
            res = scifi_fetch_paper_pdf("1706.03762")
            self.assertEqual(res["status"], "SUCCESS")
            mock_fetch.assert_called_once_with(identifier="1706.03762", output_dir="workspace", email="researcher@scifi.org")

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
                "@article{Sample2020,\n"
                "  title = {Sample Title},\n"
                "  author = {Smith, John},\n"
                "  year = {2020}\n"
                "}\n",
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

    def test_audit_attribution_with_autofix(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = Path(tmpdir) / "paper.tex"
            bib_file = Path(tmpdir) / "references.bib"
            tex_file.write_text("We trained an Adam optimizer to optimize parameters.\n", encoding="utf-8")
            bib_file.write_text("", encoding="utf-8")

            # Run with autofix=False first
            res_no_fix = scifi_audit_attribution(str(tex_file), bib_path=str(bib_file), autofix=False, enable_search=False)
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

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("mcpServers", data)
        self.assertIn("scifi", data["mcpServers"])
        scifi_cfg = data["mcpServers"]["scifi"]
        self.assertEqual(scifi_cfg.get("command"), "uv")
        self.assertEqual(scifi_cfg.get("args"), ["run", "python", "-m", "scifi.server"])


if __name__ == "__main__":
    unittest.main()
