"""Tests for the LadybugDB Semantic Knowledge Graph and SQLite provenance integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from scifi.literature.kg import KnowledgeGraphStore, validate_readonly_cypher
from scifi.literature.kg_extractor import extract_deterministic_kg_facts, record_semantic_fact
from scifi.literature.models import (
    CitationRecord,
    EntityRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperRecord,
    SemanticEdgeRecord,
)
from scifi.literature.store import LiteratureStore


@pytest.fixture()
def stores(tmp_path: Path) -> tuple[LiteratureStore, KnowledgeGraphStore]:
    sqlite_path = tmp_path / "lit.db"
    kg_path = tmp_path / "kg.lbdb"
    store = LiteratureStore(sqlite_path)
    kg = KnowledgeGraphStore(kg_path)
    try:
        yield store, kg
    finally:
        store.close()


def _seed_paper(store: LiteratureStore, paper_id: str, title: str, year: int, is_retracted: bool = False) -> None:
    store.upsert_paper(
        PaperRecord(
            id=paper_id,
            title=title,
            year=year,
            is_retracted=is_retracted,
        )
    )


def test_entity_alias_canonicalization_prevents_fragmentation(
    stores: tuple[LiteratureStore, KnowledgeGraphStore],
) -> None:
    store, _ = stores
    e1 = EntityRecord(
        id="meth_rope",
        entity_type="Method",
        canonical_name="Rotary Position Embedding",
        aliases=["RoPE", "rotary-position-embedding"],
        category="positional_encoding",
    )
    id1 = store.upsert_entity(e1)
    assert id1 == "meth_rope"

    resolved = store.resolve_entity_by_alias("RoPE", entity_type="Method")
    assert resolved is not None
    assert resolved.id == "meth_rope"

    # Upserting under alias name merges into canonical ID
    e2 = EntityRecord(
        id="meth_rope_duplicate",
        entity_type="Method",
        canonical_name="RoPE",
        aliases=["RoPE"],
    )
    id2 = store.upsert_entity(e2)
    assert id2 == "meth_rope"
    assert len(store.list_entities("Method")) == 1


def test_provenance_invariant_rejects_missing_evidence(
    stores: tuple[LiteratureStore, KnowledgeGraphStore],
) -> None:
    store, kg = stores
    edge = SemanticEdgeRecord(
        id="edge_bad",
        source_id="m1",
        source_type="Method",
        relation_type="ASSUMES",
        target_id="a1",
        target_type="Assumption",
        evidence_id="nonexistent_ev",
    )
    with pytest.raises(ValueError, match="Provenance violation"):
        store.upsert_semantic_edge(edge)

    with pytest.raises(ValueError, match="evidence_id"):
        kg.upsert_semantic_edge(
            SemanticEdgeRecord(
                id="edge_empty",
                source_id="m1",
                source_type="Method",
                relation_type="ASSUMES",
                target_id="a1",
                target_type="Assumption",
                evidence_id="",
            )
        )


def test_multihop_assumption_trace_and_falsification(
    stores: tuple[LiteratureStore, KnowledgeGraphStore],
) -> None:
    store, kg = stores
    _seed_paper(store, "p_a", "Base Estimator Paper", 2022)
    _seed_paper(store, "p_b", "Extended Estimator Paper", 2024)
    _seed_paper(store, "p_c", "Counterexample Paper", 2025)
    store.save_citation(CitationRecord(source_paper_id="p_b", target_paper_id="p_a", is_influential=True))

    m1 = EntityRecord(id="m_base", entity_type="Method", canonical_name="BaseEstimator")
    m2 = EntityRecord(id="m_ext", entity_type="Method", canonical_name="FastEstimator")
    a1 = EntityRecord(
        id="a_iid",
        entity_type="Assumption",
        canonical_name="i.i.d. noise",
        statement="Noise samples are independent and identically distributed.",
        scope="stochastic_setting",
    )

    # p_a proposes m_base; m_base assumes a_iid; m_ext extends m_base; p_c falsifies a_iid
    record_semantic_fact(
        store,
        kg,
        paper_id="p_a",
        source_id="p_a",
        source_type="Paper",
        relation_type="PROPOSES",
        target_entity=m1,
        evidence_quote="We propose BaseEstimator in Section 2.",
    )
    record_semantic_fact(
        store,
        kg,
        paper_id="p_a",
        source_id="m_base",
        source_type="Method",
        relation_type="ASSUMES",
        target_entity=a1,
        evidence_quote="Theorem 1 assumes i.i.d. Gaussian noise.",
        source_entity=m1,
    )
    record_semantic_fact(
        store,
        kg,
        paper_id="p_b",
        source_id="m_ext",
        source_type="Method",
        relation_type="EXTENDS",
        target_entity=m1,
        evidence_quote="FastEstimator extends BaseEstimator with block-sparse updates.",
        delta_summary="Block-sparse updates",
        source_entity=m2,
    )
    record_semantic_fact(
        store,
        kg,
        paper_id="p_c",
        source_id="p_c",
        source_type="Paper",
        relation_type="FALSIFIES",
        target_entity=a1,
        evidence_quote="Under heavy-tailed correlated noise, the i.i.d. bound fails.",
        regime="correlated_noise",
    )

    # Rebuild from SQLite to verify full deterministic projection
    counts = kg.rebuild_from_sqlite(store)
    assert counts["papers"] == 3
    assert counts["citations"] == 1
    assert counts["entities"] == 3
    assert counts["semantic_edges"] == 4

    trace = kg.trace_assumptions("FastEstimator", max_hops=3)
    assert trace["has_falsified_assumptions"] is True
    assert any(a["assumption_id"] == "a_iid" for a in trace["assumptions"])
    assert any(f["falsifier_id"] == "p_c" and f["regime"] == "correlated_noise" for f in trace["falsifications"])

    contradictions = kg.find_contradictions(paper_id="p_c")
    assert len(contradictions) == 1
    assert contradictions[0]["kind"] == "FALSIFIES"

    uncredited = kg.find_uncredited_method("BaseEstimator")
    assert len(uncredited) == 1
    assert uncredited[0]["paper_id"] == "p_a"


def test_delta_novelty_and_gaps(
    stores: tuple[LiteratureStore, KnowledgeGraphStore],
) -> None:
    store, kg = stores
    _seed_paper(store, "p_1", "Prior Work", 2023)
    _seed_paper(store, "p_2", "Our Work", 2026)

    ev = EvidenceRecord(
        id="ev_gap_1",
        paper_id="p_1",
        evidence_type="limitation",
        extracted_text="Quadratic O(N^2) memory bottleneck.",
        extraction_method="manual",
    )
    store.save_evidence(ev)
    store.save_paper_gap(
        PaperGapRecord(
            id="gap_1",
            paper_id="p_1",
            gap_type="scalability",
            claim_summary="Quadratic memory bottleneck",
            primary_evidence_id="ev_gap_1",
        )
    )

    m_old = EntityRecord(id="m_old", entity_type="Method", canonical_name="DenseAttn")
    m_new = EntityRecord(id="m_new", entity_type="Method", canonical_name="LinearAttn")
    a_quad = EntityRecord(id="a_quad", entity_type="Assumption", canonical_name="Short sequence")

    record_semantic_fact(
        store,
        kg,
        paper_id="p_1",
        source_id="m_old",
        source_type="Method",
        relation_type="ASSUMES",
        target_entity=a_quad,
        evidence_quote="Requires short sequences.",
        source_entity=m_old,
    )
    record_semantic_fact(
        store,
        kg,
        paper_id="p_2",
        source_id="m_new",
        source_type="Method",
        relation_type="EXTENDS",
        target_entity=m_old,
        evidence_quote="Replaces softmax kernel.",
        delta_summary="O(N) linear kernel",
        source_entity=m_new,
    )
    # Link ADDRESSES gap via SQLite
    store.upsert_semantic_edge(
        SemanticEdgeRecord(
            id="edge_addr_1",
            source_id="m_new",
            source_type="Method",
            relation_type="ADDRESSES",
            target_id="gap_1",
            target_type="Gap",
            evidence_id="ev_gap_1",
        )
    )

    kg.rebuild_from_sqlite(store)
    delta = kg.delta_novelty("LinearAttn", peer_method_ids=["m_old"])
    assert delta["status"] == "OK"
    assert len(delta["gaps_addressed"]) == 1
    assert delta["peer_comparisons"][0]["assumptions_removed_by_target"][0]["id"] == "a_quad"


def test_readonly_cypher_guard(
    stores: tuple[LiteratureStore, KnowledgeGraphStore],
) -> None:
    store, kg = stores
    _seed_paper(store, "p_ro", "ReadOnly Paper", 2025)
    kg.rebuild_from_sqlite(store)

    for forbidden in (
        "CREATE (p:Paper {id: 'x'})",
        "MATCH (p:Paper) DETACH DELETE p",
        "MATCH (p:Paper) SET p.title = 'hacked'",
        "MERGE (p:Paper {id: 'x'})",
        "DROP TABLE Paper",
        "COPY Paper TO 'out.csv'",
    ):
        with pytest.raises(PermissionError):
            validate_readonly_cypher(forbidden)
        with pytest.raises(PermissionError):
            kg.execute_read_query(forbidden)

    # String literals containing forbidden words should still be permitted
    rows = kg.execute_read_query("MATCH (p:Paper) WHERE p.title <> 'DELETE' RETURN p.id AS id, p.title AS title")
    assert len(rows) == 1
    assert rows[0]["id"] == "p_ro"


def test_deterministic_latex_extraction(
    stores: tuple[LiteratureStore, KnowledgeGraphStore],
) -> None:
    store, kg = stores
    _seed_paper(store, "p_tex", "LaTeX Extraction Paper", 2026)
    kg.rebuild_from_sqlite(store)

    tex = r"""
    We apply rotary position embedding for long-context attention.
    \begin{theorem}
    The estimator converges at rate $O(1/\sqrt{N})$ under bounded variance.
    \end{theorem}
    \begin{assumption}
    The gradient covariance matrix is uniformly bounded.
    \end{assumption}
    """
    summary = extract_deterministic_kg_facts(store, kg, paper_id="p_tex", text=tex, section="Method")
    assert summary["methods_recorded"] >= 1
    assert summary["claims_recorded"] == 1
    assert summary["assumptions_recorded"] == 1
    st = kg.stats()
    assert st["nodes"]["Method"] >= 1
    assert st["nodes"]["Claim"] == 1
    assert st["nodes"]["Assumption"] == 1


def test_mcp_kg_tools_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import scifi.server as srv

    lit_db = tmp_path / "mcp_lit.db"
    kg_db = tmp_path / "mcp_kg.lbdb"
    store = LiteratureStore(lit_db)
    kg = KnowledgeGraphStore(kg_db)

    monkeypatch.setattr(srv, "get_literature_store", lambda db_path=None: store)
    monkeypatch.setattr(srv, "get_knowledge_graph", lambda kg_path=None: kg)

    try:
        _seed_paper(store, "p_mcp", "MCP Graph Paper", 2026)
        rebuilt = srv.scifi_kg_rebuild()
        assert rebuilt["status"] == "SUCCESS"
        assert rebuilt["counts"]["papers"] == 1

        fact = srv.scifi_kg_upsert_fact(
            paper_id="p_mcp",
            source_id="p_mcp",
            source_type="Paper",
            relation_type="PROPOSES",
            target_name="GraphAudit",
            target_type="Method",
            evidence_quote="We introduce GraphAudit in Section 3.",
        )
        assert fact["status"] == "SUCCESS"

        status = srv.scifi_kg_status()
        assert status["nodes"]["Paper"] == 1
        assert status["nodes"]["Method"] == 1

        q_rows = srv.scifi_kg_query(
            "MATCH (p:Paper)-[:PROPOSES]->(m:Method) RETURN p.id AS pid, m.canonical_name AS meth"
        )
        assert q_rows == [{"pid": "p_mcp", "meth": "GraphAudit"}]
    finally:
        store.close()
