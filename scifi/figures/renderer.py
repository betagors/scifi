"""PDF-to-PNG visual rendering engine ('Eyes of SciFi') for multimodal inspection."""

from __future__ import annotations

import os
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any


def _read_png_dimensions(path: Path) -> tuple[int, int]:
    """Read width and height from a PNG IHDR header."""
    try:
        data = path.read_bytes()[:24]
        if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
            return struct.unpack(">II", data[16:24])
    except Exception:
        pass
    return (0, 0)


def _find_pdftoppm(extra_bin_dir: str | Path | None = None) -> str | None:
    """Locate pdftoppm binary on PATH, in extra_bin_dir, or via cached TeX toolchain."""
    found = shutil.which("pdftoppm")
    if found:
        return found

    candidates: list[Path] = []
    if extra_bin_dir:
        candidates.append(Path(extra_bin_dir))

    try:
        from scifi.latex.compiler import discover_tex_toolchain

        tc = discover_tex_toolchain()
        if tc.get("bin_dir"):
            candidates.append(Path(tc["bin_dir"]))
    except Exception:
        pass

    exe_name = "pdftoppm.exe" if os.name == "nt" else "pdftoppm"
    for d in candidates:
        p = d / exe_name
        if p.is_file():
            return str(p)
        p_plain = d / "pdftoppm"
        if p_plain.is_file():
            return str(p_plain)
    return None


def detect_pdf_renderer(extra_bin_dir: str | Path | None = None) -> dict[str, Any]:
    """Detect available PDF-to-image rendering backend."""
    pdftoppm_bin = _find_pdftoppm(extra_bin_dir=extra_bin_dir)
    if pdftoppm_bin:
        return {"available": True, "backend": "pdftoppm", "binary_path": pdftoppm_bin}

    try:
        import fitz  # type: ignore  # noqa: F401

        return {"available": True, "backend": "pymupdf", "binary_path": None}
    except ImportError:
        pass

    try:
        import pypdfium2  # type: ignore  # noqa: F401

        return {"available": True, "backend": "pypdfium2", "binary_path": None}
    except ImportError:
        pass

    return {
        "available": False,
        "backend": None,
        "binary_path": None,
        "hint": "Install poppler (pdftoppm), MiKTeX/TeX Live, or `pip install pymupdf`.",
    }


def _get_pdf_page_count(pdf_path: Path) -> int:
    """Return total page count of a PDF using pypdf."""
    try:
        import pypdf

        reader = pypdf.PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception:
        return 0


def parse_page_spec(
    pages: str | list[int] | None,
    total_pages: int,
    max_pages: int = 12,
) -> list[int]:
    """Parse a page specification (e.g., '1,3-5' or [1, 2]) into sorted 1-based page numbers."""
    if total_pages <= 0:
        return []

    if pages is None:
        return list(range(1, min(total_pages, max_pages) + 1))

    selected: set[int] = set()
    if isinstance(pages, list):
        for p in pages:
            try:
                num = int(p)
                if 1 <= num <= total_pages:
                    selected.add(num)
            except (TypeError, ValueError):
                continue
    elif isinstance(pages, str):
        for part in pages.split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                bounds = part.split("-", 1)
                try:
                    start = max(1, int(bounds[0].strip()))
                    end = min(total_pages, int(bounds[1].strip()))
                    for n in range(start, end + 1):
                        selected.add(n)
                except ValueError:
                    continue
            else:
                try:
                    num = int(part)
                    if 1 <= num <= total_pages:
                        selected.add(num)
                except ValueError:
                    continue

    return sorted(selected)[:max_pages]


def find_figure_pages_in_pdf(pdf_path: str | Path) -> list[int]:
    """Identify 1-based PDF page numbers that appear to contain figures or captions."""
    path = Path(pdf_path)
    if not path.is_file():
        return []
    fig_pages: list[int] = []
    try:
        import pypdf

        reader = pypdf.PdfReader(str(path))
        for idx, page in enumerate(reader.pages, start=1):
            has_xobject_image = False
            try:
                resources = page.get("/Resources")
                if resources and "/XObject" in resources:
                    xobjs = resources["/XObject"].get_object()
                    for key in xobjs:
                        obj = xobjs[key].get_object()
                        if obj.get("/Subtype") in ("/Image", "/Form"):
                            has_xobject_image = True
                            break
            except Exception:
                pass

            text = ""
            try:
                text = page.extract_text() or ""
            except Exception:
                pass

            has_fig_caption = bool(re.search(r"\b(?:Figure|Fig\.)\s*\d+\s*[:.]", text))
            if has_xobject_image or has_fig_caption:
                fig_pages.append(idx)
    except Exception:
        return []
    return fig_pages


def _group_contiguous(pages: list[int]) -> list[tuple[int, int]]:
    """Group sorted page numbers into (start, end) contiguous ranges."""
    if not pages:
        return []
    ranges: list[tuple[int, int]] = []
    start = end = pages[0]
    for p in pages[1:]:
        if p == end + 1:
            end = p
        else:
            ranges.append((start, end))
            start = end = p
    ranges.append((start, end))
    return ranges


def render_pdf_pages(
    pdf_path: str | Path,
    output_dir: str | Path | None = None,
    pages: str | list[int] | None = None,
    dpi: int = 150,
    max_pages: int = 12,
    extra_bin_dir: str | Path | None = None,
    prefix: str | None = None,
) -> dict[str, Any]:
    """
    Render PDF pages into PNG images so multimodal models can visually inspect them.

    Args:
        pdf_path: Path to the PDF file.
        output_dir: Directory where PNGs will be saved (defaults to `<pdf_dir>/.scifi_renders/<stem>`).
        pages: Page numbers or range string (e.g. "1,3-5" or [1, 2]). Defaults to first `max_pages` pages.
        dpi: Rendering resolution in DPI (default: 150 for crisp legible text & plots).
        max_pages: Maximum number of pages to render in one call (default: 12).
        extra_bin_dir: Optional directory containing pdftoppm.
        prefix: Optional filename prefix for generated PNGs.

    Returns:
        dict with status, backend, rendered_pages ([{page, image_path, width, height}]), etc.
    """
    src_pdf = Path(pdf_path)
    if not src_pdf.is_file():
        return {"status": "ERROR", "error_message": f"PDF file not found: {pdf_path}"}

    renderer = detect_pdf_renderer(extra_bin_dir=extra_bin_dir)
    if not renderer["available"]:
        return {
            "status": "RENDERER_NOT_FOUND",
            "pdf_path": str(src_pdf.resolve()),
            "hint": renderer.get("hint", "No PDF renderer available."),
            "rendered_pages": [],
        }

    total_pages = _get_pdf_page_count(src_pdf)
    if total_pages <= 0:
        # Fallback to page 1 if pypdf couldn't read page count
        target_pages = [1] if pages is None else parse_page_spec(pages, 100, max_pages=max_pages)
    else:
        target_pages = parse_page_spec(pages, total_pages, max_pages=max_pages)

    if not target_pages:
        return {
            "status": "ERROR",
            "error_message": f"No valid pages selected (total_pages={total_pages}, pages={pages!r}).",
            "rendered_pages": [],
        }

    out_dir = Path(output_dir) if output_dir else (src_pdf.parent / ".scifi_renders" / src_pdf.stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    file_prefix = prefix or f"{src_pdf.stem}_page"
    backend = renderer["backend"]
    rendered: list[dict[str, Any]] = []

    try:
        if backend == "pdftoppm":
            bin_path = renderer["binary_path"]
            env = os.environ.copy()
            bin_parent = str(Path(bin_path).parent)
            if bin_parent not in env.get("PATH", ""):
                env["PATH"] = f"{bin_parent}{os.pathsep}{env.get('PATH', '')}"

            for start, end in _group_contiguous(target_pages):
                out_prefix = out_dir / file_prefix
                cmd = [
                    bin_path,
                    "-png",
                    "-r",
                    str(dpi),
                    "-f",
                    str(start),
                    "-l",
                    str(end),
                    str(src_pdf),
                    str(out_prefix),
                ]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
                if proc.returncode != 0:
                    return {
                        "status": "ERROR",
                        "backend": backend,
                        "error_message": f"pdftoppm failed: {proc.stderr or proc.stdout}",
                        "rendered_pages": [],
                    }

            # Collect generated files matching <file_prefix>-<page>.png
            for p_num in target_pages:
                # pdftoppm zero-pads depending on total_pages width (e.g. -1.png, -01.png, -001.png)
                candidates = sorted(out_dir.glob(f"{file_prefix}-*{p_num}.png"))
                matched = None
                for c in candidates:
                    suffix_num = c.stem[len(file_prefix) + 1 :]
                    if suffix_num.isdigit() and int(suffix_num) == p_num:
                        matched = c
                        break
                if matched and matched.is_file():
                    w, h = _read_png_dimensions(matched)
                    rendered.append(
                        {
                            "page": p_num,
                            "image_path": str(matched.resolve()),
                            "width": w,
                            "height": h,
                        }
                    )

        elif backend == "pymupdf":
            import fitz  # type: ignore

            doc = fitz.open(str(src_pdf))
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)
            for p_num in target_pages:
                if p_num <= len(doc):
                    page = doc[p_num - 1]
                    pix = page.get_pixmap(matrix=mat)
                    out_file = out_dir / f"{file_prefix}-{p_num:03d}.png"
                    pix.save(str(out_file))
                    rendered.append(
                        {
                            "page": p_num,
                            "image_path": str(out_file.resolve()),
                            "width": pix.width,
                            "height": pix.height,
                        }
                    )

        elif backend == "pypdfium2":
            import pypdfium2 as pdfium  # type: ignore

            pdf = pdfium.PdfDocument(str(src_pdf))
            scale = dpi / 72.0
            for p_num in target_pages:
                if p_num <= len(pdf):
                    page = pdf[p_num - 1]
                    pil_image = page.render(scale=scale).to_pil()
                    out_file = out_dir / f"{file_prefix}-{p_num:03d}.png"
                    pil_image.save(str(out_file))
                    rendered.append(
                        {
                            "page": p_num,
                            "image_path": str(out_file.resolve()),
                            "width": pil_image.width,
                            "height": pil_image.height,
                        }
                    )

    except Exception as exc:
        return {
            "status": "ERROR",
            "backend": backend,
            "error_message": str(exc),
            "rendered_pages": rendered,
        }

    return {
        "status": "SUCCESS",
        "backend": backend,
        "pdf_path": str(src_pdf.resolve()),
        "output_dir": str(out_dir.resolve()),
        "total_pages": total_pages or len(rendered),
        "dpi": dpi,
        "rendered_pages": rendered,
    }
