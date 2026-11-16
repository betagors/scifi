"""Tests for cached LaTeX toolchain discovery, compiler transparency, and PDF-to-PNG 'Eyes of SciFi'."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

from scifi.figures.auditor import audit_latex_figures
from scifi.figures.renderer import (
    detect_pdf_renderer,
    parse_page_spec,
    render_pdf_pages,
)
from scifi.latex.compiler import check_engine, compile_latex, discover_tex_toolchain


def _make_minimal_png(width: int = 100, height: int = 80) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"


def test_discover_tex_toolchain_off_path_and_caches(monkeypatch, tmp_path: Path):
    """Toolchain discovery finds off-PATH TeX binaries and caches latex_bin_dir to config.json."""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("SCIFI_LATEX_BIN_DIR", raising=False)

    fake_bin_dir = tmp_path / "MiKTeX" / "miktex" / "bin" / "x64"
    fake_bin_dir.mkdir(parents=True)
    for name in ("latexmk.exe", "pdflatex.exe", "pdftoppm.exe", "latexmk", "pdflatex", "pdftoppm"):
        (fake_bin_dir / name).write_bytes(b"")

    monkeypatch.setenv("SCIFI_LATEX_BIN_DIR", str(fake_bin_dir))

    with (
        patch("shutil.which", return_value=None),
        patch("scifi.latex.compiler._query_version_line", return_value="MiKTeX-pdfTeX 4.18"),
    ):
        tc = discover_tex_toolchain(persist_cache=True)

    assert tc["ready"] is True
    assert tc["engine"] == "latexmk"
    assert tc["distribution"] == "MiKTeX"
    assert tc["bin_dir"] == str(fake_bin_dir)
    assert "pdftoppm" in tc["available_engines"]
    assert tc["version"] == "MiKTeX-pdfTeX 4.18"


def test_discover_tex_toolchain_persists_uncached_dir(monkeypatch, tmp_path: Path):
    """When discovered from candidate dirs (not already cached), it persists latex_bin_dir."""
    cfg_path = tmp_path / "config.json"
    monkeypatch.setenv("SCIFI_CONFIG_PATH", str(cfg_path))
    monkeypatch.delenv("SCIFI_LATEX_BIN_DIR", raising=False)

    fake_bin_dir = tmp_path / "texlive" / "2025" / "bin" / "windows"
    fake_bin_dir.mkdir(parents=True)
    for name in ("pdflatex.exe", "pdflatex"):
        (fake_bin_dir / name).write_bytes(b"")

    with (
        patch("shutil.which", return_value=None),
        patch("scifi.latex.compiler._candidate_tex_bin_dirs", return_value=[(fake_bin_dir, False)]),
        patch("scifi.latex.compiler._query_version_line", return_value="TeX Live 2025"),
    ):
        tc = discover_tex_toolchain(persist_cache=True)

    assert tc["ready"] is True
    assert tc["engine"] == "pdflatex"
    assert tc["distribution"] == "TeX Live"
    saved = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert saved["latex_bin_dir"] == str(fake_bin_dir)


def test_compile_latex_reports_compiler_metadata_and_renders(tmp_path: Path):
    """compile_latex returns distribution, engine_path, duration_seconds, and rendered_pages when requested."""
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")
    pdf_file = tmp_path / "paper.pdf"
    rendered_png = tmp_path / "paper_page-1.png"
    rendered_png.write_bytes(_make_minimal_png(200, 300))

    def fake_run(cmd, *args, **kwargs):
        pdf_file.write_bytes(b"%PDF-1.4 mock")
        m = MagicMock()
        m.returncode = 0
        m.stdout = "Output written on paper.pdf (1 page)."
        return m

    fake_tc = {
        "ready": True,
        "engine": "latexmk",
        "engine_path": "/opt/miktex/bin/latexmk",
        "bin_dir": "/opt/miktex/bin",
        "distribution": "MiKTeX",
        "version": "Latexmk 4.85",
        "available_engines": {"latexmk": "/opt/miktex/bin/latexmk", "pdflatex": "/opt/miktex/bin/pdflatex"},
        "cached": True,
        "hint": None,
    }
    fake_render = {
        "status": "SUCCESS",
        "backend": "pdftoppm",
        "rendered_pages": [{"page": 1, "image_path": str(rendered_png), "width": 200, "height": 300}],
    }

    with (
        patch("scifi.latex.compiler.discover_tex_toolchain", return_value=fake_tc),
        patch("subprocess.run", side_effect=fake_run),
        patch("scifi.figures.renderer.render_pdf_pages", return_value=fake_render),
    ):
        res = compile_latex(tex_file, engine="auto", clean=True, render_pages=True)

    assert res["status"] == "SUCCESS"
    assert res["engine"] == "latexmk"
    assert res["engine_path"] == "/opt/miktex/bin/latexmk"
    assert res["distribution"] == "MiKTeX"
    assert res["compiler_version"] == "Latexmk 4.85"
    assert isinstance(res["duration_seconds"], float)
    assert res["render_status"] == "SUCCESS"
    assert res["render_backend"] == "pdftoppm"
    assert len(res["rendered_pages"]) == 1
    assert res["rendered_pages"][0]["image_path"] == str(rendered_png)


def test_parse_page_spec():
    assert parse_page_spec(None, total_pages=5, max_pages=3) == [1, 2, 3]
    assert parse_page_spec("1, 3-5, 2", total_pages=5, max_pages=10) == [1, 2, 3, 4, 5]
    assert parse_page_spec([4, 1, 99], total_pages=5, max_pages=10) == [1, 4]


def test_render_pdf_pages_with_mock_pdftoppm(tmp_path: Path):
    """render_pdf_pages invokes pdftoppm and returns image dimensions."""
    pdf_file = tmp_path / "doc.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 fake")
    out_dir = tmp_path / "renders"

    def fake_pdftoppm(cmd, *args, **kwargs):
        out_prefix = Path(cmd[-1])
        out_prefix.parent.mkdir(parents=True, exist_ok=True)
        (out_prefix.parent / f"{out_prefix.name}-1.png").write_bytes(_make_minimal_png(640, 480))
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    with (
        patch(
            "scifi.figures.renderer.detect_pdf_renderer",
            return_value={"available": True, "backend": "pdftoppm", "binary_path": "/usr/bin/pdftoppm"},
        ),
        patch("scifi.figures.renderer._get_pdf_page_count", return_value=1),
        patch("subprocess.run", side_effect=fake_pdftoppm),
    ):
        res = render_pdf_pages(pdf_file, output_dir=out_dir, pages=[1], dpi=150)

    assert res["status"] == "SUCCESS"
    assert res["backend"] == "pdftoppm"
    assert len(res["rendered_pages"]) == 1
    assert res["rendered_pages"][0]["width"] == 640
    assert res["rendered_pages"][0]["height"] == 480


def test_audit_figures_includes_rendered_previews(tmp_path: Path):
    """audit_latex_figures returns rendered_previews for raster and vector PDF figures."""
    img_png = tmp_path / "arch.png"
    img_png.write_bytes(_make_minimal_png(400, 300))
    fig_pdf = tmp_path / "plot.pdf"
    fig_pdf.write_bytes(b"%PDF-1.4 mock")
    rendered_plot = tmp_path / "plot-1.png"
    rendered_plot.write_bytes(_make_minimal_png(500, 350))

    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        r"""
        \begin{figure}
          \includegraphics{arch.png}
          \caption{System architecture.}
          \label{fig:arch}
        \end{figure}
        \begin{figure}
          \includegraphics{plot.pdf}
          \caption{Training loss curve.}
          \label{fig:loss}
        \end{figure}
        """,
        encoding="utf-8",
    )

    with patch(
        "scifi.figures.renderer.render_pdf_pages",
        return_value={
            "status": "SUCCESS",
            "backend": "pdftoppm",
            "rendered_pages": [{"page": 1, "image_path": str(rendered_plot), "width": 500, "height": 350}],
        },
    ):
        res = audit_latex_figures(tex_file, render_previews=True)

    assert res.total_figures_inspected == 2
    kinds = {p["kind"] for p in res.rendered_previews}
    assert "raster_source" in kinds
    assert "vector_figure_render" in kinds


def test_real_toolchain_and_renderer_if_installed():
    """Smoke-check real check_engine & detect_pdf_renderer without mocking."""
    info = check_engine()
    assert "ready" in info
    assert "available_engines" in info
    renderer = detect_pdf_renderer(extra_bin_dir=info.get("bin_dir"))
    assert "available" in renderer


def test_compile_latex_falls_back_from_latexmk_missing_perl_to_xelatex_multipass(tmp_path: Path):
    """When latexmk fails due to missing Perl on a fontspec doc, compile_latex falls back to xelatex + bibtex + 2 passes."""
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        r"\documentclass{article}\usepackage{fontspec}\begin{document}\cite{foo}\end{document}",
        encoding="utf-8",
    )
    pdf_file = tmp_path / "main.pdf"
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        exe = Path(cmd[0]).stem
        m = MagicMock()
        if exe == "latexmk":
            m.returncode = 1
            m.stdout = "latexmk: The Perl interpreter could not be found."
            return m
        if exe == "xelatex":
            xelatex_pass = sum(1 for c in calls if Path(c[0]).stem == "xelatex")
            pdf_file.write_bytes(b"%PDF-1.4 mock")
            (tmp_path / "main.aux").write_text(r"\citation{foo}", encoding="utf-8")
            m.returncode = 0
            if xelatex_pass == 1:
                m.stdout = "LaTeX Warning: Citation `foo' on page 1 undefined on input line 1."
            elif xelatex_pass == 2:
                m.stdout = "LaTeX Warning: Label(s) may have changed. Rerun to get cross-references right."
                # Simulate unresolved ref still remaining until pass 3
                m.stdout += "\nLaTeX Warning: Reference `sec:intro' on page 1 undefined on input line 1."
            else:
                m.stdout = "Output written on main.pdf (1 page)."
            return m
        if exe == "bibtex":
            m.returncode = 0
            m.stdout = "This is BibTeX"
            return m
        m.returncode = 0
        m.stdout = ""
        return m

    fake_tc = {
        "ready": True,
        "engine": "latexmk",
        "engine_path": "C:/MiKTeX/latexmk.exe",
        "bin_dir": "C:/MiKTeX",
        "distribution": "MiKTeX",
        "version": "MiKTeX",
        "available_engines": {
            "latexmk": "C:/MiKTeX/latexmk.exe",
            "pdflatex": "C:/MiKTeX/pdflatex.exe",
            "xelatex": "C:/MiKTeX/xelatex.exe",
            "bibtex": "C:/MiKTeX/bibtex.exe",
        },
        "cached": True,
        "hint": None,
    }

    with (
        patch("scifi.latex.compiler.discover_tex_toolchain", return_value=fake_tc),
        patch("subprocess.run", side_effect=fake_run),
    ):
        res = compile_latex(tex_file, clean=True)

    assert res["status"] == "SUCCESS"
    assert res["engine"] == "xelatex"
    assert res["undefined_citations"] == []
    assert res["undefined_references"] == []
    assert [Path(c[0]).name for c in calls] == [
        "latexmk.exe",
        "xelatex.exe",
        "bibtex.exe",
        "xelatex.exe",
        "xelatex.exe",
    ]


def test_compile_latex_runs_biber_when_bcf_present(tmp_path: Path):
    """Direct-engine multipass uses biber when a .bcf file exists."""
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(r"\documentclass{article}\begin{document}\cite{bar}\end{document}", encoding="utf-8")
    pdf_file = tmp_path / "main.pdf"
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        exe = Path(cmd[0]).name
        m = MagicMock()
        m.returncode = 0
        if exe == "pdflatex":
            pdf_file.write_bytes(b"%PDF-1.4 mock")
            (tmp_path / "main.bcf").write_text("<bcf/>", encoding="utf-8")
            pdflatex_pass = sum(1 for c in calls if Path(c[0]).name == "pdflatex")
            m.stdout = (
                "LaTeX Warning: Citation `bar' on page 1 undefined on input line 1."
                if pdflatex_pass == 1
                else "Output written on main.pdf (1 page)."
            )
        else:
            m.stdout = "INFO - This is Biber"
        return m

    fake_tc = {
        "ready": True,
        "engine": "pdflatex",
        "engine_path": "/usr/bin/pdflatex",
        "bin_dir": "/usr/bin",
        "distribution": "TeX Live",
        "version": "TeX Live 2025",
        "available_engines": {
            "pdflatex": "/usr/bin/pdflatex",
            "biber": "/usr/bin/biber",
        },
        "cached": True,
        "hint": None,
    }

    with (
        patch("scifi.latex.compiler.discover_tex_toolchain", return_value=fake_tc),
        patch("subprocess.run", side_effect=fake_run),
    ):
        res = compile_latex(tex_file, engine="pdflatex", clean=False)

    assert res["status"] == "SUCCESS"
    assert [Path(c[0]).name for c in calls] == ["pdflatex", "biber", "pdflatex"]


def test_compile_latex_uses_devnull_stdin_and_sub_180s_timeout(tmp_path: Path):
    """Subprocess calls must detach stdin and time out below the 180s MCP deadline."""
    import subprocess

    tex_file = tmp_path / "main.tex"
    tex_file.write_text(r"\documentclass{article}\begin{document}Hi\end{document}", encoding="utf-8")
    seen_kwargs: list[dict] = []

    def fake_run(cmd, *args, **kwargs):
        seen_kwargs.append(kwargs)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 120))

    fake_tc = {
        "ready": True,
        "engine": "pdflatex",
        "engine_path": "/usr/bin/pdflatex",
        "bin_dir": "/usr/bin",
        "distribution": "TeX Live",
        "version": "TeX Live 2025",
        "available_engines": {"pdflatex": "/usr/bin/pdflatex"},
        "cached": True,
        "hint": None,
    }

    with (
        patch("scifi.latex.compiler.discover_tex_toolchain", return_value=fake_tc),
        patch("subprocess.run", side_effect=fake_run),
    ):
        res = compile_latex(tex_file, engine="pdflatex", clean=False)

    assert res["status"] == "TIMEOUT"
    assert seen_kwargs
    assert seen_kwargs[0].get("stdin") is subprocess.DEVNULL
    assert seen_kwargs[0].get("timeout", 999) < 180
