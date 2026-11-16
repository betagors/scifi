"""
Resilient HTTP helpers for dataset downloads: retry with backoff and atomic .part streaming.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import requests

DEFAULT_RETRY_STATUSES = (429, 500, 502, 503, 504)


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    retry_statuses: tuple[int, ...] = DEFAULT_RETRY_STATUSES,
    **kwargs: Any,
) -> requests.Response:
    """
    Execute an HTTP request via `session.request` with exponential backoff
    on transient RequestException or retryable HTTP status codes.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.request(method=method.upper(), url=url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            time.sleep(backoff_base * (2**attempt))
            continue

        if resp.status_code in retry_statuses and attempt < max_retries:
            retry_after = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
            delay = backoff_base * (2**attempt)
            if retry_after:
                try:
                    delay = max(delay, min(float(retry_after), 30.0))
                except ValueError:
                    pass
            time.sleep(delay)
            continue

        return resp

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"Request failed after {max_retries} retries: {url}")


def get_with_retry(
    session: requests.Session,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
    retry_statuses: tuple[int, ...] = DEFAULT_RETRY_STATUSES,
    **kwargs: Any,
) -> requests.Response:
    """
    Execute a GET request via `session.get` with exponential backoff on transient
    RequestException or retryable HTTP status codes.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            resp = session.get(url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= max_retries:
                raise
            time.sleep(backoff_base * (2**attempt))
            continue

        if resp.status_code in retry_statuses and attempt < max_retries:
            retry_after = resp.headers.get("Retry-After") if hasattr(resp, "headers") else None
            delay = backoff_base * (2**attempt)
            if retry_after:
                try:
                    delay = max(delay, min(float(retry_after), 30.0))
                except ValueError:
                    pass
            time.sleep(delay)
            continue

        return resp

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(f"GET request failed after {max_retries} retries: {url}")


def stream_to_file(resp: requests.Response, target_file: Path, chunk_size: int = 1024 * 256) -> int:
    """
    Stream a response body into a `.part` temporary file and atomically rename
    to `target_file` on completion. Removes `.part` on failure.
    """
    target_file.parent.mkdir(parents=True, exist_ok=True)
    part_file = target_file.with_name(target_file.name + ".part")
    total = 0
    try:
        with open(part_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    total += len(chunk)
        os.replace(part_file, target_file)
    except Exception:
        if part_file.exists():
            try:
                part_file.unlink()
            except OSError:
                pass
        raise
    return total
