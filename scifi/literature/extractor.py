#!/usr/bin/env python3
"""
Structured Text Extractor from Academic Paper PDFs.
Extracts abstract, methodology/system model, limitations/conclusions, and raw sample.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from pypdf import PdfReader


def extract_pdf_text(
    pdf_path: Union[str, Path],
    max_pages: int = 20,
) -> Dict[str, Any]:
    """
    Extract structured technical text from an academic paper PDF.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file on disk.
    max_pages : int
        Maximum number of pages to extract text from (default 20).

    Returns
    -------
    dict
        Status dict with keys: 'status' ('SUCCESS' or 'ERROR'), 'total_pages',
        'abstract', 'system_model_or_method', 'limitations_and_conclusion',
        'raw_sample', and 'sections'.
    """
    p = Path(pdf_path)
    if not p.exists():
        msg = f"File not found: {pdf_path}"
        return {
            "status": "ERROR",
            "error_message": msg,
            "message": msg,
        }

    try:
        reader = PdfReader(str(p))
        total_pages = len(reader.pages)
        pages_to_extract = (
            reader.pages[:max_pages]
            if (max_pages is not None and max_pages > 0)
            else reader.pages
        )

        full_text = []
        for page in pages_to_extract:
            t = page.extract_text()
            if t:
                full_text.append(t)

        raw_content = "\n".join(full_text)
        raw_sample = raw_content[:4000]

        abstract = ""
        # Abstract: between Abstract header and Introduction
        ab_match = re.search(
            r"(?i)(?:abstract|a\s+b\s+s\s+t\s+r\s+a\s+c\s+t)[\s\.:—\n](.*?)(?=\n(?:I\.|1\.|introduction))",
            raw_content,
            re.DOTALL,
        )
        if ab_match:
            abstract = ab_match.group(1).strip()[:2000]
        else:
            # Fallback: capture up to a blank line or uppercase heading
            fallback_ab = re.search(
                r"(?i)(?:abstract|a\s+b\s+s\s+t\s+r\s+a\s+c\s+t)[\s\.:—\n](.*?)(?=\n\s*\n|\n[A-Z0-9\.]+\s+[A-Z]|$)",
                raw_content,
                re.DOTALL,
            )
            if fallback_ab:
                abstract = fallback_ab.group(1).strip()[:2000]

        system_model_or_method = ""
        model_match = re.search(
            r"(?i)(?:system model|problem formulation|system formulation|methodology|proposed method|methods)(.*?)"
            r"(?=\n(?:[IVX]+\.|[0-9]+\.|algorithm|simulation|results|evaluation|experiment))",
            raw_content,
            re.DOTALL,
        )
        if model_match:
            system_model_or_method = model_match.group(1).strip()[:3000]

        limitations_and_conclusion = ""
        concl_match = re.search(
            r"(?i)(?:conclusion|concluding remarks|future work|limitations)(.*?)"
            r"(?=\n(?:references|bibliography)|$)",
            raw_content,
            re.DOTALL,
        )
        if concl_match:
            limitations_and_conclusion = concl_match.group(1).strip()[:3000]

        sections = {
            "total_pages": total_pages,
            "abstract": abstract,
            "system_model_or_method": system_model_or_method,
            "limitations_and_conclusion": limitations_and_conclusion,
            "raw_sample": raw_sample,
        }

        return {
            "status": "SUCCESS",
            "total_pages": total_pages,
            "abstract": abstract,
            "system_model_or_method": system_model_or_method,
            "limitations_and_conclusion": limitations_and_conclusion,
            "raw_sample": raw_sample,
            "sections": sections,
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
            "error": str(e),
            "message": str(e),
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract structured technical text from a PDF paper"
    )
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum pages to extract text from (default 20)",
    )
    args = parser.parse_args()
    print(json.dumps(extract_pdf_text(args.pdf, max_pages=args.max_pages), indent=2))
