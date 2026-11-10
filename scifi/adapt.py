"""
Legacy Academic Repository Adaptation Engine.
Reorganizes flat, messy, or monolithic research repositories into the
standard 2-pillar structure (paper/ + code/ + .scifi/), extracts citations,
and cross-references them against Zotero.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from scifi.env import auto_detect_zotero_dir


IGNORE_DIRS = {".git", ".venv", "venv", ".idea", ".vscode", "__pycache__", ".pytest_cache", ".scifi"}


def parse_bib_keys_and_titles(bib_path: Path) -> List[Dict[str, str]]:
    """Simple parser extracting keys, titles, and DOIs from a BibTeX file."""
    if not bib_path.is_file():
        return []
    content = bib_path.read_text(encoding="utf-8", errors="ignore")
    entries: List[Dict[str, str]] = []

    # Match @type{key, ... }
    entry_pattern = re.compile(r"@(\w+)\s*\{\s*([^,]+),", re.IGNORECASE)
    for m in entry_pattern.finditer(content):
        entry_type = m.group(1).lower()
        key = m.group(2).strip()
        if entry_type in ("comment", "preamble", "string"):
            continue

        # Extract title and DOI within the approximate block
        start_idx = m.end()
        end_idx = content.find("\n@", start_idx)
        block = content[start_idx:end_idx] if end_idx != -1 else content[start_idx:]

        title_m = re.search(r"title\s*=\s*[\"{](.*?)[\"}]", block, re.IGNORECASE | re.DOTALL)
        doi_m = re.search(r"doi\s*=\s*[\"{](.*?)[\"}]", block, re.IGNORECASE)

        entries.append({
            "key": key,
            "type": entry_type,
            "title": title_m.group(1).strip() if title_m else "",
            "doi": doi_m.group(1).strip() if doi_m else "",
        })
    return entries


def adapt_project(
    repo_dir: Union[str, Path],
    venue: str = "ieee",
    collection: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Safely adapt an existing legacy repository into SciFi structure.
    """
    root = Path(repo_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository directory does not exist: {root}")

    # Step 1: Discover files
    publication_files: List[Tuple[Path, Path]] = []
    code_files: List[Tuple[Path, Path]] = []
    data_files: List[Tuple[Path, Path]] = []

    paper_dir = root / "paper"
    code_dir = root / "code"
    scifi_dir = root / ".scifi"

    all_files = [
        f for f in root.iterdir()
        if f.is_file() and f.name not in (".gitignore", "README.md", "LICENSE")
    ]
    # Prioritize primary main/paper tex files
    all_files.sort(key=lambda p: 0 if p.name.lower() in ("main.tex", "paper.tex") else (1 if "main" in p.name.lower() or "paper" in p.name.lower() else 2))

    primary_tex_assigned = False
    bib_files: List[Path] = []

    for f in all_files:
        suffix = f.suffix.lower()
        if suffix in (".tex", ".sty", ".cls", ".bst"):
            if suffix == ".tex" and not primary_tex_assigned and ("paper" in f.name.lower() or "main" in f.name.lower()):
                dest = paper_dir / "main.tex"
                primary_tex_assigned = True
            elif suffix == ".tex" and not primary_tex_assigned:
                dest = paper_dir / "main.tex"
                primary_tex_assigned = True
            else:
                dest = paper_dir / f.name
            publication_files.append((f, dest))
        elif suffix == ".bib":
            bib_files.append(f)
            dest = paper_dir / "references.bib"
            publication_files.append((f, dest))
        elif suffix in (".py", ".ipynb", ".sh", ".bash"):
            dest = code_dir / "src" / f.name
            code_files.append((f, dest))
        elif suffix in (".csv", ".tsv", ".parquet", ".h5", ".dat"):
            dest = code_dir / "data" / f.name
            data_files.append((f, dest))

    # Existing figures folder
    fig_dir = root / "figures"
    if fig_dir.is_dir() and not (paper_dir / "figures").exists():
        publication_files.append((fig_dir, paper_dir / "figures"))

    # Step 2: Parse citations
    citations: List[Dict[str, str]] = []
    for b in bib_files:
        citations.extend(parse_bib_keys_and_titles(b))

    # Cross-reference against Zotero if available & auto-detect / provision collection
    zotero_matches = 0
    resolved_collection = collection

    zotero_dir = auto_detect_zotero_dir()
    if zotero_dir:
        try:
            from scifi.literature.zotero.reader import ZoteroLocalReader
            from scifi.literature.zotero.writer import ZoteroLocalWriter

            reader = ZoteroLocalReader(data_dir=zotero_dir)
            writer = ZoteroLocalWriter()

            for c in citations:
                matched = False
                if c.get("doi"):
                    item = reader.get_item_by_doi(c["doi"])
                    if item:
                        matched = True
                if matched:
                    zotero_matches += 1

            if resolved_collection:
                existing_col = reader.get_collection_by_name(resolved_collection)
                if not existing_col and not dry_run:
                    writer.create_collection(resolved_collection)
            else:
                best_col, best_count = reader.find_best_matching_collection(citations)
                if best_col and best_count > 0:
                    resolved_collection = best_col
                else:
                    default_name = root.name.replace("-", " ").title()
                    resolved_collection = default_name
                    if not dry_run:
                        writer.create_collection(default_name)
        except Exception:
            pass

    if dry_run:
        return {
            "status": "DRY_RUN",
            "root": str(root),
            "publication_moves": [(str(src), str(dst)) for src, dst in publication_files],
            "code_moves": [(str(src), str(dst)) for src, dst in code_files],
            "data_moves": [(str(src), str(dst)) for src, dst in data_files],
            "citations_found": len(citations),
            "zotero_matches": zotero_matches,
            "collection": resolved_collection or "",
        }

    # Step 3: Execute moves
    paper_dir.mkdir(parents=True, exist_ok=True)
    (paper_dir / "sections").mkdir(parents=True, exist_ok=True)
    (paper_dir / "figures").mkdir(parents=True, exist_ok=True)
    (paper_dir / "tables").mkdir(parents=True, exist_ok=True)
    (code_dir / "src").mkdir(parents=True, exist_ok=True)
    (code_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (code_dir / "data").mkdir(parents=True, exist_ok=True)
    (code_dir / "results").mkdir(parents=True, exist_ok=True)
    scifi_dir.mkdir(parents=True, exist_ok=True)

    for src, dst in publication_files:
        if src.is_dir():
            if not dst.exists():
                shutil.move(str(src), str(dst))
        elif src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    for src, dst in code_files:
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    for src, dst in data_files:
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))

    # Ensure macros.tex and references.bib exist in paper/
    macros_file = paper_dir / "macros.tex"
    if not macros_file.exists():
        macros_file.write_text("% Semantic and mathematical macros\n", encoding="utf-8")

    refs_file = paper_dir / "references.bib"
    if not refs_file.exists():
        refs_file.write_text("% References managed by SciFi\n", encoding="utf-8")

    # Generate .scifi/config.toml
    zotero_dir_str = str(zotero_dir).replace("\\", "/") if zotero_dir else ""
    col_str = resolved_collection or ""

    config_text = f"""[project]
name = "{root.name}"
title = "{root.name.replace('-', ' ').title()}"
active_venue = "{venue}"
target_venues = ["{venue}"]
double_blind = true

[manuscript]
paper_dir = "paper"
main_entrypoint = "main.tex"
bib_file = "references.bib"
macros_file = "macros.tex"

[code]
code_dir = "code"

[zotero]
enabled = {"true" if zotero_dir else "false"}
data_dir = "{zotero_dir_str}"
collection = "{col_str}"
port = 23119
sync_bib = "references.bib"
auto_tag = true
"""
    config_path = scifi_dir / "config.toml"
    if not config_path.exists():
        config_path.write_text(config_text, encoding="utf-8")

    return {
        "status": "SUCCESS",
        "root": str(root),
        "citations_found": len(citations),
        "zotero_matches": zotero_matches,
        "collection": col_str,
    }
