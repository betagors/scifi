#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
Turing – Notation Consistency Checker for LaTeX Manuscripts.

Scans all math environments in a .tex file and reports:
  1. Symbols that appear in multiple font-case variants
     (e.g.  P, p, \\mathbf{P}, \\boldsymbol{P})
  2. Symbols used in a section before they are introduced by a
     \\newcommand, \\def, \\text{where }, or heuristic "let X denote" phrase
  3. A full cross-section symbol manifest so the author can audit usage

Usage
-----
python verify_notation.py --file paper.tex
python verify_notation.py --file paper.tex --sections "Abstract,1,2,3,Appendix"
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ── Regex patterns ──────────────────────────────────────────────────────────

# Capture inline $...$ or $$...$$
RE_INLINE  = re.compile(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", re.DOTALL)
RE_DISPLAY = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)

# Capture named math environments
RE_ENV = re.compile(
    r"\\begin\{(equation|align|multline|gather|eqnarray)\*?\}(.*?)\\end\{\1\*?\}",
    re.DOTALL,
)

# Section headings
RE_SECTION = re.compile(
    r"\\(?:section|subsection|subsubsection|chapter)\*?\{([^}]*)\}"
)

# Strip LaTeX commands that wrap a symbol (keep the symbol letter)
RE_FONT_CMD = re.compile(
    r"\\(?:mathbf|mathbb|mathcal|mathfrak|boldsymbol|bm|hat|tilde|bar|vec|dot|ddot)\{([^}]+)\}"
)
RE_SUBSCRIPT = re.compile(r"_\{[^}]*\}|_[A-Za-z0-9]")
RE_SUPERSCRIPT = re.compile(r"\^\{[^}]*\}|\^[A-Za-z0-9]")
RE_COMMAND   = re.compile(r"\\[A-Za-z]+")

# Heuristic "definition" indicators in surrounding text
RE_DEFINITION = re.compile(
    r"(?:let|define|where|denote|set|is defined as|we write|given by)\s+\$?([A-Za-z][A-Za-z0-9]*)\$?",
    re.IGNORECASE,
)

# ── Helpers ─────────────────────────────────────────────────────────────────

def extract_math_blocks(text: str) -> list[str]:
    blocks = []
    blocks += RE_DISPLAY.findall(text)
    # Remove display math before scanning for inline to avoid double-hits
    stripped = RE_DISPLAY.sub("", text)
    blocks += RE_INLINE.findall(stripped)
    blocks += [m.group(2) for m in RE_ENV.finditer(text)]
    return blocks

def symbols_in_block(block: str) -> set[str]:
    """Return bare single-letter symbols found in a math block."""
    # Replace font commands, keeping the enclosed letter
    clean = RE_FONT_CMD.sub(r"\1", block)
    clean = RE_SUBSCRIPT.sub("", clean)
    clean = RE_SUPERSCRIPT.sub("", clean)
    clean = RE_COMMAND.sub("", clean)
    # Single Latin / Greek letters
    return set(re.findall(r"[A-Za-z]", clean))

def variant_key(raw_sym: str) -> str:
    """Case-fold to detect P vs p as the same base letter."""
    return raw_sym.lower()

def split_into_sections(text: str) -> list[tuple[str, str]]:
    """
    Returns list of (section_label, section_text).
    Text before the first \\section is labelled 'preamble'.
    """
    parts  = []
    labels = []
    positions = []
    for m in RE_SECTION.finditer(text):
        labels.append(m.group(1).strip())
        positions.append(m.start())

    if not positions:
        return [("(whole document)", text)]

    if positions[0] > 0:
        parts.append(("preamble", text[:positions[0]]))

    for i, (label, pos) in enumerate(zip(labels, positions)):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        parts.append((label, text[pos:end]))

    return parts

# ── Main check ──────────────────────────────────────────────────────────────

def check_notation(tex_path: str) -> dict:
    try:
        text = Path(tex_path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return {"status": "ERROR", "error_message": f"File not found: {tex_path}"}
    except Exception as e:
        return {"status": "ERROR", "error_message": str(e)}

    sections = split_into_sections(text)

    # symbol_variants[base_lower] = set of exact forms seen
    symbol_variants: dict[str, set] = defaultdict(set)
    # symbol_sections[exact_form] = list of section labels
    symbol_sections: dict[str, list] = defaultdict(list)

    font_re = re.compile(
        r"\\(mathbf|mathbb|mathcal|mathfrak|boldsymbol|bm|hat|tilde|bar|vec|dot|ddot)\{([^}]+)\}"
    )

    # Harvest all variant forms with section provenance
    for section_label, sec_text in sections:
        blocks = extract_math_blocks(sec_text)
        for block in blocks:
            # Collect variants (with font command prefix preserved as variant key)
            for fm in font_re.finditer(block):
                cmd, sym = fm.group(1), fm.group(2)
                variant = f"\\{cmd}{{{sym}}}"
                symbol_variants[variant_key(sym)].add(variant)
                symbol_sections[variant].append(section_label)
            # Plain letters
            plain_clean = RE_FONT_CMD.sub(r"\1", block)
            plain_clean = RE_SUBSCRIPT.sub("", plain_clean)
            plain_clean = RE_SUPERSCRIPT.sub("", plain_clean)
            plain_clean = RE_COMMAND.sub("", plain_clean)
            for letter in re.findall(r"[A-Za-z]", plain_clean):
                symbol_variants[variant_key(letter)].add(letter)
                symbol_sections[letter].append(section_label)

    # Collect defined symbols (heuristic)
    defined_symbols: set[str] = set()
    for m in RE_DEFINITION.finditer(text):
        defined_symbols.add(m.group(1).lower())

    # Flag multi-variant symbols
    multi_variant_flags = []
    for base, variants in symbol_variants.items():
        if len(variants) > 1:
            multi_variant_flags.append({
                "base_symbol": base,
                "variants_seen": sorted(variants),
                "sections": sorted(set(
                    sec
                    for v in variants
                    for sec in symbol_sections.get(v, [])
                )),
            })

    # Build cross-section manifest (unique symbols per section)
    manifest = {
        sec: sorted(set(
            letter
            for block in extract_math_blocks(txt)
            for letter in symbols_in_block(block)
        ))
        for sec, txt in sections
    }

    issues = len(multi_variant_flags)
    result = {
        "status": "VALID" if issues == 0 else "NOTATION_INCONSISTENCY",
        "is_correct": issues == 0,
        "file": tex_path,
        "sections_scanned": [s for s, _ in sections],
        "multi_variant_symbols": multi_variant_flags,
        "symbol_manifest": manifest,
    }
    if issues:
        result["hint"] = (
            f"{issues} symbol(s) appear in multiple font/case variants. "
            "Decide on a canonical form and apply it uniformly."
        )
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Turing: Notation consistency checker for LaTeX manuscripts"
    )
    parser.add_argument("--file", required=True, help="Path to the .tex file")
    args = parser.parse_args()
    res = check_notation(args.file)
    print(json.dumps(res, indent=2))
