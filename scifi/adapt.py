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
from typing import Any

from scifi.env import auto_detect_zotero_dir

IGNORE_DIRS = {".git", ".venv", "venv", ".idea", ".vscode", "__pycache__", ".pytest_cache", ".scifi"}


def parse_bib_keys_and_titles(bib_path: Path) -> list[dict[str, str]]:
    """Simple parser extracting keys, titles, and DOIs from a BibTeX file."""
    if not bib_path.is_file():
        return []
    content = bib_path.read_text(encoding="utf-8", errors="ignore")
    entries: list[dict[str, str]] = []

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
        eprint_m = re.search(r"(?:eprint|arxiv(?:id)?)\s*=\s*[\"{](.*?)[\"}]", block, re.IGNORECASE)

        entries.append(
            {
                "key": key,
                "type": entry_type,
                "title": title_m.group(1).strip() if title_m else "",
                "doi": doi_m.group(1).strip() if doi_m else "",
                "arxiv_id": eprint_m.group(1).strip() if eprint_m else "",
            }
        )
    return entries


_BIB_TO_ZOTERO_TYPE = {
    "article": ("journalArticle", "publicationTitle"),
    "inproceedings": ("conferencePaper", "proceedingsTitle"),
    "conference": ("conferencePaper", "proceedingsTitle"),
    "book": ("book", None),
    "incollection": ("bookSection", "bookTitle"),
    "phdthesis": ("thesis", None),
    "mastersthesis": ("thesis", None),
    "techreport": ("report", None),
    "misc": ("document", None),
}


def _clean_tex(s: str) -> str:
    s = re.sub(r"\\([&%_#$])", r"\1", s)
    s = re.sub(r"\{\\['`\"^~]\{?(\w)\}?\}", r"\1", s)
    s = re.sub(r"\\['`\"^~](\w)", r"\1", s)
    return re.sub(r"[{}]", "", s).strip()


def _bib_entries_to_zotero_items(bib_paths: list[Path], keys: set[str]) -> list[dict[str, Any]]:
    """Convert selected BibTeX entries to Zotero item JSON."""
    import bibtexparser

    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in bib_paths:
        if not p.is_file():
            continue
        lib = bibtexparser.parse_string(p.read_text(encoding="utf-8", errors="ignore"))
        for e in lib.entries:
            if e.key not in keys or e.key in seen:
                continue
            seen.add(e.key)
            f = {k: _clean_tex(v.value) for k, v in e.fields_dict.items()}
            item_type, venue_field = _BIB_TO_ZOTERO_TYPE.get(e.entry_type.lower(), ("document", None))
            item: dict[str, Any] = {"itemType": item_type, "title": f.get("title", e.key)}
            creators = []
            for a in re.split(r"\s+and\s+", f.get("author", "")):
                if "," in a:
                    last, first = [x.strip() for x in a.split(",", 1)]
                    creators.append({"creatorType": "author", "firstName": first, "lastName": last})
                elif a.strip():
                    creators.append({"creatorType": "author", "name": a.strip()})
            item["creators"] = creators
            if f.get("year"):
                item["date"] = f["year"]
            if f.get("doi"):
                item["DOI"] = f["doi"]
            if f.get("url"):
                item["url"] = f["url"]
            if f.get("volume"):
                item["volume"] = f["volume"]
            if f.get("number") and item_type == "journalArticle":
                item["issue"] = f["number"]
            if f.get("pages"):
                item["pages"] = f["pages"].replace("--", "–")
            if f.get("publisher") and item_type in ("book", "bookSection"):
                item["publisher"] = f["publisher"]
            venue = f.get("journal") or f.get("booktitle")
            if venue_field and venue:
                item[venue_field] = venue
            items.append(item)
    return items


def adapt_project(
    repo_dir: str | Path,
    venue: str = "ieee",
    collection: str | None = None,
    auto_match: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Safely adapt an existing legacy repository into SciFi structure.
    """
    root = Path(repo_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Repository directory does not exist: {root}")

    # Step 1: Discover files
    publication_files: list[tuple[Path, Path]] = []
    code_files: list[tuple[Path, Path]] = []
    data_files: list[tuple[Path, Path]] = []

    paper_dir = root / "paper"
    code_dir = root / "code"
    scifi_dir = root / ".scifi"

    all_files = [f for f in root.iterdir() if f.is_file() and f.name not in (".gitignore", "README.md", "LICENSE")]
    # Prioritize primary main/paper tex files
    all_files.sort(
        key=lambda p: (
            0
            if p.name.lower() in ("main.tex", "paper.tex")
            else (1 if "main" in p.name.lower() or "paper" in p.name.lower() else 2)
        )
    )

    primary_tex_assigned = (paper_dir / "main.tex").is_file()
    bib_files: list[Path] = []

    for f in all_files:
        suffix = f.suffix.lower()
        if suffix in (".tex", ".sty", ".cls", ".bst"):
            if (
                suffix == ".tex"
                and not primary_tex_assigned
                and ("paper" in f.name.lower() or "main" in f.name.lower())
            ):
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

    # Discover any existing .bib files in paper/
    bib_to_parse: list[Path] = list(bib_files)
    if (paper_dir / "references.bib").is_file() and (paper_dir / "references.bib") not in bib_to_parse:
        bib_to_parse.append(paper_dir / "references.bib")
    if paper_dir.is_dir():
        for b in sorted(paper_dir.glob("*.bib")):
            if b not in bib_to_parse:
                bib_to_parse.append(b)

    # Step 2: Parse citations
    citations: list[dict[str, str]] = []
    seen_keys: set[str] = set()
    for b in bib_to_parse:
        for entry in parse_bib_keys_and_titles(b):
            k = entry.get("key")
            if k:
                if k in seen_keys:
                    continue
                seen_keys.add(k)
            citations.append(entry)

    # Cross-reference against Zotero if available & auto-detect / provision collection
    zotero_matches = 0
    resolved_collection = collection
    collection_staged = False
    collection_error: str | None = None
    populated_linked = 0
    populated_created = 0

    zotero_dir = auto_detect_zotero_dir()
    if zotero_dir:
        try:
            from scifi.literature.zotero.reader import ZoteroLocalReader
            from scifi.literature.zotero.writer import ZoteroLocalWriter

            reader = ZoteroLocalReader(data_dir=zotero_dir)
            writer = ZoteroLocalWriter()

            matched_keys: list[str] = []
            unmatched: list[dict[str, str]] = []
            for c in citations:
                item = None
                if c.get("doi"):
                    item = reader.get_item_by_doi(c["doi"])
                if not item and c.get("arxiv_id"):
                    item = reader.get_item_by_arxiv(c["arxiv_id"])
                if item:
                    zotero_matches += 1
                    matched_keys.append(item.key)
                else:
                    unmatched.append(c)

            if not resolved_collection:
                if auto_match:
                    best_col, best_count = reader.find_best_matching_collection(citations)
                    if best_col and best_count > 0:
                        resolved_collection = best_col

                if not resolved_collection:
                    resolved_collection = root.name

            existing_col = reader.get_collection_by_name(resolved_collection)
            if not existing_col and not dry_run:
                c_res = writer.create_collection(resolved_collection)
                if c_res.get("status") == "STAGED":
                    collection_staged = True
                    if c_res.get("code") == 403 or "not enabled" in str(c_res.get("body", "")).lower():
                        collection_error = "Local API is not enabled in Zotero (Settings > Advanced > 'Allow other applications on this computer to communicate with Zotero')."

            # Populate the collection: link matched library items, import the rest from the .bib
            if not dry_run and not collection_staged:
                col_key = writer.get_collection_key(resolved_collection)
                if col_key:
                    populated_linked = writer.add_items_to_collection(col_key, matched_keys)
                    skip_titles = set()
                    if existing_col:
                        skip_titles = {
                            re.sub(r"[^a-z0-9]", "", (i.title or "").lower())
                            for i in reader.get_collection_items(resolved_collection)
                        }
                    pending = {
                        c["key"]
                        for c in unmatched
                        if re.sub(r"[^a-z0-9]", "", c.get("title", "").lower()) not in skip_titles
                    }
                    bib_items = _bib_entries_to_zotero_items(bib_to_parse, pending)
                    populated_created = writer.create_items(bib_items, col_key)
        except Exception:
            pass

    if not resolved_collection:
        resolved_collection = root.name

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

    # Inherit existing scifi.toml configurations if present
    scifi_toml = root / "scifi.toml"
    scifi_toml_data: dict[str, Any] = {}
    if scifi_toml.is_file():
        try:
            import tomllib

            scifi_toml_data = tomllib.loads(scifi_toml.read_text(encoding="utf-8"))
        except Exception:
            pass

    manuscript_sec = (
        scifi_toml_data.get("manuscript", {}) if isinstance(scifi_toml_data.get("manuscript"), dict) else {}
    )
    resolved_venue = manuscript_sec.get("target_venue", venue) if venue == "ieee" else venue
    resolved_double_blind = manuscript_sec.get("double_blind", True)

    # Derive human-friendly title: check paper/main.tex \title, scifi.toml, or fallback to folder name
    project_title = root.name.replace("-", " ").title()
    main_tex_cand = paper_dir / "main.tex"
    if not main_tex_cand.is_file():
        for src, dst in publication_files:
            if dst.name == "main.tex" and src.is_file():
                main_tex_cand = src
                break

    if main_tex_cand.is_file():
        try:
            tex_content = main_tex_cand.read_text(encoding="utf-8", errors="ignore")
            title_m = re.search(r"\\title\s*\{([^}]+)\}", tex_content)
            if title_m:
                t = title_m.group(1).replace("\n", " ").strip()
                t = re.sub(r"\\[a-zA-Z]+\{([^}]*)\}", r"\1", t)
                t = t.replace("~", " ").strip()
                if t:
                    project_title = t
        except Exception:
            pass

    # Generate .scifi/config.toml
    zotero_dir_str = str(zotero_dir).replace("\\", "/") if zotero_dir else ""
    col_str = resolved_collection or ""

    config_text = f"""[project]
name = "{root.name}"
title = "{project_title}"
active_venue = "{resolved_venue}"
target_venues = ["{resolved_venue}"]
double_blind = {"true" if resolved_double_blind else "false"}

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
        "collection_staged": collection_staged,
        "collection_error": collection_error,
        "populated_linked": populated_linked,
        "populated_created": populated_created,
    }
