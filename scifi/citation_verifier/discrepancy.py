"""
Discrepancy and consistency auditing between claimed citations and verified registry metadata.
"""

from __future__ import annotations

import difflib
import re

from .models import ClaimedMetadata, Discrepancy, Severity


def clean_text_for_comparison(text: str | None) -> str:
    """Normalize academic text, stripping LaTeX accents, braces, and excess whitespace."""
    if not text:
        return ""
    t = text.lower()
    # Remove LaTeX commands like \textbf, \emph, etc.
    t = re.sub(r"\\[a-zA-Z]+", "", t)
    # Remove TeX braces
    t = re.sub(r"[{}\[\]\"'`]", "", t)
    # Replace hyphens and punctuation with spaces
    t = re.sub(r"[^\w\s]", " ", t)
    # Collapse whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def word_token_overlap(str1: str, str2: str) -> float:
    """Compute Jaccard token overlap between two strings."""
    tokens1 = set(clean_text_for_comparison(str1).split())
    tokens2 = set(clean_text_for_comparison(str2).split())
    # Exclude common stop words for sharper comparison
    stop = {"the", "a", "an", "on", "in", "of", "and", "for", "with", "to", "at", "by", "from"}
    tokens1 = {t for t in tokens1 if t not in stop and len(t) > 1}
    tokens2 = {t for t in tokens2 if t not in stop and len(t) > 1}
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


def string_similarity(str1: str, str2: str) -> float:
    """Compute overall similarity combining SequenceMatcher and token overlap."""
    c1 = clean_text_for_comparison(str1)
    c2 = clean_text_for_comparison(str2)
    if not c1 or not c2:
        return 0.0
    seq_ratio = difflib.SequenceMatcher(None, c1, c2).ratio()
    tok_ratio = word_token_overlap(str1, str2)
    return max(seq_ratio, tok_ratio)


def audit_discrepancies(
    claimed: ClaimedMetadata,
    verified_title: str | None,
    verified_authors: list[str],
    verified_year: int | None,
    verified_venue: str | None,
) -> list[Discrepancy]:
    """
    Compare user/bibtex claimed citation metadata with authoritative registry data.
    Returns a list of Discrepancy objects.
    """
    discrepancies: list[Discrepancy] = []

    # 1. Title Audit
    if claimed.title and verified_title:
        sim = string_similarity(claimed.title, verified_title)
        if sim < 0.60:
            discrepancies.append(
                Discrepancy(
                    field="title",
                    claimed=claimed.title,
                    verified=verified_title,
                    severity=Severity.ERROR,
                    message=f"Severe title mismatch (similarity {int(sim * 100)}%). This citation may point to the wrong paper.",
                )
            )
        elif sim < 0.85:
            discrepancies.append(
                Discrepancy(
                    field="title",
                    claimed=claimed.title,
                    verified=verified_title,
                    severity=Severity.WARNING,
                    message=f"Title discrepancy or typo (similarity {int(sim * 100)}%).",
                )
            )

    # 2. Year Audit
    if claimed.year and verified_year:
        diff = abs(claimed.year - verified_year)
        if diff >= 2:
            discrepancies.append(
                Discrepancy(
                    field="year",
                    claimed=claimed.year,
                    verified=verified_year,
                    severity=Severity.ERROR,
                    message=f"Publication year discrepancy: claimed {claimed.year} vs official registry {verified_year}.",
                )
            )
        elif diff == 1:
            discrepancies.append(
                Discrepancy(
                    field="year",
                    claimed=claimed.year,
                    verified=verified_year,
                    severity=Severity.INFO,
                    message=f"One year difference: preprint vs formal publication date (claimed {claimed.year} vs registry {verified_year}).",
                )
            )

    # 3. Authors Audit
    if claimed.authors and verified_authors:
        # Extract family name of first claimed author
        first_claimed = clean_text_for_comparison(claimed.authors[0]).split()
        first_claimed_family = first_claimed[-1] if first_claimed else ""

        # Check if first claimed author family name appears in verified authors
        found_first = False
        all_verified_text = clean_text_for_comparison(" ".join(verified_authors))
        if first_claimed_family and first_claimed_family in all_verified_text:
            found_first = True

        if not found_first and first_claimed_family:
            discrepancies.append(
                Discrepancy(
                    field="author",
                    claimed=claimed.authors[0],
                    verified=verified_authors[0] if verified_authors else "Unknown",
                    severity=Severity.WARNING,
                    message=f"First author mismatch: claimed first author '{claimed.authors[0]}' not identified in official registry author list.",
                )
            )

    # 4. Venue Audit
    if claimed.venue and verified_venue:
        venue_sim = string_similarity(claimed.venue, verified_venue)
        if venue_sim < 0.50:
            discrepancies.append(
                Discrepancy(
                    field="venue",
                    claimed=claimed.venue,
                    verified=verified_venue,
                    severity=Severity.INFO,
                    message=f"Venue name variation: claimed '{claimed.venue}' vs registry '{verified_venue}'.",
                )
            )

    return discrepancies
