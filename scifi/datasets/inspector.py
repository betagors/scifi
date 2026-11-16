"""
Token-efficient dataset inspection for SciFi.

Provides compact schema, size, file breakdown, and bounded sample previews
so AI agents and researchers can understand datasets without dumping large
files or thousands of filenames into the context window.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

_TABULAR_PRIORITY = (
    ".parquet",
    ".csv",
    ".tsv",
    ".jsonl",
    ".ndjson",
    ".json",
    ".sqlite",
    ".db",
    ".sqlite3",
    ".xlsx",
    ".xls",
    ".feather",
    ".arrow",
)

_EXACT_LINE_COUNT_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
_FULL_JSON_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def format_bytes(num_bytes: int | None) -> str:
    """Format byte count as a compact human-readable string."""
    if num_bytes is None:
        return "?"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{num_bytes} B"


def truncate_str(value: str, max_chars: int = 80) -> str:
    """Collapse newlines and truncate long strings with total length annotation."""
    compact = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    if len(compact) <= max_chars:
        return compact
    return f"{compact[:max_chars]}... [{len(compact)} chars]"


def truncate_value(value: Any, max_chars: int = 80, max_items: int = 5, _depth: int = 0) -> Any:
    """Recursively bound strings, lists, and dicts so nested records stay token-safe."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate_str(value, max_chars=max_chars)
    if isinstance(value, bytes):
        return f"<bytes: {len(value)}>"
    if _depth >= 3:
        if isinstance(value, list):
            return f"<list[{len(value)}]>"
        if isinstance(value, dict):
            return f"<dict[{len(value)}]>"
        return truncate_str(str(value), max_chars=max_chars)
    if isinstance(value, list):
        items = [
            truncate_value(v, max_chars=max_chars, max_items=max_items, _depth=_depth + 1) for v in value[:max_items]
        ]
        if len(value) > max_items:
            items.append(f"... [+{len(value) - max_items} more]")
        return items
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        keys = list(value.keys())
        for k in keys[:max_items]:
            out[str(k)] = truncate_value(value[k], max_chars=max_chars, max_items=max_items, _depth=_depth + 1)
        if len(keys) > max_items:
            out["__omitted_keys__"] = len(keys) - max_items
        return out
    return truncate_str(str(value), max_chars=max_chars)


def _infer_scalar_type(raw: str) -> str:
    val = raw.strip()
    if val == "" or val.lower() in {"na", "n/a", "nan", "null", "none"}:
        return "null"
    if val.lower() in {"true", "false"}:
        return "bool"
    try:
        int(val)
        return "int"
    except ValueError:
        pass
    try:
        float(val)
        return "float"
    except ValueError:
        pass
    return "str"


def _merge_types(types_seen: set[str]) -> str:
    non_null = types_seen - {"null"}
    if not non_null:
        return "null"
    if non_null == {"int"}:
        return "int"
    if non_null <= {"int", "float"}:
        return "float"
    if non_null == {"bool"}:
        return "bool"
    if len(non_null) == 1:
        return next(iter(non_null))
    return "mixed"


def _count_or_estimate_lines(path: Path, size_bytes: int) -> tuple[int, bool]:
    """Count lines exactly up to 50 MB; estimate from a 1 MB sample for larger files."""
    if size_bytes == 0:
        return 0, False
    if size_bytes <= _EXACT_LINE_COUNT_MAX_BYTES:
        lines = 0
        with open(path, "rb") as f:
            while chunk := f.read(1024 * 1024):
                lines += chunk.count(b"\n")
        return max(lines, 1), False

    sample_bytes = 1024 * 1024
    with open(path, "rb") as f:
        chunk = f.read(sample_bytes)
    newlines = chunk.count(b"\n")
    if newlines == 0:
        return 1, True
    avg_line_len = len(chunk) / newlines
    return max(int(size_bytes / avg_line_len), 1), True


def _detect_delimiter(path: Path, sample_text: str) -> str:
    ext = path.suffix.lower()
    if ext == ".tsv":
        return "\t"
    try:
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


def _inspect_delimited(
    path: Path,
    size_bytes: int,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
) -> dict[str, Any]:
    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        head_chunk = f.read(8192)
    delimiter = _detect_delimiter(path, head_chunk)

    total_lines, estimated = _count_or_estimate_lines(path, size_bytes)
    row_count = max(total_lines - 1, 0)

    headers: list[str] = []
    sample_rows: list[dict[str, Any]] = []
    col_types: list[set[str]] = []
    col_nulls: list[int] = []
    scanned_rows = 0

    with open(path, encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.reader(f, delimiter=delimiter)
        try:
            headers = next(reader)
        except StopIteration:
            headers = []

        num_cols = len(headers)
        col_types = [set() for _ in range(num_cols)]
        col_nulls = [0 for _ in range(num_cols)]

        for row in reader:
            scanned_rows += 1
            for idx in range(min(len(row), num_cols)):
                inferred = _infer_scalar_type(row[idx])
                col_types[idx].add(inferred)
                if inferred == "null":
                    col_nulls[idx] += 1
            if len(sample_rows) < max_rows:
                rec: dict[str, Any] = {}
                for idx, col_name in enumerate(headers[:max_columns]):
                    val = row[idx] if idx < len(row) else ""
                    rec[col_name] = truncate_str(val, max_chars=max_chars)
                sample_rows.append(rec)
            if scanned_rows >= max(100, max_rows):
                break

    columns_meta = []
    for idx, name in enumerate(headers[:max_columns]):
        columns_meta.append(
            {
                "name": truncate_str(name, max_chars=max_chars),
                "type": _merge_types(col_types[idx]) if idx < len(col_types) else "unknown",
                "sample_nulls": col_nulls[idx] if idx < len(col_nulls) else 0,
            }
        )

    return {
        "path": str(path),
        "kind": "file",
        "format": "tsv" if delimiter == "\t" else "csv",
        "delimiter": delimiter,
        "size_bytes": size_bytes,
        "size_human": format_bytes(size_bytes),
        "row_count": row_count,
        "row_count_estimated": estimated,
        "column_count": len(headers),
        "columns": columns_meta,
        "omitted_columns": max(0, len(headers) - max_columns),
        "sample_scanned_rows": scanned_rows,
        "sample_rows": sample_rows,
    }


def _inspect_jsonl(
    path: Path,
    size_bytes: int,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
) -> dict[str, Any]:
    total_lines, estimated = _count_or_estimate_lines(path, size_bytes)
    key_types: dict[str, set[str]] = {}
    sample_rows: list[Any] = []
    scanned = 0

    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            scanned += 1
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                obj = {"_raw": truncate_str(stripped, max_chars=max_chars)}
            if isinstance(obj, dict):
                for k, v in list(obj.items())[:max_columns]:
                    t = "null" if v is None else type(v).__name__
                    key_types.setdefault(str(k), set()).add(t)
            if len(sample_rows) < max_rows:
                sample_rows.append(truncate_value(obj, max_chars=max_chars))
            if scanned >= max(100, max_rows):
                break

    columns_meta = [{"name": k, "type": _merge_types(ts)} for k, ts in list(key_types.items())[:max_columns]]

    return {
        "path": str(path),
        "kind": "file",
        "format": "jsonl",
        "size_bytes": size_bytes,
        "size_human": format_bytes(size_bytes),
        "row_count": total_lines,
        "row_count_estimated": estimated,
        "column_count": len(key_types),
        "columns": columns_meta,
        "omitted_columns": max(0, len(key_types) - max_columns),
        "sample_rows": sample_rows,
    }


def _inspect_json(
    path: Path,
    size_bytes: int,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
) -> dict[str, Any]:
    if size_bytes > _FULL_JSON_MAX_BYTES:
        with open(path, encoding="utf-8", errors="replace") as f:
            prefix = f.read(600)
        return {
            "path": str(path),
            "kind": "file",
            "format": "json",
            "size_bytes": size_bytes,
            "size_human": format_bytes(size_bytes),
            "large_file_skipped_full_parse": True,
            "prefix_preview": truncate_str(prefix, max_chars=400),
            "hint": "File exceeds 2 MB; inspect specific keys with streaming JSON or Python rather than loading raw text.",
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return {
            "path": str(path),
            "kind": "file",
            "format": "json",
            "size_bytes": size_bytes,
            "size_human": format_bytes(size_bytes),
            "parse_error": str(exc),
        }

    info: dict[str, Any] = {
        "path": str(path),
        "kind": "file",
        "format": "json",
        "size_bytes": size_bytes,
        "size_human": format_bytes(size_bytes),
        "root_type": type(data).__name__,
    }

    if isinstance(data, list):
        info["row_count"] = len(data)
        info["sample_rows"] = [truncate_value(item, max_chars=max_chars) for item in data[:max_rows]]
    elif isinstance(data, dict):
        keys = list(data.keys())
        info["key_count"] = len(keys)
        schema_summary: dict[str, str] = {}
        for k in keys[:max_columns]:
            v = data[k]
            if isinstance(v, list):
                schema_summary[str(k)] = f"list[{len(v)}]"
            elif isinstance(v, dict):
                schema_summary[str(k)] = f"dict[{len(v)}]"
            else:
                schema_summary[str(k)] = type(v).__name__
        info["keys_summary"] = schema_summary
        info["omitted_keys"] = max(0, len(keys) - max_columns)
        info["sample_preview"] = truncate_value(data, max_chars=max_chars, max_items=max_rows)
    else:
        info["sample_preview"] = truncate_value(data, max_chars=max_chars)

    return info


def _inspect_sqlite(
    path: Path,
    size_bytes: int,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
) -> dict[str, Any]:
    tables_out: list[dict[str, Any]] = []
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [row[0] for row in cur.fetchall()]
        for tbl in table_names[:10]:
            quoted = '"' + tbl.replace('"', '""') + '"'
            cur.execute(f"SELECT COUNT(*) FROM {quoted}")
            row_count = cur.fetchone()[0]
            cur.execute(f"PRAGMA table_info({quoted})")
            cols = [{"name": r[1], "type": r[2] or "ANY"} for r in cur.fetchall()]
            sample_rows: list[dict[str, Any]] = []
            if len(tables_out) < 3:
                cur.execute(f"SELECT * FROM {quoted} LIMIT ?", (max_rows,))
                col_names = [c["name"] for c in cols[:max_columns]]
                for row in cur.fetchall():
                    sample_rows.append(
                        {
                            col_names[i]: truncate_value(row[i], max_chars=max_chars)
                            for i in range(min(len(col_names), len(row)))
                        }
                    )
            tables_out.append(
                {
                    "table": tbl,
                    "row_count": row_count,
                    "column_count": len(cols),
                    "columns": cols[:max_columns],
                    "sample_rows": sample_rows,
                }
            )
    finally:
        conn.close()

    return {
        "path": str(path),
        "kind": "file",
        "format": "sqlite",
        "size_bytes": size_bytes,
        "size_human": format_bytes(size_bytes),
        "table_count": len(table_names),
        "tables": tables_out,
        "omitted_tables": max(0, len(table_names) - 10),
    }


def _inspect_parquet(
    path: Path,
    size_bytes: int,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
) -> dict[str, Any]:
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]

        pf = pq.ParquetFile(path)
        schema = pf.schema_arrow
        num_rows = pf.metadata.num_rows
        cols = [{"name": field.name, "type": str(field.type)} for field in list(schema)[:max_columns]]
        sample_rows: list[dict[str, Any]] = []
        if pf.num_row_groups > 0 and max_rows > 0:
            batch = pf.read_row_group(0).slice(0, max_rows).to_pylist()
            for row in batch:
                sample_rows.append(
                    {k: truncate_value(v, max_chars=max_chars) for k, v in list(row.items())[:max_columns]}
                )
        return {
            "path": str(path),
            "kind": "file",
            "format": "parquet",
            "size_bytes": size_bytes,
            "size_human": format_bytes(size_bytes),
            "row_count": num_rows,
            "row_groups": pf.num_row_groups,
            "column_count": len(schema),
            "columns": cols,
            "omitted_columns": max(0, len(schema) - max_columns),
            "sample_rows": sample_rows,
        }
    except ImportError:
        return {
            "path": str(path),
            "kind": "file",
            "format": "parquet",
            "size_bytes": size_bytes,
            "size_human": format_bytes(size_bytes),
            "hint": "Install `pyarrow` to inspect Parquet schema and sample rows without loading the full file.",
        }


def _inspect_text_or_binary(path: Path, size_bytes: int, max_rows: int = 5) -> dict[str, Any]:
    with open(path, "rb") as f:
        head = f.read(1024)
    if b"\x00" in head:
        return {
            "path": str(path),
            "kind": "file",
            "format": path.suffix.lstrip(".").lower() or "binary",
            "size_bytes": size_bytes,
            "size_human": format_bytes(size_bytes),
            "binary": True,
        }

    total_lines, estimated = _count_or_estimate_lines(path, size_bytes)
    preview_lines: list[str] = []
    char_budget = 1200
    used = 0
    line_limit = max(max_rows * 3, 10)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            if len(preview_lines) >= line_limit or used >= char_budget:
                break
            trimmed = line.rstrip("\r\n")
            if len(trimmed) > 160:
                trimmed = trimmed[:160] + "..."
            preview_lines.append(trimmed)
            used += len(trimmed)

    return {
        "path": str(path),
        "kind": "file",
        "format": path.suffix.lstrip(".").lower() or "text",
        "size_bytes": size_bytes,
        "size_human": format_bytes(size_bytes),
        "line_count": total_lines,
        "line_count_estimated": estimated,
        "preview_lines": preview_lines,
    }


def _inspect_directory(
    root: Path,
    max_files: int = 20,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
) -> dict[str, Any]:
    ext_counts: Counter[str] = Counter()
    ext_bytes: Counter[str] = Counter()
    total_files = 0
    total_bytes = 0
    candidates: list[tuple[int, int, str, int, Path]] = []

    priority_map = {ext: idx for idx, ext in enumerate(_TABULAR_PRIORITY)}

    for dirpath, _, filenames in os.walk(root):
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                fsize = fpath.stat().st_size
            except OSError:
                fsize = 0
            total_files += 1
            total_bytes += fsize
            ext = fpath.suffix.lower() or "<no_ext>"
            ext_counts[ext] += 1
            ext_bytes[ext] += fsize
            rel = str(fpath.relative_to(root)).replace("\\", "/")
            prio = priority_map.get(ext, len(_TABULAR_PRIORITY))
            candidates.append((prio, -fsize, rel, fsize, fpath))

    candidates.sort(key=lambda item: (item[0], item[1], item[2]))
    files_preview = [
        {"name": rel, "size_bytes": fsize, "size_human": format_bytes(fsize)}
        for _, _, rel, fsize, _ in candidates[:max_files]
    ]
    by_extension = [
        {
            "extension": ext,
            "count": count,
            "total_bytes": ext_bytes[ext],
            "total_human": format_bytes(ext_bytes[ext]),
        }
        for ext, count in ext_counts.most_common(15)
    ]

    result: dict[str, Any] = {
        "path": str(root),
        "kind": "directory",
        "total_files": total_files,
        "total_bytes": total_bytes,
        "total_human": format_bytes(total_bytes),
        "by_extension": by_extension,
        "files_preview": files_preview,
        "omitted_files": max(0, total_files - len(files_preview)),
    }

    # Automatically inspect the top priority tabular/data file so one call suffices.
    for prio, _, rel, _, fpath in candidates:
        if prio < len(_TABULAR_PRIORITY):
            result["primary_file"] = rel
            result["primary_file_inspection"] = inspect_dataset(
                fpath,
                max_rows=max_rows,
                max_chars=max_chars,
                max_columns=max_columns,
                max_files=max_files,
            )
            break

    return result


def inspect_dataset(
    target: Path | str,
    max_rows: int = 5,
    max_chars: int = 80,
    max_columns: int = 30,
    max_files: int = 20,
) -> dict[str, Any]:
    """
    Inspect a local dataset file or directory in a token-efficient manner.

    Returns compact schema, row/file counts, byte sizes, and a small truncated
    sample without loading or dumping full datasets into LLM context.
    """
    path = Path(target).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Dataset path not found: {path}")

    max_rows = max(0, min(int(max_rows), 50))
    max_chars = max(20, min(int(max_chars), 500))
    max_columns = max(1, min(int(max_columns), 100))
    max_files = max(1, min(int(max_files), 100))

    if path.is_dir():
        return _inspect_directory(
            path,
            max_files=max_files,
            max_rows=max_rows,
            max_chars=max_chars,
            max_columns=max_columns,
        )

    size_bytes = path.stat().st_size
    ext = path.suffix.lower()

    if ext in {".csv", ".tsv"}:
        return _inspect_delimited(
            path,
            size_bytes,
            max_rows=max_rows,
            max_chars=max_chars,
            max_columns=max_columns,
        )
    if ext in {".jsonl", ".ndjson"}:
        return _inspect_jsonl(
            path,
            size_bytes,
            max_rows=max_rows,
            max_chars=max_chars,
            max_columns=max_columns,
        )
    if ext == ".json":
        return _inspect_json(
            path,
            size_bytes,
            max_rows=max_rows,
            max_chars=max_chars,
            max_columns=max_columns,
        )
    if ext in {".db", ".sqlite", ".sqlite3"}:
        return _inspect_sqlite(
            path,
            size_bytes,
            max_rows=max_rows,
            max_chars=max_chars,
            max_columns=max_columns,
        )
    if ext == ".parquet":
        return _inspect_parquet(
            path,
            size_bytes,
            max_rows=max_rows,
            max_chars=max_chars,
            max_columns=max_columns,
        )
    return _inspect_text_or_binary(path, size_bytes, max_rows=max_rows)
