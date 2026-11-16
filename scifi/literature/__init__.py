"""
Literature Fetcher and PDF Text Extraction Module.
Consolidates Hypatia open-access paper retrieval and structured text extraction.
"""

from scifi.literature.benchmarks import BenchmarkExtractor
from scifi.literature.discovery import expand_academic_query, rerank_papers
from scifi.literature.extractor import extract_pdf_text, extract_sections_from_text
from scifi.literature.fetcher import fetch_paper_pdf, find_local_pdf, resolve_paper_pdf
from scifi.literature.gap_matrix import GapMatrixBuilder, GapSynthesisReport, PaperMatrixRow, StructuralGap
from scifi.literature.kg import DEFAULT_KG_PATH, KnowledgeGraphStore
from scifi.literature.kg_extractor import extract_deterministic_kg_facts, record_semantic_fact
from scifi.literature.resolver import PaperResolver
from scifi.literature.sota import (
    PerformanceDelta,
    SotaEvaluationReport,
    SotaEvaluationResults,
    SotaEvaluator,
)
from scifi.literature.sources import (
    fetch_arxiv_structured_text,
    fetch_openreview_reviews,
)

__all__ = [
    "DEFAULT_KG_PATH",
    "KnowledgeGraphStore",
    "extract_deterministic_kg_facts",
    "record_semantic_fact",
    "fetch_paper_pdf",
    "find_local_pdf",
    "resolve_paper_pdf",
    "extract_pdf_text",
    "extract_sections_from_text",
    "fetch_arxiv_structured_text",
    "fetch_openreview_reviews",
    "expand_academic_query",
    "rerank_papers",
    "GapMatrixBuilder",
    "GapSynthesisReport",
    "PaperMatrixRow",
    "StructuralGap",
    "PaperResolver",
    "BenchmarkExtractor",
    "SotaEvaluator",
    "PerformanceDelta",
    "SotaEvaluationReport",
    "SotaEvaluationResults",
]
