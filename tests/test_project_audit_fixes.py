"""Regression tests for real-world manuscript audit fixes (MFG_Mobile_Edge_Computing & lyap-marl-uav)."""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from scifi.argus.engine import ArgusEngine
from scifi.config import resolve_config
from scifi.figures.pixel_checks import _load_png_luminance
from scifi.latex.tables import generate_latex_table
from scifi.latex.venue import check_venue_compliance
from scifi.math.notation import check_notation
from scifi.reproducibility import audit_reproducibility


def _make_paeth_png(path: Path, width: int = 32, height: int = 24) -> None:
    """Create a valid 8-bit RGB PNG using Paeth (filter=4) scanlines."""

    def chunk(ctype: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(ctype + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(4)  # Paeth filter
        raw.extend(b"\x00" * (width * 3))
    idat = zlib.compress(bytes(raw))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    path.write_bytes(png)


def test_pixel_checks_paeth_png_fast_decode(tmp_path: Path) -> None:
    p = tmp_path / "paeth.png"
    _make_paeth_png(p)
    lum = _load_png_luminance(p)
    assert lum is not None
    assert lum.shape == (24, 32)


def test_notation_preserves_case_semantic_fonts_and_nested_section_braces() -> None:
    tex = r"""
\section{Verification of \texorpdfstring{$\mathcal{O}(K \log K)$}{O(K log K)}}
For each device $k \in \mathcal{K}$ with $|\mathcal{K}| = K$, the observation $\bm{o}_k$
and bound $B$ inside airspace $\mathcal{B}$ satisfy $\mathbb{E}[q_k] \le B$.
"""
    res = check_notation(tex)
    assert res["status"] == "VALID"
    assert res["multi_variant_symbols"] == []
    assert any("O(K log K)" in s for s in res["sections_scanned"])


def test_venue_respects_ifblindreview_conditional(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""
\documentclass{cas-sc}
\newif\ifblindreview
\blindreviewtrue
\begin{document}
\ifblindreview
  \author{Anonymous Author(s)}
\else
  \author[1]{Mahdi Boughrous}
\fi
\end{document}
""",
        encoding="utf-8",
    )
    res = check_venue_compliance(tex, venue="elsevier", double_blind=True)
    leaks = [i for i in res["issues"] if i["category"] == "ANONYMIZATION_LEAK"]
    assert leaks == []


def test_reproducibility_accepts_anonymous_supplementary_zip(tmp_path: Path) -> None:
    tex = tmp_path / "main.tex"
    tex.write_text(
        r"""
\section{Data and Code Availability}
The Python simulation suite is submitted as supplementary material (\texttt{mec\_mfg\_code\_review.zip})
for double-blind peer review across 30 random seeds with 95\% confidence intervals on an NVIDIA A100 GPU
with learning rate 0.001.
""",
        encoding="utf-8",
    )
    res = audit_reproducibility(tex, venue="elsevier", double_blind=True)
    assert res.checklist_items["code_link_anonymized"] is True


def test_argus_skips_cite_flags_inside_abstract() -> None:
    tex = r"""
\begin{abstract}
We propose a Lyapunov-guided bi-level MARL framework for multi-UAV edge computing.
\end{abstract}
\section{Introduction}
This paper studies aerial edge networks.
"""
    rep = ArgusEngine(enable_search=False).audit_text(tex)
    assert rep.findings == []


def test_config_merges_dot_scifi_and_root_toml(tmp_path: Path) -> None:
    dot_dir = tmp_path / ".scifi"
    dot_dir.mkdir()
    (dot_dir / "config.toml").write_text(
        """
[project]
active_venue = "ieee"
double_blind = false

[manuscript]
paper_dir = "paper"
main_entrypoint = "main.tex"
bib_file = "references.bib"
""",
        encoding="utf-8",
    )
    cfg = resolve_config(workspace_dir=tmp_path)
    assert cfg.main_tex == "paper/main.tex"
    assert cfg.bib_file == "paper/references.bib"
    assert cfg.target_venue == "ieee"


def test_generate_latex_table_two_column_and_inject(tmp_path: Path) -> None:
    csv_p = tmp_path / "res.csv"
    csv_p.write_text("Method,Energy,Energy_std\nOurs,10.5,0.2\nBaseline,15.0,0.4\n", encoding="utf-8")
    tex_p = tmp_path / "results.tex"
    tex_p.write_text(
        "% SCIFI:TABLE:tab:main:START\nOLD TABLE\n% SCIFI:TABLE:tab:main:END\n",
        encoding="utf-8",
    )
    res = generate_latex_table(
        csv_p,
        label="tab:main",
        lower_is_better=["Energy"],
        two_column=True,
        font_size="scriptsize",
        inject_tex_path=tex_p,
    )
    assert res["status"] == "SUCCESS"
    assert res["injected_into"] == str(tex_p.resolve())
    updated = tex_p.read_text(encoding="utf-8")
    assert r"\begin{table*}[t]" in updated
    assert r"\scriptsize" in updated
    assert "OLD TABLE" not in updated
    assert json.dumps(res["rows_count"]) == "2"
