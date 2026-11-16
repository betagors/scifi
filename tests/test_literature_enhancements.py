"""Tests for structured ingestion, hybrid gap extraction, cross-paper gap matrix, and discovery reranking."""

from __future__ import annotations

import io
import tarfile
from unittest.mock import MagicMock, patch

from scifi.literature.discovery import expand_academic_query, rerank_papers
from scifi.literature.extractor import extract_sections_from_text
from scifi.literature.gap_matrix import GapMatrixBuilder
from scifi.literature.gaps import GapExtractor
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    PaperGapRecord,
    PaperRecord,
)
from scifi.literature.sources import (
    fetch_arxiv_structured_text,
    fetch_openreview_reviews,
)


def _mock_response(status_code: int = 200, text: str = "", content: bytes = b"", json_data: dict | None = None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = content or text.encode("utf-8")
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def test_fetch_arxiv_structured_text_html():
    html = """
    <html><body>
      <div class="ltx_abstract"><p>Abstract: We study sparse transformers.</p></div>
      <section><h2>1 Introduction</h2><p>Transformers are expensive.</p></section>
      <section><h2>3 Methodology</h2><p>We assume static topology for simplicity.</p></section>
      <section><h2>6 Limitations and Conclusion</h2><p>Our method degrades on long contexts.</p></section>
    </body></html>
    """
    with patch("scifi.literature.sources.requests.get", return_value=_mock_response(200, text=html)):
        res = fetch_arxiv_structured_text("2401.12345")

    assert res["status"] == "SUCCESS"
    assert res["source"] == "arxiv_html"
    assert "sparse transformers" in res["abstract"]
    assert "static topology" in res["system_model_or_method"]
    assert "degrades on long contexts" in res["limitations_and_conclusion"]
    assert "3 Methodology" in res["all_sections"]


def test_fetch_arxiv_structured_text_latex_fallback():
    buf = io.BytesIO()
    tex_body = (
        b"\\begin{abstract}We propose FastNet.\\end{abstract}\n"
        b"\\section{System Model}\nWe assume perfect CSI.\n"
        b"\\section{Limitations}\nFuture work includes dynamic channels.\n"
    )
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("main.tex")
        info.size = len(tex_body)
        tf.addfile(info, io.BytesIO(tex_body))

    def fake_get(url, **kwargs):
        if "e-print" in url:
            return _mock_response(200, content=buf.getvalue())
        return _mock_response(404, text="Not found")

    with patch("scifi.literature.sources.requests.get", side_effect=fake_get):
        res = fetch_arxiv_structured_text("2401.99999")

    assert res["status"] == "SUCCESS"
    assert res["source"] == "arxiv_latex"
    assert "FastNet" in res["abstract"]
    assert "perfect CSI" in res["system_model_or_method"]
    assert "dynamic channels" in res["limitations_and_conclusion"]


def test_fetch_openreview_reviews():
    search_json = {
        "notes": [{"id": "forum123", "forum": "forum123", "content": {"title": {"value": "Robust Graph Learning"}}}]
    }
    forum_json = {
        "notes": [
            {
                "id": "rev1",
                "content": {
                    "weaknesses": {"value": "Evaluated only on small synthetic datasets. High memory overhead."},
                    "limitations": {"value": "Assumes static graph topology."},
                    "rating": {"value": "5: marginally below acceptance threshold"},
                },
            }
        ]
    }

    def fake_get(url, **kwargs):
        if "notes/search" in url:
            return _mock_response(200, json_data=search_json)
        return _mock_response(200, json_data=forum_json)

    with patch("scifi.literature.sources.requests.get", side_effect=fake_get):
        res = fetch_openreview_reviews(title="Robust Graph Learning")

    assert res["status"] == "SUCCESS"
    assert res["review_count"] == 1
    assert "synthetic datasets" in res["reviews"][0]["weaknesses"]


def test_extractor_dehyphenation_and_all_sections():
    raw = (
        "Abstract\nThis paper studies opti-\nmization.\n\n"
        "1. Introduction\nIntro text.\n\n"
        "3. METHODOLOGY\nWe assume convex loss.\n\n"
        "5. Threats to Validity\nEvaluation is narrow.\n\n"
        "References\n[1] Doe."
    )
    parsed = extract_sections_from_text(raw)
    assert "optimization" in parsed["abstract"]
    assert "convex loss" in parsed["system_model_or_method"]
    assert "Evaluation is narrow" in parsed["limitations_and_conclusion"]
    assert len(parsed["all_sections"]) >= 3


def test_gap_extractor_reviews_implicit_and_grounded_llm():
    paper = PaperRecord(
        id="p1",
        title="Test Paper",
        abstract="We propose X. However, latency remains high.",
    )
    sections = {
        "system_model_or_method": "For simplicity, we restrict our attention to static graphs.",
        "limitations_and_conclusion": "Beyond the scope of this work is multi-hop reasoning.",
    }
    reviews = [
        {
            "note_id": "r1",
            "weaknesses": "The method fails to generalize under distribution shift.",
            "limitations": "No runtime comparison on large graphs.",
        }
    ]

    def fake_llm(p, secs):
        return [
            {
                "gap_type": "generalization_bound",
                "claim_summary": "Fails on multi-hop reasoning",
                "evidence_quote": "Beyond the scope of this work is multi-hop reasoning.",
                "source_section": "Limitations",
            },
            {
                "gap_type": "empirical_limitation",
                "claim_summary": "Hallucinated claim",
                "evidence_quote": "This quote does not exist anywhere in the paper.",
                "source_section": "Results",
            },
        ]

    extractor = GapExtractor(llm_extractor=fake_llm)
    all_gaps = extractor.extract_all_gaps(paper, contexts=[], sections=sections, reviews=reviews)
    texts = [ev.extracted_text for ev, _ in all_gaps]

    assert any("restrict our attention to static graphs" in t for t in texts)
    assert any("distribution shift" in t for t in texts)
    assert any("Beyond the scope of this work" in t for t in texts)
    assert not any("does not exist anywhere" in t for t in texts)


def test_gap_matrix_builder_structural_gaps():
    p1 = PaperRecord(id="p1", title="Method A on Bench1", year=2020)
    p2 = PaperRecord(id="p2", title="Method B on Bench2", year=2025)
    p3 = PaperRecord(id="p3", title="Method A on Bench1 v2", year=2021)
    p4 = PaperRecord(id="p4", title="Method B on Bench2 v2", year=2024)

    b1 = BenchmarkRecord(id="b1", name="ImageNet")
    b2 = BenchmarkRecord(id="b2", name="CIFAR-100")

    results = [
        BenchmarkResultRecord(id="r1", paper_id="p1", benchmark_id="b1", metric_id="acc", metric_value=80.0),
        BenchmarkResultRecord(id="r2", paper_id="p3", benchmark_id="b1", metric_id="acc", metric_value=81.0),
        BenchmarkResultRecord(id="r3", paper_id="p2", benchmark_id="b2", metric_id="acc", metric_value=90.0),
        BenchmarkResultRecord(id="r4", paper_id="p4", benchmark_id="b2", metric_id="acc", metric_value=91.0),
    ]
    gaps = [
        PaperGapRecord(
            id="g1",
            paper_id="p1",
            gap_type="unstated_assumption",
            claim_summary="Assumes static topology with perfect channel state",
            primary_evidence_id="e1",
        ),
        PaperGapRecord(
            id="g2",
            paper_id="p2",
            gap_type="unstated_assumption",
            claim_summary="Assumes static topology and perfect channel knowledge",
            primary_evidence_id="e2",
        ),
        PaperGapRecord(
            id="g3",
            paper_id="p1",
            gap_type="empirical_limitation",
            claim_summary="Conflicting accuracy on noisy labels",
            primary_evidence_id="e3",
            verification_status="disputed",
            contradicting_count=1,
        ),
    ]

    report = GapMatrixBuilder().build(
        papers=[p1, p2, p3, p4],
        gaps=gaps,
        benchmarks=[b1, b2],
        benchmark_results=results,
        paper_methods={"p1": ["MethodA"], "p2": ["MethodB"], "p3": ["MethodA"], "p4": ["MethodB"]},
    )

    types = {g.structural_type for g in report.structural_gaps}
    assert "unexplored_combination" in types
    assert "shared_unrelaxed_assumption" in types
    assert "contradictory_evidence" in types
    assert "evaluation_blind_spot" in types
    md = report.to_markdown()
    assert "Cross-Paper Gap Synthesis Matrix" in md


def test_discovery_query_expansion_and_rerank():
    variants = expand_academic_query("LLM hallucination in RAG")
    assert variants[0] == "LLM hallucination in RAG"
    assert any("large language model" in v.lower() for v in variants)

    p_relevant = PaperRecord(
        id="rel",
        title="Mitigating Hallucination in Retrieval Augmented Generation",
        abstract="We study LLM hallucination in RAG pipelines.",
        year=2025,
        citation_count=120,
    )
    p_noise = PaperRecord(
        id="noise",
        title="Survey of Database Indexing",
        abstract="B-trees and hash tables.",
        year=2025,
        citation_count=500,
    )
    ranked = rerank_papers("LLM hallucination in RAG", [p_noise, p_relevant])
    assert ranked[0].id == "rel"
