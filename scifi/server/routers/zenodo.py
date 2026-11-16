"""
FastMCP Router: Zenodo Deposit, DOI & Submission Integration Tools.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scifi.server.app import mcp
from scifi.zenodo import ZenodoDepositClient


@mcp.tool()
def scifi_zenodo_status(sandbox: bool = False) -> dict[str, Any]:
    """
    Check Zenodo API token configuration and connectivity.
    """
    return ZenodoDepositClient(sandbox=sandbox).status()


@mcp.tool()
def scifi_zenodo_list_depositions(
    status: str | None = None,
    limit: int = 20,
    query: str | None = None,
    sandbox: bool = False,
) -> list[dict[str, Any]]:
    """
    List Zenodo depositions belonging to the configured account.
    `status` may be 'draft' or 'published'.
    """
    deps = ZenodoDepositClient(sandbox=sandbox).list_depositions(
        status=status,
        size=limit,
        query=query,
    )
    return [d.to_dict() for d in deps]


@mcp.tool()
def scifi_zenodo_get_deposition(deposition_id: int, sandbox: bool = False) -> dict[str, Any]:
    """
    Fetch full metadata and file details for a Zenodo deposition.
    """
    return ZenodoDepositClient(sandbox=sandbox).get_deposition(deposition_id).to_dict()


@mcp.tool()
def scifi_zenodo_create_deposition(
    title: str,
    upload_type: str = "software",
    description: str | None = None,
    creators: list[str] | str | None = None,
    keywords: list[str] | None = None,
    license_id: str | None = None,
    prereserve_doi: bool = True,
    sandbox: bool = False,
) -> dict[str, Any]:
    """
    Create a new Zenodo draft deposition with optional pre-reserved DOI.
    """
    dep = ZenodoDepositClient(sandbox=sandbox).create_deposition(
        title=title,
        upload_type=upload_type,
        description=description,
        creators=creators,
        keywords=keywords,
        license_id=license_id,
        prereserve_doi=prereserve_doi,
    )
    return dep.to_dict()


@mcp.tool()
def scifi_zenodo_update_metadata(
    deposition_id: int,
    metadata: dict[str, Any],
    merge_existing: bool = True,
    sandbox: bool = False,
) -> dict[str, Any]:
    """
    Update metadata fields on an existing Zenodo draft deposition.
    """
    dep = ZenodoDepositClient(sandbox=sandbox).update_metadata(
        deposition_id=deposition_id,
        metadata=metadata,
        merge_existing=merge_existing,
    )
    return dep.to_dict()


@mcp.tool()
def scifi_zenodo_upload_file(
    deposition_id: int,
    file_path: str,
    remote_name: str | None = None,
    sandbox: bool = False,
) -> dict[str, Any]:
    """
    Upload a local file to a Zenodo draft deposition.
    """
    zf = ZenodoDepositClient(sandbox=sandbox).upload_file(
        deposition_id=deposition_id,
        file_path=file_path,
        remote_name=remote_name,
    )
    return zf.to_dict()


@mcp.tool()
def scifi_zenodo_reserve_doi(deposition_id: int, sandbox: bool = False) -> dict[str, Any]:
    """
    Pre-reserve a DOI on a Zenodo draft deposition.
    """
    return ZenodoDepositClient(sandbox=sandbox).reserve_doi(deposition_id)


@mcp.tool()
def scifi_zenodo_publish_deposition(
    deposition_id: int,
    confirm: bool = False,
    sandbox: bool = False,
) -> dict[str, Any]:
    """
    Publish a Zenodo draft deposition (permanent action that mints a DOI).
    Requires `confirm=True`.
    """
    if not confirm:
        raise ValueError("Publishing a Zenodo deposition is permanent; pass confirm=True to proceed.")
    return ZenodoDepositClient(sandbox=sandbox).publish(deposition_id).to_dict()


@mcp.tool()
def scifi_zenodo_push_submission(
    files: list[str] | None = None,
    bundle_dir: str | None = None,
    deposition_id: int | None = None,
    title: str | None = None,
    description: str | None = None,
    creators: list[str] | str | None = None,
    upload_type: str = "software",
    keywords: list[str] | None = None,
    license_id: str | None = None,
    publish: bool = False,
    sandbox: bool = False,
) -> dict[str, Any]:
    """
    Push SciFi submission artifacts (explicit files or files from `bundle_dir`)
    to an existing or newly created Zenodo deposition.
    """
    resolved_files: list[Path] = []
    if files:
        resolved_files.extend(Path(f) for f in files)
    elif bundle_dir:
        bdir = Path(bundle_dir)
        if bdir.is_dir():
            for cand in sorted(bdir.iterdir()):
                if cand.is_file() and cand.suffix.lower() in {".zip", ".pdf", ".tex", ".md"}:
                    resolved_files.append(cand)

    if not resolved_files:
        raise ValueError("Provide `files` or a `bundle_dir` containing submission artifacts to upload.")

    res = ZenodoDepositClient(sandbox=sandbox).push_submission_artifacts(
        files=resolved_files,
        deposition_id=deposition_id,
        title=title,
        description=description,
        creators=creators,
        upload_type=upload_type,
        keywords=keywords,
        license_id=license_id,
        publish=publish,
    )
    return res.to_dict()
