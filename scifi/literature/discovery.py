"""
Academic Query Expansion & Multi-Signal Paper Reranking.

Improves literature discovery recall without web scraping by expanding queries
with domain synonyms/acronyms and reranking candidates using BM25-style lexical
scoring blended with citation impact and recency.
"""

from __future__ import annotations

import math
import re
from collections import Counter

from scifi.literature.models import PaperRecord

_SYNONYM_MAP: dict[str, tuple[str, ...]] = {
    "llm": ("large language model", "foundation model"),
    "rl": ("reinforcement learning", "policy optimization"),
    "gnn": ("graph neural network", "message passing neural network"),
    "vit": ("vision transformer",),
    "rag": ("retrieval augmented generation", "retrieval-augmented generation"),
    "ris": ("reconfigurable intelligent surface", "intelligent reflecting surface"),
    "mimo": ("multiple-input multiple-output", "massive mimo"),
    "csi": ("channel state information",),
    "ood": ("out-of-distribution", "domain generalization", "distribution shift"),
    "federated learning": ("decentralized learning", "distributed optimization"),
    "quantization": ("low-bit", "post-training quantization", "model compression"),
    "pruning": ("sparsification", "model compression"),
    "alignment": ("rlhf", "preference optimization", "safety alignment"),
    "hallucination": ("factuality", "grounding", "confabulation"),
}

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if len(t) > 1]


def expand_academic_query(query: str, max_variants: int = 4) -> list[str]:
    """
    Generate expanded search query variants from an initial academic query.
    Always includes the original query first.
    """
    clean = re.sub(r"\s+", " ", query).strip()
    if not clean:
        return []

    variants: list[str] = [clean]
    lower = clean.lower()

    for key, synonyms in _SYNONYM_MAP.items():
        pattern = rf"\b{re.escape(key)}\b"
        if re.search(pattern, lower):
            for syn in synonyms:
                expanded = re.sub(pattern, syn, lower, count=1)
                if expanded not in [v.lower() for v in variants]:
                    variants.append(expanded)
                    if len(variants) >= max_variants:
                        return variants
        else:
            for syn in synonyms:
                if syn in lower:
                    contracted = lower.replace(syn, key, 1)
                    if contracted not in [v.lower() for v in variants]:
                        variants.append(contracted)
                        if len(variants) >= max_variants:
                            return variants

    return variants[:max_variants]


def rerank_papers(
    query: str,
    papers: list[PaperRecord],
    *,
    lexical_weight: float = 0.65,
    impact_weight: float = 0.20,
    recency_weight: float = 0.15,
    current_year: int = 2026,
) -> list[PaperRecord]:
    """
    Rerank PaperRecord candidates using BM25-style lexical relevance over
    title + abstract, blended with log citation impact and recency.
    """
    if not papers:
        return []

    expanded = expand_academic_query(query, max_variants=3)
    query_tokens = list(dict.fromkeys(tok for q in expanded for tok in _tokenize(q)))
    if not query_tokens:
        return list(papers)

    docs_tokens: list[list[str]] = []
    for p in papers:
        text = f"{p.title} {p.title} {p.abstract or ''}"
        docs_tokens.append(_tokenize(text))

    n_docs = len(docs_tokens)
    avg_dl = sum(len(d) for d in docs_tokens) / max(n_docs, 1)
    df: Counter[str] = Counter()
    for d in docs_tokens:
        df.update(set(d))

    k1 = 1.5
    b = 0.75
    raw_bm25: list[float] = []
    for d in docs_tokens:
        tf = Counter(d)
        dl = len(d) or 1
        score = 0.0
        for term in query_tokens:
            freq = tf.get(term, 0)
            if freq == 0:
                continue
            idf = math.log(1.0 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
            denom = freq + k1 * (1.0 - b + b * (dl / max(avg_dl, 1.0)))
            score += idf * (freq * (k1 + 1.0)) / max(denom, 1e-9)
        raw_bm25.append(score)

    max_bm25 = max(raw_bm25) if raw_bm25 else 1.0
    max_bm25 = max(max_bm25, 1e-9)
    max_cit = max((math.log1p(max(0, p.citation_count or 0)) for p in papers), default=1.0)
    max_cit = max(max_cit, 1e-9)

    scored: list[tuple[float, int, PaperRecord]] = []
    for idx, p in enumerate(papers):
        lex_norm = raw_bm25[idx] / max_bm25
        cit_norm = math.log1p(max(0, p.citation_count or 0)) / max_cit
        if p.year is not None:
            age = max(0, current_year - p.year)
            rec_norm = math.exp(-0.12 * age)
        else:
            rec_norm = 0.2
        total = lexical_weight * lex_norm + impact_weight * cit_norm + recency_weight * rec_norm
        scored.append((total, idx, p))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in scored]
