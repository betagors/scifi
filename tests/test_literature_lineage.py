"""
Unit and integration tests for multi-signal lineage traversal, cycle detection,
topological depth calculation, and store persistence in scifi.literature.lineage.
"""

import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scifi.literature.lineage import LineageCrawler
from scifi.literature.models import CitationRecord, PaperIdentifierRecord, PaperRecord
from scifi.literature.resolver import PaperResolver
from scifi.literature.store import LiteratureStore


def test_backward_foundation_ranking():
    """
    Test multi-signal backward selection & ranking:
    Seed references ranked by composite weight: log(1 + C_global) + 2.0 * I_influential.
    Top 5 selected, tagged as 'foundation'.
    """
    crawler = LineageCrawler()

    # Create candidate references:
    # Ref 1: 100 citations, not influential -> ln(101) ~ 4.615
    # Ref 2: 50 citations, influential -> ln(51) + 2.0 ~ 3.931 + 2.0 = 5.931 (wins over Ref 1)
    # Ref 3: 10 citations, not influential -> ln(11) ~ 2.398
    # Ref 4: 5 citations, influential -> ln(6) + 2.0 ~ 1.792 + 2.0 = 3.792 (wins over Ref 3)
    # Ref 5: 1000 citations, not influential -> ln(1001) ~ 6.909 (highest)
    # Ref 6: 0 citations, not influential -> ln(1) = 0.0 (lowest)
    # Ref 7: 1 citation, not influential -> ln(2) ~ 0.693

    refs = [
        PaperRecord(id="ref-1", title="Ref 1", year=2010, citation_count=100, influential_citation_count=0),
        PaperRecord(id="ref-2", title="Ref 2", year=2012, citation_count=50, influential_citation_count=5),
        PaperRecord(id="ref-3", title="Ref 3", year=2015, citation_count=10, influential_citation_count=0),
        PaperRecord(id="ref-4", title="Ref 4", year=2016, citation_count=5, influential_citation_count=1),
        PaperRecord(id="ref-5", title="Ref 5", year=2008, citation_count=1000, influential_citation_count=0),
        PaperRecord(id="ref-6", title="Ref 6", year=2018, citation_count=0, influential_citation_count=0),
        PaperRecord(id="ref-7", title="Ref 7", year=2019, citation_count=1, influential_citation_count=0),
    ]

    ranked = crawler.rank_foundations(refs, top_k=5)
    assert len(ranked) == 5

    # Expected order: ref-5 (6.91), ref-2 (5.93), ref-1 (4.62), ref-4 (3.79), ref-3 (2.40)
    ranked_ids = [p.id for p in ranked]
    assert ranked_ids == ["ref-5", "ref-2", "ref-1", "ref-4", "ref-3"]


def test_forward_frontier_ranking():
    """
    Test multi-signal forward selection & ranking:
    Papers citing seed ranked by annualized velocity: C / max(0.5, CurrentYear - Year + 1).
    Select top 5 recent works (<= 3 years old). Tag role as 'frontier'.
    """
    crawler = LineageCrawler()
    cur_year = datetime.date.today().year

    # Candidate citing papers:
    # cit-1: current year, 20 citations -> 20 / max(0.5, 0 + 1) = 20.0
    # cit-2: 1 year old, 30 citations -> 30 / (1 + 1) = 15.0
    # cit-3: 2 years old, 45 citations -> 45 / (2 + 1) = 15.0
    # cit-4: 3 years old, 40 citations -> 40 / (3 + 1) = 10.0
    # cit-5: 1 year old, 10 citations -> 10 / (1 + 1) = 5.0
    # cit-old: 4 years old (too old > 3), 500 citations -> excluded!
    # cit-ancient: 10 years old, 1000 citations -> excluded!
    citing = [
        PaperRecord(id="cit-1", title="Cit 1", year=cur_year, citation_count=20),
        PaperRecord(id="cit-2", title="Cit 2", year=cur_year - 1, citation_count=30),
        PaperRecord(id="cit-3", title="Cit 3", year=cur_year - 2, citation_count=45),
        PaperRecord(id="cit-4", title="Cit 4", year=cur_year - 3, citation_count=40),
        PaperRecord(id="cit-5", title="Cit 5", year=cur_year - 1, citation_count=10),
        PaperRecord(id="cit-old", title="Cit Old", year=cur_year - 4, citation_count=500),
        PaperRecord(id="cit-ancient", title="Cit Ancient", year=cur_year - 10, citation_count=1000),
    ]

    ranked = crawler.rank_frontier(citing, top_k=5)
    assert len(ranked) == 5

    ranked_ids = [p.id for p in ranked]
    assert "cit-old" not in ranked_ids
    assert "cit-ancient" not in ranked_ids
    assert ranked_ids[0] == "cit-1"  # Velocity 20.0
    assert ranked_ids[-1] == "cit-5"  # Velocity 5.0


def test_cycle_detection_and_rectification_mutual():
    """
    Test 2-cycle detection and rectification:
    Paper A (2017) and Paper B (2022) mutually cite each other.
    A citing B is a chronological violation (older paper citing strictly newer paper).
    Rectification should resolve the cycle using publication year hierarchy.
    """
    crawler = LineageCrawler()

    paper_a = PaperRecord(id="paper-a", title="A", year=2017)
    paper_b = PaperRecord(id="paper-b", title="B", year=2022)
    papers = [paper_a, paper_b]

    citations = [
        CitationRecord(source_paper_id="paper-a", target_paper_id="paper-b"),  # Violator: 2017 cites 2022
        CitationRecord(source_paper_id="paper-b", target_paper_id="paper-a"),  # Valid: 2022 cites 2017
    ]

    rectified = crawler.detect_and_rectify_cycles(papers, citations)
    assert len(rectified) == 1
    assert rectified[0].source_paper_id == "paper-b"
    assert rectified[0].target_paper_id == "paper-a"


def test_cycle_detection_and_rectification_triangle():
    """
    Test 3-cycle detection and rectification:
    A (2015) -> B (2020) -> C (2018) -> A (2015)
    Edge A -> B is an older paper citing a newer paper (2015 < 2020).
    Edge C -> A is valid (2018 cites 2015).
    Edge B -> C is valid (2020 cites 2018).
    Rectification must break the cycle by removing the chronological violator.
    """
    crawler = LineageCrawler()

    papers = [
        PaperRecord(id="A", title="A", year=2015),
        PaperRecord(id="B", title="B", year=2020),
        PaperRecord(id="C", title="C", year=2018),
    ]

    citations = [
        CitationRecord(source_paper_id="A", target_paper_id="B"),  # Violator (2015 < 2020)
        CitationRecord(source_paper_id="B", target_paper_id="C"),  # Valid (2020 > 2018)
        CitationRecord(source_paper_id="C", target_paper_id="A"),  # Valid (2018 > 2015)
    ]

    rectified = crawler.detect_and_rectify_cycles(papers, citations)
    assert len(rectified) == 2
    pairs = {(c.source_paper_id, c.target_paper_id) for c in rectified}
    assert ("A", "B") not in pairs
    assert ("B", "C") in pairs
    assert ("C", "A") in pairs


def test_cycle_detection_self_loop():
    """Test that self-loops (paper citing itself) are pruned during rectification."""
    crawler = LineageCrawler()
    papers = [PaperRecord(id="A", title="Paper A", year=2020)]
    citations = [CitationRecord(source_paper_id="A", target_paper_id="A")]

    rectified = crawler.detect_and_rectify_cycles(papers, citations)
    assert len(rectified) == 0


def test_cycle_detection_same_year_date_tiebreaker():
    """
    Test cycle rectification when papers share the same year but have distinct publication_date strings.
    """
    crawler = LineageCrawler()
    p1 = PaperRecord(id="P1", title="Paper 1", year=2020, publication_date="2020-02-01")
    p2 = PaperRecord(id="P2", title="Paper 2", year=2020, publication_date="2020-09-01")
    papers = [p1, p2]

    # P1 (Feb) cites P2 (Sept) -> P1 is older, citing newer P2!
    # P2 (Sept) cites P1 (Feb) -> P2 is newer, citing older P1 (valid)
    citations = [
        CitationRecord(source_paper_id="P1", target_paper_id="P2"),
        CitationRecord(source_paper_id="P2", target_paper_id="P1"),
    ]

    rectified = crawler.detect_and_rectify_cycles(papers, citations)
    assert len(rectified) == 1
    assert rectified[0].source_paper_id == "P2"
    assert rectified[0].target_paper_id == "P1"


def test_compute_topological_depths_linear():
    """
    Test topological depth assignment:
    Flows from Roots/Foundations (depth 0) -> Intermediate -> Frontier (depth D).
    Citation semantics:
    Seed B cites Foundation A.
    Frontier C cites Seed B.
    """
    crawler = LineageCrawler()

    papers = [
        PaperRecord(id="A", title="Foundation A", year=2010),
        PaperRecord(id="B", title="Seed B", year=2017),
        PaperRecord(id="C", title="Frontier C", year=2024),
    ]

    citations = [
        CitationRecord(source_paper_id="B", target_paper_id="A"),  # B cites A
        CitationRecord(source_paper_id="C", target_paper_id="B"),  # C cites B
    ]

    depths = crawler.compute_topological_depths(papers, citations)
    assert depths["A"] == 0
    assert depths["B"] == 1
    assert depths["C"] == 2


def test_compute_topological_depths_dag():
    """
    Test topological depth on a diamond DAG with multiple foundations and intermediate steps:
    F1 (Foundation) depth 0
    F2 (Foundation) depth 0
    I1 cites F1 -> depth 1
    I2 cites F1 and F2 -> depth 1
    Frontier cites I1 and I2 -> depth 2
    """
    crawler = LineageCrawler()

    papers = [
        PaperRecord(id="F1", title="F1", year=2000),
        PaperRecord(id="F2", title="F2", year=2002),
        PaperRecord(id="I1", title="I1", year=2010),
        PaperRecord(id="I2", title="I2", year=2012),
        PaperRecord(id="FR", title="FR", year=2023),
    ]

    citations = [
        CitationRecord(source_paper_id="I1", target_paper_id="F1"),
        CitationRecord(source_paper_id="I2", target_paper_id="F1"),
        CitationRecord(source_paper_id="I2", target_paper_id="F2"),
        CitationRecord(source_paper_id="FR", target_paper_id="I1"),
        CitationRecord(source_paper_id="FR", target_paper_id="I2"),
    ]

    depths = crawler.compute_topological_depths(papers, citations)
    assert depths["F1"] == 0
    assert depths["F2"] == 0
    assert depths["I1"] == 1
    assert depths["I2"] == 1
    assert depths["FR"] == 2


def test_resolve_seed_formats():
    """Test seed resolution from various query formats: DOI, arXiv ID, OpenAlex ID, and Title."""
    mock_resolver = MagicMock(spec=PaperResolver)
    mock_resolver.resolve_by_openalex_id.return_value = PaperRecord(id="W1", title="Paper 1")
    mock_resolver.resolve_by_doi.return_value = PaperRecord(id="D1", title="Paper 2")
    mock_resolver.resolve_by_arxiv_id.return_value = PaperRecord(id="A1", title="Paper 3")
    mock_resolver.resolve_by_title.return_value = PaperRecord(id="T1", title="Paper 4")

    crawler = LineageCrawler(resolver=mock_resolver, max_request_budget=20)

    # 1. OpenAlex ID
    p_oa = crawler.resolve_seed("W2741809807")
    assert p_oa is not None and p_oa.id == "W1"

    # 2. DOI
    p_doi = crawler.resolve_seed("10.1145/3318464.3389700")
    assert p_doi is not None and p_doi.id == "D1"

    # 3. arXiv ID
    p_arx = crawler.resolve_seed("arxiv:1706.03762")
    assert p_arx is not None and p_arx.id == "A1"

    # 4. Title
    p_title = crawler.resolve_seed("Attention Is All You Need")
    assert p_title is not None and p_title.id == "T1"

    # 5. Direct PaperRecord pass-through
    raw_p = PaperRecord(id="raw", title="Direct")
    p_direct = crawler.resolve_seed(raw_p)
    assert p_direct is raw_p


def test_resolve_seed_unresolvable():
    """Test behavior when seed cannot be resolved: returns empty results cleanly."""
    mock_resolver = MagicMock(spec=PaperResolver)
    mock_resolver.resolve_by_title.return_value = None

    crawler = LineageCrawler(resolver=mock_resolver)
    gid, papers, cits = crawler.crawl_lineage("Nonexistent Paper Title That Does Not Exist")
    assert len(papers) == 0
    assert len(cits) == 0
    assert gid.startswith("graph-")


def test_request_budget_enforcement():
    """
    Test that LineageCrawler enforces a hard ceiling of max_request_budget
    API calls to prevent runaway requests and hanging.
    """
    mock_resolver = MagicMock(spec=PaperResolver)
    mock_resolver.resolve_by_title.return_value = PaperRecord(id="seed", title="Seed Paper", year=2020)
    mock_resolver.resolve_references.return_value = [
        PaperRecord(id=f"ref-{i}", title=f"Ref {i}", year=2015, citation_count=10)
        for i in range(10)
    ]
    mock_resolver.resolve_citations.return_value = [
        PaperRecord(id=f"cit-{i}", title=f"Cit {i}", year=2024, citation_count=15)
        for i in range(10)
    ]

    # Set budget to 2 calls:
    # Call 1: resolve seed
    # Call 2: resolve references
    # Budget exhausted: resolve citations should be skipped
    crawler = LineageCrawler(resolver=mock_resolver, max_request_budget=2)
    graph_id, papers, citations = crawler.crawl_lineage("Seed Paper", depth=1)

    assert crawler.request_count == 2
    # Seed was resolved (1) + references resolved (2)
    assert mock_resolver.resolve_by_title.call_count == 1
    assert mock_resolver.resolve_references.call_count == 1
    assert mock_resolver.resolve_citations.call_count == 0


def test_multi_hop_depth_2_traversal():
    """
    Test 2-hop lineage traversal expanding foundations backward and frontier forward.
    """
    cur_year = datetime.date.today().year

    p_seed = PaperRecord(id="seed", title="Seed", year=2020, citation_count=500)
    p_ref1 = PaperRecord(id="ref1", title="Ref 1", year=2016, citation_count=200)
    p_ref_deep = PaperRecord(id="ref-deep", title="Deep Foundation", year=2005, citation_count=5000)
    p_cit1 = PaperRecord(id="cit1", title="Cit 1", year=cur_year - 2, citation_count=50)
    p_cit_front = PaperRecord(id="cit-front", title="Frontier Leaf", year=cur_year, citation_count=10)

    mock_resolver = MagicMock(spec=PaperResolver)
    mock_resolver.resolve_by_title.return_value = p_seed

    def mock_references(work_id, limit=25):
        if work_id == "seed":
            return [p_ref1]
        elif work_id == "ref1":
            return [p_ref_deep]
        return []

    def mock_citations(work_id, limit=25):
        if work_id == "seed":
            return [p_cit1]
        elif work_id == "cit1":
            return [p_cit_front]
        return []

    mock_resolver.resolve_references.side_effect = mock_references
    mock_resolver.resolve_citations.side_effect = mock_citations

    crawler = LineageCrawler(resolver=mock_resolver, max_request_budget=15)
    gid, papers, cits = crawler.crawl_lineage("Seed", depth=2, max_papers=10)

    paper_ids = {p.id for p in papers}
    assert paper_ids == {"seed", "ref1", "ref-deep", "cit1", "cit-front"}
    assert len(cits) == 4

    depths = crawler.compute_topological_depths(papers, cits)
    assert depths["ref-deep"] == 0
    assert depths["ref1"] == 1
    assert depths["seed"] == 2
    assert depths["cit1"] == 3
    assert depths["cit-front"] == 4


def test_crawl_lineage_integration_with_store(tmp_path: Path):
    """
    End-to-end integration test of crawl_lineage:
    - Resolves seed paper
    - Discovers foundations (backward) and frontier (forward)
    - Detects and rectifies any citation cycles
    - Computes topological depths
    - Automatically persists everything into the graph-scoped LiteratureStore
    """
    db_path = tmp_path / "lineage_test.db"
    store = LiteratureStore(db_path)

    cur_year = datetime.date.today().year
    seed = PaperRecord(id="W-seed", title="Attention Is All You Need", year=2017, citation_count=80000)
    ref_found = PaperRecord(id="W-ref", title="Neural Machine Translation", year=2014, citation_count=20000, influential_citation_count=100)
    cit_front = PaperRecord(id="W-front", title="Modern Transformer Frontier", year=cur_year - 1, citation_count=150)

    # Introduce a cyclic citation where the older paper W-ref erroneously claims to cite W-front
    # and W-front legitimately cites W-seed, and W-seed cites W-ref.
    mock_resolver = MagicMock(spec=PaperResolver)
    mock_resolver.resolve_by_title.return_value = seed
    mock_resolver.resolve_references.return_value = [ref_found]
    mock_resolver.resolve_citations.return_value = [cit_front]

    crawler = LineageCrawler(resolver=mock_resolver, store=store, max_request_budget=10)
    graph_id, papers, citations = crawler.crawl_lineage("Attention Is All You Need", depth=1, graph_id="graph-trans-1")

    assert graph_id == "graph-trans-1"
    assert len(papers) == 3

    paper_ids = {p.id for p in papers}
    assert paper_ids == {"W-seed", "W-ref", "W-front"}

    # Verify store persistence
    stored_papers = store.get_graph_papers("graph-trans-1")
    assert len(stored_papers) == 3

    # Check that topological depths and node roles were correctly stored
    cursor = store.conn.cursor()
    cursor.execute(
        "SELECT paper_id, node_role, topological_depth FROM graph_papers WHERE graph_id = ? ORDER BY topological_depth ASC",
        ("graph-trans-1",),
    )
    rows = cursor.fetchall()
    roles = {r[0]: (r[1], r[2]) for r in rows}

    assert roles["W-ref"][0] == "foundation"
    assert roles["W-ref"][1] == 0

    assert roles["W-seed"][0] == "seed"
    assert roles["W-seed"][1] == 1

    assert roles["W-front"][0] == "frontier"
    assert roles["W-front"][1] == 2

    stored_citations = store.get_graph_citations("graph-trans-1")
    assert len(stored_citations) == 2
    cit_pairs = {(c.source_paper_id, c.target_paper_id) for c in stored_citations}
    assert ("W-seed", "W-ref") in cit_pairs  # Seed cites Foundation
    assert ("W-front", "W-seed") in cit_pairs  # Frontier cites Seed

    store.close()


def test_crawl_lineage_extracts_and_persists_gaps(tmp_path: Path):
    """Verify that LineageCrawler extracts abstract/citation gaps, corroborates, and persists."""
    from scifi.literature.models import CitationContextRecord

    db_path = tmp_path / "gaps_crawl.db"
    store = LiteratureStore(db_path)

    seed_paper = PaperRecord(
        id="P-seed",
        title="Scalable Transformers",
        year=2021,
        citation_count=50,
        abstract="We introduce Scalable Transformers. However, the computational complexity remains quadratic and prohibitive for long sequences.",
        identifiers=[PaperIdentifierRecord(paper_id="P-seed", provider="doi", external_id="10.1234/st2021")],
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve_by_title.return_value = seed_paper
    mock_resolver.resolve_references.return_value = []
    mock_resolver.resolve_citations.return_value = []

    mock_s2 = MagicMock()
    mock_s2.fetch_citation_contexts.return_value = [
        CitationContextRecord(
            id="ctx-1",
            source_paper_id="P-citing",
            target_paper_id="P-seed",
            context_text="While Scalable Transformers improves throughput, its quadratic complexity limits long-context tasks.",
            section_name="Related Work",
        )
    ]

    crawler = LineageCrawler(resolver=mock_resolver, store=store, s2_client=mock_s2)
    graph_id, papers, citations = crawler.crawl_lineage("Scalable Transformers", depth=1, extract_gaps=True)

    assert len(papers) == 1
    gaps_by_paper = store.get_graph_gaps(graph_id)
    assert "P-seed" in gaps_by_paper
    assert len(gaps_by_paper["P-seed"]) >= 1

    ev_map = store.get_graph_evidence(graph_id)
    assert len(ev_map) >= 1

    # Verify citation context was persisted
    contexts = store.get_citation_contexts("P-citing", "P-seed")
    assert len(contexts) == 1
    assert contexts[0].id == "ctx-1"

    store.close()
