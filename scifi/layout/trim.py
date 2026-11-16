"""Page budget micro-trimming assistant and paragraph slack analyzer."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scifi.latex.project import resolve_latex_project
from scifi.layout.abbreviations import abbreviate_bib_string
from scifi.layout.models import (
    TrimBudgetResult,
    TrimSuggestion,
    TrimSuggestionType,
)


def detect_paragraph_slack(text: str) -> list[TrimSuggestion]:
    """
    Detect paragraphs where the final line consists of a tiny orphan/widow string (1-3 words).
    Trimming 1-3 words from earlier in the paragraph saves an entire line.
    """
    suggestions: list[TrimSuggestion] = []
    # Split text into paragraphs by blank lines
    raw_paras = re.split(r"\n\s*\n", text)

    for p in raw_paras:
        clean_p = p.strip()
        if not clean_p or clean_p.startswith("%") or clean_p.startswith("\\begin"):
            continue

        lines = [line.strip() for line in clean_p.splitlines() if line.strip() and not line.strip().startswith("%")]
        if len(lines) < 2:
            continue

        last_line = lines[-1]
        words = last_line.split()
        # If last line has 1-3 words or <= 20 characters
        if 1 <= len(words) <= 3 and len(last_line) <= 25 and not last_line.startswith("\\"):
            target_snip = f"... {last_line}"
            suggestions.append(
                TrimSuggestion(
                    suggestion_type=TrimSuggestionType.WIDOW_LINE,
                    target=target_snip,
                    description=f"Paragraph ends with a widow line of only {len(words)} word(s) ('{last_line}'). Pruning {len(words)} word(s) from this paragraph will recover 1 full vertical line.",
                    potential_savings_lines=1,
                    proposed_text="[Trim 1-3 non-essential words from preceding sentences]",
                )
            )

    return suggestions


def detect_table_and_float_slack(text: str) -> list[TrimSuggestion]:
    """Detect uncompacted tables that can be made more dense via standard macros."""
    suggestions: list[TrimSuggestion] = []

    # Find table environments
    tables = re.findall(r"\\begin\{(table\*?)\}(.*?)\\end\{\1\}", text, re.DOTALL)
    for idx, (t_type, body) in enumerate(tables, start=1):
        has_font_size = any(sz in body for sz in ("\\small", "\\footnotesize", "\\scriptsize"))
        if not has_font_size:
            suggestions.append(
                TrimSuggestion(
                    suggestion_type=TrimSuggestionType.TABLE_PADDING,
                    target=f"Table {idx} ({t_type})",
                    description=f"Table {idx} does not use '\\small' or '\\footnotesize'. Adding '\\small' inside the table environment recovers 2-5 lines.",
                    potential_savings_lines=3,
                    proposed_text=r"Insert \small immediately after \centering",
                )
            )

    return suggestions


def audit_trim_budget(
    tex_path: Path | str,
    bib_path: Path | str | None = None,
    render_previews: bool = True,
    pdf_path: Path | str | None = None,
    render_dpi: int = 150,
    pages: str | list[int] | None = None,
    max_pages: int = 12,
    vlm_check: bool = False,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> TrimBudgetResult:
    """Analyze LaTeX manuscript and BibTeX bibliography for legitimate typographic line savings."""
    target_tex = Path(tex_path)
    if target_tex.exists():
        try:
            proj = resolve_latex_project(target_tex)
            full_text = proj.merged_text
            discovered_bibs = proj.bib_files
        except Exception:
            full_text = target_tex.read_text(encoding="utf-8", errors="replace")
            discovered_bibs = []
    else:
        full_text = str(tex_path)
        discovered_bibs = []

    suggestions: list[TrimSuggestion] = []

    # 1. Paragraph slack
    para_suggestions = detect_paragraph_slack(full_text)
    suggestions.extend(para_suggestions)

    # 2. Table / float slack
    table_suggestions = detect_table_and_float_slack(full_text)
    suggestions.extend(table_suggestions)

    # 3. BibTeX condensation
    condensed_count = 0
    condensed_bib = ""
    bib_to_check: list[Path] = []
    if bib_path:
        bib_to_check.append(Path(bib_path))
    else:
        bib_to_check.extend(discovered_bibs)

    for bp in bib_to_check:
        if bp.exists():
            content = bp.read_text(encoding="utf-8", errors="replace")
            new_content, c = abbreviate_bib_string(content)
            if c > 0:
                condensed_count += c
                condensed_bib = new_content
                # Each 2 abbreviated venue entries roughly saves 1-2 lines in reference section
                saved_lines = max(1, c)
                suggestions.append(
                    TrimSuggestion(
                        suggestion_type=TrimSuggestionType.BIBTEX_ABBREVIATION,
                        target=str(bp.name),
                        description=f"Found {c} verbose journal/conference titles that can be shortened to standard ISO-4/IEEE abbreviations.",
                        potential_savings_lines=saved_lines,
                        proposed_text=f"Run BibTeX abbreviation engine to shorten {c} entries",
                    )
                )

    # 4. Render compiled PDF pages for visual layout / whitespace inspection
    rendered_pages: list[dict[str, Any]] = []
    if render_previews:
        compiled_pdf = Path(pdf_path) if pdf_path else (target_tex.with_suffix(".pdf") if target_tex.exists() else None)
        if compiled_pdf and compiled_pdf.is_file():
            from scifi.figures.renderer import render_pdf_pages

            pdf_render = render_pdf_pages(
                compiled_pdf,
                pages=pages,
                dpi=render_dpi,
                max_pages=max_pages,
            )
            for rp in pdf_render.get("rendered_pages", []):
                rendered_pages.append(
                    {
                        "kind": "compiled_pdf_page",
                        "page": rp["page"],
                        "source_path": str(compiled_pdf.resolve()),
                        "image_path": rp["image_path"],
                        "width": rp["width"],
                        "height": rp["height"],
                    }
                )

    # 4b. Local pixel-level page-break whitespace check on rendered PDF pages (no API key required)
    if rendered_pages:
        from scifi.figures.pixel_checks import check_page_whitespace

        total_rendered = len(rendered_pages)
        for idx, rp in enumerate(rendered_pages):
            ws = check_page_whitespace(rp["image_path"])
            if not ws.get("analyzed"):
                continue
            rp["bottom_whitespace_ratio"] = ws["bottom_whitespace_ratio"]
            rp["ink_density"] = ws["ink_density"]
            ratio = ws["bottom_whitespace_ratio"]
            if ratio >= 0.35:
                is_last = idx == total_rendered - 1
                s_type = TrimSuggestionType.TRAILING_PAGE_SLACK if is_last else TrimSuggestionType.PAGE_BREAK_WHITESPACE
                pct = int(round(ratio * 100))
                suggestions.append(
                    TrimSuggestion(
                        suggestion_type=s_type,
                        target=f"Page {rp['page']}",
                        description=(
                            f"Page {rp['page']} has ~{pct}% trailing empty whitespace at the bottom "
                            + ("(sparse trailing final page)." if is_last else "(awkward page-break or float gap).")
                        ),
                        potential_savings_lines=max(2, int(round(ratio * 15))),
                        proposed_text="Inspect rendered page PNG and adjust float placement ([tp]) or tighten nearby paragraphs.",
                    )
                )

    # 5. Optional external VLM visual layout inspection (or host-agent checklist when vlm_check=False)
    vlm_inspection: dict[str, Any] = {
        "status": "HOST_AGENT_READY" if rendered_pages else "DISABLED",
        "mode": "host_agent" if not vlm_check else "external_vlm",
        "visual_checklist": [
            "Inspect rendered_pages[*].image_path using read_file / built-in vision.",
            "Check for awkward page-break whitespace, orphan headings, float placement gaps, and margin overflow.",
        ]
        if rendered_pages
        else [],
    }
    if vlm_check:
        if not rendered_pages:
            vlm_inspection = {
                "status": "SKIPPED_NO_IMAGES",
                "hint": "No compiled PDF pages rendered for VLM layout inspection.",
                "findings": [],
            }
        else:
            from scifi.figures.vlm import inspect_images_with_vlm

            vlm_res = inspect_images_with_vlm(
                rendered_pages,
                mode="layout",
                provider=vlm_provider,
                model=vlm_model,
                max_images=max_pages,
            )
            vlm_inspection = {k: v for k, v in vlm_res.items() if k != "findings"}
            for finding in vlm_res.get("findings", []):
                raw_cat = str(finding.get("category", "PAGE_BREAK_WHITESPACE")).upper()
                try:
                    s_type = TrimSuggestionType(raw_cat)
                except ValueError:
                    s_type = TrimSuggestionType.PAGE_BREAK_WHITESPACE
                page_num = finding.get("page")
                target_label = str(finding.get("target") or (f"Page {page_num}" if page_num else "Compiled PDF"))
                try:
                    savings = max(0, int(finding.get("potential_savings_lines") or 0))
                except (TypeError, ValueError):
                    savings = 0
                suggestions.append(
                    TrimSuggestion(
                        suggestion_type=s_type,
                        target=target_label,
                        description=f"[VLM] {finding.get('message', 'Visual layout issue detected.')}",
                        potential_savings_lines=savings,
                        proposed_text=str(finding.get("recommendation") or ""),
                    )
                )

    total_lines = sum(s.potential_savings_lines for s in suggestions)

    return TrimBudgetResult(
        status="SUCCESS",
        total_potential_lines_saved=total_lines,
        bibtex_condensed_entries=condensed_count,
        suggestions=suggestions,
        abbreviated_bib=condensed_bib,
        rendered_pages=rendered_pages,
        vlm_inspection=vlm_inspection,
    )
