"""
Unit and integration tests for graph-scoped SQLite knowledge store.
Verifies WAL mode, busy timeout, foreign keys, multi-graph session isolation,
paper/author/location/version/citation persistence, and read-only query protections.
"""

import threading
import time
from pathlib import Path
import pytest

from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    GraphSessionRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
    PaperVersionRecord,
)
from scifi.literature.store import LiteratureStore


def test_store_session_isolation_and_wal(tmp_path: Path):
    db_path = tmp_path / "test_literature.db"
    store = LiteratureStore(db_path)

    # Verify SQLite configuration pragmas
    journal_mode = store.conn.execute("PRAGMA journal_mode;").fetchone()[0]
    assert journal_mode.lower() == "wal"

    busy_timeout = store.conn.execute("PRAGMA busy_timeout;").fetchone()[0]
    assert busy_timeout == 5000

    foreign_keys = store.conn.execute("PRAGMA foreign_keys;").fetchone()[0]
    assert foreign_keys == 1

    # Create two isolated graph sessions
    g_a = store.create_or_get_graph("graph-a", "Transformer Lineage")
    g_b = store.create_or_get_graph("graph-b", "Quantum Key Distribution")
    assert isinstance(g_a, GraphSessionRecord)
    assert g_a.id == "graph-a"
    assert g_b.id == "graph-b"

    paper_a = PaperRecord(id="p-1", title="Attention Is All You Need", year=2017)
    paper_b = PaperRecord(id="p-2", title="BB84 Protocol", year=1984)

    store.save_paper(paper_a, graph_id="graph-a", node_role="seed")
    store.save_paper(paper_b, graph_id="graph-b", node_role="seed")

    papers_a = store.get_graph_papers("graph-a")
    papers_b = store.get_graph_papers("graph-b")

    assert len(papers_a) == 1
    assert papers_a[0].id == "p-1"
    assert len(papers_b) == 1
    assert papers_b[0].id == "p-2"

    store.close()


def test_read_only_query_blocks_mutations(tmp_path: Path):
    store = LiteratureStore(tmp_path / "test_sec.db")
    store.create_or_get_graph("g-sec", "Security Graph")

    # SELECT succeeds
    rows = store.execute_read_query("SELECT id, title FROM graphs WHERE id = 'g-sec'")
    assert len(rows) == 1
    assert rows[0]["id"] == "g-sec"
    assert rows[0]["title"] == "Security Graph"

    # SELECT with aggregate functions succeeds
    cnt_rows = store.execute_read_query("SELECT count(*) as total FROM graphs")
    assert len(cnt_rows) == 1
    assert cnt_rows[0]["total"] == 1

    # Mutating queries must be denied with PermissionError
    with pytest.raises(PermissionError):
        store.execute_read_query("DROP TABLE papers;")
    with pytest.raises(PermissionError):
        store.execute_read_query("INSERT INTO graphs (id, title) VALUES ('x', 'y');")
    with pytest.raises(PermissionError):
        store.execute_read_query("UPDATE graphs SET title = 'hacked' WHERE id = 'g-sec';")
    with pytest.raises(PermissionError):
        store.execute_read_query("DELETE FROM graphs WHERE id = 'g-sec';")
    with pytest.raises(PermissionError):
        store.execute_read_query("ALTER TABLE graphs ADD COLUMN test_col TEXT;")

    store.close()


def test_save_and_retrieve_paper_with_full_metadata(tmp_path: Path):
    store = LiteratureStore(tmp_path / "test_meta.db")
    store.create_or_get_graph("g-full", "Full Metadata Graph")

    authors = [
        AuthorRecord(id="a-1", name="Ashish Vaswani", orcid="0000-0001-0000-0001", institution="Google Brain"),
        AuthorRecord(id="a-2", name="Noam Shazeer", orcid="0000-0001-0000-0002", institution="Google Brain"),
    ]
    identifiers = [
        PaperIdentifierRecord(paper_id="p-vaswani", provider="doi", external_id="10.48550/arXiv.1706.03762", is_canonical=True),
        PaperIdentifierRecord(paper_id="p-vaswani", provider="arxiv", external_id="1706.03762", is_canonical=False),
    ]
    versions = [
        PaperVersionRecord(
            id="ver-1",
            paper_id="p-vaswani",
            version_type="preprint",
            version_label="arXiv:v1",
            doi="10.48550/arXiv.1706.03762",
            release_date="2017-06-12",
        ),
        PaperVersionRecord(
            id="ver-2",
            paper_id="p-vaswani",
            version_type="conference_proceedings",
            version_label="NeurIPS 2017",
            release_date="2017-12-04",
        ),
    ]
    locations = [
        PaperLocationRecord(
            id="loc-1",
            paper_id="p-vaswani",
            location_type="repository",
            is_oa=True,
            oa_status="green",
            landing_page_url="https://arxiv.org/abs/1706.03762",
            pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
            local_pdf_path="/tmp/1706.03762.pdf",
        )
    ]

    paper = PaperRecord(
        id="p-vaswani",
        title="Attention Is All You Need",
        year=2017,
        publication_date="2017-06-12",
        citation_count=100000,
        influential_citation_count=12000,
        recent_citation_growth=15.4,
        is_retracted=False,
        authors=authors,
        identifiers=identifiers,
        versions=versions,
        locations=locations,
        abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
    )

    store.save_paper(paper, graph_id="g-full", node_role="seed")

    # Retrieve from graph
    retrieved_list = store.get_graph_papers("g-full")
    assert len(retrieved_list) == 1
    p = retrieved_list[0]

    assert p.id == "p-vaswani"
    assert p.title == "Attention Is All You Need"
    assert p.year == 2017
    assert p.publication_date == "2017-06-12"
    assert p.citation_count == 100000
    assert p.influential_citation_count == 12000
    assert p.recent_citation_growth == 15.4
    assert p.is_retracted is False
    assert p.abstract.startswith("The dominant sequence")

    # Verify authors order and properties
    assert len(p.authors) == 2
    assert p.authors[0].id == "a-1"
    assert p.authors[0].name == "Ashish Vaswani"
    assert p.authors[0].institution == "Google Brain"
    assert p.authors[1].id == "a-2"
    assert p.authors[1].name == "Noam Shazeer"

    # Verify identifiers
    assert len(p.identifiers) == 2
    doi_ident = next(i for i in p.identifiers if i.provider == "doi")
    assert doi_ident.external_id == "10.48550/arXiv.1706.03762"
    assert doi_ident.is_canonical is True

    # Verify versions
    assert len(p.versions) == 2
    v1 = next(v for v in p.versions if v.id == "ver-1")
    assert v1.version_type == "preprint"
    assert v1.version_label == "arXiv:v1"

    # Verify locations
    assert len(p.locations) == 1
    loc = p.locations[0]
    assert loc.is_oa is True
    assert loc.oa_status == "green"
    assert loc.pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"
    assert loc.local_pdf_path == "/tmp/1706.03762.pdf"

    # Also test get_paper single lookup
    single = store.get_paper("p-vaswani")
    assert single is not None
    assert single.id == "p-vaswani"
    assert single.title == p.title

    assert store.get_paper("non-existent") is None

    store.close()


def test_graph_citations_and_isolation(tmp_path: Path):
    store = LiteratureStore(tmp_path / "test_citations.db")
    store.create_or_get_graph("g-1", "Graph 1")
    store.create_or_get_graph("g-2", "Graph 2")

    p1 = PaperRecord(id="p-1", title="Paper 1", year=2010)
    p2 = PaperRecord(id="p-2", title="Paper 2", year=2015)
    p3 = PaperRecord(id="p-3", title="Paper 3", year=2020)

    store.save_paper(p1, graph_id="g-1")
    store.save_paper(p2, graph_id="g-1")
    store.save_paper(p3, graph_id="g-2")

    c12 = CitationRecord(source_paper_id="p-2", target_paper_id="p-1", is_influential=True, context="Builds on p1")
    c31 = CitationRecord(source_paper_id="p-3", target_paper_id="p-1", is_influential=False, context="Mentions p1")

    store.save_citation(c12)
    store.save_citation(c31)

    # Graph 1 contains p1 and p2, so only c12 is an internal edge of Graph 1
    cits_g1 = store.get_graph_citations("g-1")
    assert len(cits_g1) == 1
    assert cits_g1[0].source_paper_id == "p-2"
    assert cits_g1[0].target_paper_id == "p-1"
    assert cits_g1[0].is_influential is True
    assert cits_g1[0].context == "Builds on p1"

    # Graph 2 only contains p3 (p1 is in Graph 1), so no internal edges exist in Graph 2
    cits_g2 = store.get_graph_citations("g-2")
    assert len(cits_g2) == 0

    store.close()


def test_list_graphs_and_create_or_get(tmp_path: Path):
    store = LiteratureStore(tmp_path / "test_list_graphs.db")
    assert store.list_graphs() == []

    g1 = store.create_or_get_graph("slug-1", "Title 1", seed_paper_id="p-seed")
    assert g1.id == "slug-1"
    assert g1.title == "Title 1"
    assert g1.seed_paper_id == "p-seed"

    # Idempotent create_or_get_graph returns existing record
    g1_again = store.create_or_get_graph("slug-1", "Title 1")
    assert g1_again.id == "slug-1"
    assert g1_again.seed_paper_id == "p-seed"

    store.create_or_get_graph("slug-2", "Title 2")
    graphs = store.list_graphs()
    assert len(graphs) == 2
    ids = {g.id for g in graphs}
    assert ids == {"slug-1", "slug-2"}

    store.close()


def test_concurrency_busy_timeout(tmp_path: Path):
    db_path = tmp_path / "test_concurrency.db"
    store1 = LiteratureStore(db_path)
    store1.create_or_get_graph("g-conc", "Concurrency Test")

    def background_holder():
        conn = LiteratureStore(db_path)
        with conn.transaction():
            p = PaperRecord(id="p-bg", title="Background Paper")
            conn.save_paper(p, graph_id="g-conc")
            time.sleep(0.4)
        conn.close()

    t = threading.Thread(target=background_holder)
    t.start()
    time.sleep(0.1)

    # store1 writes concurrently; busy_timeout (5000ms) will wait for background thread to commit
    p_main = PaperRecord(id="p-main", title="Main Thread Paper")
    store1.save_paper(p_main, graph_id="g-conc")
    t.join()

    papers = store1.get_graph_papers("g-conc")
    paper_ids = {p.id for p in papers}
    assert paper_ids == {"p-bg", "p-main"}

    store1.close()


def test_transaction_rollback_on_error(tmp_path: Path):
    db_path = tmp_path / "test_rollback.db"
    store = LiteratureStore(db_path)
    store.create_or_get_graph("g-rb", "Rollback Graph")

    p_initial = PaperRecord(id="p-initial", title="Initial Paper")
    store.save_paper(p_initial, graph_id="g-rb")

    # Verify initial paper is saved
    assert len(store.get_graph_papers("g-rb")) == 1

    # Attempt a transaction that raises an exception halfway
    with pytest.raises(RuntimeError):
        with store.transaction():
            p_fail = PaperRecord(id="p-fail", title="Failed Paper")
            store.save_paper(p_fail, graph_id="g-rb")
            raise RuntimeError("Simulated failure inside transaction")

    # Verify p-fail was rolled back
    papers = store.get_graph_papers("g-rb")
    assert len(papers) == 1
    assert papers[0].id == "p-initial"

    store.close()


def test_store_context_manager_and_in_memory():
    with LiteratureStore(":memory:") as store:
        store.create_or_get_graph("g-mem", "In Memory")
        p = PaperRecord(id="p-mem", title="Memory Paper")
        store.save_paper(p, graph_id="g-mem")
        assert len(store.get_graph_papers("g-mem")) == 1


def test_save_paper_updates_existing_record(tmp_path: Path):
    with LiteratureStore(tmp_path / "test_update.db") as store:
        store.create_or_get_graph("g-up", "Update Graph")

        p_v1 = PaperRecord(id="p-up", title="Draft Title", citation_count=5)
        store.save_paper(p_v1, graph_id="g-up")

        p_ret1 = store.get_paper("p-up")
        assert p_ret1.title == "Draft Title"
        assert p_ret1.citation_count == 5

        # Update metadata
        p_v2 = PaperRecord(
            id="p-up",
            title="Final Published Title",
            citation_count=50,
            year=2023,
            abstract="New Abstract",
        )
        store.save_paper(p_v2, graph_id="g-up")

        p_ret2 = store.get_paper("p-up")
        assert p_ret2.title == "Final Published Title"
        assert p_ret2.citation_count == 50
        assert p_ret2.year == 2023
        assert p_ret2.abstract == "New Abstract"


def test_read_only_query_multi_statement_and_empty(tmp_path: Path):
    with LiteratureStore(tmp_path / "test_sec2.db") as store:
        # Empty query returns empty list
        assert store.execute_read_query("") == []

        # Multi-statement injection attempt is blocked
        with pytest.raises(PermissionError):
            store.execute_read_query("SELECT 1; DROP TABLE papers;")

