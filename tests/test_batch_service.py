import csv
import json
import threading
import time

import pytest

from ah_disclosure import cli
from ah_disclosure.services import batch_service


def test_load_batch_items_supports_csv_json_and_jsonl(tmp_path):
    rows = [
        {
            "market": "H",
            "symbol": "01519",
            "document_type": "prospectus",
            "report_year": 2023,
            "language": "EN",
        }
    ]
    json_path = tmp_path / "batch.json"
    json_path.write_text(json.dumps({"items": rows}), encoding="utf-8")
    jsonl_path = tmp_path / "batch.jsonl"
    jsonl_path.write_text(json.dumps(rows[0]) + "\n", encoding="utf-8")
    csv_path = tmp_path / "batch.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    assert batch_service.load_batch_items(json_path)[0]["symbol"] == "01519"
    assert batch_service.load_batch_items(jsonl_path)[0]["report_year"] == 2023
    assert batch_service.load_batch_items(csv_path)[0]["language"] == "EN"


def test_batch_prepare_uses_official_pipeline_and_preserves_order(monkeypatch):
    monkeypatch.setattr(
        batch_service,
        "resolve_company",
        lambda symbol, market: {"market": market, "symbol": symbol},
    )

    def fake_prepare(**kwargs):
        return {
            "ok": True,
            "document_id": f"A_{kwargs['symbol']}_2025_annual_report_ZH_TEST",
            "local_pdf_path": f"C:/data/{kwargs['symbol']}.pdf",
            "document": {
                "title": "测试公司2025年年度报告",
                "source": "CNINFO",
                "page_count": 100,
            },
            "ingest": {"page_count": 100, "ocr_pages": []},
            "document_validation": {"status": "complete", "complete": True},
            "execution_info": {
                "document_cache_hit": False,
                "timings_ms": {"total": 1.0},
            },
        }

    monkeypatch.setattr(batch_service, "prepare_filing", fake_prepare)
    result = batch_service.batch_prepare(
        [
            {"market": "A", "symbol": "000001"},
            {"market": "A", "symbol": "000002"},
        ],
        max_workers=2,
    )

    assert result["command"] == "batch_prepare"
    assert result["success_count"] == 2
    assert result["evidence_extraction"] is False
    assert result["analysis"] is False
    assert [row["symbol"] for row in result["results"]] == ["000001", "000002"]
    assert [row["report_year"] for row in result["results"]] == [2025, 2025]


def test_batch_prepare_deduplicates_identical_items(monkeypatch):
    calls = []
    monkeypatch.setattr(
        batch_service,
        "resolve_company",
        lambda symbol, market: {"market": market, "symbol": symbol},
    )

    def fake_prepare(**kwargs):
        calls.append(kwargs)
        return {
            "ok": True,
            "document_id": "A_000001_2025_annual_report_ZH_TEST",
            "document": {"source": "CNINFO"},
            "ingest": {},
            "execution_info": {},
        }

    monkeypatch.setattr(batch_service, "prepare_filing", fake_prepare)
    item = {
        "market": "A",
        "symbol": "000001",
        "document_type": "annual_report",
        "report_year": 2025,
        "language": "ZH",
    }

    result = batch_service.batch_prepare([item, dict(item)], max_workers=4)

    assert len(calls) == 1
    assert result["effective_workers"] == 1
    assert result["deduplicated_count"] == 1
    assert result["results"][1]["deduplicated_from_row"] == 1


def test_batch_prepare_serializes_aliases_resolving_to_same_filing(monkeypatch):
    active = 0
    max_active = 0
    guard = threading.Lock()
    monkeypatch.setattr(
        batch_service,
        "resolve_company",
        lambda symbol, market: {"market": market, "symbol": "920403"},
    )

    def fake_prepare(**kwargs):
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        return {
            "ok": True,
            "document_id": "A_920403_2023_prospectus_ZH_TEST",
            "document": {"source": "CNINFO"},
            "ingest": {},
            "execution_info": {},
        }

    monkeypatch.setattr(batch_service, "prepare_filing", fake_prepare)
    result = batch_service.batch_prepare(
        [
            {"market": "A", "symbol": "837403", "document_type": "prospectus"},
            {"market": "A", "symbol": "920403", "document_type": "prospectus"},
        ],
        max_workers=2,
    )

    assert result["success_count"] == 2
    assert max_active == 1


def test_batch_prepare_reports_actual_worker_count(monkeypatch):
    monkeypatch.setattr(
        batch_service,
        "_prepare_item",
        lambda raw_item, row_no, **kwargs: {
            "row_no": row_no,
            "ok": True,
            "status": "accepted",
        },
    )

    one = batch_service.batch_prepare([{"market": "A", "symbol": "000001"}], max_workers=4)
    none = batch_service.batch_prepare([], max_workers=4)

    assert one["effective_workers"] == 1
    assert none["effective_workers"] == 0


def test_batch_prepare_cli_is_registered():
    parser = cli.build_parser()
    args = parser.parse_args(
        [
            "batch",
            "prepare",
            "--input",
            "companies.csv",
            "--max-workers",
            "3",
            "--refresh-identity",
            "--summary-only",
        ]
    )

    assert args.batch_cmd == "prepare"
    assert args.max_workers == 3
    assert args.refresh_identity is True
    assert args.summary_only is True


def test_batch_result_summary_keeps_item_outcomes_without_validation_payloads():
    result = {
        "command": "batch_prepare",
        "success_count": 1,
        "failure_count": 0,
        "elapsed_ms": 12.3,
        "output_path": "result.json",
        "results": [
            {
                "row_no": 1,
                "market": "A",
                "symbol": "600000",
                "document_type": "annual_report",
                "report_year": 2025,
                "status": "accepted",
                "document_id": "doc1",
                "validation": {"large": "payload"},
            }
        ],
    }

    summary = cli._batch_result_summary(result)

    assert summary["success_count"] == 1
    assert summary["items"][0]["report_year"] == 2025
    assert "validation" not in summary["items"][0]
    assert "document_id" not in summary["items"][0]


def test_run_batch_prepare_writes_result_and_removes_checkpoint(monkeypatch, tmp_path):
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps([{"market": "A", "symbol": "000001"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        batch_service,
        "_prepare_item",
        lambda raw_item, row_no, **kwargs: {
            "row_no": row_no,
            "market": "A",
            "symbol": raw_item["symbol"],
            "document_type": "annual_report",
            "ok": True,
            "status": "accepted",
        },
    )

    result = batch_service.run_batch_prepare(input_path, output_path)

    assert result["success_count"] == 1
    assert output_path.is_file()
    assert json.loads(output_path.read_text(encoding="utf-8"))["output_path"] == str(
        output_path.resolve()
    )
    assert not output_path.with_suffix(".json.checkpoint.json").exists()


def test_stop_on_error_preserves_checkpoint_for_resume(monkeypatch, tmp_path):
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps(
            [
                {"market": "A", "symbol": "000001"},
                {"market": "A", "symbol": "000002"},
            ]
        ),
        encoding="utf-8",
    )

    def fail_first(raw_item, row_no, **kwargs):
        return {
            "row_no": row_no,
            "market": "A",
            "symbol": raw_item["symbol"],
            "document_type": "annual_report",
            "ok": False,
            "status": "failed",
            "error": "source unavailable",
        }

    monkeypatch.setattr(batch_service, "_prepare_item", fail_first)
    first_result = batch_service.run_batch_prepare(
        input_path,
        output_path,
        stop_on_error=True,
    )
    checkpoint = output_path.with_suffix(".json.checkpoint.json")

    assert first_result["processed_count"] == 1
    assert checkpoint.is_file()

    def complete_remaining(raw_item, row_no, **kwargs):
        return {
            "row_no": row_no,
            "market": "A",
            "symbol": raw_item["symbol"],
            "document_type": "annual_report",
            "ok": True,
            "status": "accepted",
        }

    monkeypatch.setattr(batch_service, "_prepare_item", complete_remaining)
    resumed_result = batch_service.run_batch_prepare(
        input_path,
        output_path,
        resume=True,
    )

    assert resumed_result["processed_count"] == 2
    assert resumed_result["results"][0]["status"] == "failed"
    assert resumed_result["results"][1]["status"] == "accepted"
    assert not checkpoint.exists()


def test_resume_rejects_changed_input_content(monkeypatch, tmp_path):
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps(
            [
                {"market": "A", "symbol": "000001"},
                {"market": "A", "symbol": "000002"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        batch_service,
        "_prepare_item",
        lambda raw_item, row_no, **kwargs: {
            "row_no": row_no,
            "ok": False,
            "status": "failed",
        },
    )
    batch_service.run_batch_prepare(input_path, output_path, stop_on_error=True)
    input_path.write_text(
        json.dumps([{"market": "A", "symbol": "000099"}]),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="input content has changed"):
        batch_service.run_batch_prepare(input_path, output_path, resume=True)


def test_resume_rejects_changed_semantic_options(monkeypatch, tmp_path):
    input_path = tmp_path / "batch.json"
    output_path = tmp_path / "result.json"
    input_path.write_text(
        json.dumps(
            [
                {"market": "A", "symbol": "000001"},
                {"market": "A", "symbol": "000002"},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        batch_service,
        "_prepare_item",
        lambda raw_item, row_no, **kwargs: {
            "row_no": row_no,
            "ok": False,
            "status": "failed",
        },
    )
    batch_service.run_batch_prepare(
        input_path,
        output_path,
        stop_on_error=True,
        ocr="auto",
    )

    with pytest.raises(ValueError, match="options do not match"):
        batch_service.run_batch_prepare(
            input_path,
            output_path,
            resume=True,
            ocr="force",
        )
