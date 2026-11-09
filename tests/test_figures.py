"""Tests for scifi.figures auditor (da-vinci)."""

from pathlib import Path
import pytest
import struct

from scifi.figures.auditor import (
    audit_figure_accessibility,
    parse_image_dimensions_and_dpi,
    audit_latex_figures,
)
from scifi.figures.models import FigureIssueCategory, FigureSeverity


def create_minimal_png(width: int, height: int, dpi: int | None = None) -> bytes:
    """Generate minimal valid PNG bytes with optional pHYs chunk for DPI."""
    # PNG signature: 89 50 4E 47 0D 0A 1A 0A
    sig = b"\x89PNG\r\n\x1a\n"
    # IHDR chunk: length=13, "IHDR", width(4), height(4), bit_depth(1), color_type(1), compression(1), filter(1), interlace(1), crc(4)
    import zlib
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xffffffff)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc

    phys = b""
    if dpi is not None:
        # 1 inch = 0.0254 meters => ppm = round(dpi / 0.0254)
        ppm = round(dpi / 0.0254)
        phys_data = struct.pack(">IIB", ppm, ppm, 1)  # 1 = unit is meter
        phys_crc = struct.pack(">I", zlib.crc32(b"pHYs" + phys_data) & 0xffffffff)
        phys = struct.pack(">I", 9) + b"pHYs" + phys_data + phys_crc

    # IEND chunk
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xffffffff)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc

    return sig + ihdr + phys + iend


def test_parse_png_header(tmp_path: Path):
    png_file = tmp_path / "test_300dpi.png"
    png_file.write_bytes(create_minimal_png(600, 400, dpi=300))
    info = parse_image_dimensions_and_dpi(png_file)
    assert info.width == 600
    assert info.height == 400
    assert info.dpi == 300
    assert info.is_vector is False


def test_audit_raster_format_and_dpi(tmp_path: Path):
    # Low DPI file
    low_dpi_png = tmp_path / "low_res.png"
    low_dpi_png.write_bytes(create_minimal_png(300, 200, dpi=72))

    tex_content = r"""
    \begin{figure}[t]
        \centering
        \includegraphics[width=0.8\textwidth]{low_res.png}
        \caption{Comparison of training loss curves across epochs.}
        \label{fig:loss}
    \end{figure}
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_figures(tex_path=tex_file, base_dir=tmp_path)
    assert result.status == "SUCCESS"
    assert len(result.issues) >= 1

    categories = [i.category for i in result.issues]
    assert FigureIssueCategory.LOW_DPI in categories or FigureIssueCategory.RASTER_CHART in categories


def test_subfigure_parity_detects_unreferenced(tmp_path: Path):
    tex_content = r"""
    \begin{figure}[t]
        \centering
        \caption{(a) Proposed model architecture, (b) baseline ablation, and (c) extreme delay regime.}
        \label{fig:overview}
    \end{figure}

    In Section 3, we illustrate the overall design in Figure~\ref{fig:overview}(a).
    As confirmed by the ablation in Figure~\ref{fig:overview}(b), our module performs well.
    % Note: subfigure (c) is never referenced in prose!
    """
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_figures(tex_path=tex_file, base_dir=tmp_path)
    unref_issues = [i for i in result.issues if i.category == FigureIssueCategory.UNREFERENCED_SUBFIGURE]
    assert len(unref_issues) == 1
    assert "(c)" in unref_issues[0].message


def test_colorblind_palette_detection(tmp_path: Path):
    tex_content = r"""
    \begin{tikzpicture}
        \draw[red, thick] (0,0) -- (1,1);
        \draw[green, thick] (0,1) -- (1,0);
    \end{tikzpicture}
    """
    tex_file = tmp_path / "plot.tex"
    tex_file.write_text(tex_content, encoding="utf-8")

    result = audit_latex_figures(tex_path=tex_file, base_dir=tmp_path)
    cb_issues = [i for i in result.issues if i.category == FigureIssueCategory.COLORBLIND_RISK]
    assert len(cb_issues) >= 1
