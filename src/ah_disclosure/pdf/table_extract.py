from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from statistics import median
from typing import Iterable, Sequence


_HEADER_WORDS = {
    "item",
    "name",
    "date",
    "period",
    "amount",
    "total",
    "项目",
    "科目",
    "名称",
    "日期",
    "期间",
    "金额",
    "单位",
    "合计",
    "本期",
    "上期",
    "期末",
    "期初",
}
_NUMBER_RE = re.compile(
    r"^\(?[-+]?\s*(?:[$¥￥€£]\s*)?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?\)?$"
)
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}(?:年|年度)?$")


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_data_number(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return True
    text = str(value).strip()
    if not text or _YEAR_RE.fullmatch(text):
        return False
    return bool(_NUMBER_RE.fullmatch(text))


def _numeric_ratio(rows: Sequence[Sequence[object]]) -> float:
    values = [cell for row in rows for cell in row if not _is_blank(cell)]
    if not values:
        return 0.0
    return sum(_is_data_number(cell) for cell in values) / len(values)


def _header_word_ratio(rows: Sequence[Sequence[object]]) -> float:
    values = [str(cell).strip().lower() for row in rows for cell in row if not _is_blank(cell)]
    if not values:
        return 0.0
    matches = sum(any(word in value for word in _HEADER_WORDS) for value in values)
    return matches / len(values)


def _column_paths(header_rows: Sequence[Sequence[object]], column_count: int) -> list[list[str]]:
    paths: list[list[str]] = [[] for _ in range(column_count)]
    for row in header_rows:
        carried: str | None = None
        for column_index in range(column_count):
            cell = row[column_index] if column_index < len(row) else None
            if not _is_blank(cell):
                carried = str(cell).strip()
            if carried and (not paths[column_index] or paths[column_index][-1] != carried):
                paths[column_index].append(carried)
    return paths


def infer_table_structure(
    raw_rows: Sequence[Sequence[object]],
    *,
    max_header_depth: int = 3,
    confidence_threshold: float = 0.60,
) -> dict:
    """Infer table structure without mutating or normalizing the supplied rows."""
    rows = [list(row) for row in raw_rows]
    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    flags: list[str] = []

    if not rows or column_count == 0:
        return {
            "header_depth": 0,
            "confidence": 0.0,
            "column_paths": [],
            "body_start_row": 0,
            "row_count": row_count,
            "column_count": column_count,
            "quality_flags": ["empty_table"],
        }

    if any(len(row) != column_count for row in rows):
        flags.append("ragged_rows")
    if any(cell is None for row in rows for cell in row):
        flags.append("contains_null_cells")
    if any(all(_is_blank(cell) for cell in row) for row in rows):
        flags.append("blank_rows")

    candidate_limit = min(max(0, max_header_depth), max(0, row_count - 1))
    candidates: list[tuple[float, int]] = []
    for depth in range(1, candidate_limit + 1):
        header_rows = rows[:depth]
        body_sample = rows[depth : depth + 5]
        header_numeric = _numeric_ratio(header_rows)
        body_row_ratios = [_numeric_ratio([row]) for row in body_sample]
        body_numeric = median(body_row_ratios) if body_row_ratios else 0.0
        first_body_numeric = body_row_ratios[0] if body_row_ratios else 0.0
        # 表头边界应紧邻首个数据行；使用整个 body 的中位数会把下一层表头误当作数据。
        boundary = max(0.0, first_body_numeric - header_numeric)
        nonblank_header = [cell for row in header_rows for cell in row if not _is_blank(cell)]
        label_ratio = (
            sum(not _is_data_number(cell) for cell in nonblank_header) / len(nonblank_header)
            if nonblank_header
            else 0.0
        )
        merged_hint = min(
            1.0,
            sum(_is_blank(cell) for row in header_rows for cell in row)
            / max(1, depth * column_count),
        )
        lexical_hint = min(1.0, _header_word_ratio(header_rows) * 3)
        score = (
            0.55 * boundary
            + 0.20 * label_ratio
            + 0.15 * lexical_hint
            + 0.05 * body_numeric
            + 0.05 * merged_hint
        )
        candidates.append((min(1.0, score), depth))

    confidence, header_depth = max(candidates, default=(0.0, 0))
    confidence = round(confidence, 3)
    if confidence < confidence_threshold:
        header_depth = 0
        flags.append("header_low_confidence")
    else:
        flags.append("header_inferred")

    if header_depth >= row_count:
        flags.append("no_body_rows")

    return {
        "header_depth": header_depth,
        "confidence": confidence,
        "column_paths": _column_paths(rows[:header_depth], column_count)
        if header_depth
        else [],
        "body_start_row": header_depth,
        "row_count": row_count,
        "column_count": column_count,
        "quality_flags": flags,
    }


def _write_table_artifacts(table: Sequence[Sequence[object]], csv_path: Path) -> dict:
    raw_rows = [list(row) for row in table]
    structure = infer_table_structure(raw_rows)

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
        writer.writerows([["" if cell is None else cell for cell in row] for row in raw_rows])

    structure_path = csv_path.with_suffix(".json")
    payload = {"raw_rows": raw_rows, **structure}
    with structure_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    return {"structure_path": str(structure_path), "quality_flags": structure["quality_flags"]}


def extract_tables(
    pdf_path: str | Path,
    output_dir: str | Path,
    pages: Iterable[int] | None = None,
) -> list[dict]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for pattern in ("page_*_table_*.csv", "page_*_table_*.json"):
        for stale_path in out.glob(pattern):
            stale_path.unlink()
    results: list[dict] = []
    try:
        import pdfplumber

        wanted = set(pages or [])
        with pdfplumber.open(str(pdf_path)) as pdf:
            for idx, page in enumerate(pdf.pages, start=1):
                if wanted and idx not in wanted:
                    continue
                tables = page.extract_tables() or []
                for table_index, table in enumerate(tables, start=1):
                    path = out / f"page_{idx}_table_{table_index}.csv"
                    artifacts = _write_table_artifacts(table, path)
                    results.append(
                        {
                            "page_no": idx,
                            "table_index": table_index,
                            "table_path": str(path),
                            "engine": "pdfplumber",
                            **artifacts,
                        }
                    )
        return results
    except Exception as exc:
        return [
            {
                "error": f"Table extraction failed for {pdf_path}: {type(exc).__name__}: {exc}",
                "error_type": type(exc).__name__,
                "pdf_path": str(pdf_path),
                "engine": "pdfplumber",
                "table_path": None,
                "structure_path": None,
                "quality_flags": ["extraction_failed"],
            }
        ]
