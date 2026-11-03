"""
Unit and integration tests for scifi.literature.visualizer:
Verifies standalone Vis.js HTML rendering, hierarchical DAG layout,
color-coded access tiers, slide-out details drawer, and strict XSS sanitization.
"""

from pathlib import Path

import pytest

from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
)
from scifi.literature.visualizer import (
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
