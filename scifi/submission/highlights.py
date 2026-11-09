"""Research Highlights Generator and Length Validator."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Sequence

from scifi.submission.models import HighlightItem, HighlightsResult
from scifi.submission.profiles import get_publisher_profile

RE_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+\.|\\item)\s*", re.IGNORECASE)
RE_WORDY_PREFIX = re.compile(
    r"^\s*(?:in this (?:paper|work|study),?\s*(?:we\s+)?|we\s+(?:propose|demonstrate|show|present|develop|introduce|derive)\s+(?:that\s+)?|this paper\s+(?:proposes|demonstrates|presents)\s+(?:that\s+)?)",
    re.IGNORECASE,
)


def _clean_bullet(raw: str) -> str:
    """Strip leading markdown/latex bullet prefixes and normalize spaces."""
    cleaned = RE_BULLET_PREFIX.sub("", raw).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned


def extract_candidate_highlights_from_text(text: str) -> list[str]:
    """Extract candidate highlight sentences from manuscript abstract or text."""
    # Strip LaTeX comments
    clean_lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines()]
    clean_text = "\n".join(clean_lines)

    # Look for itemize blocks following contribution keywords
    m_contrib = re.search(
        r"(?:contributions?|our\s+key\s+findings?|in\s+summary)[^:]*:\s*\\begin\{itemize\}(.*?)\\end\{itemize\}",
        clean_text,
        re.DOTALL | re.IGNORECASE,
    )
    if m_contrib:
        raw_items = re.findall(r"\\item\s+([^\n\\]+)", m_contrib.group(1))
        candidates = [_clean_bullet(it) for it in raw_items if len(_clean_bullet(it)) > 15]
        if candidates:
            return candidates[:5]

    # Fallback to abstract sentences
    m_abs = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", clean_text, re.DOTALL | re.IGNORECASE)
    abs_text = m_abs.group(1) if m_abs else clean_text[:2000]
    sentences = re.split(r"(?<=[.!?])\s+", abs_text.strip())
    candidates = [_clean_bullet(s) for s in sentences if 20 <= len(_clean_bullet(s)) <= 120]
    return candidates[:4] if candidates else ["Novel methodology for robust scientific modeling."]


def generate_highlights(
    bullets: Sequence[str] | str | None = None,
    venue: str = "general",
    manuscript_path: str | Path | None = None,
    output_path: str | Path | None = None,
) -> HighlightsResult:
    """
    Generate and audit 3–5 research highlights against venue length constraints.

    Args:
        bullets: Explicit list or string of bullet points.
        venue: Target publisher or venue (e.g. elsevier, ieee, springer, general).
        manuscript_path: Optional path to manuscript (.tex or .md) to extract from.
        output_path: Optional file to save the formatted highlights.
    """
    profile = get_publisher_profile(venue)
    max_chars = profile.max_highlight_chars

    raw_list: list[str] = []
    if bullets is not None:
        if isinstance(bullets, str):
            lines = [b.strip() for b in bullets.splitlines() if b.strip()]
            if len(lines) == 1 and ";" in lines[0]:
                raw_list = [b.strip() for b in lines[0].split(";") if b.strip()]
            else:
                raw_list = lines
        else:
            raw_list = [str(b).strip() for b in bullets if str(b).strip()]

    if not raw_list and manuscript_path:
        p = Path(manuscript_path)
        if p.exists():
            text = p.read_text(encoding="utf-8", errors="replace")
            raw_list = extract_candidate_highlights_from_text(text)

    if not raw_list:
        raw_list = [
            "Proposes novel robust algorithmic formulation.",
            "Improves empirical accuracy over state-of-the-art baselines.",
            "Validates theoretical convergence under mild assumptions.",
        ]

    items: list[HighlightItem] = []
    all_valid = True

    for raw in raw_list:
        cleaned = _clean_bullet(raw)
        c_len = len(cleaned)
        is_val = c_len <= max_chars
        issue = None
        if not is_val:
            all_valid = False
            excess = c_len - max_chars
            issue = f"Exceeds {venue.capitalize()} limit by {excess} chars ({c_len}/{max_chars})."
            # Check for wordy prefix that could be trimmed
            if RE_WORDY_PREFIX.search(cleaned):
                suggested = RE_WORDY_PREFIX.sub("", cleaned).capitalize()
                issue += f" Suggestion: Remove filler prefix to '{suggested[:max_chars]}...'"

        items.append(
            HighlightItem(
                text=cleaned,
                char_count=c_len,
                max_allowed=max_chars,
                is_valid=is_val,
                issue=issue,
            )
        )

    # Check highlight count constraints (e.g. Elsevier requires 3-5 highlights)
    if len(items) < profile.min_highlights:
        all_valid = False
        count_msg = f"{profile.name} requires at least {profile.min_highlights} highlights (found {len(items)}, fewer than {profile.min_highlights})."
        if items:
            items[0].issue = f"{items[0].issue}; {count_msg}" if items[0].issue else count_msg
        else:
            items.append(HighlightItem(text="", char_count=0, max_allowed=max_chars, is_valid=False, issue=count_msg))
    elif len(items) > profile.max_highlights:
        all_valid = False
        count_msg = f"{profile.name} permits at most {profile.max_highlights} highlights (found {len(items)})."
        for it in items[profile.max_highlights:]:
            it.is_valid = False
            it.issue = f"{it.issue}; {count_msg}" if it.issue else count_msg

    # Format Markdown
    md_lines = ["# Research Highlights\n"]
    for it in items:
        valid_mark = "" if it.is_valid else f" <!-- [WARNING: {it.char_count}/{max_chars} chars] -->"
        md_lines.append(f"- {it.text}{valid_mark}")
    md_text = "\n".join(md_lines)

    # Format LaTeX itemize
    tex_lines = ["\\begin{itemize}"]
    for it in items:
        tex_lines.append(f"  \\item {it.text}")
    tex_lines.append("\\end{itemize}")
    tex_text = "\n".join(tex_lines)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".tex":
            out.write_text(tex_text, encoding="utf-8")
        else:
            out.write_text(md_text, encoding="utf-8")

    return HighlightsResult(
        status="SUCCESS",
        venue=profile.venue_id,
        max_chars=max_chars,
        all_valid=all_valid,
        highlights=items,
        markdown_text=md_text,
        latex_text=tex_text,
    )
