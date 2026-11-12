"""LaTeX manuscript diff tracking and latexdiff automation suite."""

from __future__ import annotations

import difflib
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from scifi.latex.compiler import compile_latex
from scifi.rebuttal.models import ManuscriptDiffSummary


RE_SECTION = re.compile(r"\\section\*?\{([^}]+?)\}")


def _split_into_sections(text: str) -> dict[str, list[str]]:
    """Split LaTeX text into sections."""
    sections: dict[str, list[str]] = {}
    current_sec = "Preamble / Global"
    sections[current_sec] = []

    for line in text.splitlines():
        m = RE_SECTION.search(line)
        if m:
            current_sec = m.group(1).strip()
            if current_sec not in sections:
                sections[current_sec] = []
        sections[current_sec].append(line)

    return sections


def diff_manuscript(
    old_tex_path: Path | str,
    new_tex_path: Path | str,
    generate_pdf: bool = False,
    output_tex: Path | str | None = None,
) -> ManuscriptDiffSummary:
    """Generate a structured section-by-section diff ledger and optional latexdiff markup."""
    old_p = Path(old_tex_path)
    new_p = Path(new_tex_path)

    old_content = old_p.read_text(encoding="utf-8", errors="replace") if old_p.exists() else str(old_tex_path)
    new_content = new_p.read_text(encoding="utf-8", errors="replace") if new_p.exists() else str(new_tex_path)

    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()

    # Unified diff
    diff_gen = list(difflib.unified_diff(old_lines, new_lines, lineterm=""))
    added = sum(1 for line in diff_gen if line.startswith("+") and not line.startswith("+++"))
    deleted = sum(1 for line in diff_gen if line.startswith("-") and not line.startswith("---"))

    # Section-level changes
    old_secs = _split_into_sections(old_content)
    new_secs = _split_into_sections(new_content)

    all_sec_names = list(dict.fromkeys(list(old_secs.keys()) + list(new_secs.keys())))
    modified_sections: list[dict[str, Any]] = []

    ledger_rows = [
        "| Section | Added Lines | Deleted Lines | Status |",
        "| :--- | :---: | :---: | :--- |",
    ]

    for sec in all_sec_names:
        o_lines = old_secs.get(sec, [])
        n_lines = new_secs.get(sec, [])

        if not o_lines and n_lines:
            status = "NEW_SECTION"
            sec_add = len(n_lines)
            sec_del = 0
        elif o_lines and not n_lines:
            status = "REMOVED_SECTION"
            sec_add = 0
            sec_del = len(o_lines)
        else:
            s_diff = list(difflib.unified_diff(o_lines, n_lines, lineterm=""))
            sec_add = sum(1 for l in s_diff if l.startswith("+") and not l.startswith("+++"))
            sec_del = sum(1 for l in s_diff if l.startswith("-") and not l.startswith("---"))
            status = "MODIFIED" if (sec_add > 0 or sec_del > 0) else "UNCHANGED"

        if status != "UNCHANGED":
            modified_sections.append({
                "section": sec,
                "added": sec_add,
                "deleted": sec_del,
                "status": status,
            })
            ledger_rows.append(f"| **{sec}** | +{sec_add} | -{sec_del} | `{status}` |")

    diff_ledger_md = "\n".join(ledger_rows)

    diff_tex_result: str | None = None
    diff_pdf_result: str | None = None

    # Check for latexdiff
    latexdiff_bin = shutil.which("latexdiff")
    if latexdiff_bin and old_p.exists() and new_p.exists():
        out_tex_path = Path(output_tex) if output_tex else new_p.parent / f"diff_{new_p.name}"
        try:
            cmd = [latexdiff_bin, "--math-markup=fine", str(old_p), str(new_p)]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
            out_tex_path.write_text(proc.stdout, encoding="utf-8")
            diff_tex_result = str(out_tex_path)

            if generate_pdf:
                compile_res = compile_latex(out_tex_path)
                if compile_res.get("status") == "SUCCESS" and compile_res.get("pdf_path"):
                    diff_pdf_result = compile_res.get("pdf_path")
        except Exception:
            pass

    return ManuscriptDiffSummary(
        status="SUCCESS",
        old_tex=str(old_p),
        new_tex=str(new_p),
        added_lines=added,
        deleted_lines=deleted,
        modified_sections=modified_sections,
        diff_ledger_markdown=diff_ledger_md,
        diff_tex_path=diff_tex_result,
        diff_pdf_path=diff_pdf_result,
    )
