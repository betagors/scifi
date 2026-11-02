"""
Core execution engine for Argus Attribution & Plagiarism Audit.
Coordinates detector, searcher, and reporting.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

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
    def __init__(
        self,
        author_whitelist: Optional[List[str]] = None,
        preprint_doi: Optional[str] = None,
        timeout: int = 10,
        enable_search: bool = True,
    ):
        self.searcher = ArgusSearcher(author_whitelist, preprint_doi)
        self.timeout = timeout
        self.enable_search = enable_search

    def audit_file(self, file_path: Path) -> AttributionReport:
        content = file_path.read_text(encoding="utf-8", errors="replace")
        return self.audit_text(content, source_file=str(file_path))

    def audit_text(self, text: str, source_file: Optional[str] = None) -> AttributionReport:
        spans = split_into_sentence_spans(text)
        findings: List[AttributionFinding] = []
        finding_idx = 1

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

                cite_key = candidate_work.generate_cite_key() if candidate_work else f"{entity_term.title().replace(' ', '')}Ref"
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
                            "Reformulate via the 'human' skill into objective, publication-grade academic prose."
                        ),
                    )
                )
                finding_idx += 1

        return AttributionReport(source_file=source_file, findings=findings)
