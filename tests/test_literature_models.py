"""
Unit tests for Core Literature Data Models (scifi.literature.models).
"""

from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    GraphSessionRecord,
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
