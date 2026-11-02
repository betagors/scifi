#!/usr/bin/env python3
"""
Literature PDF Fetcher for open access academic papers.
Supports arXiv IDs, arXiv URLs, DOIs via Unpaywall, and OpenAlex fallback.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

import requests


def _is_arxiv_identifier(identifier: str) -> Optional[str]:
    """
    Check if the identifier is an arXiv ID or URL, and return the cleaned arXiv ID if so.
    """
    clean = identifier.strip()
    # Check for arXiv URL
    url_match = re.search(
        r"arxiv\.org/(?:abs|pdf)/([a-zA-Z\-]+/\d+|\d{4}\.\d{4,5}(?:v\d+)?)",
        clean,
        flags=re.IGNORECASE,
    )
    if url_match:
        return url_match.group(1)

    # Check for arXiv prefix (e.g. "arxiv:2301.12345")
    if re.match(r"^arxiv:\s*", clean, flags=re.IGNORECASE):
        return re.sub(r"^arxiv:\s*", "", clean, flags=re.IGNORECASE).strip()

    # Check for new-style arXiv ID: \d{4}.\d{4,5}(v\d+)?
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", clean):
        return clean

    # Check for old-style arXiv ID: e.g. math/0102003(v1)?
    if re.match(r"^[a-zA-Z\-]+/\d{7}(v\d+)?$", clean):
        return clean

    return None


def _resolve_target_path(identifier_slug: str, output_dir: Union[str, Path]) -> Path:
    """
    Resolve the destination file path given a target directory or file path.
    """
    out = Path(output_dir)
    if out.suffix.lower() == ".pdf":
        target = out
    else:
        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", identifier_slug)
        target = out / f"{safe_name}.pdf"
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _fetch_arxiv(arxiv_id: str, target_path: Path) -> Dict[str, Any]:
    """
    Download PDF directly from arXiv.
    """
    clean_id = re.sub(r"^arxiv:\s*", "", arxiv_id, flags=re.IGNORECASE).strip()
    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
    headers = {"User-Agent": "scifi-literature/1.0 (academic-researcher)"}
    try:
        r = requests.get(pdf_url, headers=headers, stream=True, timeout=15)
        if r.status_code == 200:
            with open(target_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return {
                "status": "SUCCESS",
                "source": "arXiv",
                "pdf_url": pdf_url,
                "file_path": str(target_path),
            }
        elif r.status_code == 404:
            return {
                "status": "NOT_FOUND",
                "message": f"arXiv PDF not found (status 404): {pdf_url}",
                "file_path": None,
                "source": "arXiv",
                "pdf_url": pdf_url,
            }
        else:
            return {
                "status": "NOT_FOUND",
                "message": f"arXiv returned status {r.status_code}: {pdf_url}",
                "file_path": None,
                "source": "arXiv",
                "pdf_url": pdf_url,
            }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "error": str(e),
            "message": str(e),
            "file_path": None,
            "source": "arXiv",
            "pdf_url": pdf_url,
        }


def _download_pdf_stream(pdf_url: str, target_path: Path) -> bool:
    """
    Download PDF bytes from a given URL to the target path.
    """
    headers = {"User-Agent": "scifi-literature/1.0 (academic-researcher)"}
    res = requests.get(pdf_url, headers=headers, stream=True, timeout=20)
    if res.status_code == 200:
        with open(target_path, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False


def _fetch_doi(doi: str, email: str, target_path: Path) -> Dict[str, Any]:
    """
    Query Unpaywall and OpenAlex for an open access PDF.
    """
    clean_doi = re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", doi, flags=re.IGNORECASE
    ).strip()
    headers = {"User-Agent": "scifi-literature/1.0 (academic-researcher)"}

    unpaywall_url = f"https://api.unpaywall.org/v2/{clean_doi}?email={email}"
    unpaywall_status = None
    unpaywall_data = None

    try:
        r = requests.get(unpaywall_url, headers=headers, timeout=10)
        unpaywall_status = r.status_code
        if r.status_code == 200:
            unpaywall_data = r.json()
            best_oa = unpaywall_data.get("best_oa_location")
            if best_oa and best_oa.get("url_for_pdf"):
                pdf_url = best_oa["url_for_pdf"]
                if _download_pdf_stream(pdf_url, target_path):
                    return {
                        "status": "SUCCESS",
                        "source": "Unpaywall",
                        "title": unpaywall_data.get("title"),
                        "pdf_url": pdf_url,
                        "file_path": str(target_path),
                    }
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "error": str(e),
            "message": str(e),
            "file_path": None,
            "source": "Unpaywall",
            "pdf_url": None,
        }

    # OpenAlex fallback
    try:
        openalex_url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"
        oa_r = requests.get(openalex_url, headers=headers, timeout=10)
        if oa_r.status_code == 200:
            oa_data = oa_r.json()
            oa_loc = oa_data.get("best_oa_location") or oa_data.get("primary_location") or {}
            pdf_url = oa_loc.get("pdf_url")
            if not pdf_url and oa_data.get("open_access", {}).get("is_oa"):
                pdf_url = oa_data.get("open_access", {}).get("oa_url")

            if pdf_url:
                if _download_pdf_stream(pdf_url, target_path):
                    return {
                        "status": "SUCCESS",
                        "source": "OpenAlex",
                        "title": oa_data.get("title"),
                        "pdf_url": pdf_url,
                        "file_path": str(target_path),
                    }

            return {
                "status": "NO_OA_PDF",
                "message": f"No open access PDF location recorded on Unpaywall or OpenAlex for DOI {clean_doi}.",
                "file_path": None,
                "source": None,
                "pdf_url": None,
            }
        elif oa_r.status_code == 404:
            if unpaywall_status == 404:
                return {
                    "status": "NOT_FOUND",
                    "message": f"DOI not found on Unpaywall or OpenAlex: {clean_doi}",
                    "file_path": None,
                    "source": None,
                    "pdf_url": None,
                }
            else:
                return {
                    "status": "NO_OA_PDF",
                    "message": f"No open access PDF recorded for DOI {clean_doi}.",
                    "file_path": None,
                    "source": None,
                    "pdf_url": None,
                }
        else:
            if unpaywall_data is not None:
                return {
                    "status": "NO_OA_PDF",
                    "message": f"No open access PDF recorded for DOI {clean_doi}.",
                    "file_path": None,
                    "source": None,
                    "pdf_url": None,
                }
            return {
                "status": "NOT_FOUND",
                "message": f"DOI not found: {clean_doi}",
                "file_path": None,
                "source": None,
                "pdf_url": None,
            }

    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "error": str(e),
            "message": str(e),
            "file_path": None,
            "source": None,
            "pdf_url": None,
        }


def fetch_paper_pdf(
    identifier: str,
    output_dir: Union[str, Path] = "workspace",
    email: str = "researcher@scifi.org",
) -> Dict[str, Any]:
    """
    Fetch an open access academic paper PDF given an arXiv ID or DOI.

    Parameters
    ----------
    identifier : str
        arXiv ID (e.g. '2301.12345', 'arxiv:2301.12345'), arXiv URL, or DOI (e.g. '10.1007/...').
    output_dir : str | Path
        Directory to save the PDF into, or exact target file path ending in .pdf. Default 'workspace'.
    email : str
        Contact email for the Unpaywall API. Default 'researcher@scifi.org'.

    Returns
    -------
    dict
        Status dict with keys: 'status' ('SUCCESS', 'NOT_FOUND', 'NO_OA_PDF', 'ERROR'),
        'file_path', 'source', 'pdf_url'.
    """
    arxiv_id = _is_arxiv_identifier(identifier)
    if arxiv_id:
        target_path = _resolve_target_path(arxiv_id, output_dir)
        return _fetch_arxiv(arxiv_id, target_path)
    else:
        clean_doi = re.sub(
            r"^(?:https?://(?:dx\.)?doi\.org/|doi:)", "", identifier, flags=re.IGNORECASE
        ).strip()
        target_path = _resolve_target_path(clean_doi, output_dir)
        return _fetch_doi(clean_doi, email, target_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch open access paper PDF via DOI or arXiv ID"
    )
    parser.add_argument(
        "--id",
        required=True,
        help="DOI (e.g. 10.1007/...) or arXiv ID (e.g. 2301.12345)",
    )
    parser.add_argument(
        "--out", default="workspace", help="Target path or directory to save PDF"
    )
    parser.add_argument(
        "--email",
        default="researcher@scifi.org",
        help="Email required by Unpaywall API",
    )
    args = parser.parse_args()
    res = fetch_paper_pdf(args.id, output_dir=args.out, email=args.email)
    print(json.dumps(res, indent=2))
