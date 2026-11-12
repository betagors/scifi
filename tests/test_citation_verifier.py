"""
Unit and integration tests for SciFi Citation Verifier.
"""

import unittest
from unittest.mock import patch

import requests

from scifi.citation_verifier import verify_citation
from scifi.citation_verifier.bib_auditor import (
    audit_bib_content,
    generate_sanitized_bib,
    search_identifier_by_title,
)
from scifi.citation_verifier.discrepancy import (
    audit_discrepancies,
    clean_text_for_comparison,
    string_similarity,
)
from scifi.citation_verifier.fetchers import (
    ArXivFetcher,
    CrossRefFetcher,
    DataCiteFetcher,
    OpenAlexFetcher,
)
from scifi.citation_verifier.identifiers import clean_doi, extract_identifier
from scifi.citation_verifier.models import (
    Author,
    CitationMetadata,
    ClaimedMetadata,
    VerificationStatus,
)


class TestIdentifiers(unittest.TestCase):
    def test_clean_doi(self):
        self.assertEqual(clean_doi("10.1000/182"), "10.1000/182")
        self.assertEqual(clean_doi("https://doi.org/10.1000/182."), "10.1000/182")
        self.assertEqual(clean_doi("doi:10.1000/182,"), "10.1000/182")
        self.assertEqual(clean_doi("http://dx.doi.org/10.1000/182;"), "10.1000/182")
        # Ensure parenthesis inside DOI is preserved if balanced
        self.assertEqual(clean_doi("10.1002/(SICI)1097-0142"), "10.1002/(SICI)1097-0142")

    def test_extract_doi(self):
        t, val, _ = extract_identifier("https://doi.org/10.1038/s41586-020-2649-2")
        self.assertEqual(t, "doi")
        self.assertEqual(val, "10.1038/s41586-020-2649-2")

        t2, val2, _ = extract_identifier("Check this: 10.1145/3359591.3359737.")
        self.assertEqual(t2, "doi")
        self.assertEqual(val2, "10.1145/3359591.3359737")

    def test_extract_arxiv(self):
        t, val, _ = extract_identifier("https://arxiv.org/abs/1706.03762v5")
        self.assertEqual(t, "arxiv")
        self.assertEqual(val, "1706.03762v5")

        t2, val2, _ = extract_identifier("arxiv:2301.12345")
        self.assertEqual(t2, "arxiv")
        self.assertEqual(val2, "2301.12345")

    def test_extract_pubmed(self):
        t, val, _ = extract_identifier("https://pubmed.ncbi.nlm.nih.gov/32943785/")
        self.assertEqual(t, "pubmed")
        self.assertEqual(val, "32943785")

        t2, val2, _ = extract_identifier("PMID: 32943785")
        self.assertEqual(t2, "pubmed")
        self.assertEqual(val2, "32943785")


class TestModelsAndFormatting(unittest.TestCase):
    def test_author_parsing(self):
        a1 = Author.from_string("Harris, Charles R.")
        self.assertEqual(a1.family, "Harris")
        self.assertEqual(a1.given, "Charles R.")

        a2 = Author.from_string("John von Neumann")
        self.assertEqual(a2.family, "Neumann")

    def test_cite_key_generation(self):
        meta = CitationMetadata(
            identifier_type="doi",
            identifier_value="10.1038/s41586-020-2649-2",
            title="Array programming with NumPy",
            authors=[Author.from_string("Harris, Charles R.")],
            year=2020,
        )
        self.assertEqual(meta.generate_cite_key(), "Harris2020Array")

    def test_bibtex_formatting(self):
        meta = CitationMetadata(
            identifier_type="doi",
            identifier_value="10.1038/s41586-020-2649-2",
            canonical_doi="10.1038/s41586-020-2649-2",
            title="Array programming with NumPy",
            authors=[Author.from_string("Harris, Charles R."), Author.from_string("Millman, K. Jarrod")],
            year=2020,
            venue="Nature",
            volume="585",
            pages="357-362",
        )
        bib = meta.to_bibtex()
        self.assertIn("@article{Harris2020Array,", bib)
        self.assertIn("title = {Array programming with NumPy}", bib)
        self.assertIn("author = {Harris, Charles R. and Millman, K. Jarrod}", bib)
        self.assertIn("journal = {Nature}", bib)
        self.assertIn("year = {2020}", bib)
        self.assertIn("doi = {10.1038/s41586-020-2649-2}", bib)

    def test_apa_formatting(self):
        meta = CitationMetadata(
            identifier_type="doi",
            identifier_value="10.1038/s41586-020-2649-2",
            canonical_doi="10.1038/s41586-020-2649-2",
            title="Array programming with NumPy",
            authors=[Author.from_string("Harris, Charles R."), Author.from_string("Millman, K. Jarrod")],
            year=2020,
            venue="Nature",
            volume="585",
            issue="7825",
            pages="357-362",
        )
        apa = meta.to_apa()
        self.assertIn("Harris, C. R. & Millman, K. J.", apa)
        self.assertIn("(2020). Array programming with NumPy.", apa)
        self.assertIn("*Nature*, *585*(7825), 357-362.", apa)
        self.assertIn("https://doi.org/10.1038/s41586-020-2649-2", apa)


class TestDiscrepancyAuditor(unittest.TestCase):
    def test_text_cleaning(self):
        self.assertEqual(
            clean_text_for_comparison(r"A study of {DNA} \emph{methylation}."),
            "a study of dna methylation",
        )

    def test_string_similarity(self):
        s1 = "Array programming with NumPy"
        s2 = "Array Programming in NumPy"
        sim = string_similarity(s1, s2)
        self.assertGreater(sim, 0.75)

    def test_audit_discrepancies(self):
        claimed = ClaimedMetadata(
            title="Array programming in Python",
            authors=["Smith, John"],
            year=2015,
            venue="Science",
        )
        disc = audit_discrepancies(
            claimed=claimed,
            verified_title="Array programming with NumPy",
            verified_authors=["Charles R. Harris", "K. Jarrod Millman"],
            verified_year=2020,
            verified_venue="Nature",
        )
        # Should flag author mismatch and year mismatch
        fields = [d.field for d in disc]
        self.assertIn("author", fields)
        self.assertIn("year", fields)


class TestBibAuditor(unittest.TestCase):
    def test_audit_bib_content(self):
        bib_text = """
@article{Harris2020,
  title = {Array programming with NumPy},
  author = {Harris, Charles R.},
  year = {2020},
  doi = {10.1038/s41586-020-2649-2}
}
@article{RetractedSample,
  title = {Ileal-lymphoid-nodular hyperplasia},
  author = {Wakefield, A. J.},
  year = {1998},
  doi = {10.1016/S0140-6736(97)11096-0}
}
"""
        report = audit_bib_content(bib_text, search_missing=False)
        self.assertEqual(report.total_entries, 2)
        self.assertGreaterEqual(report.verified_count, 1)
        self.assertGreaterEqual(report.retracted_count, 1)

        sanitized = generate_sanitized_bib(report)
        self.assertIn("WARNING: CITATION RETRACTED", sanitized)


class TestLiveVerification(unittest.TestCase):
    def test_verify_known_paper(self):
        res = verify_citation("10.1038/s41586-020-2649-2")
        self.assertEqual(res.status, VerificationStatus.VERIFIED)
        self.assertIn("NumPy", res.title)
        self.assertEqual(res.year, 2020)
        self.assertFalse(res.is_retracted)

    def test_verify_retracted_paper(self):
        res = verify_citation("10.1016/S0140-6736(97)11096-0")
        self.assertEqual(res.status, VerificationStatus.RETRACTED)
        self.assertTrue(res.is_retracted)

    def test_verify_arxiv(self):
        res = verify_citation("https://arxiv.org/abs/1706.03762")
        self.assertEqual(res.status, VerificationStatus.VERIFIED)
        self.assertIn("Attention Is All You Need", res.title)


def test_crossref_fetcher_uses_resilient_session():
    with patch("scifi.citation_verifier.fetchers.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"message": {"title": ["Test Paper"]}}'
        mock_session.get.return_value = resp

        meta = CrossRefFetcher.fetch("10.1000/182")
        assert meta is not None
        assert mock_session.get.called


def test_openalex_fetcher_uses_resilient_session():
    with patch("scifi.citation_verifier.fetchers.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"id": "W123", "title": "Test Paper"}'
        mock_session.get.return_value = resp

        res = OpenAlexFetcher.fetch("10.1000/182")
        assert res is not None
        assert mock_session.get.called


def test_arxiv_fetcher_uses_resilient_session():
    with patch("scifi.citation_verifier.fetchers.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry>
            <title>Test Arxiv</title>
            <author><name>Author A</name></author>
            <published>2023-01-01T00:00:00Z</published>
          </entry>
        </feed>"""
        mock_session.get.return_value = resp

        meta = ArXivFetcher.fetch("2301.12345")
        assert meta is not None
        assert meta.title == "Test Arxiv"
        assert mock_session.get.called


def test_datacite_fetcher_uses_resilient_session():
    with patch("scifi.citation_verifier.fetchers.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp._content = (
            b'{"data": {"attributes": {"titles": [{"title": "Data Paper"}], "creators": [{"name": "Smith, J."}]}}}'
        )
        mock_session.get.return_value = resp

        meta = DataCiteFetcher.fetch("10.5061/dryad.test")
        assert meta is not None
        assert meta.title == "Data Paper"
        assert mock_session.get.called


def test_bib_auditor_search_by_title_uses_resilient_session():
    with patch("scifi.citation_verifier.bib_auditor.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b'{"results": [{"doi": "https://doi.org/10.1234/test"}]}'
        mock_session.get.return_value = resp

        res = search_identifier_by_title("A great paper on transformers")
        assert res == ("doi", "10.1234/test")
        assert mock_session.get.called


def test_extract_identifier_url_uses_resilient_session():
    with patch("scifi.citation_verifier.identifiers.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value
        resp = requests.Response()
        resp.status_code = 200
        resp.url = "https://publisher.com/paper"
        resp._content = b'<html><head><meta name="citation_doi" content="10.1234/test"></head><body></body></html>'
        mock_session.get.return_value = resp

        id_type, id_val, extra = extract_identifier("https://publisher.com/paper", follow_links=True)
        assert id_type == "doi"
        assert id_val == "10.1234/test"
        assert mock_session.get.called
        # Verify custom Mozilla header is preserved
        _, kwargs = mock_session.get.call_args
        assert "Mozilla/5.0" in kwargs["headers"]["User-Agent"]


if __name__ == "__main__":
    unittest.main()
