"""
Literature Fetcher and PDF Text Extraction Module.
Consolidates Hypatia open-access paper retrieval and structured text extraction.
"""

from scifi.literature.benchmarks import BenchmarkExtractor
from scifi.literature.extractor import extract_pdf_text
from scifi.literature.fetcher import fetch_paper_pdf
from scifi.literature.resolver import PaperResolver

__all__ = ["fetch_paper_pdf", "extract_pdf_text", "PaperResolver", "BenchmarkExtractor"]
