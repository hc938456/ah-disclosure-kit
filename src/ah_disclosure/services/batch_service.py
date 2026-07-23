from __future__ import annotations

import csv
import hashlib
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.core.naming import infer_report_year
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.identity.hkex_stockid_resolver import resolve_hkex_stock_id
from ah_disclosure.identity.resolver import resolve_company
from ah_disclosure.services.filing_pipeline import prepare_filing


SUPPORTED_DOCUMENT_TYPES = {"annual_report", "prospectus"}
MAX_WORKERS = 4
CHECKPOINT_SCHEMA_VERSION = 2
_FILING_LOCKS: dict[tuple[Any, ...], threading.Lock] = {}
_FILING_LOCKS_GUARD = threading.Lock()

_BATCH_OPTION_DEFAULTS: dict[str, Any] = {
    "prefer_cache": True,
    "refresh_source": False,
    "offline": False,
    "ocr": "auto",
    "stop_on_error": False,
    "max_workers": 2,
    "refresh_identity": False,
}


def _filing_lock(key: tuple[Any, ...]) -> threading.Lock:
    with _FILING_LOCKS_GUARD:
        return _FILING_LOCKS.setdefault(key, threading.Lock())


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _batch_options(kwargs: dict[str, Any]) -> dict[str, Any]:
    unknown = set(kwargs) - set(_BATCH_OPTION_DEFAULTS)
    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"Unsupported batch option(s): {names}")
    options = {**_BATCH_OPTION_DEFAULTS, **kwargs}
    return {
        "prefer_cache": bool(options["prefer_cache"]),
        "refresh_source": bool(options["refresh_source"]),
        "offline": bool(options["offline"]),
        "ocr": str(options["ocr"]),
        "stop_on_error": bool(options["stop_on_error"]),
        "max_workers": int(options["max_workers"]),
        "refresh_identity": bool(options["refresh_identity"]),
    }


def load_batch_items(input_path: str | Path) -> list[dict[str, Any]]:
    path = Path(input_path).expanduser().resolve()
    suffix = path.suffix.casefold()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    if suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8-sig").splitlines()
            if line.strip()
        ]
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            payload = payload.get("items")
        if not isinstance(payload, list):
            raise ValueError("JSON input must be a list or an object containing an items list.")
        return [dict(item) for item in payload]
    raise ValueError("Batch input must use .csv, .json, or .jsonl.")


def _optional_year(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(text) if text else None


def _normalize_item(item: dict[str, Any], row_no: int) -> dict[str, Any]:
    market = str(item.get("market") or "").strip().upper()
    if market not in {"A", "H"}:
        raise ValueError("market must be A or H")
    symbol = str(item.get("symbol") or "").strip()
    if not symbol:
        raise ValueError("symbol is required")
    document_type = str(item.get("document_type") or "annual_report").strip().lower()
    if document_type not in SUPPORTED_DOCUMENT_TYPES:
        raise ValueError("document_type must be annual_report or prospectus")
    language = str(
        item.get("language") or ("EN" if market == "H" else "ZH")
    ).strip().upper()
    return {
        "row_no": row_no,
        "market": market,
        "symbol": symbol,
        "company_name": str(item.get("company_name") or "").strip() or None,
        "document_type": document_type,
        "report_year": _optional_year(item.get("report_year")),
        "language": language,
        "hkex_stock_id": str(item.get("hkex_stock_id") or "").strip() or None,
    }


def _confirm_identity(
    item: dict[str, Any],
    *,
    offline: bool,
    refresh_identity: bool,
) -> dict[str, Any]:
    if item["market"] == "H":
        if offline and not item.get("hkex_stock_id"):
            return dict(resolve_company(item["symbol"], "H"))
        return resolve_hkex_stock_id(
            item["symbol"],
            candidate_stock_id=item.get("hkex_stock_id"),
            company_keyword="",
            verify=bool(item.get("hkex_stock_id")) and not offline,
            refresh=refresh_identity and not offline,
        )
    return dict(resolve_company(item["symbol"], "A"))


def _result_status(result: dict[str, Any]) -> str:
    if result.get("ok"):
        execution = result.get("execution_info") or {}
        return "cached" if execution.get("document_cache_hit") else "accepted"
    attempts = result.get("validation_attempts") or []
    if any(attempt.get("disposition") == "needs_review" for attempt in attempts):
        return "needs_review"
    return "failed"


def _prepare_item(
    raw_item: dict[str, Any],
    row_no: int,
    *,
    prefer_cache: bool,
    refresh_source: bool,
    offline: bool,
    ocr: str,
    refresh_identity: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        item = _normalize_item(raw_item, row_no)
        identity_started = time.perf_counter()
        identity = _confirm_identity(
            item,
            offline=offline,
            refresh_identity=refresh_identity,
        )
        identity_ms = (time.perf_counter() - identity_started) * 1000
        resolved_symbol = str(identity.get("symbol") or item["symbol"])
        hkex_stock_id = identity.get("hkex_stock_id") or item.get("hkex_stock_id")
        if item["market"] == "H" and not hkex_stock_id and not offline:
            raise RuntimeError(identity.get("error") or "HKEX stockId could not be resolved")
        filing_key = (
            item["market"],
            resolved_symbol,
            item["document_type"],
            item["report_year"],
            item["language"],
        )
        with _filing_lock(filing_key):
            result = prepare_filing(
                market=item["market"],
                symbol=resolved_symbol,
                document_type=item["document_type"],
                report_year=item["report_year"],
                language=item["language"],
                prefer_cache=prefer_cache,
                refresh_source=refresh_source,
                offline=offline,
                ocr=ocr,
                hkex_stock_id=str(hkex_stock_id) if hkex_stock_id else None,
                company_name=item.get("company_name"),
            )
        execution = dict(result.get("execution_info") or {})
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        execution_timings = dict(execution.get("timings_ms") or {})
        pipeline_total = execution_timings.get("total")
        execution["timings_ms"] = {
            **execution_timings,
            "identity_resolution": round(identity_ms, 2),
            "pipeline_total": pipeline_total,
            "total": elapsed_ms,
        }
        ingest = dict(result.get("ingest") or {})
        document = dict(result.get("document") or {})
        resolved_report_year = (
            document.get("report_year")
            or execution.get("latest_report_year")
            or item["report_year"]
        )
        if resolved_report_year is None and item["document_type"] == "annual_report":
            resolved_report_year = _optional_year(
                infer_report_year(
                    document.get("title"),
                    document.get("publish_time"),
                )
            )
        validation = result.get("document_validation") or result.get("completeness")
        ocr_pages = ingest.get("ocr_pages") or []
        status = _result_status(result)
        validation_status = (
            validation.get("status") if isinstance(validation, dict) else None
        ) or ("cached_index_consistent" if status == "cached" else None)
        return {
            **item,
            "symbol": resolved_symbol,
            "report_year": resolved_report_year,
            "resolved_identity": identity,
            "ok": bool(result.get("ok")),
            "status": status,
            "error": result.get("error"),
            "document_id": result.get("document_id"),
            "title": document.get("title"),
            "source": document.get("source"),
            "source_url": document.get("pdf_url") or document.get("detail_url"),
            "local_pdf_path": result.get("local_pdf_path"),
            "page_count": ingest.get("page_count") or document.get("page_count"),
            "ocr_page_count": len(ocr_pages),
            "sqlite_index_reused": ingest.get("sqlite_index_reused"),
            "validation_status": validation_status,
            "validation": validation,
            "execution_info": execution,
            "validation_attempts": result.get("validation_attempts") or [],
            "elapsed_ms": elapsed_ms,
        }
    except Exception as exc:
        return {
            "row_no": row_no,
            "market": raw_item.get("market"),
            "symbol": raw_item.get("symbol"),
            "company_name": raw_item.get("company_name"),
            "document_type": raw_item.get("document_type") or "annual_report",
            "report_year": raw_item.get("report_year"),
            "language": raw_item.get("language"),
            "ok": False,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }


def batch_prepare(
    items: list[dict[str, Any]],
    *,
    prefer_cache: bool = True,
    refresh_source: bool = False,
    offline: bool = False,
    ocr: str = "auto",
    stop_on_error: bool = False,
    max_workers: int = 2,
    refresh_identity: bool = False,
    existing_results: list[dict[str, Any]] | None = None,
    progress_callback: Callable[[dict[str, Any], int, int, list[dict[str, Any]]], None]
    | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = now_iso()
    results_by_row: dict[int, dict[str, Any]] = {}
    for fallback_row, result in enumerate(existing_results or [], start=1):
        row_no = int(result.get("row_no") or fallback_row)
        results_by_row[row_no] = result
    completed_results = [results_by_row[key] for key in sorted(results_by_row)]
    def item_key(item: dict[str, Any], row_no: int) -> tuple[Any, ...] | None:
        try:
            normalized = _normalize_item(item, row_no)
        except (TypeError, ValueError):
            return None
        return (
            normalized["market"],
            normalized["symbol"],
            normalized["document_type"],
            normalized["report_year"],
            normalized["language"],
            normalized["hkex_stock_id"],
        )

    completed_by_key: dict[tuple[Any, ...], tuple[int, dict[str, Any]]] = {}
    for row_no, result in results_by_row.items():
        if 1 <= row_no <= len(items):
            key = item_key(items[row_no - 1], row_no)
            if key is not None:
                completed_by_key[key] = (row_no, result)

    pending: list[tuple[int, dict[str, Any]]] = []
    duplicate_rows: dict[int, list[int]] = {}
    representative_by_key: dict[tuple[Any, ...], int] = {}
    for row_no, raw_item in enumerate(items, start=1):
        if row_no in results_by_row:
            continue
        item = dict(raw_item)
        key = item_key(item, row_no)
        if key is not None and key in completed_by_key:
            source_row, source_result = completed_by_key[key]
            results_by_row[row_no] = {
                **source_result,
                "row_no": row_no,
                "deduplicated_from_row": source_row,
            }
            completed_results.append(results_by_row[row_no])
            continue
        if key is not None and key in representative_by_key:
            duplicate_rows.setdefault(representative_by_key[key], []).append(row_no)
            continue
        pending.append((row_no, item))
        if key is not None:
            representative_by_key[key] = row_no

    def prepare(row_no: int, item: dict[str, Any]) -> dict[str, Any]:
        return _prepare_item(
            item,
            row_no,
            prefer_cache=prefer_cache,
            refresh_source=refresh_source,
            offline=offline,
            ocr=ocr,
            refresh_identity=refresh_identity,
        )

    def record(result: dict[str, Any], row_no: int) -> None:
        results_by_row[row_no] = result
        completed_results.append(result)
        if progress_callback:
            progress_callback(result, row_no, len(items), completed_results)
        for duplicate_row in duplicate_rows.get(row_no, []):
            duplicate_result = {
                **result,
                "row_no": duplicate_row,
                "deduplicated_from_row": row_no,
            }
            results_by_row[duplicate_row] = duplicate_result
            completed_results.append(duplicate_result)
            if progress_callback:
                progress_callback(
                    duplicate_result,
                    duplicate_row,
                    len(items),
                    completed_results,
                )

    requested_workers = max(1, int(max_workers))
    worker_count = 1 if stop_on_error else min(requested_workers, MAX_WORKERS)
    effective_workers = min(worker_count, len(pending)) if pending else 0
    if effective_workers <= 1:
        for row_no, item in pending:
            result = prepare(row_no, item)
            record(result, row_no)
            if stop_on_error and not result["ok"]:
                break
    else:
        with ThreadPoolExecutor(max_workers=effective_workers) as pool:
            futures = {
                pool.submit(prepare, row_no, item): row_no
                for row_no, item in pending
            }
            for future in as_completed(futures):
                row_no = futures[future]
                record(future.result(), row_no)

    results = [results_by_row[key] for key in sorted(results_by_row)]
    status_counts = {
        status: sum(1 for result in results if result.get("status") == status)
        for status in ("accepted", "cached", "needs_review", "failed")
    }
    return {
        "command": "batch_prepare",
        "evidence_extraction": False,
        "analysis": False,
        "max_workers": worker_count,
        "requested_workers": requested_workers,
        "effective_workers": effective_workers,
        "deduplicated_count": sum(
            1 for result in results if result.get("deduplicated_from_row") is not None
        ),
        "started_at": started_at,
        "requested_count": len(items),
        "processed_count": len(results),
        "success_count": sum(1 for result in results if result.get("ok")),
        "failure_count": sum(1 for result in results if not result.get("ok")),
        "status_counts": status_counts,
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "results": results,
    }


def _write_json_atomic(target: Path, payload: dict[str, Any]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    replace_file_with_retry(temporary, target)


def run_batch_prepare(
    input_path: str | Path,
    output_path: str | Path | None = None,
    resume: bool = False,
    progress_callback: Callable[[dict[str, Any], int, int, list[dict[str, Any]]], None]
    | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    source = Path(input_path).expanduser().resolve()
    items = load_batch_items(source)
    input_sha256 = _file_sha256(source)
    run_options = _batch_options(kwargs)
    checkpoint_options = {
        key: run_options[key]
        for key in ("prefer_cache", "refresh_source", "offline", "ocr", "refresh_identity")
    }
    target = Path(output_path).expanduser().resolve() if output_path else None
    checkpoint = target.with_suffix(target.suffix + ".checkpoint.json") if target else None
    existing_results: list[dict[str, Any]] = []
    if resume:
        if checkpoint is None:
            raise ValueError("resume requires output_path")
        if checkpoint.is_file():
            payload = json.loads(checkpoint.read_text(encoding="utf-8"))
            if payload.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
                raise ValueError("Checkpoint schema is outdated; restart without --resume.")
            if str(payload.get("input_path")) != str(source):
                raise ValueError("Checkpoint input_path does not match the requested input file.")
            if str(payload.get("input_sha256") or "") != input_sha256:
                raise ValueError("Checkpoint input content has changed; restart without --resume.")
            if payload.get("options") != checkpoint_options:
                raise ValueError("Checkpoint options do not match this run; restart without --resume.")
            existing_results = list(payload.get("results") or [])

    def checkpoint_progress(
        item_result: dict[str, Any],
        row_no: int,
        total: int,
        results: list[dict[str, Any]],
    ) -> None:
        checkpoint_stride = max(1, (total + 99) // 100)
        should_checkpoint = (
            len(results) == total
            or len(results) % checkpoint_stride == 0
            or not item_result.get("ok")
        )
        if checkpoint and should_checkpoint:
            _write_json_atomic(
                checkpoint,
                {
                    "schema_version": CHECKPOINT_SCHEMA_VERSION,
                    "input_path": str(source),
                    "input_sha256": input_sha256,
                    "options": checkpoint_options,
                    "requested_count": total,
                    "processed_count": len(results),
                    "results": results,
                },
            )
        if progress_callback:
            progress_callback(item_result, row_no, total, results)

    result = batch_prepare(
        items,
        existing_results=existing_results,
        progress_callback=checkpoint_progress,
        **run_options,
    )
    if target:
        result["output_path"] = str(target)
        _write_json_atomic(target, result)
        if checkpoint:
            if result["processed_count"] >= result["requested_count"]:
                checkpoint.unlink(missing_ok=True)
            else:
                _write_json_atomic(
                    checkpoint,
                    {
                        "schema_version": CHECKPOINT_SCHEMA_VERSION,
                        "input_path": str(source),
                        "input_sha256": input_sha256,
                        "options": checkpoint_options,
                        "requested_count": result["requested_count"],
                        "processed_count": result["processed_count"],
                        "results": result["results"],
                    },
                )
    return result
