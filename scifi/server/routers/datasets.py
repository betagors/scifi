"""
FastMCP Router: Dataset Management & Kaggle Control Tools.
"""

from __future__ import annotations

from typing import Any

from scifi.config import get_datasets_dir
from scifi.datasets import DatasetManager, KaggleClient
from scifi.datasets.inspector import truncate_str
from scifi.server.app import mcp


def _compact_file_list(files: list[Any], max_files: int) -> dict[str, Any]:
    total = len(files)
    return {
        "file_count": total,
        "files_preview": files[:max_files],
        "omitted_files": max(0, total - max_files),
    }


@mcp.tool()
def scifi_datasets_dir(set_path: str | None = None) -> dict[str, Any]:
    """
    Get or set the default datasets directory (`datasets_dir`).
    """
    if set_path and set_path.strip():
        resolved = DatasetManager.set_default_dir(set_path)
        return {"datasets_dir": str(resolved), "updated": True}
    return {"datasets_dir": str(get_datasets_dir()), "updated": False}


@mcp.tool()
def scifi_datasets_list(datasets_dir: str | None = None, max_files: int = 10) -> dict[str, Any]:
    """
    List all locally downloaded datasets tracked in the default datasets folder.
    Returns compact file counts and a bounded file preview to avoid wasting tokens.
    """
    mgr = DatasetManager(datasets_dir=datasets_dir)
    records = mgr.list_local()
    compact_records = []
    for r in records:
        d = r.to_dict()
        files = d.pop("files", [])
        d.update(_compact_file_list(files, max(0, max_files)))
        compact_records.append(d)
    return {
        "datasets_dir": str(mgr.datasets_dir),
        "count": len(records),
        "datasets": compact_records,
    }


@mcp.tool()
def scifi_datasets_inspect(
    target: str,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
    max_files: int = 20,
    datasets_dir: str | None = None,
) -> dict[str, Any]:
    """
    Inspect a local dataset file, directory, or tracked dataset identifier in a
    token-efficient way: returns schema, column types, row/file counts, byte sizes,
    and a small truncated sample instead of dumping raw dataset contents.
    """
    mgr = DatasetManager(datasets_dir=datasets_dir)
    return mgr.inspect(
        target=target,
        max_rows=max_rows,
        max_chars=max_chars,
        max_columns=max_columns,
        max_files=max_files,
    )


@mcp.tool()
def scifi_datasets_search(
    query: str,
    provider: str = "all",
    limit: int = 15,
) -> dict[str, Any]:
    """
    Search datasets across Kaggle, Hugging Face Hub, and Zenodo.
    `provider` can be 'all', 'kaggle', 'huggingface' ('hf'), or 'zenodo'.
    Descriptions and file lists are bounded to keep token usage minimal.
    """
    mgr = DatasetManager()
    res = mgr.search(query=query, provider=provider, limit=limit)
    for item in res.get("results", []):
        if isinstance(item.get("description"), str):
            item["description"] = truncate_str(item["description"], max_chars=240)
        if isinstance(item.get("files"), list):
            files = item["files"]
            item["file_count"] = len(files)
            item["files"] = files[:5]
    return res


@mcp.tool()
def scifi_datasets_download(
    source: str,
    identifier: str,
    dest_dir: str | None = None,
    file_name: str | None = None,
    unzip: bool = True,
) -> dict[str, Any]:
    """
    Download a dataset from 'kaggle', 'huggingface' ('hf'), 'zenodo', 'url', or 'auto'
    into the default datasets folder (or `dest_dir`).
    """
    mgr = DatasetManager(datasets_dir=dest_dir)
    res = mgr.download(
        source=source,
        identifier=identifier,
        dest_dir=dest_dir,
        unzip=unzip,
        file_name=file_name,
    )
    d = res.to_dict()
    files = d.get("files", [])
    d["file_count"] = len(files)
    if len(files) > 20:
        d["files"] = files[:20]
        d["omitted_files"] = len(files) - 20
    return d


@mcp.tool()
def scifi_kaggle_status() -> dict[str, Any]:
    """
    Check Kaggle authentication status, credential source, and default datasets folder.
    """
    return KaggleClient().status()


@mcp.tool()
def scifi_kaggle_push_dataset(
    folder: str,
    title: str | None = None,
    slug: str | None = None,
    is_private: bool = True,
    version_notes: str = "Uploaded via SciFi",
    create_new: bool = False,
) -> dict[str, Any]:
    """
    Create a new Kaggle dataset or push a new version from a local folder.
    """
    return KaggleClient().push_dataset(
        folder=folder,
        title=title,
        slug=slug,
        is_private=is_private,
        version_notes=version_notes,
        create_new=create_new,
    )


@mcp.tool()
def scifi_kaggle_competition_list(
    search: str | None = None,
    category: str | None = None,
    page: int = 1,
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    List Kaggle competitions with optional search and category filters.
    """
    comps = KaggleClient().list_competitions(search=search, category=category, page=page, max_results=max_results)
    return [c.to_dict() for c in comps]


@mcp.tool()
def scifi_kaggle_competition_download(
    competition: str,
    dest_dir: str | None = None,
    file_name: str | None = None,
    unzip: bool = True,
) -> dict[str, Any]:
    """
    Download Kaggle competition data files into the default datasets folder (or `dest_dir`).
    """
    res = KaggleClient().download_competition(
        competition=competition, dest_dir=dest_dir, file_name=file_name, unzip=unzip
    )
    return res.to_dict()


@mcp.tool()
def scifi_kaggle_competition_submit(
    competition: str,
    file_path: str,
    message: str = "Submitted via SciFi",
) -> dict[str, Any]:
    """
    Submit a prediction file to a Kaggle competition.
    """
    return KaggleClient().submit_competition(competition=competition, file_path=file_path, message=message)


@mcp.tool()
def scifi_kaggle_kernel_list(
    search: str | None = None,
    user: str | None = None,
    dataset: str | None = None,
    competition: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """
    List Kaggle kernels/notebooks.
    """
    kernels = KaggleClient().list_kernels(
        search=search,
        user=user,
        dataset=dataset,
        competition=competition,
        page=page,
        page_size=page_size,
    )
    return [k.to_dict() for k in kernels]


@mcp.tool()
def scifi_kaggle_kernel_pull(kernel_ref: str, dest_dir: str | None = None) -> dict[str, Any]:
    """
    Pull a Kaggle kernel's source code and `kernel-metadata.json` locally.
    """
    return KaggleClient().pull_kernel(kernel_ref=kernel_ref, dest_dir=dest_dir)


@mcp.tool()
def scifi_kaggle_kernel_push(folder: str) -> dict[str, Any]:
    """
    Push a local kernel folder (with `kernel-metadata.json`) to Kaggle and trigger execution.
    """
    return KaggleClient().push_kernel(folder=folder)


@mcp.tool()
def scifi_kaggle_kernel_status(kernel_ref: str) -> dict[str, Any]:
    """
    Check the execution status of a Kaggle kernel.
    """
    return KaggleClient().kernel_status(kernel_ref=kernel_ref)


@mcp.tool()
def scifi_kaggle_kernel_output(kernel_ref: str, dest_dir: str | None = None) -> dict[str, Any]:
    """
    Download output files and execution logs of a Kaggle kernel.
    """
    return KaggleClient().kernel_output(kernel_ref=kernel_ref, dest_dir=dest_dir)
