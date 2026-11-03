"""
Interactive Vis.js Graph Visualizer for Academic Literature Lineage.
Generates standalone, XSS-safe HTML representations of intellectual DAGs
(Roots -> Intermediate Iterations -> Frontier) with color-coded access tiers,
hierarchical layout, and a responsive slide-out metadata drawer.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from scifi.literature.models import (
    BenchmarkRecord,
    BenchmarkResultRecord,
    CitationRecord,
    EvaluationConditionRecord,
    EvaluationMetricRecord,
    EvidenceRecord,
    PaperGapRecord,
    PaperRecord,
)
from scifi.literature.resolver import clean_arxiv_id, clean_doi

# Color palette for Open Access tiers
OA_COLORS: dict[str, str] = {
    "gold": "#10b981",  # Green
    "green": "#059669",  # Emerald
    "hybrid": "#f59e0b",  # Amber
    "bronze": "#d97706",  # Copper
    "closed": "#64748b",  # Slate
}

# Color palette for gap categories
GAP_CATEGORY_COLORS: dict[str, str] = {
    "computational_complexity": "#f59e0b",  # Amber
    "unstated_assumption": "#a855f7",  # Purple
    "empirical_limitation": "#f43f5e",  # Rose
    "generalization_bound": "#06b6d4",  # Cyan
    "unresolved_problem": "#6366f1",  # Indigo
}

SEED_BORDER_COLOR: str = "#3b82f6"  # Blue accent border
SOTA_BORDER_COLOR: str = "#d97706"  # Gold / Amber accent border
SOTA_BG_COLOR: str = "#fef3c7"      # Light gold tint background


def _safe_escape(val: Optional[str]) -> str:
    """Escape arbitrary text strings to neutralize HTML injection."""
    if not val:
        return ""
    return html.escape(str(val).strip(), quote=True)


def _safe_json_dumps(obj: Any) -> str:
    """
    Serialize object to JSON and replace angle brackets and ampersands
    with Unicode escape sequences to prevent script breakout attacks.
    """
    raw_json = json.dumps(obj, ensure_ascii=False)
    return (
        raw_json.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def determine_oa_status(paper: PaperRecord) -> str:
    """
    Determine dominant Open Access tier for a paper record:
    gold > green > hybrid > bronze > closed.
    """
    if hasattr(paper, "oa_status") and getattr(paper, "oa_status"):
        status = str(getattr(paper, "oa_status")).lower().strip()
        if status in OA_COLORS:
            return status

    if paper.locations:
        found_statuses = [
            loc.oa_status.lower().strip()
            for loc in paper.locations
            if getattr(loc, "oa_status", None)
        ]
        priority = ["gold", "green", "hybrid", "bronze", "closed"]
        for p in priority:
            if p in found_statuses:
                return p

        if any(getattr(loc, "is_oa", False) for loc in paper.locations):
            return "green"

    return "closed"


def extract_paper_links(paper: PaperRecord) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract DOI, arXiv ID, and PDF URL from identifiers and locations."""
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    pdf_url: Optional[str] = None

    for ident in paper.identifiers:
        prov = (ident.provider or "").lower()
        if prov == "doi" and not doi:
            cleaned = clean_doi(ident.external_id)
            if cleaned:
                doi = cleaned
        elif prov == "arxiv" and not arxiv_id:
            cleaned = clean_arxiv_id(ident.external_id)
            if cleaned:
                arxiv_id = cleaned

    if not doi:
        for v in paper.versions:
            if v.doi:
                cleaned = clean_doi(v.doi)
                if cleaned:
                    doi = cleaned
                    break

    for loc in paper.locations:
        if loc.pdf_url:
            raw_url = loc.pdf_url.strip()
            if raw_url.startswith("http://") or raw_url.startswith("https://"):
                pdf_url = raw_url
                break

    return doi, arxiv_id, pdf_url


def format_node_label(paper: PaperRecord) -> str:
    """
    Format node label: First author + Year + Truncated Title.
    E.g. 'Vaswani et al. (2017)\\nAttention Is All You Need'
    """
    if paper.authors:
        first = paper.authors[0]
        name = first.name if hasattr(first, "name") else str(first)
        name = name.strip() if name else ""
        if "," in name:
            last = name.split(",")[0].strip()
        else:
            parts = name.split()
            last = parts[-1] if parts else name
        author_str = f"{last} et al." if len(paper.authors) > 1 else last
    else:
        author_str = "Unknown"

    year_str = str(paper.year) if paper.year is not None else "n.d."
    title = (paper.title or "Untitled").strip()
    truncated_title = (title[:35] + "...") if len(title) > 38 else title

    return f"{author_str} ({year_str})\n{truncated_title}"


def generate_interactive_html(
    graph_title: str,
    papers: list[PaperRecord],
    citations: list[CitationRecord],
    depths: dict[str, int],
    seed_paper_id: Optional[str] = None,
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
    evidence_map: Optional[dict[str, EvidenceRecord]] = None,
    benchmark_results: Optional[dict[str, list[BenchmarkResultRecord]]] = None,
    benchmarks_map: Optional[dict[str, BenchmarkRecord]] = None,
    metrics_map: Optional[dict[str, EvaluationMetricRecord]] = None,
    conditions_map: Optional[dict[str, EvaluationConditionRecord]] = None,
    node_roles: Optional[dict[str, str]] = None,
) -> str:
    """
    Render self-contained, XSS-safe Vis.js interactive HTML visualization of a literature DAG.
    """
    sanitized_graph_title = _safe_escape(graph_title)
    paper_ids = {p.id for p in papers}

    # Prepare Vis.js nodes dataset and drawer metadata map
    vis_nodes: list[dict[str, Any]] = []
    papers_data: dict[str, Any] = {}

    for paper in papers:
        oa_tier = determine_oa_status(paper)
        bg_color = OA_COLORS.get(oa_tier, OA_COLORS["closed"])
        is_seed = (paper.id == seed_paper_id) or getattr(paper, "is_seed", False) or (getattr(paper, "node_role", "") == "seed")

        # Determine SOTA leader status
        paper_bms = (benchmark_results or {}).get(paper.id, [])
        role = (node_roles or {}).get(paper.id) or getattr(paper, "node_role", "")
        has_sota_result = any(getattr(r, "is_sota", False) for r in paper_bms)
        is_sota_leader = has_sota_result or (role == "sota_leader")

        if is_sota_leader:
            node_bg = SOTA_BG_COLOR
            node_border = SOTA_BORDER_COLOR
            border_width = 4
            highlight_border = "#f59e0b"
            highlight_bg = SOTA_BG_COLOR
            hover_border = SOTA_BORDER_COLOR
            hover_bg = SOTA_BG_COLOR
            font_color = "#78350f"
        elif is_seed:
            node_bg = bg_color
            node_border = SEED_BORDER_COLOR
            border_width = 4
            highlight_border = "#2563eb"
            highlight_bg = bg_color
            hover_border = "#3b82f6"
            hover_bg = bg_color
            font_color = "#ffffff"
        else:
            node_bg = bg_color
            node_border = bg_color
            border_width = 2
            highlight_border = "#1e293b"
            highlight_bg = bg_color
            hover_border = "#3b82f6"
            hover_bg = bg_color
            font_color = "#ffffff"

        depth_level = depths.get(paper.id, 0)
        base_label = format_node_label(paper)
        node_label = f"[⭐ SOTA Leader]\n{base_label}" if is_sota_leader else base_label

        title_prefix = "[⭐ SOTA Leader] " if is_sota_leader else ""
        tooltip = _safe_escape(f"{title_prefix}{paper.title} ({paper.year or 'n.d.'})")

        doi, arxiv_id, pdf_url = extract_paper_links(paper)

        vis_nodes.append({
            "id": paper.id,
            "label": node_label,
            "level": depth_level,
            "title": tooltip,
            "color": {
                "background": node_bg,
                "border": node_border,
                "highlight": {
                    "background": highlight_bg,
                    "border": highlight_border,
                },
                "hover": {
                    "background": hover_bg,
                    "border": hover_border,
                },
            },
            "borderWidth": border_width,
            "font": {
                "color": font_color,
                "size": 13,
                "bold": {"color": font_color},
            },
            "shape": "box",
            "margin": 10,
        })

        author_list = []
        for a in paper.authors:
            author_list.append({
                "name": _safe_escape(a.name if hasattr(a, "name") else str(a)),
                "institution": _safe_escape(getattr(a, "institution", "") or ""),
                "email": _safe_escape(getattr(a, "email", "") or ""),
            })

        gaps_list = []
        for gap in (paper_gaps or {}).get(paper.id, []):
            ev = (evidence_map or {}).get(gap.primary_evidence_id) if evidence_map else None
            ev_data = None
            if ev:
                ev_data = {
                    "id": _safe_escape(ev.id),
                    "paper_id": _safe_escape(ev.paper_id),
                    "evidence_type": _safe_escape(ev.evidence_type),
                    "extracted_text": _safe_escape(ev.extracted_text),
                    "extraction_method": _safe_escape(ev.extraction_method),
                    "reporting_paper_id": _safe_escape(ev.reporting_paper_id or ""),
                    "source_section": _safe_escape(ev.source_section or ""),
                    "source_location": _safe_escape(ev.source_location or ""),
                    "confidence": ev.confidence,
                }

            verif_status = (gap.verification_status or "candidate").lower()
            if verif_status == "corroborated":
                count = gap.corroborating_count or 0
                verif_label = f"Corroborated ({count} {'source' if count == 1 else 'sources'})"
            elif verif_status == "disputed":
                verif_label = "Disputed Finding"
            else:
                verif_label = "Candidate Finding"

            cat_label = (gap.gap_type or "GAP").replace("_", " ").upper()

            gaps_list.append({
                "id": _safe_escape(gap.id),
                "paper_id": _safe_escape(gap.paper_id),
                "gap_type": _safe_escape(gap.gap_type),
                "category_label": _safe_escape(cat_label),
                "claim_summary": _safe_escape(gap.claim_summary),
                "primary_evidence_id": _safe_escape(gap.primary_evidence_id),
                "verification_status": _safe_escape(gap.verification_status),
                "verification_label": _safe_escape(verif_label),
                "corroborating_count": gap.corroborating_count,
                "contradicting_count": gap.contradicting_count,
                "evidence": ev_data,
            })

        benchmarks_list = []
        for res in paper_bms:
            bm = (benchmarks_map or {}).get(res.benchmark_id)
            bm_name = bm.name if bm else res.benchmark_id
            bm_domain = bm.domain if (bm and bm.domain) else ""

            metric = (metrics_map or {}).get(res.metric_id)
            metric_name = metric.name if metric else res.metric_id
            metric_unit = metric.unit if (metric and metric.unit) else ""

            cond = (conditions_map or {}).get(res.condition_id) if (res.condition_id and conditions_map) else None
            cond_name = cond.name if cond else (res.condition_id or "")
            cond_split = cond.dataset_split if (cond and cond.dataset_split) else ""
            cond_notes = cond.notes if (cond and cond.notes) else ""

            ev = (evidence_map or {}).get(res.evidence_id) if (res.evidence_id and evidence_map) else None
            ev_data = None
            if ev:
                ev_data = {
                    "id": _safe_escape(ev.id),
                    "extracted_text": _safe_escape(ev.extracted_text),
                    "source_section": _safe_escape(ev.source_section or ""),
                    "source_location": _safe_escape(ev.source_location or ""),
                    "extraction_method": _safe_escape(ev.extraction_method or ""),
                }

            if metric_unit:
                unit_str = f"{metric_unit}" if metric_unit == "%" else f" {metric_unit}"
                formatted_score = f"{metric_name}: {res.metric_value:g}{unit_str}"
            else:
                formatted_score = f"{metric_name}: {res.metric_value:g}"

            benchmarks_list.append({
                "id": _safe_escape(res.id),
                "benchmark_id": _safe_escape(res.benchmark_id),
                "benchmark_name": _safe_escape(bm_name),
                "benchmark_domain": _safe_escape(bm_domain),
                "metric_id": _safe_escape(res.metric_id),
                "metric_name": _safe_escape(metric_name),
                "metric_value": res.metric_value,
                "metric_unit": _safe_escape(metric_unit),
                "formatted_score": _safe_escape(formatted_score),
                "is_sota": bool(res.is_sota),
                "rank": res.rank,
                "table_or_figure": _safe_escape(res.table_or_figure or ""),
                "condition_name": _safe_escape(cond_name),
                "condition_split": _safe_escape(cond_split),
                "condition_notes": _safe_escape(cond_notes),
                "provenance_source": _safe_escape(res.provenance_source or ""),
                "evidence": ev_data,
            })

        papers_data[paper.id] = {
            "id": paper.id,
            "title": _safe_escape(paper.title or "Untitled"),
            "year": paper.year,
            "publication_date": _safe_escape(paper.publication_date or ""),
            "cite_key": _safe_escape(paper.generate_cite_key()),
            "citation_count": paper.citation_count,
            "influential_citation_count": paper.influential_citation_count,
            "oa_status": oa_tier,
            "is_seed": is_seed,
            "is_sota_leader": is_sota_leader,
            "doi": _safe_escape(doi or ""),
            "arxiv_id": _safe_escape(arxiv_id or ""),
            "pdf_url": _safe_escape(pdf_url or ""),
            "abstract": _safe_escape(paper.abstract or "No abstract available."),
            "authors": author_list,
            "gaps": gaps_list,
            "benchmarks": benchmarks_list,
        }

    # Prepare Vis.js edges
    vis_edges: list[dict[str, Any]] = []
    for c in citations:
        if c.source_paper_id not in paper_ids or c.target_paper_id not in paper_ids:
            continue

        # In lineage DAG, edges flow from Foundations (Roots, depth 0) -> Frontier (depth D)
        source_depth = depths.get(c.source_paper_id, 0)
        target_depth = depths.get(c.target_paper_id, 0)

        if target_depth <= source_depth:
            from_node = c.target_paper_id
            to_node = c.source_paper_id
        else:
            from_node = c.source_paper_id
            to_node = c.target_paper_id

        vis_edges.append({
            "from": from_node,
            "to": to_node,
            "arrows": {
                "to": {
                    "enabled": True,
                    "scaleFactor": 0.8,
                }
            },
            "width": 2.5 if c.is_influential else 1.2,
            "color": {
                "color": "#3b82f6" if c.is_influential else "#94a3b8",
                "highlight": "#1d4ed8",
                "hover": "#2563eb",
            },
            "title": "Influential Citation" if c.is_influential else "Citation",
        })

    safe_nodes_json = _safe_json_dumps(vis_nodes)
    safe_edges_json = _safe_json_dumps(vis_edges)
    safe_papers_json = _safe_json_dumps(papers_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{sanitized_graph_title}</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    :root {{
      --bg-canvas: #f8fafc;
      --card-bg: #ffffff;
      --text-main: #0f172a;
      --text-muted: #64748b;
      --border-color: #e2e8f0;
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --seed-accent: #3b82f6;
      --sota-accent: #d97706;
      --sota-bg: #fef3c7;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    body, html {{
      width: 100%;
      height: 100%;
      overflow: hidden;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: var(--bg-canvas);
      color: var(--text-main);
    }}
    #app-container {{
      display: flex;
      flex-direction: column;
      width: 100vw;
      height: 100vh;
      position: relative;
    }}
    #top-bar {{
      height: 56px;
      background: var(--card-bg);
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      z-index: 10;
      box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }}
    .title-group {{
      display: flex;
      align-items: baseline;
      gap: 12px;
    }}
    .graph-title {{
      font-size: 1.15rem;
      font-weight: 700;
      color: var(--text-main);
    }}
    .graph-stats {{
      font-size: 0.85rem;
      color: var(--text-muted);
    }}
    .legend {{
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 0.8rem;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 5px;
    }}
    .legend-color {{
      width: 12px;
      height: 12px;
      border-radius: 3px;
    }}
    .legend-seed {{
      width: 12px;
      height: 12px;
      border: 2px solid var(--seed-accent);
      border-radius: 3px;
      background: #e2e8f0;
    }}
    .legend-sota {{
      width: 12px;
      height: 12px;
      border: 2px solid var(--sota-accent);
      border-radius: 3px;
      background: var(--sota-bg);
    }}
    #network-container {{
      flex: 1;
      width: 100%;
      height: calc(100vh - 56px);
      background-color: var(--bg-canvas);
    }}
    /* Details Drawer */
    #details-drawer {{
      position: fixed;
      top: 0;
      right: 0;
      width: 440px;
      max-width: 90vw;
      height: 100vh;
      background: var(--card-bg);
      border-left: 1px solid var(--border-color);
      box-shadow: -8px 0 24px rgba(0,0,0,0.12);
      transform: translateX(100%);
      transition: transform 0.28s cubic-bezier(0.4, 0, 0.2, 1);
      z-index: 100;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
    }}
    #details-drawer.open {{
      transform: translateX(0);
    }}
    .drawer-header {{
      padding: 20px 24px 16px 24px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      position: sticky;
      top: 0;
      background: var(--card-bg);
      z-index: 2;
    }}
    .drawer-badges {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      align-items: center;
    }}
    .badge {{
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 0.72rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge-oa-gold {{ background: #d1fae5; color: #065f46; }}
    .badge-oa-green {{ background: #a7f3d0; color: #047857; }}
    .badge-oa-hybrid {{ background: #fef3c7; color: #92400e; }}
    .badge-oa-bronze {{ background: #ffedd5; color: #9a3412; }}
    .badge-oa-closed {{ background: #f1f5f9; color: #475569; }}
    .badge-seed {{ background: #dbeafe; color: #1e40af; border: 1px solid #3b82f6; }}
    .badge-sota {{ background: #fef3c7; color: #92400e; border: 1px solid #f59e0b; }}
    .badge-benchmark-domain {{ background: #e0f2fe; color: #0369a1; border: 1px solid #bae6fd; }}
    .badge-benchmark-rank {{ background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}
    #drawer-close {{
      background: none;
      border: none;
      cursor: pointer;
      font-size: 1.5rem;
      line-height: 1;
      color: var(--text-muted);
      border-radius: 4px;
      padding: 4px 8px;
      transition: background 0.15s, color 0.15s;
    }}
    #drawer-close:hover {{
      background: #f1f5f9;
      color: var(--text-main);
    }}
    .drawer-body {{
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .drawer-title {{
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text-main);
      line-height: 1.4;
    }}
    .drawer-meta-row {{
      display: flex;
      gap: 16px;
      font-size: 0.875rem;
      color: var(--text-muted);
    }}
    .drawer-section-heading {{
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 8px;
    }}
    .citekey-box {{
      display: flex;
      align-items: center;
      background: #f1f5f9;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 8px 12px;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.85rem;
      justify-content: space-between;
    }}
    #copy-citekey-btn {{
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 4px;
      padding: 4px 10px;
      font-size: 0.75rem;
      font-weight: 600;
      cursor: pointer;
      color: var(--text-main);
      transition: all 0.15s;
    }}
    #copy-citekey-btn:hover {{
      background: var(--primary);
      color: #ffffff;
      border-color: var(--primary);
    }}
    .author-item {{
      margin-bottom: 6px;
      font-size: 0.875rem;
      line-height: 1.4;
    }}
    .author-name {{
      font-weight: 600;
      color: var(--text-main);
    }}
    .author-institution {{
      color: var(--text-muted);
      font-size: 0.8rem;
    }}
    .author-email {{
      color: var(--primary);
      text-decoration: none;
      font-size: 0.8rem;
    }}
    .author-email:hover {{
      text-decoration: underline;
    }}
    .links-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .paper-link {{
      display: inline-flex;
      align-items: center;
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 0.8rem;
      font-weight: 600;
      text-decoration: none;
      color: #ffffff;
      background: var(--primary);
      transition: background 0.15s;
    }}
    .paper-link:hover {{
      background: var(--primary-hover);
    }}
    .link-pdf {{
      background: #059669;
    }}
    .link-pdf:hover {{
      background: #047857;
    }}
    .drawer-abstract {{
      font-size: 0.875rem;
      line-height: 1.6;
      color: #334155;
      background: #f8fafc;
      padding: 12px;
      border-radius: 6px;
      border: 1px solid var(--border-color);
      white-space: pre-wrap;
    }}

    /* Empirical Benchmark Performance Cards */
    .benchmarks-list {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .benchmark-card {{
      background: #f8fafc;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .benchmark-card-header {{
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .benchmark-name {{
      font-size: 0.95rem;
      font-weight: 700;
      color: var(--text-main);
    }}
    .benchmark-score {{
      font-size: 0.95rem;
      font-weight: 600;
      color: var(--text-main);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    .benchmark-condition {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .benchmark-source {{
      font-size: 0.78rem;
      color: var(--text-muted);
      font-style: italic;
    }}
    .benchmark-evidence-quote {{
      font-size: 0.825rem;
      line-height: 1.45;
      color: #334155;
      background: #ffffff;
      border-left: 3px solid var(--sota-accent);
      border-radius: 0 4px 4px 0;
      padding: 8px 10px;
      margin: 0;
      font-style: italic;
    }}

    /* Technical Gaps & Evidence */
    .gaps-list {{
      display: flex;
      flex-direction: column;
      gap: 12px;
    }}
    .gap-card {{
      background: #f8fafc;
      border: 1px solid var(--border-color);
      border-radius: 6px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .gap-card-header {{
      display: flex;
      align-items: center;
      gap: 6px;
      flex-wrap: wrap;
    }}
    .badge-gap-computational-complexity,
    .badge-gap-computational_complexity {{ background: #fef3c7; color: #92400e; border: 1px solid #fde68a; }}
    .badge-gap-unstated-assumption,
    .badge-gap-unstated_assumption {{ background: #f3e8ff; color: #6b21a8; border: 1px solid #e9d5ff; }}
    .badge-gap-empirical-limitation,
    .badge-gap-empirical_limitation {{ background: #ffe4e6; color: #9f1239; border: 1px solid #fecdd3; }}
    .badge-gap-generalization-bound,
    .badge-gap-generalization_bound {{ background: #cffafe; color: #155e75; border: 1px solid #a5f3fc; }}
    .badge-gap-unresolved-problem,
    .badge-gap-unresolved_problem {{ background: #e0e7ff; color: #3730a3; border: 1px solid #c7d2fe; }}
    .badge-gap-default {{ background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0; }}

    .badge-verif-corroborated {{ background: #d1fae5; color: #065f46; border: 1px solid #a7f3d0; }}
    .badge-verif-candidate {{ background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}
    .badge-verif-disputed {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}

    .gap-claim {{
      font-size: 0.9rem;
      font-weight: 600;
      color: var(--text-main);
      line-height: 1.4;
    }}
    .gap-evidence-quote {{
      font-size: 0.825rem;
      line-height: 1.45;
      color: #334155;
      background: #ffffff;
      border-left: 3px solid var(--primary);
      border-radius: 0 4px 4px 0;
      padding: 8px 10px;
      margin: 0;
      font-style: italic;
    }}
    .gap-meta {{
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      flex-direction: column;
      gap: 2px;
    }}
    .gap-meta-item {{
      display: flex;
      align-items: center;
      gap: 4px;
    }}
  </style>
</head>
<body>
  <div id="app-container">
    <div id="top-bar">
      <div class="title-group">
        <h1 class="graph-title">{sanitized_graph_title}</h1>
        <span class="graph-stats">{len(papers)} papers • {len(citations)} lineage connections</span>
      </div>
      <div class="legend">
        <div class="legend-item"><div class="legend-color" style="background: #10b981;"></div><span>Gold OA</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #059669;"></div><span>Green OA</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #f59e0b;"></div><span>Hybrid</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #d97706;"></div><span>Bronze</span></div>
        <div class="legend-item"><div class="legend-color" style="background: #64748b;"></div><span>Closed</span></div>
        <div class="legend-item"><div class="legend-seed"></div><span>Seed Work</span></div>
        <div class="legend-item"><div class="legend-sota"></div><span>⭐ SOTA Leader (Verified Benchmark Performance)</span></div>
      </div>
    </div>
    <div id="network-container"></div>
  </div>

  <aside id="details-drawer" aria-label="Paper Details">
    <div class="drawer-header">
      <div class="drawer-badges">
        <span id="drawer-oa-status" class="badge"></span>
        <span id="drawer-seed-badge" class="badge badge-seed" style="display: none;">SEED PAPER</span>
        <span id="drawer-sota-badge" class="badge badge-sota" style="display: none;">⭐ SOTA LEADER</span>
      </div>
      <button id="drawer-close" title="Close Drawer">&times;</button>
    </div>
    <div class="drawer-body">
      <h2 id="drawer-title" class="drawer-title"></h2>
      <div class="drawer-meta-row">
        <span>Year: <strong id="drawer-year"></strong></span>
        <span>Citations: <strong id="drawer-citations"></strong></span>
      </div>

      <div>
        <div class="drawer-section-heading">CiteKey (BibTeX)</div>
        <div class="citekey-box">
          <code id="drawer-citekey"></code>
          <button id="copy-citekey-btn">Copy</button>
        </div>
      </div>

      <div>
        <div class="drawer-section-heading">Authors</div>
        <div id="drawer-authors"></div>
      </div>

      <div>
        <div class="drawer-section-heading">Identifiers & Access</div>
        <div id="drawer-links" class="links-grid"></div>
      </div>

      <div>
        <div class="drawer-section-heading">Abstract</div>
        <div id="drawer-abstract" class="drawer-abstract"></div>
      </div>

      <div id="drawer-benchmarks-section" style="display: none;">
        <div class="drawer-section-heading">Empirical Benchmark Performance & SOTA Results</div>
        <div id="drawer-benchmarks-list" class="benchmarks-list"></div>
      </div>

      <div id="drawer-gaps-section" style="display: none;">
        <div class="drawer-section-heading">Extracted Technical Limitations & Gaps</div>
        <div id="drawer-gaps-list" class="gaps-list"></div>
      </div>
    </div>
  </aside>

  <script type="text/javascript">
    const nodesData = {safe_nodes_json};
    const edgesData = {safe_edges_json};
    const papersData = {safe_papers_json};

    const container = document.getElementById('network-container');
    const data = {{
      nodes: new vis.DataSet(nodesData),
      edges: new vis.DataSet(edgesData)
    }};

    const options = {{
      layout: {{
        hierarchical: {{
          direction: 'LR',
          sortMethod: 'directed',
          levelSeparation: 220,
          nodeSpacing: 160
        }}
      }},
      physics: {{
        hierarchicalRepulsion: {{
          nodeDistance: 160
        }}
      }},
      interaction: {{
        hover: true,
        tooltipDelay: 200,
        navigationButtons: true,
        keyboard: true
      }}
    }};

    const network = new vis.Network(container, data, options);

    const drawer = document.getElementById('details-drawer');
    const drawerCloseBtn = document.getElementById('drawer-close');
    const copyCiteKeyBtn = document.getElementById('copy-citekey-btn');

    function openDrawer(paper) {{
      if (!paper) return;

      document.getElementById('drawer-title').textContent = paper.title || 'Untitled';
      document.getElementById('drawer-year').textContent = paper.year ? paper.year : (paper.publication_date || 'n.d.');
      document.getElementById('drawer-citekey').textContent = paper.cite_key || '';

      let citsText = String(paper.citation_count ?? 0);
      if (paper.influential_citation_count) {{
        citsText += ' (' + paper.influential_citation_count + ' influential)';
      }}
      document.getElementById('drawer-citations').textContent = citsText;
      document.getElementById('drawer-abstract').textContent = paper.abstract || 'No abstract available.';

      const oaBadge = document.getElementById('drawer-oa-status');
      oaBadge.textContent = (paper.oa_status || 'closed').toUpperCase();
      oaBadge.className = 'badge badge-oa-' + (paper.oa_status || 'closed');

      const seedBadge = document.getElementById('drawer-seed-badge');
      seedBadge.style.display = paper.is_seed ? 'inline-block' : 'none';

      const sotaBadge = document.getElementById('drawer-sota-badge');
      sotaBadge.style.display = paper.is_sota_leader ? 'inline-block' : 'none';

      const authorsDiv = document.getElementById('drawer-authors');
      authorsDiv.innerHTML = '';
      if (paper.authors && paper.authors.length > 0) {{
        paper.authors.forEach(function(author) {{
          const item = document.createElement('div');
          item.className = 'author-item';

          const nameSpan = document.createElement('span');
          nameSpan.className = 'author-name';
          nameSpan.textContent = author.name;
          item.appendChild(nameSpan);

          if (author.institution) {{
            const instSpan = document.createElement('span');
            instSpan.className = 'author-institution';
            instSpan.textContent = ' — ' + author.institution;
            item.appendChild(instSpan);
          }}

          if (author.email) {{
            const emailLink = document.createElement('a');
            emailLink.className = 'author-email';
            emailLink.href = 'mailto:' + encodeURIComponent(author.email);
            emailLink.textContent = ' (' + author.email + ')';
            item.appendChild(emailLink);
          }}

          authorsDiv.appendChild(item);
        }});
      }} else {{
        authorsDiv.textContent = 'Unknown Authors';
      }}

      const linksDiv = document.getElementById('drawer-links');
      linksDiv.innerHTML = '';
      let hasLinks = false;

      if (paper.doi) {{
        hasLinks = true;
        const a = document.createElement('a');
        a.href = 'https://doi.org/' + encodeURIComponent(paper.doi);
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.className = 'paper-link';
        a.textContent = 'DOI: ' + paper.doi;
        linksDiv.appendChild(a);
      }}

      if (paper.arxiv_id) {{
        hasLinks = true;
        const a = document.createElement('a');
        a.href = 'https://arxiv.org/abs/' + encodeURIComponent(paper.arxiv_id);
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.className = 'paper-link';
        a.textContent = 'arXiv: ' + paper.arxiv_id;
        linksDiv.appendChild(a);
      }}

      if (paper.pdf_url) {{
        hasLinks = true;
        const a = document.createElement('a');
        a.href = paper.pdf_url;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.className = 'paper-link link-pdf';
        a.textContent = '📄 View Open Access PDF';
        linksDiv.appendChild(a);
      }}

      if (!hasLinks) {{
        const span = document.createElement('span');
        span.style.fontSize = '0.85rem';
        span.style.color = '#64748b';
        span.textContent = 'No external web links registered.';
        linksDiv.appendChild(span);
      }}

      // Empirical Benchmarks Section
      const bmsSection = document.getElementById('drawer-benchmarks-section');
      const bmsList = document.getElementById('drawer-benchmarks-list');
      bmsList.innerHTML = '';

      if (paper.benchmarks && paper.benchmarks.length > 0) {{
        bmsSection.style.display = 'block';
        paper.benchmarks.forEach(function(bm) {{
          const card = document.createElement('div');
          card.className = 'benchmark-card';

          const header = document.createElement('div');
          header.className = 'benchmark-card-header';

          if (bm.benchmark_domain) {{
            const domainBadge = document.createElement('span');
            domainBadge.className = 'badge badge-benchmark-domain';
            domainBadge.textContent = '[' + bm.benchmark_domain + ']';
            header.appendChild(domainBadge);
          }}

          const nameSpan = document.createElement('span');
          nameSpan.className = 'benchmark-name';
          nameSpan.textContent = bm.benchmark_name;
          header.appendChild(nameSpan);

          if (bm.is_sota) {{
            const leaderBadge = document.createElement('span');
            leaderBadge.className = 'badge badge-sota';
            leaderBadge.textContent = '⭐ SOTA Leader';
            header.appendChild(leaderBadge);
          }}

          if (bm.rank !== undefined && bm.rank !== null) {{
            const rankBadge = document.createElement('span');
            rankBadge.className = 'badge badge-benchmark-rank';
            rankBadge.textContent = 'Rank #' + bm.rank;
            header.appendChild(rankBadge);
          }}

          card.appendChild(header);

          const scoreDiv = document.createElement('div');
          scoreDiv.className = 'benchmark-score';
          scoreDiv.textContent = bm.formatted_score;
          card.appendChild(scoreDiv);

          if (bm.condition_name || bm.condition_split || bm.condition_notes) {{
            const condDiv = document.createElement('div');
            condDiv.className = 'benchmark-condition';
            let condParts = [];
            if (bm.condition_name) condParts.push(bm.condition_name);
            if (bm.condition_split) condParts.push('split: ' + bm.condition_split);
            if (bm.condition_notes) condParts.push('notes: ' + bm.condition_notes);
            condDiv.textContent = 'Condition: ' + condParts.join(' | ');
            card.appendChild(condDiv);
          }}

          if (bm.table_or_figure || bm.provenance_source) {{
            const srcDiv = document.createElement('div');
            srcDiv.className = 'benchmark-source';
            let srcText = '';
            if (bm.table_or_figure) {{
              srcText = 'Source: ' + bm.table_or_figure;
            }}
            if (bm.provenance_source && bm.provenance_source !== 'author_reported') {{
              srcText += (srcText ? ' (' : 'Source: ') + bm.provenance_source + (srcText ? ')' : '');
            }}
            srcDiv.textContent = srcText || ('Source: ' + bm.provenance_source);
            card.appendChild(srcDiv);
          }}

          if (bm.evidence && bm.evidence.extracted_text) {{
            const bq = document.createElement('blockquote');
            bq.className = 'benchmark-evidence-quote';
            bq.textContent = '“' + bm.evidence.extracted_text + '”';
            card.appendChild(bq);
          }}

          bmsList.appendChild(card);
        }});
      }} else {{
        bmsSection.style.display = 'none';
      }}

      // Technical Gaps Section
      const gapsSection = document.getElementById('drawer-gaps-section');
      const gapsList = document.getElementById('drawer-gaps-list');
      gapsList.innerHTML = '';

      if (paper.gaps && paper.gaps.length > 0) {{
        gapsSection.style.display = 'block';
        paper.gaps.forEach(function(gap) {{
          const card = document.createElement('div');
          card.className = 'gap-card';

          const header = document.createElement('div');
          header.className = 'gap-card-header';

          const catBadge = document.createElement('span');
          const gapTypeKey = (gap.gap_type || '').toLowerCase().replace(/_/g, '-');
          catBadge.className = 'badge badge-gap-' + (gapTypeKey || 'default');
          catBadge.textContent = gap.category_label || (gap.gap_type || 'GAP').replace(/_/g, ' ').toUpperCase();
          header.appendChild(catBadge);

          const verifBadge = document.createElement('span');
          let verifClass = 'badge-verif-candidate';
          let verifLabel = 'Candidate Finding';

          if (gap.verification_status === 'corroborated') {{
            verifClass = 'badge-verif-corroborated';
            const count = (gap.corroborating_count !== undefined && gap.corroborating_count !== null) ? gap.corroborating_count : 0;
            verifLabel = 'Corroborated (' + count + (count === 1 ? ' source' : ' sources') + ')';
          }} else if (gap.verification_status === 'disputed') {{
            verifClass = 'badge-verif-disputed';
            verifLabel = 'Disputed Finding';
          }} else if (gap.verification_status === 'candidate') {{
            verifClass = 'badge-verif-candidate';
            verifLabel = 'Candidate Finding';
          }}
          verifBadge.className = 'badge ' + verifClass;
          verifBadge.textContent = gap.verification_label || verifLabel;
          header.appendChild(verifBadge);

          card.appendChild(header);

          const claim = document.createElement('div');
          claim.className = 'gap-claim';
          claim.textContent = gap.claim_summary || '';
          card.appendChild(claim);

          if (gap.evidence && gap.evidence.extracted_text) {{
            const bq = document.createElement('blockquote');
            bq.className = 'gap-evidence-quote';
            bq.textContent = '“' + gap.evidence.extracted_text + '”';
            card.appendChild(bq);
          }}

          const metaDiv = document.createElement('div');
          metaDiv.className = 'gap-meta';

          if (gap.evidence) {{
            if (gap.evidence.source_section) {{
              const sec = document.createElement('div');
              sec.className = 'gap-meta-item';
              sec.textContent = 'Section: ' + gap.evidence.source_section;
              metaDiv.appendChild(sec);
            }}
            if (gap.evidence.reporting_paper_id) {{
              const rep = document.createElement('div');
              rep.className = 'gap-meta-item';
              rep.textContent = 'Reported in: ' + gap.evidence.reporting_paper_id;
              metaDiv.appendChild(rep);
            }}
            if (gap.evidence.extraction_method) {{
              const meth = document.createElement('div');
              meth.className = 'gap-meta-item';
              meth.textContent = 'Extraction Method: ' + gap.evidence.extraction_method;
              metaDiv.appendChild(meth);
            }}
          }}

          if (metaDiv.children.length > 0) {{
            card.appendChild(metaDiv);
          }}

          gapsList.appendChild(card);
        }});
      }} else {{
        gapsSection.style.display = 'none';
      }}

      drawer.classList.add('open');
    }}

    function closeDrawer() {{
      drawer.classList.remove('open');
    }}

    drawerCloseBtn.addEventListener('click', closeDrawer);

    copyCiteKeyBtn.addEventListener('click', function() {{
      const citekey = document.getElementById('drawer-citekey').textContent;
      if (citekey && navigator.clipboard) {{
        navigator.clipboard.writeText(citekey).then(function() {{
          const orig = copyCiteKeyBtn.textContent;
          copyCiteKeyBtn.textContent = 'Copied!';
          setTimeout(function() {{
            copyCiteKeyBtn.textContent = orig;
          }}, 1600);
        }}).catch(function(err) {{
          console.error('Clipboard copy failed: ', err);
        }});
      }}
    }});

    network.on("click", function(params) {{
      if (params.nodes && params.nodes.length > 0) {{
        const nodeId = params.nodes[0];
        const paper = papersData[nodeId];
        if (paper) {{
          openDrawer(paper);
        }}
      }}
    }});
  </script>
</body>
</html>
"""


render_interactive_html = generate_interactive_html


def save_interactive_html(
    output_path: str | Path,
    graph_title: str,
    papers: list[PaperRecord],
    citations: list[CitationRecord],
    depths: dict[str, int],
    seed_paper_id: Optional[str] = None,
    paper_gaps: Optional[dict[str, list[PaperGapRecord]]] = None,
    evidence_map: Optional[dict[str, EvidenceRecord]] = None,
    benchmark_results: Optional[dict[str, list[BenchmarkResultRecord]]] = None,
    benchmarks_map: Optional[dict[str, BenchmarkRecord]] = None,
    metrics_map: Optional[dict[str, EvaluationMetricRecord]] = None,
    conditions_map: Optional[dict[str, EvaluationConditionRecord]] = None,
    node_roles: Optional[dict[str, str]] = None,
) -> Path:
    """
    Render and persist interactive HTML visualization to specified filesystem path.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    html_content = generate_interactive_html(
        graph_title=graph_title,
        papers=papers,
        citations=citations,
        depths=depths,
        seed_paper_id=seed_paper_id,
        paper_gaps=paper_gaps,
        evidence_map=evidence_map,
        benchmark_results=benchmark_results,
        benchmarks_map=benchmarks_map,
        metrics_map=metrics_map,
        conditions_map=conditions_map,
        node_roles=node_roles,
    )
    path.write_text(html_content, encoding="utf-8")
    return path


__all__ = [
    "render_interactive_html",
    "generate_interactive_html",
    "save_interactive_html",
    "determine_oa_status",
    "OA_COLORS",
    "GAP_CATEGORY_COLORS",
    "SEED_BORDER_COLOR",
    "SOTA_BORDER_COLOR",
    "SOTA_BG_COLOR",
]
