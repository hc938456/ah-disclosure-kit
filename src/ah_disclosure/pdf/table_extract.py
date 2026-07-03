from __future__ import annotations

from pathlib import Path
from typing import Iterable


def extract_tables(pdf_path: str | Path, output_dir: str | Path, pages: Iterable[int] | None = None) -> list[dict]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
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
                    with path.open("w", encoding="utf-8-sig") as handle:
                        for row in table:
                            cells = [str(cell or "").replace('"', '""') for cell in row]
                            handle.write(",".join(f'"{cell}"' for cell in cells) + "\n")
                    results.append({"page_no": idx, "table_index": table_index, "table_path": str(path), "engine": "pdfplumber"})
        return results
    except Exception as exc:
        return [{"error": str(exc), "engine": "pdfplumber", "table_path": None}]
