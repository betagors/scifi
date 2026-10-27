"""
Citation Verifier: Verify scientific citations via DOI, URL, or metadata against Crossref, OpenAlex, arXiv, and DataCite.
"""

from typing import Optional

from .bib_auditor import audit_bib_content, audit_bib_file, generate_sanitized_bib
from .discrepancy import audit_discrepancies
from .fetchers import resolve_citation
from .identifiers import clean_doi, extract_identifier
from .models import (
    Author,
    BibAuditReport,
    CitationMetadata,
    ClaimedMetadata,
    Discrepancy,
    Severity,
    VerificationStatus,
)


def verify_citation(
    query: str,
    claimed_title: Optional[str] = None,
    claimed_year: Optional[int] = None,
    claimed_author: Optional[str] = None,
    claimed_venue: Optional[str] = None,
    timeout: int = 10,
) -> CitationMetadata:
    """
    Verify an individual citation by link or DOI.

    Args:
        query: DOI, arXiv URL, PubMed link, direct publisher URL, or identifier.
        claimed_title: Optional title claimed by the user to compare against.
        claimed_year: Optional publication year claimed by the user.
        claimed_author: Optional author claimed by the user.
        claimed_venue: Optional journal/conference claimed by the user.
        timeout: Request timeout in seconds.

    Returns:
        CitationMetadata with status, canonical metadata, retraction warnings, and discrepancies.
    """
    id_type, id_val, extra = extract_identifier(query, follow_links=True)
    meta = resolve_citation(id_type, id_val, extra_info=extra, timeout=timeout)

    # If user provided claimed fields, perform discrepancy audit
    if claimed_title or claimed_year or claimed_author or claimed_venue:
        claimed = ClaimedMetadata(
            title=claimed_title,
            authors=[claimed_author] if claimed_author else [],
            year=claimed_year,
            venue=claimed_venue,
        )
        meta.claimed_metadata = claimed
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
            if any(d.severity == Severity.ERROR for d in discrepancies) and meta.status == VerificationStatus.VERIFIED:
                meta.status = VerificationStatus.MISMATCH

    return meta


__all__ = [
    "verify_citation",
    "audit_bib_file",
    "audit_bib_content",
    "generate_sanitized_bib",
    "extract_identifier",
    "clean_doi",
    "resolve_citation",
    "CitationMetadata",
    "BibAuditReport",
    "VerificationStatus",
    "Severity",
    "Discrepancy",
    "Author",
    "ClaimedMetadata",
]
