"""
Unit tests for Literature Fetcher and PDF Text Extractor (scifi.literature).
"""

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from pypdf import PdfWriter

from scifi.literature import extract_pdf_text, fetch_paper_pdf


class TestPdfExtractor:
    @pytest.fixture
    def sample_asset_pdf(self):
        pdf_path = Path(__file__).resolve().parent.parent / "assets" / "1-s2.0-S0022123623002525-main.pdf"
        if not pdf_path.exists():
            pytest.skip(f"Asset PDF not found at {pdf_path}")
        return str(pdf_path)

    @pytest.fixture
    def synthetic_pdf(self, tmp_path):
        writer = PdfWriter()
        # Add 3 pages with dummy content
        # Note: pypdf creates blank pages easily, but for text extraction test
        # we can test basic page reading and metadata
        writer.add_blank_page(width=72, height=72)
        writer.add_blank_page(width=72, height=72)
        synthetic_path = tmp_path / "synthetic.pdf"
        with open(synthetic_path, "wb") as f:
            writer.write(f)
        return str(synthetic_path)

    def test_extract_pdf_text_sample_file(self, sample_asset_pdf):
        res = extract_pdf_text(sample_asset_pdf, max_pages=5)
        assert res["status"] == "SUCCESS"
        assert res["total_pages"] > 0
        assert "abstract" in res
        assert "system_model_or_method" in res
        assert "limitations_and_conclusion" in res
        assert "raw_sample" in res
        assert "sections" in res
        assert isinstance(res["abstract"], str)
        assert len(res["abstract"]) > 0

    def test_extract_pdf_text_max_pages_limit(self, sample_asset_pdf):
        res_limited = extract_pdf_text(sample_asset_pdf, max_pages=1)
        res_more = extract_pdf_text(sample_asset_pdf, max_pages=5)
        assert res_limited["status"] == "SUCCESS"
        # total_pages should reflect full document
        assert res_limited["total_pages"] == res_more["total_pages"]
        # raw_sample from 1 page should be <= raw_sample from 5 pages
        assert len(res_limited["raw_sample"]) <= len(res_more["raw_sample"])

    def test_extract_pdf_text_synthetic(self, synthetic_pdf):
        res = extract_pdf_text(synthetic_pdf)
        assert res["status"] == "SUCCESS"
        assert res["total_pages"] == 2
        assert res["abstract"] == ""
        assert res["raw_sample"] == ""

    def test_extract_pdf_text_non_existent(self, tmp_path):
        missing = tmp_path / "does_not_exist.pdf"
        res = extract_pdf_text(missing)
        assert res["status"] == "ERROR"
        assert "File not found" in res["error_message"]

    def test_extract_pdf_text_corrupt_file(self, tmp_path):
        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"This is not a valid PDF header.")
        res = extract_pdf_text(corrupt)
        assert res["status"] == "ERROR"
        assert "error" in res or "error_message" in res


class TestPaperFetcher:
    def test_fetch_paper_pdf_arxiv_id_success(self, tmp_path):
        fake_pdf_bytes = b"%PDF-1.4 dummy pdf content for arxiv"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = MagicMock(return_value=[fake_pdf_bytes])

        with patch("requests.get", return_value=mock_response) as mock_get:
            res = fetch_paper_pdf("arxiv:2301.12345", output_dir=tmp_path)
            assert res["status"] == "SUCCESS"
            assert res["source"] == "arXiv"
            assert res["pdf_url"] == "https://arxiv.org/pdf/2301.12345.pdf"
            assert Path(res["file_path"]).exists()
            assert Path(res["file_path"]).read_bytes() == fake_pdf_bytes
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            assert args[0] == "https://arxiv.org/pdf/2301.12345.pdf"

    def test_fetch_paper_pdf_arxiv_url_success(self, tmp_path):
        fake_pdf_bytes = b"%PDF-1.4 dummy pdf content"
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_content = MagicMock(return_value=[fake_pdf_bytes])

        with patch("requests.get", return_value=mock_response) as mock_get:
            res = fetch_paper_pdf("https://arxiv.org/abs/2301.12345v2", output_dir=tmp_path)
            assert res["status"] == "SUCCESS"
            assert res["source"] == "arXiv"
            assert res["pdf_url"] == "https://arxiv.org/pdf/2301.12345v2.pdf"
            assert Path(res["file_path"]).exists()

    def test_fetch_paper_pdf_arxiv_404(self, tmp_path):
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("requests.get", return_value=mock_response):
            res = fetch_paper_pdf("arxiv:9999.99999", output_dir=tmp_path)
            assert res["status"] == "NOT_FOUND"
            assert "404" in res.get("message", "") or "Could not retrieve" in res.get("message", "")

    def test_fetch_paper_pdf_doi_unpaywall_success(self, tmp_path):
        fake_pdf_bytes = b"%PDF-1.4 unpaywall pdf content"
        mock_unpaywall = MagicMock()
        mock_unpaywall.status_code = 200
        mock_unpaywall.json.return_value = {
            "title": "Unpaywall Paper Title",
            "best_oa_location": {"url_for_pdf": "https://publisher.org/paper.pdf"},
        }

        mock_pdf_stream = MagicMock()
        mock_pdf_stream.status_code = 200
        mock_pdf_stream.iter_content = MagicMock(return_value=[fake_pdf_bytes])

        def side_effect(url, **kwargs):
            if "api.unpaywall.org" in url:
                return mock_unpaywall
            elif url == "https://publisher.org/paper.pdf":
                return mock_pdf_stream
            return MagicMock(status_code=404)

        with patch("requests.get", side_effect=side_effect):
            res = fetch_paper_pdf("10.1007/s00222-023-01", output_dir=tmp_path, email="test@scifi.org")
            assert res["status"] == "SUCCESS"
            assert res["source"] == "Unpaywall"
            assert res["pdf_url"] == "https://publisher.org/paper.pdf"
            assert Path(res["file_path"]).exists()
            assert Path(res["file_path"]).read_bytes() == fake_pdf_bytes

    def test_fetch_paper_pdf_doi_openalex_fallback(self, tmp_path):
        fake_pdf_bytes = b"%PDF-1.4 openalex pdf content"
        mock_unpaywall = MagicMock()
        mock_unpaywall.status_code = 404

        mock_openalex = MagicMock()
        mock_openalex.status_code = 200
        mock_openalex.json.return_value = {
            "title": "OpenAlex Paper Title",
            "best_oa_location": {"pdf_url": "https://openalex-oa.org/paper.pdf"},
        }

        mock_pdf_stream = MagicMock()
        mock_pdf_stream.status_code = 200
        mock_pdf_stream.iter_content = MagicMock(return_value=[fake_pdf_bytes])

        def side_effect(url, **kwargs):
            if "api.unpaywall.org" in url:
                return mock_unpaywall
            elif "api.openalex.org" in url:
                return mock_openalex
            elif url == "https://openalex-oa.org/paper.pdf":
                return mock_pdf_stream
            return MagicMock(status_code=404)

        with patch("requests.get", side_effect=side_effect):
            res = fetch_paper_pdf("https://doi.org/10.1007/fallback-paper", output_dir=tmp_path)
            assert res["status"] == "SUCCESS"
            assert res["source"] == "OpenAlex"
            assert res["pdf_url"] == "https://openalex-oa.org/paper.pdf"
            assert Path(res["file_path"]).exists()

    def test_fetch_paper_pdf_doi_no_oa_pdf(self, tmp_path):
        mock_unpaywall = MagicMock()
        mock_unpaywall.status_code = 200
        mock_unpaywall.json.return_value = {
            "title": "Closed Access Paper",
            "best_oa_location": None,
        }

        mock_openalex = MagicMock()
        mock_openalex.status_code = 200
        mock_openalex.json.return_value = {
            "title": "Closed Access Paper",
            "best_oa_location": None,
            "primary_location": None,
            "open_access": {"is_oa": False, "oa_url": None},
        }

        def side_effect(url, **kwargs):
            if "api.unpaywall.org" in url:
                return mock_unpaywall
            elif "api.openalex.org" in url:
                return mock_openalex
            return MagicMock(status_code=404)

        with patch("requests.get", side_effect=side_effect):
            res = fetch_paper_pdf("10.1007/closed-paper", output_dir=tmp_path)
            assert res["status"] == "NO_OA_PDF"

    def test_fetch_paper_pdf_doi_not_found(self, tmp_path):
        mock_404 = MagicMock(status_code=404)

        with patch("requests.get", return_value=mock_404):
            res = fetch_paper_pdf("10.1007/non-existent-doi", output_dir=tmp_path)
            assert res["status"] == "NOT_FOUND"

    def test_fetch_paper_pdf_network_error(self, tmp_path):
        import requests

        with patch("requests.get", side_effect=requests.RequestException("Network timeout")):
            res = fetch_paper_pdf("arxiv:2301.12345", output_dir=tmp_path)
            assert res["status"] == "ERROR"
            assert "Network timeout" in res.get("error_message", res.get("message", ""))
