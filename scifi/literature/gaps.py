"""
4-Stage Research Gap Extraction and Corroboration Engine.

Mines technical limitation claims from reconstructed abstracts, full-text sections
(System Model/Methodology, Limitations/Discussion), and inbound citation contexts,
attributes claims to reporting papers, classifies canonical gap categories, and corroborates
findings across independent sources.
"""

from __future__ import annotations

import re
import uuid
from typing import Optional

from scifi.literature.models import (
    CitationContextRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperRecord,
)

# 5 Canonical Research Gap Categories
GAP_TYPES = (
    "computational_complexity",
    "unstated_assumption",
    "empirical_limitation",
    "generalization_bound",
    "unresolved_problem",
)

__all__ = ["GapExtractor", "GAP_TYPES"]

# Patterns and keywords for Stage 2 classification
_CATEGORY_PATTERNS: dict[str, list[tuple[str, int]]] = {
    "computational_complexity": [
        (r"\bo\([n\d\^\*\|\+\-\s]+\)", 4),
        (r"\bquadratic(?:ally)?\b", 3),
        (r"\bcubic\b", 3),
        (r"\bexponential(?:ly)?\b", 3),
        (r"\bpolynomial\b", 2),
        (r"\bcomputational(?:ly)?\s+(?:complexity|expensive|heavy|demanding|prohibitive|cost|overhead|bottleneck)\b", 4),
        (r"\btime\s+complexity\b", 4),
        (r"\bspace\s+complexity\b", 4),
        (r"\bmemory\s+(?:complexity|overhead|footprint|bound|consumption|limit|intensive|bottleneck)\b", 4),
        (r"\bcomputational\s+complexity\b", 4),
        (r"\bcomplexity\b", 2),
        (r"\blatency\b", 3),
        (r"\bruntime\b", 2),
        (r"\boverhead\b", 2),
        (r"\bprohibitive(?:ly)?\b", 3),
        (r"\bexpensive\b", 2),
        (r"\bbottleneck(?:s)?\b", 3),
        (r"\bscalab(?:le|ility)\b", 2),
        (r"\bscales?\s+(?:poorly|as|quadratically|exponentially)\b", 3),
        (r"\bhigh\s+(?:overhead|cost|latency|memory|compute)\b", 3),
    ],
    "unstated_assumption": [
        (r"\bunstated\s+assumption(?:s)?\b", 5),
        (r"\brelies?\s+on\s+(?:the\s+)?assumption\b", 4),
        (r"\bassum(?:es?|ing|ption|ptions)\b", 3),
        (r"\bchannel\s+state\s+information\b", 4),
        (r"\bchannel\s+(?:state|knowledge)\b", 4),
        (r"\bstatic\s+(?:topology|network|graph|environment|setting)\b", 4),
        (r"\bideal(?:ized)?\b", 3),
        (r"\bconvex(?:ity)?\b", 3),
        (r"\bsynchron(?:ous|y|ization)\b", 3),
        (r"\bi\.?i\.?d\.?\b", 3),
        (r"\blinear(?:ity)?\b", 2),
        (r"\bperfect\s+(?:knowledge|state|channel|information|synchronization)\b", 4),
        (r"\bfull\s+(?:state|knowledge|information|channel)\b", 3),
        (r"\brequires?\s+full\b", 3),
        (r"\bonly\s+holds?\s+(?:in|when|under|if)\b", 3),
        (r"\bunder\s+(?:the\s+)?(?:assumption|ideal)\b", 3),
    ],
    "empirical_limitation": [
        (r"\bfails?\s+to\b", 3),
        (r"\bfailure\s+to\b", 3),
        (r"\bdegrades?\s+(?:under|significantly|drastically|rapidly)?\b", 3),
        (r"\bdegradation\b", 3),
        (r"\blimited\s+(?:to|evaluation|experiments?|benchmark|scope|applicability)\b", 3),
        (r"\bnarrow\s+(?:evaluation|benchmark|scope)\b", 3),
        (r"\btoy\s+(?:benchmark|dataset|example|environment|setting|task)s?\b", 4),
        (r"\bsmall[- ]scale\b", 3),
        (r"\bsynthetic\s+(?:data|dataset|benchmark|experiments?|only)\b", 3),
        (r"\bevaluated\s+only\s+on\b", 3),
        (r"\bonly\s+tested\s+on\b", 3),
        (r"\bunproven\b", 3),
        (r"\bstruggles?\s+(?:to|with)\b", 3),
        (r"\bpoor\s+(?:performance|accuracy|convergence)\b", 3),
        (r"\blower\s+(?:accuracy|performance)\b", 2),
        (r"\bunderperform(?:s|ed|ing)?\b", 3),
        (r"\bdrawback(?:s)?\b", 2),
        (r"\bshortcoming(?:s)?\b", 2),
    ],
    "generalization_bound": [
        (r"\bout[- ]of[- ]distribution\b", 4),
        (r"\bood\b", 4),
        (r"\bdomain\s+shift(?:s)?\b", 4),
        (r"\bdistribution(?:al)?\s+shift(?:s)?\b", 4),
        (r"\bcovariate\s+shift\b", 4),
        (r"\blacks?\s+robustness\b", 4),
        (r"\bnot\s+robust\b", 3),
        (r"\brobust(?:ness)?\b", 2),
        (r"\badversarial\b", 3),
        (r"\bvulnerable\s+to\b", 3),
        (r"\bgeneraliz(?:ation|e|ing)\s+(?:bound|gap|error|poorly|fails?)\b", 4),
        (r"\bfails?\s+to\s+generalize\b", 4),
        (r"\bunseen\s+(?:domain|environment|setting|data|distribution|task)s?\b", 3),
        (r"\btransfer(?:ability)?\b", 3),
        (r"\bzero[- ]shot\s+(?:degradation|performance|failure)\b", 3),
    ],
    "unresolved_problem": [
        (r"\bopen\s+(?:problem|question|challenge|issue)s?\b", 4),
        (r"\bunresolved\b", 4),
        (r"\bfuture\s+(?:work|research|directions?|investigation)\b", 4),
        (r"\bleft\s+(?:for|to|as)\s+future\b", 4),
        (r"\bremains?\s+(?:an?\s+)?(?:open|unresolved|challenge|unclear|unexplored|missing)\b", 4),
        (r"\bunexplored\b", 3),
        (r"\bnot\s+yet\s+(?:solved|addressed|resolved|understood)\b", 3),
        (r"\bstill\s+(?:missing|open|unresolved|challenging)\b", 3),
        (r"\bfundamental\s+challenge\b", 3),
    ],
}

# Contrastive markers for abstract sentence mining
_CONTRASTIVE_MARKERS = [
    r"\bhowever\b",
    r"\balthough\b",
    r"\bwhile\b",
    r"\bnonetheless\b",
    r"\bnevertheless\b",
    r"\byet\b",
    r"\bdespite\b",
    r"\bin contrast\b",
    r"\bon the other hand\b",
    r"\bunlike\b",
    r"\bwhereas\b",
    r"\blimited to\b",
    r"\blimitation(?:s)?\b",
    r"\bbottleneck(?:s)?\b",
    r"\bassumption(?:s)?\b",
    r"\bassumes?\b",
    r"\bcost(?:s)?\b",
    r"\bexpensive\b",
    r"\bprohibitive\b",
    r"\bcomplexity\b",
    r"\bfails?\s+to\b",
    r"\bdegrades?\b",
    r"\bopen problem\b",
    r"\bfuture work\b",
    r"\bgeneralization\b",
    r"\brobustness\b",
]

# Resolution and contradiction markers for Stage 4
_CONTRADICTION_PATTERNS = [
    r"\bresolv(?:es?|ed|ing)\b",
    r"\bsolv(?:es?|ed|ing)\b",
    r"\bovercom(?:es?|ing)\b",
    r"\bmitigat(?:es?|ed|ing)\b",
    r"\baddress(?:es?|ed|ing)\s+(?:the\s+)?(?:limitation|bottleneck|issue|problem|overhead)\b",
    r"\bremed(?:ies|y|ied)\b",
    r"\brefut(?:es?|ed|ing)\b",
    r"\bdisprov(?:es?|ed|ing)\b",
    r"\bcontradict(?:s|ed|ing)?\b",
    r"\bwithout\s+(?:requiring|assuming|incurring)\b",
    r"\bno\s+longer\s+suffers?\b",
    r"\beliminat(?:es?|ed|ing)\s+(?:the\s+)?(?:need|overhead|requirement|bottleneck)\b",
]

# Stopwords for clustering key token extraction
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "are", "was", "were", "been", "being",
    "have", "has", "had", "does", "did", "doing", "would", "should", "could", "ought",
    "our", "their", "its", "your", "them", "these", "those", "which", "what", "where", "when",
    "who", "whom", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other",
    "some", "such", "than", "too", "very", "can", "will", "just", "about", "into", "through",
    "during", "before", "after", "above", "below", "between", "under", "again", "further",
    "then", "once", "here", "there", "only", "same", "also",
    "however", "although", "while", "unlike", "whereas", "nonetheless", "nevertheless",
    "method", "methods", "paper", "papers", "approach", "approaches", "algorithm", "algorithms",
    "proposed", "model", "models", "system", "systems", "work", "works",
    "author", "authors", "result", "results", "technique", "techniques", "framework",
    "study", "show", "shows", "shown", "performance", "presents", "proposes", "using", "used",
    "based", "well", "new", "via", "due", "first", "second", "one", "two", "three",
    "limitation", "limitations", "limited", "gap", "gaps", "problem", "problems",
    "challenge", "challenges", "issue", "issues",
    "suffer", "suffers", "exhibit", "exhibits", "lead", "leads", "cause", "causes",
}


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences while protecting common academic abbreviations."""
    if not text or not text.strip():
        return []

    cleaned = text.strip()
    abbreviations = [
        (r"\be\.g\.", "e_DOT_g_DOT_"),
        (r"\bi\.e\.", "i_DOT_e_DOT_"),
        (r"\bet al\.", "et al_DOT_"),
        (r"\bFig\.", "Fig_DOT_"),
        (r"\bEq\.", "Eq_DOT_"),
        (r"\bvs\.", "vs_DOT_"),
        (r"\bi\.i\.d\.", "i_DOT_i_DOT_d_DOT_"),
    ]
    for pattern, replacement in abbreviations:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)

    sentences = []
    for part in parts:
        restored = part
        for _, replacement in abbreviations:
            orig = replacement.replace("_DOT_", ".")
            restored = restored.replace(replacement, orig)
        trimmed = restored.strip()
        if trimmed:
            sentences.append(trimmed)

    return sentences


def _classify_gap_sentence(sentence: str) -> tuple[Optional[str], int]:
    """
    Score the sentence against the 5 canonical gap categories.
    Returns (best_category, score).
    """
    sentence_lower = sentence.lower()
    scores: dict[str, int] = {cat: 0 for cat in GAP_TYPES}

    for cat, patterns in _CATEGORY_PATTERNS.items():
        for pat, weight in patterns:
            if re.search(pat, sentence_lower):
                scores[cat] += weight

    best_cat = max(scores, key=lambda k: scores[k])
    best_score = scores[best_cat]
    if best_score > 0:
        return best_cat, best_score
    return None, 0


def _generate_claim_summary(sentence: str, gap_type: str) -> str:
    """Produce a concise, human-readable claim summary from the sentence."""
    text = re.sub(r"\[[\d,\s-]+\]", "", sentence).strip()

    text = re.sub(
        r"^(?:however|although|while|nevertheless|nonetheless|yet|in addition|furthermore|moreover)[,\s]+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip()

    text = re.sub(r"^(?:while|although)\s+[^,]+,\s*", "", text, flags=re.IGNORECASE).strip()

    if text:
        text = text[0].upper() + text[1:]

    return text.rstrip(".")


def _is_contradiction(text: str) -> bool:
    """Check if citation text resolves, refutes, or contradicts a prior limitation."""
    text_lower = text.lower()
    return any(re.search(pat, text_lower) for pat in _CONTRADICTION_PATTERNS)


def _extract_key_tokens(text: str) -> set[str]:
    """Extract domain-specific tokens for clustering."""
    words = re.findall(r"[a-zA-Z]{3,}", text.lower())
    tokens = set()
    for w in words:
        norm = w[:-1] if (w.endswith("s") and not w.endswith("ss")) else w
        if norm not in _STOPWORDS:
            tokens.add(norm)
    return tokens


class GapExtractor:
    """
    Multi-stage evidence-based research gap extractor.
    Mines limitations and system assumptions from abstracts, full-text sections,
    and citation contexts, classifies claims, and corroborates findings across sources.
    """

    def extract_abstract_gaps(
        self, paper: PaperRecord
    ) -> list[tuple[EvidenceRecord, PaperGapRecord]]:
        """
        Stage 1 & 2: Extract self-reported technical limitations from a paper's abstract.
        Filters sentences containing contrastive markers and classifies into canonical categories.
        """
        if not paper.abstract or not paper.abstract.strip():
            return []

        sentences = _split_into_sentences(paper.abstract)
        results: list[tuple[EvidenceRecord, PaperGapRecord]] = []

        for idx, sentence in enumerate(sentences):
            sentence_lower = sentence.lower()
            has_contrastive = any(re.search(pat, sentence_lower) for pat in _CONTRASTIVE_MARKERS)
            gap_type, score = _classify_gap_sentence(sentence)

            if has_contrastive and gap_type is not None:
                ev_id = f"ev-{uuid.uuid4().hex[:12]}"
                gap_id = f"gap-{uuid.uuid4().hex[:12]}"

                evidence = EvidenceRecord(
                    id=ev_id,
                    paper_id=paper.id,
                    evidence_type="abstract_limitation",
                    extracted_text=sentence,
                    extraction_method="contrastive_sentence_mining",
                    reporting_paper_id=None,
                    source_section="Abstract",
                    source_location=f"sentence_{idx + 1}",
                    confidence=0.90,
                )

                gap = PaperGapRecord(
                    id=gap_id,
                    paper_id=paper.id,
                    gap_type=gap_type,
                    claim_summary=_generate_claim_summary(sentence, gap_type),
                    primary_evidence_id=ev_id,
                    verification_status="candidate",
                    corroborating_count=0,
                    contradicting_count=0,
                )

                results.append((evidence, gap))

        return results

    def extract_fulltext_gaps(
        self,
        paper: PaperRecord,
        sections: dict[str, str],
    ) -> list[tuple[EvidenceRecord, PaperGapRecord]]:
        """
        Extract deep technical limitations and system assumptions from full-text paper sections.
        Mines:
        1. 'system_model_or_method': Mathematical assumptions, idealized states, and complexity bottlenecks.
        2. 'limitations_and_conclusion': Explicit author concessions, boundary conditions, and unresolved problems.
        """
        if not sections:
            return []

        results: list[tuple[EvidenceRecord, PaperGapRecord]] = []

        # 1. System Model & Methodology Mining
        system_text = sections.get("system_model_or_method") or ""
        if system_text and system_text.strip():
            sentences = _split_into_sentences(system_text)
            for idx, sentence in enumerate(sentences):
                sentence_lower = sentence.lower()
                gap_type, score = _classify_gap_sentence(sentence)

                has_assumption = bool(
                    re.search(
                        r"\b(?:we\s+)?assume\b|\bassuming\b|\bunder\s+(?:the\s+)?assumption\b|"
                        r"\bidealized\b|\bperfect\s+(?:knowledge|state|csi|channel|information|synchronization)\b|"
                        r"\bstatic\s+(?:topology|network|graph|environment)\b|\bconvexity\b|\bi\.?i\.?d\.?\b|"
                        r"\bworst-case\s+complexity\b|\bcomputational\s+(?:cost|complexity|overhead|bottleneck)\b|"
                        r"\bo\([n\d\^\*\|\+\-\s]+\)",
                        sentence_lower,
                    )
                )

                if has_assumption or (gap_type in ("unstated_assumption", "computational_complexity") and score >= 2):
                    if not gap_type:
                        if re.search(r"\bo\([n\d\^\*\|\+\-\s]+\)|\bcomplexity\b|\bcomputational\b", sentence_lower):
                            gap_type = "computational_complexity"
                        else:
                            gap_type = "unstated_assumption"

                    ev_id = f"ev-{uuid.uuid4().hex[:12]}"
                    gap_id = f"gap-{uuid.uuid4().hex[:12]}"

                    ev_type = (
                        "methodology_complexity"
                        if gap_type == "computational_complexity"
                        else "system_model_assumption"
                    )

                    evidence = EvidenceRecord(
                        id=ev_id,
                        paper_id=paper.id,
                        evidence_type=ev_type,
                        extracted_text=sentence,
                        extraction_method="system_model_fulltext_mining",
                        reporting_paper_id=None,
                        source_section="System Model / Methodology",
                        source_location=f"sentence_{idx + 1}",
                        confidence=0.92,
                    )

                    gap = PaperGapRecord(
                        id=gap_id,
                        paper_id=paper.id,
                        gap_type=gap_type,
                        claim_summary=_generate_claim_summary(sentence, gap_type),
                        primary_evidence_id=ev_id,
                        verification_status="candidate",
                        corroborating_count=0,
                        contradicting_count=0,
                    )

                    results.append((evidence, gap))

        # 2. Limitations, Discussion & Conclusion Mining
        limitations_text = sections.get("limitations_and_conclusion") or ""
        if limitations_text and limitations_text.strip():
            sentences = _split_into_sentences(limitations_text)
            for idx, sentence in enumerate(sentences):
                sentence_lower = sentence.lower()
                gap_type, score = _classify_gap_sentence(sentence)

                has_limitation_signal = (
                    any(re.search(pat, sentence_lower) for pat in _CONTRASTIVE_MARKERS)
                    or bool(
                        re.search(
                            r"\b(?:a\s+)?limitation\s+of\b|\bdoes\s+not\s+(?:account|consider|scale|generalize)\b|"
                            r"\bremains?\s+(?:an?\s+)?(?:open|unresolved|future)\b|\bfuture\s+work\b|"
                            r"\bfails?\s+to\b|\bdegrades?\b|\btoy\s+benchmark\b|\bonly\s+tested\b|"
                            r"\bdrawback\b|\bshortcoming\b",
                            sentence_lower,
                        )
                    )
                )

                if has_limitation_signal or (gap_type is not None and score >= 2):
                    if gap_type is None:
                        if re.search(r"\b(?:fail|degrade|limit|toy|small|poor|drawback|shortcoming)\b", sentence_lower):
                            gap_type = "empirical_limitation"
                        else:
                            gap_type = "unresolved_problem"

                    ev_id = f"ev-{uuid.uuid4().hex[:12]}"
                    gap_id = f"gap-{uuid.uuid4().hex[:12]}"

                    evidence = EvidenceRecord(
                        id=ev_id,
                        paper_id=paper.id,
                        evidence_type="fulltext_limitation",
                        extracted_text=sentence,
                        extraction_method="limitations_section_mining",
                        reporting_paper_id=None,
                        source_section="Limitations & Conclusion",
                        source_location=f"sentence_{idx + 1}",
                        confidence=0.95,
                    )

                    gap = PaperGapRecord(
                        id=gap_id,
                        paper_id=paper.id,
                        gap_type=gap_type,
                        claim_summary=_generate_claim_summary(sentence, gap_type),
                        primary_evidence_id=ev_id,
                        verification_status="candidate",
                        corroborating_count=0,
                        contradicting_count=0,
                    )

                    results.append((evidence, gap))

        return results

    def extract_citation_context_gaps(
        self,
        target_paper: PaperRecord,
        contexts: list[CitationContextRecord],
    ) -> list[tuple[EvidenceRecord, PaperGapRecord]]:
        """
        Stage 1, 2 & 3: Extract technical limitations from inbound citation contexts.
        Attributes claims to the citing source paper (reporting_paper_id).
        """
        if not contexts:
            return []

        results: list[tuple[EvidenceRecord, PaperGapRecord]] = []

        for context in contexts:
            if context.target_paper_id and context.target_paper_id != target_paper.id:
                continue

            sentences = _split_into_sentences(context.context_text)
            for idx, sentence in enumerate(sentences):
                sentence_lower = sentence.lower()
                has_signal = any(re.search(pat, sentence_lower) for pat in _CONTRASTIVE_MARKERS)
                gap_type, score = _classify_gap_sentence(sentence)

                if has_signal and gap_type is not None:
                    ev_id = f"ev-{uuid.uuid4().hex[:12]}"
                    gap_id = f"gap-{uuid.uuid4().hex[:12]}"

                    evidence = EvidenceRecord(
                        id=ev_id,
                        paper_id=target_paper.id,
                        evidence_type="citation_context",
                        extracted_text=sentence,
                        extraction_method="citation_context_mining",
                        reporting_paper_id=context.source_paper_id,
                        source_section=context.section_name or "Related Work",
                        source_location=f"sentence_{idx + 1}",
                        confidence=0.85,
                    )

                    gap = PaperGapRecord(
                        id=gap_id,
                        paper_id=target_paper.id,
                        gap_type=gap_type,
                        claim_summary=_generate_claim_summary(sentence, gap_type),
                        primary_evidence_id=ev_id,
                        verification_status="candidate",
                        corroborating_count=0,
                        contradicting_count=0,
                    )

                    results.append((evidence, gap))

        return results

    def corroborate_gaps(
        self, gaps_with_evidence: list[tuple[EvidenceRecord, PaperGapRecord]]
    ) -> list[tuple[EvidenceRecord, PaperGapRecord]]:
        """
        Stage 4: Corroboration & Candidate Triage.
        Clusters findings for the same target paper sharing gap_type and key token overlap.
        Promotes verification_status to 'corroborated' when 2+ independent citing sources
        report the limitation (or when corroborated between self-reported findings and citation).
        Tracks contradicting statements and flags disputed findings.
        """
        if not gaps_with_evidence:
            return []

        by_paper: dict[str, list[int]] = {}
        for idx, (ev, gap) in enumerate(gaps_with_evidence):
            by_paper.setdefault(gap.paper_id, []).append(idx)

        for paper_id, indices in by_paper.items():
            by_gap_type: dict[str, list[int]] = {}
            for idx in indices:
                _, gap = gaps_with_evidence[idx]
                by_gap_type.setdefault(gap.gap_type, []).append(idx)

            for gap_type, group_indices in by_gap_type.items():
                clusters = self._cluster_by_tokens(
                    [gaps_with_evidence[i] for i in group_indices]
                )

                for cluster_items in clusters:
                    self._triage_cluster(cluster_items)

        return gaps_with_evidence

    def extract_all_gaps(
        self,
        target_paper: PaperRecord,
        contexts: list[CitationContextRecord],
        sections: Optional[dict[str, str]] = None,
    ) -> list[tuple[EvidenceRecord, PaperGapRecord]]:
        """
        End-to-end multi-stage pipeline: extracts abstract gaps, full-text section gaps,
        citation context gaps, and corroborates findings across sources.
        """
        abstract_gaps = self.extract_abstract_gaps(target_paper)
        fulltext_gaps = self.extract_fulltext_gaps(target_paper, sections) if sections else []
        citation_gaps = self.extract_citation_context_gaps(target_paper, contexts)
        return self.corroborate_gaps(abstract_gaps + fulltext_gaps + citation_gaps)

    def _cluster_by_tokens(
        self, items: list[tuple[EvidenceRecord, PaperGapRecord]]
    ) -> list[list[tuple[EvidenceRecord, PaperGapRecord]]]:
        """Cluster items sharing at least one key domain token."""
        n = len(items)
        if n <= 1:
            return [items]

        token_sets = [
            _extract_key_tokens(f"{gap.claim_summary} {ev.extracted_text}")
            for ev, gap in items
        ]

        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i: int, j: int) -> None:
            root_i, root_j = find(i), find(j)
            if root_i != root_j:
                parent[root_i] = root_j

        for i in range(n):
            for j in range(i + 1, n):
                if token_sets[i] and token_sets[j] and (token_sets[i] & token_sets[j]):
                    union(i, j)

        clusters_dict: dict[int, list[tuple[EvidenceRecord, PaperGapRecord]]] = {}
        for i in range(n):
            root = find(i)
            clusters_dict.setdefault(root, []).append(items[i])

        return list(clusters_dict.values())

    def _triage_cluster(
        self, cluster: list[tuple[EvidenceRecord, PaperGapRecord]]
    ) -> None:
        """Evaluate corroboration and contradiction evidence for a cluster of matching gaps."""
        citing_sources: set[str] = set()
        contradicting_sources: set[str] = set()
        has_self_reported = False

        for ev, _ in cluster:
            if ev.reporting_paper_id is None or ev.evidence_type in (
                "abstract_limitation",
                "fulltext_limitation",
                "system_model_assumption",
                "methodology_complexity",
                "methodology_limitation",
            ):
                has_self_reported = True
            else:
                source_id = ev.reporting_paper_id
                if _is_contradiction(ev.extracted_text):
                    contradicting_sources.add(source_id)
                else:
                    citing_sources.add(source_id)

        corroborating_sources = citing_sources - contradicting_sources
        num_corroborating = len(corroborating_sources)
        contradicting_count = len(contradicting_sources)

        # Status determination
        if contradicting_count > 0 and contradicting_count >= num_corroborating:
            status = "disputed"
            corroborating_count = num_corroborating
        elif num_corroborating >= 2 or (has_self_reported and num_corroborating >= 1):
            status = "corroborated"
            corroborating_count = num_corroborating
        else:
            status = "candidate"
            corroborating_count = 0

        # Update all records in the cluster
        for _, gap in cluster:
            gap.verification_status = status
            gap.corroborating_count = corroborating_count
            gap.contradicting_count = contradicting_count
