"""
scifi.latex.tables — Publication-Grade LaTeX `booktabs` Table Generator.

Converts experimental evaluation results (CSV, JSON, or list of dicts) into
journal- and conference-ready LaTeX `booktabs` tables (`\\toprule`, `\\midrule`, `\\bottomrule`),
automatically highlighting:
- Best metric in `\\textbf{...}`
- Second-best metric in `\\underline{...}`
- Paired standard deviation / confidence interval columns (`mean \\pm std`)
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any


def _try_float(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return None if math.isnan(float(val)) else float(val)
    s = str(val).strip()
    if not s:
        return None
    # Strip trailing % or ± part if raw
    if "±" in s:
        s = s.split("±", 1)[0].strip()
    elif "\\pm" in s:
        s = s.split("\\pm", 1)[0].strip()
    try:
        return float(s)
    except ValueError:
        return None


def _escape_latex(text: str) -> str:
    """Escape special LaTeX characters in plain labels while leaving math/macros intact."""
    if "\\" in text or "$" in text:
        return text
    out = text.replace("&", "\\&").replace("%", "\\%").replace("_", "\\_").replace("#", "\\#")
    return out


def _load_table_rows(data_input: str | Path | list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    """Load table columns and rows from CSV file, JSON file, JSON string, or list of dicts."""
    if isinstance(data_input, list):
        if not data_input:
            raise ValueError("Data list is empty.")
        cols = list(data_input[0].keys())
        return cols, data_input

    if isinstance(data_input, Path) or (isinstance(data_input, str) and "\n" not in data_input and Path(data_input).is_file()):
        p = Path(data_input)
        content = p.read_text(encoding="utf-8", errors="replace")
        if p.suffix.lower() == ".json":
            parsed = json.loads(content)
            if isinstance(parsed, dict) and "rows" in parsed:
                parsed = parsed["rows"]
            if not isinstance(parsed, list) or not parsed:
                raise ValueError(f"JSON file {p} must contain a non-empty list of row objects.")
            return list(parsed[0].keys()), parsed
        else:
            reader = csv.DictReader(content.splitlines())
            rows = list(reader)
            if not rows:
                raise ValueError(f"CSV file {p} contains no data rows.")
            return list(reader.fieldnames or rows[0].keys()), rows

    # Try parsing as raw JSON or CSV text
    raw = str(data_input).strip()
    if raw.startswith("[") or raw.startswith("{"):
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and "rows" in parsed:
            parsed = parsed["rows"]
        if not isinstance(parsed, list) or not parsed:
            raise ValueError("JSON input must be a non-empty list of row objects.")
        return list(parsed[0].keys()), parsed

    if "\n" in raw:
        reader = csv.DictReader(raw.splitlines())
        rows = list(reader)
        if rows:
            return list(reader.fieldnames or rows[0].keys()), rows

    raise FileNotFoundError(f"Data file not found or invalid table input: {data_input}")


def generate_latex_table(
    data_input: str | Path | list[dict[str, Any]],
    caption: str = "Experimental comparison against state-of-the-art baselines.",
    label: str = "tab:results",
    lower_is_better: list[str] | None = None,
    precision: int = 2,
    highlight_best: bool = True,
    highlight_second: bool = True,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Generate a publication-grade LaTeX `booktabs` table from experimental data.

    Features:
    - Auto-pairs `<metric>_std` or `<metric>_ci` columns with `<metric>` as `$mean \\pm std$`.
    - Bolds the best metric (`\\textbf{...}`) and underlines the second-best (`\\underline{...}`).
    - Supports `lower_is_better` column list (e.g. `["RMSE", "Latency", "Params"]`).
    """
    try:
        all_columns, rows = _load_table_rows(data_input)
    except Exception as e:
        return {
            "status": "ERROR",
            "error_message": str(e),
        }

    lower_set = {c.strip().lower() for c in (lower_is_better or []) if c.strip()}

    # Identify paired std/ci columns (e.g., Acc_std paired with Acc)
    std_map: dict[str, str] = {}
    skip_cols: set[str] = set()
    col_lookup = {c.lower(): c for c in all_columns}

    for col in all_columns:
        cl = col.lower()
        for suffix in ("_std", "_ci", "_se", "_err"):
            if cl.endswith(suffix):
                base_lower = cl[: -len(suffix)]
                if base_lower in col_lookup:
                    base_col = col_lookup[base_lower]
                    std_map[base_col] = col
                    skip_cols.add(col)

    display_columns = [c for c in all_columns if c not in skip_cols]

    # Determine which columns are numeric and find best / second-best values
    numeric_cols: dict[str, bool] = {}
    best_vals: dict[str, float | None] = {}
    second_vals: dict[str, float | None] = {}

    for col in display_columns:
        vals: list[float] = []
        for r in rows:
            v = _try_float(r.get(col))
            if v is not None:
                vals.append(v)
        is_num = len(vals) >= max(1, len(rows) // 2)
        numeric_cols[col] = is_num
        if is_num and vals:
            unique_sorted = sorted(set(vals), reverse=(col.lower() not in lower_set))
            best_vals[col] = unique_sorted[0]
            second_vals[col] = unique_sorted[1] if len(unique_sorted) > 1 else None
        else:
            best_vals[col] = None
            second_vals[col] = None

    # Alignment spec: 'l' for first/text columns, 'c' for numeric metric columns
    align_spec = "".join("c" if (idx > 0 and numeric_cols.get(c, False)) else "l" for idx, c in enumerate(display_columns))

    # Format header row
    header_cells: list[str] = []
    for col in display_columns:
        h = _escape_latex(col)
        if numeric_cols.get(col, False):
            arrow = "$\\downarrow$" if col.lower() in lower_set else "$\\uparrow$"
            h = f"\\textbf{{{h}}} {arrow}"
        else:
            h = f"\\textbf{{{h}}}"
        header_cells.append(h)

    body_lines: list[str] = []
    for r in rows:
        row_cells: list[str] = []
        for idx, col in enumerate(display_columns):
            raw_val = r.get(col, "")
            num_val = _try_float(raw_val)
            if idx == 0 or not numeric_cols.get(col, False) or num_val is None:
                row_cells.append(_escape_latex(str(raw_val)))
                continue

            formatted_num = f"{num_val:.{precision}f}"
            std_col = std_map.get(col)
            std_str = ""
            if std_col and _try_float(r.get(std_col)) is not None:
                std_v = _try_float(r.get(std_col))
                std_str = f" \\pm {std_v:.{precision}f}"

            b_val = best_vals.get(col)
            s_val = second_vals.get(col)

            if highlight_best and b_val is not None and math.isclose(num_val, b_val, rel_tol=1e-9, abs_tol=1e-9):
                if std_str:
                    cell_str = f"$\\mathbf{{{formatted_num}{std_str}}}$"
                else:
                    cell_str = f"\\textbf{{{formatted_num}}}"
            elif highlight_second and s_val is not None and math.isclose(num_val, s_val, rel_tol=1e-9, abs_tol=1e-9):
                if std_str:
                    cell_str = f"\\underline{{${formatted_num}{std_str}$}}"
                else:
                    cell_str = f"\\underline{{{formatted_num}}}"
            else:
                if std_str:
                    cell_str = f"${formatted_num}{std_str}$"
                else:
                    cell_str = formatted_num

            row_cells.append(cell_str)

        body_lines.append("    " + " & ".join(row_cells) + " \\\\")

    latex_lines = [
        "\\begin{table}[t]",
        "  \\centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{{label}}}",
        f"  \\begin{{tabular}}{{{align_spec}}}",
        "    \\toprule",
        "    " + " & ".join(header_cells) + " \\\\",
        "    \\midrule",
        *body_lines,
        "    \\bottomrule",
        "  \\end{tabular}",
        "\\end{table}",
    ]
    latex_code = "\n".join(latex_lines)

    saved_path: str | None = None
    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(latex_code + "\n", encoding="utf-8")
        saved_path = str(out_p.resolve())

    return {
        "status": "SUCCESS",
        "columns": display_columns,
        "rows_count": len(rows),
        "best_values": best_vals,
        "second_best_values": second_vals,
        "latex": latex_code,
        "output_path": saved_path,
    }
