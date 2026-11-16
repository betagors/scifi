"""
Unified Dataset Manager coordinating Kaggle, Hugging Face, Zenodo, Direct URL,
and the default local datasets folder (`datasets_dir`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scifi.config import get_datasets_dir, set_global_config_value
from scifi.datasets.inspector import inspect_dataset
from scifi.datasets.kaggle import KaggleAuthError, KaggleClient
from scifi.datasets.models import DatasetInfo, DownloadResult, LocalDatasetRecord
from scifi.datasets.providers import DirectURLDownloader, HuggingFaceClient, ZenodoClient
from scifi.datasets.store import DatasetManifestStore

PROVIDER_ALIASES = {
    "kaggle": "kaggle",
    "kg": "kaggle",
    "hf": "huggingface",
    "huggingface": "huggingface",
    "zenodo": "zenodo",
    "url": "url",
    "http": "url",
    "https": "url",
}


def normalize_provider(provider: str) -> str:
    key = provider.strip().lower()
    if key not in PROVIDER_ALIASES:
        raise ValueError(f"Unknown dataset provider {provider!r}. Supported: kaggle, huggingface (hf), zenodo, url.")
    return PROVIDER_ALIASES[key]


class DatasetManager:
    """Unified facade for searching, downloading, and tracking datasets."""

    def __init__(
        self,
        datasets_dir: Path | str | None = None,
        workspace_dir: Path | str | None = None,
    ) -> None:
        self.workspace_dir = workspace_dir
        self.datasets_dir = get_datasets_dir(workspace_dir=workspace_dir, override=datasets_dir)
        self.store = DatasetManifestStore(self.datasets_dir)
        self.kaggle = KaggleClient(workspace_dir=workspace_dir)
        self.huggingface = HuggingFaceClient(workspace_dir=workspace_dir)
        self.zenodo = ZenodoClient(workspace_dir=workspace_dir)
        self.url_downloader = DirectURLDownloader(workspace_dir=workspace_dir)

    @staticmethod
    def set_default_dir(path: Path | str) -> Path:
        """Persist a new global default `datasets_dir` in ~/.scifi/config.json."""
        resolved = Path(path).expanduser().resolve()
        resolved.mkdir(parents=True, exist_ok=True)
        set_global_config_value("datasets_dir", str(resolved))
        return resolved

    def search(
        self,
        query: str,
        provider: str = "all",
        limit: int = 15,
    ) -> dict[str, Any]:
        """Search datasets across one or all supported providers."""
        prov = provider.strip().lower()
        targets = ["kaggle", "huggingface", "zenodo"] if prov == "all" else [normalize_provider(prov)]
        results: list[DatasetInfo] = []
        errors: dict[str, str] = {}

        for target in targets:
            try:
                if target == "kaggle":
                    results.extend(self.kaggle.search_datasets(query, max_results=limit))
                elif target == "huggingface":
                    results.extend(self.huggingface.search_datasets(query, limit=limit))
                elif target == "zenodo":
                    results.extend(self.zenodo.search_datasets(query, limit=limit))
            except KaggleAuthError as exc:
                errors["kaggle"] = str(exc)
            except Exception as exc:
                errors[target] = str(exc)

        return {
            "query": query,
            "provider": prov,
            "count": len(results),
            "results": [r.to_dict() for r in results],
            "errors": errors,
        }

    def download(
        self,
        source: str,
        identifier: str,
        dest_dir: Path | str | None = None,
        unzip: bool = True,
        file_name: str | None = None,
    ) -> DownloadResult:
        """
        Download a dataset from `kaggle`, `huggingface`, `zenodo`, or `url`
        into `dest_dir` (or `<default_datasets_dir>/<provider>/<slug>`).
        """
        # Support prefix syntax if source == "auto"
        if source.strip().lower() == "auto":
            if identifier.startswith(("http://", "https://")):
                prov = "url"
            elif ":" in identifier and identifier.split(":", 1)[0].lower() in PROVIDER_ALIASES:
                prefix, identifier = identifier.split(":", 1)
                prov = normalize_provider(prefix)
            else:
                prov = "kaggle"
        else:
            prov = normalize_provider(source)

        # Ensure default target folder uses self.datasets_dir when dest_dir is None
        if dest_dir is None:
            from scifi.datasets.store import sanitize_dataset_slug

            if prov == "zenodo":
                rec_id = self.zenodo._extract_record_id(identifier)
                target_dir: Path | str = self.datasets_dir / "zenodo" / f"zenodo_{rec_id}"
            elif prov == "url":
                target_dir = self.datasets_dir / "url" / sanitize_dataset_slug(identifier)
            else:
                target_dir = self.datasets_dir / prov / sanitize_dataset_slug(identifier)
        else:
            target_dir = dest_dir

        if prov == "kaggle":
            res = self.kaggle.download_dataset(identifier, dest_dir=target_dir, file_name=file_name, unzip=unzip)
        elif prov == "huggingface":
            files_arg = [file_name] if file_name else None
            res = self.huggingface.download_dataset(identifier, dest_dir=target_dir, files=files_arg, unzip=unzip)
        elif prov == "zenodo":
            files_arg = [file_name] if file_name else None
            res = self.zenodo.download_dataset(identifier, dest_dir=target_dir, files=files_arg, unzip=unzip)
        elif prov == "url":
            res = self.url_downloader.download_url(identifier, dest_dir=target_dir, filename=file_name, unzip=unzip)
        else:
            raise ValueError(f"Unsupported provider: {prov}")

        self.store.register(
            provider=res.provider,
            identifier=res.identifier,
            local_path=res.local_path,
            title=res.identifier,
        )
        return res

    def list_local(self) -> list[LocalDatasetRecord]:
        """List all locally tracked datasets in `datasets_dir`."""
        return self.store.list_local()

    def remove_local(self, identifier: str, delete_files: bool = False) -> bool:
        """Remove a dataset from the local manifest (and optionally delete its files)."""
        return self.store.remove(identifier, delete_files=delete_files)

    def inspect(
        self,
        target: Path | str,
        max_rows: int = 5,
        max_chars: int = 80,
        max_columns: int = 30,
        max_files: int = 20,
    ) -> dict[str, Any]:
        """
        Inspect a dataset file, directory, or tracked dataset identifier
        without dumping full contents into memory or LLM context.
        """
        candidate = Path(target).expanduser()
        if candidate.exists():
            return inspect_dataset(
                candidate,
                max_rows=max_rows,
                max_chars=max_chars,
                max_columns=max_columns,
                max_files=max_files,
            )

        rel_candidate = self.datasets_dir / str(target)
        if rel_candidate.exists():
            return inspect_dataset(
                rel_candidate,
                max_rows=max_rows,
                max_chars=max_chars,
                max_columns=max_columns,
                max_files=max_files,
            )

        target_str = str(target).strip()
        for rec in self.store.list_local():
            key = f"{rec.provider}:{rec.identifier}"
            if target_str == rec.identifier or target_str == key:
                return inspect_dataset(
                    rec.local_path,
                    max_rows=max_rows,
                    max_chars=max_chars,
                    max_columns=max_columns,
                    max_files=max_files,
                )

        raise FileNotFoundError(
            f"Dataset path or identifier not found: {target!r} (searched local path and {self.datasets_dir})"
        )
