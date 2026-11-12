"""
Centralized structured logging infrastructure for the SciFi toolkit.
"""
from __future__ import annotations

import logging
import os
import sys

_DEFAULT_LOG_LEVEL = logging.INFO
if os.getenv("SCIFI_DEBUG", "").lower() in ("1", "true", "yes", "on"):
    _DEFAULT_LOG_LEVEL = logging.DEBUG
elif level_name := os.getenv("SCIFI_LOG_LEVEL"):
    _DEFAULT_LOG_LEVEL = getattr(logging, level_name.upper(), logging.INFO)

_ROOT_LOGGER_NAME = "scifi"
_root_logger = logging.getLogger(_ROOT_LOGGER_NAME)
if not _root_logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    _root_logger.addHandler(_handler)
    _root_logger.setLevel(_DEFAULT_LOG_LEVEL)
    # Prevent duplicate emission if parent root logger is configured
    _root_logger.propagate = False


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Obtain a child logger under the centralized 'scifi' logger namespace.

    Args:
        name: Sub-namespace name (e.g. '__name__' or 'server.routers.citations').

    Returns:
        logging.Logger instance configured under the 'scifi' tree.
    """
    if not name:
        return _root_logger
    if name.startswith("scifi."):
        return logging.getLogger(name)
    if name == "scifi":
        return _root_logger
    return logging.getLogger(f"{_ROOT_LOGGER_NAME}.{name}")
