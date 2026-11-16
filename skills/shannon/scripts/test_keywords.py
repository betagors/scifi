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


VENUE_ABSTRACT_LIMITS: Dict[str, Dict[str, Any]] = {
    "ieee": {"min": 150, "recommended_max": 200, "hard_max": 250, "label": "IEEE (150-200w recommended, 250w max)"},
    "acm": {"min": 150, "recommended_max": 200, "hard_max": 250, "label": "ACM (150-200w recommended, 250w max)"},
    "elsevier": {"min": 150, "recommended_max": 250, "hard_max": 250, "label": "Elsevier (150-250w)"},
    "springer": {"min": 150, "recommended_max": 250, "hard_max": 250, "label": "Springer (150-250w)"},
    "general": {"min": 150, "recommended_max": 220, "hard_max": 250, "label": "General (150-220w)"},
}


def evaluate_accessibility(abstract: str, target_venue: Optional[str] = None) -> Dict[str, Any]:
    """
    Evaluate accessibility and cognitive load for non-technical or interdisciplinary readers:
    1. Abstract word count against venue-specific limits.
    2. Sentence count & sentence length distribution.
    3. Flags run-on sentences (>35 words).
    4. Analyzes opening sentence for intuitive framing vs hyper-dense nested clauses.
    """
    abstract_word_count = len(re.findall(r"\S+", abstract))
    venue_key = (target_venue or "general").strip().lower()
    limits = VENUE_ABSTRACT_LIMITS.get(venue_key, VENUE_ABSTRACT_LIMITS["general"])

    if abstract_word_count < limits["min"]:
        word_count_status = "TOO_SHORT"
    elif abstract_word_count > limits["hard_max"]:
        word_count_status = "OVER_LIMIT"
    elif abstract_word_count > limits["recommended_max"]:
        word_count_status = "OVER_RECOMMENDED"
    else:
        word_count_status = "OPTIMAL"

    # Split sentences cleanly on punctuation
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if s.strip()]
    sentence_lengths = [len(re.findall(r"\b[A-Za-z0-9-]+\b", s)) for s in sentences]

    max_len = max(sentence_lengths) if sentence_lengths else 0
    avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentence_lengths else 0
    runon_sentences = [
        {
            "index": idx + 1,
            "word_count": length,
            "preview": s[:100] + ("..." if len(s) > 100 else ""),
        }
        for idx, (s, length) in enumerate(zip(sentences, sentence_lengths))
        if length > 35
    ]
    has_runon = bool(runon_sentences)

    # Lead sentence readability check
    lead_sentence = sentences[0] if sentences else ""
    lead_words = sentence_lengths[0] if sentence_lengths else 0
    lead_accessible = (lead_words <= 30) and not bool(re.search(r"(\$|\\|\bO\([nN\d]\)|\bsuch that\b)", lead_sentence))

    return {
        "abstract_word_count": abstract_word_count,
        "word_count_status": word_count_status,
        "venue_word_limit": limits,
        "sentence_count": len(sentences),
        "sentence_lengths": sentence_lengths,
        "max_sentence_length": max_len,
        "avg_sentence_length": round(avg_len, 1),
        "has_runon_sentences": has_runon,
        "runon_sentences": runon_sentences,
        "lead_accessible": lead_accessible,
        "lead_sentence": lead_sentence,
    }


BANNED_AI_TROPES = [
    "delve", "delving", "pivotal", "testament", "tapestry", "seamless", "seamlessly",
    "groundbreaking", "beacon", "vital", "crucial", "it is crucial to note",
    "underscores the importance", "revolutionize", "revolutionary"
]

GAP_MARKERS = [
    "however", "remains limited", "remain limited", "fails to", "fail to",
    "bottleneck", "unaddressed", "trade-off", "trade off", "tradeoffs",
    "challenge", "challenging", "deficiency", "vulnerability", "restricted",
    "prohibitive", "inadequate", "shortcoming", "obstacle"
]

ALGORITHM_TERMS = [
    "algorithm", "framework", "formulation", "formulate", "manifold", "convergence",
    "matrix", "tensor", "optimization", "optimize", "architecture", "protocol",
    "scheme", "methodology", "heuristic", "estimator", "pipeline", "decomposition",
    "gradient", "layer", "model", "network"
]


def evaluate_academic_seo(title: str, abstract: str, keywords: List[str]) -> Dict[str, Any]:
    """
    Evaluate academic SEO, discoverability, and visibility tricks:
    1. Keyphrase front-loading in the first 65 characters of the title.
    2. Sweet-spot title length (10–14 words, 70–110 characters).
    3. 3-Beat keyphrase anchoring across abstract (opening, method, conclusion).
    4. Non-redundant keyword vocabulary expansion.
    5. Acronym guard (avoids obscure unsearchable abbreviations).
    """
    title_words = re.findall(r"\b[A-Za-z0-9-]+\b", title)
    title_word_count = len(title_words)
    title_char_count = len(title)

    # 1. Front-loading: Are core topic words placed within first 65 chars?
    first_65 = title[:65].lower()
    title_content_tokens = tokenize(title, remove_stopwords=True)
    first_65_tokens = tokenize(first_65, remove_stopwords=True)
    front_loaded = len(first_65_tokens) >= 2 or (len(title_content_tokens) > 0 and first_65_tokens and first_65_tokens[0] in title_content_tokens[:2])

    # 2. Sweet-spot title length (10–14 words)
    sweet_spot_length = 10 <= title_word_count <= 14

    # 3. 3-Beat Keyphrase Anchoring
    # Extract candidate primary phrases from keywords or title
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if s.strip()]
    anchoring_success = False
    if len(sentences) >= 3:
        lead_text = " ".join(sentences[:2]).lower()
        mid_text = " ".join(sentences[2:-1]).lower() if len(sentences) > 3 else sentences[1].lower()
        tail_text = sentences[-1].lower()

        # Check candidate phrases (title tokens or keywords)
        candidate_stems = [normalize_token(t) for t in title_content_tokens[:4]]
        lead_hits = any(s in lead_text for s in candidate_stems)
        mid_hits = any(s in mid_text for s in candidate_stems)
        tail_hits = any(s in tail_text for s in candidate_stems)
        anchoring_success = lead_hits and mid_hits and tail_hits

    # 4. Acronym check
    raw_title_words = re.findall(r"\b[A-Z0-9]{2,}\b", title)
    common_acronyms = {"AI", "CNN", "RNN", "LLM", "NLP", "GPU", "CPU", "FPGA", "UAV", "IoT", "SNR", "SINR", "MIMO", "RIS", "LEO", "GEO", "IEEE", "ACM"}
    flagged_acronyms = [w for w in raw_title_words if w not in common_acronyms and not w.isdigit()]

    # Collect applied SEO hacks
    applied_hacks: List[str] = []
    if front_loaded:
        applied_hacks.append("Keyphrase front-loaded in first 65 chars of title (safe against snippet truncation)")
    if sweet_spot_length:
        applied_hacks.append("10-14 word sweet-spot title length (statistically optimal citation velocity)")
    if anchoring_success:
        applied_hacks.append("3-Beat keyphrase anchoring (anchored in context lead, method, and conclusion)")
    
    overlap_res = compute_title_keyword_overlap(title, keywords)
    if overlap_res["overlap_ratio"] < 0.35:
        applied_hacks.append("Metadata expansion: keywords provide non-redundant indexing surface area")

    return {
        "front_loaded": front_loaded,
        "title_first_65_chars": title[:65],
        "sweet_spot_length": sweet_spot_length,
        "title_word_count": title_word_count,
        "title_char_count": title_char_count,
        "three_beat_anchoring": anchoring_success,
        "flagged_acronyms": flagged_acronyms,
        "seo_hacks_applied": applied_hacks,
    }


def score_snippet_readability(title: str) -> Dict[str, Any]:
    """Score title snippet readability and SEO front-loading (20 points max)."""
    words = re.findall(r"\b[A-Za-z0-9-]+\b", title)
    word_count = len(words)
    points = 20
    deductions: List[str] = []

    # Optimal length: 10–14 words
    if word_count < 8:
        points -= 8
        deductions.append(f"Title too brief ({word_count} words; target 10-14 words)")
    elif word_count in (8, 9, 15, 16):
        points -= 4
        deductions.append(f"Title slightly off sweet-spot ({word_count} words; target 10-14 words)")
    elif word_count > 16:
        points -= 10
        deductions.append(f"Title too verbose ({word_count} words; causes search truncation)")

    # Title trailing period is bad practice
    if title.strip().endswith("."):
        points -= 3
        deductions.append("Title ends with period")

    # Front loading: first 65 chars
    first_65_tokens = tokenize(title[:65], remove_stopwords=True)
    if len(first_65_tokens) < 2:
        points -= 4
        deductions.append("Primary domain keyphrase not front-loaded in first 65 characters")

    return {
        "points": max(0, points),
        "max_points": 20,
        "word_count": word_count,
        "deductions": deductions,
    }


def score_gap_precision(abstract: str) -> Dict[str, Any]:
    """Score contrastive gap precision and explicit bottleneck definition (20 points max)."""
    abstract_lower = abstract.lower()
    points = 0
    matched_markers = []

    for marker in GAP_MARKERS:
        if re.search(r"\b" + re.escape(marker) + r"\b", abstract_lower):
            matched_markers.append(marker)

    if len(matched_markers) >= 2:
        points = 20
    elif len(matched_markers) == 1:
        points = 18
    else:
        points = 4

    return {
        "points": points,
        "max_points": 20,
        "matched_markers": matched_markers,
    }


def score_algorithmic_specificity(abstract: str) -> Dict[str, Any]:
    """Score concrete algorithmic and architectural formulation (20 points max)."""
    abstract_lower = abstract.lower()
    matched_terms = []

    for term in ALGORITHM_TERMS:
        if re.search(r"\b" + re.escape(term) + r"\b", abstract_lower):
            matched_terms.append(term)

    if len(matched_terms) >= 3:
        points = 20
    elif len(matched_terms) >= 1:
        points = 18
    else:
        points = 5

    return {
        "points": points,
        "max_points": 20,
        "matched_terms": matched_terms,
    }


def score_experimental_quantification(abstract: str) -> Dict[str, Any]:
    """Score empirical quantification, benchmark numbers, units, and metrics (20 points max)."""
    # Look for quantified percentages, metrics, numbers with scientific units
    quant_pattern = r"(\b\d+(\.\d+)?\s*(%|dB|ms|s|ns|FLOPS|bps|kbps|mbps|gbps|fps|ghz|mhz|khz|hz|fold|accuracy|gain|reduction|drift|snr|sinr)\b|\b\d+(\.\d+)?%)"
    matches = re.findall(quant_pattern, abstract, re.IGNORECASE)
    digit_matches = re.findall(r"\b\d+(\.\d+)?\b", abstract)

    points = 0
    if len(matches) >= 2:
        points = 20
    elif len(matches) >= 1 or len(digit_matches) >= 3:
        points = 18
    elif len(digit_matches) >= 1:
        points = 10
    else:
        points = 0

    return {
        "points": points,
        "max_points": 20,
        "quantified_metrics_count": len(matches),
        "raw_digits_count": len(digit_matches),
    }


RE_LARGE_NUMBER_WORDS = re.compile(
    r"\b(?:ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)(?:-[a-z]+)?\b",
    re.IGNORECASE,
)
RE_SMALL_NUMBER_BEFORE_EXP_NOUN = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine)\s+(?:[a-z]+\s+){0,2}"
    r"(?:seeds?|episodes?|trials?|runs?|agents?|uavs?|nodes?|layers?|baselines?|"
    r"datasets?|folds?|epochs?|iterations?|steps?|slots?|metrics?|scenarios?|cases?)\b",
    re.IGNORECASE,
)


def detect_spelled_out_numbers(abstract: str) -> List[str]:
    """
    Detect spelled-out numbers that violate technical/IEEE numerical consistency:
    - Numbers >= 10 (e.g., 'thirty', 'twenty-five') should be digits.
    - Small counts (2-9) before experimental nouns (e.g., 'five training seeds')
      when the abstract already reports quantitative digits.
    """
    found: List[str] = []
    for m in RE_LARGE_NUMBER_WORDS.finditer(abstract):
        found.append(m.group(0))

    has_digits = bool(re.search(r"\b\d+(?:\.\d+)?\b", abstract))
    if has_digits:
        for m in RE_SMALL_NUMBER_BEFORE_EXP_NOUN.finditer(abstract):
            found.append(m.group(1))

    return list(dict.fromkeys(found))


def score_style_and_debiasing(title: str, abstract: str) -> Dict[str, Any]:
    """Score style, accessibility, and strip AI clichés and punctuation flaws (20 points max)."""
    combined_text = f"{title} {abstract}"
    combined_lower = combined_text.lower()
    points = 20
    penalties: List[str] = []
    flagged_words: List[str] = []

    # Em dash penalty (match Unicode em dash '—' or LaTeX '---', not LaTeX en-dash '--')
    if re.search(r"(?<!-)---(?!-)|—", combined_text):
        points -= 8
        penalties.append("em_dash")

    # First-person singular pronoun
    if re.search(r"\b(I|my|myself)\b", combined_text):
        points -= 5
        penalties.append("first_person_singular")

    # Banned AI tropes
    for trope in BANNED_AI_TROPES:
        if re.search(r"\b" + re.escape(trope) + r"\b", combined_lower):
            flagged_words.append(trope)
            points -= 6

    # Accessibility: Check for run-on sentences
    access = evaluate_accessibility(abstract)
    if access["has_runon_sentences"]:
        points -= 4
        penalties.append("runon_sentences")

    # Numerical style consistency: flag spelled-out numbers in quantitative abstracts
    spelled_numbers = detect_spelled_out_numbers(abstract)
    if spelled_numbers:
        points -= 3
        penalties.append("mixed_number_style")

    return {
        "points": max(0, points),
        "max_points": 20,
        "penalties": penalties,
        "flagged_words": flagged_words,
        "spelled_out_numbers": spelled_numbers,
    }


def evaluate_triage_score(title: str, abstract: str, keywords: List[str]) -> Dict[str, Any]:
    """
    Calculate the 100-Point Reviewer Triage Score:
    - Snippet Readability & SEO: 20 pts
    - Gap Precision: 20 pts
    - Algorithmic Specificity: 20 pts
    - Experimental Quantification: 20 pts
    - Style, Accessibility & AI De-biasing: 20 pts
    """
    s_readability = score_snippet_readability(title)
    s_gap = score_gap_precision(abstract)
    s_algo = score_algorithmic_specificity(abstract)
    s_quant = score_experimental_quantification(abstract)
    s_style = score_style_and_debiasing(title, abstract)

    total = (
        s_readability["points"] +
        s_gap["points"] +
        s_algo["points"] +
        s_quant["points"] +
        s_style["points"]
    )

    return {
        "total_score": total,
        "max_score": 100,
        "status": "PASS" if total >= 70 else "REVISE",
        "scores": {
            "snippet_readability": s_readability,
            "gap_precision": s_gap,
            "algorithmic_specificity": s_algo,
            "experimental_quantification": s_quant,
            "style_debiasing": s_style,
        }
    }


def compute_title_similarity(candidate: str, existing: str) -> float:
    """
    Compute string and token-level similarity between a candidate title and an existing title.
    Returns a score between 0.0 and 1.0.
    """
    c_clean = candidate.strip().lower()
    e_clean = existing.strip().lower()

    # Direct character sequence ratio
    seq_ratio = difflib.SequenceMatcher(None, c_clean, e_clean).ratio()

    # Token set Jaccard similarity
    c_tokens = set(tokenize(c_clean, remove_stopwords=True))
    e_tokens = set(tokenize(e_clean, remove_stopwords=True))
    if not c_tokens or not e_tokens:
        jaccard = 0.0
    else:
        intersection = len(c_tokens & e_tokens)
        union = len(c_tokens | e_tokens)
        jaccard = intersection / union if union > 0 else 0.0

    # Weighted blend (60% token overlap, 40% sequence match)
    combined = 0.6 * jaccard + 0.4 * seq_ratio
    return round(combined, 3)


def fetch_json_url(url: str, timeout: float = 3.0) -> Optional[Dict[str, Any]]:
    """Polite HTTP JSON fetcher with User-Agent and timeout."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "SciFi-Shannon-Validator/1.0 (mailto:scifi@research.org)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                data = response.read().decode("utf-8")
                return json.loads(data)
    except Exception:
        return None
    return None


def query_openalex_titles(title: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search OpenAlex for published works matching the candidate title."""
    encoded = urllib.parse.quote(title)
    url = f"https://api.openalex.org/works?search={encoded}&per_page={limit}"
    data = fetch_json_url(url)
    matches: List[Dict[str, Any]] = []
    if data and "results" in data:
        for item in data["results"]:
            t = item.get("title") or ""
            citations = item.get("cited_by_count", 0)
            year = item.get("publication_year")
            venue_info = item.get("primary_location") or {}
            venue_source = venue_info.get("source") or {}
            venue = venue_source.get("display_name") or "Unknown Venue"
            matches.append({
                "title": t,
                "citations": citations,
                "year": year,
                "venue": venue,
            })
    return matches


def query_crossref_titles(title: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fallback search on Crossref for published works matching title."""
    encoded = urllib.parse.quote(title)
    url = f"https://api.crossref.org/works?query.title={encoded}&rows={limit}"
    data = fetch_json_url(url)
    matches: List[Dict[str, Any]] = []
    if data and "message" in data and "items" in data["message"]:
        for item in data["message"]["items"]:
            t_list = item.get("title", [])
            t = t_list[0] if t_list else ""
            citations = item.get("is-referenced-by-count", 0)
            created = item.get("created", {}).get("date-parts", [[None]])[0][0]
            container = item.get("container-title", [])
            venue = container[0] if container else "Unknown Venue"
            matches.append({
                "title": t,
                "citations": citations,
                "year": created,
                "venue": venue,
            })
    return matches


def check_title_collision(title: str, live: bool = False) -> Dict[str, Any]:
    """
    Check candidate title against published papers on OpenAlex and Crossref.
    Categorizes risk:
    - LOW RISK (<0.60)
    - MODERATE OVERLAP (0.60–0.85)
    - HIGH COLLISION (>0.85)
    """
    if not live:
        return {
            "status": "SKIPPED_OFFLINE",
            "risk_level": "UNKNOWN",
            "max_similarity": 0.0,
            "matches": [],
        }

    raw_matches = query_openalex_titles(title)
    if not raw_matches:
        raw_matches = query_crossref_titles(title)

    scored_matches: List[Dict[str, Any]] = []
    max_sim = 0.0

    for match in raw_matches:
        ext_title = match["title"]
        sim = compute_title_similarity(title, ext_title)
        if sim > max_sim:
            max_sim = sim
        scored_matches.append({
            "title": ext_title,
            "similarity": sim,
            "year": match.get("year"),
            "citations": match.get("citations"),
            "venue": match.get("venue"),
        })

    scored_matches.sort(key=lambda x: x["similarity"], reverse=True)

    if max_sim > 0.85:
        risk_level = "HIGH COLLISION"
    elif max_sim >= 0.60:
        risk_level = "MODERATE OVERLAP"
    else:
        risk_level = "LOW RISK"

    return {
        "status": "LIVE_OK",
        "risk_level": risk_level,
        "max_similarity": max_sim,
        "matches": scored_matches[:5],
    }


def check_keyword_relevance(keywords: List[str], live: bool = False) -> Dict[str, Any]:
    """
    Query OpenAlex for candidate keywords to verify subfield hit relevance.
    """
    if not live:
        return {"status": "SKIPPED_OFFLINE", "keyword_insights": {}}

    insights: Dict[str, Any] = {}
    for kw in keywords[:4]:
        encoded = urllib.parse.quote(kw)
        url = f"https://api.openalex.org/works?search={encoded}&per_page=3"
        data = fetch_json_url(url)
        venues: List[str] = []
        if data and "results" in data:
            for item in data["results"]:
                loc = item.get("primary_location") or {}
                src = loc.get("source") or {}
                vname = src.get("display_name")
                if vname and vname not in venues:
                    venues.append(vname)
        insights[kw] = {
            "mapped_venues": venues,
            "subfield_confirmed": len(venues) > 0,
        }

    return {
        "status": "LIVE_OK",
        "keyword_insights": insights,
    }


def generate_diagnostic_report(evaluation: Dict[str, Any]) -> str:
    """Format evaluation data into an authoritative, publication-grade terminal report."""
    triage = evaluation["triage_score"]
    seo = evaluation["seo"]
    access = evaluation["accessibility"]
    overlap = evaluation["overlap"]
    density = evaluation["density"]
    collision = evaluation["collision"]

    lines = []
    lines.append("=" * 78)
    lines.append("🔬 SHANNON MANUSCRIPT AUDIT: TITLE, ABSTRACT & SEO REPORT")
    lines.append("=" * 78)

    # 1. Reviewer Triage Scorecard
    status_icon = "✅" if triage["status"] == "PASS" else "⚠️"
    lines.append(f"\n{status_icon} REVIEWER TRIAGE SCORECARD: {triage['total_score']} / {triage['max_score']} [{triage['status']}]")
    lines.append("-" * 78)
    scores = triage["scores"]
    lines.append(f"  • Snippet Readability & Title SEO : {scores['snippet_readability']['points']:2d} / 20")
    for d in scores['snippet_readability'].get('deductions', []):
        lines.append(f"    - Penalty: {d}")
    lines.append(f"  • Gap Precision & Bottleneck      : {scores['gap_precision']['points']:2d} / 20")
    if scores['gap_precision'].get('matched_markers'):
        lines.append(f"    - Markers: {', '.join(scores['gap_precision']['matched_markers'])}")
    lines.append(f"  • Algorithmic Specificity         : {scores['algorithmic_specificity']['points']:2d} / 20")
    if scores['algorithmic_specificity'].get('matched_terms'):
        lines.append(f"    - Terms  : {', '.join(scores['algorithmic_specificity']['matched_terms'])}")
    lines.append(f"  • Experimental Quantification     : {scores['experimental_quantification']['points']:2d} / 20")
    lines.append(f"    - Metrics: {scores['experimental_quantification']['quantified_metrics_count']} quantified metrics, {scores['experimental_quantification']['raw_digits_count']} digits")
    lines.append(f"  • Style, Accessibility & De-biasing: {scores['style_debiasing']['points']:2d} / 20")
    for p in scores['style_debiasing'].get('penalties', []):
        lines.append(f"    - Flag   : {p}")
    for f in scores['style_debiasing'].get('flagged_words', []):
        lines.append(f"    - Trope  : '{f}'")
    if scores['style_debiasing'].get('spelled_out_numbers'):
        nums = ", ".join(f"'{n}'" for n in scores['style_debiasing']['spelled_out_numbers'])
        lines.append(f"    - Numbers: Use digits instead of {nums} for numerical consistency")

    # 2. Academic SEO & Discoverability
    lines.append("\n📈 ACADEMIC SEO & DISCOVERABILITY HACKS")
    lines.append("-" * 78)
    lines.append(f"  • First 65 Chars Truncation Check: \"{seo['title_first_65_chars']}\"")
    lines.append(f"    - Front-Loaded Keyphrase  : {'[PASS]' if seo['front_loaded'] else '[WARN - keyphrase not in first 65 chars]'}")
    lines.append(f"  • Title Length Sweet-Spot   : {seo['title_word_count']} words ({seo['title_char_count']} chars) {'[PASS]' if seo['sweet_spot_length'] else '[WARN - optimal is 10-14 words]'}")
    lines.append(f"  • 3-Beat Keyphrase Anchoring: {'[PASS]' if seo['three_beat_anchoring'] else '[NOTICE - anchor core phrase in lead, method, and conclusion]'}")
    if seo.get("flagged_acronyms"):
        lines.append(f"  • Title Acronym Trap Alert : {', '.join(seo['flagged_acronyms'])} (Ensure defined/searchable)")
    if seo.get("seo_hacks_applied"):
        lines.append("  • Active SEO Visibility Hacks:")
        for h in seo["seo_hacks_applied"]:
            lines.append(f"    ✓ {h}")

    # 3. Dual-Audience Accessibility
    lines.append("\n👥 DUAL-AUDIENCE ACCESSIBILITY & COGNITIVE LOAD")
    lines.append("-" * 78)
    wc = access.get("abstract_word_count")
    wc_status = access.get("word_count_status", "OPTIMAL")
    venue_label = access.get("venue_word_limit", {}).get("label", "General (150-220w)")
    if wc is not None:
        lines.append(f"  • Abstract Word Count       : {wc} words [{wc_status}] ({venue_label})")
    lines.append(f"  • Sentence Count            : {access['sentence_count']} sentences (avg {access['avg_sentence_length']} words/sentence)")
    lines.append(f"  • Maximum Sentence Length   : {access['max_sentence_length']} words {'[WARN >35]' if access['has_runon_sentences'] else '[OPTIMAL]'}")
    for ro in access.get("runon_sentences", []):
        lines.append(f"    - Sentence {ro['index']} ({ro['word_count']}w): \"{ro['preview']}\"")
    lines.append(f"  • Lead Sentence Clarity     : {'[ACCESSIBLE]' if access['lead_accessible'] else '[DENSE - consider simplifying opening hook]'}")

    # 4. Metadata Vocabulary Expansion & Density
    lines.append("\n🏷️ KEYWORD METADATA EXPANSION & ABSTRACT DENSITY")
    lines.append("-" * 78)
    lines.append(f"  • Non-Redundancy Overlap    : {overlap['overlap_ratio']*100:.1f}% title overlap ({overlap['distinct_keywords_count']}/{overlap['total_keywords']} distinct keywords)")
    if overlap["overlapping_words"]:
        lines.append(f"    - Duplicated Title Words  : {', '.join(overlap['overlapping_words'])} (Replace to expand search footprint)")
    lines.append("  • Abstract Keyphrase Density:")
    for kw, stats in density.get("densities", {}).items():
        status_label = f"[{stats['status']}]"
        lines.append(f"    - {kw:<28}: {stats['count']} occurrences {status_label}")

    # 5. Live Search Diagnostics
    if collision.get("status") == "LIVE_OK":
        lines.append("\n🌐 LIVE SEARCH & TITLE COLLISION DIAGNOSTICS")
        lines.append("-" * 78)
        lines.append(f"  • Title Collision Risk      : {collision['risk_level']} (max similarity {collision['max_similarity']:.2f})")
        if collision.get("matches"):
            lines.append("    Top Matching Works in Literature:")
            for m in collision["matches"][:3]:
                lines.append(f"      * \"{m['title']}\" ({m.get('year')}) — {m.get('venue')}")

    lines.append("=" * 78)
    return "\n".join(lines)


def run_cli(args: Optional[List[str]] = None) -> int:
    """Execute the Shannon command-line validator."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="test_keywords.py",
        description="Shannon: Academic Title, Abstract & Keyword Optimization Engine"
    )
    parser.add_argument("--title", required=True, help="Draft manuscript title")
    parser.add_argument("--abstract", required=True, help="Draft manuscript abstract")
    parser.add_argument("--keywords", required=True, help="Comma-separated candidate author keywords")
    parser.add_argument("--target-venue", default=None, help="Target publisher or venue (e.g. ieee, elsevier, springer)")
    parser.add_argument("--live", action="store_true", help="Perform live search against OpenAlex/Crossref")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")

    parsed = parser.parse_args(args)

    raw_keywords = [k.strip() for k in parsed.keywords.split(",") if k.strip()]

    # Run evaluations
    triage = evaluate_triage_score(parsed.title, parsed.abstract, raw_keywords)
    seo = evaluate_academic_seo(parsed.title, parsed.abstract, raw_keywords)
    accessibility = evaluate_accessibility(parsed.abstract, target_venue=parsed.target_venue)
    overlap = compute_title_keyword_overlap(parsed.title, raw_keywords)
    density = compute_abstract_keyword_density(parsed.abstract, raw_keywords)
    collision = check_title_collision(parsed.title, live=parsed.live)
    relevance = check_keyword_relevance(raw_keywords, live=parsed.live)

    full_evaluation = {
        "title": parsed.title,
        "abstract": parsed.abstract,
        "target_venue": parsed.target_venue,
        "triage_score": triage,
        "seo": seo,
        "accessibility": accessibility,
        "overlap": overlap,
        "density": density,
        "collision": collision,
        "relevance": relevance,
    }

    if parsed.json:
        print(json.dumps(full_evaluation, indent=2))
    else:
        report = generate_diagnostic_report(full_evaluation)
        print(report)

    # Return exit code: 0 if triage score >= 70, else 1
    return 0 if triage["total_score"] >= 70 else 1


def main() -> int:
    """Entry point for CLI execution."""
    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())



