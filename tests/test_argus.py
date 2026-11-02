"""
Unit tests for Argus Attribution and Plagiarism Detection Engine.
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scifi.argus.detector import (
    COMMON_KNOWLEDGE,
    detect_informal_ai_tropes,
    extract_citations_from_span,
    extract_potential_methods,
    mask_latex_math,
    split_into_sentence_spans,
    strip_latex_comments,
)
from scifi.argus.engine import ArgusEngine
from scifi.argus.models import AttributionCategory, SuggestedAction
from scifi.argus.patcher import append_bibtex_entry, insert_cite_into_latex


class TestArgusDetector(unittest.TestCase):
    def test_strip_latex_comments(self):
        latex = "Line 1 % comment here\nLine 2\nLine 3 \\% not a comment"
        cleaned = strip_latex_comments(latex)
        lines = cleaned.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[0], "Line 1 ")
        self.assertEqual(lines[1], "Line 2")
        self.assertIn("\\%", lines[2])

    def test_mask_latex_math(self):
        latex = "Let $x \\in \\mathbb{R}$ be a variable. \\begin{equation} y = f(x) \\end{equation} End."
        masked = mask_latex_math(latex)
        self.assertNotIn("y = f(x)", masked)
        self.assertIn("[MATH]", masked)

    def test_extract_citations(self):
        text = "As shown in \\cite{Vaswani2017Attention} and recent work \\citep[p.~4]{Hu2021Lora} or [1, 2]."
        cites = extract_citations_from_span(text)
        self.assertIn("Vaswani2017Attention", cites)
        self.assertIn("Hu2021Lora", cites)
        self.assertIn("1, 2", cites)

    def test_split_into_sentence_spans(self):
        text = "First sentence here. Second sentence with LoRA. Third sentence."
        spans = split_into_sentence_spans(text)
        self.assertEqual(len(spans), 3)
        self.assertEqual(spans[0].text, "First sentence here.")
        self.assertIn("LoRA", spans[1].text)

    def test_extract_potential_methods(self):
        text = "We implement LoRA and evaluate on Swin Transformer and Mamba architecture."
        methods = extract_potential_methods(text)
        method_names = [m[0].lower() for m in methods]
        self.assertIn("lora", method_names)
        self.assertIn("swin transformer", method_names)
        self.assertIn("mamba", method_names)

    def test_common_knowledge_exemption(self):
        text = "We use stochastic gradient descent with cross entropy loss."
        methods = extract_potential_methods(text)
        for term, _ in methods:
            self.assertIn(term.lower(), COMMON_KNOWLEDGE)

    def test_detect_informal_tropes(self):
        slop = "In this tutorial, we will delve into the rich tapestry of deep learning."
        tropes = detect_informal_ai_tropes(slop)
        self.assertIn("delve", tropes)
        self.assertIn("tapestry", tropes)
        self.assertIn("in this tutorial", tropes)


class TestArgusPatcher(unittest.TestCase):
    def test_insert_cite_into_latex(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_file = Path(tmpdir) / "draft.tex"
            tex_file.write_text("We use LoRA for adaptation.\nSecond line.\n", encoding="utf-8")

            success = insert_cite_into_latex(tex_file, line_number=1, cite_key="Hu2021Lora", target_entity="LoRA")
            self.assertTrue(success)

            content = tex_file.read_text(encoding="utf-8")
            self.assertIn("LoRA~\\cite{Hu2021Lora}", content)

    def test_append_bibtex_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bib_file = Path(tmpdir) / "refs.bib"
            entry = "@article{Hu2021Lora, title={LoRA}, author={Hu, Edward}, year={2021}}"

            # First insertion
            added = append_bibtex_entry(bib_file, entry, "Hu2021Lora")
            self.assertTrue(added)
            self.assertIn("Hu2021Lora", bib_file.read_text(encoding="utf-8"))

            # Duplicate insertion should return False
            added_again = append_bibtex_entry(bib_file, entry, "Hu2021Lora")
            self.assertFalse(added_again)


class TestArgusEngine(unittest.TestCase):
    def test_engine_detects_uncited_method(self):
        engine = ArgusEngine(enable_search=False)
        text = "We apply Low-Rank Adaptation to parameterize weight matrices."
        report = engine.audit_text(text)
        self.assertEqual(report.academic_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.category, AttributionCategory.CANONICAL_ACADEMIC)
        self.assertEqual(finding.suggested_action, SuggestedAction.CITE)

    def test_engine_passes_cited_method(self):
        engine = ArgusEngine(enable_search=False)
        text = "We apply Low-Rank Adaptation \\cite{Hu2021Lora} to parameterize weight matrices."
        report = engine.audit_text(text)
        self.assertEqual(report.total_findings, 0)

    def test_engine_flags_informal_web(self):
        engine = ArgusEngine(enable_search=False)
        text = "In this tutorial, we will delve into the tapestry of models."
        report = engine.audit_text(text)
        self.assertEqual(report.web_count, 1)
        finding = report.findings[0]
        self.assertEqual(finding.category, AttributionCategory.INFORMAL_WEB)
        self.assertEqual(finding.suggested_action, SuggestedAction.REFORMULATE)


if __name__ == "__main__":
    unittest.main()
