"""
FastMCP Router for Literature & Citations (Alex & Argus).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scifi.argus.engine import ArgusEngine
from scifi.argus.models import SuggestedAction
from scifi.argus.patcher import append_bibtex_entry, insert_cite_into_latex
from scifi.citation_verifier import (
    ClaimedMetadata,
    Severity,
    VerificationStatus,
    audit_discrepancies,
)
from scifi.server.app import DEFAULT_USER_AGENT, mcp


@mcp.tool()
def scifi_verify_citation(
    identifier: str,
    claimed_title: str | None = None,
    claimed_author: str | None = None,
    claimed_year: int | None = None,
    claimed_venue: str | None = None,
) -> dict[str, Any]:
    """
    Verify an academic citation by DOI, arXiv link, PubMed URL, or raw identifier.
    Uses local SQLite registry cache to avoid redundant network lookups.

    Args:
        identifier: DOI, arXiv link, PubMed URL, or publication identifier.
        claimed_title: Optional paper title claimed by the manuscript.
        claimed_author: Optional first or primary author claimed by the manuscript.
        claimed_year: Optional publication year claimed by the manuscript.
        claimed_venue: Optional publication venue claimed by the manuscript.

    Returns:
        Dictionary with verification status (VERIFIED, RETRACTED, ERRATA_EXISTS, MISMATCH, UNRESOLVED),
        canonical DOI, title, authors, publication year, venue, and detailed discrepancy flags.
    """
    import scifi.server as srv

    cache = srv.get_cache()
    cache_key = f"citation:{identifier}"
    cached = cache.get(cache_key)

    has_claimed = bool(claimed_title or claimed_author or claimed_year or claimed_venue)

    if cached is not None:
        canonical_data = cached
    else:
        # Fetch canonical metadata only (without claimed fields) to avoid caching per-call discrepancies
        meta = srv.verify_citation(query=identifier)
        canonical_data = meta.to_dict()
        if meta.status != VerificationStatus.UNRESOLVED:
            cache.set(cache_key, canonical_data)

    if not has_claimed or canonical_data.get("status") == VerificationStatus.UNRESOLVED.value:
        return canonical_data

    # Dynamically audit claimed fields against canonical verified metadata without polluting cache
    claimed = ClaimedMetadata(
        title=claimed_title,
        authors=[claimed_author] if claimed_author else [],
        year=claimed_year,
        venue=claimed_venue,
    )
    cached_authors = [a["name"] if isinstance(a, dict) else str(a) for a in canonical_data.get("authors", [])]
    discrepancies = audit_discrepancies(
        claimed,
        verified_title=canonical_data.get("title"),
        verified_authors=cached_authors,
        verified_year=canonical_data.get("year"),
        verified_venue=canonical_data.get("venue"),
    )
    result = dict(canonical_data)
    result["claimed_metadata"] = {
        "title": claimed_title,
        "authors": [claimed_author] if claimed_author else [],
        "year": claimed_year,
        "venue": claimed_venue,
    }
    result["discrepancies"] = [d.to_dict() for d in discrepancies]
    if (
        any(d.severity == Severity.ERROR for d in discrepancies)
        and result.get("status") == VerificationStatus.VERIFIED.value
    ):
        result["status"] = VerificationStatus.MISMATCH.value
    return result


@mcp.tool()
def scifi_audit_bib(
    bib_path: str,
    output_bib: str | None = None,
) -> dict[str, Any]:
    """
    Audit an entire BibTeX (.bib) file against academic registries (Crossref, OpenAlex, arXiv).
    Detects retracted papers, errata notices, title/author mismatches, and generates sanitized clean BibTeX entries.

    Args:
        bib_path: Path to the .bib file to audit.
        output_bib: Optional path where a clean, sanitized .bib file will be written.

    Returns:
        Dictionary with total entries, counts for verified, retracted, errata, mismatch, unresolved,
        detailed findings per entry, and markdown summary.
    """
    bib_file = Path(bib_path)
    if not bib_file.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {bib_path}",
        }

    import scifi.server as srv

    report = srv.audit_bib_file(bib_file)
    if output_bib:
        sanitized = srv.generate_sanitized_bib(report)
        out_path = Path(output_bib)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sanitized, encoding="utf-8")

    return {
        "file_path": str(bib_path),
        "total_entries": report.total_entries,
        "verified_count": report.verified_count,
        "retracted_count": report.retracted_count,
        "errata_count": report.errata_count,
        "mismatch_count": report.mismatch_count,
        "unresolved_count": report.unresolved_count,
        "entries": [e.to_dict() for e in report.entries],
        "output_bib": output_bib if output_bib else None,
        "summary": report.summary_markdown(),
    }


@mcp.tool()
def scifi_search_literature(
    query: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """
    Search OpenAlex and academic registries for canonical literature by title, topic, or phrase.

    Args:
        query: Literature query, paper title, or method keyword.
        limit: Maximum number of search results to return (default: 5).

    Returns:
        List of dictionaries with paper metadata (title, doi, authors, year, venue, citation_count, cite_key, bibtex).
    """
    import scifi.server as srv

    cache = srv.get_cache()
    cache_key = f"search:{query}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None and "results" in cached:
        return cached["results"]

    results: list[dict[str, Any]] = []
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    try:
        resp = srv.requests.get(
            "https://api.openalex.org/works",
            headers=headers,
            params={"search": query, "per_page": str(limit)},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for item in data.get("results", []):
                title = item.get("title", "")
                doi_raw = item.get("doi")
                doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi_raw) if doi_raw else None
                authors = [
                    a.get("author", {}).get("display_name", "")
                    for a in item.get("authorships", [])
                    if a.get("author", {}).get("display_name")
                ]
                year = item.get("publication_year")
                venue = (item.get("primary_location") or {}).get("source", {}).get("display_name")
                cite_count = item.get("cited_by_count", 0)

                first_author = authors[0].split()[-1] if authors else "Unknown"
                first_word = re.sub(r"[^\w]", "", title.split()[0]).capitalize() if title else "Paper"
                cite_key = f"{first_author}{year or 2026}{first_word}"

                author_str = " and ".join(authors) if authors else "Unknown Author"
                bibtex = (
                    f"@article{{{cite_key},\n"
                    f"  title = {{{title}}},\n"
                    f"  author = {{{author_str}}},\n"
                    f"  year = {{{year or ''}}},\n"
                    f"  journal = {{{venue or ''}}},\n"
                    f"  doi = {{{doi or ''}}}\n"
                    f"}}"
                )

                results.append(
                    {
                        "title": title,
                        "doi": doi,
                        "authors": authors,
                        "year": year,
                        "venue": venue,
                        "citation_count": cite_count,
                        "cite_key": cite_key,
                        "bibtex": bibtex,
                    }
                )
            if results:
                cache.set(cache_key, {"results": results})
    except Exception:
        pass

    return results


@mcp.tool()
def scifi_audit_attribution(
    file_path: str,
    bib_path: str | None = None,
    autofix: bool = False,
    enable_search: bool = True,
) -> dict[str, Any]:
    """
    Audit a LaTeX manuscript or text file for uncredited methods, algorithms, models, and plagiarism risks.
    If autofix=True, automatically inserts \\cite keys at flagged method occurrences in the LaTeX file
    and appends standardized BibTeX entries to the references file.

    Args:
        file_path: Path to the LaTeX (.tex) or text file to audit.
        bib_path: Optional path to the target references.bib file. Defaults to 'references.bib' in the same folder.
        autofix: Whether to automatically mutate LaTeX file with \\cite and append to bib_path.
        enable_search: Whether to query remote registries for seminal papers of uncredited methods.

    Returns:
        AttributionReport dictionary containing findings, categories, suggestions, and autofix results.
    """
    target_path = Path(file_path)
    if not target_path.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {file_path}",
        }

    engine = ArgusEngine(enable_search=enable_search)
    report = engine.audit_file(target_path)
    findings_dict = report.to_dict()

    if autofix:
        bib_file = Path(bib_path) if bib_path else target_path.parent / "references.bib"
        fixed_count = 0
        fixed_details = []
        for f in report.findings:
            if f.suggested_action == SuggestedAction.CITE and f.cite_key:
                bib_entry = f.bibtex_entry
                if not bib_entry:
                    bib_entry = (
                        f"@misc{{{f.cite_key},\n"
                        f"  title = {{{f.matched_entity}}},\n"
                        f"  note = {{Citation required for {f.matched_entity}}}\n"
                        f"}}\n"
                    )
                if f.line_number:
                    insert_cite_into_latex(
                        target_path,
                        line_number=f.line_number,
                        cite_key=f.cite_key,
                        target_entity=f.matched_entity,
                    )
                append_bibtex_entry(bib_file, bib_entry, f.cite_key)
                fixed_count += 1
                fixed_details.append(
                    {
                        "entity": f.matched_entity,
                        "cite_key": f.cite_key,
                        "line": f.line_number,
                    }
                )
        findings_dict["autofix"] = {
            "applied": True,
            "fixed_count": fixed_count,
            "bib_path": str(bib_file),
            "fixes": fixed_details,
        }
    else:
        findings_dict["autofix"] = {
            "applied": False,
            "fixed_count": 0,
        }

    return findings_dict
