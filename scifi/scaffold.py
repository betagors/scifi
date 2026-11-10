"""
2-Pillar Academic Project Scaffolding Engine.
Generates standard paper/ + code/ + .scifi/ project hierarchies
with pre-configured LaTeX structures and Zotero collection binding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from scifi.env import auto_detect_zotero_dir


MAIN_TEX_TEMPLATE = r"""\documentclass[conference]{IEEEtran}
\usepackage{cite}
\usepackage{amsmath,amssymb,amsfonts}
\usepackage{algorithmic}
\usepackage{graphicx}
\usepackage{textcomp}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{xspace}

\input{macros.tex}

\begin{document}

\title{__TITLE__}

\author{\IEEEauthorblockN{Anonymous Author(s)}}

\maketitle

\input{sections/01_abstract.tex}
\input{sections/02_introduction.tex}
\input{sections/03_related_work.tex}
\input{sections/04_methodology.tex}
\input{sections/05_experiments.tex}
\input{sections/06_conclusion.tex}

\bibliographystyle{IEEEtran}
\bibliography{references}

\end{document}
"""

MACROS_TEX_TEMPLATE = r"""% Semantic and mathematical macros conforming to SciFi academic rules
% Enforce upright subscripts for multi-letter names ($W_{\mathrm{loss}}$)
\newcommand{\Wloss}{W_{\mathrm{loss}}\xspace}
\newcommand{\Eout}{\mathcal{E}_{\mathrm{out}}\xspace}
\newcommand{\R}{\mathbb{R}\xspace}
"""

ABSTRACT_TEX_TEMPLATE = r"""\begin{abstract}
% 5-Beat Dual-Audience Abstract Structure:
% 1. Context & Hook: The broader domain and relevance.
% 2. Critical Friction: The unresolved bottleneck or unstated assumption.
% 3. Methodological Core: Our proposed mechanism.
% 4. Empirical Delta: Quantified performance metric against competitive baseline.
% 5. Impact & Implication: Defensible scope of validity.
This is the abstract text placeholder.
\end{abstract}
"""

SECTION_STUB = r"""\section{__SECTION_NAME__}
\label{sec:__LABEL__}

Content for __SECTION_NAME__ goes here.
"""

PYPROJECT_TOML_TEMPLATE = """[project]
name = "__NAME__"
version = "0.1.0"
description = "__TITLE__ computational artifact"
requires-python = ">=3.10"
dependencies = [
    "numpy>=1.24",
    "scipy>=1.10",
    "matplotlib>=3.7",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"
"""


def scaffold_project(
    target_dir: Union[str, Path],
    title: str = "Research Manuscript",
    venue: str = "ieee",
    collection: Optional[str] = None,
    authors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Scaffold a standardized 2-pillar research repository.
    """
    root = Path(target_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    # 1. Directories
    paper_dir = root / "paper"
    sections_dir = paper_dir / "sections"
    figures_dir = paper_dir / "figures"
    tables_dir = paper_dir / "tables"

    code_dir = root / "code"
    src_dir = code_dir / "src"
    scripts_dir = code_dir / "scripts"
    data_dir = code_dir / "data"
    results_dir = code_dir / "results"

    scifi_dir = root / ".scifi"
    reviews_dir = scifi_dir / "reviews"
    submissions_dir = scifi_dir / "submissions"

    for d in [
        sections_dir,
        figures_dir,
        tables_dir,
        src_dir,
        scripts_dir,
        data_dir,
        results_dir,
        reviews_dir,
        submissions_dir,
    ]:
        d.mkdir(parents=True, exist_ok=True)

    # 2. LaTeX files
    main_tex = paper_dir / "main.tex"
    if not main_tex.exists():
        main_tex.write_text(MAIN_TEX_TEMPLATE.replace("__TITLE__", title), encoding="utf-8")

    macros_tex = paper_dir / "macros.tex"
    if not macros_tex.exists():
        macros_tex.write_text(MACROS_TEX_TEMPLATE, encoding="utf-8")

    refs_bib = paper_dir / "references.bib"
    if not refs_bib.exists():
        refs_bib.write_text("% Bibliography entries verified by SciFi\n", encoding="utf-8")

    # Sections
    sections = [
        ("01_abstract.tex", ABSTRACT_TEX_TEMPLATE),
        ("02_introduction.tex", SECTION_STUB.replace("__SECTION_NAME__", "Introduction").replace("__LABEL__", "intro")),
        ("03_related_work.tex", SECTION_STUB.replace("__SECTION_NAME__", "Related Work").replace("__LABEL__", "related")),
        ("04_methodology.tex", SECTION_STUB.replace("__SECTION_NAME__", "Methodology").replace("__LABEL__", "method")),
        ("05_experiments.tex", SECTION_STUB.replace("__SECTION_NAME__", "Experiments and Results").replace("__LABEL__", "experiments")),
        ("06_conclusion.tex", SECTION_STUB.replace("__SECTION_NAME__", "Conclusion and Limitations").replace("__LABEL__", "conclusion")),
    ]
    for s_name, s_content in sections:
        f = sections_dir / s_name
        if not f.exists():
            f.write_text(s_content, encoding="utf-8")

    # 3. Code files
    pyproject = code_dir / "pyproject.toml"
    if not pyproject.exists():
        slug = root.name.lower().replace(" ", "-")
        pyproject.write_text(
            PYPROJECT_TOML_TEMPLATE.replace("__NAME__", slug).replace("__TITLE__", title),
            encoding="utf-8",
        )

    (src_dir / "__init__.py").touch(exist_ok=True)

    # 4. .scifi/config.toml
    zotero_dir = auto_detect_zotero_dir()
    zotero_dir_str = str(zotero_dir).replace("\\", "/") if zotero_dir else ""
    col_str = collection or ""

    config_lines = [
        "[project]",
        f'name = "{root.name}"',
        f'title = "{title}"',
        f'active_venue = "{venue}"',
        f'target_venues = ["{venue}"]',
        "double_blind = true",
        "",
        "[manuscript]",
        'paper_dir = "paper"',
        'main_entrypoint = "main.tex"',
        'bib_file = "references.bib"',
        'macros_file = "macros.tex"',
        "",
        "[code]",
        'code_dir = "code"',
        "",
        "[zotero]",
        f'enabled = {"true" if zotero_dir else "false"}',
        f'data_dir = "{zotero_dir_str}"',
        f'collection = "{col_str}"',
        "port = 23119",
        'sync_bib = "references.bib"',
        "auto_tag = true",
    ]

    config_file = scifi_dir / "config.toml"
    if not config_file.exists():
        config_file.write_text("\n".join(config_lines) + "\n", encoding="utf-8")

    return {
        "status": "SUCCESS",
        "root": str(root),
        "venue": venue,
        "collection": col_str,
    }
