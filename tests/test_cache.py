"""
Unit tests for SciFi Registry & Query Caching (scifi.cache).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure scifi package is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scifi.cache import RegistryCache


class TestRegistryCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_cache.db"
        self.cache = RegistryCache(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_nonexistent_key_returns_none(self):
        result = self.cache.get("nonexistent_doi_or_query")
        self.assertIsNone(result)

    def test_set_then_get_returns_identical_dict(self):
        data = {
            "title": "Attention Is All You Need",
            "year": 2017,
            "authors": ["Ashish Vaswani", "Noam Shazeer"],
            "doi": "10.48550/arXiv.1706.03762",
            "verified": True,
            "metrics": {"citations": 120000, "score": 9.9},
        }
        self.cache.set("arxiv:1706.03762", data)
        retrieved = self.cache.get("arxiv:1706.03762")
        self.assertEqual(retrieved, data)

    def test_set_with_zero_or_negative_ttl_returns_none(self):
        data = {"title": "Immediate Expire"}
        # Pre-seed a key
        self.cache.set("zero_ttl_key", {"initial": True}, ttl_seconds=3600)
        self.assertIsNotNone(self.cache.get("zero_ttl_key"))

        # Overwrite with ttl_seconds=0
        self.cache.set("zero_ttl_key", data, ttl_seconds=0)
        self.assertIsNone(self.cache.get("zero_ttl_key"))

        # Negative TTL
        self.cache.set("neg_ttl_key", data, ttl_seconds=-60)
        self.assertIsNone(self.cache.get("neg_ttl_key"))

    def test_expired_ttl_returns_none(self):
        current_time = 1000000.0
        data = {"title": "Ephemeral Paper"}

        with mock.patch("time.time", return_value=current_time):
            self.cache.set("ephemeral_key", data, ttl_seconds=300)

        # Before expiration
        with mock.patch("time.time", return_value=current_time + 150):
            self.assertEqual(self.cache.get("ephemeral_key"), data)

        # After expiration
        with mock.patch("time.time", return_value=current_time + 301):
            self.assertIsNone(self.cache.get("ephemeral_key"))

    def test_clear_wipes_all_entries(self):
        self.cache.set("k1", {"id": 1})
        self.cache.set("k2", {"id": 2})
        self.cache.set("k3", {"id": 3})

        self.assertIsNotNone(self.cache.get("k1"))
        self.assertIsNotNone(self.cache.get("k2"))
        self.assertIsNotNone(self.cache.get("k3"))

        self.cache.clear()

        self.assertIsNone(self.cache.get("k1"))
        self.assertIsNone(self.cache.get("k2"))
        self.assertIsNone(self.cache.get("k3"))

    def test_overwrite_existing_key(self):
        self.cache.set("dup_key", {"version": 1})
        self.assertEqual(self.cache.get("dup_key"), {"version": 1})

        self.cache.set("dup_key", {"version": 2})
        self.assertEqual(self.cache.get("dup_key"), {"version": 2})

    def test_automatic_parent_directory_creation(self):
        nested_db = Path(self.temp_dir.name) / "deep" / "nested" / "dir" / "cache.db"
        nested_cache = RegistryCache(db_path=nested_db)
        nested_cache.set("key", {"value": True})
        self.assertEqual(nested_cache.get("key"), {"value": True})

    def test_default_db_path(self):
        default_cache = RegistryCache()
        expected = Path.home() / ".cache" / "scifi" / "cache.db"
        self.assertEqual(default_cache.db_path, expected)

    def test_delete_existing_and_missing_key(self):
        self.cache.set("del_key", {"to_delete": True})
        self.assertTrue(self.cache.delete("del_key"))
        self.assertIsNone(self.cache.get("del_key"))
        self.assertFalse(self.cache.delete("del_key"))

    def test_delete_and_clear_on_nonexistent_db(self):
        empty_db_path = Path(self.temp_dir.name) / "does_not_exist.db"
        empty_cache = RegistryCache(db_path=empty_db_path)
        self.assertFalse(empty_cache.delete("random_key"))
        empty_cache.clear()  # should not raise
        self.assertIsNone(empty_cache.get("random_key"))

    def test_expired_rows_purged_on_write(self):
        t0 = 2000000.0
        with mock.patch("time.time", return_value=t0):
            self.cache.set("old_key", {"old": True}, ttl_seconds=50)

        # Write new key at t0 + 100 (old_key expired)
        with mock.patch("time.time", return_value=t0 + 100):
            self.cache.set("new_key", {"new": True}, ttl_seconds=300)

            # Query database directly to confirm old_key row was deleted
            with self.cache._connection() as conn:
                cursor = conn.execute("SELECT count(*) FROM registry_cache WHERE key = 'old_key'")
                count = cursor.fetchone()[0]
                self.assertEqual(count, 0)

    def test_corrupted_json_handling(self):
        self.cache.set("valid_key", {"a": 1})
        # Manually corrupt the JSON in DB
        with self.cache._connection() as conn:
            with conn:
                conn.execute("UPDATE registry_cache SET value_json = 'INVALID_JSON{' WHERE key = 'valid_key'")
        self.assertIsNone(self.cache.get("valid_key"))


if __name__ == "__main__":
    unittest.main()
