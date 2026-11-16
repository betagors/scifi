"""
SciFi Dataset & Kaggle Integration Package.
"""

from __future__ import annotations

from scifi.datasets.inspector import inspect_dataset
from scifi.datasets.kaggle import (
    KaggleAPIError,
    KaggleAuthError,
    KaggleClient,
    resolve_kaggle_credentials,
    save_kaggle_credentials,
)
from scifi.datasets.manager import DatasetManager, normalize_provider
from scifi.datasets.models import (
    DatasetFile,
    DatasetInfo,
    DownloadResult,
    KaggleCompetition,
    KaggleKernel,
    KaggleSubmission,
    LocalDatasetRecord,
)
from scifi.datasets.providers import DirectURLDownloader, HuggingFaceClient, ZenodoClient
from scifi.datasets.store import DatasetManifestStore, safe_extract_archive, sanitize_dataset_slug

__all__ = [
    "DatasetFile",
    "DatasetInfo",
    "DatasetManager",
    "DatasetManifestStore",
    "DirectURLDownloader",
    "DownloadResult",
    "HuggingFaceClient",
    "KaggleAPIError",
    "KaggleAuthError",
    "KaggleClient",
    "KaggleCompetition",
    "KaggleKernel",
    "KaggleSubmission",
    "LocalDatasetRecord",
    "ZenodoClient",
    "inspect_dataset",
    "normalize_provider",
    "resolve_kaggle_credentials",
    "save_kaggle_credentials",
    "safe_extract_archive",
    "sanitize_dataset_slug",
]
