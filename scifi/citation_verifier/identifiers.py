"""
Extraction, parsing, and normalization for academic identifiers (DOI, arXiv, PubMed, URLs).
"""

from __future__ import annotations

import html
import re
import urllib.parse
from html.parser import HTMLParser
from typing import Dict, Optional, Tuple

import requests

from scifi.network import get_session

DOI_REGEX = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
ARXIV_NEW_REGEX = re.compile(r"(?:arxiv:)?(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)
ARXIV_OLD_REGEX = re.compile(r"(?:arxiv:)?([a-z\-]+(?:\.[a-z]{2})?/\d{7}(?:v\d+)?)", re.IGNORECASE)
PUBMED_REGEX = re.compile(r"(?:pubmed\.ncbi\.nlm\.nih\.gov/|pmid:?\s*)(\d+)", re.IGNORECASE)
PMC_REGEX = re.compile(r"(?:ncbi\.nlm\.nih\.gov/pmc/articles/|pmcid:?\s*)(PMC\d+)", re.IGNORECASE)
OPENALEX_REGEX = re.compile(r"(?:openalex\.org/|^)(W\d{8,11})", re.IGNORECASE)


class HeadMetaParser(HTMLParser):
    """Fast HTML parser that extracts academic citation meta tags from the <head> section."""

    def __init__(self) -> None:
        super().__init__()
        self.meta_tags: Dict[str, str] = {}
        self.authors: list[str] = []
        self._in_head = False
        self._stop_parsing = False

    def handle_starttag(self, tag: str, attrs: list[Tuple[str, Optional[str]]]) -> None:
        if self._stop_parsing:
            return
        tag_lower = tag.lower()
        if tag_lower == "head":
            self._in_head = True
        elif tag_lower == "body":
            self._stop_parsing = True
            return

        if tag_lower == "meta":
            attr_dict = {k.lower(): (v or "") for k, v in attrs}
            name = attr_dict.get("name") or attr_dict.get("property") or ""
            name_lower = name.lower()
            content = attr_dict.get("content", "").strip()

            if name_lower in ("citation_doi", "dc.identifier", "dc.identifier.doi", "biorxiv.doi"):
                if "doi" not in self.meta_tags:
                    self.meta_tags["doi"] = content
            elif name_lower in ("citation_title", "dc.title", "og:title"):
                if "title" not in self.meta_tags:
                    self.meta_tags["title"] = content
            elif name_lower in ("citation_author", "dc.creator"):
                if content:
                    self.authors.append(content)
            elif name_lower in ("citation_publication_date", "citation_date", "dc.date"):
                if "date" not in self.meta_tags:
                    self.meta_tags["date"] = content
            elif name_lower in ("citation_journal_title", "citation_conference_title"):
                if "venue" not in self.meta_tags:
                    self.meta_tags["venue"] = content

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "head":
            self._stop_parsing = True


def clean_doi(raw: str) -> str:
    """Normalize and strip trailing punctuation from a DOI."""
    doi = raw.strip()
    doi = urllib.parse.unquote(doi)
    # Strip URL prefixes
    prefixes = [
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
        "doi.org/",
    ]
    for p in prefixes:
        if doi.lower().startswith(p):
            doi = doi[len(p) :].strip()
            break

    # Strip trailing punctuation often caught in regex or user text
    while doi and doi[-1] in ".,;:)>]}'\"":
        # Check if the closing bracket was matching an open bracket inside the DOI
        if doi[-1] == ")" and "(" in doi and doi.count("(") == doi.count(")"):
            break
        if doi[-1] == "]" and "[" in doi and doi.count("[") == doi.count("]"):
            break
        if doi[-1] == "}" and "{" in doi and doi.count("{") == doi.count("}"):
            break
        doi = doi[:-1]

    return doi.strip()


def extract_identifier(query: str, follow_links: bool = True) -> Tuple[str, str, Dict[str, str]]:
    """
    Given a user input (DOI, URL, arXiv ID, PMID, etc.), detect the identifier type
    and return (identifier_type, identifier_value, extra_metadata).

    Identifier types:
      - 'doi': e.g., '10.1038/s41586-020-2649-2'
      - 'arxiv': e.g., '1706.03762'
      - 'pubmed': e.g., '12345678'
      - 'pmc': e.g., 'PMC1234567'
      - 'openalex': e.g., 'W2741809807'
      - 'url': arbitrary web URL
      - 'unknown': could not parse
    """
    clean_q = query.strip()

    # 1. Direct or embedded DOI
    # Check if query is or contains a DOI
    doi_match = DOI_REGEX.search(clean_q)
    if doi_match:
        extracted = clean_doi(doi_match.group(0))
        # Verify it has standard DOI form (10.xxxx/...)
        if re.match(r"^10\.\d{4,9}/.+", extracted):
            return "doi", extracted, {"source_query": clean_q}

    # 2. arXiv ID
    # Check URL: https://arxiv.org/abs/2301.12345 or direct arXiv ID
    if "arxiv.org" in clean_q.lower() or clean_q.lower().startswith("arxiv:"):
        m_new = ARXIV_NEW_REGEX.search(clean_q)
        if m_new:
            return "arxiv", m_new.group(1), {"source_query": clean_q}
        m_old = ARXIV_OLD_REGEX.search(clean_q)
        if m_old:
            return "arxiv", m_old.group(1), {"source_query": clean_q}
    else:
        # Check if query matches strict standalone arXiv pattern
        m_new = re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", clean_q)
        if m_new:
            return "arxiv", m_new.group(0), {"source_query": clean_q}

    # 3. PubMed / PMC
    pm_match = PUBMED_REGEX.search(clean_q)
    if pm_match:
        return "pubmed", pm_match.group(1), {"source_query": clean_q}

    pmc_match = PMC_REGEX.search(clean_q)
    if pmc_match:
        return "pmc", pmc_match.group(1), {"source_query": clean_q}

    # 4. OpenAlex ID
    oa_match = OPENALEX_REGEX.search(clean_q)
    if oa_match:
        return "openalex", oa_match.group(1).upper(), {"source_query": clean_q}

    # 5. Generic URL: follow redirects and inspect HTML <head> meta tags
    if clean_q.startswith("http://") or clean_q.startswith("https://"):
        if follow_links:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SciFi-CitationVerifier/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
                resp = get_session().get(clean_q, headers=headers, timeout=10, allow_redirects=True)
                final_url = resp.url

                # Check final redirected URL for DOI
                final_doi_match = DOI_REGEX.search(final_url)
                if final_doi_match:
                    extracted = clean_doi(final_doi_match.group(0))
                    if re.match(r"^10\.\d{4,9}/.+", extracted):
                        return "doi", extracted, {"resolved_url": final_url, "source_query": clean_q}

                # Parse head meta tags
                parser = HeadMetaParser()
                # Parse up to first 64KB for speed and security
                sample_html = resp.text[:65536]
                parser.feed(sample_html)

                extra = dict(parser.meta_tags)
                if parser.authors:
                    extra["authors"] = "; ".join(parser.authors)
                extra["resolved_url"] = final_url
                extra["source_query"] = clean_q

                if "doi" in extra:
                    extracted = clean_doi(extra["doi"])
                    if re.match(r"^10\.\d{4,9}/.+", extracted):
                        return "doi", extracted, extra

                return "url", final_url, extra
            except Exception as e:
                return "url", clean_q, {"error": str(e), "source_query": clean_q}
        else:
            return "url", clean_q, {"source_query": clean_q}

    return "unknown", clean_q, {"source_query": clean_q}
