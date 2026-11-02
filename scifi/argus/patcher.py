"""
Patching and remediation engine for Argus.
Handles in-place LaTeX citation injection, BibTeX updating, and humanizer prompt generation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .models import AttributionFinding, SuggestedAction


def append_bibtex_entry(bib_file: Path, bibtex_content: str, cite_key: str) -> bool:
    """
    Append a verified BibTeX entry to the .bib file if the cite key does not already exist.
    """
    if not bib_file.exists():
        bib_file.parent.mkdir(parents=True, exist_ok=True)
        bib_file.write_text(bibtex_content.strip() + "\n\n", encoding="utf-8")
        return True

    existing_content = bib_file.read_text(encoding="utf-8", errors="replace")
    # Check if key already exists: @type{key,
    key_pattern = r"@\w+\s*\{\s*" + re.escape(cite_key) + r"\s*,"
    if re.search(key_pattern, existing_content):
        return False  # Already exists

    with bib_file.open("a", encoding="utf-8") as f:
        f.write("\n" + bibtex_content.strip() + "\n")
    return True


def insert_cite_into_latex(
    tex_path: Path,
    line_number: int,
    cite_key: str,
    target_entity: Optional[str] = None,
) -> bool:
    """
    Insert a \\cite{cite_key} into the LaTeX file at the specified line.
    If target_entity is provided, places the citation right after the entity name.
    Otherwise, inserts it before the end of the sentence.
    """
    if not tex_path.exists():
        return False

    lines = tex_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    if not (1 <= line_number <= len(lines)):
        return False

    target_idx = line_number - 1
    orig_line = lines[target_idx]

    cite_str = f"~\\cite{{{cite_key}}}"

    if target_entity and re.search(re.escape(target_entity), orig_line, flags=re.IGNORECASE):
        # Insert right after the entity name
        new_line = re.sub(
            f"({re.escape(target_entity)})",
            lambda m: m.group(1) + cite_str,
            orig_line,
            count=1,
            flags=re.IGNORECASE,
        )
    else:
        # Insert before trailing punctuation or end of line
        m = re.search(r"([.!?])(\s*)$", orig_line)
        if m:
            new_line = orig_line[: m.start(1)] + cite_str + m.group(1) + m.group(2)
        else:
            new_line = orig_line.rstrip() + cite_str + "\n"

    lines[target_idx] = new_line
    tex_path.write_text("".join(lines), encoding="utf-8")
    return True


def generate_reformulate_prompt(finding: AttributionFinding) -> str:
    """
    Generate an actionable humanizer prompt for the 'human' skill.
    """
    return (
        f"Rewrite and humanize the following text following the Master Academic Humanizer protocol.\n"
        f"Eliminate any plagiarism, web/blog informalities, and AI tropes. Enforce disciplined academic voice,\n"
        f"passive constructions where standard, and epistemic hedging.\n\n"
        f"Flagged Text (Line {finding.line_number or 'N/A'}):\n"
        f'"{finding.text_snippet}"\n\n'
        f"Context / Reason: {finding.remediation_hint}"
    )
