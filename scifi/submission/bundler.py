"""All-in-One Academic Paper Submission Bundler."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from scifi.latex.project import resolve_latex_project
from scifi.submission.code_packager import package_anonymous_code
from scifi.submission.cover_letter import generate_cover_letter
from scifi.submission.highlights import generate_highlights
from scifi.submission.models import AuthorInfo, SubmissionBundleResult, normalize_authors
from scifi.submission.profiles import get_publisher_profile
from scifi.submission.title_page import extract_metadata_from_latex, generate_title_page


def _compute_md5(file_path: Path) -> str:
    """Compute MD5 hash of a file."""
    h = hashlib.md5()
    try:
        h.update(file_path.read_bytes())
        return h.hexdigest()
    except Exception:
        return ""


def _load_scifi_toml(root: Path) -> dict[str, Any]:
    """Load configuration from scifi.toml if it exists."""
    toml_path = root / "scifi.toml"
    if not toml_path.exists():
        # Check parents
        for p in root.parents:
            cand = p / "scifi.toml"
            if cand.exists():
                toml_path = cand
                break
    if not toml_path.exists():
        return {}

    try:
        import tomllib

        with open(toml_path, "rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def prepare_submission_bundle(
    target_dir_or_tex: str | Path = ".",
    journal_name: str | None = None,
    venue: str | None = None,
    issn: str | None = None,
    code_dir: str | Path | None = None,
    no_code: bool = False,
    authors: Sequence[AuthorInfo | dict[str, Any] | str] | str | None = None,
    bullets: Sequence[str] | str | None = None,
    figure_path: str | None = None,
    prior_doi: str | None = None,
    funding: str | None = None,
    conflicts: str | None = None,
    editor_name: str | None = None,
    suggested_reviewers: Sequence[dict[str, str]] | None = None,
    output_dir: str | Path | None = None,
    strict: bool = False,
    double_blind: bool | None = None,
    live: bool = False,
) -> SubmissionBundleResult:
    """
    Generate all four submission artifacts and packaging manifest in one shot.
    """
    target = Path(target_dir_or_tex).resolve()
    base_dir = target if target.is_dir() else target.parent

    # Try resolving LaTeX entrypoint
    tex_path: Path | None = None
    if target.is_file() and target.suffix == ".tex":
        tex_path = target
    else:
        try:
            proj = resolve_latex_project(target)
            tex_path = proj.entrypoint
        except Exception:
            for cand_name in ("main.tex", "paper.tex", "manuscript.tex"):
                cand = base_dir / cand_name
                if cand.exists():
                    tex_path = cand
                    break

    # Read config from scifi.toml if present
    cfg = _load_scifi_toml(base_dir)
    sub_cfg = cfg.get("submission", {})

    final_venue = venue or sub_cfg.get("venue") or cfg.get("project", {}).get("target_venue") or "general"
    profile = get_publisher_profile(final_venue)

    final_journal = journal_name or sub_cfg.get("journal") or f"{profile.name} Journal"
    final_issn = issn or sub_cfg.get("issn")
    final_editor = editor_name or sub_cfg.get("editor")
    final_prior_doi = prior_doi or sub_cfg.get("prior_doi")
    final_funding = funding or sub_cfg.get("funding")
    final_conflicts = conflicts or sub_cfg.get("conflicts")

    # Author resolution
    final_authors = normalize_authors(authors)
    if not final_authors and "authors" in sub_cfg:
        final_authors = normalize_authors(sub_cfg["authors"])

    extracted_title: str = ""
    extracted_authors: list[AuthorInfo] = []
    extracted_abs: str = ""
    if tex_path and tex_path.exists():
        extracted_title, extracted_authors, extracted_abs = extract_metadata_from_latex(tex_path)

    if not final_authors and extracted_authors:
        final_authors = extracted_authors

    final_title = extracted_title or "Manuscript Title"

    out_path = Path(output_dir or (base_dir / "dist" / "submission")).resolve()

    gate_readiness_score: int | None = None
    if strict:
        from scifi.doctor import audit_manuscript

        audit_res = audit_manuscript(
            tex_or_dir_path=target_dir_or_tex,
            venue=final_venue,
            double_blind=double_blind,
            live=live,
        )
        if audit_res.get("status") == "SUCCESS":
            gate_readiness_score = audit_res.get("readiness_score")
            blockers = audit_res.get("critical_blockers", [])
            if blockers:
                return SubmissionBundleResult(
                    status="BLOCKED",
                    output_dir=str(out_path),
                    venue=final_venue,
                    blockers=blockers,
                    readiness_score=gate_readiness_score,
                    error_message=f"Submission bundle blocked by {len(blockers)} critical blocker(s).",
                )

    out_path.mkdir(parents=True, exist_ok=True)

    # 1. Highlights
    hl_path = out_path / "highlights.md"
    hl_res = generate_highlights(
        bullets=bullets,
        venue=final_venue,
        manuscript_path=tex_path,
        output_path=hl_path,
    )
    (out_path / "highlights.tex").write_text(hl_res.latex_text, encoding="utf-8")

    # 2. Title Page
    tp_tex_path = out_path / "title_page.tex"
    tp_res = generate_title_page(
        title=final_title,
        authors=final_authors,
        venue=final_venue,
        manuscript_path=tex_path,
        abstract=extracted_abs,
        funding=final_funding,
        conflicts=final_conflicts,
        output_path=tp_tex_path,
    )
    (out_path / "title_page.md").write_text(tp_res.markdown_text, encoding="utf-8")

    # 3. Cover Letter
    cl_path = out_path / "cover_letter.md"
    cl_res = generate_cover_letter(
        manuscript_title=final_title,
        journal_name=final_journal,
        venue=final_venue,
        issn=final_issn,
        editor_name=final_editor,
        authors=final_authors,
        abstract=extracted_abs,
        contributions=[h.text for h in hl_res.highlights],
        figure_path=figure_path,
        prior_doi=final_prior_doi,
        suggested_reviewers=suggested_reviewers,
        manuscript_path=tex_path,
        output_path=cl_path,
    )
    (out_path / "cover_letter.tex").write_text(cl_res.latex_text, encoding="utf-8")

    # 4. Anonymous Code Zip (unless no_code or no code directory)
    code_zip_dest: Path | None = None
    if not no_code:
        resolved_code_dir: Path | None = None
        if code_dir:
            cand = Path(code_dir).resolve()
            if cand.exists():
                resolved_code_dir = cand
        elif "code_dir" in sub_cfg:
            cand = base_dir / sub_cfg["code_dir"]
            if cand.exists():
                resolved_code_dir = cand
        else:
            for subdir_name in ("code", "src", "experiments"):
                cand = base_dir / subdir_name
                if cand.exists() and cand.is_dir():
                    resolved_code_dir = cand
                    break

        if resolved_code_dir:
            code_zip_dest = out_path / "anonymous_code.zip"
            author_names = [a.name for a in final_authors]
            package_anonymous_code(
                code_dir=resolved_code_dir,
                output_zip_path=code_zip_dest,
                author_names=author_names,
            )

    # 5. Manifest
    manifest: dict[str, Any] = {
        "status": "READY",
        "venue": final_venue,
        "journal": final_journal,
        "title": final_title,
        "artifacts": {
            "cover_letter_md": {"path": str(cl_path), "md5": _compute_md5(cl_path)},
            "cover_letter_tex": {
                "path": str(out_path / "cover_letter.tex"),
                "md5": _compute_md5(out_path / "cover_letter.tex"),
            },
            "highlights_md": {"path": str(hl_path), "md5": _compute_md5(hl_path), "all_valid": hl_res.all_valid},
            "highlights_tex": {
                "path": str(out_path / "highlights.tex"),
                "md5": _compute_md5(out_path / "highlights.tex"),
            },
            "title_page_tex": {"path": str(tp_tex_path), "md5": _compute_md5(tp_tex_path)},
            "title_page_md": {"path": str(out_path / "title_page.md"), "md5": _compute_md5(out_path / "title_page.md")},
        },
    }
    if code_zip_dest and code_zip_dest.exists():
        manifest["artifacts"]["anonymous_code_zip"] = {
            "path": str(code_zip_dest),
            "md5": _compute_md5(code_zip_dest),
        }
    if strict:
        manifest["gate_passed"] = True
        manifest["readiness_score"] = gate_readiness_score

    manifest_path = out_path / "submission_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return SubmissionBundleResult(
        status="SUCCESS",
        output_dir=str(out_path),
        venue=final_venue,
        cover_letter_path=str(cl_path),
        highlights_path=str(hl_path),
        title_page_path=str(tp_tex_path),
        code_zip_path=str(code_zip_dest) if code_zip_dest and code_zip_dest.exists() else None,
        manifest_path=str(manifest_path),
        readiness_score=gate_readiness_score,
    )
