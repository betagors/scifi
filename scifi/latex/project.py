"""
scifi.latex.project — Multi-File LaTeX Project Resolver.

Real-world academic manuscripts often consist of a root entrypoint (e.g. `main.tex`, `paper.tex`, `ms.tex`)
that includes multiple section and table files via `\\input{sections/intro}`, `\\include{sections/method}`,
`\\subfile{...}`, or `\\import{dir}{file}`, and references one or more `.bib` files via
`\\bibliography{...}` or `\\addbibresource{...}`.

This module resolves single-file or multi-file LaTeX projects into:
- Ordered list of `TexSourceFile` objects (`main.tex`, `sections/abstract.tex`, `sections/intro.tex`, ...)
- Merged full-manuscript text with exact `(relative_file, line_number)` line mapping
- Auto-discovered `.bib` bibliography files
- Extracted cited keys (`\\cite{...}`, `\\citep{...}`, `\\citet{...}`, `\\nocite{...}`)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Regex for stripping unescaped LaTeX comments on a line
RE_COMMENT = re.compile(r"(?<!\\)%.*$")

# Regex for matching \input{...}, \include{...}, \subfile{...}
RE_INCLUDE = re.compile(r"\\(?:input|include|subfile)\s*\{\s*([^}]+?)\s*\}")

# Regex for matching \import{dir}{file} or \subimport{dir}{file}
RE_IMPORT = re.compile(r"\\(?:sub)?import\s*\{\s*([^}]*?)\s*\}\s*\{\s*([^}]+?)\s*\}")

# Regex for \bibliography{a,b} and \addbibresource{a.bib}
RE_BIBLIOGRAPHY = re.compile(r"\\(?:bibliography|addbibresource)\s*\{\s*([^}]+?)\s*\}")

# Regex for citations (\cite, \citep, \citet, \citeauthor, \citeyear, \parencite, \textcite, \autocite)
RE_CITE = re.compile(r"\\(?:[a-zA-Z]*cite[a-zA-Z]*)\*?(?:\[[^\]]*\])*\{\s*([^}]+?)\s*\}")

CANDIDATE_ROOT_NAMES = (
    "main.tex",
    "paper.tex",
    "manuscript.tex",
    "ms.tex",
    "article.tex",
    "root.tex",
)


@dataclass
class TexSourceFile:
    """Represents a single .tex file within a LaTeX project."""

    path: Path
    relative_path: str
    content: str
    lines: list[str]


@dataclass
class LatexProject:
    """Resolved representation of a single-file or multi-file LaTeX manuscript."""

    root_dir: Path
    entrypoint: Path
    files: list[TexSourceFile] = field(default_factory=list)
    merged_text: str = ""
    line_map: list[tuple[str, int]] = field(default_factory=list)  # 1-indexed via line_map[idx - 1]
    bib_files: list[Path] = field(default_factory=list)
    missing_includes: list[str] = field(default_factory=list)
    cited_keys: list[str] = field(default_factory=list)

    @property
    def is_multifile(self) -> bool:
        return len(self.files) > 1

    def map_merged_line(self, merged_line_number: int) -> tuple[str, int]:
        """Map a 1-based line number in merged_text back to (relative_file, original_line_number)."""
        if 1 <= merged_line_number <= len(self.line_map):
            return self.line_map[merged_line_number - 1]
        return (self.entrypoint.name, merged_line_number)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "root_dir": str(self.root_dir),
            "entrypoint": str(self.entrypoint),
            "is_multifile": self.is_multifile,
            "tex_files_count": len(self.files),
            "tex_files": [f.relative_path for f in self.files],
            "bib_files": [str(b) for b in self.bib_files],
            "missing_includes": list(self.missing_includes),
            "cited_keys_count": len(self.cited_keys),
        }


def strip_tex_comments(text: str) -> str:
    """Strip unescaped % comments line by line while preserving line count."""
    return "\n".join(RE_COMMENT.sub("", line) for line in text.splitlines())


def find_main_tex(directory: Path, configured_main: str | None = None) -> Path | None:
    """
    Locate the primary entrypoint .tex file inside a directory.

    Priority:
    1. Configured main_tex (e.g. from scifi.toml) if it exists
    2. Standard root names (main.tex, paper.tex, manuscript.tex, ms.tex, article.tex) that contain \\documentclass
    3. Any .tex file in the root directory containing \\documentclass
    4. Standard root names even without \\documentclass
    5. Single .tex file in the root directory
    """
    if configured_main:
        cand = directory / configured_main
        if cand.is_file():
            return cand.resolve()

    tex_files = sorted(directory.glob("*.tex"))
    if not tex_files:
        return None

    # Check standard names with \documentclass first
    for name in CANDIDATE_ROOT_NAMES:
        cand = directory / name
        if cand.is_file():
            try:
                content = cand.read_text(encoding="utf-8", errors="replace")
                if "\\documentclass" in strip_tex_comments(content):
                    return cand.resolve()
            except Exception:
                pass

    # Any top-level .tex with \documentclass
    for tf in tex_files:
        try:
            content = tf.read_text(encoding="utf-8", errors="replace")
            if "\\documentclass" in strip_tex_comments(content):
                return tf.resolve()
        except Exception:
            pass

    # Standard names without \documentclass
    for name in CANDIDATE_ROOT_NAMES:
        cand = directory / name
        if cand.is_file():
            return cand.resolve()

    return tex_files[0].resolve()


def _resolve_include_target(target_raw: str, current_dir: Path, root_dir: Path) -> Path | None:
    """Resolve an \\input{target} path relative to root_dir or current_dir."""
    cleaned = target_raw.strip().strip('"').strip("'")
    if not cleaned:
        return None

    candidates: list[Path] = []
    for base in (root_dir, current_dir):
        p = base / cleaned
        candidates.append(p)
        if not p.suffix:
            candidates.append(p.with_suffix(".tex"))

    for c in candidates:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    return None


def resolve_latex_project(
    path_or_content: str | Path,
    configured_main: str | None = None,
    explicit_bib: str | Path | None = None,
) -> LatexProject:
    """
    Resolve a single .tex file, a multi-file LaTeX directory, or raw LaTeX text into a LatexProject.

    Recursively expands `\\input{...}`, `\\include{...}`, `\\subfile{...}`, and `\\import{...}{...}`
    while recording exact `(relative_path, line_number)` provenance for every line in `merged_text`.
    """
    # Case 1: Raw LaTeX string passed directly
    if isinstance(path_or_content, str) and (
        "\n" in path_or_content or "\\" in path_or_content and not Path(path_or_content).exists()
    ):
        # Check if it looks like a missing file path vs raw LaTeX
        looks_like_path = (
            "\n" not in path_or_content
            and not path_or_content.strip().startswith("\\")
            and (path_or_content.strip().endswith(".tex") or "/" in path_or_content or "\\" in path_or_content)
        )
        if looks_like_path:
            raise FileNotFoundError(f"LaTeX file or directory not found: {path_or_content}")

        lines = path_or_content.splitlines()
        src = TexSourceFile(
            path=Path("inline.tex"),
            relative_path="inline.tex",
            content=path_or_content,
            lines=lines,
        )
        inline_line_map = [("inline.tex", i) for i in range(1, len(lines) + 1)]
        cited = _extract_cited_keys(path_or_content)
        return LatexProject(
            root_dir=Path.cwd(),
            entrypoint=Path("inline.tex"),
            files=[src],
            merged_text=path_or_content,
            line_map=inline_line_map,
            bib_files=[Path(explicit_bib).resolve()] if explicit_bib and Path(explicit_bib).is_file() else [],
            missing_includes=[],
            cited_keys=cited,
        )

    p = Path(path_or_content)
    if not p.exists():
        raise FileNotFoundError(f"LaTeX file or directory not found: {path_or_content}")

    if p.is_dir():
        root_dir = p.resolve()
        entrypoint = find_main_tex(root_dir, configured_main=configured_main)
        if entrypoint is None:
            raise FileNotFoundError(f"No .tex files found in directory: {root_dir}")
    else:
        entrypoint = p.resolve()
        root_dir = entrypoint.parent

    visited_paths: set[Path] = set()
    source_files: list[TexSourceFile] = []
    merged_lines: list[str] = []
    line_map: list[tuple[str, int]] = []
    missing_includes: list[str] = []
    discovered_bib_refs: list[str] = []

    def _rel_name(file_path: Path) -> str:
        try:
            return file_path.relative_to(root_dir).as_posix()
        except ValueError:
            return file_path.name

    def _process_file(tex_path: Path) -> None:
        resolved = tex_path.resolve()
        if resolved in visited_paths:
            return
        visited_paths.add(resolved)

        try:
            content = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return

        lines = content.splitlines()
        rel = _rel_name(resolved)
        source_files.append(
            TexSourceFile(
                path=resolved,
                relative_path=rel,
                content=content,
                lines=lines,
            )
        )

        for idx, raw_line in enumerate(lines, start=1):
            clean_line = RE_COMMENT.sub("", raw_line)

            # Collect bibliography declarations
            for bib_match in RE_BIBLIOGRAPHY.finditer(clean_line):
                for part in bib_match.group(1).split(","):
                    if part.strip():
                        discovered_bib_refs.append(part.strip())

            # Check for \import{dir}{file}
            import_matches = list(RE_IMPORT.finditer(clean_line))
            include_matches = list(RE_INCLUDE.finditer(clean_line))

            # Always record the original line first so preamble/section context stays intact
            merged_lines.append(raw_line)
            line_map.append((rel, idx))

            for im in import_matches:
                sub_dir, sub_file = im.group(1).strip(), im.group(2).strip()
                combined = f"{sub_dir.rstrip('/')}/{sub_file}" if sub_dir else sub_file
                target_path = _resolve_include_target(combined, resolved.parent, root_dir)
                if target_path is not None:
                    _process_file(target_path)
                else:
                    if combined not in missing_includes:
                        missing_includes.append(combined)

            for inc in include_matches:
                target_raw = inc.group(1).strip()
                target_path = _resolve_include_target(target_raw, resolved.parent, root_dir)
                if target_path is not None:
                    _process_file(target_path)
                else:
                    if target_raw not in missing_includes:
                        missing_includes.append(target_raw)

    _process_file(entrypoint)

    # Resolve .bib files
    bib_files: list[Path] = []
    seen_bibs: set[Path] = set()

    def _add_bib(cand: Path) -> None:
        try:
            if cand.is_file():
                r = cand.resolve()
                if r not in seen_bibs:
                    seen_bibs.add(r)
                    bib_files.append(r)
        except OSError:
            pass

    if explicit_bib:
        _add_bib(Path(explicit_bib))
        if not Path(explicit_bib).is_absolute():
            _add_bib(root_dir / explicit_bib)

    for ref in discovered_bib_refs:
        c = root_dir / ref
        _add_bib(c)
        if not c.suffix:
            _add_bib(c.with_suffix(".bib"))

    # Fallback: check standard references.bib or any .bib in root_dir if none found yet
    if not bib_files:
        _add_bib(root_dir / "references.bib")
        if not bib_files:
            for bf in sorted(root_dir.glob("*.bib")):
                _add_bib(bf)

    merged_text = "\n".join(merged_lines)
    cited_keys = _extract_cited_keys(merged_text)

    return LatexProject(
        root_dir=root_dir,
        entrypoint=entrypoint,
        files=source_files,
        merged_text=merged_text,
        line_map=line_map,
        bib_files=bib_files,
        missing_includes=missing_includes,
        cited_keys=cited_keys,
    )


def _extract_cited_keys(text: str) -> list[str]:
    """Extract all unique citation keys from \\cite*{...} commands across uncommented LaTeX text."""
    clean = strip_tex_comments(text)
    seen: set[str] = set()
    ordered: list[str] = []
    for m in RE_CITE.finditer(clean):
        raw_keys = m.group(1)
        for k in raw_keys.split(","):
            key = k.strip()
            if key and key != "*" and key not in seen:
                seen.add(key)
                ordered.append(key)
    return ordered
