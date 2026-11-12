"""
scifi.latex.compiler — Clean LaTeX compilation engine and log diagnostics parser.

Pure library module providing:
- check_engine(): inspects available LaTeX engines (latexmk, pdflatex)
- parse_log(): extracts structured errors, warnings, and missing packages from TeX logs
- compile_latex(): executes compilation with diagnostic analysis
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path


def check_engine() -> dict:
    """
    Check if latexmk or pdflatex is available in the current environment.

    Returns:
        dict: {"ready": bool, "engine": str | None, "hint": str | None}
    """
    has_latexmk = shutil.which("latexmk") is not None
    has_pdflatex = shutil.which("pdflatex") is not None

    if has_latexmk:
        return {"ready": True, "engine": "latexmk", "hint": None}
    if has_pdflatex:
        return {"ready": True, "engine": "pdflatex", "hint": None}

    system = platform.system()
    if system == "Windows":
        hint = "Install MiKTeX via 'winget install MiKTeX.MiKTeX' or install TeX Live."
    elif system == "Linux":
        hint = "Install TeX Live via 'sudo apt update && sudo apt install -y latexmk texlive-latex-recommended texlive-latex-extra'."
    elif system == "Darwin":
        hint = "Install MacTeX via 'brew install --cask mactex' or BasicTeX."
    else:
        hint = "Install TeX Live or MiKTeX."

    return {
        "ready": False,
        "engine": None,
        "hint": hint,
    }


def parse_log(log_text: str) -> dict:
    """
    Extract structured diagnostics from raw LaTeX log output.

    Identifies:
    - fatal errors (file, line, message, error_type)
    - missing packages (.sty or .cls files)
    - undefined references and citations
    - layout warnings (overfull / underfull hboxes)
    - total warnings count

    Args:
        log_text: The full string output or log from a LaTeX compilation pass.

    Returns:
        dict containing parsed errors, missing packages, warnings, and layout issues.
    """
    errors: list[dict] = []
    seen_error_messages: set[str] = set()

    # 1. file:line: error message (file-line-error format)
    # e.g., "./main.tex:42: Undefined control sequence." or "doc.tex:15: LaTeX Error: ..."
    file_line_matches = re.finditer(
        r"^([^\n\r:]+?):(\d+):\s*(.+)$",
        log_text,
        re.MULTILINE,
    )
    for m in file_line_matches:
        f_name, l_num, msg = m.group(1).strip(), int(m.group(2)), m.group(3).strip()
        # Classify error type
        if "LaTeX Error" in msg:
            error_type = "LaTeX Error"
        elif "Package" in msg and "Error" in msg:
            error_type = "Package Error"
        elif "Undefined control sequence" in msg:
            error_type = "Undefined control sequence"
        elif "Emergency stop" in msg:
            error_type = "Emergency stop"
        else:
            error_type = "Fatal Error"

        error_entry = {
            "file": f_name,
            "line": l_num,
            "message": msg,
            "error_type": error_type,
        }
        errors.append(error_entry)
        seen_error_messages.add(msg)

    # 2. Standalone TeX errors prefixed with '! ' (e.g. "! LaTeX Error: File 'foo.sty' not found.")
    bang_matches = re.finditer(r"^!\s*(.+)$", log_text, re.MULTILINE)
    for bm in bang_matches:
        full_msg = bm.group(1).strip()
        # Avoid duplicating errors already matched with file and line
        if any(full_msg in seen or seen in full_msg for seen in seen_error_messages):
            continue

        if ":" in full_msg:
            err_type_part, msg_part = full_msg.split(":", 1)
            err_type = err_type_part.strip()
            err_msg = msg_part.strip()
        else:
            err_type = "Fatal Error"
            err_msg = full_msg

        errors.append(
            {
                "file": None,
                "line": None,
                "message": err_msg or full_msg,
                "error_type": err_type,
            }
        )
        seen_error_messages.add(full_msg)

    # 3. Missing packages (.sty, .cls, .def, etc.)
    missing_packages_raw = re.findall(
        r"(?:LaTeX Error: File|File)\s*[`']([^`'\n\r]+?\.(?:sty|cls|def|clo))['`]\s*not found",
        log_text,
    )
    # Also catch general "! LaTeX Error: File `...' not found"
    missing_general = re.findall(
        r"! LaTeX Error: File\s*[`']([^`'\n\r]+)['`]\s*not found",
        log_text,
    )
    missing_packages = sorted(set(missing_packages_raw + missing_general))

    # 4. Undefined references and citations
    undefined_refs = sorted(
        set(
            re.findall(
                r"LaTeX Warning:\s*Reference\s*[`']([^`'\n\r]+)['`]\s*on page",
                log_text,
            )
        )
    )
    undefined_cites = sorted(
        set(
            re.findall(
                r"LaTeX Warning:\s*Citation\s*[`']([^`'\n\r]+)['`]\s*on page",
                log_text,
            )
        )
    )

    # 5. Layout warnings
    overfull = len(re.findall(r"Overfull \\hbox", log_text))
    underfull = len(re.findall(r"Underfull \\hbox", log_text))

    # 6. Overall warnings count
    general_warnings = len(re.findall(r"(?:LaTeX|Package\s+\S+)\s+Warning:", log_text))
    total_warnings = general_warnings + overfull + underfull

    return {
        "errors": errors[:25],
        "missing_packages": missing_packages,
        "undefined_references": undefined_refs,
        "undefined_citations": undefined_cites,
        "warnings_count": total_warnings,
        "layout_warnings": {
            "overfull_hbox": overfull,
            "underfull_hbox": underfull,
        },
    }


def compile_latex(
    entrypoint: str | Path,
    engine: str = "latexmk",
    clean: bool = True,
) -> dict:
    """
    Compile a LaTeX document and return structured diagnostic analysis.

    Args:
        entrypoint: Path to the .tex source file.
        engine: Preferred compiler engine ("latexmk" or "pdflatex"). Defaults to "latexmk".
        clean: Whether to clean auxiliary files after successful compilation.

    Returns:
        dict: Structured compilation result with status, errors, and diagnostics.
    """
    entry_path = Path(entrypoint)
    if not entry_path.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {entrypoint}",
        }

    # Verify compiler availability
    target_engine = engine
    if not shutil.which(target_engine):
        # Fall back from latexmk to pdflatex if available
        if engine == "latexmk" and shutil.which("pdflatex"):
            target_engine = "pdflatex"
        else:
            engine_info = check_engine()
            hint = engine_info.get("hint") or f"Compiler '{engine}' is not installed or not in PATH."
            return {
                "status": "COMPILER_NOT_FOUND",
                "hint": hint,
            }

    work_dir = entry_path.resolve().parent
    tex_file = entry_path.name
    pdf_path = work_dir / (entry_path.stem + ".pdf")

    # Build command line
    if target_engine == "latexmk":
        cmd = ["latexmk", "-pdf", "-interaction=nonstopmode", "-file-line-error", tex_file]
    elif target_engine == "pdflatex":
        cmd = ["pdflatex", "-interaction=nonstopmode", "-file-line-error", tex_file]
    else:
        cmd = [target_engine, "-interaction=nonstopmode", "-file-line-error", tex_file]

    try:
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
        output = proc.stdout or ""
        pdf_exists = pdf_path.exists()
        success = (proc.returncode == 0) and pdf_exists
        diagnostics = parse_log(output)

        if clean and success:
            if target_engine == "latexmk" and shutil.which("latexmk"):
                try:
                    subprocess.run(
                        ["latexmk", "-c", tex_file],
                        cwd=work_dir,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                except Exception:
                    pass
            else:
                for ext in [".aux", ".fls", ".fdb_latexmk", ".out", ".toc", ".nav", ".snm", ".vrb", ".bbl", ".blg"]:
                    aux_file = work_dir / (entry_path.stem + ext)
                    try:
                        if aux_file.exists():
                            aux_file.unlink()
                    except OSError:
                        pass

        if success:
            return {
                "status": "SUCCESS",
                "pdf_generated": True,
                "pdf_path": str(pdf_path),
                "engine": target_engine,
                "log": output,
                **diagnostics,
            }

        return {
            "status": "COMPILATION_ERROR",
            "pdf_generated": pdf_exists,
            "pdf_path": str(pdf_path) if pdf_exists else None,
            "engine": target_engine,
            "log": output,
            "raw_log_tail": "\n".join(output.splitlines()[-30:]),
            **diagnostics,
        }

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "Build took longer than 180 seconds."}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc)}
