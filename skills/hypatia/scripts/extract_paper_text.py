#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pypdf",
# ]
# ///
import argparse
import json
import re
from pathlib import Path

from pypdf import PdfReader


def extract_sections_from_pdf(pdf_path: str) -> dict:
    p = Path(pdf_path)
    if not p.exists():
        return {"status": "ERROR", "message": f"File not found: {pdf_path}"}

    try:
        reader = PdfReader(str(p))
        full_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                full_text.append(t)

        raw_content = "\n".join(full_text)

        sections = {
            "total_pages": len(reader.pages),
            "abstract": "",
            "system_model_or_method": "",
            "limitations_and_conclusion": "",
            "raw_sample": raw_content[:4000],
        }

        # Abstract: everything between "Abstract" header and the Introduction
        ab_match = re.search(
            r"(?i)abstract[\s\.:—\n](.*?)(?=\n(?:I\.|1\.|introduction))",
            raw_content,
            re.DOTALL,
        )
        if ab_match:
            sections["abstract"] = ab_match.group(1).strip()[:2000]

        # System model / method section
        model_match = re.search(
            r"(?i)(?:system model|problem formulation|system formulation|methodology)(.*?)"
            r"(?=\n(?:[IVX]+\.|[0-9]+\.|algorithm|simulation|results|evaluation|experiment))",
            raw_content,
            re.DOTALL,
        )
        if model_match:
            sections["system_model_or_method"] = model_match.group(1).strip()[:3000]

        # Conclusion / limitations section
        concl_match = re.search(
            r"(?i)(?:conclusion|concluding remarks|future work)(.*?)"
            r"(?=\n(?:references|bibliography)|$)",
            raw_content,
            re.DOTALL,
        )
        if concl_match:
            sections["limitations_and_conclusion"] = concl_match.group(1).strip()[:3000]

        return {"status": "SUCCESS", "sections": sections}

    except Exception as e:
        return {"status": "ERROR", "error": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract structured technical text from a PDF paper"
    )
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    args = parser.parse_args()
    print(json.dumps(extract_sections_from_pdf(args.pdf), indent=2))
