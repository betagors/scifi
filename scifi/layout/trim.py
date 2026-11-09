"""Page budget micro-trimming assistant and paragraph slack analyzer."""

from __future__ import annotations

from pathlib import Path
import re
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

    total_lines = sum(s.potential_savings_lines for s in suggestions)

    return TrimBudgetResult(
        status="SUCCESS",
        total_potential_lines_saved=total_lines,
        bibtex_condensed_entries=condensed_count,
        suggestions=suggestions,
        abbreviated_bib=condensed_bib,
    )
