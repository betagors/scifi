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

from scifi.literature.models import CitationRecord, PaperRecord
from scifi.literature.resolver import clean_arxiv_id, clean_doi

# Color palette for Open Access tiers
OA_COLORS: dict[str, str] = {
    "gold": "#10b981",  # Green
    "green": "#059669",  # Emerald
    "hybrid": "#f59e0b",  # Amber
    "bronze": "#d97706",  # Copper
    "closed": "#64748b",  # Slate
}

SEED_BORDER_COLOR: str = "#3b82f6"  # Blue accent border


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


def render_interactive_html(
    graph_title: str,
    papers: list[PaperRecord],
    citations: list[CitationRecord],
    depths: dict[str, int],
    seed_paper_id: Optional[str] = None,
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
        border_color = SEED_BORDER_COLOR if is_seed else bg_color
        border_width = 4 if is_seed else 2

        depth_level = depths.get(paper.id, 0)
        label = format_node_label(paper)
        doi, arxiv_id, pdf_url = extract_paper_links(paper)

        vis_nodes.append({
            "id": paper.id,
            "label": label,
            "level": depth_level,
            "title": _safe_escape(f"{paper.title} ({paper.year or 'n.d.'})"),
            "color": {
                "background": bg_color,
                "border": border_color,
                "highlight": {
                    "background": bg_color,
                    "border": "#2563eb" if is_seed else "#1e293b",
                },
                "hover": {
                    "background": bg_color,
                    "border": "#3b82f6",
                },
            },
            "borderWidth": border_width,
            "font": {
                "color": "#ffffff",
                "size": 13,
                "bold": {"color": "#ffffff"},
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
            "doi": _safe_escape(doi or ""),
            "arxiv_id": _safe_escape(arxiv_id or ""),
            "pdf_url": _safe_escape(pdf_url or ""),
            "abstract": _safe_escape(paper.abstract or "No abstract available."),
            "authors": author_list,
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
      </div>
    </div>
    <div id="network-container"></div>
  </div>

  <aside id="details-drawer" aria-label="Paper Details">
    <div class="drawer-header">
      <div class="drawer-badges">
        <span id="drawer-oa-status" class="badge"></span>
        <span id="drawer-seed-badge" class="badge badge-seed" style="display: none;">SEED PAPER</span>
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


def save_interactive_html(
    output_path: str | Path,
    graph_title: str,
    papers: list[PaperRecord],
    citations: list[CitationRecord],
    depths: dict[str, int],
    seed_paper_id: Optional[str] = None,
) -> Path:
    """
    Render and persist interactive HTML visualization to specified filesystem path.
    """
    path = Path(output_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    html_content = render_interactive_html(
        graph_title=graph_title,
        papers=papers,
        citations=citations,
        depths=depths,
        seed_paper_id=seed_paper_id,
    )
    path.write_text(html_content, encoding="utf-8")
    return path


__all__ = [
    "render_interactive_html",
    "save_interactive_html",
    "determine_oa_status",
    "OA_COLORS",
    "SEED_BORDER_COLOR",
]
