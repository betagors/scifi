"""
BibTeX file parser, batch citation auditor, and sanitizer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import bibtexparser
import requests

from scifi.network import get_session
from .discrepancy import audit_discrepancies
from .fetchers import OpenAlexFetcher, resolve_citation
from .identifiers import clean_doi, extract_identifier
from .models import (
    Author,
    BibAuditReport,
    CitationMetadata,
    ClaimedMetadata,
    Severity,
    VerificationStatus,
)


def search_identifier_by_title(title: str, author_hint: Optional[str] = None, timeout: int = 8) -> Optional[Tuple[str, str]]:
    """Search OpenAlex by title to find DOI for citations lacking an explicit identifier."""
    if not title or len(title.strip()) < 5:
        return None
    url = "https://api.openalex.org/works"
    params = {"search": title.strip(), "per-page": 3}
    headers = {"User-Agent": "SciFi-CitationVerifier/1.0 (mailto:scifi-toolkit@gmail.com)"}
    try:
        resp = get_session().get(url, params=params, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            for res in results:
                doi_url = res.get("doi")
                if doi_url:
                    clean = clean_doi(doi_url)
                    return "doi", clean
    except Exception:
        pass
    return None


def extract_claimed_metadata_from_bib_entry(entry: Any) -> Tuple[ClaimedMetadata, Optional[Tuple[str, str, Dict[str, str]]]]:
    """Extract claimed fields and best candidate identifier from a bibtexparser Entry."""
    fields = entry.fields_dict

    def get_val(key: str) -> Optional[str]:
        field_obj = fields.get(key)
        if field_obj is not None:
            val = str(field_obj.value).strip()
            # Clean curly braces
            return val.replace("{", "").replace("}", "")
        return None

    title = get_val("title")
    author_str = get_val("author")
    year_str = get_val("year")
    venue = get_val("journal") or get_val("booktitle") or get_val("series")
    doi_val = get_val("doi")
    url_val = get_val("url")
    eprint_val = get_val("eprint")

    claimed_authors: List[str] = []
    if author_str:
        for a in author_str.split(" and "):
            if a.strip():
                claimed_authors.append(a.strip())

    claimed_year: Optional[int] = None
    if year_str:
        m = re.search(r"\b(\d{4})\b", year_str)
        if m:
            claimed_year = int(m.group(1))

    claimed = ClaimedMetadata(
        title=title,
        authors=claimed_authors,
        year=claimed_year,
        venue=venue,
        doi=doi_val,
        entry_key=entry.key,
        raw_entry={k: f.value for k, f in fields.items()},
    )

    # Candidate identifier extraction
    candidate = None
    if doi_val:
        candidate = extract_identifier(doi_val, follow_links=False)
    elif url_val:
        candidate = extract_identifier(url_val, follow_links=True)
    elif eprint_val:
        candidate = extract_identifier(eprint_val, follow_links=False)

    return claimed, candidate


def audit_bib_content(
    bib_content: str,
    file_path: Optional[str] = None,
    search_missing: bool = True,
    timeout: int = 10,
) -> BibAuditReport:
    """
    Audit an entire BibTeX file or string against authoritative registries.
    Detects retracted papers, broken links, typos, and year discrepancies.
    """
    library = bibtexparser.parse_string(bib_content)
    report = BibAuditReport(file_path=file_path, total_entries=len(library.entries))

    for entry in library.entries:
        claimed, candidate = extract_claimed_metadata_from_bib_entry(entry)

        # If no identifier was found directly, search by title
        if (not candidate or candidate[0] == "unknown") and search_missing and claimed.title:
            found = search_identifier_by_title(claimed.title, claimed.authors[0] if claimed.authors else None)
            if found:
                candidate = (found[0], found[1], {"inferred_from_title": claimed.title})

        if candidate and candidate[0] != "unknown":
            id_type, id_val, extra = candidate
            meta = resolve_citation(id_type, id_val, extra, timeout=timeout)
        else:
            meta = CitationMetadata(
                identifier_type="none",
                identifier_value=entry.key or "unknown_key",
                status=VerificationStatus.UNRESOLVED,
                title=claimed.title or "Unknown Title",
                source_registry="None",
            )

        meta.claimed_metadata = claimed

        # Perform discrepancy analysis if citation was verified
        if meta.status != VerificationStatus.UNRESOLVED:
            verified_authors = [a.name for a in meta.authors]
            discrepancies = audit_discrepancies(
                claimed,
                verified_title=meta.title,
                verified_authors=verified_authors,
                verified_year=meta.year,
                verified_venue=meta.venue,
            )
            meta.discrepancies = discrepancies

            # Check if discrepancies escalate status to MISMATCH
            has_error = any(d.severity == Severity.ERROR for d in discrepancies)
            if has_error and meta.status == VerificationStatus.VERIFIED:
                meta.status = VerificationStatus.MISMATCH

        # Update tally
        if meta.status == VerificationStatus.VERIFIED:
            report.verified_count += 1
        elif meta.status == VerificationStatus.RETRACTED:
            report.retracted_count += 1
        elif meta.status == VerificationStatus.ERRATA_EXISTS:
            report.errata_count += 1
        elif meta.status == VerificationStatus.MISMATCH:
            report.mismatch_count += 1
        elif meta.status == VerificationStatus.UNRESOLVED:
            report.unresolved_count += 1

        report.entries.append(meta)

    return report


def audit_bib_file(file_path: Union[str, Path], search_missing: bool = True) -> BibAuditReport:
    """Read and audit a .bib file from disk."""
    path = Path(file_path)
    content = path.read_text(encoding="utf-8")
    return audit_bib_content(content, file_path=str(path), search_missing=search_missing)


def generate_sanitized_bib(report: BibAuditReport) -> str:
    """
    Generate an enhanced, cleaned BibTeX library from an audit report.
    Adds warnings for retracted papers and fills in verified DOIs and metadata.
    """
    bib_chunks: List[str] = []

    for meta in report.entries:
        claimed = meta.claimed_metadata
        key = claimed.entry_key if claimed and claimed.entry_key else meta.generate_cite_key()

        if meta.is_retracted:
            bib_chunks.append(
                f"% 🚨 WARNING: CITATION RETRACTED!\n"
                f"% Paper '{meta.title}' has been officially retracted.\n"
                f"% Retraction details: {meta.retraction_details or 'Check publisher notice.'}"
            )
        elif meta.has_errata:
            bib_chunks.append(
                f"% ⚠️ NOTICE: Errata / Correction published for this citation.\n"
                f"% Details: {meta.errata_details or 'Review updates before citing.'}"
            )

        if meta.status != VerificationStatus.UNRESOLVED:
            bib_chunks.append(meta.to_bibtex(key=key))
        else:
            # Re-serialize original unverified entry if available
            bib_chunks.append(f"% Unverified citation: {meta.identifier_value}")
            if claimed and claimed.title:
                bib_chunks.append(
                    f"@misc{{{key},\n  title = {{{claimed.title}}},\n  note = {{Unverified}}\n}}"
                )

    return "\n\n".join(bib_chunks)
