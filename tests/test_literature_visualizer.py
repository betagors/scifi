"""
Unit and integration tests for scifi.literature.visualizer:
Verifies standalone Vis.js HTML rendering, hierarchical DAG layout,
color-coded access tiers, slide-out details drawer, and strict XSS sanitization.
"""

from pathlib import Path

import pytest

from scifi.literature.models import (
    AuthorRecord,
    BenchmarkRecord,
    BenchmarkResultRecord,
    CitationRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
)
from scifi.literature.visualizer import (
    generate_interactive_html,
    render_interactive_html,
    save_interactive_html,
)


@pytest.fixture
def sample_papers() -> list[PaperRecord]:
    p1 = PaperRecord(
        id="paper-1",
        title="Foundations of Deep Learning",
        year=2015,
        citation_count=1500,
        influential_citation_count=120,
        authors=[
            AuthorRecord(
                id="a1",
                name="Alice Smith",
                institution="MIT",
                email="alice@mit.edu",
            ),
            AuthorRecord(
                id="a2",
                name="Bob Jones",
                institution="Stanford",
            ),
        ],
        identifiers=[
            PaperIdentifierRecord(paper_id="paper-1", provider="doi", external_id="10.1000/182"),
            PaperIdentifierRecord(paper_id="paper-1", provider="arxiv", external_id="1501.00001"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-1",
                paper_id="paper-1",
                location_type="publisher",
                is_oa=True,
                oa_status="gold",
                pdf_url="https://example.com/paper1.pdf",
            )
        ],
        abstract="This foundational paper introduces deep neural architectures.",
    )

    p2 = PaperRecord(
        id="paper-2",
        title="Attention and Transformers",
        year=2017,
        citation_count=8000,
        influential_citation_count=900,
        authors=[
            AuthorRecord(id="a3", name="Charlie Brown", institution="Google Research"),
        ],
        identifiers=[
            PaperIdentifierRecord(paper_id="paper-2", provider="doi", external_id="10.1000/183"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-2",
                paper_id="paper-2",
                location_type="repository",
                is_oa=True,
                oa_status="green",
                pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
            )
        ],
        abstract="We propose the Transformer model based solely on attention mechanisms.",
    )

    p3 = PaperRecord(
        id="paper-3",
        title="Modern Frontier LLMs",
        year=2024,
        citation_count=45,
        influential_citation_count=5,
        authors=[
            AuthorRecord(id="a4", name="Dana Scully"),
        ],
        locations=[
            PaperLocationRecord(
                id="loc-3",
                paper_id="paper-3",
                location_type="publisher",
                is_oa=False,
                oa_status="closed",
            )
        ],
        abstract="Survey of modern frontier LLMs and reasoning models.",
    )

    return [p1, p2, p3]


@pytest.fixture
def sample_citations() -> list[CitationRecord]:
    # paper-2 cites paper-1 (paper-1 is root/predecessor)
    # paper-3 cites paper-2 (paper-2 is intermediate predecessor)
    return [
        CitationRecord(source_paper_id="paper-2", target_paper_id="paper-1", is_influential=True),
        CitationRecord(source_paper_id="paper-3", target_paper_id="paper-2", is_influential=False),
    ]


@pytest.fixture
def sample_depths() -> dict[str, int]:
    return {
        "paper-1": 0,
        "paper-2": 1,
        "paper-3": 2,
    }


def test_render_interactive_html_structure(sample_papers, sample_citations, sample_depths):
    """Verify HTML structure, Vis.js CDN inclusion, containers, and title."""
    html = render_interactive_html(
        graph_title="Lineage DAG: Attention",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
        seed_paper_id="paper-2",
    )

    assert "<!DOCTYPE html>" in html
    assert "https://unpkg.com/vis-network/standalone/umd/vis-network.min.js" in html
    assert "Lineage DAG: Attention" in html
    assert 'id="network-container"' in html or 'id="network"' in html
    assert 'id="details-drawer"' in html
    assert 'id="drawer-close"' in html


def test_hierarchical_layout_config(sample_papers, sample_citations, sample_depths):
    """Verify Vis.js hierarchical layout configuration options."""
    html = render_interactive_html(
        graph_title="Hierarchical Graph",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
    )

    # Required layout params
    assert "hierarchical" in html
    assert "direction: 'LR'" in html or 'direction: "LR"' in html or '"direction": "LR"' in html
    assert "sortMethod: 'directed'" in html or 'sortMethod: "directed"' in html or '"sortMethod": "directed"' in html
    assert "levelSeparation: 220" in html or '"levelSeparation": 220' in html
    assert "nodeSpacing: 160" in html or '"nodeSpacing": 160' in html


def test_node_level_mapping_from_depths(sample_papers, sample_citations, sample_depths):
    """Verify node levels are strictly mapped from topological depths."""
    html = render_interactive_html(
        graph_title="Depth Levels Graph",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
    )

    # Check that levels 0, 1, and 2 are assigned to respective nodes in nodes data
    assert '"level": 0' in html or 'level: 0' in html
    assert '"level": 1' in html or 'level: 1' in html
    assert '"level": 2' in html or 'level: 2' in html


def test_color_coded_access_tiers(sample_depths):
    """Verify OA tiers are mapped to required hex colors."""
    gold_paper = PaperRecord(
        id="p-gold",
        title="Gold OA",
        locations=[PaperLocationRecord(id="l1", paper_id="p-gold", location_type="pub", is_oa=True, oa_status="gold")],
    )
    green_paper = PaperRecord(
        id="p-green",
        title="Green OA",
        locations=[PaperLocationRecord(id="l2", paper_id="p-green", location_type="repo", is_oa=True, oa_status="green")],
    )
    hybrid_paper = PaperRecord(
        id="p-hybrid",
        title="Hybrid OA",
        locations=[PaperLocationRecord(id="l3", paper_id="p-hybrid", location_type="pub", is_oa=True, oa_status="hybrid")],
    )
    bronze_paper = PaperRecord(
        id="p-bronze",
        title="Bronze OA",
        locations=[PaperLocationRecord(id="l4", paper_id="p-bronze", location_type="pub", is_oa=True, oa_status="bronze")],
    )
    closed_paper = PaperRecord(
        id="p-closed",
        title="Closed Paywalled",
        locations=[PaperLocationRecord(id="l5", paper_id="p-closed", location_type="pub", is_oa=False, oa_status="closed")],
    )

    papers = [gold_paper, green_paper, hybrid_paper, bronze_paper, closed_paper]
    depths = {p.id: 0 for p in papers}

    html = render_interactive_html("OA Test", papers, [], depths)

    # Color requirements:
    # gold -> #10b981
    # green -> #059669
    # hybrid -> #f59e0b
    # bronze -> #d97706
    # closed -> #64748b
    assert "#10b981" in html
    assert "#059669" in html
    assert "#f59e0b" in html
    assert "#d97706" in html
    assert "#64748b" in html


def test_seed_node_styling(sample_papers, sample_citations, sample_depths):
    """Verify seed node receives distinct blue border styling (#3b82f6)."""
    html = render_interactive_html(
        graph_title="Seed Test",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
        seed_paper_id="paper-2",
    )

    # Seed node styling check
    assert "#3b82f6" in html


def test_slide_out_drawer_components(sample_papers, sample_citations, sample_depths):
    """Verify drawer contains required inspection components and click handler."""
    html = render_interactive_html(
        graph_title="Drawer Test",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
    )

    # Drawer HTML elements
    assert 'id="drawer-title"' in html
    assert 'id="drawer-year"' in html
    assert 'id="drawer-authors"' in html
    assert 'id="drawer-citekey"' in html
    assert 'id="copy-citekey-btn"' in html
    assert 'id="drawer-links"' in html
    assert 'id="drawer-citations"' in html
    assert 'id="drawer-abstract"' in html
    assert 'id="drawer-close"' in html

    # Vis.js click handler wiring
    assert 'network.on("click"' in html or "network.on('click'" in html


def test_node_label_formatting(sample_papers, sample_citations, sample_depths):
    """Verify node labels show first author + year + truncated title."""
    html = render_interactive_html(
        graph_title="Label Test",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
    )

    # Paper 1: Alice Smith (2015) Foundations of Deep Learning
    # Label should include author, year, title
    assert "Smith" in html
    assert "2015" in html
    assert "Foundations of Deep Learning" in html


def test_strict_xss_sanitization():
    """Verify malicious script tags and HTML injection payloads are neutralized."""
    malicious_paper = PaperRecord(
        id="evil-1",
        title="<script>alert('xss-title')</script>",
        year=2023,
        citation_count=10,
        authors=[
            AuthorRecord(
                id="ea1",
                name='"><img src=x onerror=alert("xss-author")>',
                institution="<script>document.cookie</script>",
                email="attacker@evil.com",
            )
        ],
        abstract="<iframe src='http://evil.com'></iframe>Malicious abstract content.",
    )

    malicious_title = "</script><script>alert('xss-graph-title')</script>"
    depths = {"evil-1": 0}

    html = render_interactive_html(
        graph_title=malicious_title,
        papers=[malicious_paper],
        citations=[],
        depths=depths,
    )

    # Zero unescaped executable script tags allowed
    assert "<script>alert('xss-title')</script>" not in html
    assert '"><img src=x onerror=alert("xss-author")>' not in html
    assert "<script>document.cookie</script>" not in html
    assert "<iframe" not in html
    assert "</script><script>alert('xss-graph-title')</script>" not in html

    # Safe escaped forms or unicode escapes should be present
    assert "\\u003c" in html or "&lt;" in html or "&amp;lt;" in html or "\\u0026lt;" in html


def test_missing_optional_fields_resilience():
    """Verify papers with missing optional fields render gracefully."""
    sparse_paper = PaperRecord(
        id="sparse-1",
        title="",
        year=None,
        citation_count=0,
        authors=[],
        identifiers=[],
        locations=[],
        abstract=None,
    )

    depths = {"sparse-1": 0}
    html = render_interactive_html("Sparse Paper Test", [sparse_paper], [], depths)

    assert "Sparse Paper Test" in html
    assert "Unknown (n.d.)" in html
    assert "Untitled" in html


def test_edge_filtering_and_citation_direction():
    """Verify edges referencing unknown paper IDs are discarded and direction flows roots -> frontier."""
    p1 = PaperRecord(id="root-1", title="Root Paper", year=2010)
    p2 = PaperRecord(id="frontier-1", title="Frontier Paper", year=2024)

    # Valid citation: frontier-1 cites root-1 (root-1 is target, frontier-1 is source)
    c1 = CitationRecord(source_paper_id="frontier-1", target_paper_id="root-1")
    # Invalid citation referencing non-existent paper
    c2 = CitationRecord(source_paper_id="frontier-1", target_paper_id="ghost-paper")

    depths = {"root-1": 0, "frontier-1": 1}
    html = render_interactive_html("Edge Test", [p1, p2], [c1, c2], depths)

    # ghost-paper should be omitted
    assert "ghost-paper" not in html
    # Edge from root-1 to frontier-1 should be present
    assert '"from": "root-1"' in html or "'from': 'root-1'" in html
    assert '"to": "frontier-1"' in html or "'to': 'frontier-1'" in html


def test_unsafe_url_sanitization():
    """Verify javascript: URLs in pdf_url are excluded."""
    unsafe_paper = PaperRecord(
        id="unsafe-1",
        title="Unsafe Link Paper",
        locations=[
            PaperLocationRecord(
                id="l-bad",
                paper_id="unsafe-1",
                location_type="repo",
                pdf_url="javascript:alert('xss-pdf')",
            )
        ],
    )

    depths = {"unsafe-1": 0}
    html = render_interactive_html("Unsafe URL Test", [unsafe_paper], [], depths)

    assert "javascript:alert" not in html


def test_save_interactive_html(tmp_path: Path, sample_papers, sample_citations, sample_depths):
    """Verify save_interactive_html writes the rendered HTML to target path."""
    out_file = tmp_path / "subfolder" / "interactive_lineage.html"
    returned_path = save_interactive_html(
        output_path=out_file,
        graph_title="Saved Lineage",
        papers=sample_papers,
        citations=sample_citations,
        depths=sample_depths,
        seed_paper_id="paper-1",
    )

    assert returned_path == out_file
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "Saved Lineage" in content
    assert "paper-1" in content


def test_visualizer_renders_evidence_drawer_safely():
    """Verify evidence drawer renders category badges, verification badges, quotes, and metadata safely."""
    paper = PaperRecord(id="p-1", title="Paper One", year=2022)
    ev = EvidenceRecord(
        id="ev-1",
        paper_id="p-1",
        reporting_paper_id="paper-2",
        evidence_type="citation_context",
        source_section="Related Work",
        extracted_text="Paper One requires O(N^2) memory <script>alert('xss')</script>",
        extraction_method="semantic_scholar_api",
    )
    gap = PaperGapRecord(
        id="gap-1",
        paper_id="p-1",
        gap_type="computational_complexity",
        claim_summary="Quadratic memory complexity",
        primary_evidence_id="ev-1",
        verification_status="corroborated",
        corroborating_count=2,
    )

    html = render_interactive_html(
        "Evidence Test",
        [paper],
        [],
        {"p-1": 0},
        paper_gaps={"p-1": [gap]},
        evidence_map={"ev-1": ev},
    )

    assert "Extracted Technical Limitations & Gaps" in html
    assert "Quadratic memory complexity" in html
    assert "corroborated" in html
    assert "Corroborated (2 sources)" in html
    assert "computational_complexity" in html or "badge-gap-computational-complexity" in html
    assert "badge-verif-corroborated" in html
    assert "Paper One requires O(N^2) memory" in html
    assert "Related Work" in html
    assert "paper-2" in html
    assert "semantic_scholar_api" in html

    # Strict XSS check
    assert "<script>alert('xss')</script>" not in html
    assert "\\u003c" in html or "&lt;" in html or "\\u0026lt;" in html


def test_visualizer_renders_candidate_finding():
    """Verify candidate gap renders Candidate Finding badge and various gap category classes."""
    paper = PaperRecord(id="p-1", title="Paper One", year=2022)
    ev = EvidenceRecord(
        id="ev-cand",
        paper_id="p-1",
        evidence_type="abstract",
        source_section="Abstract",
        extracted_text="Assumes synchronous clock across all nodes.",
        extraction_method="rule_based",
    )
    gap1 = PaperGapRecord(
        id="gap-cand",
        paper_id="p-1",
        gap_type="unstated_assumption",
        claim_summary="Assumes synchronized clocks",
        primary_evidence_id="ev-cand",
        verification_status="candidate",
        corroborating_count=0,
    )
    gap2 = PaperGapRecord(
        id="gap-emp",
        paper_id="p-1",
        gap_type="empirical_limitation",
        claim_summary="Degrades under high noise",
        primary_evidence_id="ev-cand",
        verification_status="candidate",
        corroborating_count=0,
    )

    html = render_interactive_html(
        "Candidate Test",
        [paper],
        [],
        {"p-1": 0},
        paper_gaps={"p-1": [gap1, gap2]},
        evidence_map={"ev-cand": ev},
    )

    assert "Candidate Finding" in html
    assert "badge-verif-candidate" in html
    assert "Assumes synchronized clocks" in html
    assert "Degrades under high noise" in html
    assert "badge-gap-unstated-assumption" in html
    assert "badge-gap-empirical-limitation" in html


def test_strict_xss_in_evidence_passages():
    """Verify evidence passages containing script tags, img error handlers, and angle brackets are sanitized."""
    paper = PaperRecord(id="p-xss", title="Safe Title", year=2024)
    malicious_ev = EvidenceRecord(
        id="ev-evil",
        paper_id="p-xss",
        evidence_type="citation_context",
        source_section="<script>alert('sec')</script>",
        reporting_paper_id="<script>alert('rep')</script>",
        extracted_text="Passage with <script>alert(1)</script> and <img src=x onerror=alert('xss2')> and math a < b > c",
        extraction_method="regex_<script>",
    )
    malicious_gap = PaperGapRecord(
        id="gap-evil",
        paper_id="p-xss",
        gap_type="computational_complexity",
        claim_summary="Claim with <script>alert('claim')</script> and <b>bold</b>",
        primary_evidence_id="ev-evil",
        verification_status="candidate",
    )

    html = render_interactive_html(
        "XSS Test",
        [paper],
        [],
        {"p-xss": 0},
        paper_gaps={"p-xss": [malicious_gap]},
        evidence_map={"ev-evil": malicious_ev},
    )

    # No unescaped malicious tags anywhere in generated HTML
    assert "<script>alert(1)</script>" not in html
    assert "<img src=x onerror=alert('xss2')>" not in html
    assert "<script>alert('sec')</script>" not in html
    assert "<script>alert('rep')</script>" not in html
    assert "<script>alert('claim')</script>" not in html
    assert "regex_<script>" not in html


def test_save_interactive_html_with_evidence(tmp_path: Path):
    """Verify save_interactive_html forwards evidence and gaps to file."""
    paper = PaperRecord(id="p-save", title="Saved With Evidence", year=2023)
    ev = EvidenceRecord(
        id="ev-s",
        paper_id="p-save",
        evidence_type="abstract",
        extracted_text="Scalability is bounded by bandwidth.",
        extraction_method="rule_based",
    )
    gap = PaperGapRecord(
        id="gap-s",
        paper_id="p-save",
        gap_type="generalization_bound",
        claim_summary="Bandwidth bound on scaling",
        primary_evidence_id="ev-s",
        verification_status="corroborated",
        corroborating_count=3,
    )

    out_file = tmp_path / "viz" / "evidence_lineage.html"
    returned = save_interactive_html(
        output_path=out_file,
        graph_title="Lineage With Evidence",
        papers=[paper],
        citations=[],
        depths={"p-save": 0},
        paper_gaps={"p-save": [gap]},
        evidence_map={"ev-s": ev},
    )

    assert returned == out_file
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Lineage With Evidence" in content
    assert "Bandwidth bound on scaling" in content
    assert "Scalability is bounded by bandwidth." in content
    assert "Corroborated (3 sources)" in content



def test_visualizer_renders_sota_badge_and_benchmark_section():
    """Verify Vis.js SOTA node styling, legend, and drawer benchmark performance cards."""
    paper = PaperRecord(id="p-sota", title="Winning Method", year=2024)
    bm = BenchmarkRecord(id="bm-1", name="HumanEval", domain="Code Generation")
    m = EvaluationMetricRecord(id="m-1", name="pass@1", goal="maximize", unit="%")
    cond = EvaluationConditionRecord(id="cond-1", name="0-shot Greedy", dataset_split="test", notes="greedy temp=0.0")
    ev = EvidenceRecord(
        id="ev-bm",
        paper_id="p-sota",
        evidence_type="benchmark_table",
        source_section="Section 4.1",
        extracted_text="Evaluated on HumanEval pass@1 achieving 88.5% outperforming baseline.",
        extraction_method="table_parser",
    )
    res = BenchmarkResultRecord(
        id="r-1",
        paper_id="p-sota",
        benchmark_id="bm-1",
        metric_id="m-1",
        condition_id="cond-1",
        metric_value=88.5,
        is_sota=True,
        rank=1,
        table_or_figure="Table 2",
        evidence_id="ev-bm",
    )

    html = generate_interactive_html(
        "Benchmark Map",
        [paper],
        [],
        {"p-sota": 1},
        benchmark_results={"p-sota": [res]},
        benchmarks_map={"bm-1": bm},
        metrics_map={"m-1": m},
        conditions_map={"cond-1": cond},
        evidence_map={"ev-bm": ev},
    )

    # Canvas node styling: gold border / background, SOTA leader label / title
    assert ("#d97706" in html or "#f59e0b" in html)
    assert "#fef3c7" in html
    assert "SOTA Leader" in html

    # Legend
    assert "⭐ SOTA Leader (Verified Benchmark Performance)" in html

    # Drawer section
    assert ("Empirical Benchmark Performance & SOTA Results" in html or "Empirical Benchmark Performance &amp; SOTA Results" in html)
    assert "HumanEval" in html
    assert "Code Generation" in html
    assert "88.5%" in html
    assert "0-shot Greedy" in html
    assert "Table 2" in html
    assert "Evaluated on HumanEval pass@1 achieving 88.5%" in html


def test_visualizer_sota_node_role_without_benchmark_results():
    """Verify a paper marked sota_leader via node_roles receives gold styling."""
    paper = PaperRecord(id="p-leader", title="Leader By Role", year=2023)
    html = generate_interactive_html(
        "Role Map",
        [paper],
        [],
        {"p-leader": 0},
        node_roles={"p-leader": "sota_leader"},
    )
    assert ("#d97706" in html or "#f59e0b" in html)
    assert "#fef3c7" in html
    assert "SOTA Leader" in html


def test_visualizer_benchmark_xss_sanitization():
    """Verify all benchmark fields, conditions, metrics, and quotes undergo strict XSS escaping."""
    paper = PaperRecord(id="p-xss-bm", title="XSS Paper", year=2024)
    bm = BenchmarkRecord(
        id="bm-evil",
        name="<script>alert('bm-name')</script>",
        domain="<img src=x onerror=alert('bm-domain')>",
    )
    m = EvaluationMetricRecord(
        id="m-evil",
        name="<script>alert('metric')</script>",
        goal="maximize",
        unit="<b onclick=alert(1)>%</b>",
    )
    cond = EvaluationConditionRecord(
        id="cond-evil",
        name="<svg onload=alert('cond')>",
        notes="Notes <script>alert('notes')</script>",
    )
    ev = EvidenceRecord(
        id="ev-evil-bm",
        paper_id="p-xss-bm",
        evidence_type="table",
        extracted_text="Quote with <script>alert('quote')</script>",
        extraction_method="rule_based",
    )
    res = BenchmarkResultRecord(
        id="r-evil",
        paper_id="p-xss-bm",
        benchmark_id="bm-evil",
        metric_id="m-evil",
        condition_id="cond-evil",
        metric_value=99.9,
        is_sota=True,
        table_or_figure="<script>alert('tbl')</script>",
        evidence_id="ev-evil-bm",
    )

    html = generate_interactive_html(
        "XSS Benchmark Test",
        [paper],
        [],
        {"p-xss-bm": 0},
        benchmark_results={"p-xss-bm": [res]},
        benchmarks_map={"bm-evil": bm},
        metrics_map={"m-evil": m},
        conditions_map={"cond-evil": cond},
        evidence_map={"ev-evil-bm": ev},
    )

    # Zero unescaped malicious scripts
    assert "<script>alert('bm-name')</script>" not in html
    assert "<img src=x onerror=alert('bm-domain')>" not in html
    assert "<script>alert('metric')</script>" not in html
    assert "<b onclick=alert(1)>%</b>" not in html
    assert "<svg onload=alert('cond')>" not in html
    assert "<script>alert('notes')</script>" not in html
    assert "<script>alert('quote')</script>" not in html
    assert "<script>alert('tbl')</script>" not in html


def test_save_interactive_html_with_benchmarks(tmp_path: Path):
    """Verify save_interactive_html forwards benchmark results, metrics, and conditions."""
    paper = PaperRecord(id="p-save-bm", title="Save Benchmark Paper", year=2024)
    bm = BenchmarkRecord(id="bm-s", name="MMLU", domain="Reasoning")
    m = EvaluationMetricRecord(id="m-s", name="accuracy", goal="maximize", unit="%")
    res = BenchmarkResultRecord(
        id="r-s",
        paper_id="p-save-bm",
        benchmark_id="bm-s",
        metric_id="m-s",
        metric_value=85.2,
        is_sota=False,
        table_or_figure="Figure 3",
    )

    out_file = tmp_path / "viz" / "benchmark_lineage.html"
    returned = save_interactive_html(
        output_path=out_file,
        graph_title="Lineage With Benchmarks",
        papers=[paper],
        citations=[],
        depths={"p-save-bm": 0},
        benchmark_results={"p-save-bm": [res]},
        benchmarks_map={"bm-s": bm},
        metrics_map={"m-s": m},
    )

    assert returned == out_file
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    assert "Lineage With Benchmarks" in content
    assert "MMLU" in content
    assert "Reasoning" in content
    assert "accuracy: 85.2%" in content
    assert "Figure 3" in content


def test_visualizer_backward_compatibility_none_benchmarks():
    """Verify visualizer functions properly when benchmark arguments are None."""
    paper = PaperRecord(id="p-compat", title="Compat Paper", year=2021)
    html = generate_interactive_html(
        "Compat Graph",
        [paper],
        [],
        {"p-compat": 0},
        benchmark_results=None,
        benchmarks_map=None,
        metrics_map=None,
        conditions_map=None,
    )
    assert "Compat Graph" in html
    assert "Compat Paper" in html
