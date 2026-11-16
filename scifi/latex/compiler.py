"""
scifi.latex.compiler — Clean LaTeX compilation engine, cached toolchain discovery, and log diagnostics parser.

Provides:
- discover_tex_toolchain(): locates MiKTeX / TeX Live / TinyTeX / MacTeX binaries (even off-PATH) and caches bin_dir
- check_engine(): inspects available LaTeX engines, distribution, version, and binary paths
- parse_log(): extracts structured errors, warnings, and missing packages from TeX logs
- compile_latex(): executes compilation with diagnostic analysis, timing, compiler metadata, and optional PDF rendering
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

_KNOWN_TEX_ENGINES = ("latexmk", "pdflatex", "xelatex", "lualatex")
_TOOLCHAIN_BINARIES = ("latexmk", "pdflatex", "xelatex", "lualatex", "bibtex", "biber", "pdftoppm", "latexdiff")


def _exe_name(name: str) -> str:
    if platform.system() == "Windows" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


def _install_hint() -> str:
    system = platform.system()
    if system == "Windows":
        return "Install MiKTeX via 'winget install MiKTeX.MiKTeX' or install TeX Live."
    if system == "Linux":
        return (
            "Install TeX Live via 'sudo apt update && sudo apt install -y "
            "latexmk texlive-latex-recommended texlive-latex-extra'."
        )
    if system == "Darwin":
        return "Install MacTeX via 'brew install --cask mactex' or BasicTeX."
    return "Install TeX Live or MiKTeX."


def _candidate_tex_bin_dirs(workspace_dir: Path | str | None = None) -> list[tuple[Path, bool]]:
    """Return ordered list of (candidate_dir, is_cached) to search for TeX binaries."""
    candidates: list[tuple[Path, bool]] = []
    seen: set[str] = set()

    def _add(p: Path | str | None, cached: bool = False) -> None:
        if not p:
            return
        path_obj = Path(p)
        key = str(path_obj).lower()
        if key not in seen and path_obj.is_dir():
            seen.add(key)
            candidates.append((path_obj, cached))

    # 1. Explicit env var
    _add(os.environ.get("SCIFI_LATEX_BIN_DIR"), cached=True)

    # 2. Cached / configured path from ~/.scifi/config.json or scifi.toml
    try:
        from scifi.config import resolve_config

        cfg = resolve_config(workspace_dir=workspace_dir)
        _add(cfg.latex_bin_dir, cached=True)
    except Exception:
        pass

    # 3. Standard OS installation paths
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        local_app = Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local"))
        roaming_app = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        prog_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        prog_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))

        _add(local_app / "Programs" / "MiKTeX" / "miktex" / "bin" / "x64")
        _add(prog_files / "MiKTeX" / "miktex" / "bin" / "x64")
        _add(prog_files / "MiKTeX 2.9" / "miktex" / "bin" / "x64")
        _add(prog_files_x86 / "MiKTeX" / "miktex" / "bin")
        _add(roaming_app / "TinyTeX" / "bin" / "windows")
        _add(local_app / "TinyTeX" / "bin" / "windows")
        _add(home / "scoop" / "apps" / "miktex" / "current" / "texmfs" / "install" / "miktex" / "bin" / "x64")
        _add(home / "scoop" / "shims")

        # TeX Live C:\texlive\<year>\bin\windows (newest year first)
        texlive_root = Path(r"C:\texlive")
        if texlive_root.is_dir():
            for year_dir in sorted(texlive_root.iterdir(), reverse=True):
                if year_dir.is_dir() and year_dir.name.isdigit():
                    _add(year_dir / "bin" / "windows")
                    _add(year_dir / "bin" / "win32")

    elif system == "Darwin":
        _add("/Library/TeX/texbin")
        _add(home / "Library" / "TinyTeX" / "bin" / "universal-darwin")
        texlive_root = Path("/usr/local/texlive")
        if texlive_root.is_dir():
            for year_dir in sorted(texlive_root.iterdir(), reverse=True):
                if year_dir.is_dir() and year_dir.name.isdigit():
                    _add(year_dir / "bin" / "universal-darwin")
        _add("/opt/homebrew/bin")
        _add("/usr/local/bin")

    else:
        texlive_root = Path("/usr/local/texlive")
        if texlive_root.is_dir():
            for year_dir in sorted(texlive_root.iterdir(), reverse=True):
                if year_dir.is_dir() and year_dir.name.isdigit():
                    _add(year_dir / "bin" / "x86_64-linux")
                    _add(year_dir / "bin" / "aarch64-linux")
        _add(home / ".TinyTeX" / "bin" / "x86_64-linux")
        _add(home / ".TinyTeX" / "bin" / "aarch64-linux")
        _add("/usr/bin")
        _add("/usr/local/bin")

    return candidates


def _infer_distribution(bin_path: str | None, version_line: str | None = None) -> str:
    """Infer TeX distribution name from binary path or version string."""
    combined = f"{bin_path or ''} {version_line or ''}".lower()
    if "miktex" in combined:
        return "MiKTeX"
    if "tinytex" in combined:
        return "TinyTeX"
    if "texlive" in combined or "tex live" in combined:
        return "TeX Live"
    if "mactex" in combined or "/library/tex" in combined:
        return "MacTeX"
    if "tectonic" in combined:
        return "Tectonic"
    return "TeX"


def _query_version_line(binary_path: str) -> str | None:
    """Run `<binary> --version` and return the first non-empty line."""
    try:
        proc = subprocess.run(
            [binary_path, "--version"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=4,
        )
        for line in (proc.stdout or "").splitlines():
            line = line.strip()
            if line and not line.startswith("Initial Win CP"):
                return line
    except Exception:
        pass
    return None


def _persist_bin_dir(bin_dir: str) -> None:
    """Cache discovered TeX bin_dir into ~/.scifi/config.json if not already saved."""
    try:
        from scifi.config import load_global_config, set_global_config_value

        existing = load_global_config().get("latex_bin_dir")
        if not existing:
            set_global_config_value("latex_bin_dir", bin_dir)
    except Exception:
        pass


def discover_tex_toolchain(
    workspace_dir: Path | str | None = None,
    persist_cache: bool = True,
) -> dict[str, Any]:
    """
    Discover the installed LaTeX toolchain (on PATH, cached in config, or in standard OS paths).

    Returns:
        dict with ready, engine, engine_path, bin_dir, distribution, version, available_engines, cached, hint.
    """
    available: dict[str, str] = {}
    cached = False

    # 1. Check current PATH first
    for tool in _TOOLCHAIN_BINARIES:
        found = shutil.which(tool)
        if found:
            available[tool] = found

    primary_engine = next((eng for eng in ("latexmk", "pdflatex", "xelatex", "lualatex") if eng in available), None)
    resolved_bin_dir: str | None = str(Path(available[primary_engine]).parent) if primary_engine else None

    # 2. If primary engine not on PATH, check cached & standard OS locations
    if not primary_engine:
        for cand_dir, is_cached in _candidate_tex_bin_dirs(workspace_dir=workspace_dir):
            found_in_dir: dict[str, str] = {}
            for tool in _TOOLCHAIN_BINARIES:
                exe = cand_dir / _exe_name(tool)
                if exe.is_file():
                    found_in_dir[tool] = str(exe)
                elif (cand_dir / tool).is_file():
                    found_in_dir[tool] = str(cand_dir / tool)

            if any(eng in found_in_dir for eng in _KNOWN_TEX_ENGINES):
                available.update(found_in_dir)
                primary_engine = next(
                    (eng for eng in ("latexmk", "pdflatex", "xelatex", "lualatex") if eng in available),
                    None,
                )
                resolved_bin_dir = str(cand_dir)
                cached = is_cached
                if persist_cache and not is_cached:
                    _persist_bin_dir(resolved_bin_dir)
                break

    if not primary_engine:
        return {
            "ready": False,
            "engine": None,
            "engine_path": None,
            "bin_dir": None,
            "distribution": None,
            "version": None,
            "available_engines": available,
            "cached": False,
            "hint": _install_hint(),
        }

    engine_path = available[primary_engine]
    version_line = _query_version_line(engine_path)
    distribution = _infer_distribution(engine_path, version_line)

    return {
        "ready": True,
        "engine": primary_engine,
        "engine_path": engine_path,
        "bin_dir": resolved_bin_dir,
        "distribution": distribution,
        "version": version_line,
        "available_engines": available,
        "cached": cached,
        "hint": None,
    }


def check_engine(workspace_dir: Path | str | None = None) -> dict[str, Any]:
    """
    Check if a LaTeX compiler (latexmk, pdflatex, xelatex, lualatex) is available.

    Returns:
        dict: {"ready": bool, "engine": str | None, "hint": str | None, ...}
    """
    return discover_tex_toolchain(workspace_dir=workspace_dir)


def parse_log(log_text: str) -> dict[str, Any]:
    """
    Extract structured diagnostics from raw LaTeX log output.

    Identifies:
    - fatal errors (file, line, message, error_type)
    - missing packages (.sty or .cls files)
    - undefined references and citations
    - layout warnings (overfull / underfull hboxes)
    - total warnings count
    """
    errors: list[dict[str, Any]] = []
    seen_error_messages: set[str] = set()

    # 1. file:line: error message (file-line-error format)
    file_line_matches = re.finditer(
        r"^([^\n\r:]+?):(\d+):\s*(.+)$",
        log_text,
        re.MULTILINE,
    )
    for m in file_line_matches:
        f_name, l_num, msg = m.group(1).strip(), int(m.group(2)), m.group(3).strip()
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

        errors.append(
            {
                "file": f_name,
                "line": l_num,
                "message": msg,
                "error_type": error_type,
            }
        )
        seen_error_messages.add(msg)

    # 2. Standalone TeX errors prefixed with '! '
    bang_matches = re.finditer(r"^!\s*(.+)$", log_text, re.MULTILINE)
    for bm in bang_matches:
        full_msg = bm.group(1).strip()
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


def _detect_needs_unicode_engine(entry_path: Path) -> str | None:
    """Return 'xelatex' if the preamble explicitly loads fontspec or unicode-math."""
    try:
        head = entry_path.read_text(encoding="utf-8", errors="replace")[:5000]
        if re.search(r"\\usepackage(?:\[[^\]]*\])?\{(?:fontspec|unicode-math)\}", head):
            return "xelatex"
    except Exception:
        pass
    return None


def _get_pdf_page_count(pdf_path: Path) -> int | None:
    """Return PDF page count using pypdf if available."""
    try:
        import pypdf

        return len(pypdf.PdfReader(str(pdf_path)).pages)
    except Exception:
        return None


def _build_compile_cmd(
    target_engine: str,
    engine_bin: str,
    tex_file: str,
    unicode_eng: str | None = None,
) -> list[str]:
    """Build the subprocess command list for the selected TeX engine."""
    if target_engine == "latexmk":
        pdf_flag = "-xelatex" if unicode_eng == "xelatex" else "-pdf"
        return [engine_bin, pdf_flag, "-interaction=nonstopmode", "-file-line-error", tex_file]
    return [engine_bin, "-interaction=nonstopmode", "-file-line-error", tex_file]


def _pick_direct_fallback_engine(
    available_engines: dict[str, str],
    unicode_eng: str | None = None,
) -> str | None:
    """Choose a direct TeX engine when latexmk cannot run (e.g. missing Perl on Windows)."""
    if unicode_eng and unicode_eng in available_engines:
        return unicode_eng
    return next((eng for eng in ("pdflatex", "xelatex", "lualatex") if eng in available_engines), None)


def _run_direct_multipass(
    cmd: list[str],
    work_dir: Path,
    stem: str,
    pdf_path: Path,
    available_engines: dict[str, str],
    sub_env: dict[str, str],
    initial_output: str,
    initial_diagnostics: dict[str, Any],
) -> tuple[bool, str, dict[str, Any]]:
    """Run bibtex/biber and up to two follow-up passes so citations and cross-refs settle."""
    output = initial_output
    diagnostics = initial_diagnostics
    success = True

    aux_path = work_dir / f"{stem}.aux"
    bcf_path = work_dir / f"{stem}.bcf"

    if bcf_path.is_file() and "biber" in available_engines:
        subprocess.run(
            [available_engines["biber"], stem],
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            env=sub_env,
            check=False,
        )
    elif diagnostics["undefined_citations"] and "bibtex" in available_engines and aux_path.is_file():
        subprocess.run(
            [available_engines["bibtex"], stem],
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=60,
            env=sub_env,
            check=False,
        )

    for _ in range(2):
        proc_next = subprocess.run(
            cmd,
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            env=sub_env,
        )
        if proc_next.stdout:
            output = proc_next.stdout
            diagnostics = parse_log(output)
        success = (proc_next.returncode == 0) and pdf_path.exists()
        if not success or not (diagnostics["undefined_references"] or diagnostics["undefined_citations"]):
            break

    return success, output, diagnostics


def compile_latex(
    entrypoint: str | Path,
    engine: str = "auto",
    clean: bool = True,
    render_pages: bool = False,
    render_dpi: int = 150,
    max_render_pages: int = 10,
) -> dict[str, Any]:
    """
    Compile a LaTeX document and return structured diagnostic analysis & compiler metadata.

    Args:
        entrypoint: Path to the .tex source file.
        engine: Preferred compiler engine ("latexmk", "pdflatex", "xelatex", "lualatex", or "auto").
        clean: Whether to clean auxiliary files after successful compilation.
        render_pages: If True, render compiled PDF pages to PNG images for visual inspection.
        render_dpi: DPI for rendered page PNGs (default: 150).
        max_render_pages: Maximum number of pages to render when render_pages=True.

    Returns:
        dict: Structured compilation result with status, compiler metadata, errors, and diagnostics.
    """
    entry_path = Path(entrypoint)
    if not entry_path.exists():
        return {
            "status": "ERROR",
            "error_message": f"File not found: {entrypoint}",
        }

    work_dir = entry_path.resolve().parent
    requested_engine = (engine or "auto").strip()

    # Unknown custom engine name (not auto or known TeX engine): only check PATH directly
    if requested_engine != "auto" and requested_engine not in _KNOWN_TEX_ENGINES:
        custom_bin = shutil.which(requested_engine)
        if not custom_bin:
            engine_info = check_engine(workspace_dir=work_dir)
            hint = engine_info.get("hint") or f"Compiler '{requested_engine}' is not installed or not in PATH."
            return {
                "status": "COMPILER_NOT_FOUND",
                "hint": hint,
            }
        target_engine = requested_engine
        engine_bin = custom_bin
        bin_dir = str(Path(custom_bin).parent)
        distribution = _infer_distribution(custom_bin)
        compiler_version = None
        available_engines = {requested_engine: custom_bin}
    else:
        toolchain = discover_tex_toolchain(workspace_dir=work_dir)
        if not toolchain["ready"]:
            return {
                "status": "COMPILER_NOT_FOUND",
                "hint": toolchain.get("hint") or _install_hint(),
            }

        available_engines = toolchain["available_engines"]
        bin_dir = toolchain["bin_dir"]
        distribution = toolchain["distribution"]
        compiler_version = toolchain["version"]

        if requested_engine == "auto":
            unicode_eng = _detect_needs_unicode_engine(entry_path)
            if unicode_eng and "latexmk" in available_engines:
                target_engine = "latexmk"
            elif unicode_eng and unicode_eng in available_engines:
                target_engine = unicode_eng
            elif "latexmk" in available_engines:
                target_engine = "latexmk"
            else:
                target_engine = toolchain["engine"]
        elif requested_engine in available_engines:
            target_engine = requested_engine
        elif requested_engine == "latexmk" and "pdflatex" in available_engines:
            target_engine = "pdflatex"
        else:
            return {
                "status": "COMPILER_NOT_FOUND",
                "hint": f"Requested engine '{requested_engine}' not found. Available: {list(available_engines.keys())}",
            }

        engine_bin = available_engines[target_engine]

    tex_file = entry_path.name
    pdf_path = work_dir / (entry_path.stem + ".pdf")

    unicode_eng = _detect_needs_unicode_engine(entry_path) if requested_engine == "auto" else None
    cmd = _build_compile_cmd(target_engine, engine_bin, tex_file, unicode_eng=unicode_eng)

    # Ensure discovered TeX bin_dir is on subprocess PATH so latexmk/bibtex can spawn sub-tools
    sub_env = os.environ.copy()
    if bin_dir and bin_dir not in sub_env.get("PATH", ""):
        sub_env["PATH"] = f"{bin_dir}{os.pathsep}{sub_env.get('PATH', '')}"

    start_time = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=work_dir,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=120,
            env=sub_env,
        )
        output = proc.stdout or ""
        pdf_exists = pdf_path.exists()
        success = (proc.returncode == 0) and pdf_exists
        diagnostics = parse_log(output)

        # Fallback from latexmk when Perl/script-engine is missing (common with MiKTeX on Windows)
        if not success and not pdf_exists and target_engine == "latexmk":
            lower_out = output.lower()
            if "perl" in lower_out or "script engine" in lower_out:
                fallback_engine = _pick_direct_fallback_engine(available_engines, unicode_eng=unicode_eng)
                if fallback_engine:
                    target_engine = fallback_engine
                    engine_bin = available_engines[fallback_engine]
                    cmd = _build_compile_cmd(target_engine, engine_bin, tex_file)
                    proc = subprocess.run(
                        cmd,
                        cwd=work_dir,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=120,
                        env=sub_env,
                    )
                    output = proc.stdout or ""
                    pdf_exists = pdf_path.exists()
                    success = (proc.returncode == 0) and pdf_exists
                    diagnostics = parse_log(output)

        # If using direct single-pass engine and references/citations are unresolved, run bibtex/biber + follow-up passes
        if (
            success
            and target_engine in ("pdflatex", "xelatex", "lualatex")
            and (diagnostics["undefined_references"] or diagnostics["undefined_citations"])
        ):
            success, output, diagnostics = _run_direct_multipass(
                cmd=cmd,
                work_dir=work_dir,
                stem=entry_path.stem,
                pdf_path=pdf_path,
                available_engines=available_engines,
                sub_env=sub_env,
                initial_output=output,
                initial_diagnostics=diagnostics,
            )
            pdf_exists = pdf_path.exists()

        duration_seconds = round(time.monotonic() - start_time, 2)

        if clean and success:
            latexmk_bin = available_engines.get("latexmk")
            if target_engine == "latexmk" and latexmk_bin:
                try:
                    subprocess.run(
                        [latexmk_bin, "-c", tex_file],
                        cwd=work_dir,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                        env=sub_env,
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
            result: dict[str, Any] = {
                "status": "SUCCESS",
                "pdf_generated": True,
                "pdf_path": str(pdf_path),
                "engine": target_engine,
                "engine_path": engine_bin,
                "distribution": distribution,
                "compiler_version": compiler_version,
                "duration_seconds": duration_seconds,
                "page_count": _get_pdf_page_count(pdf_path),
                "log": output,
                **diagnostics,
            }
            if render_pages:
                from scifi.figures.renderer import render_pdf_pages

                render_res = render_pdf_pages(
                    pdf_path,
                    dpi=render_dpi,
                    max_pages=max_render_pages,
                    extra_bin_dir=bin_dir,
                )
                result["render_status"] = render_res.get("status")
                result["render_backend"] = render_res.get("backend")
                result["rendered_pages"] = render_res.get("rendered_pages", [])
            return result

        return {
            "status": "COMPILATION_ERROR",
            "pdf_generated": pdf_exists,
            "pdf_path": str(pdf_path) if pdf_exists else None,
            "engine": target_engine,
            "engine_path": engine_bin,
            "distribution": distribution,
            "compiler_version": compiler_version,
            "duration_seconds": duration_seconds,
            "log": output,
            "raw_log_tail": "\n".join(output.splitlines()[-30:]),
            **diagnostics,
        }

    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "error": "Build took longer than 120 seconds.", "engine": target_engine}
    except Exception as exc:
        return {"status": "ERROR", "error": str(exc), "engine": target_engine}
