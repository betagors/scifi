"""
Claim-to-Citation Entailment Audit Engine.
Uses Hypatia (OpenAlex abstract + Unpaywall/arXiv PDF text) to verify whether
cited references in LaTeX sentences actually support the claims made.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import bibtexparser

from scifi.cache import RegistryCache
from scifi.citation_verifier.bib_auditor import extract_claimed_metadata_from_bib_entry
from scifi.citation_verifier.models import ClaimedMetadata
from scifi.latex.project import resolve_latex_project

from .detector import split_into_sentence_spans
from .models import EntailmentFinding, EntailmentReport, EntailmentStatus

_STOP_WORDS: set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "but",
    "nor",
    "for",
    "yet",
    "so",
    "in",
    "on",
    "at",
    "to",
    "from",
    "by",
    "with",
    "of",
    "as",
    "into",
    "onto",
    "upon",
    "about",
    "over",
    "under",
    "between",
    "among",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "can",
    "could",
    "that",
    "this",
    "these",
    "those",
    "which",
    "who",
    "whom",
    "whose",
    "what",
    "where",
    "when",
    "why",
    "how",
    "their",
    "they",
    "them",
    "its",
    "our",
    "we",
    "us",
    "he",
    "she",
    "it",
    "such",
    "also",
    "well",
    "however",
    "moreover",
    "furthermore",
    "therefore",
    "thus",
    "hence",
    "while",
    "whereas",
    "although",
    "though",
    "because",
    "since",
    "if",
    "then",
    "than",
    "more",
    "most",
    "less",
    "least",
    "very",
    "each",
    "every",
    "both",
    "all",
    "some",
    "any",
    "many",
    "much",
    "few",
    "several",
    "other",
    "another",
    "same",
    "similar",
    "different",
    "new",
    "novel",
    "existing",
    "previous",
    "prior",
    "recent",
    "recently",
    "first",
    "second",
    "third",
    "one",
    "two",
    "three",
    "high",
    "low",
    "large",
    "small",
    "significant",
    "significantly",
    "show",
    "shows",
    "showed",
    "shown",
    "demonstrate",
    "demonstrates",
    "demonstrated",
    "propose",
    "proposes",
    "proposed",
    "present",
    "presents",
    "presented",
    "report",
    "reports",
    "reported",
    "observe",
    "observes",
    "observed",
    "find",
    "finds",
    "found",
    "study",
    "studies",
    "paper",
    "work",
    "works",
    "author",
    "authors",
    "method",
    "methods",
    "approach",
    "approaches",
    "model",
    "models",
    "result",
    "results",
    "using",
    "used",
    "use",
    "based",
    "et",
    "al",
    "math",
}

_NEGATION_PATTERN = re.compile(
    r"\b(not|no|never|neither|nor|cannot|can't|doesn't|don't|didn't|won't|"
    r"fails?|failed|unable|without|lacks?|lacked|ineffective|insufficient|"
    r"insignificant|non-significant|null\s+effect|refutes?|contradicts?|disproves?)\b",
    re.IGNORECASE,
)

# Directional / evaluative antonym groups: (positive_terms, negative_terms)
_ANTONYM_PAIRS: list[tuple[set[str], set[str]]] = [
    (
        {"increase", "increases", "increased", "increasing", "higher", "gain", "gains", "boost", "boosts", "boosted"},
        {
            "decrease",
            "decreases",
            "decreased",
            "decreasing",
            "lower",
            "drop",
            "drops",
            "dropped",
            "reduce",
            "reduces",
            "reduced",
        },
    ),
    (
        {
            "improve",
            "improves",
            "improved",
            "improving",
            "improvement",
            "outperform",
            "outperforms",
            "outperformed",
            "superior",
            "better",
            "faster",
        },
        {
            "degrade",
            "degrades",
            "degraded",
            "degrading",
            "underperform",
            "underperforms",
            "underperformed",
            "inferior",
            "worse",
            "slower",
        },
    ),
    (
        {
            "effective",
            "beneficial",
            "significant",
            "converge",
            "converges",
            "converged",
            "stable",
            "convex",
            "accurate",
            "safe",
            "scalable",
        },
        {
            "ineffective",
            "harmful",
            "insignificant",
            "non-significant",
            "diverge",
            "diverges",
            "diverged",
            "unstable",
            "non-convex",
            "inaccurate",
            "unsafe",
            "unscalable",
        },
    ),
]

_METRIC_NAMES = (
    r"accuracy|acc|f1(?:-score)?|precision|recall|bleu|rouge(?:-[12l])?|"
    r"perplexity|ppl|auc|roc-auc|auroc|rmse|mae|mse|iou|miou|map|psnr|"
    r"ssim|wer|cer|top-1|top-5|pass@1|pass@k|speedup|latency|throughput"
)
_UNIT_NAMES = (
    r"x|×|times|ms|sec|seconds|minutes|hours|mb|gb|tb|kb|hz|khz|mhz|ghz|"
    r"db|fps|flops|gflops|tflops"
)
_STRUCTURAL_REF_RE = re.compile(
    r"\b(?:section|sec\.?|table|tab\.?|figure|fig\.?|equation|eq\.?|algorithm|alg\.?|chapter|appendix)\s+\d+(?:\.\d+)*\b",
    re.IGNORECASE,
)


def clean_claim_text(text: str) -> str:
    """Strip LaTeX citation commands, formatting macros, and structural noise."""
    cleaned = re.sub(
        r"\\(?:cite|citep|citet|citeauthor|parencite|textcite)(?:\[[^\]]*\])*\{[^}]+\}",
        "",
        text,
    )
    cleaned = re.sub(r"\\(?:ref|eqref|label|autoref|cref)\{[^}]+\}", "", cleaned)
    cleaned = re.sub(r"\\(?:textbf|textit|emph|texttt|underline)\{([^}]*)\}", r"\1", cleaned)
    cleaned = cleaned.replace(r"\%", "%")
    cleaned = re.sub(r"\[MATH\]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _normalize_token(token: str) -> str:
    """Apply lightweight suffix normalization for lexical matching."""
    t = token.lower()
    if len(t) <= 3:
        return t
    if t.endswith("ies") and len(t) > 4:
        return t[:-3] + "y"
    if t.endswith("ing") and len(t) > 5:
        return t[:-3]
    if t.endswith("ed") and len(t) > 4:
        return t[:-2]
    if t.endswith("es") and len(t) > 4:
        return t[:-2]
    if t.endswith("s") and not t.endswith("ss") and len(t) > 3:
        return t[:-1]
    return t


def extract_content_keywords(text: str) -> set[str]:
    """Extract normalized non-stopword content tokens from text."""
    raw_tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{1,}", text.lower())
    keywords: set[str] = set()
    for tok in raw_tokens:
        if tok in _STOP_WORDS:
            continue
        norm = _normalize_token(tok)
        if norm and norm not in _STOP_WORDS and len(norm) >= 2:
            keywords.add(norm)
    return keywords


def extract_cited_metrics(claim_text: str) -> list[dict[str, str | None]]:
    """Extract quantitative metrics and named evaluation metrics from a claim sentence."""
    sanitized = _STRUCTURAL_REF_RE.sub(" ", claim_text)
    metrics: list[dict[str, str | None]] = []
    seen_labels: set[str] = set()

    def _add(label: str, number: str | None, metric_name: str | None, is_percent: bool = False) -> None:
        key = label.lower().strip()
        if key not in seen_labels:
            seen_labels.add(key)
            metrics.append(
                {
                    "label": label.strip(),
                    "number": number,
                    "metric_name": metric_name.lower() if metric_name else None,
                    "is_percent": "1" if is_percent else "0",
                }
            )

    # 1. Percentages (e.g., 94.2%, 15 percent)
    for m in re.finditer(r"\b(\d+(?:\.\d+)?)\s*(%|percent|percentage\s+points?)\b", sanitized, re.IGNORECASE):
        _add(m.group(0), m.group(1), None, is_percent=True)

    # 2. Named metric + value (e.g., "F1 of 0.89", "BLEU score of 34.5", "accuracy = 92.3%")
    pattern_metric_val = re.compile(
        rf"\b({_METRIC_NAMES})\b(?:\s+score)?\s*(?:of|is|was|=|:|at|reached|achieved|scored|around|about)?\s*(\d+(?:\.\d+)?)\s*(%?)",
        re.IGNORECASE,
    )
    for m in pattern_metric_val.finditer(sanitized):
        m_name, num, pct = m.group(1), m.group(2), m.group(3)
        _add(f"{m_name} {num}{pct}".strip(), num, m_name, is_percent=bool(pct))

    # 3. Value + named metric (e.g., "92.3% accuracy", "0.89 F1")
    pattern_val_metric = re.compile(
        rf"\b(\d+(?:\.\d+)?)\s*(%?)\s+(?:in\s+)?({_METRIC_NAMES})\b",
        re.IGNORECASE,
    )
    for m in pattern_val_metric.finditer(sanitized):
        num, pct, m_name = m.group(1), m.group(2), m.group(3)
        _add(f"{num}{pct} {m_name}".strip(), num, m_name, is_percent=bool(pct))

    # 4. Number + unit/multiplier (e.g., "3.5x speedup", "12 ms")
    pattern_unit = re.compile(rf"\b(\d+(?:\.\d+)?)\s*({_UNIT_NAMES})\b", re.IGNORECASE)
    for m in pattern_unit.finditer(sanitized):
        num, unit = m.group(1), m.group(2)
        if unit.lower() == "x" and len(num) == 4 and num.startswith(("19", "20")):
            continue
        _add(m.group(0), num, unit, is_percent=False)

    # 5. Standalone named metric in an empirical assertion (if no numeric value already captured it)
    if not metrics:
        for m in re.finditer(rf"\b({_METRIC_NAMES})\b", sanitized, re.IGNORECASE):
            m_name = m.group(1)
            _add(m_name, None, m_name, is_percent=False)

    return metrics


def _number_in_text(number_str: str, is_percent: bool, evidence_text: str) -> bool:
    """Check whether a numeric value (or its percentage/decimal equivalent) appears in evidence."""
    escaped = re.escape(number_str)
    if re.search(rf"(?<!\d){escaped}(?!\d)", evidence_text):
        return True
    try:
        val = float(number_str)
    except ValueError:
        return False

    if is_percent:
        # e.g. 94.2% -> 0.942
        dec = f"{val / 100.0:.4f}".rstrip("0").rstrip(".")
        if re.search(rf"(?<!\d){re.escape(dec)}(?!\d)", evidence_text):
            return True
    elif 0.0 < val < 1.0:
        # e.g. 0.89 -> 89% or 89.0%
        pct_val = val * 100.0
        pct_int = f"{pct_val:.1f}".rstrip("0").rstrip(".")
        if re.search(rf"(?<!\d){re.escape(pct_int)}\s*%", evidence_text):
            return True
    return False


def find_missing_metrics(claim_text: str, evidence_text: str) -> list[str]:
    """Return cited metrics/values from the claim that are absent in the evidence text."""
    cited = extract_cited_metrics(claim_text)
    if not cited:
        return []
    ev_lower = evidence_text.lower()
    missing: list[str] = []
    for item in cited:
        num = item["number"]
        m_name = item["metric_name"]
        is_pct = item["is_percent"] == "1"
        if num is not None:
            if not _number_in_text(num, is_pct, evidence_text):
                missing.append(str(item["label"]))
        elif m_name is not None:
            if not re.search(rf"\b{re.escape(m_name)}\b", ev_lower):
                missing.append(str(item["label"]))
    return missing


def detect_contradiction(claim_text: str, evidence_text: str) -> tuple[bool, str | None, str | None]:
    """Detect whether any sentence in evidence_text contradicts claim_text."""
    claim_kw = extract_content_keywords(claim_text)
    if not claim_kw:
        return False, None, None

    claim_neg = bool(_NEGATION_PATTERN.search(claim_text))
    claim_words = set(re.findall(r"[a-zA-Z-]+", claim_text.lower()))

    ev_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", evidence_text) if len(s.strip()) > 10]
    for ev_sent in ev_sentences:
        ev_kw = extract_content_keywords(ev_sent)
        shared = claim_kw & ev_kw
        if len(shared) < 2 and len(shared) / max(1, len(claim_kw)) < 0.35:
            continue

        ev_neg = bool(_NEGATION_PATTERN.search(ev_sent))
        ev_words = set(re.findall(r"[a-zA-Z-]+", ev_sent.lower()))

        # 1. Explicit negation mismatch on shared topic
        if claim_neg != ev_neg:
            return (
                True,
                ev_sent,
                f"Polarity contradiction on shared concepts ({', '.join(sorted(shared)[:4])}): "
                f"claim and cited work have opposite negation.",
            )

        # 2. Directional / evaluative antonym conflict
        for pos_set, neg_set in _ANTONYM_PAIRS:
            c_pos = bool(claim_words & pos_set)
            c_neg = bool(claim_words & neg_set)
            e_pos = bool(ev_words & pos_set)
            e_neg = bool(ev_words & neg_set)
            if (c_pos and e_neg and not c_neg) or (c_neg and e_pos and not c_pos):
                return (
                    True,
                    ev_sent,
                    f"Directional contradiction on shared concepts ({', '.join(sorted(shared)[:4])}): "
                    f"claim and cited work assert opposite effects.",
                )

    return False, None, None


def evaluate_claim_entailment(
    claim_text: str,
    paper_title: str | None,
    evidence_text: str | None,
) -> tuple[EntailmentStatus, float, str, float, list[str], str | None]:
    """Evaluate claim-to-citation entailment against a paper's title and evidence text.

    Returns:
        Tuple of ``(status, confidence, reason, overlap_ratio, missing_metrics, contradiction_excerpt)``.
    """
    if not evidence_text or not evidence_text.strip():
        return (
            EntailmentStatus.INSUFFICIENT_EVIDENCE,
            0.0,
            "No abstract or full-text content could be retrieved for the cited work.",
            0.0,
            [],
            None,
        )

    combined_paper_text = f"{paper_title or ''}\n{evidence_text}".strip()
    claim_kw = extract_content_keywords(claim_text)
    paper_kw = extract_content_keywords(combined_paper_text)

    if claim_kw:
        shared_kw = claim_kw & paper_kw
        overlap_ratio = len(shared_kw) / len(claim_kw)
    else:
        shared_kw = set()
        overlap_ratio = 1.0

    # 1. Off-topic check
    if (len(claim_kw) >= 2 and overlap_ratio < 0.15 and len(shared_kw) < 2) or (
        len(claim_kw) == 1 and len(shared_kw) == 0
    ):
        return (
            EntailmentStatus.OFF_TOPIC,
            0.85,
            f"Cited work appears off-topic relative to the claim (topical keyword overlap: {overlap_ratio:.0%}).",
            overlap_ratio,
            [],
            None,
        )

    # 2. Contradiction check
    is_contra, excerpt, contra_reason = detect_contradiction(claim_text, evidence_text)
    if is_contra:
        return (
            EntailmentStatus.CONTRADICTS,
            0.82,
            contra_reason or "Cited work contains statements contradicting the claim.",
            overlap_ratio,
            [],
            excerpt,
        )

    # 3. Missing metric check
    missing_metrics = find_missing_metrics(claim_text, evidence_text)
    if missing_metrics:
        return (
            EntailmentStatus.MISSING_METRIC,
            0.80,
            f"Cited work does not contain the claimed metric(s): {', '.join(missing_metrics)}.",
            overlap_ratio,
            missing_metrics,
            None,
        )

    return (
        EntailmentStatus.SUPPORTED,
        min(0.95, 0.65 + 0.30 * overlap_ratio),
        f"Cited work aligns topically with the claim (overlap: {overlap_ratio:.0%}) with no contradictions or missing metrics.",
        overlap_ratio,
        [],
        None,
    )


@dataclass
class _PaperEvidence:
    """Cached evidence bundle for a resolved BibTeX citation key."""

    title: str | None
    doi: str | None
    abstract: str | None
    full_text: str | None
    evidence_source: str | None


def _retrieve_paper_evidence(
    claimed: ClaimedMetadata | None,
    resolver: Any,
    fetch_pdf: bool,
    pdf_dir: Path,
    cache: RegistryCache | None,
) -> _PaperEvidence:
    """Retrieve OpenAlex abstract and (if needed/enabled) Unpaywall/arXiv PDF text."""
    if claimed is None:
        return _PaperEvidence(None, None, None, None, None)

    paper = None
    if claimed.doi:
        paper = resolver.resolve_by_doi(claimed.doi)
    elif claimed.raw_entry.get("eprint"):
        eprint = str(claimed.raw_entry["eprint"]).strip()
        paper = resolver.resolve_by_doi(f"10.48550/arXiv.{eprint}")
        if paper is None and claimed.title:
            paper = resolver.resolve_by_title(claimed.title)
    elif claimed.title:
        paper = resolver.resolve_by_title(claimed.title)

    title = (paper.title if paper else None) or claimed.title
    paper_doi = None
    if paper and getattr(paper, "identifiers", None):
        for ident in paper.identifiers:
            if getattr(ident, "provider", "").lower() == "doi" and getattr(ident, "external_id", None):
                paper_doi = ident.external_id
                break
    doi = paper_doi or claimed.doi
    abstract = paper.abstract if paper else None
    source = "OpenAlex Abstract" if abstract else None

    full_text: str | None = None
    if fetch_pdf and (doi or claimed.raw_entry.get("eprint")):
        identifier = doi or str(claimed.raw_entry["eprint"]).strip()
        # Fetch PDF only when abstract is missing; caller can also upgrade later if metric missing
        if not abstract:
            full_text, pdf_source = _try_fetch_and_extract_pdf(identifier, pdf_dir, cache)
            if full_text:
                source = pdf_source

    return _PaperEvidence(
        title=title,
        doi=doi,
        abstract=abstract,
        full_text=full_text,
        evidence_source=source,
    )


def _try_fetch_and_extract_pdf(
    identifier: str,
    pdf_dir: Path,
    cache: RegistryCache | None,
) -> tuple[str | None, str | None]:
    """Download OA PDF via Hypatia fetcher and extract text sections."""
    from scifi.literature.extractor import extract_pdf_text
    from scifi.literature.fetcher import fetch_paper_pdf

    try:
        res = fetch_paper_pdf(identifier, output_dir=pdf_dir)
        if res.get("status") == "SUCCESS" and res.get("file_path"):
            extracted = extract_pdf_text(res["file_path"], cache=cache, use_cache=cache is not None)
            if extracted.get("status") == "SUCCESS":
                parts = [
                    extracted.get("abstract") or "",
                    extracted.get("system_model_or_method") or "",
                    extracted.get("limitations_and_conclusion") or "",
                    extracted.get("raw_sample") or "",
                ]
                combined = "\n".join(p for p in parts if p).strip()
                if combined:
                    src = f"{res.get('source', 'Unpaywall')} PDF"
                    return combined, src
    except Exception:
        pass
    return None, None


def _discover_bib_file(tex_path: Path, content: str) -> Path | None:
    """Locate the .bib file referenced by a LaTeX manuscript or in its directory."""
    m = re.search(r"\\(?:bibliography|addbibresource)\{([^}]+)\}", content)
    if m:
        first_bib = m.group(1).split(",")[0].strip()
        if not first_bib.endswith(".bib"):
            first_bib += ".bib"
        candidate = tex_path.parent / first_bib
        if candidate.exists():
            return candidate
    default_bib = tex_path.parent / "references.bib"
    if default_bib.exists():
        return default_bib
    bibs = sorted(tex_path.parent.glob("*.bib"))
    return bibs[0] if bibs else None


def _parse_bib_entries(bib_path: Path) -> dict[str, ClaimedMetadata]:
    """Parse a .bib file into a mapping from cite key to ClaimedMetadata."""
    content = bib_path.read_text(encoding="utf-8", errors="replace")
    library = bibtexparser.parse_string(content)
    entries: dict[str, ClaimedMetadata] = {}
    for entry in library.entries:
        claimed, _ = extract_claimed_metadata_from_bib_entry(entry)
        if claimed.entry_key:
            entries[claimed.entry_key] = claimed
    return entries


def audit_claim_entailment(
    tex_content_or_path: str | Path,
    bib_path: str | Path | None = None,
    fetch_pdf: bool = True,
    cache: RegistryCache | None = None,
    timeout: int = 10,
) -> EntailmentReport:
    """Run a claim-to-citation entailment audit on a LaTeX manuscript or text.

    Args:
        tex_content_or_path: Path to a ``.tex``/``.md`` file, project directory, or raw text.
        bib_path: Optional path to the ``.bib`` file resolving citation keys.
        fetch_pdf: When True, fetch Unpaywall/OpenAlex/arXiv PDFs if abstract is missing
            or lacks a cited metric.
        cache: Optional ``RegistryCache`` instance.
        timeout: HTTP request timeout in seconds.

    Returns:
        ``EntailmentReport`` containing per-citation verdicts and aggregate counts.
    """
    from scifi.literature.resolver import PaperResolver

    active_cache = cache if cache is not None else RegistryCache()
    resolver = PaperResolver(cache=active_cache, timeout=timeout)

    files_to_scan: list[tuple[str | None, str]] = []
    source_label: str | None = None
    resolved_bib: Path | None = Path(bib_path) if bib_path else None

    if isinstance(tex_content_or_path, Path) or (
        isinstance(tex_content_or_path, str) and "\n" not in tex_content_or_path and Path(tex_content_or_path).exists()
    ):
        target = Path(tex_content_or_path)
        source_label = str(target)
        if target.is_dir() or target.suffix.lower() == ".tex":
            try:
                proj = resolve_latex_project(target)
                if proj.is_multifile:
                    for src in proj.files:
                        files_to_scan.append((src.relative_path, src.content))
                    if resolved_bib is None:
                        resolved_bib = _discover_bib_file(proj.entrypoint, proj.merged_text)
                else:
                    content = target.read_text(encoding="utf-8", errors="replace")
                    files_to_scan.append((None, content))
                    if resolved_bib is None:
                        resolved_bib = _discover_bib_file(target, content)
            except Exception:
                content = target.read_text(encoding="utf-8", errors="replace")
                files_to_scan.append((None, content))
                if resolved_bib is None:
                    resolved_bib = _discover_bib_file(target, content)
        else:
            content = target.read_text(encoding="utf-8", errors="replace")
            files_to_scan.append((None, content))
            if resolved_bib is None:
                resolved_bib = _discover_bib_file(target, content)
    else:
        files_to_scan.append((None, str(tex_content_or_path)))

    bib_entries: dict[str, ClaimedMetadata] = {}
    if resolved_bib and resolved_bib.exists():
        bib_entries = _parse_bib_entries(resolved_bib)

    evidence_cache: dict[str, _PaperEvidence] = {}
    findings: list[EntailmentFinding] = []
    finding_idx = 1

    with tempfile.TemporaryDirectory(prefix="scifi_entail_") as tmp_dir:
        pdf_dir = Path(tmp_dir)

        for rel_file, content in files_to_scan:
            spans = split_into_sentence_spans(content)
            for span in spans:
                if not span.citations:
                    continue
                claim_clean = clean_claim_text(span.text)
                if len(claim_clean) < 5:
                    continue

                for cite_key in span.citations:
                    # Skip purely numeric bracket citations like "1" when not in bib
                    if cite_key.isdigit() and cite_key not in bib_entries:
                        continue

                    if cite_key not in bib_entries:
                        findings.append(
                            EntailmentFinding(
                                id=f"ENTAIL-{finding_idx:03d}",
                                line_number=span.line_number,
                                cite_key=cite_key,
                                claim_text=claim_clean,
                                status=EntailmentStatus.INSUFFICIENT_EVIDENCE,
                                confidence=0.0,
                                reason=(
                                    f"Citation key '{cite_key}' not found in BibTeX file."
                                    if resolved_bib
                                    else "No BibTeX file found to resolve citation key."
                                ),
                                source_file=rel_file,
                            )
                        )
                        finding_idx += 1
                        continue

                    if cite_key not in evidence_cache:
                        evidence_cache[cite_key] = _retrieve_paper_evidence(
                            bib_entries[cite_key],
                            resolver=resolver,
                            fetch_pdf=fetch_pdf,
                            pdf_dir=pdf_dir,
                            cache=active_cache,
                        )
                    ev = evidence_cache[cite_key]

                    combined_ev = "\n".join(p for p in (ev.abstract, ev.full_text) if p).strip()
                    status, conf, reason, overlap, missing_metrics, excerpt = evaluate_claim_entailment(
                        claim_clean,
                        ev.title,
                        combined_ev,
                    )

                    # Lazy PDF fallback: if abstract alone didn't have the cited metric, try Unpaywall/arXiv PDF
                    if (
                        status == EntailmentStatus.MISSING_METRIC
                        and fetch_pdf
                        and ev.full_text is None
                        and (ev.doi or bib_entries[cite_key].raw_entry.get("eprint"))
                    ):
                        ident = ev.doi or str(bib_entries[cite_key].raw_entry["eprint"]).strip()
                        pdf_text, pdf_src = _try_fetch_and_extract_pdf(ident, pdf_dir, active_cache)
                        if pdf_text:
                            ev.full_text = pdf_text
                            ev.evidence_source = f"{ev.evidence_source} + {pdf_src}" if ev.evidence_source else pdf_src
                            combined_ev = "\n".join(p for p in (ev.abstract, ev.full_text) if p).strip()
                            status, conf, reason, overlap, missing_metrics, excerpt = evaluate_claim_entailment(
                                claim_clean,
                                ev.title,
                                combined_ev,
                            )

                    findings.append(
                        EntailmentFinding(
                            id=f"ENTAIL-{finding_idx:03d}",
                            line_number=span.line_number,
                            cite_key=cite_key,
                            claim_text=claim_clean,
                            status=status,
                            confidence=conf,
                            reason=reason,
                            evidence_source=ev.evidence_source,
                            paper_title=ev.title,
                            paper_doi=ev.doi,
                            missing_metrics=missing_metrics,
                            contradiction_excerpt=excerpt,
                            topical_overlap=overlap,
                            source_file=rel_file,
                        )
                    )
                    finding_idx += 1

    return EntailmentReport(
        source_file=source_label,
        bib_file=str(resolved_bib) if resolved_bib else None,
        findings=findings,
        files_scanned=[f for f, _ in files_to_scan if f],
    )
