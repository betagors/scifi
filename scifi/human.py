"""
scifi.human — Master Academic Humanizer & LaTeX Stylometric Forensic Auditor.

Evaluates academic manuscripts (single .tex files, multi-file LaTeX directories,
or plain/Markdown text) across six forensic dimensions that distinguish authentic
human-authored scientific source code from synthetic (LLM-generated) markup:

1. List Environments (Itemize / Enumerate Signature):
   - Clausal itemize-bold ratio R_IB (\\item \\textbf{...}:)
   - Item character-length coefficient of variation CV = sigma / mu (< 0.15 synthetic vs > 0.40 human)
   - Rigid cardinality clustering at N in {3, 5}
2. Document Preamble & Package Stack (S_preamble):
   - Uncurated "kitchen-sink" package imports (amsmath, amssymb, amsfonts, graphicx,
     booktabs, hyperref, geometry, microtype)
   - Unused package detection (e.g. booktabs or graphicx imported but never invoked)
   - Stereotypical saturated hyperref color configuration (linkcolor=blue, citecolor=blue)
3. Tabular Markup & Structural Rigidity:
   - Unweighted single-character column specifiers (cccc, lcccc with >= 4 columns)
     lacking width management (p{...}, m{...}, tabular*, tabularx, \\makecell, \\tabcolsep)
4. Macro Abstraction Ratio (mu_macro):
   - Ratio of author-defined macros (\\newcommand, \\def, \\DeclareMathOperator) to raw
     canonical math expansions (\\mathbb, \\mathcal, \\mathbf, \\mathfrak, \\mathsf)
5. Mathematical Syntax & Notational Quirks:
   - Conversational English inside display math (\\text{where }, \\text{such that}, \\text{for all})
     measured via natural language density rho_math_text
   - Inline math over-sanitization ($k$-th, trailing sentence punctuation inside $...$)
   - Un-scoped multi-letter italic word subscripts (e.g. W_{loss} instead of W_{\\mathrm{loss}})
   - Alignment monoculture & missing typographic micro-spacing (unspaced differentials dx, d\\tau)
6. Stylometric & Linguistic Indicators Embedded in TeX:
   - Kobak et al. excess AI style vocabulary (delve, pivotal, intricate, crucial, notably,
     underscores, showcasing, tapestry, testament, groundbreaking, seamless, realm, etc.)
   - Structural boundary clustering (abstract opening, section opening, pre-equation transitions)
   - Conversational em-dashes (Unicode — or LaTeX --- in prose)
   - Sentence-length Burstiness B_length = sigma(L_s) / mu(L_s) (< 0.28 synthetic vs > 0.55 human)
   - Paragraph token standard deviation sigma_para and redundant \\subsection summary wrap-ups
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

from scifi.latex.project import resolve_latex_project, strip_tex_comments

# ---------------------------------------------------------------------------
# Constants & Forensic Dictionaries
# ---------------------------------------------------------------------------

KITCHEN_SINK_PACKAGES: set[str] = {
    "amsmath",
    "amssymb",
    "amsfonts",
    "graphicx",
    "booktabs",
    "hyperref",
    "geometry",
    "microtype",
}

# Kobak et al. excess style words and high-signal synthetic academic tropes
EXCESS_STYLE_WORDS: dict[str, str] = {
    "delve": "Replace with 'investigate', 'examine', or 'analyze'.",
    "delves": "Replace with 'investigates', 'examines', or 'analyzes'.",
    "delving": "Replace with 'investigating', 'examining', or 'analyzing'.",
    "pivotal": "Remove significance inflation or replace with 'central' or 'primary'.",
    "intricate": "Replace with 'complex', 'coupled', or specific structural descriptors.",
    "crucial": "Replace with 'necessary', 'essential', or state the technical condition directly.",
    "crucially": "Eliminate editorializing sentence adverb; state the empirical observation directly.",
    "notably": "Remove formulaic sentence starter or integrate into a subordinate clause.",
    "underscore": "Replace with 'indicate', 'demonstrate', or 'confirm'.",
    "underscores": "Replace with 'indicates', 'demonstrates', or 'confirms'.",
    "underscoring": "Replace with 'indicating', 'demonstrating', or 'confirming'.",
    "showcasing": "Replace with 'demonstrating' or 'illustrating'.",
    "showcase": "Replace with 'demonstrate' or 'illustrate'.",
    "showcases": "Replace with 'demonstrates' or 'illustrates'.",
    "tapestry": "Eliminate metaphorical AI trope; use 'system', 'framework', or 'architecture'.",
    "testament": "Eliminate promotional phrasing ('testament to'); state empirical evidence directly.",
    "beacon": "Eliminate metaphorical AI trope.",
    "groundbreaking": "Eliminate promotional adjective; specify the exact technical novelty.",
    "game-changer": "Eliminate promotional buzzword.",
    "vital": "Replace with 'necessary' or 'primary', or remove significance inflation.",
    "fostering": "Replace with 'facilitating', 'enabling', or 'inducing'.",
    "multifaceted": "Replace with specific dimensional or multi-objective descriptors.",
    "realm": "Replace 'in the realm of' with 'in' or 'within'.",
    "seamless": "Replace with 'continuous', 'integrated', or 'uninterrupted'.",
    "seamlessly": "Replace with 'directly' or 'without interface overhead'.",
    "undeniable": "Eliminate unhedged certainty; use epistemic hedging ('suggests', 'indicates').",
    "ever-evolving": "Eliminate cliché opener ('in the ever-evolving landscape').",
    "unprecedented": "Avoid unquantified superlative unless backed by historical benchmark bounds.",
    "meticulous": "Remove self-congratulatory adjective; describe the experimental protocol.",
    "meticulously": "Remove self-congratulatory adverb; state the procedure in passive voice.",
}

EXCESS_STYLE_PHRASES: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"\bit\s+is\s+(?:crucial|important|worth|essential|vital)\s+to\s+note\s+that\b", re.IGNORECASE),
        "it is [crucial/worth] to note that",
        "Delete conversational meta-commentary; state the technical proposition directly.",
    ),
    (
        re.compile(r"\bit\s+is\s+worth\s+noting\s+that\b", re.IGNORECASE),
        "it is worth noting that",
        "Delete filler meta-clause and lead with the grammatical subject.",
    ),
    (
        re.compile(r"\bmarks\s+a\s+paradigm\s+shift\b", re.IGNORECASE),
        "marks a paradigm shift",
        "Eliminate significance inflation; state the specific methodological difference.",
    ),
    (
        re.compile(r"\bin\s+the\s+realm\s+of\b", re.IGNORECASE),
        "in the realm of",
        "Replace verbose prepositional phrase with 'in'.",
    ),
    (
        re.compile(r"\bserves\s+as\s+a\s+testament\b", re.IGNORECASE),
        "serves as a testament",
        "Replace inflated copula and trope with 'demonstrates' or 'indicates'.",
    ),
]

# Multi-letter English words commonly left un-scoped in math subscripts by LLMs
UNSCOPED_SUBSCRIPT_WORDS: set[str] = {
    "loss",
    "train",
    "val",
    "test",
    "reg",
    "total",
    "max",
    "min",
    "init",
    "out",
    "in",
    "attn",
    "proj",
    "emb",
    "pred",
    "true",
    "opt",
    "data",
    "kl",
    "ce",
    "mse",
    "norm",
    "feat",
    "hidden",
    "layer",
    "batch",
}

RE_DISPLAY_MATH = re.compile(
    r"\\begin\{(equation\*?|align\*?|gather\*?|multline\*?|eqnarray\*?)\}(.*?)\\end\{\1\}"
    r"|\\\[(.*?)\\\]"
    r"|\$\$(.*?)\$\$",
    re.DOTALL,
)

RE_LIST_ENV = re.compile(
    r"\\begin\{(itemize|enumerate)\}(?:\[[^\]]*\])?(.*?)\\end\{\1\}",
    re.DOTALL,
)

RE_TABULAR_ENV = re.compile(
    r"\\begin\{(tabular\*?|tabularx)\}(?:\{[^}]*\})?\{([^}]*)\}(.*?)\\end\{\1\}",
    re.DOTALL,
)

RE_PRE_EQ_TRANSITION = re.compile(
    r"\b(Moreover|Furthermore|Crucially|Notably|Importantly|Specifically|It is worth noting that)\b[^.!?\n]*:\s*$"
)


def _mean_std_cv(values: list[float]) -> tuple[float, float, float]:
    """Compute population mean, standard deviation, and coefficient of variation (sigma / mu)."""
    if not values:
        return 0.0, 0.0, 0.0
    n = len(values)
    mu = sum(values) / n
    if mu == 0.0 or n < 2:
        return mu, 0.0, 0.0
    var = sum((v - mu) ** 2 for v in values) / n
    sigma = math.sqrt(var)
    return mu, sigma, sigma / mu


def _map_line(
    line_no: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None = None,
) -> tuple[str | None, int]:
    """Resolve a 1-based merged line number to (file, line) provenance."""
    if line_map and 1 <= line_no <= len(line_map):
        return line_map[line_no - 1]
    return default_file, line_no


def _line_number_at_offset(text: str, offset: int) -> int:
    """Return 1-based line number for a character offset in text."""
    return text.count("\n", 0, max(0, offset)) + 1


# ---------------------------------------------------------------------------
# 1. List Environments (Itemize / Enumerate Signature)
# ---------------------------------------------------------------------------


def evaluate_list_fingerprints(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Evaluate `itemize` and `enumerate` environments for synthetic formatting templates:
    - Bold-prefix ratio R_IB (\\item \\textbf{...}:) >= 0.80
    - Item character-count coefficient of variation CV < 0.15
    - Rigid cardinality clustering at N in {3, 5}
    """
    clean = strip_tex_comments(tex_source)
    blocks: list[dict[str, Any]] = []
    anomalous_blocks: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []

    for idx, match in enumerate(RE_LIST_ENV.finditer(clean)):
        env_name = match.group(1)
        content = match.group(2).strip()
        raw_line = _line_number_at_offset(clean, match.start())
        src_file, src_line = _map_line(raw_line, line_map, default_file)

        items = [it.strip() for it in re.split(r"\\item(?:\[[^\]]*\])?\s+", content)[1:] if it.strip()]
        if len(items) < 2:
            continue

        bold_prefix_count = sum(1 for it in items if re.match(r"^\\textbf\{[^}]+\}\s*[:.]|^\\textbf\{[^}]+:\}", it))
        lengths = [float(len(re.sub(r"\s+", " ", it))) for it in items]
        _, _, cv = _mean_std_cv(lengths)
        bold_ratio = bold_prefix_count / len(items)
        is_clustered_cardinality = len(items) in (3, 5)

        is_anomalous = len(items) >= 3 and (
            (bold_ratio >= 0.80 and cv < 0.18) or (bold_ratio >= 0.80 and is_clustered_cardinality and cv < 0.25)
        )

        block_info: dict[str, Any] = {
            "list_id": idx,
            "environment": env_name,
            "item_count": len(items),
            "bold_ratio": round(bold_ratio, 3),
            "length_cv": round(cv, 3),
            "is_cardinality_3_or_5": is_clustered_cardinality,
            "is_anomalous": is_anomalous,
            "line": src_line,
        }
        if src_file:
            block_info["file"] = src_file
        blocks.append(block_info)

        if is_anomalous:
            anomalous_blocks.append(block_info)
            flag: dict[str, Any] = {
                "dimension": "list_environments",
                "severity": "WARNING",
                "line": src_line,
                "matched_text": f"\\begin{{{env_name}}} ({len(items)} items, R_IB={bold_ratio:.2f}, CV={cv:.2f})",
                "explanation": (
                    f"Synthetic list fingerprint: {bold_prefix_count}/{len(items)} items use "
                    f"'\\item \\textbf{{...}}:' template with uniform clausal lengths (CV={cv:.2f} < 0.25)."
                ),
                "remedy": (
                    "Convert bulleted list into integrated body paragraphs, remove repetitive "
                    "\\textbf{...}: lead-ins, or vary clausal structure and length across items (target CV > 0.40)."
                ),
            }
            if src_file:
                flag["file"] = src_file
            flags.append(flag)

    metrics = {
        "total_lists": len(blocks),
        "anomalous_lists_count": len(anomalous_blocks),
        "anomalous_lists": anomalous_blocks,
        "all_lists": blocks,
    }
    return metrics, flags


# ---------------------------------------------------------------------------
# 2. Document Preamble & Package Stack (S_preamble)
# ---------------------------------------------------------------------------


def evaluate_preamble_fingerprint(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Inspect the LaTeX preamble for:
    - Kitchen-sink package imports (amsmath, amssymb, amsfonts, graphicx, booktabs, hyperref, geometry, microtype)
    - Uninvoked packages (e.g. booktabs imported without tabular/\\toprule, graphicx without \\includegraphics)
    - Stereotypical saturated hyperref colors (linkcolor=blue, citecolor=blue)
    """
    clean = strip_tex_comments(tex_source)
    doc_split = re.split(r"\\begin\{document\}", clean, maxsplit=1)
    if len(doc_split) < 2:
        return {
            "has_preamble": False,
            "imported_packages": [],
            "kitchen_sink_overlap": [],
            "unused_packages": [],
            "stereotypical_hyperref": False,
        }, []

    preamble, body = doc_split[0], doc_split[1]
    flags: list[dict[str, Any]] = []

    imported_packages: list[str] = []
    pkg_lines: dict[str, int] = {}
    for m in re.finditer(r"\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}", preamble):
        raw_line = _line_number_at_offset(preamble, m.start())
        for pkg in m.group(1).split(","):
            p_clean = pkg.strip()
            if p_clean and p_clean not in imported_packages:
                imported_packages.append(p_clean)
                pkg_lines[p_clean] = raw_line

    kitchen_overlap = sorted(KITCHEN_SINK_PACKAGES.intersection(imported_packages))

    # Check for unused packages in body
    unused_packages: list[str] = []
    if "booktabs" in imported_packages and not re.search(r"\\(?:toprule|midrule|bottomrule|cmidrule)\b", body):
        unused_packages.append("booktabs")
    if "graphicx" in imported_packages and not re.search(r"\\(?:includegraphics|resizebox|scalebox|rotatebox)\b", body):
        unused_packages.append("graphicx")

    for upkg in unused_packages:
        src_file, src_line = _map_line(pkg_lines.get(upkg, 1), line_map, default_file)
        flag: dict[str, Any] = {
            "dimension": "preamble",
            "severity": "INFO",
            "line": src_line,
            "matched_text": f"\\usepackage{{{upkg}}}",
            "explanation": f"Package '{upkg}' is imported in the preamble but its macros are never invoked in the document body.",
            "remedy": f"Remove unused '\\usepackage{{{upkg}}}' from the preamble to avoid uncurated boilerplate.",
        }
        if src_file:
            flag["file"] = src_file
        flags.append(flag)

    # Check stereotypical hyperref blue configuration
    stereotypical_hyperref = False
    m_hyper = re.search(
        r"\\(?:hypersetup|usepackage)\s*(?:\[|\{)[^}\]]*colorlinks\s*=\s*true[^}\]]*"
        r"(?:linkcolor\s*=\s*(?:blue|magenta)|citecolor\s*=\s*(?:blue|magenta))",
        preamble,
        re.DOTALL | re.IGNORECASE,
    )
    has_custom_color = bool(re.search(r"\\definecolor\b", preamble))
    if m_hyper and not has_custom_color:
        stereotypical_hyperref = True
        raw_line = _line_number_at_offset(preamble, m_hyper.start())
        src_file, src_line = _map_line(raw_line, line_map, default_file)
        flag = {
            "dimension": "preamble",
            "severity": "INFO",
            "line": src_line,
            "matched_text": "colorlinks=true, linkcolor=blue, citecolor=blue",
            "explanation": "Stereotypical LLM hyperref configuration using raw saturated primary colors without custom xcolor definitions.",
            "remedy": (
                "Define a low-saturation palette via \\definecolor{darknavy}{rgb}{0.0, 0.1, 0.4} "
                "or use pdfborder={0 0 0} per camera-ready venue conventions."
            ),
        }
        if src_file:
            flag["file"] = src_file
        flags.append(flag)

    metrics = {
        "has_preamble": True,
        "imported_packages": imported_packages,
        "kitchen_sink_overlap": kitchen_overlap,
        "kitchen_sink_ratio": round(len(kitchen_overlap) / len(KITCHEN_SINK_PACKAGES), 3),
        "unused_packages": unused_packages,
        "stereotypical_hyperref": stereotypical_hyperref,
    }
    return metrics, flags


# ---------------------------------------------------------------------------
# 3. Tabular Markup & Structural Rigidity
# ---------------------------------------------------------------------------


def evaluate_tabular_fingerprint(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Inspect tabular environments for unweighted single-character column specifiers
    (e.g. `lcccc`, `ccccc` with >= 4 columns) lacking width/wrapping tuning.
    """
    clean = strip_tex_comments(tex_source)
    tables: list[dict[str, Any]] = []
    rigid_tables: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []

    for idx, match in enumerate(RE_TABULAR_ENV.finditer(clean)):
        env_name = match.group(1)
        col_spec = match.group(2).strip()
        body = match.group(3)
        raw_line = _line_number_at_offset(clean, match.start())
        src_file, src_line = _map_line(raw_line, line_map, default_file)

        # Look at surrounding 300 chars before \begin{tabular} for \tabcolsep or \resizebox
        window_start = max(0, match.start() - 280)
        surrounding = clean[window_start : match.end() + 120]

        stripped_spec = re.sub(r"[\s|]", "", col_spec)
        is_pure_single_char = bool(re.fullmatch(r"[lcr]{4,}", stripped_spec))
        has_layout_tuning = bool(
            env_name in ("tabular*", "tabularx")
            or re.search(r"[pmb]\{|X|@\{", col_spec)
            or re.search(r"\\(?:tabcolsep|resizebox|adjustbox|makecell|RaggedRight|cmidrule)\b", surrounding + body)
        )

        is_rigid = is_pure_single_char and not has_layout_tuning
        t_info: dict[str, Any] = {
            "table_id": idx,
            "environment": env_name,
            "column_spec": col_spec,
            "column_count": len(stripped_spec) if is_pure_single_char else None,
            "has_layout_tuning": has_layout_tuning,
            "is_rigid": is_rigid,
            "line": src_line,
        }
        if src_file:
            t_info["file"] = src_file
        tables.append(t_info)

        if is_rigid:
            rigid_tables.append(t_info)
            flag: dict[str, Any] = {
                "dimension": "tabular",
                "severity": "INFO",
                "line": src_line,
                "matched_text": f"\\begin{{{env_name}}}{{{col_spec}}}",
                "explanation": (
                    f"Unweighted single-character column specification '{col_spec}' ({len(stripped_spec)} columns) "
                    "without width constraints, cell wrapping, or \\tabcolsep tuning."
                ),
                "remedy": (
                    "Use fixed-width or wrapping columns (p{...}, tabularx with X, tabular* with @{\\extracolsep{\\fill}}), "
                    "\\makecell for multi-line headers, or tune \\setlength{\\tabcolsep}{...}."
                ),
            }
            if src_file:
                flag["file"] = src_file
            flags.append(flag)

    metrics = {
        "total_tables": len(tables),
        "rigid_tables_count": len(rigid_tables),
        "rigid_tables": rigid_tables,
        "all_tables": tables,
    }
    return metrics, flags


# ---------------------------------------------------------------------------
# 4. Macro Abstraction Ratio (mu_macro)
# ---------------------------------------------------------------------------


def evaluate_macro_abstraction(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Compute the authorial macro-to-expansion ratio:
      mu_macro = N_custom_macros / max(N_canonical_expansions, 1)
    """
    clean = strip_tex_comments(tex_source)
    flags: list[dict[str, Any]] = []

    custom_macros = re.findall(
        r"\\(?:newcommand|renewcommand|providecommand|DeclareMathOperator|DeclarePairedDelimiter)\*?\b|\\def\\[a-zA-Z]+",
        clean,
    )
    canonical_calls = re.findall(
        r"\\(?:mathbb|mathcal|mathbf|mathfrak|mathsf)\s*\{[^}]+\}",
        clean,
    )

    n_custom = len(custom_macros)
    n_canonical = len(canonical_calls)
    ratio = n_custom / max(n_canonical, 1)

    if n_canonical >= 8 and n_custom == 0:
        src_file, src_line = _map_line(1, line_map, default_file)
        flag: dict[str, Any] = {
            "dimension": "macros",
            "severity": "WARNING",
            "line": src_line,
            "matched_text": f"mu_macro = 0.00 ({n_canonical} canonical expansions, 0 custom macros)",
            "explanation": (
                f"Manuscript contains {n_canonical} raw canonical math expansions (e.g. \\mathbb, \\mathcal) "
                "with zero author-defined macro abstractions (\\newcommand, \\DeclareMathOperator)."
            ),
            "remedy": (
                "Define reusable semantic macros in the preamble (e.g. \\newcommand{\\R}{\\mathbb{R}}, "
                "\\newcommand{\\E}{\\mathbb{E}}, \\DeclareMathOperator{\\argmax}{arg\\,max}) and replace repetitive raw expansions."
            ),
        }
        if src_file:
            flag["file"] = src_file
        flags.append(flag)

    metrics = {
        "custom_macro_count": n_custom,
        "canonical_expansion_count": n_canonical,
        "macro_abstraction_ratio": round(ratio, 3),
    }
    return metrics, flags


# ---------------------------------------------------------------------------
# 5. Mathematical Syntax & Notational Quirks
# ---------------------------------------------------------------------------


def evaluate_math_syntax_quirks(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Evaluate mathematical environments and inline math for:
    - Conversational English commentary inside display math (rho_math_text)
    - Inline math over-sanitization ($k$-th, trailing punctuation trapped inside $...$)
    - Un-scoped multi-letter italic word subscripts (e.g. W_{loss})
    - Unspaced differential operators inside integrals (e.g. \\int f(x) dx without \\,)
    """
    clean = strip_tex_comments(tex_source)
    flags: list[dict[str, Any]] = []

    # 5.1 Conversational English commentary inside display math
    display_count = 0
    in_math_commentary_count = 0
    unspaced_differentials_count = 0
    micro_spacing_count = len(re.findall(r"\\[,!:;]", clean))

    for m in RE_DISPLAY_MATH.finditer(clean):
        display_count += 1
        math_body = m.group(2) or m.group(3) or m.group(4) or ""
        raw_line = _line_number_at_offset(clean, m.start())
        src_file, src_line = _map_line(raw_line, line_map, default_file)

        conv_matches = re.findall(
            r"\\(?:text|mathrm|mbox)\s*\{\s*(?:where|such\s+that|for\s+all|if\s+and\s+only\s+if|with\s+respect\s+to)\b[^}]*\}",
            math_body,
            re.IGNORECASE,
        )
        if conv_matches:
            in_math_commentary_count += len(conv_matches)
            flag: dict[str, Any] = {
                "dimension": "math_syntax",
                "severity": "WARNING",
                "line": src_line,
                "matched_text": conv_matches[0].strip(),
                "explanation": (
                    "Conversational English explanation embedded inside display math environment "
                    "rather than integrated into surrounding body prose."
                ),
                "remedy": (
                    "Terminate the display equation with a comma and move 'where ...' to the following "
                    "line of regular paragraph text (optionally preceded by \\noindent)."
                ),
            }
            if src_file:
                flag["file"] = src_file
            flags.append(flag)

        # Check for integrals with unspaced differential d\tau / dx
        if "\\int" in math_body:
            if re.search(r"(?<![\\,])\s+d(?:[a-zA-Z]|\\[a-zA-Z]+)\b", math_body):
                unspaced_differentials_count += 1

    rho_math_text = in_math_commentary_count / max(display_count, 1)

    # 5.2 Inline math over-sanitization & un-scoped word subscripts
    kth_count = 0
    trapped_punct_count = 0
    unscoped_subscript_count = 0

    for line_idx, line in enumerate(clean.splitlines(), start=1):
        src_file, src_line = _map_line(line_idx, line_map, default_file)

        # $i$-th / $k$-th pattern
        for m_kth in re.finditer(r"\$[a-zA-Z0-9]+\$-(?:th|st|nd|rd)\b", line):
            kth_count += 1
            if kth_count <= 3:
                flag = {
                    "dimension": "math_syntax",
                    "severity": "INFO",
                    "line": src_line,
                    "matched_text": m_kth.group(0),
                    "explanation": "Rigid token-boundary inline math hyphenation ('$k$-th').",
                    "remedy": "Prefer '$k$th' or '$k$\\textsuperscript{th}' consistently across the manuscript.",
                }
                if src_file:
                    flag["file"] = src_file
                flags.append(flag)

        # Trapped trailing punctuation inside inline math: e.g. $(x, y, z.)$ or $x = 1.$ followed by space/EOL
        for m_inline in re.finditer(r"(?<!\\)\$([^$\n]+?)(?<!\\)\$", line):
            inner = m_inline.group(1).strip()
            after_char = line[m_inline.end() : m_inline.end() + 2].strip()
            if (
                re.search(r"(?:[,.]|[,.]\s*\))$", inner)
                and not inner.endswith("\\dots")
                and not inner.endswith("\\ldots")
                and (not after_char or after_char[0].isupper() or after_char[0].islower())
            ):
                # Ensure the character immediately after closing $ is not another punctuation mark
                raw_after = line[m_inline.end() : m_inline.end() + 1]
                if raw_after not in (".", ",", ";", ":", ")"):
                    trapped_punct_count += 1
                    if trapped_punct_count <= 3:
                        flag = {
                            "dimension": "math_syntax",
                            "severity": "WARNING",
                            "line": src_line,
                            "matched_text": f"${inner}$",
                            "explanation": "Sentence-ending or clausal punctuation trapped inside inline math delimiters.",
                            "remedy": "Move trailing punctuation outside the closing '$' delimiter.",
                        }
                        if src_file:
                            flag["file"] = src_file
                        flags.append(flag)

        # Un-scoped multi-letter word subscripts: e.g. W_{loss} or \mathcal{L}_{reg}
        for m_sub in re.finditer(r"_\{([a-zA-Z]{2,10})\}", line):
            word = m_sub.group(1)
            if word.lower() in UNSCOPED_SUBSCRIPT_WORDS:
                unscoped_subscript_count += 1
                if unscoped_subscript_count <= 4:
                    flag = {
                        "dimension": "math_syntax",
                        "severity": "WARNING",
                        "line": src_line,
                        "matched_text": m_sub.group(0),
                        "explanation": (
                            f"Multi-letter textual subscript '{m_sub.group(0)}' is typeset in math italics "
                            "(interpreted by TeX as a product of individual scalar variables)."
                        ),
                        "remedy": f"Scope textual subscripts in upright roman font: '_{{\\mathrm{{{word}}}}}' or '_{{\\text{{{word}}}}}'.",
                    }
                    if src_file:
                        flag["file"] = src_file
                    flags.append(flag)

    metrics = {
        "display_math_environments": display_count,
        "in_math_commentary_count": in_math_commentary_count,
        "rho_math_text": round(rho_math_text, 3),
        "inline_kth_count": kth_count,
        "trapped_punctuation_count": trapped_punct_count,
        "unscoped_subscript_count": unscoped_subscript_count,
        "unspaced_integral_differentials": unspaced_differentials_count,
        "manual_micro_spacing_count": micro_spacing_count,
    }
    return metrics, flags


# ---------------------------------------------------------------------------
# 6. Stylometric & Linguistic Indicators Embedded in TeX
# ---------------------------------------------------------------------------


def _extract_clean_prose_paragraphs(clean_tex: str) -> list[str]:
    """Extract running body prose paragraphs stripped of preamble, display math, tables, and lists."""
    doc_parts = re.split(r"\\begin\{document\}", clean_tex, maxsplit=1)
    body = doc_parts[1] if len(doc_parts) > 1 else clean_tex
    body = re.split(r"\\end\{document\}|\\begin\{thebibliography\}", body, maxsplit=1)[0]

    # Strip display math, tables, figures, algorithms, and itemize/enumerate blocks
    body = RE_DISPLAY_MATH.sub("\n\n", body)
    body = re.sub(
        r"\\begin\{(?:table\*?|figure\*?|tabular\*?|tabularx|algorithm\*?|algorithmic|lstlisting|verbatim)\}.*?\\end\{(?:table\*?|figure\*?|tabular\*?|tabularx|algorithm\*?|algorithmic|lstlisting|verbatim)\}",
        "\n\n",
        body,
        flags=re.DOTALL,
    )
    body = RE_LIST_ENV.sub("\n\n", body)

    # Remove section headers and standalone declaration lines
    body = re.sub(
        r"\\(?:section|subsection|subsubsection|paragraph|title|author|date|maketitle|label|bibliography|bibliographystyle)\*?\{[^}]*\}",
        "\n\n",
        body,
    )
    body = re.sub(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{[^}]*\}", "", body)
    body = re.sub(r"\$(?:[^$]|\\\$)+\$", "MATHTOKEN", body)
    body = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", body)
    body = re.sub(r"\\[a-zA-Z]+\*?", " ", body)
    body = re.sub(r"[{}~]", " ", body)

    raw_paras = re.split(r"\n\s*\n", body)
    paragraphs: list[str] = []
    for p in raw_paras:
        p_clean = re.sub(r"\s+", " ", p).strip()
        words = re.findall(r"[A-Za-z0-9']+", p_clean)
        if len(words) >= 12:
            paragraphs.append(p_clean)
    return paragraphs


def evaluate_stylometric_profile(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Evaluate natural language prose embedded in TeX or Markdown for:
    - Kobak et al. excess AI style words and phrases
    - Structural boundary clustering (abstract opening, intro opening, pre-equation transitions)
    - Em-dash usage (— or --- in prose)
    - Sentence-length Burstiness B_length = sigma(L_s) / mu(L_s)
    - Paragraph token standard deviation sigma_para
    - Redundant subsection summary paragraphs
    """
    clean = strip_tex_comments(tex_source)
    flags: list[dict[str, Any]] = []

    excess_word_hits: list[dict[str, Any]] = []
    em_dash_count = 0
    pre_eq_scaffolding_count = 0

    lines = clean.splitlines()
    for line_idx, line in enumerate(lines, start=1):
        src_file, src_line = _map_line(line_idx, line_map, default_file)
        # Mask inline math on the line before scanning vocabulary
        prose_line = re.sub(r"(?<!\\)\$.*?(?<!\\)\$", " ", line)

        # 6.1 Excess style phrases
        for phrase_re, label, remedy in EXCESS_STYLE_PHRASES:
            for m_p in phrase_re.finditer(prose_line):
                hit = {"term": label, "line": src_line, "file": src_file}
                excess_word_hits.append(hit)
                flag: dict[str, Any] = {
                    "dimension": "stylometry",
                    "severity": "WARNING",
                    "line": src_line,
                    "matched_text": m_p.group(0),
                    "explanation": f"Synthetic AI framing phrase '{m_p.group(0)}' detected.",
                    "remedy": remedy,
                }
                if src_file:
                    flag["file"] = src_file
                flags.append(flag)

        # 6.2 Excess style words (Kobak et al. markers)
        for word, remedy in EXCESS_STYLE_WORDS.items():
            for m_w in re.finditer(r"\b" + re.escape(word) + r"\b", prose_line, re.IGNORECASE):
                hit = {"term": word, "line": src_line, "file": src_file}
                excess_word_hits.append(hit)
                flag = {
                    "dimension": "stylometry",
                    "severity": "WARNING",
                    "line": src_line,
                    "matched_text": m_w.group(0),
                    "explanation": f"High-displacement synthetic style marker '{m_w.group(0)}' (Kobak et al. excess vocabulary).",
                    "remedy": remedy,
                }
                if src_file:
                    flag["file"] = src_file
                flags.append(flag)

        # 6.3 Em-dashes (Unicode — or LaTeX --- in prose)
        for m_em in re.finditer(r"—|(?<!-)---(?!-)", prose_line):
            em_dash_count += 1
            if em_dash_count <= 5:
                flag = {
                    "dimension": "stylometry",
                    "severity": "WARNING",
                    "line": src_line,
                    "matched_text": m_em.group(0),
                    "explanation": "Conversational em-dash punctuation detected in academic prose.",
                    "remedy": "Replace em-dashes with commas, parentheses, colons, or discrete clauses.",
                }
                if src_file:
                    flag["file"] = src_file
                flags.append(flag)

        # 6.4 Formulaic pre-equation scaffolding (Moreover/Furthermore/Crucially ... : followed by display math)
        if RE_PRE_EQ_TRANSITION.search(prose_line.strip()):
            next_nonempty = ""
            for look_ahead in range(line_idx, min(line_idx + 3, len(lines))):
                cand = lines[look_ahead].strip()
                if cand:
                    next_nonempty = cand
                    break
            if re.match(r"\\begin\{(?:equation|align|gather|multline)|\\\[|\$\$", next_nonempty):
                pre_eq_scaffolding_count += 1
                flag = {
                    "dimension": "stylometry",
                    "severity": "INFO",
                    "line": src_line,
                    "matched_text": prose_line.strip()[:90],
                    "explanation": "Formulaic discourse transition immediately preceding display mathematics.",
                    "remedy": "Integrate the equation directly into the domain narrative without 'Moreover/Crucially' scaffolding.",
                }
                if src_file:
                    flag["file"] = src_file
                flags.append(flag)

    # 6.5 Sentence-length Burstiness (B_length) & Paragraph Token Spread (sigma_para)
    paragraphs = _extract_clean_prose_paragraphs(clean)
    para_lengths = [float(len(re.findall(r"[A-Za-z0-9']+", p))) for p in paragraphs]
    para_mu, para_sigma, _ = _mean_std_cv(para_lengths)

    sentences: list[str] = []
    for p in paragraphs:
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", p):
            words = re.findall(r"[A-Za-z0-9']+", s)
            if len(words) >= 4:
                sentences.append(s)

    sent_lengths = [float(len(re.findall(r"[A-Za-z0-9']+", s))) for s in sentences]
    sent_mu, sent_sigma, burstiness_length = _mean_std_cv(sent_lengths)

    is_low_burstiness = len(sentences) >= 6 and burstiness_length < 0.28
    if is_low_burstiness:
        src_file, src_line = _map_line(1, line_map, default_file)
        flag = {
            "dimension": "stylometry",
            "severity": "WARNING",
            "line": src_line,
            "matched_text": f"B_length = {burstiness_length:.2f} (mean={sent_mu:.1f} words, sigma={sent_sigma:.1f})",
            "explanation": (
                f"Suppressed sentence-length burstiness (B_length = {burstiness_length:.2f} < 0.28 across {len(sentences)} sentences). "
                "Prose exhibits a monotonic, uniform sentence rhythm typical of autoregressive decoding."
            ),
            "remedy": (
                "Increase clausal variance (target B_length > 0.55): intersperse concise empirical assertions "
                "(8-12 words) with multi-clause analytical sentences (28-40 words)."
            ),
        }
        if src_file:
            flag["file"] = src_file
        flags.append(flag)

    is_compressed_paragraphs = len(paragraphs) >= 4 and para_sigma < 15.0
    if is_compressed_paragraphs:
        src_file, src_line = _map_line(1, line_map, default_file)
        flag = {
            "dimension": "stylometry",
            "severity": "INFO",
            "line": src_line,
            "matched_text": f"sigma_para = {para_sigma:.1f} words across {len(paragraphs)} paragraphs",
            "explanation": (
                f"Compressed paragraph length standard deviation (sigma = {para_sigma:.1f} < 15.0 words), "
                "indicating symmetrical, modular paragraph generation."
            ),
            "remedy": "Vary paragraph lengths naturally across sections rather than using uniform 3-to-4 sentence blocks.",
        }
        if src_file:
            flag["file"] = src_file
        flags.append(flag)

    # 6.6 Redundant subsection summary paragraphs
    redundant_subsection_summaries = 0
    subsec_matches = list(re.finditer(r"\\subsection\*?\{([^}]*)\}", clean))
    for i, sm in enumerate(subsec_matches):
        start_pos = sm.end()
        end_pos = subsec_matches[i + 1].start() if i + 1 < len(subsec_matches) else len(clean)
        next_sec = re.search(r"\\(?:section\*?\{|end\{document\})", clean[start_pos:end_pos])
        if next_sec:
            end_pos = start_pos + next_sec.start()
        sub_body = clean[start_pos:end_pos].strip()
        sub_units = [p.strip() for p in re.split(r"\n\s*\n|\n", sub_body) if p.strip()]
        if len(sub_units) >= 2:
            last_para = sub_units[-1]
            if re.match(
                r"^(?:In\s+summary|To\s+summarize|Overall|Taken\s+together|Thus,\s+this\s+subsection|Consequently,\s+these\s+features)\s*,",
                last_para,
                re.IGNORECASE,
            ):
                redundant_subsection_summaries += 1
                raw_line = _line_number_at_offset(clean, start_pos + sub_body.rfind(last_para))
                src_file, src_line = _map_line(raw_line, line_map, default_file)
                flag = {
                    "dimension": "stylometry",
                    "severity": "INFO",
                    "line": src_line,
                    "matched_text": last_para[:80] + "...",
                    "explanation": f"Redundant summary wrap-up paragraph at the end of \\subsection{{{sm.group(1)}}}.",
                    "remedy": "Remove premature subsection summary paragraphs; reserve synthesis for the Discussion or Conclusion section.",
                }
                if src_file:
                    flag["file"] = src_file
                flags.append(flag)

    metrics = {
        "excess_style_word_count": len(excess_word_hits),
        "excess_style_words": excess_word_hits,
        "em_dash_count": em_dash_count,
        "pre_equation_scaffolding_count": pre_eq_scaffolding_count,
        "sentence_count": len(sentences),
        "sentence_length_mean": round(sent_mu, 2),
        "sentence_length_std": round(sent_sigma, 2),
        "burstiness_length_cv": round(burstiness_length, 3),
        "is_low_burstiness": is_low_burstiness,
        "paragraph_count": len(paragraphs),
        "paragraph_length_mean": round(para_mu, 2),
        "paragraph_length_std": round(para_sigma, 2),
        "is_compressed_paragraphs": is_compressed_paragraphs,
        "redundant_subsection_summaries": redundant_subsection_summaries,
    }
    return metrics, flags


# ---------------------------------------------------------------------------
# Unified Forensic & Stylometric Audit Entrypoint
# ---------------------------------------------------------------------------


def audit_human_prose(
    tex_or_dir_path: str | Path,
    output_report: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run the 6-dimension SciFi Humanizer & LaTeX Forensic Stylometry Audit on a single
    .tex file, multi-file LaTeX directory (`main.tex` + `sections/*.tex`), Markdown/text
    file, or raw LaTeX/prose string.
    """
    file_label: str | None = None
    files_scanned: list[str] = []
    line_map: list[tuple[str, int]] | None = None
    merged_text: str = ""

    if isinstance(tex_or_dir_path, Path) or (
        isinstance(tex_or_dir_path, str)
        and "\n" not in tex_or_dir_path
        and (Path(tex_or_dir_path).exists() or tex_or_dir_path.strip().endswith((".tex", ".md", ".txt")))
    ):
        p = Path(tex_or_dir_path)
        if not p.exists():
            return {
                "status": "ERROR",
                "error_message": f"File or directory not found: {tex_or_dir_path}",
            }
        if p.is_dir() or p.suffix.lower() == ".tex":
            try:
                proj = resolve_latex_project(p)
                file_label = str(proj.entrypoint)
                files_scanned = [f.relative_path for f in proj.files]
                merged_text = proj.merged_text
                line_map = proj.line_map
            except Exception as e:
                return {
                    "status": "ERROR",
                    "error_message": str(e),
                }
        else:
            file_label = str(p.resolve())
            files_scanned = [p.name]
            merged_text = p.read_text(encoding="utf-8", errors="replace")
    elif isinstance(tex_or_dir_path, str):
        merged_text = tex_or_dir_path
    else:
        return {
            "status": "ERROR",
            "error_message": f"Unsupported input type: {type(tex_or_dir_path).__name__}",
        }

    default_file = files_scanned[0] if len(files_scanned) == 1 else None

    list_metrics, list_flags = evaluate_list_fingerprints(merged_text, line_map, default_file)
    preamble_metrics, preamble_flags = evaluate_preamble_fingerprint(merged_text, line_map, default_file)
    tabular_metrics, tabular_flags = evaluate_tabular_fingerprint(merged_text, line_map, default_file)
    macro_metrics, macro_flags = evaluate_macro_abstraction(merged_text, line_map, default_file)
    math_metrics, math_flags = evaluate_math_syntax_quirks(merged_text, line_map, default_file)
    stylo_metrics, stylo_flags = evaluate_stylometric_profile(merged_text, line_map, default_file)

    all_flags = list_flags + preamble_flags + tabular_flags + macro_flags + math_flags + stylo_flags

    # Compute 100-point Human Authenticity Score
    score = 100
    deductions: list[str] = []

    if list_metrics["anomalous_lists_count"] > 0:
        pen = min(20, list_metrics["anomalous_lists_count"] * 10)
        score -= pen
        deductions.append(
            f"-{pen} pts: {list_metrics['anomalous_lists_count']} list environment(s) match synthetic '\\item \\textbf{{...}}:' low-CV fingerprint"
        )

    if preamble_metrics["unused_packages"] or preamble_metrics["stereotypical_hyperref"]:
        pen = min(
            10, len(preamble_metrics["unused_packages"]) * 4 + (5 if preamble_metrics["stereotypical_hyperref"] else 0)
        )
        score -= pen
        deductions.append(f"-{pen} pts: Preamble exhibits uncurated packages or stereotypical hyperref configuration")

    if tabular_metrics["rigid_tables_count"] > 0:
        pen = min(10, tabular_metrics["rigid_tables_count"] * 5)
        score -= pen
        deductions.append(
            f"-{pen} pts: {tabular_metrics['rigid_tables_count']} table(s) use unweighted single-character column specifiers without layout tuning"
        )

    if macro_metrics["canonical_expansion_count"] >= 8 and macro_metrics["custom_macro_count"] == 0:
        score -= 12
        deductions.append(
            f"-12 pts: Zero author-defined macros across {macro_metrics['canonical_expansion_count']} canonical math expansions (mu_macro = 0)"
        )

    math_issues = (
        math_metrics["in_math_commentary_count"] * 6
        + math_metrics["trapped_punctuation_count"] * 4
        + math_metrics["unscoped_subscript_count"] * 4
        + math_metrics["inline_kth_count"] * 2
    )
    if math_issues > 0:
        pen = min(20, math_issues)
        score -= pen
        deductions.append(
            f"-{pen} pts: Mathematical syntax artifacts (in-equation commentary={math_metrics['in_math_commentary_count']}, "
            f"un-scoped subscripts={math_metrics['unscoped_subscript_count']}, trapped punctuation={math_metrics['trapped_punctuation_count']})"
        )

    stylo_pen = min(25, stylo_metrics["excess_style_word_count"] * 5 + stylo_metrics["em_dash_count"] * 4)
    if stylo_metrics["is_low_burstiness"]:
        stylo_pen = min(30, stylo_pen + 10)
    if stylo_pen > 0:
        score -= stylo_pen
        deductions.append(
            f"-{stylo_pen} pts: Stylometric AI markers ({stylo_metrics['excess_style_word_count']} excess style terms, "
            f"{stylo_metrics['em_dash_count']} em-dashes, B_length={stylo_metrics['burstiness_length_cv']:.2f})"
        )

    score = max(0, score)
    if score >= 80:
        classification = "AUTHENTIC_HUMAN_BASELINE"
    elif score >= 55:
        classification = "MIXED_OR_ASSISTED_PROSE"
    else:
        classification = "STRONG_SYNTHETIC_SIGNATURE"

    confounder_notes = [
        "ESL Phrasebank Guardrail: Low sentence-length burstiness (B_length < 0.28) can occur when non-native English authors use standardized academic phrasebanks; corroborate with source-level markup metrics (mu_macro, R_IB, rho_math_text).",
        "Publisher Template Guardrail: Standard package stacks and hyperref settings may originate from official conference templates (IEEE, ACM, Springer) rather than generative boilerplate.",
        "Formal Proof Guardrail: Pure mathematics and theoretical computer science sections naturally exhibit repetitive symbolic phrasing; evaluate prose cadence primarily on Introduction, Related Work, and Discussion sections.",
    ]

    result: dict[str, Any] = {
        "status": "SUCCESS",
        "human_score": score,
        "classification": classification,
        "total_flags": len(all_flags),
        "deductions": deductions,
        "dimensions": {
            "list_environments": list_metrics,
            "preamble": preamble_metrics,
            "tabular": tabular_metrics,
            "macros": macro_metrics,
            "math_syntax": math_metrics,
            "stylometry": stylo_metrics,
        },
        "flags": all_flags,
        "confounder_notes": confounder_notes,
    }
    if file_label:
        result["file"] = file_label
    if files_scanned:
        result["files_scanned"] = files_scanned

    report_md = format_human_report_markdown(result)
    result["report_markdown"] = report_md

    if output_report:
        out_p = Path(output_report)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(report_md, encoding="utf-8")
        result["output_report"] = str(out_p.resolve())

    return result


def format_human_report_markdown(data: dict[str, Any]) -> str:
    """Format the 6-dimension Humanizer & LaTeX Forensic Stylometry Audit into Markdown."""
    score = data["human_score"]
    cls = data["classification"]
    dims = data["dimensions"]
    lst = dims["list_environments"]
    pre = dims["preamble"]
    tab = dims["tabular"]
    mac = dims["macros"]
    mth = dims["math_syntax"]
    sty = dims["stylometry"]

    badge = "✅" if score >= 80 else ("⚠️" if score >= 55 else "❌")
    lines = [
        "# 🧬 SciFi Humanizer & LaTeX Stylometric Forensic Report",
        "",
        f"**Human Authenticity Score:** {badge} **{score} / 100** (`{cls}`)",
        f"**Total Forensic & Stylometric Flags:** {data['total_flags']}",
    ]
    if data.get("file"):
        lines.append(f"**Target:** `{data['file']}`")
    if data.get("files_scanned"):
        lines.append(
            f"**Files Scanned ({len(data['files_scanned'])}):** {', '.join(f'`{f}`' for f in data['files_scanned'])}"
        )
    lines.append("")

    if data.get("deductions"):
        lines.append("## 🔍 Score Deductions Summary")
        for d in data["deductions"]:
            lines.append(f"- {d}")
        lines.append("")

    lines.extend(
        [
            "## 📊 6-Dimension Source-Code & Stylometric Profile",
            "",
            "| Forensic Dimension | Measured Metrics | Diagnostic Status |",
            "| :--- | :--- | :--- |",
            f"| **1. List Environments** | Total: {lst['total_lists']}, Anomalous (`R_IB >= 0.80`, low `CV`): {lst['anomalous_lists_count']} | {'⚠️ Synthetic Template' if lst['anomalous_lists_count'] else '✅ Human Baseline'} |",
            f"| **2. Document Preamble** | Kitchen-sink overlap: {len(pre['kitchen_sink_overlap'])}/8, Unused: {', '.join(pre['unused_packages']) or 'None'}, Stereotypical `hyperref`: {pre['stereotypical_hyperref']} | {'⚠️ Boilerplate Stack' if (pre['unused_packages'] or pre['stereotypical_hyperref']) else '✅ Curated'} |",
            f"| **3. Tabular Markup** | Total tables: {tab['total_tables']}, Unweighted rigid specs: {tab['rigid_tables_count']} | {'⚠️ Rigid Columns' if tab['rigid_tables_count'] else '✅ Tuned Layout'} |",
            f"| **4. Macro Abstraction** | Custom macros: {mac['custom_macro_count']}, Canonical calls: {mac['canonical_expansion_count']} ($\\mu_{{\\mathrm{{macro}}}} = {mac['macro_abstraction_ratio']:.2f}$) | {'⚠️ Raw Expansions' if (mac['canonical_expansion_count'] >= 8 and mac['custom_macro_count'] == 0) else '✅ Modular'} |",
            f"| **5. Mathematical Syntax** | Display eqs: {mth['display_math_environments']}, In-math text ($\\rho = {mth['rho_math_text']:.2f}$), Un-scoped subscripts: {mth['unscoped_subscript_count']}, Trapped punct: {mth['trapped_punctuation_count']} | {'⚠️ Math Artifacts' if (mth['in_math_commentary_count'] or mth['unscoped_subscript_count'] or mth['trapped_punctuation_count']) else '✅ Clean Typesetting'} |",
            f"| **6. Prose Stylometry** | Excess AI words: {sty['excess_style_word_count']}, Em-dashes: {sty['em_dash_count']}, Sentence Burstiness $B_{{\\mathrm{{length}}}} = {sty['burstiness_length_cv']:.2f}$ ($\\mu={sty['sentence_length_mean']:.1f}$w) | {'⚠️ Synthetic Cadence' if (sty['excess_style_word_count'] or sty['em_dash_count'] or sty['is_low_burstiness']) else '✅ Natural Cadence'} |",
            "",
        ]
    )

    flags = data.get("flags", [])
    if flags:
        lines.append("## 🛠️ Actionable Humanization & Remediation Plan")
        for f in flags[:25]:
            loc = f"{f.get('file', '')}:{f.get('line', '')}".strip(":")
            lines.append(
                f"- **[{f['severity']}]** `{loc}` ({f['dimension']}) — `{f['matched_text']}`\n"
                f"  - *Issue:* {f['explanation']}\n"
                f"  - *Fix:* {f['remedy']}"
            )
        lines.append("")

    lines.append("## ⚖️ Sociolinguistic Confounders & Editorial Triage Notes")
    for note in data.get("confounder_notes", []):
        lines.append(f"- {note}")
    lines.append("")

    return "\n".join(lines)
