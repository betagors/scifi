"""
FastMCP Server Daemon for SciFi: Scientific Research & Academic Writing Toolkit.

Exposes 25 typed JSON-RPC tools for citation verification, bib auditing,
attribution & plagiarism detection, symbolic calculus, physical dimensions,
matrix shapes, LaTeX compilation, numerical curves, statistics, adversarial review,
and open-access literature retrieval.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

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
from scifi.doctor import audit_manuscript
from scifi.figures import audit_figure_accessibility
from scifi.human import audit_human_prose
from scifi.latex import check_venue_compliance, compile_latex, generate_latex_table
from scifi.layout import audit_trim_budget
from scifi.literature import extract_pdf_text, fetch_paper_pdf
from scifi.literature.benchmarks import CANONICAL_BENCHMARKS
from scifi.literature.lineage import LineageCrawler
from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    PaperRecord,
    ProjectRecord,
)
from scifi.literature.reporter import save_bibtex_file, save_markdown_report
from scifi.literature.reprint import (
    ingest_paper_copy,
    prepare_reprint_for_paper,
)
from scifi.literature.sota import SotaEvaluator
from scifi.literature.store import DEFAULT_CENTRAL_STORE_PATH, LiteratureStore
from scifi.literature.visualizer import save_interactive_html
from scifi.math import (
    check_convexity,
    check_limits,
    check_matrix_shapes,
    check_notation,
    check_units,
    verify_derivation_step,
    verify_derivative,
)
from scifi.proofs import audit_latex_proofs
from scifi.rebuttal import diff_manuscript, format_rebuttal_scaffold
from scifi.reproducibility import audit_reproducibility
from scifi.review import audit_claims
from scifi.shannon import evaluate_manuscript_metadata
from scifi.stats import audit_statistics, verify_curve
from scifi.submission import (
    generate_cover_letter,
    generate_highlights,
    generate_title_page,
    package_anonymous_code,
    prepare_submission_bundle,
)

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
        canonical_data = cached
    else:
        # Fetch canonical metadata only (without claimed fields) to avoid caching per-call discrepancies
        meta = verify_citation(query=identifier)
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

    report = audit_bib_file(bib_file)
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
                results.append(
                    {
                        "title": title,
                        "doi": doi,
                        "authors": authors,
                        "year": year,
                        "venue": venue,
                        "citation_count": citation_count,
                        "cite_key": cite_key,
                        "bibtex": bibtex,
                    }
                )
    except Exception:
        pass

    if not results:
        searcher = ArgusSearcher()
        canonical = searcher.search_canonical_work(query)
        if canonical:
            meta, conf, _ = canonical
            cite_key = meta.generate_cite_key()
            results.append(
                {
                    "title": meta.title,
                    "doi": meta.canonical_doi,
                    "authors": [a.name for a in meta.authors],
                    "year": meta.year,
                    "venue": meta.venue,
                    "citation_count": meta.citation_count,
                    "cite_key": cite_key,
                    "bibtex": meta.to_bibtex(key=cite_key),
                    "confidence": conf,
                }
            )

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
    max_section_length: int | None = None,
) -> dict[str, Any]:
    """
    Extract structured text from a scientific paper PDF for synthesis, methodology audit, and delta-novelty matrix generation.

    Args:
        pdf_path: Path to the PDF file.
        max_pages: Maximum number of pages to extract text from (default: 20).
        max_section_length: Optional maximum characters per extracted section (default: 15000).

    Returns:
        Dictionary with status, page_count, extracted text, and detected paper sections.
    """
    kwargs: dict[str, Any] = {"pdf_path": pdf_path, "max_pages": max_pages}
    if max_section_length is not None:
        kwargs["max_section_length"] = max_section_length
    return extract_pdf_text(**kwargs)


# ---------------------------------------------------------------------------
# 8. Literature Lineage & Knowledge Store (Discovery)
# ---------------------------------------------------------------------------

DEFAULT_LITERATURE_DB_PATH = DEFAULT_CENTRAL_STORE_PATH


def get_literature_store(db_path: Path | str | None = None) -> LiteratureStore:
    """Return a LiteratureStore instance for literature intelligence."""
    path = db_path or DEFAULT_CENTRAL_STORE_PATH
    return LiteratureStore(path)


def _resolve_project(
    store: LiteratureStore,
    project_name_or_path: str | Path | None = None,
) -> ProjectRecord | None:
    """
    Resolve a ProjectRecord from an ID, name, workspace path, or current working directory.
    If project_name_or_path is omitted, auto-discovers from Path.cwd().
    """
    if project_name_or_path:
        target_str = str(project_name_or_path).strip()
        if target_str.lower() == "all":
            return None
        # 1. Exact ID match
        proj = store.get_project(target_str)
        if proj is not None:
            return proj

        # 2. Canonical workspace path match
        target_path = Path(target_str).resolve()
        proj = store.get_project_by_workspace(target_path)
        if proj is not None:
            return proj

        # 3. Match by name or directory name
        all_projects = store.list_projects()
        for p in all_projects:
            if p.name.lower() == target_str.lower():
                return p
            if Path(p.workspace_path).name.lower() == target_str.lower():
                return p
            try:
                if Path(p.workspace_path).resolve() == target_path:
                    return p
            except Exception:
                pass
        return None

    # Omitted or None: auto-discover from Path.cwd()
    cwd = Path.cwd().resolve()
    proj = store.get_project_by_workspace(cwd)
    if proj is not None:
        return proj
    for p in store.list_projects():
        try:
            if Path(p.workspace_path).resolve() == cwd:
                return p
        except Exception:
            pass
    if (cwd / ".scifi").is_dir():
        manifest_file = cwd / ".scifi" / "literature_manifest.json"
        if manifest_file.exists():
            try:
                from scifi.literature.manifest import sync_workspace

                proj = sync_workspace(store, cwd)
            except Exception:
                proj = store.register_project(name=cwd.name, workspace_path=cwd)
        else:
            proj = store.register_project(name=cwd.name, workspace_path=cwd)
        if proj is not None:
            return proj

    # Walk up parent directories to find containing project
    for parent in cwd.parents:
        proj = store.get_project_by_workspace(parent)
        if proj is not None:
            return proj
        for p in store.list_projects():
            try:
                if Path(p.workspace_path).resolve() == parent:
                    return p
            except Exception:
                pass
        if (parent / ".scifi").is_dir():
            proj = store.get_project_by_workspace(parent)
            if proj is None:
                manifest_file = parent / ".scifi" / "literature_manifest.json"
                if manifest_file.exists():
                    try:
                        from scifi.literature.manifest import sync_workspace

                        proj = sync_workspace(store, parent)
                    except Exception:
                        proj = store.register_project(name=parent.name, workspace_path=parent)
                else:
                    proj = store.register_project(name=parent.name, workspace_path=parent)
            if proj is not None:
                return proj
    return None


@mcp.tool()
def scifi_map_literature(
    query: str,
    depth: int = 2,
    max_papers: int = 25,
    graph_id: str | None = None,
    output_dir: str | None = None,
    min_year: int | None = None,
    max_year: int | None = None,
    venue_tier: str | None = None,
    require_evidence: bool = False,
    extract_fulltext: bool = True,
    pdf_dir: str | None = None,
    auto_fetch_pdf: bool = False,
) -> dict[str, Any]:
    """
    Discover intellectual lineage and construct an interactive literature graph from a seed paper or query.
    Extracts foundational citations, frontier developments, persists to SQLite store, and optionally renders artifacts.

    Args:
        query: Seed paper title, DOI, arXiv ID, or OpenAlex ID.
        depth: Traversal hops backward (foundations) and forward (frontier) (default: 2).
        max_papers: Maximum number of papers to discover (default: 25).
        graph_id: Optional persistent graph session identifier.
        output_dir: Optional filesystem directory to save interactive HTML map, Markdown report, and references.bib.

    Returns:
        Dictionary with status ('SUCCESS' or 'ERROR'), graph_id, seed_paper_id, total_papers, total_citations,
        papers list, and generated file paths if output_dir specified.
    """
    store = get_literature_store()
    crawler = LineageCrawler(store=store)

    assigned_graph_id, papers, citations = crawler.crawl_lineage(
        query=query,
        depth=depth,
        max_papers=max_papers,
        graph_id=graph_id,
        min_year=min_year,
        max_year=max_year,
        venue_tier=venue_tier,
        require_evidence=require_evidence,
        extract_fulltext_gaps=extract_fulltext,
        pdf_dir=pdf_dir,
        auto_fetch_pdf=auto_fetch_pdf,
    )

    if not papers:
        return {
            "status": "ERROR",
            "message": f"Could not resolve seed paper or find literature for query: '{query}'",
            "graph_id": assigned_graph_id,
            "seed_paper_id": None,
            "total_papers": 0,
            "total_citations": 0,
            "gaps_count": 0,
            "corroborated_gaps_count": 0,
            "gaps": [],
            "papers": [],
            "benchmark_results_count": 0,
            "sota_leaders": [],
            "benchmarks": [],
            "files": None,
        }

    depths = crawler.compute_topological_depths(papers, citations)
    files_dict: dict[str, str] | None = None

    paper_gaps = store.get_graph_gaps(assigned_graph_id)
    evidence_map = store.get_graph_evidence(assigned_graph_id)
    benchmark_results = store.get_graph_benchmark_results(assigned_graph_id)
    benchmarks_map = store.get_graph_benchmarks(assigned_graph_id)
    metrics_map = store.get_graph_metrics(assigned_graph_id)
    conditions_map = store.get_graph_conditions(assigned_graph_id)

    total_gaps = sum(len(glist) for glist in paper_gaps.values())
    corroborated_count = sum(
        1 for glist in paper_gaps.values() for g in glist if g.verification_status == "corroborated"
    )
    gaps_list = [gap.to_dict() for glist in paper_gaps.values() for gap in glist]

    total_results = sum(len(rlist) for rlist in benchmark_results.values())
    sota_leaders = [r for rlist in benchmark_results.values() for r in rlist if r.is_sota]

    if output_dir:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        title = papers[0].title if papers else query
        seed_id = papers[0].id if papers else None

        html_path = save_interactive_html(
            out_path / "literature_map.html",
            graph_title=title,
            papers=papers,
            citations=citations,
            depths=depths,
            seed_paper_id=seed_id,
            paper_gaps=paper_gaps,
            evidence_map=evidence_map,
            benchmark_results=benchmark_results,
            benchmarks_map=benchmarks_map,
            metrics_map=metrics_map,
            conditions_map=conditions_map,
        )
        md_path = save_markdown_report(
            out_path / "literature_report.md",
            graph_title=title,
            papers=papers,
            citations=citations,
            depths=depths,
            paper_gaps=paper_gaps,
            evidence_map=evidence_map,
            benchmark_results=benchmark_results,
            benchmarks_map=benchmarks_map,
            metrics_map=metrics_map,
            conditions_map=conditions_map,
        )
        bib_path = save_bibtex_file(
            out_path / "references.bib",
            papers=papers,
        )

        files_dict = {
            "html_map": str(html_path.resolve()),
            "report_markdown": str(md_path.resolve()),
            "bibtex": str(bib_path.resolve()),
        }

    return {
        "status": "SUCCESS",
        "graph_id": assigned_graph_id,
        "seed_paper_id": papers[0].id if papers else None,
        "total_papers": len(papers),
        "total_citations": len(citations),
        "gaps_count": total_gaps,
        "corroborated_gaps_count": corroborated_count,
        "gaps": gaps_list,
        "benchmark_results_count": total_results,
        "sota_leaders": [r.to_dict() for r in sota_leaders],
        "benchmarks": [b.to_dict() for b in benchmarks_map.values()],
        "papers": [p.to_dict() for p in papers],
        "files": files_dict,
    }


@mcp.tool()
def scifi_query_sota_benchmarks(
    query: str,
    benchmark_name: str | None = None,
) -> dict[str, Any]:
    """
    Query benchmarks, active evaluation metrics, reported results, and current SOTA leaders for a research topic or benchmark name.
    Inspects canonical benchmark suites, domain taxonomies, and persisted empirical results to identify true state-of-the-art leaders and performance deltas.

    Args:
        query: Research domain, topic, paper title, DOI, or benchmark alias (e.g., 'Code Generation', 'HumanEval', 'Attention Is All You Need').
        benchmark_name: Optional explicit canonical benchmark name or ID to filter by (e.g., 'HumanEval', 'MMLU').

    Returns:
        Dictionary containing matched benchmarks, metrics, reported benchmark results, SOTA leaders, and performance deltas.
    """
    store = get_literature_store()
    q_clean = (query or "").strip().lower()
    bm_clean = (benchmark_name or "").strip().lower()

    matched_benchmarks: dict[str, BenchmarkRecord] = {}

    # 1. Check canonical benchmark catalog
    for bm_id, bm in CANONICAL_BENCHMARKS.items():
        if bm_clean:
            if bm_clean in bm.name.lower() or bm_clean in bm.id.lower() or bm_clean in bm.domain.lower():
                matched_benchmarks[bm.id] = bm
        elif q_clean:
            if (
                q_clean in bm.name.lower()
                or q_clean in bm.id.lower()
                or q_clean in bm.domain.lower()
                or (bm.description and q_clean in bm.description.lower())
            ):
                matched_benchmarks[bm.id] = bm

    # 2. Check benchmarks table in SQLite store
    try:
        with store._lock:
            cur = store.conn.cursor()
            cur.execute("SELECT id, name, domain, canonical_url, description FROM benchmarks")
            for r in cur.fetchall():
                bm = store._row_to_benchmark(r)
                if bm_clean:
                    if bm_clean in bm.name.lower() or bm_clean in bm.id.lower() or bm_clean in bm.domain.lower():
                        matched_benchmarks[bm.id] = bm
                elif q_clean:
                    if (
                        q_clean in bm.name.lower()
                        or q_clean in bm.id.lower()
                        or q_clean in bm.domain.lower()
                        or (bm.description and q_clean in bm.description.lower())
                    ):
                        matched_benchmarks[bm.id] = bm
    except Exception:
        pass

    # 3. Check matching papers by ID or title
    matched_paper_ids: set[str] = set()
    if q_clean:
        try:
            with store._lock:
                cur = store.conn.cursor()
                cur.execute(
                    "SELECT id, title FROM papers WHERE lower(id) LIKE ? OR lower(title) LIKE ?",
                    (f"%{q_clean}%", f"%{q_clean}%"),
                )
                for pid, ptitle in cur.fetchall():
                    matched_paper_ids.add(pid)
        except Exception:
            pass

    # 4. Query benchmark results for matched benchmarks and matched papers
    all_results: list[BenchmarkResultRecord] = []
    benchmark_ids = list(matched_benchmarks.keys())

    if benchmark_ids or matched_paper_ids:
        try:
            with store._lock:
                cur = store.conn.cursor()
                clauses: list[str] = []
                params: list[Any] = []
                if benchmark_ids:
                    ph = ",".join("?" for _ in benchmark_ids)
                    clauses.append(f"br.benchmark_id IN ({ph})")
                    params.extend(benchmark_ids)
                if matched_paper_ids:
                    ph = ",".join("?" for _ in matched_paper_ids)
                    clauses.append(f"br.paper_id IN ({ph})")
                    params.extend(list(matched_paper_ids))

                sql = f"""
                    SELECT br.id, br.paper_id, br.benchmark_id, br.metric_id, br.condition_id,
                           br.metric_value, br.is_sota, br.rank, br.evidence_id, br.table_or_figure,
                           br.result_date, br.provenance_source
                    FROM benchmark_results br
                    WHERE {" OR ".join(clauses)}
                    ORDER BY br.benchmark_id ASC, br.metric_value DESC, br.id ASC
                """
                cur.execute(sql, tuple(params))
                for r in cur.fetchall():
                    res = store._row_to_benchmark_result(r)
                    all_results.append(res)
                    if res.benchmark_id not in matched_benchmarks:
                        cur2 = store.conn.cursor()
                        cur2.execute(
                            "SELECT id, name, domain, canonical_url, description FROM benchmarks WHERE id = ?",
                            (res.benchmark_id,),
                        )
                        bm_row = cur2.fetchone()
                        if bm_row:
                            matched_benchmarks[res.benchmark_id] = store._row_to_benchmark(bm_row)
        except Exception:
            pass

    # 5. Fetch associated metrics, conditions, and paper records
    metrics_map: dict[str, EvaluationMetricRecord] = {}
    conditions_map: dict[str, EvaluationConditionRecord] = {}
    papers_map: dict[str, PaperRecord] = {}

    if all_results:
        metric_ids = list({r.metric_id for r in all_results if r.metric_id})
        condition_ids = list({r.condition_id for r in all_results if r.condition_id})
        paper_ids = list({r.paper_id for r in all_results if r.paper_id})

        try:
            with store._lock:
                cur = store.conn.cursor()
                if metric_ids:
                    ph = ",".join("?" for _ in metric_ids)
                    cur.execute(
                        f"SELECT id, name, goal, unit, description FROM evaluation_metrics WHERE id IN ({ph})",
                        tuple(metric_ids),
                    )
                    for mr in cur.fetchall():
                        metrics_map[mr[0]] = store._row_to_metric(mr)
                if condition_ids:
                    ph = ",".join("?" for _ in condition_ids)
                    cur.execute(
                        f"SELECT id, name, dataset_split, hardware, notes FROM evaluation_conditions WHERE id IN ({ph})",
                        tuple(condition_ids),
                    )
                    for cr in cur.fetchall():
                        conditions_map[cr[0]] = store._row_to_condition(cr)
                if paper_ids:
                    for pid in paper_ids:
                        p = store.get_paper(pid)
                        if p:
                            papers_map[pid] = p
        except Exception:
            pass

    # 6. Evaluate SOTA rankings and deltas if results exist
    deltas: list[dict[str, Any]] = []
    if all_results:
        try:
            evaluator = SotaEvaluator()
            papers_list = list(papers_map.values()) or [
                PaperRecord(id=r.paper_id, title=r.paper_id) for r in all_results
            ]
            sota_results = evaluator.evaluate_sota_frontier(
                papers=papers_list,
                benchmark_results=all_results,
                metrics=metrics_map,
                benchmarks=matched_benchmarks,
            )
            for rep in sota_results.values():
                for d in rep.deltas:
                    deltas.append(d.to_dict())
        except Exception:
            pass

    sota_leaders = [r for r in all_results if r.is_sota]

    return {
        "status": "SUCCESS",
        "query": query,
        "benchmark_name": benchmark_name,
        "total_benchmarks": len(matched_benchmarks),
        "benchmarks": [b.to_dict() for b in matched_benchmarks.values()],
        "metrics": [m.to_dict() for m in metrics_map.values()],
        "total_results": len(all_results),
        "results": [r.to_dict() for r in all_results],
        "sota_leaders": [r.to_dict() for r in sota_leaders],
        "deltas": deltas,
    }


@mcp.tool()
def scifi_query_store(
    query_sql: str,
) -> list[dict[str, Any]]:
    """
    Execute a read-only SQL SELECT query against the SciFi literature intelligence SQLite store.
    Strictly enforced via SQLite authorizer callbacks; rejecting any INSERT, UPDATE, DELETE, DROP, or ALTER.

    Args:
        query_sql: Read-only SQL SELECT statement.

    Returns:
        List of dictionaries representing rows returned by the query.

    Raises:
        PermissionError: If any non-read-only SQL statement is attempted.
    """
    store = get_literature_store()
    return store.execute_read_query(query_sql)


@mcp.tool()
def scifi_export_bibtex(
    graph_id: str,
    output_path: str,
) -> dict[str, Any]:
    """
    Export verified and standardized BibTeX entries for all papers in a specific literature graph session.

    Args:
        graph_id: Persistent literature graph session ID.
        output_path: Destination path for the generated .bib file.

    Returns:
        Dictionary with status ('SUCCESS' or 'ERROR'), graph_id, total_entries, and output_path.
    """
    store = get_literature_store()
    papers = store.get_graph_papers(graph_id)

    if not papers:
        return {
            "status": "ERROR",
            "message": f"No papers found for graph session '{graph_id}'",
            "graph_id": graph_id,
            "total_entries": 0,
            "output_path": None,
        }

    out_file = save_bibtex_file(output_path, papers)
    return {
        "status": "SUCCESS",
        "graph_id": graph_id,
        "total_entries": len(papers),
        "output_path": str(out_file.resolve()),
    }


# ---------------------------------------------------------------------------
# 9. Central Literature Hub, Projects & Author Reprints
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_list_projects() -> list[dict[str, Any]]:
    """
    List all registered research projects in the central literature knowledge store.

    Returns:
        List of project metadata dictionaries with ID, name, workspace_path,
        description, and timestamps.
    """
    store = get_literature_store()
    projects = store.list_projects()
    return [p.to_dict() for p in projects]


@mcp.tool()
def scifi_get_project_summary(
    project_name_or_path: str | None = None,
) -> dict[str, Any]:
    """
    Retrieve project statistics, paper counts, open-access distribution,
    and reprint requests for a registered project workspace.
    If project_name_or_path is omitted, auto-discovers from current working directory.

    Args:
        project_name_or_path: Optional project name, ID, or workspace path.

    Returns:
        Dictionary with status, project metadata, paper counts, open access counts,
        and pending reprint requests.
    """
    store = get_literature_store()
    proj = _resolve_project(store, project_name_or_path)
    if proj is None:
        return {
            "status": "NOT_FOUND",
            "message": f"Project '{project_name_or_path or Path.cwd()}' not found.",
            "available_projects": [p.name for p in store.list_projects()],
        }

    papers = store.get_project_papers(proj.id)
    reprints = store.get_reprint_requests(project_id=proj.id)

    oa_count = sum(1 for p in papers if any(loc.is_oa for loc in p.locations))
    paywalled_count = len(papers) - oa_count
    pending_reprints = [r for r in reprints if r.status in ("DRAFT_READY", "SENT")]
    received_reprints = [r for r in reprints if r.status == "RECEIVED"]

    return {
        "status": "SUCCESS",
        "project": proj.to_dict(),
        "total_papers": len(papers),
        "open_access_papers": oa_count,
        "paywalled_papers": paywalled_count,
        "total_reprint_requests": len(reprints),
        "pending_reprints_count": len(pending_reprints),
        "received_reprints_count": len(received_reprints),
        "pending_reprints": [r.to_dict() for r in pending_reprints],
    }


@mcp.tool()
def scifi_draft_reprint_request(
    identifier: str,
    project_name: str | None = None,
) -> dict[str, Any]:
    """
    Generate an academic-standard author reprint request letter and mailto URL
    for a paywalled paper. Queries public registries for author contact and saves
    the draft to the central literature store.

    Args:
        identifier: DOI or paper identifier (e.g. '10.1016/j.neucom.2023.12345').
        project_name: Optional project name, ID, or workspace path to link with.

    Returns:
        Dictionary containing status ('DRAFT_READY' or 'ERROR'), subject, body,
        mailto_url, author_name, and author_email.
    """
    store = get_literature_store()
    if project_name:
        if str(project_name).strip().lower() == "all":
            proj_id = None
        else:
            proj = _resolve_project(store, project_name)
            if proj is None:
                return {
                    "status": "ERROR",
                    "message": f"Project '{project_name}' not found.",
                    "identifier": identifier,
                }
            proj_id = proj.id
    else:
        proj = _resolve_project(store, None)
        proj_id = proj.id if proj else None

    try:
        req = prepare_reprint_for_paper(
            store=store,
            project_id=proj_id,
            paper_id=identifier,
        )
        return req.to_dict()
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e),
            "identifier": identifier,
        }


@mcp.tool()
def scifi_list_pending_reprints(
    project_name: str | None = None,
) -> list[dict[str, Any]]:
    """
    List pending reprint requests awaiting author responses (status DRAFT_READY or SENT).

    Args:
        project_name: Optional project name, ID, or workspace path filter.

    Returns:
        List of reprint request dictionaries.
    """
    store = get_literature_store()
    if project_name:
        if str(project_name).strip().lower() == "all":
            proj_id = None
        else:
            proj = _resolve_project(store, project_name)
            if proj is None:
                return []
            proj_id = proj.id
    else:
        proj = _resolve_project(store, None)
        proj_id = proj.id if proj else None

    requests = store.get_reprint_requests(project_id=proj_id)
    return [r.to_dict() for r in requests if r.status in ("DRAFT_READY", "SENT")]


@mcp.tool()
def scifi_ingest_paper_pdf(
    identifier: str,
    pdf_path: str,
    project_name: str | None = None,
) -> dict[str, Any]:
    """
    Ingest an acquired paper PDF copy into the content-addressed central store.
    Marks the paper location as accessible OA and transitions associated reprint
    requests to RECEIVED.

    Args:
        identifier: DOI or paper identifier.
        pdf_path: Local filesystem path to the PDF file.
        project_name: Optional project name, ID, or workspace path to link paper to.

    Returns:
        Dictionary with status ('SUCCESS' or 'ERROR'), stored_path, sha256, and paper_id.
    """
    store = get_literature_store()
    if project_name:
        if str(project_name).strip().lower() == "all":
            proj_id = None
        else:
            proj = _resolve_project(store, project_name)
            if proj is None:
                return {
                    "status": "ERROR",
                    "message": f"Project '{project_name}' not found.",
                    "identifier": identifier,
                }
            proj_id = proj.id
    else:
        proj = _resolve_project(store, None)
        proj_id = proj.id if proj else None

    try:
        return ingest_paper_copy(
            store=store,
            project_id=proj_id,
            paper_id=identifier,
            pdf_path=pdf_path,
        )
    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e),
            "identifier": identifier,
            "pdf_path": pdf_path,
        }


# ---------------------------------------------------------------------------
# 10. Unified Manuscript Audit, Shannon SEO, Tables & Venue Compliance
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_audit_manuscript(
    tex_or_dir_path: str = ".",
    bib_path: str | None = None,
    venue: str | None = None,
    double_blind: bool | None = None,
    compile_pdf: bool = False,
    live: bool = False,
    output_report: str | None = None,
) -> dict[str, Any]:
    """
    Run the complete 6-stage SciFi Manuscript Readiness Pipeline (doctor) across a single .tex
    file or multi-file LaTeX project directory (main.tex + sections/*.tex).
    Combines Alex (bib cross-check), Argus (attribution), Turing (cross-section notation),
    Popper (claims), Shannon (title/abstract triage), and Venue/Double-Blind compliance.
    """
    return audit_manuscript(
        tex_or_dir_path=tex_or_dir_path,
        bib_path=bib_path,
        venue=venue,
        double_blind=double_blind,
        compile_pdf=compile_pdf,
        live=live,
        output_report=output_report,
    )


@mcp.tool()
def scifi_evaluate_title_abstract(
    title: str | None = None,
    abstract: str | None = None,
    keywords: list[str] | str | None = None,
    tex_path: str | None = None,
    target_venue: str | None = None,
    live: bool = False,
) -> dict[str, Any]:
    """
    Evaluate academic manuscript title, 5-beat cognitive abstract, and author keywords
    using Shannon's 100-point Reviewer Triage Scorecard and SEO checks.
    Accepts either explicit title/abstract/keywords OR tex_path (single .tex or multi-file directory).
    """
    return evaluate_manuscript_metadata(
        title=title,
        abstract=abstract,
        keywords=keywords,
        tex_path=tex_path,
        target_venue=target_venue,
        live=live,
    )


@mcp.tool()
def scifi_generate_latex_table(
    data_input: str | list[dict[str, Any]],
    caption: str = "Experimental comparison against state-of-the-art baselines.",
    label: str = "tab:results",
    lower_is_better: list[str] | None = None,
    precision: int = 2,
    highlight_best: bool = True,
    highlight_second: bool = True,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate a publication-grade LaTeX booktabs table from CSV file, JSON file, or inline row objects.
    Automatically bolds best values (textbf), underlines second-best (underline), and pairs _std/_ci columns as $mean +- std$.
    """
    return generate_latex_table(
        data_input=data_input,
        caption=caption,
        label=label,
        lower_is_better=lower_is_better,
        precision=precision,
        highlight_best=highlight_best,
        highlight_second=highlight_second,
        output_path=output_path,
    )


@mcp.tool()
def scifi_check_venue_compliance(
    tex_or_dir_path: str,
    venue: str | None = None,
    double_blind: bool = False,
    author_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Audit a single-file or multi-file LaTeX project (main.tex + sections/*.tex) for venue compliance,
    double-blind anonymization leaks, forbidden negative vspace / margin hacks, and unreferenced floats.
    """
    return check_venue_compliance(
        tex_or_dir_path=tex_or_dir_path,
        venue=venue,
        double_blind=double_blind,
        author_names=author_names,
    )


@mcp.tool()
def scifi_audit_human(
    tex_or_dir_path: str,
    output_report: str | None = None,
) -> dict[str, Any]:
    """
    Audit a LaTeX manuscript (single .tex file or multi-file directory) or academic prose
    across 6 forensic stylometric and structural AI-detection dimensions:
    (1) List environments (R_IB bold ratio and item length CV),
    (2) Document preamble package stack and hyperref stereotyping,
    (3) Tabular column rigidity,
    (4) Macro abstraction ratio (mu_macro),
    (5) Mathematical syntax quirks (in-equation commentary rho_math_text, un-scoped subscripts, trapped punctuation),
    (6) Prose stylometry (Kobak et al. excess AI vocabulary, em-dashes, and sentence-length burstiness B_length).
    """
    return audit_human_prose(
        tex_or_dir_path=tex_or_dir_path,
        output_report=output_report,
    )


@mcp.tool()
def scifi_audit_figures(
    tex_path: str,
    base_dir: str | None = None,
    min_dpi: int = 300,
) -> dict[str, Any]:
    """
    Audit figures in a LaTeX manuscript for print resolution (min DPI >= 300),
    vector vs raster format for charts/plots, subfigure parity ((a), (b), (c) in body text),
    and colorblind accessibility (red/green curve collisions).
    """
    return audit_figure_accessibility(tex_path=tex_path, base_dir=base_dir, min_dpi=min_dpi)


@mcp.tool()
def scifi_trim_budget(
    tex_path: str,
    bib_path: str | None = None,
) -> dict[str, Any]:
    """
    Analyze LaTeX manuscript and BibTeX bibliography for legitimate typographic line savings:
    identifies widow/orphan lines in paragraphs (1-3 trailing words), condenses BibTeX conference/journal
    titles using standard ISO-4/IEEE abbreviations, and suggests float compaction.
    """
    res = audit_trim_budget(tex_path=tex_path, bib_path=bib_path)
    return res.to_dict()


@mcp.tool()
def scifi_audit_proofs(
    tex_path: str,
) -> dict[str, Any]:
    """
    Audit mathematical theorems, lemmas, propositions, and corollaries for completeness:
    detects orphan theorems lacking inline proofs or explicit pointers to appendix derivations,
    and verifies that referenced appendix labels exist.
    """
    res = audit_latex_proofs(tex_path=tex_path)
    return res.to_dict()


@mcp.tool()
def scifi_audit_reproducibility(
    tex_path: str,
    venue: str = "neurips",
    double_blind: bool = False,
) -> dict[str, Any]:
    """
    Audit manuscript against conference reproducibility checklists (NeurIPS/ICML/IEEE):
    checks for explicit random seeds, trial counts, error bars (+- std), compute hardware disclosures,
    hyperparameter specifications, and double-blind repository anonymization.
    """
    res = audit_reproducibility(tex_path=tex_path, venue=venue, double_blind=double_blind)
    return res.to_dict()


@mcp.tool()
def scifi_format_rebuttal(
    reviews_text: str,
    venue: str = "openreview",
) -> dict[str, Any]:
    """
    Parse raw peer reviews into a disciplined, 4-beat author response template:
    (1) Summary & Direct Answer, (2) Action Taken & Manuscript Revision,
    (3) Empirical/Theoretical Evidence, (4) Revised Manuscript Excerpt.
    """
    res = format_rebuttal_scaffold(reviews_text=reviews_text, venue=venue)
    return res.to_dict()


@mcp.tool()
def scifi_diff_manuscript(
    old_tex_path: str,
    new_tex_path: str,
    generate_pdf: bool = False,
    output_tex: str | None = None,
) -> dict[str, Any]:
    """
    Perform a section-by-section diff between two LaTeX manuscripts, generating a markdown diff ledger
    and invoking latexdiff (if installed) to generate marked-up LaTeX diff and revision PDF.
    """
    res = diff_manuscript(
        old_tex_path=old_tex_path,
        new_tex_path=new_tex_path,
        generate_pdf=generate_pdf,
        output_tex=output_tex,
    )
    return res.to_dict()


# ---------------------------------------------------------------------------
# 12. Academic Paper Submission Suite
# ---------------------------------------------------------------------------


@mcp.tool()
def scifi_generate_highlights(
    bullets: list[str] | str | None = None,
    venue: str = "general",
    manuscript_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate and validate 3-5 research highlights against venue character limits (e.g. Elsevier 85-char ceiling).
    """
    res = generate_highlights(
        bullets=bullets,
        venue=venue,
        manuscript_path=manuscript_path,
        output_path=output_path,
    )
    return res.to_dict()


@mcp.tool()
def scifi_generate_title_page(
    title: str | None = None,
    authors: list[dict[str, Any]] | list[str] | str | None = None,
    venue: str = "general",
    manuscript_path: str | None = None,
    funding: str | None = None,
    conflicts: str | None = None,
    data_availability: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate an unblinded standalone Title Page document (LaTeX and Markdown) for double-blind review fairness.
    """
    res = generate_title_page(
        title=title,
        authors=authors,
        venue=venue,
        manuscript_path=manuscript_path,
        funding=funding,
        conflicts=conflicts,
        data_availability=data_availability,
        output_path=output_path,
    )
    return res.to_dict()


@mcp.tool()
def scifi_generate_cover_letter(
    manuscript_title: str | None = None,
    journal_name: str = "Target Journal",
    venue: str = "general",
    issn: str | None = None,
    editor_name: str | None = None,
    authors: list[dict[str, Any]] | list[str] | str | None = None,
    figure_path: str | None = None,
    prior_doi: str | None = None,
    code_link: str | None = None,
    manuscript_path: str | None = None,
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Generate an academic editorial cover letter in Markdown and LaTeX format tailored to publisher guidelines.
    """
    res = generate_cover_letter(
        manuscript_title=manuscript_title,
        journal_name=journal_name,
        venue=venue,
        issn=issn,
        editor_name=editor_name,
        authors=authors,
        figure_path=figure_path,
        prior_doi=prior_doi,
        code_link=code_link,
        manuscript_path=manuscript_path,
        output_path=output_path,
    )
    return res.to_dict()


@mcp.tool()
def scifi_package_anonymous_code(
    code_dir: str,
    output_zip_path: str | None = None,
    author_names: list[str] | None = None,
) -> dict[str, Any]:
    """
    Package a code directory into a reproducible anonymous ZIP archive with git history, secrets, and author paths scrubbed.
    """
    res = package_anonymous_code(
        code_dir=code_dir,
        output_zip_path=output_zip_path,
        author_names=author_names,
    )
    return res.to_dict()


@mcp.tool()
def scifi_prepare_submission_bundle(
    target_dir_or_tex: str = ".",
    journal_name: str | None = None,
    venue: str = "general",
    issn: str | None = None,
    authors: list[dict[str, Any]] | list[str] | str | None = None,
    code_dir: str | None = None,
    no_code: bool = False,
    figure_path: str | None = None,
    prior_doi: str | None = None,
    funding: str | None = None,
    conflicts: str | None = None,
    editor_name: str | None = None,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    Generate all four submission artifacts (cover letter, highlights, title page, anonymous code zip) and packaging manifest in one shot.
    """
    res = prepare_submission_bundle(
        target_dir_or_tex=target_dir_or_tex,
        journal_name=journal_name,
        venue=venue,
        issn=issn,
        authors=authors,
        code_dir=code_dir,
        no_code=no_code,
        figure_path=figure_path,
        prior_doi=prior_doi,
        funding=funding,
        conflicts=conflicts,
        editor_name=editor_name,
        output_dir=output_dir,
    )
    return res.to_dict()


@mcp.tool()
def scifi_zotero_status() -> dict[str, Any]:
    """
    Check the status of the local Zotero library, data directory, and port 23119 server.
    """
    from scifi.env import auto_detect_zotero_dir, is_zotero_port_open
    from scifi.literature.zotero.reader import ZoteroLocalReader

    z_dir = auto_detect_zotero_dir()
    port_open = is_zotero_port_open()
    collections: list[dict[str, Any]] = []
    if z_dir:
        try:
            reader = ZoteroLocalReader(data_dir=z_dir)
            cols = reader.get_collections()
            collections = [{"id": c.collection_id, "name": c.name} for c in cols]
        except Exception:
            pass

    return {
        "status": "RUNNING" if port_open else ("INSTALLED_OFFLINE" if z_dir else "NOT_FOUND"),
        "detected": z_dir is not None,
        "data_dir": str(z_dir) if z_dir else None,
        "port_23119_open": port_open,
        "collections": collections,
    }


@mcp.tool()
def scifi_zotero_get_collection_papers(collection: str | None = None) -> list[dict[str, Any]]:
    """
    Retrieve papers belonging to a Zotero collection with their local PDF file paths.
    """
    from scifi.literature.zotero.reader import ZoteroLocalReader

    reader = ZoteroLocalReader()
    col = collection
    if not col:
        from pathlib import Path

        cfg = Path(".scifi/config.toml")
        if cfg.is_file():
            for line in cfg.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("collection ="):
                    col = line.split("=")[1].strip().strip('"').strip("'")
                    break

    items = reader.get_collection_items(col) if col else []
    return [
        {
            "key": it.key,
            "title": it.title,
            "doi": it.doi,
            "arxiv_id": it.arxiv_id,
            "year": it.year,
            "abstract": it.abstract,
            "pdf_path": str(it.pdf_path) if it.pdf_path else None,
            "tags": it.tags,
        }
        for it in items
    ]


@mcp.tool()
def scifi_zotero_get_annotations(item_key: str) -> list[dict[str, Any]]:
    """
    Retrieve user PDF highlights, notes, and comments for a Zotero paper.
    """
    from scifi.literature.zotero.reader import ZoteroLocalReader

    reader = ZoteroLocalReader()
    annos = reader.get_user_annotations(item_key)
    return [
        {
            "id": a.id,
            "type": a.type,
            "text": a.text,
            "comment": a.comment,
            "color": a.color,
            "page_label": a.page_label,
        }
        for a in annos
    ]


@mcp.tool()
def scifi_zotero_push_audit_note(item_key: str, audit_data: dict[str, Any]) -> dict[str, Any]:
    """
    Push or in-place upsert a SciFi audit card child note to a paper in Zotero.
    """
    from scifi.literature.zotero.models import ZoteroAuditCard
    from scifi.literature.zotero.writer import ZoteroLocalWriter

    card = ZoteroAuditCard(
        item_key=item_key,
        contribution=audit_data.get("contribution", "Scientific Contribution"),
        assumptions_flagged=audit_data.get("assumptions_flagged", []),
        benchmarks_extracted=audit_data.get("benchmarks_extracted", []),
        math_verified=audit_data.get("math_verified", False),
        retraction_status=audit_data.get("retraction_status", "OK"),
    )
    writer = ZoteroLocalWriter()
    res = writer.push_audit_card_note(item_key, card)
    if res.get("status") in ("CREATED", "UPDATED", "SUCCESS", "STAGED"):
        tags = ["#scifi-audited"]
        if card.assumptions_flagged:
            tags.append("#unstated-assumption")
        if card.math_verified and not card.assumptions_flagged:
            tags.append("#scifi-verified")
        writer.apply_tags(item_key, tags)
    return res


if __name__ == "__main__":
    mcp.run()
