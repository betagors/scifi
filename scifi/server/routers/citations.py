"""
FastMCP Router for Literature & Citations (Alex & Argus).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scifi.argus.engine import ArgusEngine
from scifi.argus.entailment import audit_claim_entailment
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
    strict_consensus: bool = False,
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
        strict_consensus: When True, require >=2 independent registries to confirm the reference.

    Returns:
        Dictionary with verification status (VERIFIED, RETRACTED, ERRATA_EXISTS, MISMATCH, UNRESOLVED),
        canonical DOI, title, authors, publication year, venue, and detailed discrepancy flags.
    """
    import scifi.server as srv

    cache = srv.get_cache()
    cache_key = f"citation:{identifier}:strict" if strict_consensus else f"citation:{identifier}"
    cached = cache.get(cache_key)

    has_claimed = bool(claimed_title or claimed_author or claimed_year or claimed_venue)

    if cached is not None:
        canonical_data = cached
    else:
        # Fetch canonical metadata only (without claimed fields) to avoid caching per-call discrepancies
        meta = srv.verify_citation(query=identifier, strict_consensus=strict_consensus)
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
    include_verified: bool = False,
    include_summary: bool = False,
    strict_consensus: bool = False,
) -> dict[str, Any]:
    """
    Audit an entire BibTeX (.bib) file against academic registries (Crossref, OpenAlex, arXiv).
    Detects retracted papers, errata notices, title/author mismatches, and generates sanitized clean BibTeX entries.

    Args:
        bib_path: Path to the .bib file to audit.
        output_bib: Optional path where a clean, sanitized .bib file will be written.
        include_verified: If True, include full metadata dicts for VERIFIED entries (default: False, returns only flagged entries).
        include_summary: If True, include redundant markdown summary alongside structured entries (default: False).
        strict_consensus: When True, require >=2 independent registries to confirm each reference.

    Returns:
        Dictionary with total entries, counts for verified, retracted, errata, mismatch, unresolved,
        and detailed findings for flagged entries (or all entries if include_verified=True).
    """
    bib_file = Path(bib_path)
    if not bib_file.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {bib_path}",
        }

    import scifi.server as srv

    report = srv.audit_bib_file(bib_file, cache=srv.get_cache(), strict_consensus=strict_consensus)
    if output_bib:
        sanitized = srv.generate_sanitized_bib(report)
        out_path = Path(output_bib)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(sanitized, encoding="utf-8")

    entries = (
        [e.to_dict() for e in report.entries]
        if include_verified
        else [e.to_dict() for e in report.entries if e.status != VerificationStatus.VERIFIED]
    )

    result: dict[str, Any] = {
        "file_path": str(bib_path),
        "total_entries": report.total_entries,
        "verified_count": report.verified_count,
        "retracted_count": report.retracted_count,
        "errata_count": report.errata_count,
        "mismatch_count": report.mismatch_count,
        "unresolved_count": report.unresolved_count,
        "entries": entries,
        "output_bib": output_bib if output_bib else None,
    }
    if not include_verified and report.verified_count > 0:
        result["verified_entries_omitted"] = report.verified_count
    if include_summary:
        result["summary"] = report.summary_markdown()
    return result


def _format_search_results(results: list[dict[str, Any]], include_bibtex: bool) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for r in results:
        item = dict(r)
        authors = item.get("authors") or []
        if len(authors) > 5:
            item["authors"] = authors[:5]
            item["total_authors"] = len(authors)
        if not include_bibtex:
            item.pop("bibtex", None)
        formatted.append(item)
    return formatted


@mcp.tool()
def scifi_search_literature(
    query: str,
    limit: int = 5,
    include_bibtex: bool = False,
) -> list[dict[str, Any]]:
    """
    Search OpenAlex and academic registries for canonical literature by title, topic, or phrase.

    Args:
        query: Literature query, paper title, or method keyword.
        limit: Maximum number of search results to return (default: 5).
        include_bibtex: If True, include generated BibTeX entry strings per result (default: False).

    Returns:
        List of dictionaries with paper metadata (title, doi, authors, year, venue, citation_count, cite_key).
    """
    import scifi.server as srv

    cache = srv.get_cache()
    cache_key = f"search:{query}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None and "results" in cached:
        return _format_search_results(cached["results"], include_bibtex=include_bibtex)

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

    return _format_search_results(results, include_bibtex=include_bibtex)


@mcp.tool()
def scifi_audit_attribution(
    file_path: str,
    bib_path: str | None = None,
    autofix: bool = False,
    enable_search: bool = True,
    include_full_candidates: bool = False,
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
        include_full_candidates: If True, include full CitationMetadata dicts inside candidate_work (default: False).

    Returns:
        AttributionReport dictionary containing findings, categories, suggestions, and autofix results.
    """
    target_path = Path(file_path)
    if not target_path.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {file_path}",
        }

    import scifi.server as srv

    engine = ArgusEngine(enable_search=enable_search, cache=srv.get_cache())
    report = engine.audit_file(target_path)
    findings_dict = report.to_dict(compact_candidate=not include_full_candidates)

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


@mcp.tool()
def scifi_audit_claim_entailment(
    file_path: str,
    bib_path: str | None = None,
    fetch_pdf: bool = True,
) -> dict[str, Any]:
    """
    Run a Hypatia-backed claim-to-citation entailment audit on a LaTeX manuscript.
    Checks whether each \\cite{} reference actually supports the claim in its sentence,
    flagging off-topic citations, contradictions, and missing cited metrics.

    Args:
        file_path: Path to the LaTeX (.tex), markdown, or project directory to audit.
        bib_path: Optional path to the .bib file resolving citation keys.
        fetch_pdf: Whether to fetch Unpaywall/arXiv PDFs when abstract is missing or lacks a cited metric.

    Returns:
        EntailmentReport dictionary with per-citation verdicts and aggregate counts.
    """
    target_path = Path(file_path)
    if not target_path.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {file_path}",
        }

    import scifi.server as srv

    report = audit_claim_entailment(
        target_path,
        bib_path=bib_path,
        fetch_pdf=fetch_pdf,
        cache=srv.get_cache(),
    )
    return report.to_dict()
