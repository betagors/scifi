"""Local deterministic pixel-level visual checks on rendered PNGs (no VLM API key required)."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Any

import numpy as np


def _load_png_luminance(path: Path) -> np.ndarray | None:
    """Decode an 8-bit PNG into a 2D uint8 grayscale luminance array (0=black, 255=white)."""
    try:
        # Fast C-backed path when Pillow is installed
        try:
            from PIL import Image  # type: ignore[import-not-found]

            with Image.open(path) as img:
                if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                    rgba = img.convert("RGBA")
                    bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                    composited = Image.alpha_composite(bg, rgba).convert("L")
                    return np.asarray(composited, dtype=np.uint8)
                return np.asarray(img.convert("L"), dtype=np.uint8)
        except ImportError:
            pass

        data = path.read_bytes()
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            return None

        pos = 8
        width = height = bit_depth = color_type = 0
        idat_chunks: list[bytes] = []

        while pos + 8 <= len(data):
            length = struct.unpack(">I", data[pos : pos + 4])[0]
            ctype = data[pos + 4 : pos + 8]
            chunk_data = data[pos + 8 : pos + 8 + length]
            pos += 12 + length

            if ctype == b"IHDR" and len(chunk_data) >= 13:
                width, height, bit_depth, color_type, _, _, interlace = struct.unpack(">IIBBBBB", chunk_data[:13])
                if bit_depth != 8 or interlace != 0:
                    return None
            elif ctype == b"IDAT":
                idat_chunks.append(chunk_data)
            elif ctype == b"IEND":
                break

        if width <= 0 or height <= 0 or not idat_chunks:
            return None

        channels_map = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
        channels = channels_map.get(color_type)
        if channels is None or color_type == 3:
            # Skip indexed-palette PNGs to avoid complexity; Pillow handles them above if installed
            return None

        raw = zlib.decompress(b"".join(idat_chunks))
        stride = width * channels
        expected_len = height * (1 + stride)
        if len(raw) < expected_len:
            return None

        arr = np.frombuffer(raw[:expected_len], dtype=np.uint8).reshape((height, 1 + stride))
        filters = arr[:, 0]
        pixels = arr[:, 1:]

        # Reconstruct PNG scanline filters (0=None, 1=Sub, 2=Up, 3=Average, 4=Paeth)
        if np.any(filters != 0):
            # Pure-NumPy fast paths for Sub (1) and Up (2)
            if np.all((filters == 0) | (filters == 1) | (filters == 2)):
                recon = pixels.copy()
                sub_mask = filters == 1
                if np.any(sub_mask):
                    sub_rows = recon[sub_mask].reshape(-1, width, channels)
                    recon[sub_mask] = (
                        (np.cumsum(sub_rows, axis=1, dtype=np.uint16) & 0xFF).astype(np.uint8).reshape(-1, stride)
                    )
                if np.any(filters == 2):
                    for y in range(height):
                        if int(filters[y]) == 2 and y > 0:
                            recon[y] = (recon[y].astype(np.uint16) + recon[y - 1]) & 0xFF
                pixels = recon
            else:
                # Bytearray fallback avoids NumPy scalar-boxing overhead on Average/Paeth
                recon_buf = bytearray(height * stride)
                prev_row = bytearray(stride)
                for y in range(height):
                    f = int(filters[y])
                    row_off = y * stride
                    raw_row = raw[y * (1 + stride) + 1 : y * (1 + stride) + 1 + stride]
                    if f == 0:
                        recon_buf[row_off : row_off + stride] = raw_row
                        prev_row = recon_buf[row_off : row_off + stride]
                    elif f == 1:
                        cur = bytearray(raw_row)
                        for x in range(channels, stride):
                            cur[x] = (cur[x] + cur[x - channels]) & 0xFF
                        recon_buf[row_off : row_off + stride] = cur
                        prev_row = cur
                    elif f == 2:
                        cur = bytearray((raw_row[x] + prev_row[x]) & 0xFF for x in range(stride))
                        recon_buf[row_off : row_off + stride] = cur
                        prev_row = cur
                    elif f == 3:
                        cur = bytearray(raw_row)
                        for x in range(channels):
                            cur[x] = (cur[x] + (prev_row[x] >> 1)) & 0xFF
                        for x in range(channels, stride):
                            cur[x] = (cur[x] + ((cur[x - channels] + prev_row[x]) >> 1)) & 0xFF
                        recon_buf[row_off : row_off + stride] = cur
                        prev_row = cur
                    elif f == 4:
                        cur = bytearray(raw_row)
                        for x in range(channels):
                            cur[x] = (cur[x] + prev_row[x]) & 0xFF
                        for x in range(channels, stride):
                            a = cur[x - channels]
                            b = prev_row[x]
                            c = prev_row[x - channels]
                            p = a + b - c
                            pa = p - a if p >= a else a - p
                            pb = p - b if p >= b else b - p
                            pc = p - c if p >= c else c - p
                            pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                            cur[x] = (cur[x] + pr) & 0xFF
                        recon_buf[row_off : row_off + stride] = cur
                        prev_row = cur
                    else:
                        return None
                pixels = np.frombuffer(recon_buf, dtype=np.uint8).reshape((height, stride))

        img = pixels.reshape((height, width, channels))
        if channels == 1:
            return img[:, :, 0]
        if channels == 2:
            # Grayscale + Alpha: composite over white
            alpha = img[:, :, 1].astype(np.float32) / 255.0
            gray = img[:, :, 0].astype(np.float32)
            return np.clip(gray * alpha + 255.0 * (1.0 - alpha), 0, 255).astype(np.uint8)
        rgb = img[:, :, :3].astype(np.float32)
        lum = 0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2]
        if channels == 4:
            alpha = img[:, :, 3].astype(np.float32) / 255.0
            lum = lum * alpha + 255.0 * (1.0 - alpha)
        return np.clip(lum, 0, 255).astype(np.uint8)
    except Exception:
        return None


def check_figure_edge_clipping(image_path: str | Path, ink_threshold: int = 235) -> dict[str, Any]:
    """
    Detect whether non-white ink pixels touch the outer 1-pixel border of a rendered figure PNG,
    which often indicates a clipped legend, axis label, or tight bounding box.
    """
    p = Path(image_path)
    lum = _load_png_luminance(p)
    if lum is None or lum.shape[0] < 10 or lum.shape[1] < 10:
        return {"clipped": False, "edges": []}

    dark = lum < ink_threshold
    # Ignore solid dark frames if >90% of an entire border is dark (likely a deliberate border box)
    edges: list[str] = []
    checks = {
        "top": float(np.mean(dark[0, :])),
        "bottom": float(np.mean(dark[-1, :])),
        "left": float(np.mean(dark[:, 0])),
        "right": float(np.mean(dark[:, -1])),
    }
    for edge_name, ratio in checks.items():
        if 0.01 < ratio < 0.85:
            edges.append(edge_name)

    return {"clipped": bool(edges), "edges": edges}


def check_page_whitespace(image_path: str | Path, ink_threshold: int = 240) -> dict[str, Any]:
    """
    Measure trailing bottom whitespace and content density on a rendered PDF page PNG.
    """
    p = Path(image_path)
    lum = _load_png_luminance(p)
    if lum is None or lum.shape[0] < 20 or lum.shape[1] < 20:
        return {"analyzed": False}

    h, _w = lum.shape
    dark = lum < ink_threshold
    # Ignore the outer 5% top/bottom header/footer band when finding main body bottom
    top_ignore = max(1, int(h * 0.05))
    bot_ignore = max(top_ignore + 1, int(h * 0.93))
    body_rows = np.any(dark[top_ignore:bot_ignore, :], axis=1)
    if not np.any(body_rows):
        return {"analyzed": True, "bottom_whitespace_ratio": 1.0, "ink_density": 0.0}

    last_ink_row = int(np.where(body_rows)[0][-1]) + top_ignore
    bottom_whitespace_ratio = round(max(0.0, (bot_ignore - last_ink_row) / float(bot_ignore - top_ignore)), 3)
    ink_density = round(float(np.mean(dark)), 4)

    return {
        "analyzed": True,
        "bottom_whitespace_ratio": bottom_whitespace_ratio,
        "ink_density": ink_density,
    }
