#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "requests",
# ]
# ///
import argparse
import json
import re
import sys
from pathlib import Path

import requests


def get_arxiv_pdf(arxiv_id: str, output_path: Path) -> dict:
    clean_id = re.sub(r"^arxiv:\s*", "", arxiv_id, flags=re.IGNORECASE).strip()
    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"
    headers = {"User-Agent": "scifi-hypatia/1.0 (academic-researcher)"}
    try:
        r = requests.get(pdf_url, headers=headers, stream=True, timeout=15)
        if r.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    f.write(chunk)
            return {
                "status": "SUCCESS",
                "source": "arXiv",
                "pdf_url": pdf_url,
                "file_path": str(output_path),
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
    return {"status": "NOT_FOUND", "message": "Could not retrieve arXiv PDF."}


def get_unpaywall_pdf(doi: str, email: str, output_path: Path) -> dict:
    url = f"https://api.unpaywall.org/v2/{doi}?email={email}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return {
                "status": "NOT_FOUND",
                "message": f"Unpaywall returned status {r.status_code}",
            }
        data = r.json()
        best_oa = data.get("best_oa_location")
        if not best_oa or not best_oa.get("url_for_pdf"):
            return {
                "status": "NO_OA_PDF",
                "message": "No open access PDF location recorded on Unpaywall.",
            }

        pdf_url = best_oa["url_for_pdf"]
        headers = {"User-Agent": "scifi-hypatia/1.0 (academic-researcher)"}
        pdf_res = requests.get(pdf_url, headers=headers, stream=True, timeout=20)
        if pdf_res.status_code == 200:
            with open(output_path, "wb") as f:
                for chunk in pdf_res.iter_content(chunk_size=8192):
                    f.write(chunk)
            return {
                "status": "SUCCESS",
                "source": "Unpaywall",
                "title": data.get("title"),
                "pdf_url": pdf_url,
                "file_path": str(output_path),
            }
    except Exception as e:
        return {"status": "ERROR", "error": str(e)}
    return {"status": "DOWNLOAD_FAILED", "message": "Failed to stream PDF from OA host."}


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
        "--out", default="downloaded_paper.pdf", help="Target path to save PDF"
    )
    parser.add_argument(
        "--email",
        default="researcher@university.edu",
        help="Email required by Unpaywall API",
    )
    args = parser.parse_args()

    out_p = Path(args.out)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    if "arxiv" in args.id.lower() or re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", args.id):
        res = get_arxiv_pdf(args.id, out_p)
    else:
        res = get_unpaywall_pdf(args.id, args.email, out_p)

    print(json.dumps(res, indent=2))
