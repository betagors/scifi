"""Figure and Visual Accessibility Auditor (da-vinci)."""

from __future__ import annotations

import math
from pathlib import Path
import re
import struct
from typing import Any

from scifi.figures.models import (
    FigureAuditResult,
    FigureIssue,
    FigureIssueCategory,
    FigureSeverity,
    ImageFileInfo,
)
from scifi.latex.project import resolve_latex_project


RE_INCLUDEGRAPHICS = re.compile(
    r"\\includegraphics\*?(?:\[([^\]]*)\])?\s*\{\s*([^}]+?)\s*\}"
)
RE_CAPTION = re.compile(r"\\caption\*?(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
RE_LABEL = re.compile(r"\\label\s*\{\s*([^}]+?)\s*\}")
RE_FIGURE_ENV = re.compile(
    r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", re.DOTALL
)
RE_SUBFIGURE_TAG = re.compile(r"\(([a-z])\)")
RE_TIKZ_RED_GREEN = re.compile(
    r"\\draw\[[^\]]*?(?:red)[^\]]*?\].*?;.*?\\draw\[[^\]]*?(?:green)[^\]]*?\]",
    re.DOTALL | re.IGNORECASE,
)


def parse_image_dimensions_and_dpi(path: Path) -> ImageFileInfo:
    """Parse image dimensions and DPI without external binary dependencies."""
    suffix = path.suffix.lower()
    if suffix in (".pdf", ".eps", ".svg"):
        info = ImageFileInfo(path=path, is_vector=True, format_name=suffix.lstrip("."))
        if suffix == ".pdf":
            try:
                import pypdf

                reader = pypdf.PdfReader(str(path))
                if len(reader.pages) > 0:
                    box = reader.pages[0].mediabox
                    info.width = int(float(box.width))
                    info.height = int(float(box.height))
            except Exception:
                pass
        return info

    if not path.is_file():
        return ImageFileInfo(path=path, format_name=suffix.lstrip("."))

    try:
        data = path.read_bytes()
    except Exception:
        return ImageFileInfo(path=path, format_name=suffix.lstrip("."))

    # Check PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        # IHDR is always first chunk
        width, height = struct.unpack(">II", data[16:24])
        dpi = None
        # Scan for pHYs chunk
        pos = 8
        while pos + 8 < len(data):
            chunk_len = struct.unpack(">I", data[pos : pos + 4])[0]
            chunk_type = data[pos + 4 : pos + 8]
            if chunk_type == b"pHYs" and chunk_len >= 9:
                ppux, ppuy, unit = struct.unpack(
                    ">IIB", data[pos + 8 : pos + 8 + 9]
                )
                if unit == 1:  # 1 meter
                    dpi = round(ppux * 0.0254)
                break
            pos += 12 + chunk_len
        return ImageFileInfo(
            path=path,
            width=width,
            height=height,
            dpi=dpi,
            is_vector=False,
            format_name="png",
        )

    # Check JPEG
    if data.startswith(b"\xff\xd8"):
        pos = 2
        width = 0
        height = 0
        dpi = None
        while pos + 4 < len(data):
            if data[pos] != 0xFF:
                pos += 1
                continue
            marker = data[pos + 1]
            pos += 2
            if marker in (0xD8, 0xD9):  # SOI, EOI
                continue
            length = struct.unpack(">H", data[pos : pos + 2])[0]
            if marker == 0xE0 and length >= 14:  # APP0 JFIF
                identifier = data[pos + 2 : pos + 7]
                if identifier == b"JFIF\x00":
                    density_unit = data[pos + 9]
                    x_density, y_density = struct.unpack(">HH", data[pos + 10 : pos + 14])
                    if density_unit == 1:  # dots per inch
                        dpi = x_density
                    elif density_unit == 2:  # dots per cm
                        dpi = round(x_density * 2.54)
            elif marker in (0xC0, 0xC2):  # SOF0, SOF2
                height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
                break
            pos += length
        return ImageFileInfo(
            path=path,
            width=width,
            height=height,
            dpi=dpi,
            is_vector=False,
            format_name="jpeg",
        )

    return ImageFileInfo(path=path, format_name=suffix.lstrip("."))


def audit_figure_accessibility(tex_path: Path | str, base_dir: Path | str | None = None, min_dpi: int = 300) -> dict[str, Any]:
    """MCP entrypoint returning dict."""
    res = audit_latex_figures(tex_path, base_dir=base_dir, min_dpi=min_dpi)
    return res.to_dict()


def audit_latex_figures(
    tex_path: Path | str,
    base_dir: Path | str | None = None,
    min_dpi: int = 300,
) -> FigureAuditResult:
    """Audit figures in LaTeX manuscript for DPI, vector formats, subfigure parity, and accessibility."""
    target_path = Path(tex_path)
    root_dir = Path(base_dir) if base_dir else (target_path.parent if target_path.exists() else Path.cwd())

    # Load text content
    if target_path.exists():
        try:
            proj = resolve_latex_project(target_path)
            full_text = proj.merged_text
        except Exception:
            full_text = target_path.read_text(encoding="utf-8", errors="replace")
    else:
        full_text = str(tex_path)

    issues: list[FigureIssue] = []
    total_inspected = 0

    # 1. Inspect TikZ plots for colorblind risk
    tikz_blocks = re.findall(r"\\begin\{tikzpicture\}(.*?)\\end\{tikzpicture\}", full_text, re.DOTALL)
    for tb in tikz_blocks:
        total_inspected += 1
        if RE_TIKZ_RED_GREEN.search(tb):
            has_dash = any(kw in tb for kw in ["dashed", "dotted", "dashdotted", "mark="])
            if not has_dash:
                issues.append(
                    FigureIssue(
                        category=FigureIssueCategory.COLORBLIND_RISK,
                        severity=FigureSeverity.WARNING,
                        figure_ref="tikzpicture",
                        message="Simultaneous red and green curves detected without distinct line styles (e.g., dashed, dotted, or marker symbols).",
                        recommendation="Use colorblind-safe palettes (Viridis, ColorBrewer) and differentiate lines using 'dashed' or distinct data markers.",
                    )
                )

    # 2. Inspect Figure environments
    figure_matches = list(RE_FIGURE_ENV.finditer(full_text))
    for fm in figure_matches:
        total_inspected += 1
        f_body = fm.group(2)

        # Extract caption & label
        caption_m = RE_CAPTION.search(f_body)
        caption_text = caption_m.group(1) if caption_m else ""

        label_m = RE_LABEL.search(f_body)
        fig_label = label_m.group(1) if label_m else "unlabeled_figure"

        # Check for subfigures in caption: (a), (b), (c)
        declared_subfigs = RE_SUBFIGURE_TAG.findall(caption_text)
        if declared_subfigs:
            # Text outside of this figure environment, stripped of comments
            raw_outside = full_text[: fm.start()] + full_text[fm.end() :]
            clean_lines = [re.sub(r"(?<!\\)%.*$", "", line) for line in raw_outside.splitlines()]
            outside_text = "\n".join(clean_lines)
            for sf in declared_subfigs:
                # Look for references like (a), Fig. 1(a), fig:loss(a), or \ref{...}(a)
                ref_patterns = [
                    rf"\({sf}\)",
                    rf"\b{fig_label}\({sf}\)",
                    rf"\\ref\{{{fig_label}\}}\s*\({sf}\)",
                    rf"Figure\s*\\ref\{{{fig_label}\}}\s*{sf}\b",
                    rf"Fig\.\s*\\ref\{{{fig_label}\}}\s*{sf}\b",
                ]
                referenced = any(re.search(pat, outside_text, re.IGNORECASE) for pat in ref_patterns)
                if not referenced:
                    issues.append(
                        FigureIssue(
                            category=FigureIssueCategory.UNREFERENCED_SUBFIGURE,
                            severity=FigureSeverity.WARNING,
                            figure_ref=fig_label,
                            message=f"Subfigure ({sf}) declared in caption of '{fig_label}' is never referenced or discussed in manuscript body text.",
                            recommendation=f"Add discussion or explicit cross-reference to ({sf}) in the corresponding section prose.",
                        )
                    )

        # Inspect \includegraphics
        for img_m in RE_INCLUDEGRAPHICS.finditer(f_body):
            img_opts = img_m.group(1) or ""
            img_target = img_m.group(2).strip()

            # Locate file on disk
            img_path = root_dir / img_target
            if not img_path.exists():
                for ext in (".pdf", ".png", ".jpg", ".jpeg", ".eps"):
                    cand = root_dir / f"{img_target}{ext}"
                    if cand.exists():
                        img_path = cand
                        break

            file_info = parse_image_dimensions_and_dpi(img_path)

            # Check raster vs vector for charts/plots
            is_chart_caption = any(
                w in caption_text.lower()
                for w in ["loss", "accuracy", "curve", "plot", "comparison", "convergence", "runtime", "benchmark"]
            )
            if not file_info.is_vector and file_info.format_name in ("png", "jpg", "jpeg") and is_chart_caption:
                issues.append(
                    FigureIssue(
                        category=FigureIssueCategory.RASTER_CHART,
                        severity=FigureSeverity.WARNING,
                        figure_ref=img_target,
                        message=f"Bitmap raster format (.{file_info.format_name}) used for scientific chart/plot '{img_target}'.",
                        recommendation="Export scientific plots and schematics as vector PDF, EPS, or SVG for crisp rendering at all zoom levels.",
                    )
                )

            # Check DPI if raster
            if not file_info.is_vector and file_info.dpi is not None:
                if file_info.dpi < min_dpi:
                    issues.append(
                        FigureIssue(
                            category=FigureIssueCategory.LOW_DPI,
                            severity=FigureSeverity.CRITICAL,
                            figure_ref=img_target,
                            message=f"Image resolution {file_info.dpi} DPI for '{img_target}' is below the required {min_dpi} DPI print threshold.",
                            recommendation=f"Re-export image at $\\ge {min_dpi}$ DPI or use vector format.",
                        )
                    )

    # Calculate clean score
    crit_count = sum(1 for i in issues if i.severity == FigureSeverity.CRITICAL)
    warn_count = sum(1 for i in issues if i.severity == FigureSeverity.WARNING)
    score = max(0, 100 - (crit_count * 20 + warn_count * 5))

    return FigureAuditResult(
        status="SUCCESS",
        total_figures_inspected=total_inspected,
        issues=issues,
        clean_score=score,
    )
