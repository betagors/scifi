#!/usr/bin/env python3
"""
test_keywords.py — Academic Title, Abstract & Keyword Optimization Engine (Shannon).
Evaluates academic manuscripts for:
1. Title-keyword non-redundancy & metadata expansion.
2. Abstract keyphrase density and 3-beat anchoring.
3. Dual-audience accessibility & sentence complexity (for non-technical/interdisciplinary readers).
4. Academic SEO & Visibility Hacks (snippet front-loading, sweet-spot length).
5. 100-point Reviewer Triage Scorecard.
6. Live OpenAlex/Crossref title collision and subfield relevance diagnostics.
"""

from __future__ import annotations

import difflib
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

# Standard English stop words common in academic titles and abstracts
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "should", "shouldn't", "so", "some", "such", "than", "that", "the",
    "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "wasn't", "we", "were", "weren't", "what", "when", "where", "which", "while",
    "who", "whom", "why", "with", "won't", "would", "wouldn't", "you", "your",
    "yours", "yourself", "yourselves", "via", "using", "based", "toward", "towards"
}


def normalize_token(word: str) -> str:
    """Strip leading/trailing punctuation and apply lightweight morphological normalization."""
    w = word.strip().lower()
    w = re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", w)
    # Simple suffix normalization (e.g., optimization -> optimiz, learning -> learn)
    for suffix in ("ing", "ion", "ions", "es", "s", "ed", "ly"):
        if w.endswith(suffix) and len(w) - len(suffix) >= 4:
            w = w[:-len(suffix)]
            break
    return w


def tokenize(text: str, remove_stopwords: bool = True) -> List[str]:
    """Tokenize text into cleaned alphanumeric tokens, optionally filtering stop words."""
    raw_tokens = re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text)
    tokens: List[str] = []
    for token in raw_tokens:
        subparts = token.split("-")
        for part in subparts:
            lowered = part.lower()
            if remove_stopwords and lowered in STOP_WORDS:
                continue
            cleaned = re.sub(r"[^a-z0-9]", "", lowered)
            if cleaned and len(cleaned) > 1:
                tokens.append(cleaned)
    return tokens


def compute_title_keyword_overlap(title: str, keywords: List[str]) -> Dict[str, Any]:
    """
    Calculate the vocabulary overlap between the title and author keywords.
    Keywords should provide metadata expansion and NOT duplicate title words.
    """
    title_tokens = set(tokenize(title, remove_stopwords=True))
    title_stems = {normalize_token(t) for t in title_tokens}

    overlapping_words: Set[str] = set()
    keyword_evaluations: List[Dict[str, Any]] = []

    for kw in keywords:
        kw_tokens = tokenize(kw, remove_stopwords=True)
        overlap_found = False
        matched_tokens = []
        for token in kw_tokens:
            stem = normalize_token(token)
            if token in title_tokens or stem in title_stems:
                overlapping_words.add(token)
                matched_tokens.append(token)
                overlap_found = True

        keyword_evaluations.append({
            "keyword": kw,
            "is_redundant": overlap_found,
            "matched_title_words": matched_tokens
        })

    total_kw_words = sum(len(tokenize(kw, remove_stopwords=True)) for kw in keywords) or 1
    overlap_ratio = len(overlapping_words) / total_kw_words
    distinct_count = sum(1 for k in keyword_evaluations if not k["is_redundant"])

    return {
        "overlap_ratio": round(overlap_ratio, 3),
        "overlapping_words": sorted(list(overlapping_words)),
        "distinct_keywords_count": distinct_count,
        "total_keywords": len(keywords),
        "keyword_evaluations": keyword_evaluations,
    }


def compute_abstract_keyword_density(abstract: str, keywords: List[str]) -> Dict[str, Any]:
    """
    Measure repetition frequency of keywords in the abstract.
    Optimal density: 2–4 occurrences per primary keyphrase.
    >5 is keyword stuffing; 0 is omitted.
    """
    abstract_lower = abstract.lower()
    densities: Dict[str, Dict[str, Any]] = {}

    for kw in keywords:
        kw_clean = kw.strip().lower()
        if not kw_clean:
            continue
        # Search for exact phrase match with word boundaries
        pattern = r"\b" + re.escape(kw_clean) + r"\b"
        matches = re.findall(pattern, abstract_lower)
        count = len(matches)

        # Fallback to token stem matching if compound phrase not found intact
        if count == 0:
            tokens = tokenize(kw_clean, remove_stopwords=True)
            if tokens:
                all_found = True
                token_counts = []
                for t in tokens:
                    t_matches = len(re.findall(r"\b" + re.escape(t) + r"\b", abstract_lower))
                    token_counts.append(t_matches)
                    if t_matches == 0:
                        all_found = False
                if all_found:
                    count = min(token_counts)

        if count == 0:
            status = "OMITTED"
        elif 1 <= count <= 4:
            status = "OPTIMAL" if count >= 2 else "LIGHT"
        else:
            status = "STUFFED"

        densities[kw] = {
            "count": count,
            "status": status,
        }

    return {
        "densities": densities,
        "total_keywords": len(keywords),
    }


def evaluate_accessibility(abstract: str) -> Dict[str, Any]:
    """
    Evaluate accessibility and cognitive load for non-technical or interdisciplinary readers:
    1. Sentence count & sentence length distribution.
    2. Flags run-on sentences (>35 words).
    3. Analyzes opening sentence for intuitive framing vs hyper-dense nested clauses.
    """
    # Split sentences cleanly on punctuation
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if s.strip()]
    sentence_lengths = [len(re.findall(r"\b[A-Za-z0-9-]+\b", s)) for s in sentences]

    max_len = max(sentence_lengths) if sentence_lengths else 0
    avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0
    has_runon = any(length > 35 for length in sentence_lengths)

    # Lead sentence readability check
    lead_sentence = sentences[0] if sentences else ""
    lead_words = sentence_lengths[0] if sentence_lengths else 0
    lead_accessible = (lead_words <= 30) and not bool(re.search(r"(\$|\\|\bO\([nN\d]\)|\bsuch that\b)", lead_sentence))

    return {
        "sentence_count": len(sentences),
        "sentence_lengths": sentence_lengths,
        "max_sentence_length": max_len,
        "avg_sentence_length": round(avg_len, 1),
        "has_runon_sentences": has_runon,
        "lead_accessible": lead_accessible,
        "lead_sentence": lead_sentence,
    }
