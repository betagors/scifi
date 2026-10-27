#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
import argparse
import json
import re
import sys
from pathlib import Path

# Common patterns indicating unhedged or sweeping claims
OVERCLAIM_PATTERNS = [
    (r"\b(drastically|dramatically|enormously|tremendously)\s+(improve[s|d]?|reduce[s|d]?|increase[s|d]?)\b", "Overstated impact adverb without exact quantitative bound"),
    (r"\b(completely|totally|entirely)\s+(eliminat(es?|ed|ing)|solv(es?|ed|ing))\b", "Absolute claim of total elimination/solution"),
    (r"\b(optimal|optimality)\b(?!\s+(bound|guarantee|condition|policy|gap|sub-))", "Claim of 'optimal' without formal optimality condition or proof context"),
    (r"\bfirst\s+work\s+to\b|\bfor\s+the\s+first\s+time\b", "Priority claim ('first to...') requiring exhaustive literature proof"),
    (r"\boutperform[s]?\s+all\s+(existing|prior|state-of-the-art)\b", "Sweeping superiority claim over all existing methods"),
    (r"\bperfect\s+(information|knowledge|csi|synchronization)\b", "Fragile idealised assumption: verify if justified in system model")
]

def scan_text(file_path: Path) -> dict:
    if not file_path.exists():
        return {"status": "ERROR", "message": f"File not found: {file_path}"}

    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    flagged_issues = []
    for line_idx, line in enumerate(lines, start=1):
        # Strip comments
        clean_line = re.sub(r"%.*$", "", line).strip()
        if not clean_line:
            continue

        for pattern, rule_desc in OVERCLAIM_PATTERNS:
            matches = re.finditer(pattern, clean_line, re.IGNORECASE)
            for m in matches:
                flagged_issues.append({
                    "line": line_idx,
                    "matched_text": m.group(0),
                    "critique": rule_desc,
                    "snippet": clean_line[:120]
                })

    return {
        "status": "SUCCESS",
        "file": str(file_path),
        "total_flags": len(flagged_issues),
        "flags": flagged_issues
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit manuscript for overclaims and fragile assumptions")
    parser.add_argument("--file", required=True, help="Path to LaTeX or Markdown file")
    args = parser.parse_args()
    print(json.dumps(scan_text(Path(args.file)), indent=2))
