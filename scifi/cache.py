"""
SQLite-backed Persistent Registry and Query Caching for SciFi.

Caches Crossref, OpenAlex, arXiv, and other academic registry query responses
to prevent rate limits and ensure instantaneous repeated lookups.
"""

from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time
from typing import Any, Generator


class RegistryCache:
    """
    Persistent SQLite caching layer for academic registry query results.

    Schema:
        registry_cache (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """

    DEFAULT_TTL_SECONDS: int = 604800  # 7 days

    def __init__(self, db_path: Path | str | None = None) -> None:
        """
        Initialize the registry cache with a path to a SQLite database.

        Args:
            db_path: Path to the SQLite database file. Defaults to
                `~/.cache/scifi/cache.db`.
        """
        if db_path is None:
            self.db_path = Path.home() / ".cache" / "scifi" / "cache.db"
        else:
            self.db_path = Path(db_path).expanduser().resolve()

        self._initialized: bool = False

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager yielding an active SQLite connection and guaranteeing closure.
        Automatically creates parent directory and ensures table exists.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        try:
            if not self._initialized:
                with conn:
                    conn.execute(
                        """
                        CREATE TABLE IF NOT EXISTS registry_cache (
                            key TEXT PRIMARY KEY,
                            value_json TEXT NOT NULL,
                            expires_at REAL NOT NULL
                        )
                        """
                    )
                    conn.execute(
                        "CREATE INDEX IF NOT EXISTS idx_expires_at ON registry_cache (expires_at)"
                    )
                self._initialized = True
            yield conn
        finally:
            conn.close()

    def get(self, key: str) -> dict[str, Any] | None:
        """
        Retrieve a cached dictionary by key. Returns None if key is absent or expired.
        Automatically purges expired rows on lookup.

        Args:
            key: Unique lookup key (e.g., DOI, arXiv ID, or normalized query string).

        Returns:
            Cached dictionary if present and unexpired; None otherwise.
        """
        if not self.db_path.exists():
            return None

        now = time.time()
        with self._connection() as conn:
            with conn:
                cursor = conn.execute(
                    "SELECT value_json, expires_at FROM registry_cache WHERE key = ?",
                    (key,),
                )
                row = cursor.fetchone()
                if row is None:
                    return None

                value_json, expires_at = row[0], row[1]
                if expires_at <= now:
                    conn.execute("DELETE FROM registry_cache WHERE key = ?", (key,))
                    return None

                try:
                    return json.loads(value_json)
                except (json.JSONDecodeError, TypeError):
                    return None

    def set(
        self,
        key: str,
        data: dict[str, Any],
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
    ) -> None:
        """
        Store a dictionary under the given key with an expiration TTL.
        Automatically cleans up expired rows on write.

        Args:
            key: Unique cache key.
            data: JSON-serializable dictionary to cache.
            ttl_seconds: Time-to-live in seconds (default: 604800, or 7 days).
                         If <= 0, any existing entry for the key is deleted and
                         the entry is not stored.
        """
        now = time.time()
        with self._connection() as conn:
            with conn:
                # Purge globally expired rows
                conn.execute(
                    "DELETE FROM registry_cache WHERE expires_at <= ?",
                    (now,),
                )

                if ttl_seconds <= 0:
                    conn.execute("DELETE FROM registry_cache WHERE key = ?", (key,))
                    return

                expires_at = now + ttl_seconds
                value_json = json.dumps(data)
                conn.execute(
                    """
                    INSERT OR REPLACE INTO registry_cache (key, value_json, expires_at)
                    VALUES (?, ?, ?)
                    """,
                    (key, value_json, expires_at),
                )

    def delete(self, key: str) -> bool:
        """
        Remove a specific key from the cache.

        Args:
            key: Unique cache key.

        Returns:
            True if a row was deleted, False otherwise.
        """
        if not self.db_path.exists():
            return False

        with self._connection() as conn:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM registry_cache WHERE key = ?",
                    (key,),
                )
                return cursor.rowcount > 0

    def clear(self) -> None:
        """
        Wipe all cached entries from the database.
        """
        if not self.db_path.exists():
            return

        with self._connection() as conn:
            with conn:
                conn.execute("DELETE FROM registry_cache")
