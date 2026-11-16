"""
API fetchers for Crossref, OpenAlex, arXiv, DataCite, and DOI content negotiation.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

import requests

from scifi.cache import RegistryCache
from scifi.network import get_session

from .models import Author, CitationMetadata, Discrepancy, Severity, VerificationStatus

DEFAULT_USER_AGENT = "SciFi-CitationVerifier/1.0 (https://github.com/scifi-toolkit; mailto:scifi-toolkit@gmail.com)"


class CrossRefFetcher:
    """Fetcher for querying metadata, DOIs, and retractions from the Crossref API.

    Attributes:
        BASE_URL: Crossref API endpoint for querying individual works by DOI.
    """

    BASE_URL = "https://api.crossref.org/works/"

    @classmethod
    def fetch(cls, doi: str, timeout: int = 10) -> dict[str, Any] | None:
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        url = f"{cls.BASE_URL}{requests.utils.quote(doi)}"
        try:
            resp = get_session().get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("message")
        except Exception:
            pass
        return None

    @classmethod
    def parse_metadata(cls, msg: dict[str, Any], doi: str) -> CitationMetadata:
        title = "Unknown"
        if msg.get("title") and len(msg["title"]) > 0:
            title = msg["title"][0].strip()

        authors: list[Author] = []
        for a in msg.get("author", []):
            family = a.get("family", "")
            given = a.get("given", "")
            name = f"{given} {family}".strip() if (given or family) else a.get("name", "Unknown")
            orcid = a.get("ORCID")
            authors.append(Author(name=name, family=family, given=given, orcid=orcid))

        year = None
        for date_key in ("published-print", "published-online", "issued", "created"):
            date_info = msg.get(date_key)
            if date_info and "date-parts" in date_info and date_info["date-parts"]:
                parts = date_info["date-parts"][0]
                if parts and isinstance(parts[0], int):
                    year = parts[0]
                    break

        venue = None
        if msg.get("container-title") and len(msg["container-title"]) > 0:
            venue = msg["container-title"][0].strip()
        elif msg.get("short-container-title") and len(msg["short-container-title"]) > 0:
            venue = msg["short-container-title"][0].strip()

        volume = msg.get("volume")
        issue = msg.get("issue")
        pages = msg.get("page")
        publisher = msg.get("publisher")

        type_map = {
            "journal-article": "article",
            "proceedings-article": "inproceedings",
            "book": "book",
            "book-chapter": "incollection",
            "dataset": "misc",
            "posted-content": "misc",
            "report": "techreport",
        }
        cr_type = msg.get("type", "journal-article")
        entry_type = type_map.get(cr_type, "article")

        citations = msg.get("is-referenced-by-count")

        # Check Crossmark / updates / retractions
        is_retracted = False
        retraction_details = None
        has_errata = False
        errata_details = None

        updates = msg.get("update-to", [])
        for u in updates:
            u_type = u.get("type", "").lower()
            u_label = u.get("label", "")
            if "retract" in u_type or "retract" in u_label.lower():
                is_retracted = True
                retraction_details = (
                    f"Crossmark retraction recorded: {u.get('updated', {}).get('timestamp', '')} {u.get('doi', '')}"
                )
            elif any(k in u_type or k in u_label.lower() for k in ("errat", "correct", "concern")):
                has_errata = True
                errata_details = f"Crossmark update recorded: {u_type} {u.get('doi', '')}"

        return CitationMetadata(
            identifier_type="doi",
            identifier_value=doi,
            status=VerificationStatus.RETRACTED
            if is_retracted
            else (VerificationStatus.ERRATA_EXISTS if has_errata else VerificationStatus.VERIFIED),
            canonical_doi=doi,
            canonical_url=f"https://doi.org/{doi}",
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            volume=str(volume) if volume is not None else None,
            issue=str(issue) if issue is not None else None,
            pages=str(pages) if pages is not None else None,
            publisher=publisher,
            entry_type=entry_type,
            citation_count=citations,
            is_retracted=is_retracted,
            retraction_details=retraction_details,
            has_errata=has_errata,
            errata_details=errata_details,
            source_registry="Crossref",
        )


class OpenAlexFetcher:
    """Fetcher for querying unified academic entity metadata from the OpenAlex Works API.

    Attributes:
        BASE_URL: OpenAlex Works REST API endpoint.
    """

    BASE_URL = "https://api.openalex.org/works/"

    @classmethod
    def fetch(cls, identifier: str, timeout: int = 10) -> dict[str, Any] | None:
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
        # identifier can be: DOI, OpenAlex ID (W...), PMID, etc.
        if identifier.startswith("10."):
            url = f"{cls.BASE_URL}https://doi.org/{identifier}"
        elif identifier.startswith("http"):
            url = f"{cls.BASE_URL}{identifier}"
        elif identifier.lower().startswith("pmid:"):
            url = f"{cls.BASE_URL}pmid:{identifier.split(':')[-1].strip()}"
        else:
            url = f"{cls.BASE_URL}{identifier}"

        try:
            resp = get_session().get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    @classmethod
    def parse_metadata(cls, data: dict[str, Any]) -> CitationMetadata:
        title = data.get("title") or "Unknown"
        doi_url = data.get("doi")
        canonical_doi = doi_url.replace("https://doi.org/", "") if doi_url else None

        authors: list[Author] = []
        for auth_entry in data.get("authorships", []):
            raw_author = auth_entry.get("author", {})
            name = raw_author.get("display_name", "")
            orcid = raw_author.get("orcid")
            authors.append(Author.from_string(name))
            if orcid and authors:
                authors[-1].orcid = orcid

        year = data.get("publication_year")

        venue = None
        primary_loc = data.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        if source:
            venue = source.get("display_name")

        type_map = {
            "journal-article": "article",
            "article": "article",
            "proceedings-article": "inproceedings",
            "conference": "inproceedings",
            "book": "book",
            "book-chapter": "incollection",
            "preprint": "misc",
            "dataset": "misc",
        }
        oa_type = data.get("type", "article")
        entry_type = type_map.get(oa_type, "article")

        citation_count = data.get("cited_by_count")
        is_retracted = bool(data.get("is_retracted", False))
        retraction_details = None
        if is_retracted:
            retraction_details = "Paper marked as retracted in OpenAlex registry."

        biblio = data.get("biblio") or {}
        volume = biblio.get("volume")
        issue = biblio.get("issue")
        first_page = biblio.get("first_page")
        last_page = biblio.get("last_page")
        pages = f"{first_page}-{last_page}" if (first_page and last_page) else first_page

        return CitationMetadata(
            identifier_type="openalex" if not canonical_doi else "doi",
            identifier_value=data.get("id", ""),
            status=VerificationStatus.RETRACTED if is_retracted else VerificationStatus.VERIFIED,
            canonical_doi=canonical_doi,
            canonical_url=doi_url or data.get("id"),
            title=title,
            authors=authors,
            year=year,
            venue=venue,
            volume=str(volume) if volume is not None else None,
            issue=str(issue) if issue is not None else None,
            pages=str(pages) if pages is not None else None,
            publisher=source.get("host_organization_name"),
            entry_type=entry_type,
            citation_count=citation_count,
            is_retracted=is_retracted,
            retraction_details=retraction_details,
            source_registry="OpenAlex",
        )


class ArXivFetcher:
    """Fetcher for querying preprint metadata from the official arXiv OAI-PMH/XML API.

    Attributes:
        BASE_URL: arXiv raw API query endpoint.
    """

    BASE_URL = "http://export.arxiv.org/api/query?id_list="

    @classmethod
    def fetch(cls, arxiv_id: str, timeout: int = 10) -> CitationMetadata | None:
        clean_id = re.sub(r"^arxiv:", "", arxiv_id, flags=re.IGNORECASE).strip()
        url = f"{cls.BASE_URL}{clean_id}"
        try:
            resp = get_session().get(url, timeout=timeout)
            if resp.status_code != 200:
                return None

            root = ET.fromstring(resp.text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            entry = root.find("atom:entry", ns)
            if entry is None:
                return None

            raw_title = entry.find("atom:title", ns)
            title = (
                re.sub(r"\s+", " ", raw_title.text.strip()) if raw_title is not None and raw_title.text else "Unknown"
            )

            authors: list[Author] = []
            for author_node in entry.findall("atom:author", ns):
                name_node = author_node.find("atom:name", ns)
                if name_node is not None and name_node.text:
                    authors.append(Author.from_string(name_node.text.strip()))

            published_node = entry.find("atom:published", ns)
            year = None
            if published_node is not None and published_node.text:
                m = re.match(r"^(\d{4})", published_node.text.strip())
                if m:
                    year = int(m.group(1))

            comment_node = entry.find("arxiv:comment", ns)
            comment_text = comment_node.text.strip() if comment_node is not None and comment_node.text else ""

            is_retracted = False
            retraction_details = None
            if "withdrawn" in comment_text.lower():
                is_retracted = True
                retraction_details = f"Preprint marked as withdrawn on arXiv: {comment_text}"

            doi_node = entry.find("arxiv:doi", ns)
            published_doi = doi_node.text.strip() if doi_node is not None and doi_node.text else None

            journal_ref_node = entry.find("arxiv:journal_ref", ns)
            venue = (
                journal_ref_node.text.strip()
                if journal_ref_node is not None and journal_ref_node.text
                else f"arXiv:{clean_id}"
            )

            return CitationMetadata(
                identifier_type="arxiv",
                identifier_value=clean_id,
                status=VerificationStatus.RETRACTED if is_retracted else VerificationStatus.VERIFIED,
                canonical_doi=published_doi,
                canonical_url=f"https://arxiv.org/abs/{clean_id}",
                title=title,
                authors=authors,
                year=year,
                venue=venue,
                entry_type="misc" if not published_doi else "article",
                is_retracted=is_retracted,
                retraction_details=retraction_details,
                source_registry="arXiv",
            )
        except Exception:
            return None


class DataCiteFetcher:
    """Fetcher for querying research dataset and artifact metadata from the DataCite REST API.

    Attributes:
        BASE_URL: DataCite DOIs REST API endpoint.
    """

    BASE_URL = "https://api.datacite.org/dois/"

    @classmethod
    def fetch(cls, doi: str, timeout: int = 10) -> CitationMetadata | None:
        headers = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/vnd.api+json"}
        url = f"{cls.BASE_URL}{requests.utils.quote(doi)}"
        try:
            resp = get_session().get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                return None
            data = resp.json().get("data", {})
            attrs = data.get("attributes", {})

            titles = attrs.get("titles", [])
            title = titles[0].get("title") if titles else "Unknown"

            creators = attrs.get("creators", [])
            authors: list[Author] = []
            for c in creators:
                family = c.get("familyName")
                given = c.get("givenName")
                name = c.get("name") or f"{given} {family}".strip()
                authors.append(Author(name=name, family=family, given=given))

            year = attrs.get("publicationYear")
            publisher = attrs.get("publisher")
            types = attrs.get("types", {})
            resource_type = types.get("resourceTypeGeneral", "Text").lower()

            entry_type = "article" if "journal" in resource_type or "article" in resource_type else "misc"

            return CitationMetadata(
                identifier_type="doi",
                identifier_value=doi,
                status=VerificationStatus.VERIFIED,
                canonical_doi=doi,
                canonical_url=f"https://doi.org/{doi}",
                title=title,
                authors=authors,
                year=year,
                publisher=publisher,
                entry_type=entry_type,
                source_registry="DataCite",
            )
        except Exception:
            return None


def resolve_citation(
    identifier_type: str,
    identifier_value: str,
    extra_info: dict[str, Any] | None = None,
    timeout: int = 10,
    cache: RegistryCache | None = None,
    use_cache: bool = False,
    strict_consensus: bool = False,
) -> CitationMetadata:
    """
    Composite resolution pipeline:
    1. Crossref / OpenAlex / arXiv / DataCite.
    2. Cross-checks OpenAlex for retraction status and citation counts.
    3. When strict_consensus=True, requires >=2 independent registries to confirm the reference.
    4. Returns unified CitationMetadata (cached in RegistryCache when use_cache=True).
    """
    active_cache = cache if cache is not None else (RegistryCache() if use_cache else None)
    cache_suffix = ":strict" if strict_consensus else ""
    cache_key = f"cv:{identifier_type}:{identifier_value}{cache_suffix}"
    if active_cache is not None and identifier_type != "url":
        cached = active_cache.get(cache_key)
        if cached is not None:
            return CitationMetadata.from_dict(cached)

    meta: CitationMetadata | None = None
    confirmed_registries: list[str] = []

    if identifier_type == "doi":
        # 1. Query Crossref first
        cr_data = CrossRefFetcher.fetch(identifier_value, timeout=timeout)
        if cr_data:
            meta = CrossRefFetcher.parse_metadata(cr_data, identifier_value)
            confirmed_registries.append("Crossref")

        # 2. Fallback to DataCite if not found in Crossref (or if strict consensus needs another source)
        if not meta:
            dc_meta = DataCiteFetcher.fetch(identifier_value, timeout=timeout)
            if dc_meta:
                meta = dc_meta
                confirmed_registries.append("DataCite")

        # 3. Always cross-check with OpenAlex for retraction status, citation count, and consensus
        oa_data = OpenAlexFetcher.fetch(identifier_value, timeout=timeout)
        if oa_data:
            confirmed_registries.append("OpenAlex")
            if not meta:
                meta = OpenAlexFetcher.parse_metadata(oa_data)
            else:
                # Augment with OpenAlex retraction and citation signals
                if oa_data.get("is_retracted"):
                    meta.is_retracted = True
                    meta.status = VerificationStatus.RETRACTED
                    meta.retraction_details = "Verified retracted in OpenAlex registry."
                if meta.citation_count is None and "cited_by_count" in oa_data:
                    meta.citation_count = oa_data.get("cited_by_count")

        # 4. Under strict consensus, try DataCite if we still have < 2 registries
        if strict_consensus and len(confirmed_registries) < 2 and "DataCite" not in confirmed_registries:
            dc_meta = DataCiteFetcher.fetch(identifier_value, timeout=timeout)
            if dc_meta:
                confirmed_registries.append("DataCite")
                if not meta:
                    meta = dc_meta

    elif identifier_type == "arxiv":
        meta = ArXivFetcher.fetch(identifier_value, timeout=timeout)
        if meta:
            confirmed_registries.append("arXiv")
        # If arXiv entry points to a published peer-reviewed DOI, augment it
        if meta and meta.canonical_doi:
            oa_data = OpenAlexFetcher.fetch(meta.canonical_doi, timeout=timeout)
            if oa_data:
                confirmed_registries.append("OpenAlex")
                oa_meta = OpenAlexFetcher.parse_metadata(oa_data)
                if oa_meta.venue:
                    meta.venue = oa_meta.venue
                if oa_meta.citation_count is not None:
                    meta.citation_count = oa_meta.citation_count
                if oa_meta.is_retracted:
                    meta.is_retracted = True
                    meta.status = VerificationStatus.RETRACTED
            if strict_consensus and len(confirmed_registries) < 2:
                cr_data = CrossRefFetcher.fetch(meta.canonical_doi, timeout=timeout)
                if cr_data:
                    confirmed_registries.append("Crossref")
        elif meta and strict_consensus and len(confirmed_registries) < 2:
            arxiv_base = meta.identifier_value.split("v")[0]
            oa_data = OpenAlexFetcher.fetch(f"https://doi.org/10.48550/arXiv.{arxiv_base}", timeout=timeout)
            if oa_data:
                confirmed_registries.append("OpenAlex")

    elif identifier_type in ("openalex", "pubmed"):
        oa_data = OpenAlexFetcher.fetch(identifier_value, timeout=timeout)
        if oa_data:
            meta = OpenAlexFetcher.parse_metadata(oa_data)
            confirmed_registries.append("OpenAlex")
        if meta and strict_consensus and len(confirmed_registries) < 2 and meta.canonical_doi:
            cr_data = CrossRefFetcher.fetch(meta.canonical_doi, timeout=timeout)
            if cr_data:
                confirmed_registries.append("Crossref")
            elif DataCiteFetcher.fetch(meta.canonical_doi, timeout=timeout):
                confirmed_registries.append("DataCite")

    elif identifier_type == "url":
        # If we have extracted metadata from HTML head
        if extra_info and extra_info.get("title"):
            authors = []
            if extra_info.get("authors"):
                for a_str in extra_info["authors"].split(";"):
                    if a_str.strip():
                        authors.append(Author.from_string(a_str.strip()))
            year = None
            if extra_info.get("date"):
                m = re.match(r"^(\d{4})", extra_info["date"])
                if m:
                    year = int(m.group(1))

            meta = CitationMetadata(
                identifier_type="url",
                identifier_value=identifier_value,
                status=VerificationStatus.VERIFIED,
                canonical_url=extra_info.get("resolved_url", identifier_value),
                title=extra_info.get("title"),
                authors=authors,
                year=year,
                venue=extra_info.get("venue"),
                source_registry="HTML-Meta",
            )
            confirmed_registries.append("HTML-Meta")

    if not meta:
        return CitationMetadata(
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            status=VerificationStatus.UNRESOLVED,
            title="Could not resolve metadata",
            source_registry="None",
        )

    meta.confirmed_registries = confirmed_registries
    if strict_consensus and len(confirmed_registries) < 2:
        meta.discrepancies.append(
            Discrepancy(
                field="consensus",
                claimed=">=2 registries",
                verified=f"{len(confirmed_registries)} ({', '.join(confirmed_registries) or 'none'})",
                severity=Severity.ERROR,
                message=(
                    f"Strict consensus failed: only {len(confirmed_registries)} registry confirmed "
                    f"({', '.join(confirmed_registries) or 'none'}); >=2 required."
                ),
            )
        )
        if meta.status != VerificationStatus.RETRACTED:
            meta.status = VerificationStatus.UNRESOLVED

    if active_cache is not None and identifier_type != "url" and meta.status != VerificationStatus.UNRESOLVED:
        active_cache.set(cache_key, meta.to_dict())

    return meta
