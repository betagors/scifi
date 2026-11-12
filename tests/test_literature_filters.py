"""
Unit and integration tests for literature domain-agnostic filters:
- Publication year window (--min-year, --max-year)
- Universal venue prestige (--venue-tier top / all)
- Evidence density (--require-evidence)
- LiteratureStore venue persistence
- CLI and FastMCP parameter plumbing
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import scifi.cli
from scifi.literature.lineage import LineageCrawler
from scifi.literature.models import (
    PaperRecord,
)
from scifi.literature.resolver import classify_venue_tier
from scifi.literature.store import LiteratureStore


def test_paper_record_venue_fields_and_serialization():
    """Verify venue_name and venue_tier fields serialize and deserialize cleanly."""
    paper = PaperRecord(
        id="P-test",
        title="Edge UAV Optimization",
        year=2023,
        venue_name="IEEE Transactions on Mobile Computing",
        venue_tier="top",
    )
    d = paper.to_dict()
    assert d["venue_name"] == "IEEE Transactions on Mobile Computing"
    assert d["venue_tier"] == "top"

    rehydrated = PaperRecord.from_dict(d)
    assert rehydrated.venue_name == "IEEE Transactions on Mobile Computing"
    assert rehydrated.venue_tier == "top"


def test_classify_venue_tier():
    """Test domain-agnostic venue tier classification for journals, conferences, preprints."""
    # Top CS/Networking/AI venues
    assert classify_venue_tier("IEEE Transactions on Mobile Computing") == "top"
    assert classify_venue_tier("IEEE Transactions on Wireless Communications") == "top"
    assert classify_venue_tier("ACM Transactions on Computer Systems") == "top"
    assert classify_venue_tier("IEEE INFOCOM 2021 - IEEE Conference on Computer Communications") == "top"
    assert classify_venue_tier("ACM SIGCOMM 2022") == "top"
    assert classify_venue_tier("Advances in Neural Information Processing Systems (NeurIPS)") == "top"
    assert classify_venue_tier("International Conference on Machine Learning (ICML)") == "top"
    assert classify_venue_tier("IEEE/CVF Conference on Computer Vision and Pattern Recognition") == "top"
    assert classify_venue_tier("Nature") == "top"
    assert classify_venue_tier("Science") == "top"
    assert classify_venue_tier("Proceedings of the National Academy of Sciences") == "top"

    # Preprints / unranked
    assert classify_venue_tier("arXiv") == "preprint"
    assert classify_venue_tier("arXiv preprint arXiv:2104.12345") == "preprint"
    assert classify_venue_tier(None) == "preprint"
    assert classify_venue_tier("") == "preprint"

    # Standard / regional venues
    assert classify_venue_tier("Journal of Ambient Intelligence and Humanized Computing") == "standard"
    assert classify_venue_tier("Sensors") == "standard"


def test_store_persists_and_rehydrates_venue(tmp_path: Path):
    """Verify LiteratureStore stores and rehydrates venue_name and venue_tier."""
    db_path = tmp_path / "venue_test.db"
    store = LiteratureStore(db_path)

    paper = PaperRecord(
        id="P-venue-1",
        title="Resource Allocation in UAV Networks",
        year=2022,
        venue_name="IEEE Transactions on Wireless Communications",
        venue_tier="top",
    )
    store.create_or_get_graph("g1", "Test Graph", "P-venue-1")
    store.save_paper(paper, "g1", "seed", 0)

    # Fetch paper individually
    fetched = store.get_paper("P-venue-1")
    assert fetched is not None
    assert fetched.venue_name == "IEEE Transactions on Wireless Communications"
    assert fetched.venue_tier == "top"

    # Fetch via graph papers
    graph_papers = store.get_graph_papers("g1")
    assert len(graph_papers) == 1
    assert graph_papers[0].venue_name == "IEEE Transactions on Wireless Communications"
    assert graph_papers[0].venue_tier == "top"

    store.close()


def test_crawler_is_paper_accepted_year_filter():
    """Verify min_year and max_year filters on candidate papers."""
    crawler = LineageCrawler()

    paper_old = PaperRecord(id="p-2015", title="Old Paper", year=2015)
    paper_mid = PaperRecord(id="p-2021", title="Mid Paper", year=2021)
    paper_fut = PaperRecord(id="p-2028", title="Future Paper", year=2028)

    # Without filters, all accepted
    assert crawler.is_paper_accepted(paper_old) is True
    assert crawler.is_paper_accepted(paper_mid) is True
    assert crawler.is_paper_accepted(paper_fut) is True

    # min_year filter
    assert crawler.is_paper_accepted(paper_old, min_year=2020) is False
    assert crawler.is_paper_accepted(paper_mid, min_year=2020) is True
    assert crawler.is_paper_accepted(paper_fut, min_year=2020) is True

    # max_year filter
    assert crawler.is_paper_accepted(paper_old, max_year=2025) is True
    assert crawler.is_paper_accepted(paper_mid, max_year=2025) is True
    assert crawler.is_paper_accepted(paper_fut, max_year=2025) is False

    # Window [2020, 2025]
    assert crawler.is_paper_accepted(paper_old, min_year=2020, max_year=2025) is False
    assert crawler.is_paper_accepted(paper_mid, min_year=2020, max_year=2025) is True
    assert crawler.is_paper_accepted(paper_fut, min_year=2020, max_year=2025) is False


def test_crawler_is_paper_accepted_venue_filter():
    """Verify venue_tier filter on candidate papers."""
    crawler = LineageCrawler()

    top_paper = PaperRecord(id="p-top", title="Top Paper", year=2022, venue_tier="top")
    std_paper = PaperRecord(id="p-std", title="Std Paper", year=2022, venue_tier="standard")
    prep_paper = PaperRecord(id="p-prep", title="Preprint Paper", year=2022, venue_tier="preprint")

    # venue_tier="all" or None allows all
    assert crawler.is_paper_accepted(top_paper, venue_tier="all") is True
    assert crawler.is_paper_accepted(std_paper, venue_tier="all") is True
    assert crawler.is_paper_accepted(prep_paper, venue_tier="all") is True

    # venue_tier="top" only allows top
    assert crawler.is_paper_accepted(top_paper, venue_tier="top") is True
    assert crawler.is_paper_accepted(std_paper, venue_tier="top") is False
    assert crawler.is_paper_accepted(prep_paper, venue_tier="top") is False


def test_crawler_is_paper_accepted_require_evidence():
    """Verify require_evidence filters out papers with no gaps and no benchmarks."""
    crawler = LineageCrawler()

    # Paper with gap keyword in abstract
    gap_paper = PaperRecord(
        id="p-gap",
        title="UAV Edge Latency",
        year=2022,
        abstract="We optimize UAV latency. However, high mobility remains a prohibitive challenge.",
    )
    # Paper with benchmark result keyword in abstract
    bm_paper = PaperRecord(
        id="p-bm",
        title="UAV Image Classification",
        year=2023,
        abstract="Our edge model achieves 89.4% accuracy on ImageNet with lower inference cost.",
    )
    # Generic paper with no gap or benchmark in abstract
    vague_paper = PaperRecord(
        id="p-vague",
        title="A Survey on Networks",
        year=2021,
        abstract="In this survey, we discuss network architectures and wireless protocols.",
    )

    assert crawler.is_paper_accepted(gap_paper, require_evidence=True) is True
    assert crawler.is_paper_accepted(bm_paper, require_evidence=True) is True
    assert crawler.is_paper_accepted(vague_paper, require_evidence=True) is False


def test_crawl_lineage_filters_candidates(tmp_path: Path):
    """Verify LineageCrawler.crawl_lineage excludes candidate references and citations that violate filters."""
    db_path = tmp_path / "crawl_filter.db"
    store = LiteratureStore(db_path)

    seed_paper = PaperRecord(
        id="P-seed",
        title="UAV Edge Optimization 2021",
        year=2021,
        citation_count=50,
        venue_name="IEEE Transactions on Wireless Communications",
        venue_tier="top",
        abstract="We introduce optimization for UAVs. However, battery lifetime limits flight duration.",
    )

    # Candidates:
    # ref_old: 2012 (older than min_year 2020)
    # ref_modern: 2020, top venue
    # cit_future: 2027 (violates max_year 2025)
    # cit_valid: 2022, top venue
    ref_old = PaperRecord(id="ref-old", title="Old UAV", year=2012, citation_count=100)
    ref_modern = PaperRecord(
        id="ref-modern",
        title="Modern UAV Foundation",
        year=2020,
        citation_count=40,
        venue_name="IEEE INFOCOM",
        venue_tier="top",
        abstract="However, decentralized UAV coordination remains an open limitation.",
    )
    cit_future = PaperRecord(id="cit-future", title="Far Future", year=2027, citation_count=5)
    cit_valid = PaperRecord(
        id="cit-valid",
        title="Valid Frontier",
        year=2022,
        citation_count=15,
        venue_name="ACM SIGCOMM",
        venue_tier="top",
        abstract="Empirical evaluation shows 94.2% accuracy on benchmark test split.",
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve_by_title.return_value = seed_paper
    mock_resolver.resolve_references.return_value = [ref_old, ref_modern]
    mock_resolver.resolve_citations.return_value = [cit_future, cit_valid]

    crawler = LineageCrawler(resolver=mock_resolver, store=store)
    graph_id, papers, citations = crawler.crawl_lineage(
        "UAV Edge Optimization 2021",
        depth=1,
        min_year=2020,
        max_year=2025,
        venue_tier="top",
        require_evidence=True,
    )

    paper_ids = [p.id for p in papers]
    assert "P-seed" in paper_ids
    assert "ref-modern" in paper_ids
    assert "cit-valid" in paper_ids

    # ref-old and cit-future must be filtered out
    assert "ref-old" not in paper_ids
    assert "cit-future" not in paper_ids

    store.close()


def test_cli_report_with_filter_flags(tmp_path: Path):
    """Verify CLI argument parser correctly parses --min-year, --max-year, --venue-tier, --require-evidence."""
    out_dir = tmp_path / "cli_test_dir"
    db_file = tmp_path / "cli_test.db"

    with patch("scifi.literature.cli.LineageCrawler") as MockCrawler:
        instance = MockCrawler.return_value
        sample_seed = PaperRecord(id="S1", title="Sample Seed", year=2022)
        instance.crawl_lineage.return_value = ("graph-123", [sample_seed], [])
        instance.compute_topological_depths.return_value = {"S1": 0}

        ret = scifi.cli.main(
            [
                "literature",
                "report",
                "test query",
                "--min-year",
                "2020",
                "--max-year",
                "2025",
                "--venue-tier",
                "top",
                "--require-evidence",
                "--output-dir",
                str(out_dir),
                "--db",
                str(db_file),
            ]
        )
        assert ret == 0

        # Verify crawl_lineage called with filter parameters
        instance.crawl_lineage.assert_called_once()
        _, kwargs = instance.crawl_lineage.call_args
        assert kwargs.get("min_year") == 2020
        assert kwargs.get("max_year") == 2025
        assert kwargs.get("venue_tier") == "top"
        assert kwargs.get("require_evidence") is True


def test_server_scifi_map_literature_forwards_filters():
    """Verify FastMCP tool scifi_map_literature accepts and forwards filter parameters."""
    from scifi.server import scifi_map_literature

    with patch("scifi.server.LineageCrawler") as MockCrawler:
        instance = MockCrawler.return_value
        sample_seed = PaperRecord(id="S1", title="Sample Seed", year=2022)
        instance.crawl_lineage.return_value = ("graph-123", [sample_seed], [])
        instance.compute_topological_depths.return_value = {"S1": 0}

        res = scifi_map_literature(
            query="test query",
            min_year=2020,
            max_year=2026,
            venue_tier="top",
            require_evidence=True,
        )
        assert res["status"] == "SUCCESS"

        _, kwargs = instance.crawl_lineage.call_args
        assert kwargs.get("min_year") == 2020
        assert kwargs.get("max_year") == 2026
        assert kwargs.get("venue_tier") == "top"
        assert kwargs.get("require_evidence") is True
