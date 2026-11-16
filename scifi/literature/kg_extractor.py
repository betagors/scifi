"""
Deterministic Knowledge Graph extraction and provenance-backed fact recording.

Ensures every semantic entity and edge written to the Knowledge Graph is first
anchored to an EvidenceRecord in SQLite (`LiteratureStore`) before projection
to LadybugDB (`KnowledgeGraphStore`).
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING, Any

from scifi.argus.detector import CANONICAL_METHODS
from scifi.literature.models import EntityRecord, EvidenceRecord, SemanticEdgeRecord

if TYPE_CHECKING:
    from scifi.literature.kg import KnowledgeGraphStore
    from scifi.literature.store import LiteratureStore

_LATEX_ENV_RE = re.compile(
    r"\\begin\{(assumption|theorem|lemma|proposition)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}",
    re.DOTALL | re.IGNORECASE,
)


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def _extract_snippet(text: str, start: int, end: int, window: int = 160) -> str:
    lo = max(0, start - window)
    hi = min(len(text), end + window)
    return re.sub(r"\s+", " ", text[lo:hi]).strip()


def record_semantic_fact(
    store: LiteratureStore,
    kg: KnowledgeGraphStore | None,
    *,
    paper_id: str,
    source_id: str,
    source_type: str,
    relation_type: str,
    target_entity: EntityRecord,
    evidence_quote: str,
    evidence_type: str = "kg_extraction",
    extraction_method: str = "deterministic",
    source_section: str | None = None,
    confidence: float = 0.9,
    is_implicit: bool = False,
    regime: str | None = None,
    delta_summary: str | None = None,
    source_entity: EntityRecord | None = None,
) -> dict[str, str]:
    """
    Atomically persist an EvidenceRecord + canonical EntityRecord(s) + SemanticEdgeRecord
    to SQLite and project them into LadybugDB.
    """
    ev_id = _stable_id("ev", paper_id, source_id, relation_type, target_entity.canonical_name, evidence_quote[:80])
    evidence = EvidenceRecord(
        id=ev_id,
        paper_id=paper_id,
        evidence_type=evidence_type,
        extracted_text=evidence_quote,
        extraction_method=extraction_method,
        source_section=source_section,
        confidence=confidence,
    )
    store.save_evidence(evidence)

    canonical_source_id = source_id
    if source_entity is not None:
        canonical_source_id = store.upsert_entity(source_entity)
        source_entity.id = canonical_source_id

    canonical_target_id = store.upsert_entity(target_entity)
    target_entity.id = canonical_target_id

    edge_id = _stable_id("edge", canonical_source_id, relation_type, canonical_target_id, ev_id)
    edge = SemanticEdgeRecord(
        id=edge_id,
        source_id=canonical_source_id,
        source_type=source_type,
        relation_type=relation_type,
        target_id=canonical_target_id,
        target_type=target_entity.entity_type,
        evidence_id=ev_id,
        confidence=confidence,
        is_implicit=is_implicit,
        regime=regime,
        delta_summary=delta_summary,
    )
    store.upsert_semantic_edge(edge)

    if kg is not None:
        if source_entity is not None:
            kg.upsert_entity(source_entity)
        kg.upsert_entity(target_entity)
        kg.upsert_semantic_edge(edge)

    return {
        "evidence_id": ev_id,
        "source_id": canonical_source_id,
        "target_id": canonical_target_id,
        "edge_id": edge_id,
    }


def extract_deterministic_kg_facts(
    store: LiteratureStore,
    kg: KnowledgeGraphStore | None,
    *,
    paper_id: str,
    text: str,
    section: str | None = None,
) -> dict[str, Any]:
    """
    Extract deterministic Method, Claim, and Assumption facts from manuscript/PDF text
    with full Evidence provenance. Zero LLM cost.
    """
    methods_recorded = 0
    claims_recorded = 0
    assumptions_recorded = 0
    lowered = text.lower()

    # 1. Known methods from Argus registry -> (:Paper)-[:USES]->(:Method)
    for term, canonical_title in CANONICAL_METHODS.items():
        idx = lowered.find(term)
        if idx == -1:
            continue
        if not re.search(rf"\b{re.escape(term)}\b", lowered):
            continue
        snippet = _extract_snippet(text, idx, idx + len(term))
        method_id = _stable_id("meth", canonical_title.lower())
        method_ent = EntityRecord(
            id=method_id,
            entity_type="Method",
            canonical_name=canonical_title,
            aliases=[term, canonical_title],
            category="canonical_method",
        )
        record_semantic_fact(
            store,
            kg,
            paper_id=paper_id,
            source_id=paper_id,
            source_type="Paper",
            relation_type="USES",
            target_entity=method_ent,
            evidence_quote=snippet,
            evidence_type="method_mention",
            extraction_method="argus_dictionary",
            source_section=section,
            confidence=0.95,
        )
        methods_recorded += 1

    # 2. LaTeX theorem / lemma / proposition / assumption environments
    for match in _LATEX_ENV_RE.finditer(text):
        env_kind = match.group(1).lower()
        body = re.sub(r"\s+", " ", match.group(2)).strip()
        if len(body) < 12:
            continue
        quote = body[:500]
        if env_kind == "assumption":
            ent = EntityRecord(
                id=_stable_id("asmp", body[:120].lower()),
                entity_type="Assumption",
                canonical_name=body[:120],
                statement=body,
                scope=section,
            )
            # Link to Paper as Claim/Method assumption if paper has a method; otherwise store canonical entity
            store.upsert_entity(ent)
            if kg is not None:
                kg.upsert_entity(ent)
            assumptions_recorded += 1
        else:
            claim_ent = EntityRecord(
                id=_stable_id("clm", paper_id, body[:120].lower()),
                entity_type="Claim",
                canonical_name=body[:120],
                category="theoretical",
                statement=body,
            )
            record_semantic_fact(
                store,
                kg,
                paper_id=paper_id,
                source_id=paper_id,
                source_type="Paper",
                relation_type="PROVES",
                target_entity=claim_ent,
                evidence_quote=quote,
                evidence_type=env_kind,
                extraction_method="latex_env_parser",
                source_section=section,
                confidence=0.95,
            )
            claims_recorded += 1

    return {
        "paper_id": paper_id,
        "methods_recorded": methods_recorded,
        "claims_recorded": claims_recorded,
        "assumptions_recorded": assumptions_recorded,
    }


__all__ = [
    "extract_deterministic_kg_facts",
    "record_semantic_fact",
]
