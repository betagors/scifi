"""
Structured Open-Access Full-Text and Peer-Review Ingestion.

Supplements raw PDF extraction with structured sources that preserve section
boundaries, equations, and peer-reviewer critiques without fragile HTML scraping:
1. arXiv HTML / ar5iv HTML and arXiv LaTeX e-print source tarballs.
2. OpenReview API v2 peer-review weaknesses, limitations, and meta-reviews.
"""

from __future__ import annotations

import io
import re
import tarfile
import urllib.parse
from html.parser import HTMLParser
from typing import Any

import requests

from scifi.literature.resolver import clean_arxiv_id
from scifi.network import get_session

_ORIG_REQUESTS_GET = requests.get
DEFAULT_USER_AGENT = "scifi-literature/1.0 (academic-researcher)"


def _http_get(url: str, **kwargs: Any) -> requests.Response:
    """Execute GET request via requests.get if patched in tests, else ResilientSession."""
    if requests.get is not _ORIG_REQUESTS_GET:
        return requests.get(url, **kwargs)
    return get_session().get(url, **kwargs)


class _ArxivHTMLSectionParser(HTMLParser):
    """Lightweight stdlib HTML parser for arXiv HTML / ar5iv articles."""

    _SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "noscript"}
    _HEADING_TAGS = {"h1", "h2", "h3", "h4"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._in_heading = False
        self._in_abstract = False
        self._current_heading: list[str] = []
        self._current_section_title = "Preamble"
        self._sections: dict[str, list[str]] = {}
        self._abstract_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l in self._SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth > 0:
            return

        attr_map = {k.lower(): (v or "") for k, v in attrs}
        cls = attr_map.get("class", "").lower()
        if "ltx_abstract" in cls or attr_map.get("id", "").lower() == "abstract":
            self._in_abstract = True

        if tag_l in self._HEADING_TAGS:
            self._in_heading = True
            self._current_heading = []

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if self._skip_depth > 0:
            return

        if tag_l in self._HEADING_TAGS and self._in_heading:
            self._in_heading = False
            title = re.sub(r"\s+", " ", "".join(self._current_heading)).strip()
            if title:
                self._current_section_title = title
                if title.lower().startswith("abstract"):
                    self._in_abstract = True
                elif self._in_abstract:
                    self._in_abstract = False
                self._sections.setdefault(title, [])
        elif tag_l in {"p", "div", "section", "li", "tr"}:
            if self._in_abstract:
                self._abstract_parts.append("\n")
            else:
                self._sections.setdefault(self._current_section_title, []).append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or not data:
            return
        if self._in_heading:
            self._current_heading.append(data)
        elif self._in_abstract:
            self._abstract_parts.append(data)
        else:
            self._sections.setdefault(self._current_section_title, []).append(data)

    def get_parsed(self) -> tuple[str, dict[str, str]]:
        abstract = re.sub(r"\s+", " ", "".join(self._abstract_parts)).strip()
        abstract = re.sub(r"^Abstract[:\.\s]*", "", abstract, flags=re.IGNORECASE).strip()
        sections: dict[str, str] = {}
        for title, chunks in self._sections.items():
            text = re.sub(r"[ \t]+", " ", "".join(chunks))
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            if text:
                sections[title] = text
        return abstract, sections


def _map_sections_to_canonical(
    abstract: str,
    sections: dict[str, str],
    max_section_length: int = 15000,
) -> dict[str, Any]:
    """Map arbitrary section titles into SciFi's canonical section buckets."""
    method_parts: list[str] = []
    limitation_parts: list[str] = []
    all_parts: list[str] = []

    method_re = re.compile(
        r"(?:system\s+model|problem\s+formulation|formulation|method|methodology|"
        r"proposed|approach|framework|architecture|algorithm|model|theory|preliminaries)",
        re.IGNORECASE,
    )
    limitation_re = re.compile(
        r"(?:limitation|threats?\s+to\s+validity|discussion|conclusion|concluding|"
        r"future\s+work|broader\s+impact|ethical|societal|open\s+problem)",
        re.IGNORECASE,
    )

    for title, body in sections.items():
        all_parts.append(f"{title}\n{body}")
        if title.lower().startswith("abstract") and not abstract:
            abstract = body
            continue
        if limitation_re.search(title):
            limitation_parts.append(f"{title}\n{body}")
        elif method_re.search(title):
            method_parts.append(f"{title}\n{body}")

    system_model_or_method = "\n\n".join(method_parts).strip()
    limitations_and_conclusion = "\n\n".join(limitation_parts).strip()
    full_text = "\n\n".join(all_parts).strip()

    if max_section_length > 0:
        abstract = abstract[:max_section_length]
        system_model_or_method = system_model_or_method[:max_section_length]
        limitations_and_conclusion = limitations_and_conclusion[:max_section_length]

    return {
        "abstract": abstract,
        "system_model_or_method": system_model_or_method,
        "limitations_and_conclusion": limitations_and_conclusion,
        "raw_sample": full_text[:4000],
        "all_sections": sections,
    }


def _parse_latex_sections(tex_source: str, max_section_length: int = 15000) -> dict[str, Any]:
    """Extract abstract and \\section{...} blocks from raw LaTeX source."""
    # Strip unescaped % comments
    cleaned_lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in tex_source.splitlines()]
    cleaned = "\n".join(cleaned_lines)

    abstract = ""
    ab_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", cleaned, re.DOTALL | re.IGNORECASE)
    if ab_match:
        abstract = re.sub(r"\s+", " ", ab_match.group(1)).strip()

    sec_pattern = re.compile(r"\\(?:sub)*section\*?\{([^}]+)\}")
    matches = list(sec_pattern.finditer(cleaned))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        title = re.sub(r"\s+", " ", m.group(1)).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(cleaned)
        body = cleaned[start:end].strip()
        if body:
            sections[title] = body

    return _map_sections_to_canonical(abstract, sections, max_section_length=max_section_length)


def fetch_arxiv_structured_text(
    arxiv_id: str,
    max_section_length: int = 15000,
    timeout: int = 12,
) -> dict[str, Any]:
    """
    Fetch structured full text for an arXiv paper via arXiv HTML, ar5iv HTML,
    or LaTeX e-print source tarball.
    """
    clean_id = clean_arxiv_id(arxiv_id)
    if not clean_id:
        return {"status": "ERROR", "error_message": f"Invalid arXiv identifier: {arxiv_id}"}

    headers = {"User-Agent": DEFAULT_USER_AGENT}

    # 1. Try native arXiv HTML, then ar5iv HTML
    for source_name, url in (
        ("arxiv_html", f"https://arxiv.org/html/{clean_id}"),
        ("ar5iv_html", f"https://ar5iv.labs.arxiv.org/html/{clean_id}"),
    ):
        try:
            resp = _http_get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and "<html" in resp.text.lower():
                parser = _ArxivHTMLSectionParser()
                parser.feed(resp.text)
                abstract, sections = parser.get_parsed()
                if sections or abstract:
                    mapped = _map_sections_to_canonical(abstract, sections, max_section_length=max_section_length)
                    return {"status": "SUCCESS", "source": source_name, "arxiv_id": clean_id, **mapped}
        except Exception:
            continue

    # 2. Fallback to arXiv LaTeX e-print source
    eprint_url = f"https://arxiv.org/e-print/{clean_id}"
    try:
        resp = _http_get(eprint_url, headers=headers, timeout=timeout)
        if resp.status_code == 200 and resp.content:
            tex_chunks: list[str] = []
            try:
                with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:*") as tf:
                    for member in tf.getmembers():
                        if member.isfile() and member.name.lower().endswith(".tex"):
                            f = tf.extractfile(member)
                            if f is not None:
                                tex_chunks.append(f.read().decode("utf-8", errors="replace"))
            except tarfile.TarError:
                text_body = resp.content.decode("utf-8", errors="replace")
                if "\\begin{document}" in text_body or "\\section" in text_body:
                    tex_chunks.append(text_body)

            if tex_chunks:
                combined_tex = "\n\n".join(tex_chunks)
                mapped = _parse_latex_sections(combined_tex, max_section_length=max_section_length)
                return {"status": "SUCCESS", "source": "arxiv_latex", "arxiv_id": clean_id, **mapped}
    except Exception as exc:
        return {"status": "ERROR", "error_message": str(exc), "arxiv_id": clean_id}

    return {"status": "NOT_FOUND", "error_message": f"No structured HTML or LaTeX source found for {clean_id}"}


def _extract_note_field(content: dict[str, Any], key: str) -> str:
    """Handle both OpenReview API v2 ({'value': ...}) and v1 (plain str) note content."""
    val = content.get(key)
    if isinstance(val, dict):
        val = val.get("value", "")
    if isinstance(val, list):
        return "\n".join(str(v) for v in val if v)
    return str(val).strip() if val is not None else ""


def fetch_openreview_reviews(
    title: str | None = None,
    forum_id: str | None = None,
    timeout: int = 12,
    max_reviews: int = 10,
) -> dict[str, Any]:
    """
    Fetch official peer-review weaknesses, limitations, and questions from OpenReview API v2.
    """
    if not title and not forum_id:
        return {"status": "ERROR", "error_message": "Provide either title or forum_id."}

    headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    resolved_forum = forum_id

    if not resolved_forum and title:
        encoded = urllib.parse.quote(title.strip())
        search_url = f"https://api2.openreview.net/notes/search?query={encoded}&limit=5"
        try:
            resp = _http_get(search_url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                notes = resp.json().get("notes", [])
                target_norm = re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()
                best_note = None
                for note in notes:
                    note_title = _extract_note_field(note.get("content", {}), "title")
                    note_norm = re.sub(r"[^a-z0-9]+", " ", note_title.lower()).strip()
                    if note_norm == target_norm or (target_norm and target_norm in note_norm):
                        best_note = note
                        break
                if best_note is None and notes:
                    best_note = notes[0]
                if best_note:
                    resolved_forum = best_note.get("forum") or best_note.get("id")
        except Exception as exc:
            return {"status": "ERROR", "error_message": f"OpenReview search failed: {exc}"}

    if not resolved_forum:
        return {"status": "NOT_FOUND", "reviews": [], "message": "No matching OpenReview forum found."}

    forum_url = f"https://api2.openreview.net/notes?forum={urllib.parse.quote(resolved_forum)}"
    try:
        resp = _http_get(forum_url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return {"status": "ERROR", "error_message": f"OpenReview forum query returned {resp.status_code}"}
        notes = resp.json().get("notes", [])
    except Exception as exc:
        return {"status": "ERROR", "error_message": str(exc)}

    reviews: list[dict[str, Any]] = []
    for note in notes:
        content = note.get("content") or {}
        weaknesses = _extract_note_field(content, "weaknesses")
        limitations = _extract_note_field(content, "limitations")
        questions = _extract_note_field(content, "questions")
        main_review = _extract_note_field(content, "main_review")
        summary = _extract_note_field(content, "summary")
        rating = _extract_note_field(content, "rating")
        confidence = _extract_note_field(content, "confidence")

        if any((weaknesses, limitations, questions, main_review)):
            reviews.append(
                {
                    "note_id": note.get("id", ""),
                    "forum_id": resolved_forum,
                    "rating": rating,
                    "confidence": confidence,
                    "summary": summary,
                    "weaknesses": weaknesses,
                    "limitations": limitations,
                    "questions": questions,
                    "main_review": main_review,
                }
            )
        if len(reviews) >= max_reviews:
            break

    return {
        "status": "SUCCESS" if reviews else "NOT_FOUND",
        "forum_id": resolved_forum,
        "review_count": len(reviews),
        "reviews": reviews,
    }
