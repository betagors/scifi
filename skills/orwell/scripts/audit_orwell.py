#!/usr/bin/env python3
"""
Standalone CLI & Skill Script for SciFi Orwell Academic Prose & LaTeX Stylometry Audit.

Usage:
    uv run python skills/orwell/scripts/audit_orwell.py <path/to/paper.tex | project_dir | raw_text> [--json] [--output report.md]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Ensure repository root is on sys.path when invoked directly as a script
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scifi.orwell import audit_orwell_prose


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(
        description="Audit a LaTeX manuscript or academic text across 6 forensic stylometric and structural AI-detection dimensions."
    )
    parser.add_argument(
        "target",
        help="Path to .tex file, multi-file LaTeX directory, Markdown/text file, or inline text string.",
    )
    parser.add_argument(
        "--output",
        help="Optional path to save the Markdown forensic report.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON.",
    )
    args = parser.parse_args(argv)

    res = audit_orwell_prose(args.target, output_report=args.output)
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Orwell audit failed.')}", file=sys.stderr)
        return 1

    if args.json:
        out = dict(res)
        out.pop("report_markdown", None)
        print(json.dumps(out, indent=2))
    else:
        print(res.get("report_markdown", ""))
    return 0 if res.get("human_score", 0) >= 55 else 1


if __name__ == "__main__":
    sys.exit(main())
