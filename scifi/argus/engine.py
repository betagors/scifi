"""
Core execution engine for Argus Attribution & Plagiarism Audit.
Coordinates detector, searcher, and reporting across single files or multi-file LaTeX projects.
"""

from __future__ import annotations

from pathlib import Path

from scifi.latex.project import resolve_latex_project

from .detector import (
    COMMON_KNOWLEDGE,
    detect_informal_ai_tropes,
    extract_potential_methods,
    split_into_sentence_spans,
)
from .models import (
    AttributionCategory,
    AttributionFinding,
    AttributionReport,
    SuggestedAction,
)
from .searcher import ArgusSearcher


class ArgusEngine:
    """Core sentinel engine for attribution auditing and uncredited method detection.

    Scans LaTeX manuscripts and multi-file projects to detect named algorithms, models,
    and methodologies lacking citations, cross-referencing against academic registries.

    Args:
        author_whitelist: Optional author names excluded from self-plagiarism alerts.
        preprint_doi: Optional preprint DOI representing prior versions of this work.
        timeout: HTTP request timeout in seconds when querying registries.
        enable_search: Whether to query external registries (OpenAlex/Crossref) for matches.
    """

    def __init__(
        self,
        author_whitelist: list[str] | None = None,
        preprint_doi: str | None = None,
        timeout: int = 10,
        enable_search: bool = True,
    ):
        self.searcher = ArgusSearcher(author_whitelist, preprint_doi)
        self.timeout = timeout
        self.enable_search = enable_search

    def audit_file(self, file_path: Path) -> AttributionReport:
        if file_path.is_dir() or file_path.suffix.lower() == ".tex":
            try:
                proj = resolve_latex_project(file_path)
                if proj.is_multifile:
                    all_findings: list[AttributionFinding] = []
                    next_idx = 1
                    for src_file in proj.files:
                        sub_rep = self.audit_text(
                            src_file.content,
                            source_file=src_file.relative_path,
                            start_idx=next_idx,
                        )
                        for f in sub_rep.findings:
                            f.source_file = src_file.relative_path
                            all_findings.append(f)
                        next_idx += len(sub_rep.findings)
                    return AttributionReport(
                        source_file=str(proj.entrypoint),
                        findings=all_findings,
                        files_scanned=[f.relative_path for f in proj.files],
                    )
            except Exception:
                pass
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return self.audit_text(content, source_file=str(file_path))

    def audit_text(
        self,
        text: str,
        source_file: str | None = None,
        start_idx: int = 1,
    ) -> AttributionReport:
        spans = split_into_sentence_spans(text)
        findings: list[AttributionFinding] = []
        finding_idx = start_idx

        for span in spans:
            has_local_citation = len(span.citations) > 0

            # 1. Audit named methods and algorithms
            methods = extract_potential_methods(span.text)
            for entity_term, canonical_query in methods:
                lower_term = entity_term.lower()

                if lower_term in COMMON_KNOWLEDGE:
                    # Common knowledge concept - no citation needed
                    continue

                if has_local_citation:
                    # Method has an accompanying citation in this sentence
                    continue

                candidate_work = None
                confidence = 0.85
                is_self = False

                if self.enable_search:
                    search_res = self.searcher.search_canonical_work(canonical_query, timeout=self.timeout)
                    if search_res:
                        candidate_work, confidence, is_self = search_res

                if is_self:
                    cat = AttributionCategory.PREPRINT_ALIGNMENT
                    action = SuggestedAction.CITE
                    hint = (
                        "Text aligns with author's own preprint or prior work. "
                        "Cite explicitly to establish lineage and avoid self-plagiarism concerns."
                    )
                else:
                    cat = AttributionCategory.CANONICAL_ACADEMIC
                    action = SuggestedAction.CITE
                    hint = (
                        f"Specific method '{entity_term}' is introduced without an accompanying citation. "
                        f"Cite the canonical literature to attribute origin."
                    )

                cite_key = (
                    candidate_work.generate_cite_key()
                    if candidate_work
                    else f"{entity_term.title().replace(' ', '')}Ref"
                )
                bibtex = candidate_work.to_bibtex(key=cite_key) if candidate_work else None

                findings.append(
                    AttributionFinding(
                        id=f"ARGUS-{finding_idx:03d}",
                        line_number=span.line_number,
                        text_snippet=span.text,
                        matched_entity=entity_term,
                        category=cat,
                        suggested_action=action,
                        confidence=confidence,
                        remediation_hint=hint,
                        candidate_work=candidate_work,
                        cite_key=cite_key,
                        bibtex_entry=bibtex,
                    )
                )
                finding_idx += 1

            # 2. Audit informal web patterns and AI slop hallmarks
            tropes = detect_informal_ai_tropes(span.text)
            if len(tropes) >= 2 or any("tutorial" in t or "blog" in t or "delve" in t for t in tropes):
                findings.append(
                    AttributionFinding(
                        id=f"ARGUS-{finding_idx:03d}",
                        line_number=span.line_number,
                        text_snippet=span.text,
                        matched_entity=", ".join(tropes),
                        category=AttributionCategory.INFORMAL_WEB,
                        suggested_action=SuggestedAction.REFORMULATE,
                        confidence=0.90,
                        remediation_hint=(
                            f"Contains informal web or synthetic AI phrasing ({', '.join(tropes)}). "
                            f"Rewrite into objective, hedged academic prose via the 'human' skill."
                        ),
                    )
                )
                finding_idx += 1

        return AttributionReport(source_file=source_file, findings=findings)
