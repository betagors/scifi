"""
Argus: Sentinel for Academic Attribution, Uncredited Methods, and Plagiarism Detection.
"""

from .detector import (
    CANONICAL_METHODS,
    COMMON_KNOWLEDGE,
    SentenceSpan,
    detect_informal_ai_tropes,
    extract_potential_methods,
    split_into_sentence_spans,
)
from .engine import ArgusEngine
from .models import (
    AttributionCategory,
    AttributionFinding,
    AttributionReport,
    SuggestedAction,
)
from .patcher import (
    append_bibtex_entry,
    generate_reformulate_prompt,
    insert_cite_into_latex,
)
from .searcher import ArgusSearcher

__all__ = [
    "ArgusEngine",
    "ArgusSearcher",
    "AttributionCategory",
    "AttributionFinding",
    "AttributionReport",
    "CANONICAL_METHODS",
    "COMMON_KNOWLEDGE",
    "SentenceSpan",
    "SuggestedAction",
    "append_bibtex_entry",
    "detect_informal_ai_tropes",
    "extract_potential_methods",
    "generate_reformulate_prompt",
    "insert_cite_into_latex",
    "split_into_sentence_spans",
]
