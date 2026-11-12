"""
Doctor Subcommand Handler (`sf doctor`).
"""

from __future__ import annotations

import argparse
import json
import sys


def cmd_doctor(args: argparse.Namespace) -> int:
    """Run the 6-stage Manuscript Readiness Pipeline or Environment Diagnostics (`sf doctor`)."""
    if getattr(args, "env", False):
        from scifi.env import diagnose_environment

        diag = diagnose_environment(auto_fix=getattr(args, "fix", False))
        print("=== SciFi Environment Health Diagnostic ===")
        print(f"Python: {diag['python']['version']} ({diag['python']['executable']})")
        uv_status = (
            "Available (" + diag["uv"].get("version", "") + ")"
            if diag["uv"]["available"]
            else "Missing (fallback active)"
        )
        print(f"uv: {uv_status}")
        z = diag["zotero"]
        port_str = "OPEN" if z["port_23119_open"] else "CLOSED"
        print(f"Zotero: {z['status']} (data_dir: {z['data_dir']}, port 23119: {port_str})")
        lat = diag["latex"]
        lat_status = "Available" if lat["available"] else "Missing"
        print(f"LaTeX Toolchain: {lat_status}")
        return 0

    from scifi.doctor import audit_manuscript

    res = audit_manuscript(
        tex_or_dir_path=args.target,
        bib_path=getattr(args, "bib", None),
        venue=getattr(args, "venue", None),
        double_blind=True if getattr(args, "double_blind", False) else None,
        compile_pdf=getattr(args, "compile", False),
        live=getattr(args, "live", False),
        output_report=getattr(args, "output", None),
    )
    if res.get("status") != "SUCCESS":
        print(f"[ERROR] {res.get('error_message', 'Manuscript audit failed.')}", file=sys.stderr)
        return 1

    if getattr(args, "format", "markdown") == "json":
        out = dict(res)
        out.pop("report_markdown", None)
        print(json.dumps(out, indent=2))
    else:
        print(res.get("report_markdown", ""))
    return 0 if res.get("readiness_score", 0) >= 65 else 1
