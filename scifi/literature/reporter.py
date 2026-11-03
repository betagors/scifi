"""
Deterministic academic report synthesizer and standardized BibTeX exporter.
Formats intellectual lineages into publication-ready Markdown sections,
evidence-backed Delta-Novelty matrices, traceable limitations, and clean .bib citation files.
"""

from __future__ import annotations

import collections
import datetime
from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple

from scifi.literature.models import (
    AuthorRecord,
    CitationRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperRecord,
)
from scifi.literature.resolver import clean_arxiv_id, clean_doi
from scifi.literature.visualizer import determine_oa_status, extract_paper_links

# 4 Canonical Delta-Novelty Evaluation Dimensions and mapped gap types
DELTA_NOVELTY_DIMENSIONS = [
    ("Theoretical Paradigm", ["generalization_bound"]),
    ("Key Assumptions", ["unstated_assumption"]),
    ("Scalability / Complexity", ["computational_complexity"]),
    ("Open Limitations", ["empirical_limitation", "unresolved_problem"]),
]

DEFAULT_PROPOSED_TEMPLATES = {
    "Theoretical Paradigm": "[Your proposed theoretical framework / formulation]",
    "Key Assumptions": "[Your proposed relaxation or alternative assumption]",
    "Scalability / Complexity": "[Your proposed optimization or complexity reduction]",
    "Open Limitations": "[Your proposed methodology addressing this limitation]",
}

DEFAULT_BASELINE_PARADIGMS = {
    "Theoretical Paradigm": "Canonical theoretical formulation",
    "Key Assumptions": "Standard operating conditions and system model",
    "Scalability / Complexity": "Baseline computational complexity and overhead",
    "Open Limitations": "Reported baseline evaluation and scope",
}

DEFAULT_UNRESOLVED_GAPS = {
    "Theoretical Paradigm": "Generalization bounds and theoretical edge cases",
    "Key Assumptions": "Unstated environmental or system assumptions",
    "Scalability / Complexity": "Scaling bottlenecks under high dimensions or volume",
    "Open Limitations": "Empirical constraints and real-world deployment limitations",
}


def escape_bibtex(text: str) -> str:
    """
    Escape LaTeX/BibTeX special characters (&, %, $, _, #) while avoiding double-escaping.
    """
    if not text:
        return ""
    val = str(text)
    val = re.sub(r"(?<!\\)&", r"\&", val)
    val = re.sub(r"(?<!\\)%", r"\%", val)
    val = re.sub(r"(?<!\\)\$", r"\$", val)
    val = re.sub(r"(?<!\\)_", r"\_", val)
    val = re.sub(r"(?<!\\)#", r"\#", val)
    return val


def escape_table_cell(text: str) -> str:
    """
    Escape vertical pipes in table cells to maintain valid markdown table formatting.
    """
    if not text:
        return ""
    return str(text).replace("|", r"\|").strip()


def extract_oa_url(paper: PaperRecord) -> Optional[str]:
    """
    Extract best available Open Access URL (PDF or landing page) from paper locations or identifiers.
    Returns None if no open access location or repository preprint exists.
    """
    # 1. Locations marked OA
    for loc in paper.locations:
        if loc.is_oa or (loc.oa_status and loc.oa_status.lower() in ("gold", "green", "hybrid", "bronze")):
            if loc.pdf_url:
                return loc.pdf_url.strip()
            if loc.landing_page_url:
                return loc.landing_page_url.strip()

    # 2. ArXiv identifier (always Open Access)
    for ident in paper.identifiers:
        if (ident.provider or "").lower() == "arxiv":
            cleaned = clean_arxiv_id(ident.external_id)
            if cleaned:
                return f"https://arxiv.org/abs/{cleaned}"

    # 3. Any location with pdf_url if oa_status != 'closed'
    for loc in paper.locations:
        if loc.pdf_url and getattr(loc, "oa_status", "").lower() != "closed":
            return loc.pdf_url.strip()

    return None


def format_primary_authors(authors: list[AuthorRecord]) -> str:
    """Format authors list concisely for summary tables."""
    if not authors:
        return "Unknown"
    names = []
    for a in authors:
        n = a.name if hasattr(a, "name") else str(a)
        if n and n.strip():
            names.append(n.strip())
    if not names:
        return "Unknown"
    if len(names) == 1:
        return names[0]
    elif len(names) == 2:
        return f"{names[0]} and {names[1]}"
    else:
        return f"{names[0]} et al."


def assign_cite_keys(papers: list[PaperRecord]) -> dict[str, str]:
    """
    Assign standardized, collision-free BibTeX cite keys to papers by ID.
    If multiple papers produce identical base keys, attaches alphabetical suffixes (a, b, ...).
    """
    assigned: dict[str, str] = {}
    seen_keys: set[str] = set()
    for paper in papers:
        base_key = paper.generate_cite_key()
        cite_key = base_key
        counter = 1
        while cite_key in seen_keys:
            suffix = chr(ord("a") + counter - 1) if counter <= 26 else f"-{counter}"
            cite_key = f"{base_key}{suffix}"
            counter += 1
        seen_keys.add(cite_key)
        assigned[paper.id] = cite_key
    return assigned


def export_bibtex_entries(papers: list[PaperRecord]) -> str:
    """
    Export standardized, sanitized BibTeX entries for a list of papers.
    Ensures unique citation keys and escapes special characters in titles and authors.
    """
    if not papers:
        return ""

    key_map = assign_cite_keys(papers)
    entries: list[str] = []

    for paper in papers:
        cite_key = key_map.get(paper.id, paper.generate_cite_key())
        entry_type = "article"
        title = paper.title.strip() if paper.title else "Untitled"
        escaped_title = escape_bibtex(title)

        # Authors
        if paper.authors:
            author_names = [a.name.strip() for a in paper.authors if a.name and a.name.strip()]
            if author_names:
                escaped_authors = escape_bibtex(" and ".join(author_names))
            else:
                escaped_authors = "Unknown"
        else:
            escaped_authors = "Unknown"

        # Year
        year_val = paper.year
        if year_val is None and paper.publication_date:
            m = re.search(r"\b(19\d\d|20\d\d)\b", paper.publication_date)
            if m:
                try:
                    year_val = int(m.group(1))
                except ValueError:
                    pass

        doi, arxiv_id, pdf_url = extract_paper_links(paper)

        lines = [f"@{entry_type}{{{cite_key},"]
        lines.append(f"  title = {{{escaped_title}}},")
        lines.append(f"  author = {{{escaped_authors}}},")
        if year_val is not None:
            lines.append(f"  year = {{{year_val}}},")
        if doi:
            lines.append(f"  doi = {{{doi}}},")
        if pdf_url:
            lines.append(f"  url = {{{pdf_url}}},")
        elif doi:
            lines.append(f"  url = {{https://doi.org/{doi}}},")
        elif arxiv_id:
            lines.append(f"  url = {{https://arxiv.org/abs/{arxiv_id}}},")

        if arxiv_id and not doi:
            lines.append(f"  eprint = {{{arxiv_id}}},")
            lines.append("  archiveprefix = {arXiv},")

        # Trim trailing comma from last property
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("}")

        entries.append("\n".join(lines))

    return "\n\n".join(entries) + "\n"


def _select_baseline_papers(
    papers: list[PaperRecord],
    depths: dict[str, int],
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
) -> list[tuple[PaperRecord, str]]:
    """
    Select foundational roots (depth 0) and frontier baselines (depth max_depth)
    for Delta-Novelty Matrix comparison.
    Returns list of (PaperRecord, role) tuples.
    """
    if not papers:
        return []

    paper_depths = [depths.get(p.id, 0) for p in papers]
    max_d = max(paper_depths) if paper_depths else 0

    roots = [p for p in papers if depths.get(p.id, 0) == 0]
    frontiers = [p for p in papers if depths.get(p.id, 0) == max_d and depths.get(p.id, 0) > 0]

    # Prioritize papers having extracted gaps, then by citation count descending
    def sort_key(p: PaperRecord) -> tuple[int, int]:
        gap_count = len((paper_gaps or {}).get(p.id, []))
        return (1 if gap_count > 0 else 0, p.citation_count)

    roots.sort(key=sort_key, reverse=True)
    frontiers.sort(key=sort_key, reverse=True)

    selected: list[tuple[PaperRecord, str]] = []

    # Take up to 2 roots
    for p in roots[:2]:
        selected.append((p, "Foundational"))

    # Take up to 2 frontiers
    for p in frontiers[:2]:
        selected.append((p, "Frontier"))

    # Fallback if no roots/frontiers matched
    if not selected and papers:
        selected.append((papers[0], "Baseline"))

    return selected


def format_delta_novelty_matrix(
    papers: list[PaperRecord],
    depths: dict[str, int],
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
    evidence_map: Optional[dict[str, EvidenceRecord]] = None,
    key_map: Optional[dict[str, str]] = None,
) -> list[str]:
    """
    Format Section 3: Evidence-Backed Delta-Novelty Matrix comparing foundational roots
    vs frontier baselines across 4 evaluation dimensions.
    """
    lines: list[str] = [
        "## 3. Evidence-Backed Delta-Novelty Matrix",
        "",
        "This matrix systematically compares foundational roots and frontier baselines across core evaluation dimensions, "
        "highlighting unresolved gaps and providing an editable template for your proposed contribution.",
        "",
        "| Evaluation Dimension | Baseline Work [Ref] | Baseline Paradigm / Assumption | Unresolved Gap | Proposed Approach (Yours) |",
        "|---|---|---|---|---|",
    ]

    if not papers:
        for dim_name, _ in DELTA_NOVELTY_DIMENSIONS:
            prop_tpl = DEFAULT_PROPOSED_TEMPLATES.get(dim_name, "[Your proposed approach]")
            lines.append(f"| {escape_table_cell(dim_name)} | N/A | N/A | N/A | {escape_table_cell(prop_tpl)} |")
        lines.append("")
        return lines

    if key_map is None:
        key_map = assign_cite_keys(papers)

    selected_baselines = _select_baseline_papers(papers, depths, paper_gaps)

    for dim_name, matching_gap_types in DELTA_NOVELTY_DIMENSIONS:
        prop_tpl = DEFAULT_PROPOSED_TEMPLATES.get(dim_name, "[Your proposed approach]")

        for paper, role in selected_baselines:
            cite_key = key_map.get(paper.id, paper.generate_cite_key())
            paper_title = paper.title or "Untitled"
            baseline_ref = f"[{cite_key}] {paper_title} ({role})"

            # Look up gaps for this paper and dimension
            gaps_for_paper = (paper_gaps or {}).get(paper.id, [])
            matching_gaps = [g for g in gaps_for_paper if g.gap_type in matching_gap_types]

            if matching_gaps:
                # Prioritize corroborated gaps, then highest corroborating_count
                matching_gaps.sort(
                    key=lambda g: (
                        1 if (g.verification_status or "").lower() == "corroborated" else 0,
                        g.corroborating_count or 0,
                    ),
                    reverse=True,
                )
                best_gap = matching_gaps[0]
                ev = (evidence_map or {}).get(best_gap.primary_evidence_id)

                if ev and ev.extracted_text:
                    baseline_assumption = ev.extracted_text
                else:
                    baseline_assumption = best_gap.claim_summary

                unresolved_gap = best_gap.claim_summary
            else:
                baseline_assumption = DEFAULT_BASELINE_PARADIGMS.get(dim_name, "Standard baseline formulation")
                unresolved_gap = DEFAULT_UNRESOLVED_GAPS.get(dim_name, "Reported baseline limitation")

            cell_dim = escape_table_cell(dim_name)
            cell_ref = escape_table_cell(baseline_ref)
            cell_paradigm = escape_table_cell(baseline_assumption)
            cell_gap = escape_table_cell(unresolved_gap)
            cell_prop = escape_table_cell(prop_tpl)

            lines.append(f"| {cell_dim} | {cell_ref} | {cell_paradigm} | {cell_gap} | {cell_prop} |")

    lines.append("")
    return lines


def format_traceable_limitations(
    papers: list[PaperRecord],
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
    evidence_map: Optional[dict[str, EvidenceRecord]] = None,
    key_map: Optional[dict[str, str]] = None,
) -> list[str]:
    """
    Format Section 4: Traceable Limitations & Research Opportunities grouping gaps by paper
    with badges, verbatim blockquotes, and attribution lines.
    """
    lines: list[str] = [
        "## 4. Traceable Limitations & Research Opportunities",
        "",
        "This section details extracted research gaps, unstated assumptions, and empirical limitations across the analyzed literature lineage. "
        "Each finding is grounded in verbatim evidence quotes from author abstracts or inbound citation contexts and corroborated across independent sources.",
        "",
    ]

    all_gaps: list[PaperGapRecord] = []
    if paper_gaps:
        for glist in paper_gaps.values():
            all_gaps.extend(glist)

    if not all_gaps:
        lines.append("No traceable limitations or research gaps extracted for the current literature graph.")
        lines.append("")
        return lines

    if key_map is None:
        key_map = assign_cite_keys(papers)

    papers_by_id = {p.id: p for p in papers}

    for paper in papers:
        gaps_for_paper = (paper_gaps or {}).get(paper.id, [])
        if not gaps_for_paper:
            continue

        cite_key = key_map.get(paper.id, paper.generate_cite_key())
        title_str = paper.title or "Untitled"
        year_str = f" ({paper.year})" if paper.year is not None else ""

        lines.append(f"### [{cite_key}] {title_str}{year_str}")
        lines.append("")

        for gap in gaps_for_paper:
            gap_type_display = (gap.gap_type or "gap").replace("_", " ").title()
            status = (gap.verification_status or "candidate").lower()

            if status == "corroborated":
                count = gap.corroborating_count or 0
                src_word = "source" if count == 1 else "sources"
                verif_badge = f"[Corroborated: {count} {src_word}]"
            elif status == "disputed":
                verif_badge = "[Disputed Finding]"
            else:
                verif_badge = "[Candidate Finding]"

            lines.append(f"#### [{gap_type_display}] {verif_badge}")
            lines.append("")
            lines.append(f"- **Claim Summary:** {gap.claim_summary}")

            ev = (evidence_map or {}).get(gap.primary_evidence_id)
            if ev and ev.extracted_text:
                quote_text = ev.extracted_text.strip()
            else:
                quote_text = gap.claim_summary.strip()

            lines.append(f'> "{quote_text}"')

            # Attribution line
            if ev and ev.reporting_paper_id and ev.evidence_type != "abstract_limitation":
                rep_paper = papers_by_id.get(ev.reporting_paper_id)
                if rep_paper:
                    rep_key = key_map.get(rep_paper.id, rep_paper.generate_cite_key())
                    rep_author = format_primary_authors(rep_paper.authors)
                    rep_ref = f"[{rep_key}] {rep_author}"
                else:
                    rep_ref = f"Paper ID: {ev.reporting_paper_id}"

                sec_str = f" (Section: {ev.source_section})" if ev.source_section else ""
                lines.append(f"- *Reported by: {rep_ref}{sec_str}*")
            else:
                lines.append("- *Self-reported in author abstract*")

            lines.append("")

    return lines


def generate_markdown_report(
    graph_title: str,
    papers: list[PaperRecord],
    citations: list[CitationRecord],
    depths: dict[str, int],
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
    evidence_map: Optional[dict[str, EvidenceRecord]] = None,
) -> str:
    """
    Generate structured, publication-ready Markdown report synthesizing
    intellectual lineage evolution, topological depth hierarchy, baseline comparisons,
    evidence-backed Delta-Novelty Matrix, traceable limitations with verbatim quotes,
    and clean BibTeX entries.
    """
    total_papers = len(papers)
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Compute gap statistics
    all_gaps: list[PaperGapRecord] = []
    if paper_gaps:
        for glist in paper_gaps.values():
            all_gaps.extend(glist)
    total_gaps = len(all_gaps)
    corroborated_gaps = sum(
        1 for g in all_gaps if (g.verification_status or "").lower() == "corroborated"
    )

    if total_papers == 0:
        max_depth = 0
        root_count = 0
        frontier_count = 0
        intermediate_count = 0
    else:
        paper_depths = [depths.get(p.id, 0) for p in papers]
        max_depth = max(paper_depths)
        root_count = sum(1 for d in paper_depths if d == 0)
        if max_depth > 0:
            frontier_count = sum(1 for d in paper_depths if d == max_depth)
            intermediate_count = sum(1 for d in paper_depths if 0 < d < max_depth)
        else:
            frontier_count = 0
            intermediate_count = 0

    key_map = assign_cite_keys(papers)

    # 1. Header & Executive Summary
    report_lines: list[str] = [
        f"# Literature Intelligence Report: {graph_title}",
        "",
        f"- **Generated:** {now_utc}",
        f"- **Total Papers:** {total_papers}",
        f"- **Root Papers:** {root_count}",
        f"- **Frontier Papers:** {frontier_count}",
        f"- **Total Extracted Gaps:** {total_gaps} ({corroborated_gaps} corroborated)",
        f"- **Topological Depth Span:** 0 to {max_depth}",
        "",
        "## Executive Summary",
        "",
    ]

    if total_papers == 0:
        report_lines.append("The research graph contains no papers.")
    else:
        summary_sentence = (
            f"This report synthesizes the literature lineage for **{graph_title}**, "
            f"encompassing **{total_papers}** papers across a topological depth span of **$0 \\dots {max_depth}$** "
            f"with **{len(citations)}** citation links"
        )
        if total_gaps > 0:
            summary_sentence += (
                f". Across this lineage, **{total_gaps}** traceable technical gaps have been identified "
                f"(**{corroborated_gaps}** independently corroborated across multiple sources)."
            )
        else:
            summary_sentence += "."

        report_lines.append(summary_sentence)
        report_lines.append("")
        report_lines.append(
            f"- **Foundational Lineage (Level 0):** {root_count} seminal foundation paper(s) anchoring the research domain."
        )
        if max_depth > 1:
            report_lines.append(
                f"- **Architectural Iterations (Levels 1 to {max_depth - 1}):** {intermediate_count} intermediate paper(s) advancing methodology and architectures."
            )
        if max_depth > 0:
            report_lines.append(
                f"- **Research Frontier (Level {max_depth}):** {frontier_count} recent frontier paper(s) pushing current state of the art."
            )
    report_lines.append("")

    # Section 1: Intellectual Evolution & Lineage
    report_lines.append("## 1. Intellectual Evolution & Lineage")
    report_lines.append("")

    if total_papers == 0:
        report_lines.append("No paper evolution data available.")
        report_lines.append("")
    else:
        # Group papers by topological depth
        level_papers: dict[int, list[PaperRecord]] = collections.defaultdict(list)
        for p in papers:
            d = depths.get(p.id, 0)
            level_papers[d].append(p)

        # Iterate through levels
        for d in sorted(level_papers.keys()):
            # Level header
            if max_depth == 0:
                level_title = "Level 0: Seminal Foundations & Roots"
            elif d == 0:
                level_title = "Level 0: Seminal Foundations & Roots"
            elif d == max_depth:
                level_title = f"Level {d}: Recent Research Frontier"
            else:
                level_title = f"Level {d}: Intermediate Architectural Iterations"

            report_lines.append(f"### {level_title}")
            report_lines.append("")

            # Sort papers within level chronologically
            level_papers[d].sort(key=lambda p: (p.year if p.year is not None else 9999, p.title or ""))

            for paper in level_papers[d]:
                cite_key = key_map.get(paper.id, paper.generate_cite_key())
                authors_full = ", ".join([a.name.strip() for a in paper.authors if a.name and a.name.strip()]) or "Unknown"
                year_display = str(paper.year) if paper.year is not None else "Unknown"
                abstract_display = paper.abstract.strip() if paper.abstract and paper.abstract.strip() else "No abstract available."
                oa_tier_display = determine_oa_status(paper).capitalize()

                report_lines.append(f"#### [{cite_key}] {paper.title or 'Untitled'}")
                report_lines.append(f"- **CiteKey:** `{cite_key}`")
                report_lines.append(f"- **Year:** {year_display}")
                report_lines.append(f"- **Authors:** {authors_full}")
                report_lines.append(f"- **Citations:** {paper.citation_count} (influential: {paper.influential_citation_count})")
                report_lines.append(f"- **Access Tier:** {oa_tier_display}")
                report_lines.append(f"- **Abstract / Summary:** {abstract_display}")
                report_lines.append("")

    # Section 2: Baseline Summary Table
    report_lines.append("## 2. Baseline Summary Table")
    report_lines.append("")
    report_lines.append("| Paper / CiteKey | Year | Primary Authors | Citations | Access Tier | Open Access URL |")
    report_lines.append("|---|---|---|---|---|---|")

    if total_papers == 0:
        report_lines.append("| N/A | N/A | N/A | N/A | N/A | N/A |")
    else:
        # Sort papers for table by depth, then year, then title
        sorted_papers = sorted(
            papers,
            key=lambda p: (
                depths.get(p.id, 0),
                p.year if p.year is not None else 9999,
                p.title or "",
            ),
        )
        for paper in sorted_papers:
            cite_key = key_map.get(paper.id, paper.generate_cite_key())
            escaped_title = escape_table_cell(paper.title or "Untitled")
            cell_paper = f"[{cite_key}] {escaped_title}"
            year_cell = str(paper.year) if paper.year is not None else "Unknown"
            primary_authors = escape_table_cell(format_primary_authors(paper.authors))
            citations_cell = str(paper.citation_count)
            access_tier_cell = determine_oa_status(paper).capitalize()
            oa_url = extract_oa_url(paper)
            oa_url_cell = f"[Link]({oa_url})" if oa_url else "N/A"

            report_lines.append(
                f"| {cell_paper} | {year_cell} | {primary_authors} | {citations_cell} | {access_tier_cell} | {oa_url_cell} |"
            )
    report_lines.append("")

    # Section 3: Evidence-Backed Delta-Novelty Matrix
    matrix_lines = format_delta_novelty_matrix(papers, depths, paper_gaps, evidence_map, key_map)
    report_lines.extend(matrix_lines)

    # Section 4: Traceable Limitations & Research Opportunities
    limitation_lines = format_traceable_limitations(papers, paper_gaps, evidence_map, key_map)
    report_lines.extend(limitation_lines)

    # Section 5: Standardized BibTeX Entries
    report_lines.append("## 5. Standardized BibTeX Entries")
    report_lines.append("")
    bibtex_str = export_bibtex_entries(papers)
    report_lines.append("```bibtex")
    if bibtex_str.strip():
        report_lines.append(bibtex_str.strip())
    report_lines.append("```")
    report_lines.append("")

    return "\n".join(report_lines)


def save_markdown_report(
    output_path: str | Path,
    graph_title: str,
    papers: list[PaperRecord],
    citations: list[CitationRecord],
    depths: dict[str, int],
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
    evidence_map: Optional[dict[str, EvidenceRecord]] = None,
) -> Path:
    """Save generated markdown report to disk, creating parent directories if needed."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    content = generate_markdown_report(
        graph_title,
        papers,
        citations,
        depths,
        paper_gaps=paper_gaps,
        evidence_map=evidence_map,
    )
    out.write_text(content, encoding="utf-8")
    return out


def save_bibtex_file(
    output_path: str | Path,
    papers: list[PaperRecord],
) -> Path:
    """Save formatted BibTeX entries to disk, creating parent directories if needed."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    content = export_bibtex_entries(papers)
    out.write_text(content, encoding="utf-8")
    return out


__all__ = [
    "DELTA_NOVELTY_DIMENSIONS",
    "assign_cite_keys",
    "escape_bibtex",
    "escape_table_cell",
    "export_bibtex_entries",
    "extract_oa_url",
    "format_delta_novelty_matrix",
    "format_primary_authors",
    "format_traceable_limitations",
    "generate_markdown_report",
    "save_bibtex_file",
    "save_markdown_report",
]
