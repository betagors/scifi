#!/usr/bin/env python3
"""
Structured Text Extractor from Academic Paper PDFs.
Extracts abstract, methodology/system model, limitations/conclusions, and raw sample.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader


def extract_sections_from_text(
    raw_content: str,
    max_section_length: int = 15000,
) -> dict[str, str]:
    """
    Parse raw academic paper text into structured section blocks.

    Parameters
    ----------
    raw_content : str
        Extracted text of the paper.
    max_section_length : int
        Maximum characters per extracted section (0 for unlimited). Default 15000.

    Returns
    -------
    dict
        Structured sections: 'abstract', 'system_model_or_method', 'limitations_and_conclusion', 'raw_sample'.
    """
    raw_sample = raw_content[:4000]

    abstract = ""
    # Abstract: between Abstract header and Introduction
    ab_match = re.search(
        r"(?i)(?:abstract|a\s+b\s+s\s+t\s+r\s+a\s+c\s+t)[\s\.:—\n](.*?)(?=\n\s*(?:I\.|1\.|introduction))",
        raw_content,
        re.DOTALL,
    )
    if ab_match:
        abstract = ab_match.group(1).strip()
    else:
        fallback_ab = re.search(
            r"(?i)(?:abstract|a\s+b\s+s\s+t\s+r\s+a\s+c\s+t)[\s\.:—\n](.*?)(?=\n\s*\n|\n\s*[A-Z0-9\.]+\s+[A-Z]|$)",
            raw_content,
            re.DOTALL,
        )
        if fallback_ab:
            abstract = fallback_ab.group(1).strip()

    if max_section_length > 0 and len(abstract) > max_section_length:
        abstract = abstract[:max_section_length]
    elif not max_section_length and len(abstract) > 4000:
        abstract = abstract[:4000]

    system_model_or_method = ""
    model_match = re.search(
        r"(?i)(?:(?:\n\s*|^)(?:[IVX0-9]+\.?\s*)?(?:system model(?: (?:and|&)(?: problem)? formulation)?|problem formulation|system formulation|methodology|proposed (?:method|approach|scheme|framework|model)|methods|system architecture|theoretical framework|analytical model)[\s\.:—\n])(.*?)"
        r"(?=\n\s*(?:[IVX0-9]+\.?\s*)?(?:simulation|results|numerical results|experiments|evaluation|performance evaluation|discussion|conclusion|references))",
        raw_content,
        re.DOTALL,
    )
    if model_match:
        system_model_or_method = model_match.group(1).strip()
    else:
        alt_match = re.search(
            r"(?i)(?:(?:\n\s*|^)(?:[IVX0-9]+\.?\s*)?(?:methodology|methods|system model|formulation)[\s\.:—\n])(.*?)"
            r"(?=\n\s*(?:[IVX0-9]+\.?\s*)?(?:results|experiments|discussion|conclusion))",
            raw_content,
            re.DOTALL,
        )
        if alt_match:
            system_model_or_method = alt_match.group(1).strip()

    if max_section_length > 0 and len(system_model_or_method) > max_section_length:
        system_model_or_method = system_model_or_method[:max_section_length]

    limitations_and_conclusion = ""
    concl_match = re.search(
        r"(?i)(?:(?:\n\s*|^)(?:[IVX0-9]+\.?\s*)?(?:limitations|threats to validity|discussion(?: and limitations)?|conclusions?(?: and future work)?|concluding remarks|future work)[\s\.:—\n])(.*?)"
        r"(?=\n\s*(?:references|bibliography|acknowledg(?:e)?ments|appendix)|$)",
        raw_content,
        re.DOTALL,
    )
    if concl_match:
        limitations_and_conclusion = concl_match.group(1).strip()
    else:
        alt_concl = re.search(
            r"(?i)(?:(?:\n\s*|^)(?:conclusions?|future work|limitations)[\s\.:—\n])(.*?)"
            r"(?=\n\s*(?:references|bibliography)|$)",
            raw_content,
            re.DOTALL,
        )
        if alt_concl:
            limitations_and_conclusion = alt_concl.group(1).strip()

    if max_section_length > 0 and len(limitations_and_conclusion) > max_section_length:
        limitations_and_conclusion = limitations_and_conclusion[:max_section_length]

    return {
        "abstract": abstract,
        "system_model_or_method": system_model_or_method,
        "limitations_and_conclusion": limitations_and_conclusion,
        "raw_sample": raw_sample,
    }


def extract_pdf_text(
    pdf_path: str | Path,
    max_pages: int = 20,
    max_section_length: int = 15000,
) -> dict[str, Any]:
    """
    Extract structured technical text from an academic paper PDF.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the PDF file on disk.
    max_pages : int
        Maximum number of pages to extract text from (default 20).
    max_section_length : int
        Maximum character length per extracted section (default 15000).

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
        pages_to_extract = reader.pages[:max_pages] if (max_pages is not None and max_pages > 0) else reader.pages

        full_text = []
        for page in pages_to_extract:
            t = page.extract_text()
            if t:
                full_text.append(t)

        raw_content = "\n".join(full_text)
        parsed = extract_sections_from_text(raw_content, max_section_length=max_section_length)

        sections = {
            "total_pages": total_pages,
            "abstract": parsed["abstract"],
            "system_model_or_method": parsed["system_model_or_method"],
            "limitations_and_conclusion": parsed["limitations_and_conclusion"],
            "raw_sample": parsed["raw_sample"],
        }

        return {
            "status": "SUCCESS",
            "total_pages": total_pages,
            "abstract": parsed["abstract"],
            "system_model_or_method": parsed["system_model_or_method"],
            "limitations_and_conclusion": parsed["limitations_and_conclusion"],
            "raw_sample": parsed["raw_sample"],
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
    parser = argparse.ArgumentParser(description="Extract structured technical text from a PDF paper")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=20,
        help="Maximum pages to extract text from (default 20)",
    )
    parser.add_argument(
        "--max-section-length",
        type=int,
        default=15000,
        help="Maximum characters per extracted section (default 15000)",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            extract_pdf_text(
                args.pdf,
                max_pages=args.max_pages,
                max_section_length=args.max_section_length,
            ),
            indent=2,
        )
    )
