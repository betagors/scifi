"""
Zenodo Deposit & Account Integration Package for SciFi.
"""

from __future__ import annotations

from scifi.zenodo.client import ZENODO_PROD_API, ZENODO_SANDBOX_API, ZenodoDepositClient
from scifi.zenodo.models import ZenodoDeposition, ZenodoFile, ZenodoPushResult

__all__ = [
    "ZENODO_PROD_API",
    "ZENODO_SANDBOX_API",
    "ZenodoDepositClient",
    "ZenodoDeposition",
    "ZenodoFile",
    "ZenodoPushResult",
]
