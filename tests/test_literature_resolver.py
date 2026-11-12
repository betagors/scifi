"""
Unit tests for Canonical Paper Resolver & Registry Client (scifi.literature.resolver).
"""

from unittest.mock import MagicMock, patch

import requests

from scifi.cache import RegistryCache
from scifi.literature.models import PaperRecord
from scifi.literature.resolver import PaperResolver, clean_arxiv_id, clean_doi, reconstruct_abstract


class TestAbstractReconstruction:
    def test_reconstruct_abstract_basic(self):
        inverted = {
            "We": [0],
            "propose": [1],
            "a": [2, 6],
            "novel": [3],
            "method": [4],
            "and": [5],
            "architecture.": [7],
        }
        text = reconstruct_abstract(inverted)
        assert text == "We propose a novel method and a architecture."

    def test_reconstruct_abstract_none_or_empty(self):
        assert reconstruct_abstract(None) is None
        assert reconstruct_abstract({}) is None
        assert reconstruct_abstract("not a dict") is None

    def test_reconstruct_abstract_sparse_and_disordered(self):
        inverted = {
            "world!": [5],
            "Hello": [0],
        }
        text = reconstruct_abstract(inverted)
        assert text == "Hello world!"


class TestIdentifierCleaning:
    def test_clean_doi_variations(self):
        assert clean_doi("10.1038/s41586-020-2649-2") == "10.1038/s41586-020-2649-2"
        assert clean_doi("https://doi.org/10.1038/s41586-020-2649-2") == "10.1038/s41586-020-2649-2"
        assert clean_doi("http://dx.doi.org/10.1038/s41586-020-2649-2.") == "10.1038/s41586-020-2649-2"
        assert clean_doi("doi:10.1038/s41586-020-2649-2;") == "10.1038/s41586-020-2649-2"

    def test_clean_arxiv_id_variations(self):
        assert clean_arxiv_id("1706.03762") == "1706.03762"
        assert clean_arxiv_id("arxiv:1706.03762v5") == "1706.03762v5"
        assert clean_arxiv_id("https://arxiv.org/abs/1706.03762") == "1706.03762"
        assert clean_arxiv_id("https://arxiv.org/pdf/1706.03762v2.pdf") == "1706.03762v2"


class TestPaperResolver:
    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_by_title_openalex_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W2741809807",
                    "doi": "https://doi.org/10.48550/arxiv.1706.03762",
                    "title": "Attention Is All You Need",
                    "publication_year": 2017,
                    "publication_date": "2017-06-12",
                    "cited_by_count": 95000,
                    "authorships": [
                        {
                            "author": {
                                "id": "https://openalex.org/A1",
                                "display_name": "Ashish Vaswani",
                                "orcid": "https://orcid.org/0000-0001-2345-6789",
                            },
                            "institutions": [{"display_name": "Google Brain"}],
                        }
                    ],
                    "open_access": {
                        "is_oa": True,
                        "oa_status": "green",
                        "oa_url": "https://arxiv.org/pdf/1706.03762",
                    },
                    "abstract_inverted_index": {
                        "The": [0],
                        "dominant": [1],
                        "sequence": [2],
                        "transduction": [3],
                        "models": [4],
                    },
                }
            ]
        }
        mock_get.return_value = mock_resp

        resolver = PaperResolver(email="researcher@test.org")
        paper = resolver.resolve_by_title("Attention Is All You Need")

        assert paper is not None
        assert isinstance(paper, PaperRecord)
        assert paper.id == "W2741809807"
        assert paper.title == "Attention Is All You Need"
        assert paper.year == 2017
        assert paper.publication_date == "2017-06-12"
        assert paper.citation_count == 95000
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "Ashish Vaswani"
        assert paper.authors[0].orcid == "https://orcid.org/0000-0001-2345-6789"
        assert paper.authors[0].institution == "Google Brain"
        assert paper.locations[0].oa_status == "green"
        assert paper.locations[0].is_oa is True
        assert paper.abstract == "The dominant sequence transduction models"

        # Check polite pool user agent was passed
        mock_get.assert_called_once()
        headers = mock_get.call_args[1].get("headers", {})
        assert "mailto:researcher@test.org" in headers.get("User-Agent", "")

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_by_title_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        resolver = PaperResolver()
        paper = resolver.resolve_by_title("Non Existent Paper Title 12345")
        assert paper is None

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_by_doi_openalex_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "id": "https://openalex.org/W2963403869",
            "doi": "https://doi.org/10.1038/s41586-020-2649-2",
            "title": "Highly accurate protein structure prediction with AlphaFold",
            "publication_year": 2021,
            "publication_date": "2021-07-15",
            "cited_by_count": 22000,
            "is_retracted": False,
            "authorships": [
                {
                    "author": {"id": "https://openalex.org/A2", "display_name": "John Jumper"},
                    "institutions": [{"display_name": "DeepMind"}],
                }
            ],
            "locations": [
                {
                    "source": {"type": "journal"},
                    "is_oa": True,
                    "oa_status": "gold",
                    "landing_page_url": "https://doi.org/10.1038/s41586-020-2649-2",
                    "pdf_url": "https://www.nature.com/articles/s41586-020-2649-2.pdf",
                }
            ],
        }
        mock_get.return_value = mock_resp

        resolver = PaperResolver()
        paper = resolver.resolve_by_doi("https://doi.org/10.1038/s41586-020-2649-2")

        assert paper is not None
        assert paper.id == "W2963403869"
        assert paper.title == "Highly accurate protein structure prediction with AlphaFold"
        assert paper.year == 2021
        assert paper.citation_count == 22000
        assert len(paper.identifiers) >= 2
        # Verify both DOI and OpenAlex identifiers are present
        providers = {i.provider: i.external_id for i in paper.identifiers}
        assert providers["openalex"] == "W2963403869"
        assert providers["doi"] == "10.1038/s41586-020-2649-2"
        assert paper.locations[0].oa_status == "gold"
        assert paper.locations[0].location_type == "publisher"

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_by_doi_not_found(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        resolver = PaperResolver()
        paper = resolver.resolve_by_doi("10.9999/nonexistent.doi")
        assert paper is None

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_by_arxiv_id_openalex_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W2741809807",
                    "doi": "https://doi.org/10.48550/arxiv.1706.03762",
                    "title": "Attention Is All You Need",
                    "publication_year": 2017,
                    "ids": {"arxiv": "https://arxiv.org/abs/1706.03762"},
                    "authorships": [{"author": {"display_name": "Ashish Vaswani"}}],
                    "open_access": {"is_oa": True, "oa_status": "green"},
                }
            ]
        }
        mock_get.return_value = mock_resp

        resolver = PaperResolver()
        paper = resolver.resolve_by_arxiv_id("arxiv:1706.03762")

        assert paper is not None
        assert paper.id == "W2741809807"
        assert paper.title == "Attention Is All You Need"
        providers = {i.provider: i.external_id for i in paper.identifiers}
        assert "arxiv" in providers
        assert providers["arxiv"] == "1706.03762"

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_by_arxiv_id_fallback_arxiv_api(self, mock_get):
        # OpenAlex returns 404, fallback to arXiv XML API
        openalex_404 = MagicMock()
        openalex_404.status_code = 404

        arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>http://arxiv.org/abs/2301.12345v1</id>
            <title>Quantum Advantage in Machine Learning</title>
            <summary>We show quantum advantage in learning tasks.</summary>
            <published>2023-01-28T12:00:00Z</published>
            <author>
              <name>Alice Quantum</name>
            </author>
          </entry>
        </feed>"""
        arxiv_resp = MagicMock()
        arxiv_resp.status_code = 200
        arxiv_resp.text = arxiv_xml

        def side_effect(url, **kwargs):
            if "api.openalex.org" in url:
                return openalex_404
            elif "export.arxiv.org" in url:
                return arxiv_resp
            return MagicMock(status_code=404)

        mock_get.side_effect = side_effect

        resolver = PaperResolver()
        paper = resolver.resolve_by_arxiv_id("2301.12345")

        assert paper is not None
        assert paper.title == "Quantum Advantage in Machine Learning"
        assert paper.year == 2023
        assert paper.authors[0].name == "Alice Quantum"
        assert paper.abstract == "We show quantum advantage in learning tasks."
        assert paper.locations[0].oa_status == "green"
        assert paper.locations[0].pdf_url == "https://arxiv.org/pdf/2301.12345.pdf"

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_references_success(self, mock_get):
        # 1. Fetch seed work
        work_resp = MagicMock()
        work_resp.status_code = 200
        work_resp.json.return_value = {
            "id": "https://openalex.org/W2741809807",
            "referenced_works": [
                "https://openalex.org/W1000000001",
                "https://openalex.org/W1000000002",
            ],
        }

        # 2. Batch fetch referenced works
        batch_resp = MagicMock()
        batch_resp.status_code = 200
        batch_resp.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W1000000001",
                    "title": "Neural Machine Translation by Jointly Learning to Align and Translate",
                    "publication_year": 2014,
                    "cited_by_count": 30000,
                },
                {
                    "id": "https://openalex.org/W1000000002",
                    "title": "Sequence to Sequence Learning with Neural Networks",
                    "publication_year": 2014,
                    "cited_by_count": 25000,
                },
            ]
        }

        def side_effect(url, **kwargs):
            if url.endswith("W2741809807"):
                return work_resp
            elif "filter=" in url or kwargs.get("params", {}).get("filter"):
                return batch_resp
            return MagicMock(status_code=404)

        mock_get.side_effect = side_effect

        resolver = PaperResolver()
        refs = resolver.resolve_references("W2741809807", limit=10)

        assert len(refs) == 2
        assert refs[0].id == "W1000000001"
        assert refs[0].title == "Neural Machine Translation by Jointly Learning to Align and Translate"
        assert refs[1].id == "W1000000002"

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_references_empty(self, mock_get):
        work_resp = MagicMock()
        work_resp.status_code = 200
        work_resp.json.return_value = {
            "id": "https://openalex.org/W2741809807",
            "referenced_works": [],
        }
        mock_get.return_value = work_resp

        resolver = PaperResolver()
        refs = resolver.resolve_references("W2741809807", limit=10)
        assert refs == []

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_citations_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W2963403869",
                    "title": "BERT: Pre-training of Deep Bidirectional Transformers",
                    "publication_year": 2018,
                    "cited_by_count": 80000,
                },
                {
                    "id": "https://openalex.org/W3000000001",
                    "title": "Language Models are Few-Shot Learners",
                    "publication_year": 2020,
                    "cited_by_count": 45000,
                },
            ]
        }
        mock_get.return_value = mock_resp

        resolver = PaperResolver()
        citations = resolver.resolve_citations("W2741809807", limit=5)

        assert len(citations) == 2
        assert citations[0].id == "W2963403869"
        assert citations[0].title == "BERT: Pre-training of Deep Bidirectional Transformers"
        assert citations[1].id == "W3000000001"

    @patch("scifi.literature.resolver.requests.get")
    def test_resolve_citations_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        resolver = PaperResolver()
        citations = resolver.resolve_citations("W2741809807", limit=5)
        assert citations == []

    @patch("scifi.literature.resolver.requests.get")
    def test_error_resilience_timeouts_and_exceptions(self, mock_get):
        mock_get.side_effect = requests.Timeout("Network timeout connecting to OpenAlex")

        resolver = PaperResolver()
        assert resolver.resolve_by_title("Any Title") is None
        assert resolver.resolve_by_doi("10.1000/182") is None
        assert resolver.resolve_by_arxiv_id("1706.03762") is None
        assert resolver.resolve_references("W12345") == []
        assert resolver.resolve_citations("W12345") == []

    @patch("scifi.literature.resolver.requests.get")
    def test_cache_integration(self, mock_get, tmp_path):
        db_path = tmp_path / "resolver_cache.db"
        cache = RegistryCache(db_path)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W2741809807",
                    "title": "Attention Is All You Need",
                    "publication_year": 2017,
                }
            ]
        }
        mock_get.return_value = mock_resp

        resolver = PaperResolver(cache=cache)
        # First call hits mock_get
        p1 = resolver.resolve_by_title("Attention Is All You Need")
        assert p1 is not None
        assert mock_get.call_count == 1

        # Second identical call should hit cache and NOT invoke requests.get again
        p2 = resolver.resolve_by_title("Attention Is All You Need")
        assert p2 is not None
        assert p2.id == p1.id
        assert mock_get.call_count == 1

    @patch("scifi.literature.resolver.get_session")
    def test_routes_through_resilient_session(self, mock_get_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": "https://openalex.org/W99999",
                    "title": "Resilient Session Test",
                    "publication_year": 2024,
                }
            ]
        }
        mock_get_session.return_value.get.return_value = mock_resp

        resolver = PaperResolver()
        p = resolver.resolve_by_title("Resilient Session Test")

        assert p is not None
        assert p.title == "Resilient Session Test"
        assert mock_get_session.return_value.get.called
        args, kwargs = mock_get_session.return_value.get.call_args
        assert "api.openalex.org" in args[0]
