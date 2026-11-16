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
        sf_info = diag.get("scifi", {})
        if sf_info:
            print(f"SciFi: v{sf_info.get('version')} (install: {sf_info.get('install_mode')})")
            st = sf_info.get("store", {})
            if st.get("exists"):
                print(f"Literature Store: schema v{st.get('schema_version')} (integrity: {st.get('integrity')})")
            else:
                print("Literature Store: Not initialized yet")
            rules = sf_info.get("rules", {})
            if rules.get("total_marked", 0) > 0:
                out = rules.get("out_of_sync", [])
                rule_msg = f"{len(out)} out of sync ({', '.join(out)})" if out else "all in sync"
                print(f"Workspace Rules: {rule_msg}")
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
        ds = diag.get("datasets", {})
        if ds:
            print(f"Datasets Folder: {ds.get('status')} ({ds.get('default_dir')})")
        kg = diag.get("kaggle", {})
        if kg:
            kg_user = f" as {kg.get('username')}" if kg.get("username") else ""
            print(f"Kaggle: {kg.get('status')}{kg_user}")
            if kg.get("hint"):
                print(f"  Hint: {kg['hint']}")
        return 0

    if getattr(args, "history", False):
        from scifi.doctor import load_audit_history

        runs = load_audit_history(getattr(args, "target", "."))
        if getattr(args, "format", "markdown") == "json":
            print(json.dumps({"runs": runs}, indent=2))
        else:
            if not runs:
                print("No audit history found in .scifi/audit_history.json.")
                return 0
            print("# Readiness Ledger (.scifi/audit_history.json)")
            prev_score: int | None = None
            for r in runs:
                sc = int(r.get("readiness_score", 0))
                if prev_score is None:
                    delta_str = "baseline"
                else:
                    d = sc - prev_score
                    delta_str = f"+{d}" if d > 0 else str(d)
                prev_score = sc
                print(
                    f"- Run #{r.get('run_number')}: {sc}/100 ({delta_str}) | "
                    f"{r.get('readiness_tier')} | blockers={r.get('critical_blockers_count', 0)} | "
                    f"{r.get('timestamp')}"
                )
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
