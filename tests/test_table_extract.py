from __future__ import annotations

import csv
import json
import sys
from types import SimpleNamespace

from ah_disclosure.pdf.table_extract import extract_tables, infer_table_structure


def test_infer_table_structure_supports_three_header_levels() -> None:
    rows = [
        ["项目", "2024年度", None, "2023年度", None],
        [None, "境内", None, "境内", None],
        [None, "收入", "成本", "收入", "成本"],
        ["主营业务", "120", "80", "100", "70"],
        ["其他业务", "20", "10", "18", "9"],
    ]

    structure = infer_table_structure(rows)

    assert structure["header_depth"] == 3
    assert structure["body_start_row"] == 3
    assert structure["confidence"] >= 0.60
    assert structure["row_count"] == 5
    assert structure["column_count"] == 5
    assert structure["column_paths"] == [
        ["项目"],
        ["2024年度", "境内", "收入"],
        ["2024年度", "境内", "成本"],
        ["2023年度", "境内", "收入"],
        ["2023年度", "境内", "成本"],
    ]
    assert "contains_null_cells" in structure["quality_flags"]
    assert "header_inferred" in structure["quality_flags"]


def test_infer_table_structure_does_not_force_uncertain_header() -> None:
    rows = [["Alice", "North"], ["Bob", "South"], ["Carol", "West"]]

    structure = infer_table_structure(rows)

    assert structure["header_depth"] == 0
    assert structure["body_start_row"] == 0
    assert structure["column_paths"] == []
    assert structure["confidence"] < 0.60
    assert "header_low_confidence" in structure["quality_flags"]


def test_extract_tables_writes_utf8_csv_and_json_sidecar(tmp_path, monkeypatch) -> None:
    raw_rows = [["项目", "金额"], ["营业收入", "1,200"], ["备注", None]]

    class FakePdf:
        pages = [SimpleNamespace(extract_tables=lambda: [raw_rows])]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _path: FakePdf()))

    results = extract_tables(tmp_path / "sample.pdf", tmp_path / "tables")

    assert len(results) == 1
    result = results[0]
    csv_bytes = (tmp_path / "tables" / "page_1_table_1.csv").read_bytes()
    assert not csv_bytes.startswith(b"\xef\xbb\xbf")
    with open(result["table_path"], encoding="utf-8", newline="") as handle:
        assert list(csv.reader(handle)) == [["项目", "金额"], ["营业收入", "1,200"], ["备注", ""]]

    payload = json.loads((tmp_path / "tables" / "page_1_table_1.json").read_text(encoding="utf-8"))
    assert result["structure_path"].endswith("page_1_table_1.json")
    assert payload["raw_rows"] == raw_rows
    assert payload["row_count"] == 3
    assert payload["column_count"] == 2
    assert payload["raw_rows"][-1][-1] is None
    assert result["quality_flags"] == payload["quality_flags"]


def test_extract_tables_honors_page_filter(tmp_path, monkeypatch) -> None:
    pages = [
        SimpleNamespace(extract_tables=lambda: [[['skip']]]),
        SimpleNamespace(extract_tables=lambda: [[['项目', '金额'], ['收入', '10']]]),
    ]

    class FakePdf:
        def __init__(self):
            self.pages = pages

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _path: FakePdf()))

    results = extract_tables(tmp_path / "sample.pdf", tmp_path / "tables", pages=[2])

    assert [result["page_no"] for result in results] == [2]
    assert not (tmp_path / "tables" / "page_1_table_1.csv").exists()
    assert (tmp_path / "tables" / "page_2_table_1.json").exists()


def test_extract_tables_rebuild_removes_stale_artifacts(tmp_path, monkeypatch) -> None:
    output_dir = tmp_path / "tables"
    output_dir.mkdir()
    (output_dir / "page_9_table_3.csv").write_text("stale", encoding="utf-8")
    (output_dir / "page_9_table_3.json").write_text("{}", encoding="utf-8")

    class FakePdf:
        pages = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    monkeypatch.setitem(sys.modules, "pdfplumber", SimpleNamespace(open=lambda _path: FakePdf()))

    assert extract_tables(tmp_path / "sample.pdf", output_dir) == []
    assert list(output_dir.glob("page_*_table_*.csv")) == []
    assert list(output_dir.glob("page_*_table_*.json")) == []


def test_extract_tables_returns_contextual_error(tmp_path, monkeypatch) -> None:
    monkeypatch.setitem(
        sys.modules,
        "pdfplumber",
        SimpleNamespace(open=lambda _path: (_ for _ in ()).throw(ValueError("broken xref"))),
    )

    results = extract_tables(tmp_path / "broken.pdf", tmp_path / "tables")

    assert results[0]["error_type"] == "ValueError"
    assert results[0]["pdf_path"].endswith("broken.pdf")
    assert "broken xref" in results[0]["error"]
