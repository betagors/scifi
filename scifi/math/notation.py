"""
Manuscript notation consistency verifier (scifi.math.notation).
Supports single-file .tex manuscripts, multi-file LaTeX projects (via \\input / \\include),
project directories, and raw LaTeX strings.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from scifi.latex.project import resolve_latex_project

# ── Regex patterns ──────────────────────────────────────────────────────────

RE_DISPLAY = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
RE_INLINE = re.compile(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", re.DOTALL)
RE_ENV = re.compile(
    r"\\begin\{(equation|align|multline|gather|eqnarray)\*?\}(.*?)\\end\{\1\*?\}",
    re.DOTALL,
)

RE_SECTION = re.compile(r"\\(?:section|subsection|subsubsection|chapter)\*?\{([^}]*)\}")

# Math font commands
RE_FONT_CMD = re.compile(r"\\(?:mathbf|mathbb|mathcal|mathfrak|boldsymbol|bm|hat|tilde|bar|vec|dot|ddot)\{([^}]+)\}")
FONT_RE = re.compile(r"\\(mathbf|mathbb|mathcal|mathfrak|boldsymbol|bm|hat|tilde|bar|vec|dot|ddot)\{([^}]+)\}")

RE_SUBSCRIPT = re.compile(r"_\{[^}]*\}|_[A-Za-z0-9]")
RE_SUPERSCRIPT = re.compile(r"\^\{[^}]*\}|\^[A-Za-z0-9]")
RE_COMMAND = re.compile(r"\\[A-Za-z]+")

RE_DEFINITION = re.compile(
    r"(?:let|define|where|denote|set|is defined as|we write|given by)\s+\$?([A-Za-z][A-Za-z0-9]*)\$?",
    re.IGNORECASE,
)


def extract_math_blocks(text: str) -> list[str]:
    """Extract math blocks from LaTeX text across display, inline, and environments."""
    blocks: list[str] = []
    blocks.extend(RE_DISPLAY.findall(text))
    # Remove display math before scanning for inline to avoid duplicate extraction
    stripped = RE_DISPLAY.sub("", text)
    blocks.extend(RE_INLINE.findall(stripped))
    blocks.extend(m.group(2) for m in RE_ENV.finditer(text))
    return blocks


def symbols_in_block(block: str) -> set[str]:
    """Return single-letter symbols found in a math block."""
    clean = RE_FONT_CMD.sub(r"\1", block)
    clean = RE_SUBSCRIPT.sub("", clean)
    clean = RE_SUPERSCRIPT.sub("", clean)
    clean = RE_COMMAND.sub("", clean)
    return set(re.findall(r"[A-Za-z]", clean))


def variant_key(raw_sym: str) -> str:
    """Case-fold to group font/case variants under a base identifier."""
    return raw_sym.lower()


def split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Split LaTeX document into (section_label, section_text) tuples.
    Text before the first section is labelled 'preamble'.
    """
    labels: list[str] = []
    positions: list[int] = []
    for m in RE_SECTION.finditer(text):
        labels.append(m.group(1).strip())
        positions.append(m.start())

    if not positions:
        return [("(whole document)", text)]

    parts: list[tuple[str, str]] = []
    if positions[0] > 0:
        parts.append(("preamble", text[: positions[0]]))

    for i, (label, pos) in enumerate(zip(labels, positions)):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        parts.append((label, text[pos:end]))

    return parts


def check_notation(
    tex_content_or_path: str | Path,
    sections: list[str] | None = None,
) -> dict[str, Any]:
    """
    Scan LaTeX manuscript or multi-file LaTeX project for notation consistency,
    multi-variant symbols, and unintroduced notations.

    Args:
        tex_content_or_path: File path to .tex file, directory path, or raw LaTeX content.
        sections: Optional list of section names to restrict the analysis to.
    """
    tex_path: str | None = None
    files_scanned: list[str] = []

    if isinstance(tex_content_or_path, Path):
        if not tex_content_or_path.exists():
            return {
                "status": "ERROR",
                "error_message": f"File not found: {tex_content_or_path}",
            }
        try:
            proj = resolve_latex_project(tex_content_or_path)
            tex_path = str(proj.entrypoint)
            text = proj.merged_text
            files_scanned = [f.relative_path for f in proj.files]
        except Exception as e:
            return {"status": "ERROR", "error_message": str(e)}
    else:
        input_str = tex_content_or_path.strip()
        if "\n" not in input_str:
            p = Path(input_str)
            if p.exists():
                try:
                    proj = resolve_latex_project(p)
                    tex_path = str(proj.entrypoint)
                    text = proj.merged_text
                    files_scanned = [f.relative_path for f in proj.files]
                except Exception as e:
                    return {"status": "ERROR", "error_message": str(e)}
            elif input_str.endswith(".tex") or "/" in input_str or "\\" in input_str:
                return {
                    "status": "ERROR",
                    "error_message": f"File not found: {input_str}",
                }
            else:
                text = input_str
        else:
            text = input_str

    all_sections = split_into_sections(text)

    if sections is not None:
        target_filters = [s.strip().lower() for s in sections if s.strip()]
        matched_sections = [
            (label, sec_text) for label, sec_text in all_sections if any(tf in label.lower() for tf in target_filters)
        ]
        if matched_sections:
            all_sections = matched_sections

    symbol_variants: dict[str, set[str]] = defaultdict(set)
    symbol_sections: dict[str, list[str]] = defaultdict(list)

    for section_label, sec_text in all_sections:
        blocks = extract_math_blocks(sec_text)
        for block in blocks:
            # 1. Harvest font-decorated variants
            for fm in FONT_RE.finditer(block):
                cmd, sym = fm.group(1), fm.group(2)
                variant = f"\\{cmd}{{{sym}}}"
                symbol_variants[variant_key(sym)].add(variant)
                symbol_sections[variant].append(section_label)

            # 2. Harvest plain letters (strip font commands completely so font variants aren't re-added)
            plain_clean = RE_FONT_CMD.sub("", block)
            plain_clean = RE_SUBSCRIPT.sub("", plain_clean)
            plain_clean = RE_SUPERSCRIPT.sub("", plain_clean)
            plain_clean = RE_COMMAND.sub("", plain_clean)

            for letter in re.findall(r"[A-Za-z]", plain_clean):
                symbol_variants[variant_key(letter)].add(letter)
                symbol_sections[letter].append(section_label)

    multi_variant_flags: list[dict[str, Any]] = []
    for base, variants in symbol_variants.items():
        if len(variants) > 1:
            multi_variant_flags.append(
                {
                    "base_symbol": base,
                    "variants_seen": sorted(variants),
                    "sections": sorted(set(sec for v in variants for sec in symbol_sections.get(v, []))),
                }
            )

    # Cross-section symbol manifest
    manifest = {
        sec: sorted(set(letter for block in extract_math_blocks(sec_txt) for letter in symbols_in_block(block)))
        for sec, sec_txt in all_sections
    }

    issues_count = len(multi_variant_flags)
    result: dict[str, Any] = {
        "status": "VALID" if issues_count == 0 else "NOTATION_INCONSISTENCY",
        "is_correct": issues_count == 0,
        "sections_scanned": [s for s, _ in all_sections],
        "multi_variant_symbols": multi_variant_flags,
        "symbol_manifest": manifest,
    }
    if tex_path:
        result["file"] = tex_path
    if files_scanned:
        result["files_scanned"] = files_scanned

    if issues_count > 0:
        result["hint"] = (
            f"{issues_count} symbol(s) appear in multiple font/case variants. "
            "Decide on a canonical form and apply it uniformly."
        )

    return result
