"""
FastMCP Server Daemon for SciFi: Scientific Research & Academic Writing Toolkit.

Exposes 17 typed JSON-RPC tools for citation verification, bib auditing,
attribution & plagiarism detection, symbolic calculus, physical dimensions,
matrix shapes, LaTeX compilation, numerical curves, statistics, adversarial review,
and open-access literature retrieval.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
import requests

from scifi.argus.engine import ArgusEngine
from scifi.argus.models import SuggestedAction
from scifi.argus.patcher import append_bibtex_entry, insert_cite_into_latex
from scifi.argus.searcher import DEFAULT_USER_AGENT, ArgusSearcher
from scifi.cache import RegistryCache
from scifi.citation_verifier import (
    Author,
    CitationMetadata,
    ClaimedMetadata,
    Severity,
    VerificationStatus,
    audit_bib_file,
    audit_discrepancies,
    generate_sanitized_bib,
    verify_citation,
)
from scifi.latex import compile_latex
from scifi.literature import extract_pdf_text, fetch_paper_pdf
from scifi.math import (
    check_convexity,
    check_limits,
    check_matrix_shapes,
    check_notation,
    check_units,
    verify_derivation_step,
    verify_derivative,
)
from scifi.review import audit_claims
from scifi.stats import audit_statistics, verify_curve

mcp = FastMCP("scifi", instructions="Scientific Research & Academic Writing Toolkit")

_cache_instance: RegistryCache | None = None


def get_cache() -> RegistryCache:
    """Return the active RegistryCache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = RegistryCache()
    return _cache_instance


# ---------------------------------------------------------------------------
# 1. Literature & Citations (Alex)
# ---------------------------------------------------------------------------


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
    cache = get_cache()
    cache_key = f"citation:{identifier}"
    cached = cache.get(cache_key)

    has_claimed = bool(claimed_title or claimed_author or claimed_year or claimed_venue)

    if cached is not None:
        if not has_claimed:
            return cached

        # Re-audit claimed fields against cached verified metadata without remote network call
        claimed = ClaimedMetadata(
            title=claimed_title,
            authors=[claimed_author] if claimed_author else [],
            year=claimed_year,
            venue=claimed_venue,
        )
        cached_authors = [
            a["name"] if isinstance(a, dict) else str(a)
            for a in cached.get("authors", [])
        ]
        discrepancies = audit_discrepancies(
            claimed,
            verified_title=cached.get("title"),
            verified_authors=cached_authors,
            verified_year=cached.get("year"),
            verified_venue=cached.get("venue"),
        )
        result = dict(cached)
        result["claimed_metadata"] = {
            "title": claimed_title,
            "authors": [claimed_author] if claimed_author else [],
            "year": claimed_year,
            "venue": claimed_venue,
        }
        result["discrepancies"] = [d.to_dict() for d in discrepancies]
        if any(d.severity == Severity.ERROR for d in discrepancies) and result.get("status") == VerificationStatus.VERIFIED.value:
            result["status"] = VerificationStatus.MISMATCH.value
        return result

    meta = verify_citation(
        query=identifier,
        claimed_title=claimed_title,
        claimed_year=claimed_year,
        claimed_author=claimed_author,
        claimed_venue=claimed_venue,
    )
    data = meta.to_dict()
    if meta.status != VerificationStatus.UNRESOLVED:
        cache.set(cache_key, data)
    return data


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
    report = audit_bib_file(Path(bib_path))
    if output_bib:
        sanitized = generate_sanitized_bib(report)
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
    cache = get_cache()
    cache_key = f"literature_search:{query}:{limit}"
    cached = cache.get(cache_key)
    if cached is not None and "results" in cached:
        return cached["results"]

    results: list[dict[str, Any]] = []
    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    try:
        resp = requests.get(
            "https://api.openalex.org/works",
            headers=headers,
            params={"search": query, "per_page": limit},
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
                primary_loc = item.get("primary_location") or {}
                source = primary_loc.get("source") or {}
                venue = source.get("display_name") if source else None
                citation_count = item.get("cited_by_count", 0)

                author_objs = [Author.from_string(name) for name in authors]
                meta = CitationMetadata(
                    identifier_type="doi" if doi else "title",
                    identifier_value=doi if doi else title,
                    status=VerificationStatus.VERIFIED if doi else VerificationStatus.UNRESOLVED,
                    canonical_doi=doi,
                    title=title,
                    authors=author_objs,
                    year=year,
                    venue=venue,
                    citation_count=citation_count,
                )
                cite_key = meta.generate_cite_key()
                bibtex = meta.to_bibtex(key=cite_key)
                results.append({
                    "title": title,
                    "doi": doi,
                    "authors": authors,
                    "year": year,
                    "venue": venue,
                    "citation_count": citation_count,
                    "cite_key": cite_key,
                    "bibtex": bibtex,
                })
    except Exception:
        pass

    if not results:
        searcher = ArgusSearcher()
        canonical = searcher.search_canonical_work(query)
        if canonical:
            meta, conf, _ = canonical
            cite_key = meta.generate_cite_key()
            results.append({
                "title": meta.title,
                "doi": meta.canonical_doi,
                "authors": [a.name for a in meta.authors],
                "year": meta.year,
                "venue": meta.venue,
                "citation_count": meta.citation_count,
                "cite_key": cite_key,
                "bibtex": meta.to_bibtex(key=cite_key),
                "confidence": conf,
            })

    if results:
        cache.set(cache_key, {"results": results})
    return results


# ---------------------------------------------------------------------------
# 2. Attribution & Plagiarism (Argus)
# ---------------------------------------------------------------------------


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
                fixed_details.append({
                    "entity": f.matched_entity,
                    "cite_key": f.cite_key,
                    "line": f.line_number,
                })
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


# ---------------------------------------------------------------------------
# 3. Symbolic Math & Physics (Turing)
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_verify_derivative(
    expr: str,
    var: str,
    claimed: str,
) -> dict[str, Any]:
    """
    Symbolically verify an analytical derivative d(expr)/d(var) against a claimed expression using SymPy.

    Args:
        expr: Mathematical expression string or LaTeX (e.g. 'x**3 + 2*x' or '\\sin(x)').
        var: Differentiation variable (e.g. 'x').
        claimed: Claimed analytical derivative to verify against.

    Returns:
        Dictionary with status, is_correct flag, computed derivative, claimed derivative, and simplified difference.
    """
    return verify_derivative(expr=expr, var=var, claimed=claimed)


@mcp.tool()
def scifi_verify_derivation_step(
    lhs: str,
    rhs: str,
    assumptions: list[str] | None = None,
) -> dict[str, Any]:
    """
    Symbolically verify an algebraic derivation step asserting that LHS == RHS using SymPy.

    Args:
        lhs: Left-hand side mathematical expression.
        rhs: Right-hand side mathematical expression.
        assumptions: Optional list of algebraic assumptions (e.g. ['x > 0', 'n >= 1']).

    Returns:
        Dictionary with status, is_equivalent flag, simplified difference, and steps.
    """
    return verify_derivation_step(lhs=lhs, rhs=rhs, assumptions=assumptions)


@mcp.tool()
def scifi_check_units(
    lhs: str,
    rhs: str | None = None,
    check_mode: str = "eq",
) -> dict[str, Any]:
    """
    Verify physical dimensional homogeneity across equations or additive terms using Pint.

    Args:
        lhs: Left-hand expression with physical units (e.g. '10 * meter / second').
        rhs: Optional right-hand expression for equality checks (e.g. '36 * kilometer / hour').
        check_mode: 'eq' for equality or 'terms' for additive term consistency.

    Returns:
        Dictionary with status, is_consistent flag, reduced units, and dimensional analysis details.
    """
    return check_units(lhs=lhs, rhs=rhs, check_mode=check_mode)


@mcp.tool()
def scifi_check_matrix_shapes(
    operation: str,
    dimensions: dict[str, list[int | str]] | str,
) -> dict[str, Any]:
    """
    Verify linear algebra matrix product, vector multiplication, or tensor contraction shapes.

    Args:
        operation: Matrix operation string (e.g. 'A * B', 'A.T * B', 'X * W + b').
        dimensions: Dictionary mapping matrix symbols to shapes (e.g. {'A': [3, 4], 'B': [4, 5]}).

    Returns:
        Dictionary with status, is_valid flag, resulting shape, and step-by-step dimension propagation.
    """
    return check_matrix_shapes(operation=operation, dimensions=dimensions)


@mcp.tool()
def scifi_check_limits(
    expr: str,
    var: str,
    point: str,
    claimed: str,
    direction: str = "+-",
) -> dict[str, Any]:
    """
    Symbolically evaluate and verify asymptotic limits lim_{var -> point} expr == claimed using SymPy.

    Args:
        expr: Mathematical expression string or LaTeX.
        var: Limit variable (e.g. 'x', 'n').
        point: Limit target point (e.g. '0', 'oo', '-oo').
        claimed: Claimed limit value to verify against.
        direction: Approach direction: '+-' (bidirectional), '+' (right), or '-' (left).

    Returns:
        Dictionary with status, is_correct flag, computed limit, and claimed limit.
    """
    return check_limits(expr=expr, var=var, point=point, claimed=claimed, direction=direction)


@mcp.tool()
def scifi_check_convexity(
    expr: str,
    var: str,
    claimed: str = "convex",
) -> dict[str, Any]:
    """
    Verify convexity or concavity of a scalar objective function via its second derivative (Hessian).

    Args:
        expr: Objective expression string or LaTeX.
        var: Optimization variable (e.g. 'x').
        claimed: Claimed property: 'convex', 'strictly convex', 'concave', or 'strictly concave'.

    Returns:
        Dictionary with status, is_convex flag, second derivative expression, and sign analysis.
    """
    return check_convexity(expr=expr, var=var, claimed=claimed)


@mcp.tool()
def scifi_check_notation(
    tex_path: str,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """
    Audit manuscript LaTeX for mathematical symbol notation consistency, collisions, and overloading.

    Args:
        tex_path: Path to LaTeX manuscript file or raw LaTeX content.
        sections: Optional list of sections to restrict the audit to.

    Returns:
        Dictionary with status, symbols_found, collisions, and notation recommendations.
    """
    return check_notation(tex_content_or_path=tex_path, sections=sections)


# ---------------------------------------------------------------------------
# 4. LaTeX Compilation (Compiler)
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_compile_latex(
    entrypoint: str,
    engine: str = "latexmk",
    clean: bool = True,
) -> dict[str, Any]:
    """
    Autonomously compile LaTeX manuscripts with automated log error parsing and engine diagnostics.

    Args:
        entrypoint: Path to the main .tex manuscript file.
        engine: Compiler engine ('latexmk', 'pdflatex', 'xelatex', 'lualatex').
        clean: Whether to clean auxiliary build files upon completion.

    Returns:
        Dictionary with status (SUCCESS / ERROR), engine used, pdf_path, error list, and log excerpt.
    """
    return compile_latex(entrypoint=entrypoint, engine=engine, clean=clean)


# ---------------------------------------------------------------------------
# 5. Numerical Curves & Statistics (Gauss)
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_verify_curve(
    formula_latex: str,
    var_name: str,
    sim_data_path: str | None = None,
    x_vals: list[float] | None = None,
    y_vals: list[float] | None = None,
    x_col: str = "x",
    y_col: str = "y",
    rtol: float = 0.01,
    atol: float = 0.001,
) -> dict[str, Any]:
    """
    Verify that theoretical closed-form LaTeX formulas align with empirical simulation curves.

    Args:
        formula_latex: Theoretical mathematical equation (e.g. 'y = 2*x + 1' or '2*x + 1').
        var_name: Independent variable symbol (e.g. 'x').
        sim_data_path: Optional path to CSV or JSON file containing simulation points.
        x_vals: Optional list of independent variable sample values.
        y_vals: Optional list of empirical simulation values.
        x_col: Column name for x in CSV/JSON data (default: 'x').
        y_col: Column name for y in CSV/JSON data (default: 'y').
        rtol: Relative tolerance for numerical alignment (default: 0.01 = 1%).
        atol: Absolute tolerance for numerical alignment (default: 0.001).

    Returns:
        Dictionary with status, is_aligned flag, max_relative_error, max_absolute_error, and comparisons.
    """
    return verify_curve(
        formula_latex=formula_latex,
        var_name=var_name,
        sim_data_path=sim_data_path,
        x_vals=x_vals,
        y_vals=y_vals,
        x_col=x_col,
        y_col=y_col,
        rtol=rtol,
        atol=atol,
    )


@mcp.tool()
def scifi_audit_statistics(
    samples: list[float],
    confidence: float = 0.95,
) -> dict[str, Any]:
    """
    Audit empirical simulation data: compute confidence intervals and check Central Limit Theorem sample size (N >= 30).

    Args:
        samples: Array of numerical data observations.
        confidence: Confidence level for the interval (default: 0.95 for 95% CI).

    Returns:
        Dictionary with sample_size, mean, std_dev, std_error, confidence_interval, and clt_warning.
    """
    return audit_statistics(samples=samples, confidence=confidence)


# ---------------------------------------------------------------------------
# 6. Adversarial Review & Methodology (Popper)
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_audit_claims(
    file_path: str,
) -> dict[str, Any]:
    """
    Audit academic manuscript text for unstated assumptions, unhedged overclaims, and sweeping statements.

    Args:
        file_path: Path to LaTeX (.tex) or markdown/text manuscript file (or raw content string).

    Returns:
        Dictionary with status, total_flags, and detailed list of flagged statements with line numbers and reviewer critiques.
    """
    return audit_claims(tex_content_or_path=file_path)


# ---------------------------------------------------------------------------
# 7. Open-Access Literature Retrieval (Hypatia)
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_fetch_paper_pdf(
    identifier: str,
    output_dir: str = "workspace",
    email: str = "researcher@scifi.org",
) -> dict[str, Any]:
    """
    Fetch an open-access PDF for a paper by DOI or arXiv ID from arXiv, Unpaywall, or OpenAlex.

    Args:
        identifier: DOI (e.g. '10.1038/nature14539') or arXiv ID (e.g. '1706.03762').
        output_dir: Directory where the downloaded PDF should be stored.
        email: Contact email for polite OpenAlex/Unpaywall registry requests.

    Returns:
        Dictionary with status, identifier, file_path, source, and file size.
    """
    return fetch_paper_pdf(identifier=identifier, output_dir=output_dir, email=email)


@mcp.tool()
def scifi_extract_pdf_text(
    pdf_path: str,
    max_pages: int = 20,
) -> dict[str, Any]:
    """
    Extract structured text from a scientific paper PDF for synthesis, methodology audit, and delta-novelty matrix generation.

    Args:
        pdf_path: Path to the PDF file.
        max_pages: Maximum number of pages to extract text from (default: 20).

    Returns:
        Dictionary with status, page_count, extracted text, and detected paper sections.
    """
    return extract_pdf_text(pdf_path=pdf_path, max_pages=max_pages)


if __name__ == "__main__":
    mcp.run()
