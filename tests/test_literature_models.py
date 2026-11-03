"""
Unit tests for Core Literature Data Models (scifi.literature.models).
"""

from scifi.literature.models import (
    AuthorRecord,
    CitationContextRecord,
    CitationRecord,
    EvidenceRecord,
    GraphSessionRecord,
    PaperGapRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
    PaperVersionRecord,
)


def test_paper_record_defaults_and_citekey():
    author = AuthorRecord(id="A1", name="Ashish Vaswani")
    paper = PaperRecord(
        id="p-1234",
        title="Attention Is All You Need",
        year=2017,
        publication_date="2017-06-12",
        authors=[author],
    )
    assert paper.id == "p-1234"
    assert paper.year == 2017
    assert paper.generate_cite_key() == "Vaswani2017Attention"
    assert paper.recent_citation_growth == 0.0
    assert paper.citation_count == 0
    assert paper.influential_citation_count == 0
    assert paper.is_retracted is False
    assert paper.abstract is None
    assert paper.identifiers == []
    assert paper.versions == []
    assert paper.locations == []


def test_paper_location_access_tiers():
    loc = PaperLocationRecord(
        id="loc-1",
        paper_id="p-1234",
        location_type="repository",
        is_oa=True,
        oa_status="green",
        pdf_url="https://arxiv.org/pdf/1706.03762.pdf",
    )
    assert loc.is_oa is True
    assert loc.oa_status == "green"
    assert loc.pdf_url == "https://arxiv.org/pdf/1706.03762.pdf"
    assert loc.landing_page_url is None
    assert loc.local_pdf_path is None


def test_cite_key_variations_and_fallbacks():
    # Missing author defaults to Unknown
    paper_no_author = PaperRecord(id="p-1", title="Title", year=2024)
    assert paper_no_author.generate_cite_key() == "Unknown2024Title"

    # Missing author and missing year
    paper_no_author_no_year = PaperRecord(id="p-2", title="Title")
    assert paper_no_author_no_year.generate_cite_key() == "UnknownUnknownTitle"

    # Author with comma format (Lastname, Firstname)
    paper_comma = PaperRecord(
        id="p-3",
        title="Attention",
        year=2017,
        authors=[AuthorRecord(id="a", name="Vaswani, Ashish")],
    )
    assert paper_comma.generate_cite_key() == "Vaswani2017Attention"

    # Title starting with stop words
    paper_stop_words = PaperRecord(
        id="p-4",
        title="On the Convergence of SGD",
        year=2021,
        authors=[AuthorRecord(id="a", name="John Smith")],
    )
    assert paper_stop_words.generate_cite_key() == "Smith2021Convergence"

    # Author mixed case preservation
    paper_mixed_case = PaperRecord(
        id="p-5",
        title="Gradient-Based Learning Applied to Document Recognition",
        year=1998,
        authors=[AuthorRecord(id="a", name="Yann LeCun")],
    )
    assert paper_mixed_case.generate_cite_key() == "LeCun1998Gradient"

    # Year fallback from publication_date
    paper_date_fallback = PaperRecord(
        id="p-6",
        title="Deep Residual Learning",
        publication_date="2016-12-10",
        authors=[AuthorRecord(id="a", name="Kaiming He")],
    )
    assert paper_date_fallback.generate_cite_key() == "He2016Deep"

    # Empty title fallback
    paper_empty_title = PaperRecord(id="p-7", title="", year=2020)
    assert paper_empty_title.generate_cite_key() == "Unknown2020Title"


def test_citation_record_and_graph_session():
    citation = CitationRecord(
        source_paper_id="p-1",
        target_paper_id="p-2",
        is_influential=True,
        context="Building directly upon the self-attention architecture...",
    )
    assert citation.source_paper_id == "p-1"
    assert citation.target_paper_id == "p-2"
    assert citation.is_influential is True
    assert "self-attention" in citation.context

    session = GraphSessionRecord(
        id="graph-1",
        title="Transformer Lineage",
        seed_paper_id="p-1",
        created_at="2026-11-03T10:00:00Z",
    )
    assert session.id == "graph-1"
    assert session.title == "Transformer Lineage"
    assert session.seed_paper_id == "p-1"


def test_paper_identifier_and_version_records():
    ident = PaperIdentifierRecord(
        paper_id="p-1",
        provider="openalex",
        external_id="W12345",
        is_canonical=True,
    )
    assert ident.paper_id == "p-1"
    assert ident.provider == "openalex"
    assert ident.is_canonical is True

    ver = PaperVersionRecord(
        id="v-1",
        paper_id="p-1",
        version_type="preprint",
        version_label="arXiv:v1",
        doi="10.48550/arxiv.1706.03762",
        release_date="2017-06-12",
    )
    assert ver.version_type == "preprint"
    assert ver.version_label == "arXiv:v1"
    assert ver.doi == "10.48550/arxiv.1706.03762"


def test_serialization_roundtrip():
    author = AuthorRecord(id="a1", name="Ashish Vaswani", orcid="0000-0001-2345-6789")
    ident = PaperIdentifierRecord(paper_id="p-1", provider="doi", external_id="10.1234/test", is_canonical=True)
    ver = PaperVersionRecord(id="v-1", paper_id="p-1", version_type="conference_proceedings")
    loc = PaperLocationRecord(id="l-1", paper_id="p-1", location_type="repository", is_oa=True, oa_status="green")

    paper = PaperRecord(
        id="p-1",
        title="Attention Is All You Need",
        year=2017,
        publication_date="2017-06-12",
        citation_count=90000,
        influential_citation_count=12000,
        recent_citation_growth=0.15,
        is_retracted=False,
        authors=[author],
        identifiers=[ident],
        versions=[ver],
        locations=[loc],
        abstract="The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...",
    )

    d = paper.to_dict()
    assert d["id"] == "p-1"
    assert d["authors"][0]["name"] == "Ashish Vaswani"
    assert d["identifiers"][0]["provider"] == "doi"

    # Deserialization from dictionary
    restored = PaperRecord.from_dict(d)
    assert restored.id == paper.id
    assert restored.title == paper.title
    assert restored.year == paper.year
    assert len(restored.authors) == 1
    assert restored.authors[0].orcid == "0000-0001-2345-6789"
    assert len(restored.identifiers) == 1
    assert restored.identifiers[0].is_canonical is True
    assert len(restored.versions) == 1
    assert len(restored.locations) == 1
    assert restored.locations[0].oa_status == "green"

    # Deserialization with extraneous keys should be ignored safely
    d_extra = d.copy()
    d_extra["unexpected_column"] = "ignored_value"
    d_extra["topological_depth"] = 2
    restored_extra = PaperRecord.from_dict(d_extra)
    assert restored_extra.id == "p-1"


def test_evidence_and_gap_records():
    # 1. CitationContextRecord
    ctx = CitationContextRecord(
        id="ctx-1",
        source_paper_id="p-100",
        target_paper_id="p-200",
        context_text="Vaswani et al. (2017) demonstrated that attention alone is sufficient.",
        section_name="Related Work",
        intent="methodology",
        is_influential=True,
    )
    assert ctx.id == "ctx-1"
    assert ctx.source_paper_id == "p-100"
    assert ctx.target_paper_id == "p-200"
    assert ctx.context_text == "Vaswani et al. (2017) demonstrated that attention alone is sufficient."
    assert ctx.section_name == "Related Work"
    assert ctx.intent == "methodology"
    assert ctx.is_influential is True

    # Defaults check
    ctx_default = CitationContextRecord(
        id="ctx-2",
        source_paper_id="p-100",
        target_paper_id="p-200",
        context_text="Some text",
    )
    assert ctx_default.section_name is None
    assert ctx_default.intent is None
    assert ctx_default.is_influential is False

    # to_dict / from_dict roundtrip
    ctx_dict = ctx.to_dict()
    assert ctx_dict["id"] == "ctx-1"
    assert ctx_dict["is_influential"] is True
    ctx_dict["extra_key"] = "extra"
    restored_ctx = CitationContextRecord.from_dict(ctx_dict)
    assert restored_ctx.id == ctx.id
    assert restored_ctx.context_text == ctx.context_text
    assert not hasattr(restored_ctx, "extra_key")

    # 2. EvidenceRecord
    ev = EvidenceRecord(
        id="ev-1",
        paper_id="p-200",
        reporting_paper_id="p-100",
        evidence_type="citation_context",
        source_section="Introduction",
        source_location="para 2",
        extracted_text="Quadratic self-attention complexity hinders scaling to long contexts.",
        extraction_method="semantic_scholar_api",
        confidence=0.88,
        retrieved_at="2026-11-03T12:00:00Z",
    )
    assert ev.id == "ev-1"
    assert ev.paper_id == "p-200"
    assert ev.reporting_paper_id == "p-100"
    assert ev.evidence_type == "citation_context"
    assert ev.source_section == "Introduction"
    assert ev.source_location == "para 2"
    assert ev.extracted_text == "Quadratic self-attention complexity hinders scaling to long contexts."
    assert ev.extraction_method == "semantic_scholar_api"
    assert ev.confidence == 0.88
    assert ev.retrieved_at == "2026-11-03T12:00:00Z"

    # Nullable confidence & optional field defaults
    ev_defaults = EvidenceRecord(
        id="ev-2",
        paper_id="p-200",
        evidence_type="full_text_section",
        extracted_text="Memory footprint is O(N^2).",
        extraction_method="pdf_text_parser",
    )
    assert ev_defaults.reporting_paper_id is None
    assert ev_defaults.source_section is None
    assert ev_defaults.source_location is None
    assert ev_defaults.confidence is None
    assert ev_defaults.retrieved_at is None

    # to_dict / from_dict roundtrip
    ev_dict = ev.to_dict()
    assert ev_dict["confidence"] == 0.88
    ev_dict["unexpected"] = 42
    restored_ev = EvidenceRecord.from_dict(ev_dict)
    assert restored_ev.id == ev.id
    assert restored_ev.confidence == 0.88
    assert not hasattr(restored_ev, "unexpected")

    # 3. PaperGapRecord
    gap = PaperGapRecord(
        id="gap-1",
        paper_id="p-200",
        gap_type="computational_complexity",
        claim_summary="Quadratic O(N^2) memory complexity in self-attention mechanisms",
        primary_evidence_id="ev-1",
        verification_status="corroborated",
        corroborating_count=3,
        contradicting_count=0,
    )
    assert gap.id == "gap-1"
    assert gap.paper_id == "p-200"
    assert gap.gap_type == "computational_complexity"
    assert gap.claim_summary == "Quadratic O(N^2) memory complexity in self-attention mechanisms"
    assert gap.primary_evidence_id == "ev-1"
    assert gap.verification_status == "corroborated"
    assert gap.corroborating_count == 3
    assert gap.contradicting_count == 0

    # Defaults check
    gap_default = PaperGapRecord(
        id="gap-2",
        paper_id="p-200",
        gap_type="unstated_assumption",
        claim_summary="Assumes infinite memory bandwidth",
        primary_evidence_id="ev-2",
    )
    assert gap_default.verification_status == "candidate"
    assert gap_default.corroborating_count == 0
    assert gap_default.contradicting_count == 0

    # verification_status values ('candidate', 'corroborated', 'disputed')
    gap_disputed = PaperGapRecord(
        id="gap-3",
        paper_id="p-200",
        gap_type="empirical_limitation",
        claim_summary="Fails on sequence lengths > 8k tokens",
        primary_evidence_id="ev-2",
        verification_status="disputed",
    )
    assert gap_disputed.verification_status == "disputed"

    # to_dict / from_dict roundtrip
    gap_dict = gap.to_dict()
    assert gap_dict["gap_type"] == "computational_complexity"
    assert gap_dict["verification_status"] == "corroborated"
    gap_dict["unknown_field"] = "val"
    restored_gap = PaperGapRecord.from_dict(gap_dict)
    assert restored_gap.id == gap.id
    assert restored_gap.claim_summary == gap.claim_summary
    assert not hasattr(restored_gap, "unknown_field")
