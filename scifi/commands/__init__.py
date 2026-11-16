"""
Subcommand Handlers for the SciFi CLI.
"""

from __future__ import annotations

from scifi.commands.datasets import cmd_datasets, cmd_kaggle
from scifi.commands.doctor import cmd_doctor
from scifi.commands.math import cmd_math, cmd_stats
from scifi.commands.submission import cmd_submission
from scifi.commands.zenodo import cmd_zenodo
from scifi.commands.zotero import cmd_zotero

__all__ = [
    "cmd_datasets",
    "cmd_doctor",
    "cmd_kaggle",
    "cmd_math",
    "cmd_stats",
    "cmd_submission",
    "cmd_zenodo",
    "cmd_zotero",
]
