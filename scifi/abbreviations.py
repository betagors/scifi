"""
Manuscript abbreviation and acronym hygiene auditor (scifi.abbreviations).

Evaluates academic manuscripts for:
1. First-occurrence definitions in both the abstract and the main body.
2. One-use / low-use abbreviations that add cognitive overhead without payoff.
3. Invented or artificially constructed compound algorithm acronyms and variant labels
   (e.g., ``Lya-BiMAPPO``, ``Safe-Pure-MAPPO``, ``Lya-BiMAPPO-MaxSNR``).
4. Sentence-level abbreviation overload (stacking 4+ acronyms in a single sentence).
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# Universal acronyms that do not require first-occurrence expansion in technical papers
UNIVERSAL_ACRONYMS: set[str] = {
    "AI",
    "ML",
    "DL",
    "RL",
    "CPU",
    "GPU",
    "TPU",
    "RAM",
    "ROM",
    "SSD",
    "API",
    "URL",
    "URI",
    "DOI",
    "PDF",
    "EPS",
    "SVG",
    "PNG",
    "JPEG",
    "JPG",
    "CSV",
    "TSV",
    "JSON",
    "XML",
    "HTML",
    "HTTP",
    "HTTPS",
    "UTF",
    "ASCII",
    "RGB",
    "DPI",
    "IEEE",
    "ACM",
    "SIAM",
    "AAAI",
    "ICML",
    "ICLR",
    "CVPR",
    "ECCV",
    "ICCV",
    "ACL",
    "EMNLP",
    "NAACL",
    "US",
    "UK",
    "EU",
    "USA",
    "ID",
    "OK",
    "OS",
    "PC",
    "IO",
    "AM",
    "PM",
    "VS",
    "DNA",
    "RNA",
    "PH",
    "LED",
    "USB",
    "SSD",
    "SQL",
    "CLI",
    "GUI",
    "SDK",
}

# Non-acronym tokens that match uppercase/mixed-case patterns
NON_ACRONYM_TOKENS: set[str] = {
    "I",
    "II",
    "III",
    "IV",
    "VI",
    "VII",
    "VIII",
    "IX",
    "XI",
    "XII",
    "LaTeX",
    "BibTeX",
    "TeX",
    "XeTeX",
    "LuaTeX",
    "PyTorch",
    "TensorFlow",
    "OpenAI",
    "GitHub",
    "ResNet",
    "DenseNet",
    "ConvNeXt",
    "MobileNet",
    "EfficientNet",
    "GraphSAGE",
    "DeepMind",
    "ChatGPT",
    "macOS",
    "iOS",
    "kHz",
    "MHz",
    "GHz",
    "THz",
    "dBm",
    "mRNA",
    "tRNA",
    "siRNA",
    "miRNA",
    "cDNA",
    "dsDNA",
    "kNN",
    "tSNE",
    "TBD",
    "TODO",
    "NA",
    "ET",
    "AL",
    "EG",
    "IE",
    "CF",
    "FIG",
    "TAB",
    "EQ",
    "SEC",
    "ALG",
    "APP",
    "THM",
    "LEM",
    "PROP",
    "COR",
    "DEF",
    "REM",
}

# Modifier prefixes commonly attached to algorithm acronyms to form awkward compound labels
_COMPOUND_MODIFIER_PREFIXES: set[str] = {
    "lya",
    "lyap",
    "penalty",
    "pure",
    "safe",
    "vanilla",
    "naive",
    "full",
    "base",
    "adaptive",
    "improved",
    "enhanced",
    "modified",
    "standard",
    "proposed",
    "no",
    "non",
    "without",
}

_KNOWN_ALGO_SUFFIXES: set[str] = {
    "MAPPO",
    "PPO",
    "DQN",
    "SAC",
    "DDPG",
    "TD3",
    "A2C",
    "A3C",
    "TRPO",
    "MARL",
    "MPC",
    "CBF",
    "SQP",
    "SCA",
    "MCTS",
    "RL",
    "DRL",
}

_NON_DEFINING_PRECEDERS: set[str] = {
    "see",
    "for",
    "via",
    "with",
    "using",
    "e.g.",
    "i.e.",
    "cf.",
    "eq.",
    "fig.",
    "tab.",
    "sec.",
    "alg.",
    "and",
    "or",
    "of",
    "in",
    "to",
    "as",
}

_RE_COMMENTS = re.compile(r"(?<!\\)%[^\n]*")
_RE_MATH_ENV = re.compile(
    r"\\begin\{(equation|align|gather|multline|eqnarray)\*?\}.*?\\end\{\1\*?\}",
    re.DOTALL,
)
_RE_DISPLAY_DOLLAR = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_RE_DISPLAY_BRACKET = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_RE_INLINE_DOLLAR = re.compile(r"(?<!\\)\$(?!\$).*?(?<!\\)\$", re.DOTALL)
_RE_LATEX_SKIP_CMD = re.compile(
    r"\\(?:cite[a-zA-Z]*|ref|eqref|autoref|cref|Cref|label|url|href|includegraphics|"
    r"bibliography|bibliographystyle|usepackage|documentclass|newcommand|renewcommand|"
    r"providecommand|DeclareMathOperator|definecolor|hypersetup)\*?"
    r"(?:\[[^\]]*\])?(?:\{[^{}]*\})+"
)
_RE_LATEX_CMD_NAME = re.compile(r"\\[a-zA-Z]+\*?")
_RE_NEWACRONYM = re.compile(r"\\newacronym(?:\[[^\]]*\])?\{[^}]+\}\{([A-Za-z0-9-]+)\}\{[^}]+\}")
_RE_ACRO = re.compile(r"\\acro\{([A-Za-z0-9-]+)\}(?:\[[^\]]*\])?\{[^}]+\}")
_RE_ABSTRACT_BLOCK = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.DOTALL)
_RE_DOC_START = re.compile(r"\\begin\{document\}")
_RE_SECTION_ALL_CAPS = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([A-Z0-9\s:,-]+)\}")

# Matches parenthetical definition: "Full Term (ABBR)" or "Full Term (ABBRs)"
_RE_PAREN_DEF = re.compile(r"([A-Za-z][A-Za-z0-9'/-]*(?:\s+[A-Za-z][A-Za-z0-9'/-]*){1,10})\s*\(([A-Za-z0-9-]{2,15})\)")

# Matches blended/invented camelCase-to-ALLCAPS algorithm acronyms (e.g. BiMAPPO, Lya-BiMAPPO)
_RE_BLENDED_ALGO = re.compile(r"\b(?:[A-Z][a-z]{1,8}-)*[A-Z][a-z]{1,4}[A-Z]{3,}[A-Za-z0-9]*\b")

# Matches hyphenated compound tokens containing at least one uppercase acronym segment
_RE_HYPHEN_COMPOUND = re.compile(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b")

# Matches candidate acronym tokens (2+ uppercase letters, optionally mixed case like LoS, NLoS, IoT)
_RE_ACRONYM_TOKEN = re.compile(r"\b[A-Za-z0-9]{2,14}\b")

# Sentence boundary splitter (ignores common abbreviations)
_RE_SENTENCE_SPLIT = re.compile(
    r"(?<!Fig)(?<!Eq)(?<!Sec)(?<!Tab)(?<!Alg)(?<!al)(?<!e\.g)(?<!i\.e)(?<!vs)[.!?]\s+|\n\s*\n"
)


def _line_number_at_offset(text: str, offset: int) -> int:
    """Return 1-based line number for a character offset in text."""
    return text.count("\n", 0, max(0, offset)) + 1


def _map_line(
    line_no: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None = None,
) -> tuple[str | None, int]:
    """Resolve a 1-based merged line number to (file, line) provenance."""
    if line_map and 1 <= line_no <= len(line_map):
        return line_map[line_no - 1]
    return default_file, line_no


def _mask_span_with_spaces(text: str, pattern: re.Pattern[str]) -> str:
    """Replace regex matches with spaces while preserving newlines to keep line offsets intact."""

    def _repl(match: re.Match[str]) -> str:
        s = match.group(0)
        return "".join("\n" if ch == "\n" else " " for ch in s)

    return pattern.sub(_repl, text)


def _canonicalize_acronym(token: str) -> str:
    """Normalize plural suffix 's' on all-caps/mixed acronyms (e.g. UAVs -> UAV)."""
    if len(token) >= 3 and token.endswith("s") and token[:-1].isupper():
        return token[:-1]
    return token


def _is_candidate_acronym(token: str) -> bool:
    """Return True if token looks like a technical acronym/abbreviation."""
    if token in NON_ACRONYM_TOKENS:
        return False
    canon = _canonicalize_acronym(token)
    if canon in NON_ACRONYM_TOKENS:
        return False
    if len(canon) < 2 or len(canon) > 10:
        return False
    if canon.isdigit():
        return False
    # Must contain at least 2 uppercase letters (covers UAV, MAPPO, IoT, LoS, NLoS, 5G? No, 5G has 1)
    upper_count = sum(1 for ch in canon if ch.isupper())
    if upper_count >= 2:
        # Exclude pure TitleCase words (e.g. "Abc") — already requires 2+ uppercase
        # Exclude words like "McDonald" if somehow 2 uppercase unless short
        return True
    return False


def _sanitize_latex_preserving_lines(tex_source: str) -> tuple[str, set[str], tuple[int, int] | None, int]:
    """
    Strip comments, preamble, math blocks, and non-prose LaTeX commands while
    preserving exact character/line offsets.

    Returns:
        (masked_text, glossary_defined_acronyms, abstract_span, body_start_offset)
    """
    glossary_defined: set[str] = set()
    for m in _RE_NEWACRONYM.finditer(tex_source):
        glossary_defined.add(_canonicalize_acronym(m.group(1)))
    for m in _RE_ACRO.finditer(tex_source):
        glossary_defined.add(_canonicalize_acronym(m.group(1)))

    masked = _mask_span_with_spaces(tex_source, _RE_COMMENTS)

    abstract_match = _RE_ABSTRACT_BLOCK.search(masked)
    abstract_span: tuple[int, int] | None = (abstract_match.start(1), abstract_match.end(1)) if abstract_match else None

    doc_match = _RE_DOC_START.search(masked)
    doc_start = doc_match.end() if doc_match else 0
    if doc_start > 0:
        # Mask preamble
        masked = "".join("\n" if ch == "\n" else " " for ch in masked[:doc_start]) + masked[doc_start:]

    body_start = abstract_match.end() if abstract_match else doc_start

    # Mask all-caps section titles so \section{INTRODUCTION} doesn't trigger false positives
    def _mask_caps_section(m: re.Match[str]) -> str:
        inner = m.group(1)
        return m.group(0).replace(inner, " " * len(inner))

    masked = _RE_SECTION_ALL_CAPS.sub(_mask_caps_section, masked)

    for pat in (
        _RE_MATH_ENV,
        _RE_DISPLAY_DOLLAR,
        _RE_DISPLAY_BRACKET,
        _RE_INLINE_DOLLAR,
        _RE_LATEX_SKIP_CMD,
        _RE_LATEX_CMD_NAME,
    ):
        masked = _mask_span_with_spaces(masked, pat)

    # Replace braces/brackets with spaces so tokens inside \textbf{...} remain cleanly bounded
    masked = re.sub(r"[{}]", " ", masked)
    return masked, glossary_defined, abstract_span, body_start


def _scan_awkward_algorithm_labels(text: str) -> tuple[dict[str, int], dict[str, int]]:
    """Scan text for invented/blended algorithm acronyms and compound variant labels."""
    invented_algos: dict[str, int] = {}
    compound_variants: dict[str, int] = {}
    covered_spans: list[tuple[int, int]] = []

    for m in _RE_HYPHEN_COMPOUND.finditer(text):
        tok = m.group(0)
        parts = tok.split("-")
        has_3plus_upper = any(len(p) >= 3 and p.isupper() for p in parts)
        has_blended_part = any(_RE_BLENDED_ALGO.fullmatch(p) and p not in NON_ACRONYM_TOKENS for p in parts)
        if not (has_3plus_upper or has_blended_part):
            continue
        if len(parts) >= 3:
            compound_variants.setdefault(tok, m.start())
            covered_spans.append((m.start(), m.end()))
        elif (
            len(parts) == 2
            and parts[0].lower() in _COMPOUND_MODIFIER_PREFIXES
            and (parts[1] in _KNOWN_ALGO_SUFFIXES or has_blended_part)
        ):
            if parts[0].lower() == "lya" and has_blended_part:
                invented_algos.setdefault(tok, m.start())
            else:
                compound_variants.setdefault(tok, m.start())
            covered_spans.append((m.start(), m.end()))
        elif has_blended_part:
            invented_algos.setdefault(tok, m.start())
            covered_spans.append((m.start(), m.end()))

    for m in _RE_BLENDED_ALGO.finditer(text):
        tok = m.group(0)
        if tok in NON_ACRONYM_TOKENS:
            continue
        if any(s <= m.start() and m.end() <= e for s, e in covered_spans):
            continue
        invented_algos.setdefault(tok, m.start())

    return invented_algos, compound_variants


def find_awkward_algorithm_labels(text: str) -> tuple[list[str], list[str]]:
    """Return sorted (invented_algorithm_acronyms, compound_algorithm_variants) found in text."""
    invented, compound = _scan_awkward_algorithm_labels(text)
    return sorted(invented.keys()), sorted(compound.keys())


def evaluate_abbreviation_hygiene(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Audit manuscript abbreviations and acronyms across four dimensions:
    1. First-occurrence definitions in abstract and main body.
    2. One-use / low-use abbreviations that create unnecessary cognitive load.
    3. Invented blended or compound algorithm variant acronyms.
    4. Sentence-level abbreviation overload (4+ distinct acronyms in one sentence).
    """
    masked, glossary_defined, abstract_span, body_start = _sanitize_latex_preserving_lines(tex_source)
    flags: list[dict[str, Any]] = []

    def _make_flag(
        offset: int,
        severity: str,
        matched_text: str,
        explanation: str,
        remedy: str,
    ) -> dict[str, Any]:
        line_no = _line_number_at_offset(tex_source, offset)
        file_name, mapped_line = _map_line(line_no, line_map, default_file)
        return {
            "dimension": "abbreviations",
            "severity": severity,
            "file": file_name,
            "line": mapped_line,
            "matched_text": matched_text,
            "explanation": explanation,
            "remedy": remedy,
        }

    # ── 1. Detect Invented & Compound Algorithm Acronyms ─────────────────────
    invented_algos, compound_variants = _scan_awkward_algorithm_labels(masked)

    for tok, offset in invented_algos.items():
        flags.append(
            _make_flag(
                offset,
                "MEDIUM",
                tok,
                f"Invented/blended algorithm acronym '{tok}' looks artificially constructed.",
                f"Simplify '{tok}' to a clear, academically readable name in prose (e.g., expanding the prefix) and use a short label only if needed in figures/tables.",
            )
        )

    for tok, offset in compound_variants.items():
        flags.append(
            _make_flag(
                offset,
                "MEDIUM",
                tok,
                f"Compound algorithm variant label '{tok}' adds unnecessary notation overhead.",
                f"Replace '{tok}' with a descriptive experimental label such as 'MAPPO (safety-filtered)' or 'Proposed method (variant)'.",
            )
        )

    # ── 2. Extract Definitions & Occurrences ─────────────────────────────────
    abstract_defs: dict[str, int] = {}
    body_defs: dict[str, int] = {}
    for m in _RE_PAREN_DEF.finditer(masked):
        preceding = m.group(1).strip()
        last_word = preceding.split()[-1].lower()
        if last_word in _NON_DEFINING_PRECEDERS:
            continue
        abbr = _canonicalize_acronym(m.group(2))
        if not _is_candidate_acronym(abbr):
            continue
        offset = m.start(2)
        if abstract_span and abstract_span[0] <= offset <= abstract_span[1]:
            abstract_defs.setdefault(abbr, offset)
        elif offset >= body_start:
            body_defs.setdefault(abbr, offset)

    # Collect occurrences in abstract and body
    abstract_occ: dict[str, list[int]] = {}
    body_occ: dict[str, list[int]] = {}
    total_counts: Counter[str] = Counter()

    for m in _RE_ACRONYM_TOKEN.finditer(masked):
        raw_tok = m.group(0)
        if not _is_candidate_acronym(raw_tok):
            continue
        canon = _canonicalize_acronym(raw_tok)
        offset = m.start()
        total_counts[canon] += 1
        if abstract_span and abstract_span[0] <= offset <= abstract_span[1]:
            abstract_occ.setdefault(canon, []).append(offset)
        elif offset >= body_start:
            body_occ.setdefault(canon, []).append(offset)

    # ── 3. First-Occurrence Definition Audit ─────────────────────────────────
    undefined_in_abstract: list[str] = []
    for abbr, offsets in sorted(abstract_occ.items()):
        if abbr in UNIVERSAL_ACRONYMS or abbr in glossary_defined:
            continue
        if abbr not in abstract_defs:
            undefined_in_abstract.append(abbr)
            flags.append(
                _make_flag(
                    offsets[0],
                    "MEDIUM",
                    abbr,
                    f"Abbreviation '{abbr}' is used in the abstract without being defined at first occurrence.",
                    f"Define '{abbr}' on its first occurrence in the abstract (e.g., 'Full Term ({abbr})') or spell it out.",
                )
            )

    undefined_in_body: list[str] = []
    for abbr, offsets in sorted(body_occ.items()):
        if abbr in UNIVERSAL_ACRONYMS or abbr in glossary_defined:
            continue
        if abbr not in body_defs:
            undefined_in_body.append(abbr)
            flags.append(
                _make_flag(
                    offsets[0],
                    "MEDIUM",
                    abbr,
                    f"Abbreviation '{abbr}' is used in the main text without a first-occurrence definition in the body.",
                    f"Define '{abbr}' at its first occurrence in the main text (even if already defined in the abstract).",
                )
            )
        elif offsets[0] < body_defs[abbr]:
            flags.append(
                _make_flag(
                    offsets[0],
                    "MEDIUM",
                    abbr,
                    f"Abbreviation '{abbr}' is used in the main text before its definition.",
                    f"Move the full expansion 'Full Term ({abbr})' to the first occurrence of '{abbr}' in the main text.",
                )
            )

    # ── 4. One-Use / Low-Use Abbreviations ───────────────────────────────────
    low_use_abbrs: list[str] = []
    all_defined = set(abstract_defs) | set(body_defs)
    for abbr in sorted(all_defined):
        if abbr in UNIVERSAL_ACRONYMS:
            continue
        if total_counts[abbr] <= 2:
            low_use_abbrs.append(abbr)
            offset = body_defs.get(abbr, abstract_defs.get(abbr, 0))
            flags.append(
                _make_flag(
                    offset,
                    "LOW",
                    abbr,
                    f"Abbreviation '{abbr}' is defined but appears only {total_counts[abbr]} time(s) in the manuscript.",
                    f"Remove the one- or two-use abbreviation '{abbr}' and keep its full expression to reduce reader overhead.",
                )
            )

    # ── 5. Sentence-Level Abbreviation Overload ──────────────────────────────
    overloaded_sentences_count = 0
    pos = 0
    for seg in _RE_SENTENCE_SPLIT.split(masked):
        seg_start = masked.find(seg, pos)
        if seg_start == -1:
            seg_start = pos
        pos = seg_start + len(seg)
        stripped_seg = seg.strip()
        if not stripped_seg or "&" in stripped_seg or "\\\\" in stripped_seg:
            continue
        abbrs_in_sentence: list[str] = []
        seen_in_sentence: set[str] = set()
        for m in _RE_ACRONYM_TOKEN.finditer(seg):
            tok = m.group(0)
            if _is_candidate_acronym(tok):
                canon = _canonicalize_acronym(tok)
                if canon not in seen_in_sentence:
                    seen_in_sentence.add(canon)
                    abbrs_in_sentence.append(canon)
        if len(abbrs_in_sentence) >= 4:
            overloaded_sentences_count += 1
            snippet = " ".join(stripped_seg.split())[:120]
            flags.append(
                _make_flag(
                    seg_start,
                    "MEDIUM",
                    snippet,
                    f"Sentence stacks {len(abbrs_in_sentence)} distinct abbreviations ({', '.join(abbrs_in_sentence)}).",
                    "Avoid combining 4+ abbreviations in a single sentence; spell out secondary concepts in ordinary technical prose.",
                )
            )

    all_abbrs = sorted(total_counts.keys())
    issue_count = (
        len(invented_algos)
        + len(compound_variants)
        + len(undefined_in_abstract)
        + len(undefined_in_body)
        + len(low_use_abbrs)
        + overloaded_sentences_count
    )

    metrics: dict[str, Any] = {
        "total_abbreviations": len(all_abbrs),
        "abbreviations_found": all_abbrs,
        "defined_abbreviations": sorted(all_defined | glossary_defined),
        "undefined_in_abstract": undefined_in_abstract,
        "undefined_in_body": undefined_in_body,
        "low_use_abbreviations": low_use_abbrs,
        "invented_algorithm_acronyms": sorted(invented_algos.keys()),
        "compound_algorithm_variants": sorted(compound_variants.keys()),
        "overloaded_sentences_count": overloaded_sentences_count,
        "issue_count": issue_count,
    }
    return metrics, flags
