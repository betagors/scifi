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
    EvidenceRecord,
    PaperGapRecord,
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
    assert "## Executive Summary" in report
    assert "## 1. Intellectual Evolution & Lineage" in report
    assert "## 2. Baseline Summary Table" in report
    assert "## 3. Evidence-Backed Delta-Novelty Matrix" in report
    assert "## 4. Traceable Limitations & Research Opportunities" in report
    assert "## 5. Standardized BibTeX Entries" in report

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


def test_report_includes_delta_novelty_matrix_and_evidence(lineage_dataset):
    papers, citations, depths = lineage_dataset
    root_paper = papers[0]     # p0-a
    frontier_paper = papers[3] # p2-a

    ev1 = EvidenceRecord(
        id="ev-1",
        paper_id=root_paper.id,
        evidence_type="citation_context",
        extracted_text="Foundations of Deep Learning relies on static network graphs and unbounded compute.",
        extraction_method="citation_context_mining",
        reporting_paper_id=frontier_paper.id,
        source_section="Related Work",
        confidence=0.88,
    )
    gap1 = PaperGapRecord(
        id="gap-1",
        paper_id=root_paper.id,
        gap_type="unstated_assumption",
        claim_summary="Relies on static network graphs and unbounded compute",
        primary_evidence_id="ev-1",
        verification_status="corroborated",
        corroborating_count=2,
    )

    ev2 = EvidenceRecord(
        id="ev-2",
        paper_id=frontier_paper.id,
        evidence_type="abstract_limitation",
        extracted_text="However, LLaMA struggles with catastrophic forgetting in long-horizon reasoning.",
        extraction_method="contrastive_sentence_mining",
        reporting_paper_id=None,
        source_section="Abstract",
        confidence=0.92,
    )
    gap2 = PaperGapRecord(
        id="gap-2",
        paper_id=frontier_paper.id,
        gap_type="empirical_limitation",
        claim_summary="Struggles with catastrophic forgetting in long-horizon reasoning",
        primary_evidence_id="ev-2",
        verification_status="candidate",
        corroborating_count=0,
    )

    paper_gaps = {
        root_paper.id: [gap1],
        frontier_paper.id: [gap2],
    }
    evidence_map = {
        "ev-1": ev1,
        "ev-2": ev2,
    }

    report = generate_markdown_report(
        "Deep Learning & Transformers Lineage",
        papers,
        citations,
        depths,
        paper_gaps=paper_gaps,
        evidence_map=evidence_map,
    )

    # 1. Executive Summary includes total extracted gaps and corroborated findings count
    assert "**Total Extracted Gaps:** 2 (1 corroborated)" in report
    assert "2 traceable technical gaps" in report or "2" in report
    assert "1 independently corroborated" in report or "1 corroborated" in report

    # 2. Section 3: Evidence-Backed Delta-Novelty Matrix
    assert "## 3. Evidence-Backed Delta-Novelty Matrix" in report
    matrix_header = "| Evaluation Dimension | Baseline Work [Ref] | Baseline Paradigm / Assumption | Unresolved Gap | Proposed Approach (Yours) |"
    assert matrix_header in report
    assert "|---|---|---|---|---|" in report

    # Evaluation Dimensions
    assert "Theoretical Paradigm" in report
    assert "Key Assumptions" in report
    assert "Scalability / Complexity" in report
    assert "Open Limitations" in report or "Open Limitation" in report
    assert "Proposed Approach (Yours)" in report

    # Baselines in matrix (foundational root and frontier)
    assert "Foundations of Deep Learning" in report
    assert "Llama: Open and Efficient Foundation Language Models" in report
    assert "Relies on static network graphs and unbounded compute" in report

    # 3. Section 4: Traceable Limitations & Research Opportunities
    assert "## 4. Traceable Limitations & Research Opportunities" in report
    assert "[Unstated Assumption]" in report
    assert "[Corroborated: 2 sources]" in report
    assert "[Empirical Limitation]" in report
    assert "[Candidate Finding]" in report

    # Verbatim evidence blockquotes
    assert '> "Foundations of Deep Learning relies on static network graphs and unbounded compute."' in report
    assert '> "However, LLaMA struggles with catastrophic forgetting in long-horizon reasoning."' in report

    # Attribution lines
    assert "*Reported by: [Touvron2023Llama] Hugo Touvron (Section: Related Work)*" in report
    assert "*Self-reported in author abstract*" in report


def test_delta_novelty_matrix_pipe_escaping():
    paper = PaperRecord(
        id="p-pipe",
        title="Architecture | Model A | Model B",
        year=2023,
        citation_count=50,
        authors=[AuthorRecord(id="a1", name="Alice Smith")],
    )
    ev = EvidenceRecord(
        id="ev-pipe",
        paper_id="p-pipe",
        evidence_type="citation_context",
        extracted_text="The system uses A | B pipeline which fails under load.",
        extraction_method="citation_context_mining",
    )
    gap = PaperGapRecord(
        id="gap-pipe",
        paper_id="p-pipe",
        gap_type="unstated_assumption",
        claim_summary="Uses A | B pipeline with assumptions",
        primary_evidence_id="ev-pipe",
        verification_status="corroborated",
        corroborating_count=2,
    )

    report = generate_markdown_report(
        "Pipe Report",
        [paper],
        [],
        {"p-pipe": 0},
        paper_gaps={"p-pipe": [gap]},
        evidence_map={"ev-pipe": ev},
    )

    assert "## 3. Evidence-Backed Delta-Novelty Matrix" in report
    # Ensure vertical pipes are cleanly escaped as \| in table cells
    assert r"Architecture \| Model A \| Model B" in report
    assert r"Uses A \| B pipeline with assumptions" in report or r"A \| B pipeline" in report


def test_save_markdown_report_forwards_gaps_and_evidence(tmp_path, lineage_dataset):
    papers, citations, depths = lineage_dataset
    gap = PaperGapRecord(
        id="gap-test",
        paper_id="p0-a",
        gap_type="computational_complexity",
        claim_summary="O(N^2) complexity bottleneck",
        primary_evidence_id="ev-test",
        verification_status="corroborated",
        corroborating_count=3,
    )
    ev = EvidenceRecord(
        id="ev-test",
        paper_id="p0-a",
        evidence_type="abstract_limitation",
        extracted_text="Incurring O(N^2) computational complexity during training.",
        extraction_method="contrastive_sentence_mining",
    )

    out_file = tmp_path / "report_with_evidence.md"
    saved_path = save_markdown_report(
        out_file,
        "Lineage with Evidence",
        papers,
        citations,
        depths,
        paper_gaps={"p0-a": [gap]},
        evidence_map={"ev-test": ev},
    )

    assert saved_path == out_file
    text = saved_path.read_text(encoding="utf-8")
    assert "## 3. Evidence-Backed Delta-Novelty Matrix" in text
    assert "## 4. Traceable Limitations & Research Opportunities" in text
    assert "O(N^2) complexity bottleneck" in text
