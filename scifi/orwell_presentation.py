"""
scifi.orwell_presentation — 7th Orwell Forensic Dimension: Presentation & Reviewer Red-Flag Audit.

Detects IEEE/peer-reviewer presentation red flags in LaTeX manuscripts without
penalizing legitimate mathematical rigor:
1. Compound/over-engineered method and baseline naming (plus \\texttt method styling)
2. Abstract overload (word count, inline math, big-O, numeric density, explicit bold vs IEEEtran default)
3. Inline math density in prose paragraphs & multi-definition sentences
4. Heading & contribution-title complexity
5. Absolutist/promotional adjective density & placement in titles/abstract
6. Formulaic transition/opener repetition
7. Times text / Computer Modern math font mismatch
8. Exact repeated sentences (copy/paste regeneration artifacts)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from scifi.latex.project import strip_tex_comments

# ---------------------------------------------------------------------------
# Module-level thresholds & constants
# ---------------------------------------------------------------------------

COMPOUND_NAME_DISTINCT_THRESHOLD = 4
COMPOUND_NAME_SEGMENTS_THRESHOLD = 3
COMPOUND_NAME_SHARED_ROOT_THRESHOLD = 2

ABSTRACT_WORD_LOW = 220
ABSTRACT_WORD_MEDIUM = 250
ABSTRACT_INLINE_MATH_THRESHOLD = 6
ABSTRACT_BIG_O_THRESHOLD = 2
ABSTRACT_NUMERIC_THRESHOLD = 8

INLINE_MATH_PARA_COUNT_THRESHOLD = 12
INLINE_MATH_PARA_RATIO_THRESHOLD = 0.12
INLINE_MATH_SENT_DEF_THRESHOLD = 4

SECTION_TITLE_MAX_WORDS = 8
THEOREM_TITLE_MAX_WORDS = 7

ABSOLUTIST_DENSITY_PER_1K_THRESHOLD = 6.0

TRANSITION_SINGLE_THRESHOLD = 3
TRANSITION_TO_VERB_THRESHOLD = 4
TRANSITION_RATIO_THRESHOLD = 0.04
TRANSITION_MIN_SENTENCES = 25

REPEATED_SENTENCE_MIN_WORDS = 8

_LEGITIMATE_COMPOUND_EXACT = {
    "BCD-SCA",
    "Karush-Kuhn-Tucker",
    "Gauss-Markov",
    "Nelder-Mead",
    "Foster-Lyapunov",
    "Student-t",
    "Multi-UAV",
    "Multi-Agent",
    "Line-of-Sight",
    "Mixed-Integer",
    "Drift-Plus-Penalty",
    "Real-Time",
    "Closed-Form",
    "Time-Average",
    "Continuous-Time",
    "Discrete-Time",
    "Non-Convex",
    "Two-Tier",
    "One-Slot",
    "Multi-Slot",
    "End-to-End",
    "On-Policy",
    "Off-Policy",
    "Warm-Start",
    "Double-Blind",
    "Open-Source",
    "State-of-the-Art",
    "Translational-Lift",
    "Zero-Offloading",
    "Backlog-Clipped",
    "Queue-Aware",
    "Queue-Unaware",
    "Static-Hover",
    "Fixed-Fraction",
    "Finite-Difference",
    "Finite-Precision",
    "Short-Horizon",
    "Long-Term",
    "Cross-Seed",
    "Post-Movement",
    "Start-of-Slot",
    "Half-Space",
    "Small-Scale",
    "Large-Scale",
    "High-Density",
    "Low-Complexity",
    "Near-Optimal",
    "Worst-Case",
    "Best-Case",
    "All-to-All",
    "Positive-Definite",
    "Semi-Definite",
    "UAV-MEC",
    "IoT-Enabled",
    "IEEE-Style",
    "Lyapunov-Guided",
    "Bi-Level",
    "Penalty-Based",
    "Oracle-Referenced",
    "Segment-Verified",
    "Warm-Started",
    "Assumption-Free",
    "Zero-Duality-Gap",
    "Marginal-Cost",
    "Water-Filling",
    "Dual-Audience",
    "Single-Tier",
    "Multi-Start",
    "Closed-Loop",
    "Open-Loop",
    "Mini-Batch",
    "Wall-Clock",
    "Per-Slot",
    "Intra-Slot",
    "Inter-UAV",
    "Pre-Clipped",
    "Pre-Assigned",
    "Non-Negative",
    "Non-Zero",
    "First-Order",
    "Second-Order",
    "Sub-Problem",
    "Sub-Routine",
}

_GENERIC_PREFIXES = (
    "Multi-",
    "Two-",
    "One-",
    "Three-",
    "Non-",
    "Pre-",
    "Post-",
    "Sub-",
    "Per-",
    "Semi-",
    "Self-",
    "Zero-",
    "Cross-",
    "Short-",
    "Long-",
    "Real-",
    "Closed-",
    "Open-",
    "High-",
    "Low-",
    "Near-",
    "Worst-",
    "Best-",
    "Half-",
    "All-",
    "Fixed-",
    "Static-",
    "Finite-",
    "Small-",
    "Large-",
    "Single-",
    "Double-",
    "First-",
    "Second-",
    "Inter-",
    "Intra-",
    "Warm-",
    "Mini-",
    "Wall-",
    "Full-",
    "Fast-",
    "Slow-",
)

_ABSOLUTIST_RE = re.compile(
    r"\b("
    r"exact|explicit(?:ly)?|unconditional(?:ly)?|analytical(?:ly)?|"
    r"assumption-free|strictly|zero-duality-gap|rigorous(?:ly)?|"
    r"provabl[ye]|guarantee[sd]?|certif(?:y|ied|ies)|"
    r"deterministic|closed-form"
    r")\b",
    re.IGNORECASE,
)

_SINGLE_OPENERS = (
    "Furthermore",
    "Moreover",
    "Consequently",
    "Additionally",
    "Conversely",
    "Notably",
    "Crucially",
    "Rather than",
)

_TO_VERB_RE = re.compile(
    r"^To\s+([a-z]{3,18})\b[^.?!]{0,80},",
)

_RE_DISPLAY_MATH = re.compile(
    r"\\begin\{(?:equation|align|gather|multline|flalign|alignat)\*?\}[\s\S]*?"
    r"\\end\{(?:equation|align|gather|multline|flalign|alignat)\*?\}"
    r"|\\\[[\s\S]*?\\\]"
    r"|\$\$[\s\S]*?\$\$",
)
_RE_INLINE_MATH = re.compile(r"(?<!\\)\$(?!\$)(?:\\.|[^$\\])+(?<!\\)\$")
_RE_MATH_DEF = re.compile(r"\\triangleq|:=|\\coloneqq|(?<![<>!])=(?!=)")


def _line_at(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _resolve_loc(
    line_no: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[str | None, int]:
    if line_map and 1 <= line_no <= len(line_map):
        return line_map[line_no - 1]
    return default_file, line_no


def _make_flag(
    dimension: str,
    severity: str,
    src_file: str | None,
    src_line: int,
    matched_text: str,
    explanation: str,
    remedy: str,
) -> dict[str, Any]:
    flag: dict[str, Any] = {
        "dimension": dimension,
        "severity": severity,
        "line": src_line,
        "matched_text": matched_text,
        "explanation": explanation,
        "remedy": remedy,
    }
    if src_file:
        flag["file"] = src_file
    return flag


def _strip_envs_for_prose(body: str, drop_proofs: bool = True) -> str:
    """Strip display math, tables, figures, algorithms, and optionally proofs."""
    s = _RE_DISPLAY_MATH.sub("\n\n", body)
    envs = (
        r"table\*?|figure\*?|tabular\*?|tabularx|algorithm\*?|algorithmic|"
        r"lstlisting|verbatim|tikzpicture"
    )
    if drop_proofs:
        envs += r"|proof"
    s = re.sub(
        rf"\\begin\{{(?:{envs})\}}[\s\S]*?\\end\{{(?:{envs})\}}",
        "\n\n",
        s,
    )
    return s


def _mask_non_prose_tokens(text: str) -> str:
    """Mask inline math, citations, labels, refs, and URLs so prose scans ignore them."""
    s = re.sub(r"\\cite[a-zA-Z]*\*?(?:\[[^\]]*\])*\{[^}]*\}", " ", text)
    s = re.sub(r"\\(?:label|ref|eqref|autoref|cref|Cref|pageref|url|href|includegraphics)\*?\{[^}]*\}", " ", s)
    s = _RE_INLINE_MATH.sub(" ", s)
    return s


# ---------------------------------------------------------------------------
# 1. Compound Method Names & \texttt Method Styling
# ---------------------------------------------------------------------------


def _check_compound_method_names(
    clean: str,
    body: str,
    body_offset: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    prose_scan = _mask_non_prose_tokens(_strip_envs_for_prose(body, drop_proofs=False))

    # Extract \texttt{...} method-like tokens first
    texttt_methods: Counter[str] = Counter()
    texttt_first_pos: dict[str, int] = {}
    for m in re.finditer(r"\\texttt\{([A-Za-z0-9][A-Za-z0-9_\- ]{1,40})\}", body):
        tok = m.group(1).strip()
        if any(ch.isupper() for ch in tok) and ("-" in tok or len(tok) >= 4):
            texttt_methods[tok] += 1
            texttt_first_pos.setdefault(tok, body_offset + m.start())

    # Scan hyphenated tokens in prose
    compound_counts: Counter[str] = Counter()
    compound_first_pos: dict[str, int] = {}

    _METHOD_HINT_RE = re.compile(
        r"(?:MAPPO|PPO|DRL|DQN|SAC|DDPG|TD3|A2C|A3C|MARL|Oracle|Greedy|Baseline|Heuristic)",
        re.IGNORECASE,
    )
    _ALLOWED_PAIR_TERMS = {"CBF-QCQP", "CBF-SOCP", "ITU-R", "BCD-SCA"}

    for m in re.finditer(r"\b([A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+)\b", prose_scan):
        tok = m.group(1)
        if tok in _LEGITIMATE_COMPOUND_EXACT or tok in _ALLOWED_PAIR_TERMS:
            continue
        segs = tok.split("-")
        # Skip if any segment starts lowercase (normal English hyphenated modifiers like multi-UAV, device-to-UAV, shared-CPU)
        if any(not s or s[0].islower() for s in segs) and tok not in texttt_methods:
            continue
        has_acronym = any(sum(1 for c in s if c.isupper()) >= 2 for s in segs)
        all_title = all(s[0].isupper() for s in segs if s)
        starts_generic = tok.startswith(_GENERIC_PREFIXES) and len(segs) == 2 and not has_acronym
        short_prefix_acronym = len(segs) == 2 and len(segs[0]) <= 2 and segs[1].isupper() and tok not in texttt_methods
        if starts_generic or short_prefix_acronym:
            continue
        if not (tok in texttt_methods or (all_title and (len(segs) >= 3 or _METHOD_HINT_RE.search(tok)))):
            continue
        # Single 2-segment acronym+acronym or known baseline like BCD-SCA already excluded above
        compound_counts[tok] += 1
        if tok not in compound_first_pos:
            # Locate in original body for line accuracy
            pos_in_body = body.find(tok)
            compound_first_pos[tok] = body_offset + (pos_in_body if pos_in_body >= 0 else m.start())

    distinct_names = sorted(compound_counts.keys())
    three_plus_seg = [n for n in distinct_names if len(n.split("-")) >= COMPOUND_NAME_SEGMENTS_THRESHOLD]

    # Check shared roots (prefix or suffix shared by >=2 distinct names)
    root_groups: dict[str, list[str]] = {}
    for name in distinct_names:
        segs = name.split("-")
        for root in {segs[0], segs[-1]}:
            if len(root) >= 3:
                root_groups.setdefault(root, []).append(name)
    shared_roots = {r: v for r, v in root_groups.items() if len(v) >= COMPOUND_NAME_SHARED_ROOT_THRESHOLD}

    if len(distinct_names) >= COMPOUND_NAME_DISTINCT_THRESHOLD or three_plus_seg or shared_roots:
        first_name = three_plus_seg[0] if three_plus_seg else distinct_names[0]
        src_file, src_line = _resolve_loc(_line_at(clean, compound_first_pos[first_name]), line_map, default_file)
        flags.append(
            _make_flag(
                dimension="presentation_naming",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=", ".join(distinct_names[:6]),
                explanation=(
                    f"Over-engineered compound method/baseline naming: {len(distinct_names)} distinct "
                    f"compound identifiers ({len(three_plus_seg)} with >=3 segments, "
                    f"{len(shared_roots)} shared root family/families)."
                ),
                remedy=(
                    "Keep one concise proposed method name (e.g. L-MAPPO) and use plain descriptive "
                    "labels for baselines and ablations (e.g. 'L-MAPPO with equal CPU allocation')."
                ),
            )
        )

    if texttt_methods:
        sample = ", ".join(sorted(texttt_methods.keys())[:4])
        first_tok = next(iter(texttt_first_pos))
        src_file, src_line = _resolve_loc(_line_at(clean, texttt_first_pos[first_tok]), line_map, default_file)
        flags.append(
            _make_flag(
                dimension="presentation_naming",
                severity="LOW",
                src_file=src_file,
                src_line=src_line,
                matched_text=sample,
                explanation="Algorithm/baseline names typeset in \\texttt{...} monospace font in prose.",
                remedy="Typeset method and baseline names in normal roman text rather than \\texttt{...}.",
            )
        )

    return {
        "distinct_compound_names": len(distinct_names),
        "compound_names": distinct_names,
        "three_plus_segment_names": three_plus_seg,
        "shared_root_families": shared_roots,
        "texttt_method_count": len(texttt_methods),
    }, flags


# ---------------------------------------------------------------------------
# 2. Abstract Overload & Boldness
# ---------------------------------------------------------------------------


def _check_abstract(
    clean: str,
    preamble: str,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    m_abs = re.search(r"\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}", clean)
    if not m_abs:
        return {"present": False}, flags

    abs_raw = m_abs.group(1)
    src_file, src_line = _resolve_loc(_line_at(clean, m_abs.start()), line_map, default_file)

    has_explicit_bold = bool(
        re.search(r"\\bfseries\b|\\boldmath\b", abs_raw) or re.search(r"\\textbf\{[^}]{40,}\}", abs_raw)
    )
    if has_explicit_bold:
        flags.append(
            _make_flag(
                dimension="presentation_abstract",
                severity="HIGH",
                src_file=src_file,
                src_line=src_line,
                matched_text="\\textbf / \\bfseries in abstract",
                explanation="Explicit bold formatting found inside the abstract environment.",
                remedy="Remove \\bfseries/\\textbf wrappers inside \\begin{abstract} so body text uses normal weight.",
            )
        )
    else:
        is_ieee_journal = bool(re.search(r"\\documentclass\[[^\]]*\bjournal\b[^\]]*\]\{IEEEtran\}", preamble))
        if is_ieee_journal:
            flags.append(
                _make_flag(
                    dimension="presentation_abstract",
                    severity="INFO",
                    src_file=src_file,
                    src_line=src_line,
                    matched_text="\\documentclass[journal]{IEEEtran}",
                    explanation="IEEEtran [journal] sets abstract text in bold by template design (not a source defect).",
                    remedy="Keep the standard IEEEtran abstract environment; do not override class typography.",
                )
            )

    inline_maths = _RE_INLINE_MATH.findall(abs_raw)
    big_o_hits = re.findall(r"(?:\\mathcal\{O\}|\\mathrm\{O\}|\bO)\s*\(", abs_raw)

    # Numeric results (percentages, decimals, +/- intervals, values with units)
    num_hits = set(re.findall(r"\d+\.\d+(?:%|\\%|\\times)?|\d+(?:\\%|%|\s*\\times)", abs_raw))

    # Word count (inline math counted as 1 token each)
    abs_words_str = _RE_INLINE_MATH.sub(" MATH ", abs_raw)
    abs_words_str = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", abs_words_str)
    abs_words_str = re.sub(r"\\[a-zA-Z]+\*?", " ", abs_words_str)
    word_count = len(re.findall(r"[A-Za-z0-9']+", abs_words_str))

    if word_count > ABSTRACT_WORD_MEDIUM:
        flags.append(
            _make_flag(
                dimension="presentation_abstract",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{word_count} words",
                explanation=f"Abstract is {word_count} words (> {ABSTRACT_WORD_MEDIUM}), crowding too many details.",
                remedy="Trim the abstract to 150-220 words focusing on problem, method, main guarantee, and headline results.",
            )
        )
    elif word_count > ABSTRACT_WORD_LOW:
        flags.append(
            _make_flag(
                dimension="presentation_abstract",
                severity="LOW",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{word_count} words",
                explanation=f"Abstract is {word_count} words (> {ABSTRACT_WORD_LOW} target ceiling).",
                remedy="Tighten secondary qualifiers to stay within 150-220 words.",
            )
        )

    if len(inline_maths) > ABSTRACT_INLINE_MATH_THRESHOLD:
        flags.append(
            _make_flag(
                dimension="presentation_abstract",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{len(inline_maths)} inline math expressions",
                explanation=f"Abstract contains {len(inline_maths)} inline math expressions (> {ABSTRACT_INLINE_MATH_THRESHOLD}).",
                remedy="Describe complexity and regimes concisely in prose; keep only essential symbols in the abstract.",
            )
        )

    if len(big_o_hits) >= ABSTRACT_BIG_O_THRESHOLD:
        flags.append(
            _make_flag(
                dimension="presentation_abstract",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{len(big_o_hits)} big-O expressions",
                explanation=f"Abstract packs {len(big_o_hits)} asymptotic complexity expressions.",
                remedy="Keep per-subroutine big-O bounds in Section IV and retain at most one high-level bound in the abstract.",
            )
        )

    if len(num_hits) > ABSTRACT_NUMERIC_THRESHOLD:
        flags.append(
            _make_flag(
                dimension="presentation_abstract",
                severity="LOW",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{len(num_hits)} distinct numeric results",
                explanation=f"Abstract reports {len(num_hits)} distinct numeric metrics (> {ABSTRACT_NUMERIC_THRESHOLD}).",
                remedy="Report 3-5 headline empirical numbers in the abstract and leave secondary comparisons for Section V.",
            )
        )

    return {
        "present": True,
        "word_count": word_count,
        "inline_math_count": len(inline_maths),
        "big_o_count": len(big_o_hits),
        "numeric_result_count": len(num_hits),
        "explicit_bold": has_explicit_bold,
    }, flags


# ---------------------------------------------------------------------------
# 3. Inline Math Density in Prose
# ---------------------------------------------------------------------------


def _check_inline_math_density(
    clean: str,
    body: str,
    body_offset: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    # Strip display math, tables, figures, proofs, and section headers
    prose = _strip_envs_for_prose(body, drop_proofs=True)
    prose = re.sub(
        r"\\(?:section|subsection|subsubsection|paragraph|caption|label)\*?\{[^}]*\}",
        "\n\n",
        prose,
    )

    dense_paras = 0
    worst_ratio = 0.0
    multi_def_sentences = 0

    for m_para in re.finditer(r"(?:^|\n\s*\n)([\s\S]+?)(?=\n\s*\n|$)", prose):
        p_raw = m_para.group(1).strip()
        if not p_raw or p_raw.startswith("\\begin{"):
            continue
        maths = _RE_INLINE_MATH.findall(p_raw)
        # Count words with inline math replaced by 1 token
        p_words_str = _RE_INLINE_MATH.sub(" MATH ", p_raw)
        p_words_str = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", p_words_str)
        p_words_str = re.sub(r"\\[a-zA-Z]+\*?", " ", p_words_str)
        n_words = len(re.findall(r"[A-Za-z0-9']+", p_words_str))
        if n_words < 20:
            continue

        ratio = len(maths) / n_words
        if ratio > worst_ratio:
            worst_ratio = ratio

        if len(maths) >= INLINE_MATH_PARA_COUNT_THRESHOLD and ratio > INLINE_MATH_PARA_RATIO_THRESHOLD:
            dense_paras += 1
            if dense_paras <= 6:
                pos = body.find(p_raw[:40])
                offset = body_offset + (pos if pos >= 0 else m_para.start())
                src_file, src_line = _resolve_loc(_line_at(clean, offset), line_map, default_file)
                flags.append(
                    _make_flag(
                        dimension="presentation_inline_math",
                        severity="MEDIUM",
                        src_file=src_file,
                        src_line=src_line,
                        matched_text=f"{len(maths)} inline math / {n_words} words ({ratio:.2f})",
                        explanation=(
                            f"Paragraph embeds {len(maths)} inline math segments across {n_words} words "
                            f"(density {ratio:.2f} > {INLINE_MATH_PARA_RATIO_THRESHOLD})."
                        ),
                        remedy="Move substantial definitions into displayed equations and explain physical meaning between formulas.",
                    )
                )

        # Sentence-level multi-definition check
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\\$])", p_raw):
            s_maths = _RE_INLINE_MATH.findall(sent)
            if len(s_maths) >= INLINE_MATH_SENT_DEF_THRESHOLD and any(_RE_MATH_DEF.search(sm) for sm in s_maths):
                multi_def_sentences += 1
                if multi_def_sentences <= 5:
                    pos = body.find(sent[:40])
                    offset = body_offset + (pos if pos >= 0 else m_para.start())
                    src_file, src_line = _resolve_loc(_line_at(clean, offset), line_map, default_file)
                    flags.append(
                        _make_flag(
                            dimension="presentation_inline_math",
                            severity="LOW",
                            src_file=src_file,
                            src_line=src_line,
                            matched_text=re.sub(r"\s+", " ", sent)[:80] + "...",
                            explanation=f"Single sentence introduces {len(s_maths)} inline math expressions with definitions.",
                            remedy="Split multi-symbol definitions into a displayed equation or separate sentences.",
                        )
                    )

    return {
        "dense_paragraphs": dense_paras,
        "worst_math_word_ratio": round(worst_ratio, 3),
        "multi_def_sentences": multi_def_sentences,
    }, flags


# ---------------------------------------------------------------------------
# 4. Heading & Contribution-Title Complexity
# ---------------------------------------------------------------------------


def _extract_braced(text: str, start_brace: int) -> tuple[str, int]:
    """Extract balanced {...} content starting at index of '{'."""
    depth = 0
    for i in range(start_brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start_brace + 1 : i], i + 1
    return text[start_brace + 1 :], len(text)


def _check_headings(
    clean: str,
    body: str,
    body_offset: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    titles: list[tuple[str, str, int]] = []  # (kind, title_text, abs_offset)

    for m in re.finditer(r"\\(?:section|subsection|subsubsection)\*?\{", body):
        t_raw, _ = _extract_braced(body, m.end() - 1)
        titles.append(("section", t_raw, body_offset + m.start()))

    for m in re.finditer(r"\\begin\{(?:theorem|lemma|proposition|corollary)\}\[([^\]]+)\]", body):
        titles.append(("theorem", m.group(1), body_offset + m.start()))

    for m in re.finditer(r"\\item\s+\\(?:emph|textbf)\{", body):
        t_raw, _ = _extract_braced(body, m.end() - 1)
        titles.append(("contribution", t_raw, body_offset + m.start()))

    complex_count = 0
    long_count = 0

    for kind, t_raw, abs_off in titles:
        t_clean = re.sub(r"\\texorpdfstring\{([^}]*)\}\{[^}]*\}", r"\1", t_raw)
        t_clean = re.sub(r"\\[a-zA-Z]+\*?\{([^}]*)\}", r"\1", t_clean)
        words = re.findall(r"[A-Za-z0-9']+", _RE_INLINE_MATH.sub(" MATH ", t_clean))
        n_words = len(words)

        has_ref_list = bool(re.search(r"\\(?:ref|eqref)|(?:Theorem|Lemma|Proposition|Corollary)s?~?\d", t_raw))
        commas = t_clean.count(",")
        has_and = bool(re.search(r"\band\b", t_clean))
        chains_three = commas >= 2 or (commas >= 1 and has_and)

        src_file, src_line = _resolve_loc(_line_at(clean, abs_off), line_map, default_file)
        if has_ref_list or chains_three:
            complex_count += 1
            flags.append(
                _make_flag(
                    dimension="presentation_headings",
                    severity="MEDIUM",
                    src_file=src_file,
                    src_line=src_line,
                    matched_text=t_clean[:90],
                    explanation="Title chains multiple distinct results or embeds theorem/reference lists.",
                    remedy="Use a concise single-idea title and move theorem/lemma references into the body prose.",
                )
            )
        else:
            limit = SECTION_TITLE_MAX_WORDS if kind == "section" else THEOREM_TITLE_MAX_WORDS
            if n_words > limit:
                long_count += 1
                flags.append(
                    _make_flag(
                        dimension="presentation_headings",
                        severity="LOW",
                        src_file=src_file,
                        src_line=src_line,
                        matched_text=t_clean[:90],
                        explanation=f"{kind.capitalize()} title is {n_words} words (> {limit}).",
                        remedy="Shorten heading to a crisp 3-7 word noun phrase.",
                    )
                )

    return {
        "titles_checked": len(titles),
        "chained_or_ref_titles": complex_count,
        "overlong_titles": long_count,
    }, flags


# ---------------------------------------------------------------------------
# 5. Absolutist / Promotional Adjectives
# ---------------------------------------------------------------------------


def _check_absolutist_adjectives(
    clean: str,
    body: str,
    body_offset: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    prose = _mask_non_prose_tokens(_strip_envs_for_prose(body, drop_proofs=False))
    total_words = max(1, len(re.findall(r"[A-Za-z0-9']+", prose)))

    hits = list(_ABSOLUTIST_RE.finditer(prose))
    density_per_1k = (len(hits) * 1000.0) / total_words

    if density_per_1k > ABSOLUTIST_DENSITY_PER_1K_THRESHOLD:
        src_file, src_line = _resolve_loc(_line_at(clean, body_offset), line_map, default_file)
        top_terms = ", ".join(f"{k}({v})" for k, v in Counter(m.group(0).lower() for m in hits).most_common(5))
        flags.append(
            _make_flag(
                dimension="presentation_absolutist",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{len(hits)} hits ({density_per_1k:.1f}/1k words): {top_terms}",
                explanation=(
                    f"High concentration of absolutist/promotional qualifiers ({density_per_1k:.1f} per 1,000 words "
                    f"> {ABSOLUTIST_DENSITY_PER_1K_THRESHOLD})."
                ),
                remedy="Retain only mathematically necessary qualifiers (e.g. 'strictly convex') and drop promotional modifiers.",
            )
        )

    # Check high-visibility zones: headings, abstract, contribution item titles
    visible_zones: list[tuple[str, str, int]] = []
    m_abs = re.search(r"\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}", clean)
    if m_abs:
        visible_zones.append(("abstract", m_abs.group(1), m_abs.start(1)))
    for m in re.finditer(r"\\(?:section|subsection|subsubsection)\*?\{([^}]*)\}", body):
        visible_zones.append(("heading", m.group(1), body_offset + m.start(1)))
    for m in re.finditer(r"\\item\s+\\(?:emph|textbf)\{([^}]*)\}", body):
        visible_zones.append(("contribution title", m.group(1), body_offset + m.start(1)))

    vis_flagged = 0
    for zone_name, z_text, z_off in visible_zones:
        z_masked = _mask_non_prose_tokens(z_text)
        for m_hit in _ABSOLUTIST_RE.finditer(z_masked):
            vis_flagged += 1
            if vis_flagged <= 10:
                src_file, src_line = _resolve_loc(_line_at(clean, z_off + m_hit.start()), line_map, default_file)
                flags.append(
                    _make_flag(
                        dimension="presentation_absolutist",
                        severity="LOW",
                        src_file=src_file,
                        src_line=src_line,
                        matched_text=f"{m_hit.group(0)} (in {zone_name})",
                        explanation=f"Absolutist qualifier '{m_hit.group(0)}' placed in {zone_name}.",
                        remedy=f"Remove unnecessary qualifier '{m_hit.group(0)}' from the {zone_name}.",
                    )
                )

    return {
        "total_hits": len(hits),
        "density_per_1k_words": round(density_per_1k, 2),
        "visible_zone_hits": vis_flagged,
    }, flags


# ---------------------------------------------------------------------------
# 6. Transition Repetition & 8. Repeated Sentences
# ---------------------------------------------------------------------------


def _extract_prose_sentences(
    clean: str,
    body: str,
    body_offset: int,
) -> list[tuple[str, int]]:
    """Return list of (sentence_text, approx_offset_in_clean)."""
    prose = _strip_envs_for_prose(body, drop_proofs=True)
    prose = re.sub(
        r"\\(?:section|subsection|subsubsection|paragraph|caption|label|title|author|thanks|maketitle|"
        r"bibliographystyle|bibliography)\*?\{[^}]*\}",
        "\n\n",
        prose,
    )
    prose = re.sub(
        r"\\begin\{(?:abstract|quote|enumerate|itemize)\}|\\end\{(?:abstract|quote|enumerate|itemize)\}", "\n", prose
    )
    prose = re.sub(r"\\item\b", "\n", prose)

    results: list[tuple[str, int]] = []
    for para in re.split(r"\n\s*\n", prose):
        p_norm = re.sub(r"\s+", " ", para).strip()
        if len(p_norm) < 20:
            continue
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\\])", p_norm):
            s = sent.strip()
            if len(re.findall(r"[A-Za-z0-9']+", s)) >= 4:
                anchor = s[:36]
                pos = body.find(anchor)
                off = body_offset + (pos if pos >= 0 else 0)
                results.append((s, off))
    return results


def _check_transitions_and_repeats(
    clean: str,
    body: str,
    body_offset: int,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    sentences = _extract_prose_sentences(clean, body, body_offset)

    opener_counts: Counter[str] = Counter()
    opener_first_off: dict[str, int] = {}
    to_verb_count = 0
    to_verb_first_off: int | None = None

    norm_seen: dict[str, int] = {}
    repeated_sents: list[tuple[str, int]] = []

    for sent, off in sentences:
        # Transition openers
        matched_single = False
        for op in _SINGLE_OPENERS:
            if re.match(rf"^{re.escape(op)}\b", sent):
                opener_counts[op] += 1
                opener_first_off.setdefault(op, off)
                matched_single = True
                break
        if not matched_single and _TO_VERB_RE.match(sent):
            to_verb_count += 1
            if to_verb_first_off is None:
                to_verb_first_off = off

        # Exact repeated sentences
        norm = re.sub(r"\s+", " ", sent).strip()
        words = re.findall(r"[A-Za-z0-9']+", norm)
        if len(words) >= REPEATED_SENTENCE_MIN_WORDS:
            if norm in norm_seen:
                repeated_sents.append((norm, off))
            else:
                norm_seen[norm] = off

    for op, cnt in opener_counts.items():
        if cnt >= TRANSITION_SINGLE_THRESHOLD:
            src_file, src_line = _resolve_loc(_line_at(clean, opener_first_off[op]), line_map, default_file)
            flags.append(
                _make_flag(
                    dimension="presentation_transitions",
                    severity="LOW",
                    src_file=src_file,
                    src_line=src_line,
                    matched_text=f"'{op}' x{cnt}",
                    explanation=f"Sentence opener '{op}' repeats {cnt} times across prose.",
                    remedy="Vary sentence openings or let the logical connection speak without formulaic transitions.",
                )
            )

    if to_verb_count >= TRANSITION_TO_VERB_THRESHOLD and to_verb_first_off is not None:
        src_file, src_line = _resolve_loc(_line_at(clean, to_verb_first_off), line_map, default_file)
        flags.append(
            _make_flag(
                dimension="presentation_transitions",
                severity="LOW",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"'To <verb>, ...' x{to_verb_count}",
                explanation=f"Purpose-clause opener 'To <verb>, ...' appears {to_verb_count} times.",
                remedy="Start sentences directly with the subject or action rather than repeated 'To <verb>,' scaffolding.",
            )
        )

    total_formulaic = sum(opener_counts.values()) + to_verb_count
    ratio = (total_formulaic / len(sentences)) if sentences else 0.0
    if len(sentences) >= TRANSITION_MIN_SENTENCES and ratio > TRANSITION_RATIO_THRESHOLD:
        src_file, src_line = _resolve_loc(_line_at(clean, body_offset), line_map, default_file)
        flags.append(
            _make_flag(
                dimension="presentation_transitions",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=f"{total_formulaic}/{len(sentences)} sentences ({ratio:.1%})",
                explanation=f"Formulaic openers account for {ratio:.1%} of prose sentences (> {TRANSITION_RATIO_THRESHOLD:.0%}).",
                remedy="Trim repetitive discourse transitions and connect claims directly.",
            )
        )

    for rep_text, off in repeated_sents[:5]:
        src_file, src_line = _resolve_loc(_line_at(clean, off), line_map, default_file)
        flags.append(
            _make_flag(
                dimension="presentation_repetition",
                severity="MEDIUM",
                src_file=src_file,
                src_line=src_line,
                matched_text=rep_text[:90],
                explanation="Exact duplicate sentence detected in manuscript prose.",
                remedy="Remove or consolidate the duplicated sentence.",
            )
        )

    trans_metrics = {
        "sentence_count": len(sentences),
        "formulaic_opener_count": total_formulaic,
        "formulaic_opener_ratio": round(ratio, 3),
        "opener_breakdown": dict(opener_counts),
        "to_verb_opener_count": to_verb_count,
    }
    rep_metrics = {
        "repeated_sentence_count": len(repeated_sents),
    }
    return trans_metrics, rep_metrics, flags


# ---------------------------------------------------------------------------
# 7. Font Pairing (Times Text vs Computer Modern Math)
# ---------------------------------------------------------------------------


def _check_font_pairing(
    clean: str,
    preamble: str,
    line_map: list[tuple[str, int]] | None,
    default_file: str | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    flags: list[dict[str, Any]] = []
    if not preamble:
        return {"times_text": False, "matching_math_font": True, "mismatch": False}, flags

    has_times_text = bool(
        re.search(r"\\documentclass(?:\[[^\]]*\])?\{IEEEtran\}", preamble)
        or re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(?:times|newtxtext|ptm|mathptmx)\b[^}]*\}", preamble)
    )
    has_matching_math = bool(
        re.search(
            r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(?:newtxmath|mathptmx|txfonts|stix|stix2|unicode-math|mtpro2)\b[^}]*\}",
            preamble,
        )
    )
    mismatch = has_times_text and not has_matching_math
    if mismatch:
        m_doc = re.search(r"\\documentclass[^\n]*", preamble)
        line_no = _line_at(clean, m_doc.start()) if m_doc else 1
        src_file, src_line = _resolve_loc(line_no, line_map, default_file)
        flags.append(
            _make_flag(
                dimension="presentation_fonts",
                severity="LOW",
                src_file=src_file,
                src_line=src_line,
                matched_text="Times text + Computer Modern math",
                explanation="Text/math font mismatch: Times-compatible body text paired with default Computer Modern math.",
                remedy=(
                    "Test \\usepackage{newtxtext,newtxmath} after amsmath (dropping amsfonts/amssymb if they conflict) "
                    "and verify equation spacing."
                ),
            )
        )

    return {
        "times_text": has_times_text,
        "matching_math_font": has_matching_math,
        "mismatch": mismatch,
    }, flags


# ---------------------------------------------------------------------------
# Public Entrypoint
# ---------------------------------------------------------------------------


def evaluate_presentation_fingerprint(
    tex_source: str,
    line_map: list[tuple[str, int]] | None = None,
    default_file: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Evaluate 7th Orwell dimension: IEEE-reviewer presentation red flags across
    naming, abstract overload/boldness, inline math density, heading complexity,
    absolutist adjectives, transition repetition, font pairing, and repeated sentences.
    """
    clean = strip_tex_comments(tex_source)
    m_doc = re.search(r"\\begin\{document\}", clean)
    if m_doc:
        preamble = clean[: m_doc.start()]
        body = clean[m_doc.end() :]
        body_offset = m_doc.end()
    else:
        preamble = ""
        body = clean
        body_offset = 0

    naming_m, naming_f = _check_compound_method_names(clean, body, body_offset, line_map, default_file)
    abstract_m, abstract_f = _check_abstract(clean, preamble, line_map, default_file)
    math_m, math_f = _check_inline_math_density(clean, body, body_offset, line_map, default_file)
    heading_m, heading_f = _check_headings(clean, body, body_offset, line_map, default_file)
    abs_adj_m, abs_adj_f = _check_absolutist_adjectives(clean, body, body_offset, line_map, default_file)
    trans_m, rep_m, trans_rep_f = _check_transitions_and_repeats(clean, body, body_offset, line_map, default_file)
    font_m, font_f = _check_font_pairing(clean, preamble, line_map, default_file)

    all_flags = naming_f + abstract_f + math_f + heading_f + abs_adj_f + trans_rep_f + font_f
    non_info_flags = sum(1 for f in all_flags if f["severity"] != "INFO")

    metrics: dict[str, Any] = {
        "flag_count": non_info_flags,
        "naming": naming_m,
        "abstract": abstract_m,
        "inline_math": math_m,
        "headings": heading_m,
        "absolutist": abs_adj_m,
        "transitions": trans_m,
        "repetition": rep_m,
        "fonts": font_m,
    }
    return metrics, all_flags
