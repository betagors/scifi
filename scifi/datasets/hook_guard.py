"""Antigravity PreToolUse hook guard preventing raw reads of large dataset files."""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAW_DATASET_SUFFIXES = frozenset(
    {".csv", ".tsv", ".jsonl", ".parquet", ".feather", ".sqlite", ".db", ".xlsx", ".h5", ".npz"}
)
JSON_SIZE_LIMIT_BYTES = 32_768


def evaluate_hook(payload: dict) -> dict[str, str]:
    """Evaluate a PreToolUse read_file hook payload and return allow/deny decision."""
    tool_call = payload.get("toolCall")
    args = tool_call.get("args") if isinstance(tool_call, dict) else None
    path_str = args.get("Path", "") if isinstance(args, dict) else ""
    if not isinstance(path_str, str) or not path_str.strip():
        return {"decision": "allow"}

    target = Path(path_str)
    suffix = target.suffix.lower()
    if suffix in RAW_DATASET_SUFFIXES or (
        suffix == ".json" and target.is_file() and target.stat().st_size > JSON_SIZE_LIMIT_BYTES
    ):
        return {
            "decision": "deny",
            "reason": "Use scifi_datasets_inspect (or sf datasets inspect) before reading raw dataset files.",
        }
    return {"decision": "allow"}


def main() -> int:
    """Read Antigravity hook payload from stdin and emit JSON decision on stdout."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    print(json.dumps(evaluate_hook(payload)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
