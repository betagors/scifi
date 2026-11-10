"""
Unit tests for LaTeX Compiler (scifi.latex) and Adversarial Claims Scanner (scifi.review).
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scifi.latex import check_engine, compile_latex, parse_log
from scifi.review import audit_claims


class TestAuditClaims(unittest.TestCase):
    def test_audit_claims_sweeping_claims(self):
        text = (
            "In this section, we show that our method drastically improves latency.\n"
            "Our technique completely eliminates synchronization overhead.\n"
            "We construct an optimal algorithm for resource allocation.\n"
            "This is established for the first time in the literature.\n"
            "The proposed pipeline outperforms all existing methods by a wide margin.\n"
            "Finally, we assume perfect knowledge of the system state."
        )
        res = audit_claims(text)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertGreaterEqual(res["total_flags"], 5)
        for flag in res["flags"]:
            self.assertIn("line", flag)
            self.assertIn("matched_text", flag)
            self.assertIn("critique", flag)
            self.assertIn("snippet", flag)

    def test_audit_claims_neutral_text(self):
        text = (
            "We present an empirical study of gradient variance.\n"
            "Under assumption A, the algorithm converges to a stationary point.\n"
            "Experiments demonstrate a 12% reduction in execution time.\n"
            "The bounds are sub-optimal but provide practical guarantees."
        )
        res = audit_claims(text)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_flags"], 0)
        self.assertEqual(res["flags"], [])

    def test_audit_claims_ignores_comments(self):
        text = (
            "% This drastically improves performance and completely eliminates all errors\n"
            "% optimal solution for the first time\n"
            "We evaluate the proposed framework against three baseline models.\n"
        )
        res = audit_claims(text)
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["total_flags"], 0)
        self.assertEqual(res["flags"], [])

    def test_audit_claims_file_path_vs_raw_string(self):
        claim_line = "Our framework outperforms all existing architectures.\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "paper.tex"
            file_path.write_text(claim_line, encoding="utf-8")

            # Test Path object
            res_path = audit_claims(file_path)
            self.assertEqual(res_path["status"], "SUCCESS")
            self.assertEqual(res_path["total_flags"], 1)

            # Test string file path
            res_str_path = audit_claims(str(file_path))
            self.assertEqual(res_str_path["status"], "SUCCESS")
            self.assertEqual(res_str_path["total_flags"], 1)

            # Test raw string content directly
            res_raw = audit_claims(claim_line)
            self.assertEqual(res_raw["status"], "SUCCESS")
            self.assertEqual(res_raw["total_flags"], 1)

    def test_audit_claims_missing_file(self):
        missing_path = Path("nonexistent_paper_file_987654.tex")
        res = audit_claims(missing_path)
        self.assertEqual(res["status"], "ERROR")
        msg = res.get("message") or res.get("error_message", "")
        self.assertIn("File not found", msg)


class TestParseLog(unittest.TestCase):
    def test_parse_log_undefined_references_and_citations(self):
        sample_log = (
            "This is pdfTeX, Version 3.141592653-2.6-1.40.24 (TeX Live 2022)\n"
            "LaTeX Warning: Reference `sec:experiments' on page 3 undefined on input line 45.\n"
            "LaTeX Warning: Citation `vaswani2017' on page 1 undefined on input line 12.\n"
            "LaTeX Warning: Citation `devlin2018' on page 2 undefined on input line 25.\n"
            "LaTeX Warning: There were undefined references.\n"
        )
        res = parse_log(sample_log)
        self.assertIn("sec:experiments", res["undefined_references"])
        self.assertIn("vaswani2017", res["undefined_citations"])
        self.assertIn("devlin2018", res["undefined_citations"])
        self.assertGreaterEqual(res["warnings_count"], 3)

    def test_parse_log_missing_packages(self):
        sample_log = (
            "! LaTeX Error: File `amsmath.sty' not found.\n"
            "! LaTeX Error: File 'custom_cls.cls' not found.\n"
        )
        res = parse_log(sample_log)
        self.assertIn("amsmath.sty", res["missing_packages"])
        self.assertIn("custom_cls.cls", res["missing_packages"])

    def test_parse_log_fatal_errors(self):
        sample_log = (
            "./main.tex:42: Undefined control sequence.\n"
            "./main.tex:88: LaTeX Error: Environment theorem undefined.\n"
            "! LaTeX Error: File 'foo.sty' not found.\n"
        )
        res = parse_log(sample_log)
        self.assertGreaterEqual(len(res["errors"]), 2)
        err0 = res["errors"][0]
        self.assertEqual(err0["file"], "./main.tex")
        self.assertEqual(err0["line"], 42)
        self.assertIn("Undefined control sequence", err0["message"])

        # Check that error_type is extracted
        self.assertTrue(all("error_type" in e for e in res["errors"]))

    def test_parse_log_layout_warnings(self):
        sample_log = (
            "Overfull \\hbox (15.2pt too wide) in paragraph at lines 10--15\n"
            "Overfull \\hbox (3.1pt too wide) in paragraph at lines 30--35\n"
            "Underfull \\hbox (badness 10000) in paragraph at lines 50--55\n"
        )
        res = parse_log(sample_log)
        self.assertEqual(res["layout_warnings"]["overfull_hbox"], 2)
        self.assertEqual(res["layout_warnings"]["underfull_hbox"], 1)


class TestCheckEngine(unittest.TestCase):
    def test_check_engine_return_schema(self):
        info = check_engine()
        self.assertIsInstance(info, dict)
        self.assertIn("ready", info)
        self.assertIn("engine", info)
        self.assertIn("hint", info)
        self.assertIsInstance(info["ready"], bool)
        if info["ready"]:
            self.assertIn(info["engine"], ["latexmk", "pdflatex"])
            self.assertIsNone(info["hint"])
        else:
            self.assertIsNone(info["engine"])
            self.assertIsInstance(info["hint"], str)


class TestCompileLatex(unittest.TestCase):
    def test_compile_latex_missing_file(self):
        res = compile_latex("missing_manuscript_file_1234.tex")
        self.assertEqual(res["status"], "ERROR")
        self.assertIn("File not found: missing_manuscript_file_1234.tex", res["error_message"])

    def test_compile_latex_missing_compiler(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = Path(tmpdir) / "doc.tex"
            tex_file.write_text(r"\documentclass{article}\begin{document}Hello\end{document}", encoding="utf-8")

            with patch("shutil.which", return_value=None):
                res = compile_latex(tex_file, engine="nonexistent_compiler_xyz")
                self.assertEqual(res["status"], "COMPILER_NOT_FOUND")
                self.assertIn("hint", res)

    def test_compile_latex_mock_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = Path(tmpdir) / "doc.tex"
            tex_file.write_text(r"\documentclass{article}\begin{document}Hello\end{document}", encoding="utf-8")
            pdf_file = Path(tmpdir) / "doc.pdf"

            def fake_run(cmd, *args, **kwargs):
                pdf_file.write_bytes(b"%PDF-1.4 fake content")
                mock_res = MagicMock()
                mock_res.returncode = 0
                mock_res.stdout = "Output written on doc.pdf (1 page, 1000 bytes)."
                return mock_res

            with patch("shutil.which", return_value="/usr/bin/latexmk"), patch("subprocess.run", side_effect=fake_run):
                res = compile_latex(tex_file, engine="latexmk", clean=True)
                self.assertEqual(res["status"], "SUCCESS")
                self.assertTrue(res["pdf_generated"])
                self.assertIsNotNone(res["pdf_path"])
                self.assertEqual(Path(res["pdf_path"]).resolve(), pdf_file.resolve())
                self.assertIn("log", res)

    def test_compile_latex_mock_compilation_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = Path(tmpdir) / "doc.tex"
            tex_file.write_text(r"\documentclass{article}\begin{document}\undefinedmacro\end{document}", encoding="utf-8")

            def fake_run(cmd, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.returncode = 1
                mock_res.stdout = "./doc.tex:1: Undefined control sequence.\n! Emergency stop."
                return mock_res

            with patch("shutil.which", return_value="/usr/bin/pdflatex"), patch("subprocess.run", side_effect=fake_run):
                res = compile_latex(tex_file, engine="pdflatex", clean=False)
                self.assertEqual(res["status"], "COMPILATION_ERROR")
                self.assertFalse(res["pdf_generated"])
                self.assertGreaterEqual(len(res["errors"]), 1)
                self.assertIn("raw_log_tail", res)


if __name__ == "__main__":
    unittest.main()
