"""
Unit tests for Semantic Scholar Citation Context Client (scifi.literature.semantic_scholar).
"""

from unittest.mock import MagicMock, patch

import requests

from scifi.literature.models import CitationContextRecord
from scifi.literature.semantic_scholar import SemanticScholarClient, format_paper_id


class TestFormatPaperId:
    def test_format_doi_plain(self):
        assert format_paper_id("10.1145/3318464.3389700") == "DOI:10.1145/3318464.3389700"

    def test_format_doi_url(self):
        assert format_paper_id("https://doi.org/10.1145/3318464.3389700") == "DOI:10.1145/3318464.3389700"

    def test_format_doi_prefix(self):
        assert format_paper_id("doi:10.1145/3318464.3389700") == "DOI:10.1145/3318464.3389700"

    def test_format_doi_already_prefixed(self):
        assert format_paper_id("DOI:10.1145/3318464.3389700") == "DOI:10.1145/3318464.3389700"

    def test_format_arxiv_plain(self):
        assert format_paper_id("2301.12345") == "ARXIV:2301.12345"

    def test_format_arxiv_versioned(self):
        assert format_paper_id("2301.12345v2") == "ARXIV:2301.12345v2"

    def test_format_arxiv_url(self):
        assert format_paper_id("https://arxiv.org/abs/2301.12345") == "ARXIV:2301.12345"

    def test_format_arxiv_prefix(self):
        assert format_paper_id("arxiv:2301.12345") == "ARXIV:2301.12345"
        assert format_paper_id("ARXIV:2301.12345") == "ARXIV:2301.12345"

    def test_format_corpus_id(self):
        assert format_paper_id("CorpusId:12345") == "CorpusId:12345"
        assert format_paper_id("corpusid:12345") == "CorpusId:12345"

    def test_format_s2_hash(self):
        sha = "649def34f8be52c8b66281af98ae884c09aef38b"
        assert format_paper_id(sha) == sha

    def test_format_empty(self):
        assert format_paper_id("") == ""
        assert format_paper_id("   ") == ""


class TestGetPaperCitationsWithContexts:
    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_get_citations_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "contexts": ["In contrast to [1], our transformer architecture avoids quadratic latency."],
                    "intents": ["methodology"],
                    "isInfluential": True,
                    "citingPaper": {
                        "paperId": "citing_paper_01",
                        "title": "Attention Optimization",
                        "year": 2023,
                        "externalIds": {"DOI": "10.1016/j.jcp.2023.01"},
                    },
                },
                {
                    "contexts": [
                        "Prior work [1] established baseline convergence bounds.",
                        "We extend the theorem in [1] to non-convex domains.",
                    ],
                    "intents": ["background", "methodology"],
                    "isInfluential": False,
                    "citingPaper": {
                        "paperId": "citing_paper_02",
                        "title": "Extended Convergence Analysis",
                        "year": 2024,
                        "externalIds": {"ArXiv": "2401.54321"},
                    },
                },
            ],
            "offset": 0,
        }
        mock_get.return_value = mock_resp

        client = SemanticScholarClient(api_key="test-api-key")
        records = client.get_paper_citations_with_contexts("10.1145/3318464.3389700", limit=10)

        assert len(records) == 3
        assert all(isinstance(r, CitationContextRecord) for r in records)

        # Check target paper ID
        assert all(r.target_paper_id == "10.1145/3318464.3389700" for r in records)

        # Record 1 from citing_paper_01
        r1 = records[0]
        assert r1.source_paper_id == "citing_paper_01"
        assert "quadratic latency" in r1.context_text
        assert r1.is_influential is True
        assert r1.intent == "methodology"
        assert len(r1.id) > 0

        # Record 2 & 3 from citing_paper_02 (multiple contexts)
        r2 = records[1]
        assert r2.source_paper_id == "citing_paper_02"
        assert "baseline convergence bounds" in r2.context_text
        assert r2.is_influential is False
        assert r2.intent == "background, methodology"

        r3 = records[2]
        assert r3.source_paper_id == "citing_paper_02"
        assert "non-convex domains" in r3.context_text
        assert r3.is_influential is False
        assert r3.intent == "background, methodology"

        # Unique deterministic IDs
        assert len({r1.id, r2.id, r3.id}) == 3

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_query_params_and_headers(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_get.return_value = mock_resp

        client = SemanticScholarClient(api_key="my-secret-token", timeout=15)
        client.get_paper_citations_with_contexts("10.1234/test.doi", limit=50)

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args

        # URL check
        assert args[0] == "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test.doi/citations"
        # Params check
        assert kwargs["params"]["limit"] == 50
        assert "contexts" in kwargs["params"]["fields"]
        assert "citingPaper.paperId" in kwargs["params"]["fields"]
        # Headers check
        assert kwargs["headers"]["x-api-key"] == "my-secret-token"
        assert "scifi" in kwargs["headers"]["User-Agent"]
        # Timeout check
        assert kwargs["timeout"] == 15

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_empty_contexts_handling(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"contexts": [], "intents": ["background"], "isInfluential": False, "citingPaper": {"paperId": "p1"}},
                {"contexts": None, "intents": [], "isInfluential": True, "citingPaper": {"paperId": "p2"}},
                {
                    "contexts": ["  Valid context sentence.  "],
                    "intents": [],
                    "isInfluential": False,
                    "citingPaper": {"paperId": "p3"},
                },
            ]
        }
        mock_get.return_value = mock_resp

        client = SemanticScholarClient()
        records = client.get_paper_citations_with_contexts("2301.12345")

        assert len(records) == 1
        assert records[0].source_paper_id == "p3"
        assert records[0].context_text == "Valid context sentence."
        assert records[0].intent is None

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_empty_response_data(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"data": []}
        mock_get.return_value = mock_resp

        client = SemanticScholarClient()
        assert client.get_paper_citations_with_contexts("DOI:10.1234/none") == []

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_rate_limit_429_graceful_degradation(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        client = SemanticScholarClient(max_retries=0)
        records = client.get_paper_citations_with_contexts("10.1234/ratelimit")
        assert records == []

    @patch("scifi.literature.semantic_scholar.time.sleep")
    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_rate_limit_429_backoff_and_retry_success(self, mock_get, mock_sleep):
        mock_429 = MagicMock(status_code=429)
        mock_200 = MagicMock(status_code=200)
        mock_200.json.return_value = {
            "data": [
                {
                    "contexts": ["Recovered context after backoff."],
                    "intents": ["methodology"],
                    "isInfluential": False,
                    "citingPaper": {"paperId": "recovered_01"},
                }
            ]
        }
        mock_get.side_effect = [mock_429, mock_200]

        client = SemanticScholarClient(max_retries=2, backoff_factor=0.01)
        records = client.get_paper_citations_with_contexts("10.1234/retry")

        assert len(records) == 1
        assert records[0].source_paper_id == "recovered_01"
        assert mock_sleep.called

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_404_not_found_handling(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        client = SemanticScholarClient()
        records = client.get_paper_citations_with_contexts("10.1234/notfound")
        assert records == []

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_timeout_and_network_error_resilience(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out")

        client = SemanticScholarClient()
        records = client.get_paper_citations_with_contexts("10.1234/timeout")
        assert records == []

    def test_empty_paper_id(self):
        client = SemanticScholarClient()
        assert client.get_paper_citations_with_contexts("") == []
        assert client.get_paper_citations_with_contexts("   ") == []


class TestGetPaperMetadata:
    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_get_paper_metadata_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "paperId": "abc12345",
            "title": "Attention Is All You Need",
            "year": 2017,
            "citationCount": 95000,
            "influentialCitationCount": 12000,
        }
        mock_get.return_value = mock_resp

        client = SemanticScholarClient()
        meta = client.get_paper_metadata("1706.03762")

        assert meta is not None
        assert meta["title"] == "Attention Is All You Need"
        assert meta["citationCount"] == 95000

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_get_paper_metadata_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        client = SemanticScholarClient()
        meta = client.get_paper_metadata("nonexistent_paper_id")
        assert meta is None

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_get_paper_metadata_rate_limit(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        client = SemanticScholarClient(max_retries=0)
        meta = client.get_paper_metadata("10.1234/ratelimit")
        assert meta is None


class TestClientCaching:
    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_citation_context_caching(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {
                    "contexts": ["Cached context."],
                    "intents": ["methodology"],
                    "isInfluential": True,
                    "citingPaper": {"paperId": "cached_paper"},
                }
            ]
        }
        mock_get.return_value = mock_resp

        memory_cache = {}
        cache_wrapper = MagicMock()
        cache_wrapper.get.side_effect = lambda k: memory_cache.get(k)
        cache_wrapper.set.side_effect = lambda k, v: memory_cache.__setitem__(k, v)

        client = SemanticScholarClient(cache=cache_wrapper)

        # First call hits mock_get
        records1 = client.get_paper_citations_with_contexts("10.1234/cached", limit=10)
        assert len(records1) == 1
        assert mock_get.call_count == 1
        assert cache_wrapper.set.called

        # Second call hits cache
        records2 = client.get_paper_citations_with_contexts("10.1234/cached", limit=10)
        assert len(records2) == 1
        assert records2[0].context_text == "Cached context."
        assert mock_get.call_count == 1  # No additional network call

    @patch("scifi.literature.semantic_scholar.requests.get")
    def test_metadata_caching(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"paperId": "meta1", "title": "Cached Title"}
        mock_get.return_value = mock_resp

        memory_cache = {}
        cache_wrapper = MagicMock()
        cache_wrapper.get.side_effect = lambda k: memory_cache.get(k)
        cache_wrapper.set.side_effect = lambda k, v: memory_cache.__setitem__(k, v)

        client = SemanticScholarClient(cache=cache_wrapper)

        meta1 = client.get_paper_metadata("10.1234/meta")
        assert meta1["title"] == "Cached Title"
        assert mock_get.call_count == 1

        meta2 = client.get_paper_metadata("10.1234/meta")
        assert meta2["title"] == "Cached Title"
        assert mock_get.call_count == 1


class TestResilientSessionIntegration:
    @patch("scifi.literature.semantic_scholar.get_session")
    def test_routes_through_get_session(self, mock_get_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"paperId": "abc12345", "title": "Centralized Network Test"}
        mock_get_session.return_value.get.return_value = mock_resp

        client = SemanticScholarClient()
        meta = client.get_paper_metadata("10.1234/test")

        assert meta is not None
        assert meta["title"] == "Centralized Network Test"
        assert mock_get_session.return_value.get.called
        args, kwargs = mock_get_session.return_value.get.call_args
        assert "api.semanticscholar.org" in args[0]
