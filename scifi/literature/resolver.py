"""
Canonical Paper Resolver & Registry Client for OpenAlex and arXiv.

Resolves papers by title, DOI, or arXiv ID, normalizes bibliographic identifiers,
reconstructs abstracts from inverted indices, and models access and authorship roasters.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

import requests

from scifi.literature.models import (
    AuthorRecord,
    PaperIdentifierRecord,
    PaperLocationRecord,
    PaperRecord,
    PaperVersionRecord,
)
from scifi.network import get_session

_ORIG_REQUESTS_GET = requests.get


def _http_get(url: str, **kwargs: Any) -> requests.Response:
    """Execute GET request via requests.get if patched in tests, else ResilientSession."""
    if requests.get is not _ORIG_REQUESTS_GET:
        return requests.get(url, **kwargs)
    return get_session().get(url, **kwargs)

DEFAULT_USER_AGENT = "scifi-literature/1.0 (academic-researcher)"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ARXIV_API_URL = "http://export.arxiv.org/api/query"
CROSSREF_WORKS_URL = "https://api.crossref.org/works"

DOI_REGEX = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
ARXIV_ID_REGEX = re.compile(
    r"(?:arxiv\.org/(?:abs|pdf)/|^arxiv:\s*|^)?([a-zA-Z\-]+/\d{7}(?:v\d+)?|\d{4}\.\d{4,5}(?:v\d+)?)",
    re.IGNORECASE,
)


def clean_doi(raw: str) -> str:
    """
    Normalize and strip prefixes and trailing punctuation from a DOI.
    """
    if not raw:
        return ""
    doi = raw.strip()
    doi = urllib.parse.unquote(doi)

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

    # Strip trailing punctuation
    while doi and doi[-1] in ".,;:)>]}'\"":
        if doi[-1] == ")" and "(" in doi and doi.count("(") == doi.count(")"):
            break
        if doi[-1] == "]" and "[" in doi and doi.count("[") == doi.count("]"):
            break
        if doi[-1] == "}" and "{" in doi and doi.count("{") == doi.count("}"):
            break
        doi = doi[:-1]

    # If the DOI contains a DOI regex match, prefer the matched span
    match = DOI_REGEX.search(doi)
    if match:
        return match.group(0).rstrip(".,;")

    return doi.strip()


def clean_arxiv_id(raw: str) -> str:
    """
    Extract and normalize clean arXiv identifier (e.g. '1706.03762' or 'math/0102003v1').
    """
    if not raw:
        return ""
    clean = raw.strip()
    clean = re.sub(r"\.pdf$", "", clean, flags=re.IGNORECASE)

    # Check for direct URL match
    match = ARXIV_ID_REGEX.search(clean)
    if match and match.group(1):
        return match.group(1).strip()

    # Fallback stripping
    clean = re.sub(r"^https?://arxiv\.org/(?:abs|pdf)/", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^arxiv:\s*", "", clean, flags=re.IGNORECASE)
    return clean.strip()


def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """
    Reconstruct full abstract string from an OpenAlex abstract inverted index.
    """
    if not inverted_index or not isinstance(inverted_index, dict):
        return None

    pos_words: List[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for pos in positions:
                if isinstance(pos, int):
                    pos_words.append((pos, word))

    if not pos_words:
        return None

    pos_words.sort(key=lambda item: item[0])
    return " ".join(w for _, w in pos_words).strip()


TOP_VENUE_PATTERNS = [
    # Top Journals & Multidisciplinary
    r"\bNature\b",
    r"\bScience\b",
    r"\bPNAS\b",
    r"Proceedings of the National Academy of Sciences",
    r"Nature Communications",
    r"Science Advances",
    r"\bCell\b",
    r"\bLancet\b",
    r"New England Journal of Medicine",
    r"Physical Review Letters",
    r"\bPRL\b",
    r"\bJACS\b",
    r"Journal of the American Chemical Society",
    # Society Flagships (IEEE, ACM, SIAM)
    r"IEEE Transactions\b",
    r"IEEE Trans\b",
    r"IEEE/ACM Transactions\b",
    r"IEEE Journal\b",
    r"Proceedings of the IEEE\b",
    r"ACM Transactions\b",
    r"ACM Trans\b",
    r"ACM Computing Surveys",
    r"SIAM Journal\b",
    r"SIAM Review\b",
    # AI / ML / CV / NLP
    r"\bNeurIPS\b",
    r"Neural Information Processing Systems",
    r"\bICML\b",
    r"International Conference on Machine Learning",
    r"\bICLR\b",
    r"International Conference on Learning Representations",
    r"\bCVPR\b",
    r"Conference on Computer Vision and Pattern Recognition",
    r"\bICCV\b",
    r"International Conference on Computer Vision",
    r"\bECCV\b",
    r"European Conference on Computer Vision",
    r"\bACL\b",
    r"Association for Computational Linguistics",
    r"\bEMNLP\b",
    r"\bNAACL\b",
    r"\bAAAI\b",
    r"\bIJCAI\b",
    r"\bCOLT\b",
    # Systems / Networking / Architecture
    r"\bINFOCOM\b",
    r"\bSIGCOMM\b",
    r"\bMobiCom\b",
    r"\bNSDI\b",
    r"\bOSDI\b",
    r"\bSOSP\b",
    r"\bFAST\b",
    r"\bSIGMETRICS\b",
    r"USENIX",
    r"\bEuroSys\b",
    r"\bCoNEXT\b",
    r"\bSECON\b",
    r"\bICDCS\b",
    r"\bGLOBECOM\b",
    r"\bICC\b",
    # Software Engineering / PL
    r"\bICSE\b",
    r"\bFSE\b",
    r"\bASE\b",
    r"\bISSTA\b",
    r"\bPLDI\b",
    r"\bPOPL\b",
    r"\bOOPSLA\b",
    # Security
    r"IEEE Symposium on Security and Privacy",
    r"ACM Conference on Computer and Communications Security",
    r"\bCCS\b",
    r"\bNDSS\b",
    # Data / Web
    r"\bSIGMOD\b",
    r"\bVLDB\b",
    r"Very Large Data Bases",
    r"\bICDE\b",
    r"\bKDD\b",
    r"Knowledge Discovery and Data Mining",
    r"\bSIGIR\b",
    r"\bWSDM\b",
    r"The Web Conference",
    r"\bWWW\b",
    # Robotics & Control
    r"\bICRA\b",
    r"\bIROS\b",
    r"Robotics: Science and Systems",
    r"\bRSS\b",
    r"\bAutomatica\b",
]

COMPILED_TOP_VENUE_REGEX = [re.compile(p, re.IGNORECASE) for p in TOP_VENUE_PATTERNS]


def classify_venue_tier(venue_name: Optional[str]) -> str:
    """
    Classify a publication venue into domain-agnostic prestige tiers:
    - 'top': CORE A*/A flagship conferences or SJR Q1 / IEEE / ACM / Nature / Science journals.
    - 'preprint': arXiv, bioRxiv, chemRxiv, medRxiv, or unspecified venue.
    - 'standard': peer-reviewed venues not matching top-tier flagship patterns.
    """
    if not venue_name or not str(venue_name).strip():
        return "preprint"

    name_clean = str(venue_name).strip()
    # Check if preprint
    if re.search(r"\b(arxiv|biorxiv|medrxiv|chemrxiv|techrxiv|pre-?print|ssrn)\b", name_clean, re.IGNORECASE):
        for pattern in COMPILED_TOP_VENUE_REGEX:
            if pattern.search(name_clean):
                return "top"
        return "preprint"

    for pattern in COMPILED_TOP_VENUE_REGEX:
        if pattern.search(name_clean):
            return "top"

    return "standard"


class PaperResolver:
    """
    Canonical paper resolver interfacing with OpenAlex and arXiv registries.
    """

    def __init__(
        self,
        email: Optional[str] = None,
        timeout: int = 10,
        cache: Any = None,
    ) -> None:
        self.email = email
        self.timeout = timeout
        self.cache = cache

        if email:
            self.user_agent = f"scifi-literature/1.0 (mailto:{email})"
        else:
            self.user_agent = DEFAULT_USER_AGENT

        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
        }

    def _get_cached_paper(self, key: str) -> Optional[PaperRecord]:
        if not self.cache:
            return None
        try:
            cached_val = self.cache.get(key)
            if cached_val and isinstance(cached_val, dict):
                return PaperRecord.from_dict(cached_val)
        except Exception:
            pass
        return None

    def _set_cached_paper(self, key: str, paper: PaperRecord) -> None:
        if not self.cache or not paper:
            return
        try:
            self.cache.set(key, paper.to_dict())
        except Exception:
            pass

    def _parse_openalex_work(self, data: Dict[str, Any]) -> PaperRecord:
        """
        Parse an OpenAlex work JSON object into a canonical PaperRecord.
        """
        raw_id = data.get("id") or ""
        openalex_id = raw_id.strip().rstrip("/").split("/")[-1] if raw_id else ""
        paper_id = openalex_id or f"paper-{abs(hash(data.get('title', '')))}"

        title = (data.get("title") or "Untitled").strip()

        # Year and publication date
        year = data.get("publication_year")
        publication_date = data.get("publication_date")
        if year is None and publication_date:
            m = re.search(r"\b(19\d\d|20\d\d)\b", str(publication_date))
            if m:
                year = int(m.group(1))

        citation_count = int(data.get("cited_by_count") or 0)
        influential_citation_count = int(data.get("influential_citation_count") or 0)
        recent_citation_growth = float(data.get("recent_citation_growth") or 0.0)
        is_retracted = bool(data.get("is_retracted", False))

        # Abstract
        abstract = data.get("abstract")
        if not abstract:
            abstract = reconstruct_abstract(data.get("abstract_inverted_index"))

        # Authors
        authors: List[AuthorRecord] = []
        for idx, a in enumerate(data.get("authorships") or []):
            if not isinstance(a, dict):
                continue
            author_obj = a.get("author") or {}
            raw_a_id = author_obj.get("id") or f"A-{idx}"
            clean_a_id = raw_a_id.strip().rstrip("/").split("/")[-1] if raw_a_id else f"A-{idx}"
            name = (author_obj.get("display_name") or a.get("raw_author_name") or "Unknown").strip()
            orcid = author_obj.get("orcid")

            institution = None
            institutions = a.get("institutions") or []
            if institutions and isinstance(institutions, list) and isinstance(institutions[0], dict):
                institution = institutions[0].get("display_name")
            if not institution and a.get("raw_affiliation_strings"):
                raw_affs = a.get("raw_affiliation_strings")
                if isinstance(raw_affs, list) and raw_affs:
                    institution = str(raw_affs[0]).strip()

            email = a.get("email") or author_obj.get("email")

            authors.append(
                AuthorRecord(
                    id=clean_a_id,
                    name=name,
                    orcid=orcid,
                    email=email,
                    institution=institution,
                )
            )

        # Identifiers
        identifiers: List[PaperIdentifierRecord] = []
        if openalex_id:
            identifiers.append(
                PaperIdentifierRecord(
                    paper_id=paper_id,
                    provider="openalex",
                    external_id=openalex_id,
                    is_canonical=True,
                )
            )

        raw_doi = data.get("doi") or (data.get("ids") or {}).get("doi")
        clean_doi_str = clean_doi(raw_doi) if raw_doi else ""
        if clean_doi_str:
            identifiers.append(
                PaperIdentifierRecord(
                    paper_id=paper_id,
                    provider="doi",
                    external_id=clean_doi_str,
                    is_canonical=(not openalex_id),
                )
            )

        # ArXiv identifier
        ids_dict = data.get("ids") or {}
        raw_arxiv = ids_dict.get("arxiv")
        if not raw_arxiv and clean_doi_str and "arxiv" in clean_doi_str.lower():
            raw_arxiv = clean_doi_str
        if not raw_arxiv:
            oa_url = (data.get("open_access") or {}).get("oa_url") or ""
            if "arxiv.org" in oa_url.lower():
                raw_arxiv = oa_url

        if raw_arxiv:
            clean_arxiv = clean_arxiv_id(str(raw_arxiv))
            if clean_arxiv:
                identifiers.append(
                    PaperIdentifierRecord(
                        paper_id=paper_id,
                        provider="arxiv",
                        external_id=clean_arxiv,
                        is_canonical=False,
                    )
                )

        # Locations & Access Modeling
        locations: List[PaperLocationRecord] = []
        oa_info = data.get("open_access") or {}
        is_oa = bool(oa_info.get("is_oa", False))
        oa_status = oa_info.get("oa_status") or ("green" if is_oa else "closed")
        oa_url = oa_info.get("oa_url")

        raw_locations = data.get("locations") or []
        if raw_locations and isinstance(raw_locations, list):
            for loc in raw_locations:
                if not isinstance(loc, dict):
                    continue
                loc_source = loc.get("source") or {}
                loc_source_type = (loc_source.get("type") or "").lower()
                pdf_url = loc.get("pdf_url")
                landing_page = loc.get("landing_page_url")
                loc_is_oa = bool(loc.get("is_oa", is_oa))
                loc_oa_status = loc.get("oa_status") or oa_status

                is_repo = (
                    "repository" in loc_source_type
                    or (landing_page and "arxiv.org" in str(landing_page).lower())
                    or (pdf_url and "arxiv.org" in str(pdf_url).lower())
                )
                loc_type = "repository" if is_repo else "publisher"

                locations.append(
                    PaperLocationRecord(
                        id=f"{paper_id}-loc-{len(locations)}",
                        paper_id=paper_id,
                        location_type=loc_type,
                        is_oa=loc_is_oa,
                        oa_status=loc_oa_status,
                        landing_page_url=landing_page,
                        pdf_url=pdf_url,
                    )
                )

        if not locations:
            # Construct from primary_location, best_oa_location, or open_access
            primary_loc = data.get("primary_location") or {}
            best_oa_loc = data.get("best_oa_location") or {}
            target_loc = best_oa_loc if (best_oa_loc.get("pdf_url") or best_oa_loc.get("landing_page_url")) else primary_loc

            pdf_url = target_loc.get("pdf_url") or (oa_url if (oa_url and oa_url.endswith(".pdf")) else None)
            landing_page = target_loc.get("landing_page_url") or oa_url
            loc_source = target_loc.get("source") or {}
            loc_source_type = (loc_source.get("type") or "").lower()

            is_repo = (
                "repository" in loc_source_type
                or (landing_page and "arxiv.org" in str(landing_page).lower())
                or (pdf_url and "arxiv.org" in str(pdf_url).lower())
                or oa_status == "green"
            )
            loc_type = "repository" if is_repo else "publisher"

            locations.append(
                PaperLocationRecord(
                    id=f"{paper_id}-loc-0",
                    paper_id=paper_id,
                    location_type=loc_type,
                    is_oa=is_oa,
                    oa_status=oa_status,
                    landing_page_url=landing_page,
                    pdf_url=pdf_url,
                )
            )

        # Versions
        versions: List[PaperVersionRecord] = []
        raw_type = data.get("type", "")
        version_type = "preprint" if raw_type == "preprint" else "publishedVersion"
        versions.append(
            PaperVersionRecord(
                id=f"{paper_id}-v1",
                paper_id=paper_id,
                version_type=version_type,
                doi=clean_doi_str or None,
                release_date=publication_date,
            )
        )

        # Venue extraction for OpenAlex
        venue_name: Optional[str] = None
        primary_loc = data.get("primary_location") or {}
        source = primary_loc.get("source") or {}
        if source and isinstance(source, dict):
            venue_name = source.get("display_name")

        if not venue_name:
            host_venue = data.get("host_venue") or {}
            if isinstance(host_venue, dict):
                venue_name = host_venue.get("display_name")

        if not venue_name:
            locations_list = data.get("locations") or []
            for loc in locations_list:
                if isinstance(loc, dict):
                    s = loc.get("source") or {}
                    if s and isinstance(s, dict) and s.get("display_name"):
                        name = s.get("display_name")
                        if (s.get("type") or "").lower() != "repository":
                            venue_name = name
                            break
                        elif not venue_name:
                            venue_name = name

        venue_tier = classify_venue_tier(venue_name)

        return PaperRecord(
            id=paper_id,
            title=title,
            year=year,
            publication_date=publication_date,
            citation_count=citation_count,
            influential_citation_count=influential_citation_count,
            recent_citation_growth=recent_citation_growth,
            is_retracted=is_retracted,
            authors=authors,
            identifiers=identifiers,
            versions=versions,
            locations=locations,
            abstract=abstract,
            venue_name=venue_name,
            venue_tier=venue_tier,
        )

    def _parse_arxiv_atom(self, entry: ET.Element, arxiv_id: str) -> Optional[PaperRecord]:
        """
        Parse an arXiv XML Atom entry into a PaperRecord.
        """
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        title_node = entry.find("atom:title", ns)
        if title_node is None or not title_node.text:
            return None
        title = re.sub(r"\s+", " ", title_node.text.strip())

        summary_node = entry.find("atom:summary", ns)
        abstract = re.sub(r"\s+", " ", summary_node.text.strip()) if summary_node is not None and summary_node.text else None

        published_node = entry.find("atom:published", ns)
        publication_date = published_node.text.strip() if published_node is not None and published_node.text else None
        year = None
        if publication_date:
            m = re.search(r"\b(19\d\d|20\d\d)\b", publication_date)
            if m:
                year = int(m.group(1))

        authors: List[AuthorRecord] = []
        for idx, auth_node in enumerate(entry.findall("atom:author", ns)):
            name_node = auth_node.find("atom:name", ns)
            name = name_node.text.strip() if name_node is not None and name_node.text else "Unknown"
            authors.append(AuthorRecord(id=f"arxiv-a-{idx}", name=name))

        paper_id = f"arxiv:{arxiv_id}"
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        landing_page_url = f"https://arxiv.org/abs/{arxiv_id}"

        identifiers = [
            PaperIdentifierRecord(
                paper_id=paper_id,
                provider="arxiv",
                external_id=arxiv_id,
                is_canonical=True,
            )
        ]

        locations = [
            PaperLocationRecord(
                id=f"{paper_id}-loc-0",
                paper_id=paper_id,
                location_type="repository",
                is_oa=True,
                oa_status="green",
                landing_page_url=landing_page_url,
                pdf_url=pdf_url,
            )
        ]

        versions = [
            PaperVersionRecord(
                id=f"{paper_id}-v1",
                paper_id=paper_id,
                version_type="preprint",
                release_date=publication_date,
            )
        ]

        # Venue extraction for arXiv
        journal_ref_node = entry.find("arxiv:journal_ref", ns)
        if journal_ref_node is not None and journal_ref_node.text:
            venue_name = journal_ref_node.text.strip()
            venue_tier = classify_venue_tier(venue_name)
        else:
            venue_name = "arXiv"
            venue_tier = "preprint"

        return PaperRecord(
            id=paper_id,
            title=title,
            year=year,
            publication_date=publication_date,
            citation_count=0,
            influential_citation_count=0,
            recent_citation_growth=0.0,
            is_retracted=False,
            authors=authors,
            identifiers=identifiers,
            versions=versions,
            locations=locations,
            abstract=abstract,
            venue_name=venue_name,
            venue_tier=venue_tier,
        )

    def resolve_by_title(
        self,
        title: str,
        min_year: Optional[int] = None,
        max_year: Optional[int] = None,
    ) -> Optional[PaperRecord]:
        """
        Resolve a paper by its title using OpenAlex search, optionally filtering by year range.
        """
        clean_title = (title or "").strip()
        if not clean_title:
            return None

        cache_key = f"openalex:title:{clean_title.lower()}"
        cached = self._get_cached_paper(cache_key)
        if cached:
            if min_year is not None and cached.year is not None and cached.year < min_year:
                pass
            elif max_year is not None and cached.year is not None and cached.year > max_year:
                pass
            else:
                return cached

        try:
            params = {"search": clean_title, "per-page": 10}
            resp = _http_get(
                OPENALEX_WORKS_URL,
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results") or []
                if results and isinstance(results, list):
                    for r in results:
                        p = self._parse_openalex_work(r)
                        if min_year is not None and p.year is not None and p.year < min_year:
                            continue
                        if max_year is not None and p.year is not None and p.year > max_year:
                            continue
                        self._set_cached_paper(cache_key, p)
                        return p
                    if not min_year and not max_year and results:
                        paper = self._parse_openalex_work(results[0])
                        self._set_cached_paper(cache_key, paper)
                        return paper
        except Exception:
            return None

        return None

    def resolve_by_doi(self, doi: str) -> Optional[PaperRecord]:
        """
        Resolve a paper by DOI using OpenAlex with Crossref fallback.
        """
        clean_doi_str = clean_doi(doi)
        if not clean_doi_str:
            return None

        cache_key = f"openalex:doi:{clean_doi_str.lower()}"
        cached = self._get_cached_paper(cache_key)
        if cached:
            return cached

        # 1. Try OpenAlex
        try:
            url = f"{OPENALEX_WORKS_URL}/https://doi.org/{clean_doi_str}"
            resp = _http_get(url, headers=self.headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                work = data.get("results", [data])[0] if "results" in data else data
                paper = self._parse_openalex_work(work)
                self._set_cached_paper(cache_key, paper)
                return paper
        except Exception:
            pass

        # 2. Fallback to Crossref
        try:
            cr_url = f"{CROSSREF_WORKS_URL}/{urllib.parse.quote(clean_doi_str)}"
            cr_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
            cr_resp = _http_get(cr_url, headers=cr_headers, timeout=self.timeout)
            if cr_resp.status_code == 200:
                cr_data = cr_resp.json().get("message", {})
                title = cr_data.get("title", ["Untitled"])[0] if cr_data.get("title") else "Untitled"
                year = None
                for dkey in ("published-print", "published-online", "issued", "created"):
                    dinfo = cr_data.get(dkey, {})
                    parts = dinfo.get("date-parts", [[]])[0]
                    if parts and isinstance(parts[0], int):
                        year = parts[0]
                        break

                authors: List[AuthorRecord] = []
                for idx, a in enumerate(cr_data.get("author", [])):
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip() or a.get("name", "Unknown")
                    orcid = a.get("ORCID")
                    authors.append(AuthorRecord(id=f"cr-a-{idx}", name=name, orcid=orcid))

                paper_id = f"doi:{clean_doi_str}"
                paper = PaperRecord(
                    id=paper_id,
                    title=title,
                    year=year,
                    citation_count=int(cr_data.get("is-referenced-by-count") or 0),
                    authors=authors,
                    identifiers=[
                        PaperIdentifierRecord(
                            paper_id=paper_id,
                            provider="doi",
                            external_id=clean_doi_str,
                            is_canonical=True,
                        )
                    ],
                    locations=[
                        PaperLocationRecord(
                            id=f"{paper_id}-loc-0",
                            paper_id=paper_id,
                            location_type="publisher",
                            landing_page_url=f"https://doi.org/{clean_doi_str}",
                        )
                    ],
                )
                self._set_cached_paper(cache_key, paper)
                return paper
        except Exception:
            pass

        return None

    def resolve_by_arxiv_id(self, arxiv_id: str) -> Optional[PaperRecord]:
        """
        Resolve a paper by arXiv identifier using OpenAlex or arXiv XML API fallback.
        """
        clean_id = clean_arxiv_id(arxiv_id)
        if not clean_id:
            return None

        cache_key = f"arxiv:{clean_id.lower()}"
        cached = self._get_cached_paper(cache_key)
        if cached:
            return cached

        clean_without_v = re.sub(r"v\d+$", "", clean_id)

        # 1. Try OpenAlex by arXiv DOI
        try:
            doi_url = f"{OPENALEX_WORKS_URL}/https://doi.org/10.48550/arxiv.{clean_without_v}"
            resp = _http_get(doi_url, headers=self.headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                work = data.get("results", [data])[0] if "results" in data else data
                paper = self._parse_openalex_work(work)
                self._set_cached_paper(cache_key, paper)
                return paper
        except Exception:
            pass

        # 2. Try OpenAlex filter by ids.arxiv
        try:
            params = {"filter": f"ids.arxiv:{clean_without_v}", "per-page": 1}
            resp = _http_get(OPENALEX_WORKS_URL, headers=self.headers, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                results = resp.json().get("results") or []
                if results and isinstance(results, list):
                    paper = self._parse_openalex_work(results[0])
                    self._set_cached_paper(cache_key, paper)
                    return paper
        except Exception:
            pass

        # 3. Fallback to arXiv XML API
        try:
            url = f"{ARXIV_API_URL}?id_list={clean_id}"
            resp = _http_get(url, timeout=self.timeout)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                entry = root.find("atom:entry", ns)
                if entry is not None:
                    arxiv_paper = self._parse_arxiv_atom(entry, clean_id)
                    if arxiv_paper:
                        self._set_cached_paper(cache_key, arxiv_paper)
                        return arxiv_paper
        except Exception:
            pass

        return None

    def resolve_by_openalex_id(self, openalex_id: str) -> Optional[PaperRecord]:
        """
        Directly retrieve an OpenAlex work record by its OpenAlex work ID.
        """
        clean_id = (openalex_id or "").strip().rstrip("/").split("/")[-1]
        if not clean_id:
            return None

        cache_key = f"openalex:work:{clean_id}"
        cached = self._get_cached_paper(cache_key)
        if cached:
            return cached

        try:
            url = f"{OPENALEX_WORKS_URL}/{clean_id}"
            resp = _http_get(url, headers=self.headers, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                work = data.get("results", [data])[0] if "results" in data else data
                paper = self._parse_openalex_work(work)
                self._set_cached_paper(cache_key, paper)
                return paper
        except Exception:
            pass

        return None

    def resolve_references(self, openalex_work_id: str, limit: int = 10) -> List[PaperRecord]:
        """
        Resolve referenced works (foundational papers) for a given OpenAlex work ID.
        """
        clean_id = (openalex_work_id or "").strip().rstrip("/").split("/")[-1]
        if not clean_id:
            return []

        try:
            work_url = f"{OPENALEX_WORKS_URL}/{clean_id}"
            resp = _http_get(work_url, headers=self.headers, timeout=self.timeout)
            if resp.status_code != 200:
                return []

            work_data = resp.json()
            ref_urls = work_data.get("referenced_works") or []
            if not ref_urls or not isinstance(ref_urls, list):
                return []

            ref_ids = [u.strip().rstrip("/").split("/")[-1] for u in ref_urls[:limit] if u]
            if not ref_ids:
                return []

            # Batch query referenced works
            params = {
                "filter": f"openalex_id:{'|'.join(ref_ids)}",
                "per-page": len(ref_ids),
            }
            batch_resp = _http_get(
                OPENALEX_WORKS_URL,
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            if batch_resp.status_code == 200:
                results = batch_resp.json().get("results") or []
                if results and isinstance(results, list):
                    return [self._parse_openalex_work(r) for r in results]

            # Fallback to individual resolution if batch returns empty
            papers: List[PaperRecord] = []
            for rid in ref_ids:
                p = self.resolve_by_openalex_id(rid)
                if p:
                    papers.append(p)
            return papers

        except Exception:
            return []

    def resolve_citations(self, openalex_work_id: str, limit: int = 10) -> List[PaperRecord]:
        """
        Resolve citing works (recent frontier papers) citing a given OpenAlex work ID.
        """
        clean_id = (openalex_work_id or "").strip().rstrip("/").split("/")[-1]
        if not clean_id:
            return []

        try:
            params = {
                "filter": f"cites:{clean_id}",
                "per-page": limit,
                "sort": "cited_by_count:desc",
            }
            resp = _http_get(
                OPENALEX_WORKS_URL,
                headers=self.headers,
                params=params,
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                results = resp.json().get("results") or []
                if results and isinstance(results, list):
                    return [self._parse_openalex_work(r) for r in results]
        except Exception:
            return []

        return []


__all__ = [
    "clean_doi",
    "clean_arxiv_id",
    "reconstruct_abstract",
    "PaperResolver",
]
