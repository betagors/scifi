"""
Unit tests for scifi.literature.reporter:
Verifies Markdown report synthesis, topological depth progression grouping,
baseline summary table formatting, standardized BibTeX key generation,
special character sanitization, and file export operations.
"""

from pathlib import Path
import pytest

from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
    PaperVersionRecord,
)
from scifi.literature.reporter import (
    escape_bibtex,
    export_bibtex_entries,
    generate_markdown_report,
    save_bibtex_file,
    save_markdown_report,
)


@pytest.fixture
def lineage_dataset() -> tuple[list[PaperRecord], list[CitationRecord], dict[str, int]]:
    p0_a = PaperRecord(
        id="p0-a",
        title="Foundations of Deep Learning",
        year=2015,
        citation_count=12000,
        influential_citation_count=1500,
        authors=[
            AuthorRecord(id="a1", name="Yann LeCun"),
            AuthorRecord(id="a2", name="Yoshua Bengio"),
            AuthorRecord(id="a3", name="Geoffrey Hinton"),
        ],
        identifiers=[
            PaperIdentifierRecord(paper_id="p0-a", provider="doi", external_id="10.1038/nature14539"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-0a",
                paper_id="p0-a",
                location_type="publisher",
                is_oa=False,
                oa_status="closed",
            )
        ],
        abstract="Deep learning allows computational models composed of multiple processing layers to learn representations of data.",
    )

    p0_b = PaperRecord(
        id="p0-b",
        title="Deep Residual Learning for Image Recognition",
        year=2016,
        citation_count=180000,
        influential_citation_count=25000,
        authors=[
            AuthorRecord(id="a4", name="Kaiming He"),
            AuthorRecord(id="a5", name="Xiangyu Zhang"),
        ],
        identifiers=[
            PaperIdentifierRecord(paper_id="p0-b", provider="doi", external_id="10.1109/CVPR.2016.90"),
            PaperIdentifierRecord(paper_id="p0-b", provider="arxiv", external_id="1512.03385"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-0b",
                paper_id="p0-b",
                location_type="repository",
                is_oa=True,
                oa_status="green",
                pdf_url="https://arxiv.org/pdf/1512.03385.pdf",
            )
        ],
        abstract="Deeper neural networks are more difficult to train. We present a residual learning framework to ease the training of networks.",
    )

    p1_a = PaperRecord(
        id="p1-a",
        title="Attention Is All You Need",
        year=2017,
        citation_count=110000,
        influential_citation_count=18000,
        authors=[
            AuthorRecord(id="a6", name="Ashish Vaswani"),
            AuthorRecord(id="a7", name="Noam Shazeer"),
            AuthorRecord(id="a8", name="Niki Parmar"),
        ],
        identifiers=[
            PaperIdentifierRecord(paper_id="p1-a", provider="arxiv", external_id="1706.03762"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-1a",
                paper_id="p1-a",
                location_type="repository",
                is_oa=True,
                oa_status="gold",
                pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
            )
        ],
        abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. We propose the Transformer.",
    )

    p2_a = PaperRecord(
        id="p2-a",
        title="Llama: Open and Efficient Foundation Language Models",
        year=2023,
        citation_count=6500,
        influential_citation_count=850,
        authors=[
            AuthorRecord(id="a9", name="Hugo Touvron"),
        ],
        identifiers=[
            PaperIdentifierRecord(paper_id="p2-a", provider="arxiv", external_id="2302.13971"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-2a",
                paper_id="p2-a",
                location_type="repository",
                is_oa=True,
                oa_status="green",
                landing_page_url="https://arxiv.org/abs/2302.13971",
            )
        ],
        abstract="We introduce LLaMA, a collection of foundation language models ranging from 7B to 65B parameters.",
    )

    papers = [p0_a, p0_b, p1_a, p2_a]
    citations = [
        CitationRecord(source_paper_id="p1-a", target_paper_id="p0-a", is_influential=True),
        CitationRecord(source_paper_id="p2-a", target_paper_id="p1-a", is_influential=True),
        CitationRecord(source_paper_id="p2-a", target_paper_id="p0-b", is_influential=False),
    ]
    depths = {
        "p0-a": 0,
        "p0-b": 0,
        "p1-a": 1,
        "p2-a": 2,
    }
    return papers, citations, depths


def test_generate_markdown_report_structure(lineage_dataset):
    papers, citations, depths = lineage_dataset
    report = generate_markdown_report("Deep Learning & Transformers Lineage", papers, citations, depths)

    # Title & Header
    assert "# Literature Intelligence Report: Deep Learning & Transformers Lineage" in report
    assert "**Total Papers:** 4" in report
    assert "**Root Papers:** 2" in report
    assert "**Frontier Papers:** 1" in report
    assert "**Topological Depth Span:** 0 to 2" in report

    # Section Headers
    assert "## 1. Executive Summary & Lineage Topology" in report
    assert "## 2. Intellectual Evolution & Progression" in report
    assert "## 3. Baseline Summary Table" in report
    assert "## 4. Standardized BibTeX Entries" in report

    # Paper details in Section 2
    assert "Vaswani2017Attention" in report
    assert "Ashish Vaswani" in report
    assert "Attention Is All You Need" in report
    assert "Deep Residual Learning for Image Recognition" in report
    assert "Llama: Open and Efficient Foundation Language Models" in report


def test_topological_depth_grouping(lineage_dataset):
    papers, citations, depths = lineage_dataset
    report = generate_markdown_report("Transformer Evolution", papers, citations, depths)

    # Check Depth Level Headers
    assert "### Level 0: Seminal Foundations & Roots" in report
    assert "### Level 1: Intermediate Architectural Iterations" in report
    assert "### Level 2: Recent Research Frontier" in report

    # Level 0 should contain p0-a and p0-b in chronological order (2015 before 2016)
    idx_p0_a = report.find("Foundations of Deep Learning")
    idx_p0_b = report.find("Deep Residual Learning for Image Recognition")
    idx_p1_a = report.find("Attention Is All You Need")
    idx_p2_a = report.find("Llama: Open and Efficient Foundation Language Models")

    assert idx_p0_a < idx_p0_b < idx_p1_a < idx_p2_a


def test_baseline_summary_table_formatting(lineage_dataset):
    papers, citations, depths = lineage_dataset
    report = generate_markdown_report("Transformer Evolution", papers, citations, depths)

    # Check table column header
    table_header = "| Paper / CiteKey | Year | Primary Authors | Citations | Access Tier | Open Access URL |"
    assert table_header in report
    assert "|---|---|---|---|---|---|" in report

    # Check row contents
    assert "[Vaswani2017Attention]" in report
    assert "| 2017 |" in report
    assert "Ashish Vaswani et al." in report
    assert "| 110000 |" in report
    assert "| Gold |" in report
    assert "[Link](https://arxiv.org/pdf/1706.03762.pdf)" in report

    # Two authors format: Author 1 and Author 2
    assert "Kaiming He and Xiangyu Zhang" in report

    # Single author format: Hugo Touvron
    assert "Hugo Touvron" in report

    # Closed access paper without direct OA url
    assert "| Closed |" in report


def test_table_escapes_pipe_characters():
    paper = PaperRecord(
        id="p-pipe",
        title="Pipe | Separation | Architecture",
        year=2021,
        citation_count=10,
        authors=[AuthorRecord(id="a1", name="Author One")],
    )
    report = generate_markdown_report("Pipe Test", [paper], [], {"p-pipe": 0})
    # Pipe in title must be escaped as \| in table row to avoid malformed markdown table
    assert r"Pipe \| Separation \| Architecture" in report


def test_export_bibtex_entries_formatting_and_sanitization():
    p1 = PaperRecord(
        id="p-res",
        title="Deep Residual Learning",
        year=2016,
        authors=[AuthorRecord(id="a1", name="Kaiming He")],
    )
    p2 = PaperRecord(
        id="p-special",
        title="Scaling & Efficiency: 50% Speedup under $O(N)$ with C# & Py_Torch",
        year=2022,
        authors=[AuthorRecord(id="a2", name="Jane Doe & John Smith")],
        identifiers=[
            PaperIdentifierRecord(paper_id="p-special", provider="doi", external_id="10.1000/special.1"),
            PaperIdentifierRecord(paper_id="p-special", provider="arxiv", external_id="2201.00001"),
        ],
    )

    bib = export_bibtex_entries([p1, p2])

    # Check p1
    assert "@article{He2016Deep," in bib
    assert "  title = {Deep Residual Learning}," in bib
    assert "  author = {Kaiming He}," in bib
    assert "  year = {2016}" in bib

    # Check special character sanitization in p2
    assert r"Scaling \& Efficiency: 50\% Speedup under \$O(N)\$ with C\# \& Py\_Torch" in bib
    assert r"Jane Doe \& John Smith" in bib
    assert "  doi = {10.1000/special.1}," in bib


def test_export_bibtex_deduplicates_identical_keys():
    p1 = PaperRecord(
        id="p-1",
        title="Attention Mechanism",
        year=2020,
        authors=[AuthorRecord(id="a1", name="Alice Smith")],
    )
    p2 = PaperRecord(
        id="p-2",
        title="Attention Models",
        year=2020,
        authors=[AuthorRecord(id="a2", name="Alice Smith")],
    )

    bib = export_bibtex_entries([p1, p2])
    assert "@article{Smith2020Attention," in bib
    assert "@article{Smith2020Attentiona," in bib


def test_escape_bibtex_helper():
    raw = "Let's test & % $ _ # characters and already escaped \\& \\% \\$."
    escaped = escape_bibtex(raw)
    assert r"\&" in escaped
    assert r"\%" in escaped
    assert r"\$" in escaped
    assert r"\_" in escaped
    assert r"\#" in escaped
    assert r"\\&" not in escaped
    assert r"\\%" not in escaped


def test_save_markdown_report_and_bibtex_file(tmp_path, lineage_dataset):
    papers, citations, depths = lineage_dataset

    report_path = tmp_path / "deep" / "nested" / "report.md"
    bib_path = tmp_path / "deep" / "nested" / "references.bib"

    saved_report = save_markdown_report(report_path, "Test Lineage", papers, citations, depths)
    saved_bib = save_bibtex_file(bib_path, papers)

    assert saved_report == report_path
    assert saved_report.is_file()
    content_report = saved_report.read_text(encoding="utf-8")
    assert "# Literature Intelligence Report: Test Lineage" in content_report

    assert saved_bib == bib_path
    assert saved_bib.is_file()
    content_bib = saved_bib.read_text(encoding="utf-8")
    assert "@article{Vaswani2017Attention," in content_bib


def test_empty_and_edge_cases():
    # Empty papers
    empty_report = generate_markdown_report("Empty Graph", [], [], {})
    assert "# Literature Intelligence Report: Empty Graph" in empty_report
    assert "**Total Papers:** 0" in empty_report
    assert "**Root Papers:** 0" in empty_report
    assert "**Frontier Papers:** 0" in empty_report
    assert export_bibtex_entries([]) == ""

    # Paper with missing fields
    sparse_paper = PaperRecord(
        id="sparse-1",
        title="",
        year=None,
        authors=[],
        abstract=None,
    )
    sparse_report = generate_markdown_report("Sparse Graph", [sparse_paper], [], {"sparse-1": 0})
    assert "Unknown" in sparse_report
    assert "No abstract available." in sparse_report

    sparse_bib = export_bibtex_entries([sparse_paper])
    assert "@article{" in sparse_bib
    assert "Unknown" in sparse_bib
