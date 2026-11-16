"""Figure and Visual Accessibility Auditor (da-vinci)."""

from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any

from scifi.abbreviations import find_awkward_algorithm_labels
from scifi.figures.models import (
    FigureAuditResult,
    FigureIssue,
    FigureIssueCategory,
    FigureSeverity,
    ImageFileInfo,
)
from scifi.latex.project import resolve_latex_project

RE_INCLUDEGRAPHICS = re.compile(r"\\includegraphics\*?(?:\[([^\]]*)\])?\s*\{\s*([^}]+?)\s*\}")
RE_CAPTION = re.compile(r"\\caption\*?(?:\[[^\]]*\])?\s*\{((?:[^{}]|\{[^{}]*\})*)\}")
RE_LABEL = re.compile(r"\\label\s*\{\s*([^}]+?)\s*\}")
RE_FIGURE_ENV = re.compile(r"\\begin\{(figure\*?)\}(.*?)\\end\{\1\}", re.DOTALL)
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
                ppux, ppuy, unit = struct.unpack(">IIB", data[pos + 8 : pos + 8 + 9])
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


def audit_figure_accessibility(
    tex_path: Path | str,
    base_dir: Path | str | None = None,
    min_dpi: int = 300,
    render_previews: bool = True,
    pdf_path: Path | str | None = None,
    render_dpi: int = 150,
    vlm_check: bool = False,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> dict[str, Any]:
    """MCP entrypoint returning dict."""
    res = audit_latex_figures(
        tex_path,
        base_dir=base_dir,
        min_dpi=min_dpi,
        render_previews=render_previews,
        pdf_path=pdf_path,
        render_dpi=render_dpi,
        vlm_check=vlm_check,
        vlm_provider=vlm_provider,
        vlm_model=vlm_model,
    )
    return res.to_dict()


def _extract_figure_embedded_text(img_path: Path) -> str:
    """Extract embedded text labels from vector figure assets (.pdf or .svg)."""
    if not img_path.is_file():
        return ""
    suffix = img_path.suffix.lower()
    if suffix == ".svg":
        try:
            raw = img_path.read_text(encoding="utf-8", errors="replace")
            return re.sub(r"<[^>]+>", " ", raw)
        except Exception:
            return ""
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(img_path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    return ""


def _check_figure_label_consistency(text: str, figure_ref: str, source_label: str) -> list[FigureIssue]:
    """Flag invented or compound algorithm/variant labels inside figure text, captions, or diagrams."""
    if not text.strip():
        return []
    invented, compound = find_awkward_algorithm_labels(text)
    found: list[FigureIssue] = []
    for tok in invented:
        found.append(
            FigureIssue(
                category=FigureIssueCategory.LABEL_CONSISTENCY,
                severity=FigureSeverity.WARNING,
                figure_ref=figure_ref,
                message=f"Invented/blended algorithm label '{tok}' found in {source_label} '{figure_ref}'.",
                recommendation=f"Replace '{tok}' in the {source_label} with a simplified, standardized label (e.g., 'L-MAPPO' or 'Proposed') matching the manuscript text and tables.",
            )
        )
    for tok in compound:
        found.append(
            FigureIssue(
                category=FigureIssueCategory.LABEL_CONSISTENCY,
                severity=FigureSeverity.WARNING,
                figure_ref=figure_ref,
                message=f"Compound algorithm variant label '{tok}' found in {source_label} '{figure_ref}'.",
                recommendation=f"Replace '{tok}' in the {source_label} with a descriptive experimental label (e.g., 'MAPPO (safety-filtered)' or 'Proposed (Max-SNR)') matching your tables.",
            )
        )
    return found


def audit_latex_figures(
    tex_path: Path | str,
    base_dir: Path | str | None = None,
    min_dpi: int = 300,
    render_previews: bool = True,
    pdf_path: Path | str | None = None,
    render_dpi: int = 150,
    vlm_check: bool = False,
    vlm_provider: str | None = None,
    vlm_model: str | None = None,
) -> FigureAuditResult:
    """Audit figures in LaTeX manuscript for DPI, vector formats, subfigure parity, and visual previews."""
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
    rendered_previews: list[dict[str, Any]] = []
    seen_preview_sources: set[str] = set()
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
        issues.extend(_check_figure_label_consistency(tb, "tikzpicture", "TikZ diagram"))

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
        issues.extend(_check_figure_label_consistency(caption_text, fig_label, "figure caption"))

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
            img_m.group(1) or ""
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
            if file_info.is_vector and img_path.is_file():
                embedded_txt = _extract_figure_embedded_text(img_path)
                issues.extend(_check_figure_label_consistency(embedded_txt, img_target, "figure asset"))

            # Collect / render visual preview for multimodal inspection
            if render_previews and img_path.is_file():
                src_key = str(img_path.resolve())
                if src_key not in seen_preview_sources:
                    seen_preview_sources.add(src_key)
                    if file_info.format_name in ("png", "jpg", "jpeg"):
                        rendered_previews.append(
                            {
                                "kind": "raster_source",
                                "figure_ref": fig_label,
                                "source_path": src_key,
                                "image_path": src_key,
                                "width": file_info.width,
                                "height": file_info.height,
                            }
                        )
                    elif file_info.format_name == "pdf":
                        from scifi.figures.renderer import render_pdf_pages

                        r_res = render_pdf_pages(
                            img_path,
                            output_dir=root_dir / ".scifi_renders" / "figures",
                            pages=[1],
                            dpi=render_dpi,
                            max_pages=1,
                            prefix=img_path.stem,
                        )
                        for rp in r_res.get("rendered_pages", []):
                            rendered_previews.append(
                                {
                                    "kind": "vector_figure_render",
                                    "figure_ref": fig_label,
                                    "source_path": src_key,
                                    "image_path": rp["image_path"],
                                    "width": rp["width"],
                                    "height": rp["height"],
                                }
                            )

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

    # 3. Render figure-bearing pages from compiled manuscript PDF if available
    if render_previews:
        compiled_pdf = (
            Path(pdf_path) if pdf_path else (target_path.with_suffix(".pdf") if target_path.exists() else None)
        )
        if compiled_pdf and compiled_pdf.is_file():
            from scifi.figures.renderer import find_figure_pages_in_pdf, render_pdf_pages

            fig_pages = find_figure_pages_in_pdf(compiled_pdf)
            if fig_pages:
                pdf_render = render_pdf_pages(
                    compiled_pdf,
                    pages=fig_pages,
                    dpi=render_dpi,
                    max_pages=8,
                )
                for rp in pdf_render.get("rendered_pages", []):
                    rendered_previews.append(
                        {
                            "kind": "compiled_pdf_page",
                            "page": rp["page"],
                            "source_path": str(compiled_pdf.resolve()),
                            "image_path": rp["image_path"],
                            "width": rp["width"],
                            "height": rp["height"],
                        }
                    )

    # 3b. Local pixel-level edge-clipping check on rendered figure PNGs (no API key required)
    if render_previews and rendered_previews:
        from scifi.figures.pixel_checks import check_figure_edge_clipping

        for rp in rendered_previews:
            if rp.get("kind") in ("raster_source", "vector_figure_render") and rp.get("image_path"):
                clip_res = check_figure_edge_clipping(rp["image_path"])
                if clip_res.get("clipped"):
                    edges_str = ", ".join(clip_res["edges"])
                    issues.append(
                        FigureIssue(
                            category=FigureIssueCategory.CLIPPED_CONTENT,
                            severity=FigureSeverity.WARNING,
                            figure_ref=str(rp.get("figure_ref") or Path(rp["image_path"]).name),
                            file_path=rp["image_path"],
                            message=(
                                f"Rendered figure pixels touch the outer {edges_str} border(s), "
                                "indicating a potentially clipped legend, axis label, or tight bounding box."
                            ),
                            recommendation="Re-export with padding (e.g., bbox_inches='tight', pad_inches=0.05) and inspect the PNG.",
                        )
                    )

    # 4. Optional external VLM visual defect inspection (or host-agent checklist when vlm_check=False)
    vlm_inspection: dict[str, Any] = {
        "status": "HOST_AGENT_READY" if rendered_previews else "DISABLED",
        "mode": "host_agent" if not vlm_check else "external_vlm",
        "visual_checklist": [
            "Inspect rendered_previews[*].image_path using read_file / built-in vision.",
            "Check for overlapping tick labels, clipped legends, illegible font sizes, subfigure misalignment, and margin overflow.",
        ]
        if rendered_previews
        else [],
    }
    if vlm_check:
        if not rendered_previews:
            vlm_inspection = {
                "status": "SKIPPED_NO_IMAGES",
                "hint": "No rendered figure or PDF page PNGs available for VLM inspection.",
                "findings": [],
            }
        else:
            from scifi.figures.vlm import inspect_images_with_vlm

            vlm_res = inspect_images_with_vlm(
                rendered_previews,
                mode="figure",
                provider=vlm_provider,
                model=vlm_model,
            )
            vlm_inspection = {k: v for k, v in vlm_res.items() if k != "findings"}
            for finding in vlm_res.get("findings", []):
                raw_cat = str(finding.get("category", "VISUAL_DEFECT")).upper()
                try:
                    cat = FigureIssueCategory(raw_cat)
                except ValueError:
                    cat = FigureIssueCategory.VISUAL_DEFECT
                raw_sev = str(finding.get("severity", "WARNING")).upper()
                try:
                    sev = FigureSeverity(raw_sev)
                except ValueError:
                    sev = FigureSeverity.WARNING
                issues.append(
                    FigureIssue(
                        category=cat,
                        severity=sev,
                        figure_ref=str(finding.get("target") or "visual_preview"),
                        message=f"[VLM] {finding.get('message', 'Visual defect detected.')}",
                        recommendation=str(finding.get("recommendation") or ""),
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
        rendered_previews=rendered_previews,
        vlm_inspection=vlm_inspection,
    )
