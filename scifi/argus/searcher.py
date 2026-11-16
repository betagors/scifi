"""
Literature searcher and registry resolver for Argus.
Queries OpenAlex and Crossref for canonical works and matches author whitelists.
"""

from __future__ import annotations

import re
from typing import Any

import requests

from scifi.cache import RegistryCache
from scifi.citation_verifier.discrepancy import string_similarity
from scifi.citation_verifier.models import Author, CitationMetadata, VerificationStatus
from scifi.network import get_session

_ORIG_REQUESTS_GET = requests.get


def _http_get(url: str, **kwargs: Any) -> requests.Response:
    """Execute GET request via requests.get if patched in tests, else ResilientSession."""
    if requests.get is not _ORIG_REQUESTS_GET:
        return requests.get(url, **kwargs)
    return get_session().get(url, **kwargs)


DEFAULT_USER_AGENT = "SciFi-Argus/1.0 (https://github.com/scifi-toolkit; mailto:scifi-toolkit@gmail.com)"


class ArgusSearcher:
    """Registry search client for retrieving canonical academic works and evaluating attribution gaps.

    Queries OpenAlex and Crossref to resolve candidate publications for uncredited
    method references and preprints.

    Attributes:
        OPENALEX_BASE: Base endpoint for the OpenAlex Works API.
        CROSSREF_BASE: Base endpoint for the Crossref Works API.
        author_whitelist: Set of lowercased author names ignored for plagiarism flagging.
        preprint_doi: Canonical DOI of prior preprint for self-alignment checking.
    """

    OPENALEX_BASE = "https://api.openalex.org/works"
    CROSSREF_BASE = "https://api.crossref.org/works"

    def __init__(
        self,
        author_whitelist: list[str] | None = None,
        preprint_doi: str | None = None,
        cache: RegistryCache | None = None,
        use_cache: bool = False,
    ):
        self.author_whitelist: set[str] = {a.lower().strip() for a in (author_whitelist or []) if a.strip()}
        self.preprint_doi: str | None = preprint_doi.lower().strip() if preprint_doi else None
        self.cache: RegistryCache | None = cache if cache is not None else (RegistryCache() if use_cache else None)

    def search_canonical_work(self, query: str, timeout: int = 10) -> tuple[CitationMetadata, float, bool] | None:
        """
        Search OpenAlex and Crossref for the seminal or canonical paper for a method or title query.
        Returns: (CitationMetadata, confidence_score, is_self_alignment).
        """
        clean_query = query.strip()
        if not clean_query:
            return None

        cache_key = f"argus:{clean_query.lower()}"
        if self.cache is not None:
            cached = self.cache.get(cache_key)
            if cached and isinstance(cached.get("metadata"), dict):
                metadata = CitationMetadata.from_dict(cached["metadata"])
                confidence = float(cached.get("confidence", 0.5))
                is_self_alignment = self._check_self_alignment(metadata)
                return metadata, confidence, is_self_alignment

        # 1. Try OpenAlex first
        result = self._search_openalex(clean_query, timeout=timeout)
        if not result:
            # 2. Try Crossref fallback
            result = self._search_crossref(clean_query, timeout=timeout)

        if not result:
            return None

        metadata, confidence = result
        if self.cache is not None:
            self.cache.set(cache_key, {"metadata": metadata.to_dict(), "confidence": confidence})

        is_self_alignment = self._check_self_alignment(metadata)

        return metadata, confidence, is_self_alignment

    def _check_self_alignment(self, metadata: CitationMetadata) -> bool:
        """Check if paper belongs to author whitelist or matches claimed preprint."""
        if self.preprint_doi and metadata.canonical_doi:
            if self.preprint_doi in metadata.canonical_doi.lower():
                return True

        if self.author_whitelist and metadata.authors:
            for a in metadata.authors:
                full_name = a.name.lower()
                family = a.family.lower() if a.family else ""
                for wl in self.author_whitelist:
                    if wl in full_name or (family and wl == family):
                        return True
        return False

    def _search_openalex(self, query: str, timeout: int = 10) -> tuple[CitationMetadata, float] | None:
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        # Quote exact query if short, else free text
        encoded_query = f'"{query}"' if len(query.split()) <= 4 else query
        params = {
            "search": encoded_query,
            "per_page": 3,
        }
        try:
            resp = _http_get(self.OPENALEX_BASE, headers=headers, params=params, timeout=timeout)
            if resp.status_code != 200:
                return None
            data = resp.json()
            results = data.get("results", [])
            if not results:
                # Try unquoted search
                params["search"] = query
                resp2 = _http_get(self.OPENALEX_BASE, headers=headers, params=params, timeout=timeout)
                if resp2.status_code == 200:
                    results = resp2.json().get("results", [])

            if not results:
                return None

            best = results[0]
            title = best.get("title", "")
            doi_raw = best.get("doi")
            canonical_doi = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", doi_raw) if doi_raw else None

            authors: list[Author] = []
            for authorship in best.get("authorships", []):
                a_obj = authorship.get("author", {})
                display_name = a_obj.get("display_name", "")
                if display_name:
                    authors.append(Author.from_string(display_name))

            year = best.get("publication_year")
            venue = None
            primary_loc = best.get("primary_location") or {}
            source = primary_loc.get("source") or {}
            if source:
                venue = source.get("display_name")

            citation_count = best.get("cited_by_count", 0)

            # Confidence calculation based on title match and citation volume
            sim = string_similarity(query, title)
            # Boost confidence for highly cited canonical papers
            cite_boost = min(0.3, (citation_count / 5000.0) * 0.3)
            confidence = min(0.99, max(0.5, sim + cite_boost))

            metadata = CitationMetadata(
                identifier_type="doi" if canonical_doi else "openalex",
                identifier_value=canonical_doi or best.get("id", ""),
                status=VerificationStatus.VERIFIED,
                canonical_doi=canonical_doi,
                canonical_url=best.get("id"),
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                citation_count=citation_count,
                source_registry="OpenAlex",
            )
            return metadata, confidence
        except Exception:
            return None

    def _search_crossref(self, query: str, timeout: int = 10) -> tuple[CitationMetadata, float] | None:
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        params = {"query.bibliographic": query, "rows": 1}
        try:
            resp = _http_get(self.CROSSREF_BASE, headers=headers, params=params, timeout=timeout)
            if resp.status_code != 200:
                return None
            items = resp.json().get("message", {}).get("items", [])
            if not items:
                return None

            best = items[0]
            title = best.get("title", [""])[0] if best.get("title") else ""
            doi = best.get("DOI")

            authors: list[Author] = []
            for a in best.get("author", []):
                family = a.get("family", "")
                given = a.get("given", "")
                name = f"{given} {family}".strip() if (given or family) else "Unknown"
                authors.append(Author(name=name, family=family, given=given))

            year = None
            for d_field in ("published-print", "published-online", "issued"):
                parts = best.get(d_field, {}).get("date-parts", [])
                if parts and parts[0]:
                    year = parts[0][0]
                    break

            venue = best.get("container-title", [""])[0] if best.get("container-title") else None
            sim = string_similarity(query, title)
            confidence = max(0.4, sim)

            metadata = CitationMetadata(
                identifier_type="doi",
                identifier_value=doi,
                status=VerificationStatus.VERIFIED,
                canonical_doi=doi,
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                source_registry="Crossref",
            )
            return metadata, confidence
        except Exception:
            return None
