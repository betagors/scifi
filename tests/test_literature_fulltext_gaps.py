"""
Unit tests for Full-Text PDF Extraction, Local PDF Ingestion, and Full-Text Gap Mining.
"""

from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from pypdf import PdfWriter

from scifi.literature.extractor import extract_sections_from_text
from scifi.literature.fetcher import find_local_pdf, resolve_paper_pdf
from scifi.literature.gaps import GapExtractor
from scifi.literature.lineage import LineageCrawler
from scifi.literature.models import (
    CitationContextRecord,
    PaperGapRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
)
from scifi.literature.store import LiteratureStore


def test_extract_sections_from_text():
    sample_text = """
    A Novel Framework for Resilient UAV Coordination
    Author Name

    Abstract:
    We present an optimization framework for multi-UAV path planning under uncertain dynamics.
    
    1. Introduction
    Unmanned Aerial Vehicles (UAVs) have received significant attention.
    
    II. SYSTEM MODEL AND PROBLEM FORMULATION
    We consider a network of N UAVs operating in a 3D coordinate space.
    We assume perfect channel state information between all nodes and the ground station.
    The communication topology is assumed static during each allocation epoch.
    The worst-case computational complexity scales as O(N^3) per scheduling iteration.
    
    III. SIMULATION RESULTS
    We evaluate the scheme using 100 Monte Carlo runs.
    
    IV. LIMITATIONS AND CONCLUSION
    A limitation of our approach is that performance degrades significantly under non-Gaussian noise.
    Moreover, the proposed algorithm was evaluated only on synthetic benchmarks with N <= 20.
    In conclusion, we showed resilience guarantees. Future work will investigate decentralized consensus.
    
    REFERENCES
    [1] A. Vaswani et al.
    """

    sections = extract_sections_from_text(sample_text)
    assert "optimization framework" in sections["abstract"]
    assert "We consider a network of N UAVs" in sections["system_model_or_method"]
    assert "perfect channel state information" in sections["system_model_or_method"]
    assert "O(N^3)" in sections["system_model_or_method"]
    assert "performance degrades significantly" in sections["limitations_and_conclusion"]
    assert "Future work" in sections["limitations_and_conclusion"]


def test_extract_fulltext_gaps():
    paper = PaperRecord(
        id="paper-uav-test",
        title="Resilient UAV Trajectory Optimization",
        year=2023,
    )

    sections = {
        "system_model_or_method": (
            "We assume perfect channel state information and zero packet loss. "
            "The computational complexity of the centralized solver scales as O(N^3)."
        ),
        "limitations_and_conclusion": (
            "A notable limitation of our method is that it degrades under non-Gaussian noise. "
            "Furthermore, scaling to dense swarms remains an open challenge left for future work."
        ),
    }

    extractor = GapExtractor()
    gaps = extractor.extract_fulltext_gaps(paper, sections)

    assert len(gaps) >= 3

    # Check system model assumptions & complexity
    gap_types = [g.gap_type for _, g in gaps]
    evidence_types = [ev.evidence_type for ev, _ in gaps]
    sections_mined = [ev.source_section for ev, _ in gaps]

    assert "unstated_assumption" in gap_types
    assert "computational_complexity" in gap_types
    assert "system_model_assumption" in evidence_types or "methodology_complexity" in evidence_types
    assert "System Model / Methodology" in sections_mined
    assert "Limitations & Conclusion" in sections_mined

    # Check confidence
    for ev, g in gaps:
        assert ev.confidence >= 0.90
        assert ev.reporting_paper_id is None  # self-reported by authors


def test_corroborate_fulltext_gap_with_citation():
    paper = PaperRecord(
        id="paper-seed",
        title="Centralized UAV Coordination",
        year=2022,
    )

    # 1. Paper self-reports complexity O(N^3) in full-text system model
    sections = {
        "system_model_or_method": "The computational complexity scales as O(N^3) requiring centralized processing.",
        "limitations_and_conclusion": "Future work should investigate distributed coordination.",
    }

    extractor = GapExtractor()
    fulltext_gaps = extractor.extract_fulltext_gaps(paper, sections)

    # 2. Citing paper points out the same computational bottleneck
    context = CitationContextRecord(
        id="ctx-1",
        source_paper_id="citing-paper-1",
        target_paper_id="paper-seed",
        context_text="However, Centralized UAV Coordination incurs prohibitive computational complexity O(N^3) as nodes increase.",
        section_name="Related Work",
    )
    citation_gaps = extractor.extract_citation_context_gaps(paper, [context])

    all_gaps = fulltext_gaps + citation_gaps
    corroborated = extractor.corroborate_gaps(all_gaps)

    # The O(N^3) complexity gap should be corroborated between self-reported fulltext and citing context
    complexity_gaps = [g for _, g in corroborated if g.gap_type == "computational_complexity"]
    assert len(complexity_gaps) >= 1
    assert any(g.verification_status == "corroborated" for g in complexity_gaps)
    assert any(g.corroborating_count >= 1 for g in complexity_gaps)


def test_find_local_pdf(tmp_path):
    pdf_dir = tmp_path / "papers"
    pdf_dir.mkdir()

    arxiv_file = pdf_dir / "2301.12345.pdf"
    arxiv_file.write_text("%PDF-1.4 dummy", encoding="utf-8")

    doi_file = pdf_dir / "10.1109_TWC.2023.3291234.pdf"
    doi_file.write_text("%PDF-1.4 dummy", encoding="utf-8")

    title_file = pdf_dir / "deep_reinforcement_learning_for_uav_networks.pdf"
    title_file.write_text("%PDF-1.4 dummy", encoding="utf-8")

    # 1. Match by arXiv ID
    p_arxiv = PaperRecord(
        id="paper-1",
        title="Unmanned Flight",
        identifiers=[PaperIdentifierRecord(paper_id="paper-1", provider="arxiv", external_id="2301.12345")],
    )
    found_arxiv = find_local_pdf(p_arxiv, search_dirs=[pdf_dir])
    assert found_arxiv is not None
    assert found_arxiv.name == "2301.12345.pdf"

    # 2. Match by DOI
    p_doi = PaperRecord(
        id="paper-2",
        title="Wireless Channel Modeling",
        identifiers=[PaperIdentifierRecord(paper_id="paper-2", provider="doi", external_id="10.1109/TWC.2023.3291234")],
    )
    found_doi = find_local_pdf(p_doi, search_dirs=[pdf_dir])
    assert found_doi is not None
    assert found_doi.name == "10.1109_TWC.2023.3291234.pdf"

    # 3. Match by title
    p_title = PaperRecord(
        id="paper-3",
        title="Deep Reinforcement Learning for UAV Networks",
    )
    found_title = find_local_pdf(p_title, search_dirs=[pdf_dir])
    assert found_title is not None
    assert found_title.name == "deep_reinforcement_learning_for_uav_networks.pdf"

    # 4. Fallback on paper.locations local_pdf_path
    p_loc = PaperRecord(
        id="paper-4",
        title="Custom Local File",
        locations=[PaperLocationRecord(id="loc-1", paper_id="paper-4", location_type="local", local_pdf_path=str(arxiv_file))],
    )
    found_loc = find_local_pdf(p_loc, search_dirs=[tmp_path / "empty"])
    assert found_loc is not None
    assert found_loc == arxiv_file


def test_lineage_crawler_with_fulltext_gaps(tmp_path):
    # Setup temporary store and dummy PDF
    db_path = tmp_path / "test_lineage.db"
    store = LiteratureStore(db_path)

    pdf_dir = tmp_path / "papers"
    pdf_dir.mkdir()

    # Create dummy PDF file
    dummy_pdf = pdf_dir / "2301.12345.pdf"
    dummy_pdf.write_text("%PDF-1.4 dummy", encoding="utf-8")

    seed_paper = PaperRecord(
        id="paper-seed",
        title="Scalable Multi-Agent Path Planning",
        year=2023,
        abstract="We present an algorithm for multi-agent coordination.",
        identifiers=[PaperIdentifierRecord(paper_id="paper-seed", provider="arxiv", external_id="2301.12345")],
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve_paper.return_value = seed_paper
    mock_resolver.resolve_by_arxiv_id.return_value = seed_paper
    mock_resolver.resolve_references.return_value = []
    mock_resolver.resolve_citations.return_value = []

    crawler = LineageCrawler(resolver=mock_resolver, store=store)

    # Mock extract_pdf_text to return realistic sections
    mock_sections = {
        "abstract": "We present an algorithm for multi-agent coordination.",
        "system_model_or_method": "We assume perfect channel state information. Centralized coordination complexity scales as O(N^3).",
        "limitations_and_conclusion": "A notable limitation of our method is that performance degrades under asynchronous delays.",
        "raw_sample": "...",
    }

    with patch("scifi.literature.lineage.extract_pdf_text") as mock_extract:
        mock_extract.return_value = {
            "status": "SUCCESS",
            "total_pages": 10,
            "sections": mock_sections,
            **mock_sections,
        }

        graph_id, papers, citations = crawler.crawl_lineage(
            query=seed_paper,
            depth=1,
            max_papers=5,
            extract_gaps=True,
            extract_fulltext_gaps=True,
            pdf_dir=pdf_dir,
        )

        assert len(papers) == 1
        mock_extract.assert_called_once()

        # Check persisted gaps in store
        gaps_map = store.get_graph_gaps(graph_id)
        assert "paper-seed" in gaps_map
        paper_gaps = gaps_map["paper-seed"]
        assert len(paper_gaps) >= 2

        gap_types = [g.gap_type for g in paper_gaps]
        assert "unstated_assumption" in gap_types or "computational_complexity" in gap_types

        evidence_map = store.get_graph_evidence(graph_id)
        ev_sections = [ev.source_section for ev in evidence_map.values()]
        assert "System Model / Methodology" in ev_sections or "Limitations & Conclusion" in ev_sections
