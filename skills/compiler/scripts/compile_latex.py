#!/usr/bin/env python3
"""
compile_latex.py — Clean LaTeX compilation diagnostic engine.

Runs latexmk (or pdflatex as fallback), captures exit codes, and uses regex
to extract errors, missing packages, and broken references without flooding
the terminal with thousands of raw TeX log lines.

Cross-platform: auto-installs missing TeX packages via tlmgr (TeX Live) or
mpm (MiKTeX), and can bootstrap the entire engine on Windows via winget.
"""

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"


# ---------------------------------------------------------------------------
# Engine detection & installation
# ---------------------------------------------------------------------------

def check_or_install_engine() -> dict:
    """Verify that pdflatex or latexmk is available; attempt bootstrap if not."""
    has_latexmk = shutil.which("latexmk") is not None
    has_pdflatex = shutil.which("pdflatex") is not None

    if has_latexmk or has_pdflatex:
        return {"ready": True, "engine": "latexmk" if has_latexmk else "pdflatex"}

    # --- Windows: try winget → MiKTeX ---
    if IS_WINDOWS:
        if shutil.which("winget"):
            print("[compiler] No TeX engine found. Installing MiKTeX via winget...", file=sys.stderr)
            res = subprocess.run(
                ["winget", "install", "--id", "MiKTeX.MiKTeX", "-e", "--silent"],
                check=False,
            )
            if res.returncode == 0:
                return {
                    "ready": True,
                    "engine": "pdflatex",
                    "note": "MiKTeX installed. Restart terminal if PATH has not updated yet.",
                }
        return {
            "ready": False,
            "install_command": "winget install MiKTeX.MiKTeX",
        }

    # --- Linux / WSL: return actionable apt command ---
    if IS_LINUX:
        return {
            "ready": False,
            "install_command": (
                "sudo apt update && "
                "sudo apt install -y latexmk texlive-latex-recommended "
                "texlive-latex-extra texlive-fonts-recommended"
            ),
        }

    return {"ready": False, "install_command": "Install TeX Live or MiKTeX manually."}


# ---------------------------------------------------------------------------
# Missing-package installation
# ---------------------------------------------------------------------------

def install_missing_sty(package_name: str) -> bool:
    """Install a missing LaTeX package via tlmgr (TeX Live) or mpm (MiKTeX)."""
    pkg = re.sub(r"\.(sty|cls|def|clo)$", "", package_name)

    # TeX Live
    if shutil.which("tlmgr"):
        res = subprocess.run(
            ["tlmgr", "install", pkg],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return res.returncode == 0

    # MiKTeX (Windows)
    if shutil.which("mpm"):
        res = subprocess.run(
            ["mpm", f"--install={pkg}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return res.returncode == 0

    return False


# ---------------------------------------------------------------------------
# Log parsing helpers
# ---------------------------------------------------------------------------

def parse_log(output: str) -> dict:
    """Extract structured diagnostics from a raw TeX log string."""
    # file:line: error message (file-line-error format)
    raw_errors = re.findall(r"^(.+?):(\d+):\s*(.+)$", output, re.MULTILINE)

    # Missing style/class files
    missing_files = re.findall(
        r"! LaTeX Error: File `(.+?)' not found", output
    )

    # Undefined references / citations (warnings, non-fatal)
    undefined_refs = re.findall(
        r"LaTeX Warning: Reference `(.+?)' on page", output
    )
    undefined_cites = re.findall(
        r"LaTeX Warning: Citation `(.+?)' on page", output
    )

    # Overfull / underfull hboxes (layout warnings)
    overfull = len(re.findall(r"Overfull \\hbox", output))
    underfull = len(re.findall(r"Underfull \\hbox", output))

    return {
        "errors": [
            {"file": e[0], "line": int(e[1]), "message": e[2].strip()}
            for e in raw_errors[:10]          # cap at 10 to avoid noise
        ],
        "missing_packages": sorted(set(missing_files)),
        "undefined_references": sorted(set(undefined_refs)),
        "undefined_citations": sorted(set(undefined_cites)),
        "layout_warnings": {"overfull_hbox": overfull, "underfull_hbox": underfull},
    }


# ---------------------------------------------------------------------------
# Core compilation
# ---------------------------------------------------------------------------

def compile_document(tex_path: Path, auto_fix_packages: bool = True) -> dict:
    """
    Compile *tex_path* to PDF.

    Parameters
    ----------
    tex_path : Path
        Absolute or relative path to the root .tex file.
    auto_fix_packages : bool
        When True (default), attempt to install missing packages and recompile
        once automatically before returning a FAILED result.

    Returns
    -------
    dict
        Structured JSON-serialisable result with status, pdf_path, errors, etc.
    """
    engine_check = check_or_install_engine()
    if not engine_check["ready"]:
        return {"status": "ENGINE_MISSING", "action_required": engine_check}

    work_dir = tex_path.parent.resolve()
    tex_file = tex_path.name
    engine = engine_check["engine"]

    # Build compiler command
    if engine == "latexmk":
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-file-line-error", tex_file]
    elif IS_WINDOWS:
        # MiKTeX: --enable-installer pulls missing .sty on the fly
        cmd = [
            "pdflatex",
            "-interaction=nonstopmode",
            "-file-line-error",
            "--enable-installer",
            tex_file,
        ]
    else:
        cmd = ["pdflatex", "-interaction=nonstopmode", "-file-line-error", tex_file]

    try:
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
        output = proc.stdout
        pdf_path = work_dir / (tex_path.stem + ".pdf")
        success = proc.returncode == 0 and pdf_path.exists()

        diagnostics = parse_log(output)

        # Auto-fix missing packages then recompile (one pass only)
        if diagnostics["missing_packages"] and auto_fix_packages:
            installed_any = any(
                install_missing_sty(f) for f in diagnostics["missing_packages"]
            )
            if installed_any:
                return compile_document(tex_path, auto_fix_packages=False)

        result = {
            "status": "SUCCESS" if success else "FAILED",
            "pdf_generated": pdf_path.exists(),
            "pdf_path": str(pdf_path) if pdf_path.exists() else None,
            "engine": engine,
            **diagnostics,
        }

        # Append raw log tail only on failure to aid debugging
        if not success:
            result["raw_log_tail"] = "\n".join(output.splitlines()[-30:])

        return result

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "Build took longer than 180 seconds."}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean LaTeX compilation diagnostic engine"
    )
    parser.add_argument(
        "--tex",
        required=True,
        help="Path to the root .tex file (absolute or relative to CWD)",
    )
    parser.add_argument(
        "--no-auto-fix",
        action="store_true",
        help="Disable automatic package installation on missing .sty errors",
    )
    args = parser.parse_args()

    target = Path(args.tex)
    if not target.exists():
        print(json.dumps({"status": "FILE_NOT_FOUND", "path": str(target)}, indent=2))
        sys.exit(1)

    result = compile_document(target, auto_fix_packages=not args.no_auto_fix)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["status"] == "SUCCESS" else 1)
