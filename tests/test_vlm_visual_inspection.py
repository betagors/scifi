"""Tests for VLM visual PDF & figure inspection in da-vinci (`sf figures`) and layout (`sf trim`)."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

from scifi.cli import main as cli_main
from scifi.figures.auditor import audit_latex_figures
from scifi.figures.models import FigureIssueCategory, FigureSeverity
from scifi.figures.vlm import inspect_images_with_vlm, resolve_vlm_config
from scifi.layout.models import TrimSuggestionType
from scifi.layout.trim import audit_trim_budget


def _make_minimal_png(width: int = 300, height: int = 200) -> bytes:
    """Create a valid minimal 1-bit grayscale PNG for testing."""

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw_scanline = b"\x00" + b"\xff" * width
    idat = zlib.compress(raw_scanline * height)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def test_resolve_vlm_config_no_key(monkeypatch):
    for var in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SCIFI_VLM_API_KEY",
        "SCIFI_VLM_PROVIDER",
        "SCIFI_VLM_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    cfg = resolve_vlm_config()
    assert cfg["available"] is False
    assert "No VLM API key" in cfg["hint"]


def test_resolve_vlm_config_auto_providers(monkeypatch):
    for var in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SCIFI_VLM_API_KEY",
        "SCIFI_VLM_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)

    monkeypatch.setenv("GEMINI_API_KEY", "gem-test-key")
    cfg = resolve_vlm_config()
    assert cfg["available"] is True
    assert cfg["provider"] == "gemini"
    assert cfg["model"] == "gemini-2.5-flash"

    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("OPENAI_API_KEY", "oai-test-key")
    cfg = resolve_vlm_config()
    assert cfg["available"] is True
    assert cfg["provider"] == "openai"
    assert cfg["model"] == "gpt-4o"

    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant-test-key")
    cfg = resolve_vlm_config()
    assert cfg["available"] is True
    assert cfg["provider"] == "anthropic"


def test_inspect_images_with_vlm_skips_without_key(tmp_path: Path, monkeypatch):
    for var in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SCIFI_VLM_API_KEY",
        "SCIFI_VLM_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)
    img = tmp_path / "fig1.png"
    img.write_bytes(_make_minimal_png())
    res = inspect_images_with_vlm([{"image_path": str(img), "figure_ref": "fig:1"}], mode="figure")
    assert res["status"] == "SKIPPED_NO_API_KEY"
    assert res["findings"] == []


def test_inspect_images_with_vlm_gemini_mock(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    img = tmp_path / "plot.png"
    img.write_bytes(_make_minimal_png())

    vlm_payload = [
        {
            "category": "CLIPPED_CONTENT",
            "severity": "CRITICAL",
            "target": "fig:loss",
            "message": "Legend on the right edge is clipped by the plot bounding box.",
            "recommendation": "Use bbox_inches='tight' when exporting the figure.",
        }
    ]
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": f"```json\n{json.dumps(vlm_payload)}\n```"}]}}]
    }

    with patch("scifi.figures.vlm.requests.post", return_value=mock_resp) as post_mock:
        res = inspect_images_with_vlm([{"image_path": str(img), "figure_ref": "fig:loss"}], mode="figure")

    assert res["status"] == "SUCCESS"
    assert res["provider"] == "gemini"
    assert res["images_inspected"] == 1
    assert len(res["findings"]) == 1
    assert res["findings"][0]["category"] == "CLIPPED_CONTENT"
    assert post_mock.called


def test_audit_latex_figures_with_vlm_check(tmp_path: Path):
    img_png = tmp_path / "arch.png"
    img_png.write_bytes(_make_minimal_png(400, 300))

    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        r"""
        \begin{figure}
          \includegraphics{arch.png}
          \caption{System architecture.}
          \label{fig:arch}
        \end{figure}
        """,
        encoding="utf-8",
    )

    mock_vlm_res = {
        "status": "SUCCESS",
        "provider": "gemini",
        "model": "gemini-2.5-flash",
        "images_inspected": 1,
        "findings_count": 1,
        "findings": [
            {
                "category": "OVERLAPPING_ELEMENTS",
                "severity": "WARNING",
                "target": "fig:arch",
                "message": "X-axis tick labels overlap at 10^3 and 10^4.",
                "recommendation": "Rotate tick labels by 30 degrees or reduce tick density.",
            }
        ],
    }

    with patch("scifi.figures.vlm.inspect_images_with_vlm", return_value=mock_vlm_res):
        res = audit_latex_figures(tex_file, render_previews=True, vlm_check=True)

    assert res.vlm_inspection["status"] == "SUCCESS"
    cats = [i.category for i in res.issues]
    assert FigureIssueCategory.OVERLAPPING_ELEMENTS in cats
    vlm_issue = next(i for i in res.issues if i.category == FigureIssueCategory.OVERLAPPING_ELEMENTS)
    assert vlm_issue.severity == FigureSeverity.WARNING
    assert "[VLM]" in vlm_issue.message
    assert res.clean_score == 95


def test_audit_trim_budget_renders_pages_and_runs_vlm(tmp_path: Path):
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        r"""
        \documentclass{article}
        \begin{document}
        Hello world.
        \end{document}
        """,
        encoding="utf-8",
    )
    pdf_file = tmp_path / "main.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 mock")
    page_png = tmp_path / "main_page-001.png"
    page_png.write_bytes(_make_minimal_png(600, 800))

    mock_render = {
        "status": "SUCCESS",
        "backend": "pymupdf",
        "rendered_pages": [{"page": 1, "image_path": str(page_png), "width": 600, "height": 800}],
    }
    mock_vlm = {
        "status": "SUCCESS",
        "provider": "openai",
        "model": "gpt-4o",
        "images_inspected": 1,
        "findings_count": 1,
        "findings": [
            {
                "category": "PAGE_BREAK_WHITESPACE",
                "severity": "WARNING",
                "page": 1,
                "target": "Page 1 (bottom)",
                "message": "Large 35% empty whitespace gap before float on next page.",
                "recommendation": "Adjust float placement specifier to [tp] or tighten preceding paragraph.",
                "potential_savings_lines": 4,
            }
        ],
    }

    with (
        patch("scifi.figures.renderer.render_pdf_pages", return_value=mock_render),
        patch("scifi.figures.vlm.inspect_images_with_vlm", return_value=mock_vlm),
    ):
        res = audit_trim_budget(tex_path=tex_file, render_previews=True, vlm_check=True)

    assert len(res.rendered_pages) == 1
    assert res.rendered_pages[0]["page"] == 1
    assert res.vlm_inspection["status"] == "SUCCESS"
    assert res.total_potential_lines_saved >= 4
    types = [s.suggestion_type for s in res.suggestions]
    assert TrimSuggestionType.PAGE_BREAK_WHITESPACE in types


def test_cli_figures_and_trim_vlm_json(tmp_path: Path, monkeypatch, capsys):
    for var in (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "SCIFI_VLM_API_KEY",
        "SCIFI_VLM_PROVIDER",
    ):
        monkeypatch.delenv(var, raising=False)

    img_png = tmp_path / "fig.png"
    img_png.write_bytes(_make_minimal_png(400, 300))
    tex_file = tmp_path / "paper.tex"
    tex_file.write_text(
        r"""
        \begin{figure}
          \includegraphics{fig.png}
          \caption{Test.}
          \label{fig:test}
        \end{figure}
        """,
        encoding="utf-8",
    )

    rc_fig = cli_main(["figures", str(tex_file), "--vlm", "--json"])
    assert rc_fig == 0
    fig_out = json.loads(capsys.readouterr().out)
    assert fig_out["vlm_inspection"]["status"] == "SKIPPED_NO_API_KEY"

    rc_trim = cli_main(["trim", str(tex_file), "--vlm", "--json"])
    assert rc_trim == 0
    trim_out = json.loads(capsys.readouterr().out)
    assert trim_out["vlm_inspection"]["status"] == "SKIPPED_NO_IMAGES"


def test_local_pixel_checks_no_api_key(tmp_path: Path):
    """Local deterministic pixel checks detect edge clipping and page-break whitespace without any API key."""
    import numpy as np

    from scifi.figures.pixel_checks import check_figure_edge_clipping, check_page_whitespace

    # Build a PNG with dark pixels touching the right border (simulated clipped legend)
    def encode_gray_png(arr: np.ndarray) -> bytes:
        h, w = arr.shape
        raw = b"".join(b"\x00" + arr[y].tobytes() for y in range(h))

        def chunk(ctype: bytes, data: bytes) -> bytes:
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
        return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")

    fig_arr = np.full((100, 100), 255, dtype=np.uint8)
    fig_arr[20:60, -1] = 0  # 40% of right border has ink -> clipped legend
    clipped_png = tmp_path / "clipped.png"
    clipped_png.write_bytes(encode_gray_png(fig_arr))
    clip_res = check_figure_edge_clipping(clipped_png)
    assert clip_res["clipped"] is True
    assert "right" in clip_res["edges"]

    # Build a page PNG where ink stops at 35% height -> >60% bottom whitespace
    page_arr = np.full((200, 150), 255, dtype=np.uint8)
    page_arr[20:70, 20:130] = 0
    sparse_page = tmp_path / "page1.png"
    sparse_page.write_bytes(encode_gray_png(page_arr))
    ws_res = check_page_whitespace(sparse_page)
    assert ws_res["analyzed"] is True
    assert ws_res["bottom_whitespace_ratio"] >= 0.50
