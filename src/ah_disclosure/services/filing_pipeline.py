from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from ah_disclosure.clients.hkex_client import HkexClient, get_thread_hkex_client
from ah_disclosure.core.file_utils import replace_file_with_retry
from ah_disclosure.core.naming import (
    build_document_id,
    build_pdf_filename,
    infer_language,
    infer_report_year,
    normalize_document_type,
)
from ah_disclosure.core.paths import get_data_paths
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.identity.a_symbol_resolver import resolve_a_symbol
from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.completeness import (
    validate_annual_report_pages,
    validate_prospectus_pages,
)
from ah_disclosure.pdf.candidate_files import discard_staged_candidate, move_staged_candidate
from ah_disclosure.pdf.downloader import download_file, file_sha256
from ah_disclosure.pdf.ingest import ingest_pdf
from ah_disclosure.pdf.identity import validate_document_identity
from ah_disclosure.pdf.package import merge_pdf_parts
from ah_disclosure.pdf.text_extract import extract_pages
from ah_disclosure.services.disclosure_service import search_a_annual_report, search_a_filings, search_h_annual_report, search_h_filings
from ah_disclosure.services.evidence_service import get_evidence_packet
from ah_disclosure.services.prospectus_service import search_prospectus
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _validation_cache_path(paths: Any, document_id: str) -> Path:
    return paths.parsed / document_id / "validation_report.json"


def _read_validation_cache(
    paths: Any,
    document_id: str,
    sha256: str,
    document_type: str,
    symbol: str,
) -> dict[str, Any] | None:
    path = _validation_cache_path(paths, document_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    validation = payload.get("document_validation")
    if (
        str(payload.get("sha256") or "") != str(sha256)
        or normalize_document_type(payload.get("document_type"))
        != normalize_document_type(document_type)
        or str(payload.get("symbol") or "") != str(symbol)
        or not isinstance(validation, dict)
        or validation.get("complete") is not True
    ):
        return None
    identity = validation.get("identity")
    if isinstance(identity, dict) and identity.get("passed") is not True:
        return None
    return dict(validation)


def _write_validation_cache(
    paths: Any,
    document_id: str,
    sha256: str,
    meta: dict[str, Any],
    validation: dict[str, Any] | None,
    source_url: str,
) -> str | None:
    if not isinstance(validation, dict) or validation.get("complete") is not True:
        return None
    target = _validation_cache_path(paths, document_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f"{target.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(
            {
                "document_id": document_id,
                "market": meta.get("market"),
                "symbol": meta.get("symbol"),
                "document_type": meta.get("document_type"),
                "sha256": sha256,
                "source_url": source_url,
                "document_validation": validation,
                "validated_at": now_iso(),
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    replace_file_with_retry(temporary, target)
    return str(target)


def _valid_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if isinstance(row, dict)
        and not row.get("error")
        and (row.get("pdf_url") or row.get("detail_url"))
    ]


def _is_overseas_regulatory_annual_report(row: dict[str, Any]) -> bool:
    title = " ".join(str(row.get("title") or "").casefold().split())
    return any(
        token in title
        for token in ("overseas regulatory announcement", "海外監管公告", "海外监管公告")
    )


def _is_h_share_announcement(row: dict[str, Any]) -> bool:
    title = " ".join(str(row.get("title") or "").casefold().split())
    return any(
        token in title
        for token in ("h股公告", "港股公告", "h-share announcement")
    )


def _search_source(
    market: str,
    symbol: str,
    document_type: str,
    report_year: int | None,
    language: str,
    hkex_stock_id: str | None,
    max_rows: int,
    offline: bool,
    refresh: bool,
    max_cache_age_seconds: int | None,
    company_name: str | None,
) -> list[dict[str, Any]]:
    normalized = normalize_document_type(document_type)
    common: dict[str, Any] = {
        "prefer_cache": True,
        "refresh": refresh,
        "offline": offline,
        "max_cache_age_seconds": max_cache_age_seconds,
    }
    if normalized == "prospectus":
        return search_prospectus(
            market,
            symbol=symbol,
            company_keyword=company_name or "",
            max_rows=max_rows,
            lang=language,
            hkex_stock_id=hkex_stock_id,
            **common,
        )
    if normalized == "annual_report":
        if market.upper().startswith("H"):
            return search_h_annual_report(
                symbol,
                report_year=report_year,
                hkex_stock_id=hkex_stock_id,
                max_rows=max_rows,
                lang=language,
                **common,
            )
        return search_a_annual_report(
            symbol,
            report_year=report_year,
            max_rows=max_rows,
            **common,
        )
    if market.upper().startswith("H"):
        return search_h_filings(
            symbol,
            hkex_stock_id=hkex_stock_id,
            title_keyword=document_type,
            max_rows=max_rows,
            lang=language,
            **common,
        )
    return search_a_filings(
        symbol,
        category=document_type,
        max_rows=max_rows,
        **common,
    )


def _candidate_source_url(candidate: dict[str, Any]) -> str | None:
    for key in ("pdf_url", "detail_url"):
        value = candidate.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _canonical_request_symbol(
    market: str,
    symbol: str,
    *,
    offline: bool,
) -> tuple[str, dict[str, Any] | None]:
    if not market.upper().startswith("A"):
        return symbol, None
    identity = dict(resolve_a_symbol(symbol, offline=offline))
    return str(identity.get("symbol") or symbol), identity


def _is_hkex_listing_package(candidate: dict[str, Any], document_type: str) -> bool:
    if normalize_document_type(document_type) != "prospectus":
        return False
    url = str(candidate.get("detail_url") or "")
    return (
        url.casefold().endswith((".htm", ".html"))
        and "hkexnews.hk" in url.casefold()
        and not candidate.get("pdf_url")
    )


def _trusted_a_prospectus_identity(
    candidate: dict[str, Any],
    symbol: str,
    identity: dict[str, Any],
) -> bool:
    """Allow pre-listing A-share prospectuses whose body omits the final stock code."""
    title = str(candidate.get("title") or "")
    source = str(candidate.get("source") or "").casefold()
    candidate_symbol = re.sub(r"\D", "", str(candidate.get("symbol") or ""))
    expected_symbol = re.sub(r"\D", "", str(symbol))
    return (
        not identity.get("passed")
        and "cninfo" in source
        and bool(candidate_symbol)
        and candidate_symbol == expected_symbol
        and "招股说明书" in title
        and "意向书" not in title
    )


def _canonical_candidate_symbol(
    market: str,
    requested_symbol: str,
    candidate: dict[str, Any],
) -> str:
    """Use the provider's current BSE code while retaining legacy codes as query aliases."""
    candidate_symbol = re.sub(r"\D", "", str(candidate.get("symbol") or ""))
    requested_digits = re.sub(r"\D", "", str(requested_symbol))
    if (
        market.upper().startswith("A")
        and candidate_symbol.startswith("920")
        and requested_digits.startswith(("4", "8", "920"))
    ):
        return candidate_symbol
    return requested_symbol


def _candidate_score(
    row: dict[str, Any],
    document_type: str,
    report_year: int | None,
    language: str,
) -> int:
    title = str(row.get("title") or "")
    folded_title = " ".join(title.casefold().split())
    score = 0
    if str(row.get("pdf_url") or "").lower().endswith(".pdf"):
        score += 20
    if normalize_document_type(row.get("document_type"), title) == normalize_document_type(document_type):
        score += 10
    if report_year is not None and str(report_year) in title:
        score += 10
    if language.upper().startswith("EN") and not any("\u4e00" <= char <= "\u9fff" for char in title):
        score += 3
    if language.upper().startswith(("ZH", "CN")) and any("\u4e00" <= char <= "\u9fff" for char in title):
        score += 3
    if language.upper().startswith(("ZH", "CN")) and (
        "英文版" in title or not any("\u4e00" <= char <= "\u9fff" for char in title)
    ):
        score -= 40
    if language.upper().startswith("EN") and any(
        token in title for token in ("中文版", "中文版本")
    ):
        score -= 40
    if normalize_document_type(document_type) == "annual_report":
        if report_year is None:
            year = r"\d{4}"
        else:
            numeric_year = str(report_year)
            chinese_year = numeric_year.translate(
                str.maketrans("0123456789", "零一二三四五六七八九")
            )
            year_tokens = (numeric_year, chinese_year, chinese_year.replace("零", "〇"))
            year = "(?:" + "|".join(re.escape(token) for token in year_tokens) + ")"
        exact_patterns = (
            rf"^(?:annual report(?: and accounts)? {year}|(?:fiscal year )?{year} annual report(?: and accounts)?)(?:\s*\([^)]*\))?$",
            rf"^(?:年報|年度報告)\s*{year}$",
            rf"^{year}\s*(?:年報|年年報|年度報告)$",
        )
        if any(re.fullmatch(pattern, folded_title, flags=re.IGNORECASE) for pattern in exact_patterns):
            score += 35
        if "with employee share plans" in folded_title:
            score += 5
        negative_tokens = (
            "summary",
            "摘要",
            "通知",
            "通函",
            "notification",
            "notice of publication",
            "reply form",
            "letter to",
            "form of proxy",
            "proxy form",
            "overseas regulatory announcement",
            "海外監管公告",
            "港股公告",
            "h股公告",
            "h-share announcement",
            "esg",
            "更正",
            "修订",
            "修訂",
        )
        if any(token in folded_title for token in negative_tokens):
            score -= 45
    elif normalize_document_type(document_type) == "prospectus":
        category = " ".join(
            str(row.get("category") or row.get("document_type") or "").casefold().split()
        )
        if "listing documents" in category and "offer for subscription" in category:
            score += 45
        elif "listing documents" in category:
            score += 25
        if "formal notice" in category or "announcements and notices" in category:
            score -= 45
    elif any(token in folded_title for token in ("摘要", "summary", "esg", "更正", "修订", "修訂")):
        score -= 15
    return score


def _title_report_year(row: dict[str, Any]) -> int:
    value = infer_report_year(row.get("title"))
    return int(value) if str(value).isdigit() else 0


def _select_candidate(
    rows: list[dict[str, Any]],
    document_type: str,
    report_year: int | None,
    language: str,
) -> tuple[dict[str, Any] | None, bool]:
    if not rows:
        return None, False
    ranked = _rank_candidates(rows, document_type, report_year, language)
    if len(ranked) == 1:
        return ranked[0], False
    first_score = _candidate_score(ranked[0], document_type, report_year, language)
    second_score = _candidate_score(ranked[1], document_type, report_year, language)
    if first_score > second_score:
        return ranked[0], False
    if normalize_document_type(document_type) == "annual_report" and report_year is None:
        first_year = _title_report_year(ranked[0])
        second_year = _title_report_year(ranked[1])
        if first_year > second_year:
            return ranked[0], False
    first_title = " ".join(str(ranked[0].get("title") or "").casefold().split())
    second_title = " ".join(str(ranked[1].get("title") or "").casefold().split())
    if first_score >= 60 and first_title == second_title:
        return ranked[0], False
    return None, True


def _rank_candidates(
    rows: list[dict[str, Any]],
    document_type: str,
    report_year: int | None,
    language: str,
) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda row: (
            _candidate_score(row, document_type, report_year, language),
            _title_report_year(row)
            if normalize_document_type(document_type) == "annual_report" and report_year is None
            else 0,
            str(row.get("publish_time") or ""),
        ),
        reverse=True,
    )


def _latest_annual_report_candidates(
    candidates: list[dict[str, Any]],
    document_type: str,
    report_year: int | None,
) -> tuple[list[dict[str, Any]], int | None]:
    if normalize_document_type(document_type) != "annual_report" or report_year is not None:
        return candidates, report_year
    years = [_title_report_year(candidate) for candidate in candidates]
    latest_year = max(years, default=0)
    if latest_year <= 0:
        return candidates, None
    return [
        candidate
        for candidate in candidates
        if _title_report_year(candidate) == latest_year
    ], latest_year


def _document_cache_ready(
    meta: dict[str, Any] | None,
    store: SQLiteStore | None = None,
) -> bool:
    if not meta:
        return False
    local_pdf = Path(str(meta.get("local_pdf_path") or ""))
    pages_jsonl = Path(str(meta.get("pages_jsonl_path") or ""))
    if not local_pdf.is_file() or not pages_jsonl.is_file():
        return False
    expected_sha = str(meta.get("sha256") or "")
    if expected_sha:
        try:
            if file_sha256(local_pdf) != expected_sha:
                return False
        except OSError:
            return False
    expected_pages = int(meta.get("page_count") or 0)
    if expected_pages and store is not None:
        if store.count_document_pages(str(meta.get("document_id") or "")) != expected_pages:
            return False
    return True


def _find_cached_document(
    store: SQLiteStore,
    market: str,
    symbol: str,
    document_type: str,
    report_year: int | None,
    language: str,
    document_id: str | None,
) -> dict[str, Any] | None:
    if document_id:
        meta = store.get_document_meta(document_id)
        return meta if _document_cache_ready(meta, store) else None
    expected_type = normalize_document_type(document_type)
    expected_language = infer_language(document_language=language)
    matches = [
        row
        for row in store.list_documents_by_company(market, symbol)
        if normalize_document_type(row.get("document_type"), row.get("title")) == expected_type
        and (report_year is None or int(row.get("report_year") or 0) == int(report_year))
        and infer_language(row.get("title"), row.get("document_language")) == expected_language
        and _document_cache_ready(row, store)
    ]
    matches.sort(
        key=lambda row: (
            int(row.get("report_year") or 0),
            str(row.get("publish_time") or ""),
        ),
        reverse=True,
    )
    return matches[0] if matches else None


def find_filing_source(
    market: str,
    symbol: str,
    document_type: str,
    report_year: int | None = None,
    language: str | None = None,
    max_rows: int = 10,
    prefer_cache: bool = True,
    refresh: bool = False,
    offline: bool = False,
    max_cache_age_seconds: int | None = None,
    hkex_stock_id: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    if refresh and offline:
        raise ValueError("refresh and offline cannot both be true")
    requested_symbol = symbol
    symbol, symbol_resolution = _canonical_request_symbol(
        market,
        symbol,
        offline=offline,
    )
    language = language or ("EN" if market.upper().startswith("H") else "ZH")
    started = time.perf_counter()
    run_id = uuid.uuid4().hex
    rows: list[dict[str, Any]] = []
    source_cache_hit = False
    remote_source_queried = False
    cache_lookup_ms = 0.0
    remote_lookup_ms = 0.0

    if (prefer_cache or offline) and not refresh:
        cache_started = time.perf_counter()
        try:
            rows = _search_source(
                market,
                symbol,
                document_type,
                report_year,
                language,
                hkex_stock_id,
                max_rows,
                offline=True,
                refresh=False,
                max_cache_age_seconds=max_cache_age_seconds,
                company_name=company_name,
            )
            source_cache_hit = bool(_valid_candidates(rows)) or rows == []
        except RuntimeError:
            rows = []
        cache_lookup_ms = (time.perf_counter() - cache_started) * 1000

    candidates = _valid_candidates(rows)
    if not candidates and not offline and not source_cache_hit:
        remote_started = time.perf_counter()
        rows = _search_source(
            market,
            symbol,
            document_type,
            report_year,
            language,
            hkex_stock_id,
            max_rows,
            offline=False,
            refresh=True,
            max_cache_age_seconds=max_cache_age_seconds,
            company_name=company_name,
        )
        candidates = _valid_candidates(rows)
        remote_lookup_ms = (time.perf_counter() - remote_started) * 1000
        remote_source_queried = True
        source_cache_hit = False

    selection_started = time.perf_counter()
    selected, ambiguous = _select_candidate(candidates, document_type, report_year, language)
    selection_ms = (time.perf_counter() - selection_started) * 1000
    return {
        "ok": bool(candidates),
        "requested_symbol": requested_symbol,
        "resolved_symbol": symbol,
        "symbol_resolution": symbol_resolution,
        "selected": selected,
        "candidates": candidates,
        "ambiguous": ambiguous,
        "execution_info": {
            "run_id": run_id,
            "source_cache_hit": source_cache_hit,
            "remote_source_queried": remote_source_queried,
            "downloaded": False,
            "ingested": False,
            "timings_ms": {
                "cache_lookup": round(cache_lookup_ms, 2),
                "remote_lookup": round(remote_lookup_ms, 2),
                "selection": round(selection_ms, 2),
                "total": round((time.perf_counter() - started) * 1000, 2),
            },
        },
    }


def ensure_filing_evidence(
    query: str,
    market: str,
    symbol: str,
    document_type: str,
    report_year: int | None = None,
    language: str | None = None,
    document_id: str | None = None,
    max_pages: int = 8,
    max_chars: int = 12000,
    strategy: str = "auto",
    prefer_cache: bool = True,
    refresh_source: bool = False,
    offline: bool = False,
    ingest_if_missing: bool = True,
    ocr: str = "auto",
    hkex_stock_id: str | None = None,
    company_name: str | None = None,
    extract_evidence: bool = True,
) -> dict[str, Any]:
    evidence: dict[str, Any] | None
    started = time.perf_counter()
    language = language or ("EN" if market.upper().startswith("H") else "ZH")
    requested_symbol = symbol
    symbol, symbol_resolution = _canonical_request_symbol(
        market,
        symbol,
        offline=offline,
    )
    store = SQLiteStore()
    cached_document = None
    if not refresh_source:
        cached_document = _find_cached_document(
            store,
            market,
            symbol,
            document_type,
            report_year,
            language,
            document_id,
        )
    if cached_document:
        evidence_started = time.perf_counter()
        cached_document_id = str(cached_document["document_id"])
        evidence = (
            get_evidence_packet(
                query,
                market=market,
                symbol=symbol,
                document_id=cached_document_id,
                max_pages=max_pages,
                max_chars=max_chars,
                include_structured_data=False,
                strategy=strategy,
                reconcile=False,
            )
            if extract_evidence
            else None
        )
        evidence_ms = round((time.perf_counter() - evidence_started) * 1000, 2)
        return {
            "ok": True,
            "requested_symbol": requested_symbol,
            "resolved_symbol": symbol,
            "symbol_resolution": symbol_resolution,
            "latest_report_year": (
                int(cached_document.get("report_year") or 0) or None
                if normalize_document_type(document_type) == "annual_report"
                and report_year is None
                else report_year
            ),
            "older_year_fallback_blocked": False,
            "document_id": cached_document_id,
            "local_pdf_path": cached_document.get("local_pdf_path"),
            "document": cached_document,
            "evidence_packet": evidence,
            "execution_info": {
                "run_id": uuid.uuid4().hex,
                "document_cache_hit": True,
                "source_lookup_skipped": True,
                "source_cache_hit": False,
                "remote_source_queried": False,
                "pdf_cache_hit": True,
                "ingest_cache_hit": True,
                "downloaded": False,
                "ingested": False,
                "evidence_skipped": not extract_evidence,
                "document_id": cached_document_id,
                "timings_ms": {
                    "source_lookup": 0.0,
                    "download": 0.0,
                    "text_extraction": 0.0,
                    "completeness_check": 0.0,
                    "identity_check": 0.0,
                    "validation": 0.0,
                    "ingest": 0.0,
                    "evidence": evidence_ms,
                    "total": round((time.perf_counter() - started) * 1000, 2),
                },
            },
        }

    source_started = time.perf_counter()
    located = find_filing_source(
        market,
        symbol,
        document_type,
        report_year=report_year,
        language=language,
        prefer_cache=prefer_cache,
        refresh=refresh_source,
        offline=offline,
        hkex_stock_id=hkex_stock_id,
        company_name=company_name,
    )
    located["requested_symbol"] = requested_symbol
    located["resolved_symbol"] = symbol
    located["symbol_resolution"] = symbol_resolution
    source_ms = round((time.perf_counter() - source_started) * 1000, 2)
    is_annual_report = normalize_document_type(document_type) == "annual_report"
    is_prospectus = normalize_document_type(document_type) == "prospectus"
    selected = located.get("selected")
    ranked_candidates = _rank_candidates(
        located.get("candidates") or [], document_type, report_year, language
    )
    ranked_candidates, latest_report_year = _latest_annual_report_candidates(
        ranked_candidates,
        document_type,
        report_year,
    )
    if is_annual_report and report_year is None and latest_report_year is not None:
        selected, _ = _select_candidate(
            ranked_candidates,
            document_type,
            latest_report_year,
            language,
        )
    if not selected and not ((is_annual_report or is_prospectus) and ranked_candidates):
        context = " ".join(
            str(value)
            for value in (market, symbol, document_type, report_year)
            if value is not None
        )
        return {
            **located,
            "error": f"No unambiguous filing source was selected for {context}.",
        }
    paths = get_data_paths()
    output_dir = paths.raw_hkex if market.upper().startswith("H") else paths.raw_cninfo
    pipeline_run_id = str((located.get("execution_info") or {}).get("run_id") or uuid.uuid4().hex)
    staging_dir = paths.staging_downloads / pipeline_run_id
    ordered_candidates = ([selected] if selected else []) + [
        candidate
        for candidate in ranked_candidates
        if not selected or _candidate_source_url(candidate) != _candidate_source_url(selected)
    ]
    validation_attempts: list[dict[str, Any]] = []
    downloaded: dict[str, Any] | None = None
    completeness: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None
    resolved_document_id: str | None = None
    extracted_pages: list[PdfPage] | None = None
    validation_cache_hit = False
    validation_cache_path: str | None = None
    download_ms = 0.0
    validation_ms = 0.0
    text_extraction_ms = 0.0
    completeness_check_ms = 0.0
    identity_check_ms = 0.0
    for candidate in ordered_candidates:
        candidate_url = _candidate_source_url(candidate)
        is_listing_package = _is_hkex_listing_package(candidate, document_type)
        if not isinstance(candidate_url, str) or not (
            candidate_url.lower().endswith(".pdf") or is_listing_package
        ):
            continue
        url = candidate_url
        if (
            is_annual_report
            and market.upper().startswith("H")
            and _is_overseas_regulatory_annual_report(candidate)
        ):
            validation_attempts.append(
                {
                    "title": candidate.get("title"),
                    "pdf_url": url,
                    "local_pdf_path": candidate.get("local_pdf_path"),
                    "completeness": None,
                    "error": "wrong document variant: overseas regulatory announcement",
                }
            )
            continue
        if (
            is_annual_report
            and market.upper().startswith("A")
            and _is_h_share_announcement(candidate)
        ):
            validation_attempts.append(
                {
                    "title": candidate.get("title"),
                    "pdf_url": url,
                    "local_pdf_path": candidate.get("local_pdf_path"),
                    "completeness": None,
                    "error": "wrong document variant: H-share announcement",
                }
            )
            continue
        candidate_meta = {
            **candidate,
            "market": market,
            "symbol": _canonical_candidate_symbol(market, symbol, candidate),
            "document_type": document_type,
            "report_year": report_year,
            "language": language,
        }
        candidate_document_id = build_document_id(
            candidate_meta,
            fallback_title=candidate.get("title") or "filing",
        )
        filename = build_pdf_filename(
            candidate_meta, fallback_title=candidate.get("title") or "filing"
        )
        if offline:
            cached_path = Path(str(candidate.get("local_pdf_path") or ""))
            if not cached_path.is_file():
                cached_path = output_dir / filename
            if not cached_path.is_file():
                validation_attempts.append(
                    {
                        "title": candidate.get("title"),
                        "pdf_url": url,
                        "local_pdf_path": None,
                        "completeness": None,
                        "error": "offline mode: PDF is not available locally",
                    }
                )
                continue
            candidate_download: dict[str, Any] = {
                "path": str(cached_path),
                "existed": True,
            }
        else:
            linked_path = Path(str(candidate.get("local_pdf_path") or ""))
            if linked_path.is_file():
                candidate_download = {"path": str(linked_path), "existed": True}
            elif is_listing_package:
                download_started = time.perf_counter()
                part_dir: Path | None = None
                try:
                    package_urls = get_thread_hkex_client(HkexClient).listing_package_pdf_urls(url)
                    if len(package_urls) < 2:
                        raise ValueError(
                            "HKEX listing package did not contain multiple sectional PDFs."
                        )
                    part_dir = staging_dir / "package_parts"
                    part_downloads = [
                        download_file(
                            part_url,
                            output_dir=part_dir,
                            filename=f"{index:03d}.pdf",
                        )
                        for index, part_url in enumerate(package_urls, start=1)
                    ]
                    merged_path = merge_pdf_parts(
                        [part["path"] for part in part_downloads],
                        staging_dir / filename,
                    )
                    candidate_download = {
                        "url": url,
                        "path": str(merged_path),
                        "filename": merged_path.name,
                        "bytes_written": merged_path.stat().st_size,
                        "sha256": file_sha256(merged_path),
                        "existed": False,
                        "staged": True,
                        "package_pdf_urls": package_urls,
                        "package_part_count": len(package_urls),
                    }
                except Exception as exc:
                    validation_attempts.append(
                        {
                            "title": candidate.get("title"),
                            "pdf_url": None,
                            "detail_url": url,
                            "local_pdf_path": None,
                            "completeness": None,
                            "error": f"listing package assembly failed: {type(exc).__name__}: {exc}",
                        }
                    )
                    continue
                finally:
                    if part_dir and part_dir.is_dir():
                        shutil.rmtree(part_dir, ignore_errors=True)
                download_ms += (time.perf_counter() - download_started) * 1000
            else:
                download_started = time.perf_counter()
                candidate_download = download_file(url, output_dir=staging_dir, filename=filename)
                candidate_download["staged"] = True
                download_ms += (time.perf_counter() - download_started) * 1000
        candidate_sha256 = str(
            candidate_download.get("sha256")
            or file_sha256(candidate_download["path"])
        )
        candidate_download["sha256"] = candidate_sha256
        cached_validation = _read_validation_cache(
            paths,
            candidate_document_id,
            candidate_sha256,
            document_type,
            candidate_meta["symbol"],
        )
        candidate_validation_cache_hit = cached_validation is not None
        candidate_pages = None
        candidate_completeness: dict[str, Any] | None
        extraction_elapsed = 0.0
        completeness_elapsed = 0.0
        if cached_validation is not None:
            candidate_completeness = cached_validation
        elif is_annual_report:
            extraction_started = time.perf_counter()
            candidate_pages = extract_pages(
                candidate_download["path"], ocr=ocr if ingest_if_missing else "off"
            )
            extraction_elapsed = (time.perf_counter() - extraction_started) * 1000
            text_extraction_ms += extraction_elapsed
            completeness_started = time.perf_counter()
            candidate_completeness = validate_annual_report_pages(
                candidate_download["path"], candidate_pages
            )
            completeness_elapsed = (time.perf_counter() - completeness_started) * 1000
            completeness_check_ms += completeness_elapsed
        elif is_prospectus:
            extraction_started = time.perf_counter()
            candidate_pages = extract_pages(
                candidate_download["path"], ocr=ocr if ingest_if_missing else "off"
            )
            extraction_elapsed = (time.perf_counter() - extraction_started) * 1000
            text_extraction_ms += extraction_elapsed
            completeness_started = time.perf_counter()
            candidate_completeness = validate_prospectus_pages(
                candidate_download["path"], candidate_pages
            )
            completeness_elapsed = (time.perf_counter() - completeness_started) * 1000
            completeness_check_ms += completeness_elapsed
        else:
            candidate_completeness = None
        identity_elapsed = 0.0
        if candidate_completeness and candidate_pages:
            identity_started = time.perf_counter()
            identity = validate_document_identity(
                candidate_pages,
                expected_year=report_year,
                expected_company_name=candidate.get("company_name"),
                expected_symbol=candidate_meta["symbol"],
            )
            candidate_completeness["identity"] = identity
            if candidate_completeness.get("complete") is True and not identity["passed"]:
                if (
                    is_prospectus
                    and market.upper().startswith("A")
                    and _trusted_a_prospectus_identity(
                        candidate, candidate_meta["symbol"], identity
                    )
                ):
                    identity["passed"] = True
                    identity["trusted_source_override"] = (
                        "CNINFO symbol-scoped exact prospectus title"
                    )
                else:
                    candidate_completeness["complete"] = None
                    candidate_completeness["status"] = "needs_review_identity_mismatch"
            identity_elapsed = (time.perf_counter() - identity_started) * 1000
            identity_check_ms += identity_elapsed
        validation_ms += extraction_elapsed + completeness_elapsed + identity_elapsed
        attempt = {
            "title": candidate.get("title"),
            "pdf_url": candidate.get("pdf_url"),
            "detail_url": candidate.get("detail_url"),
            "local_pdf_path": candidate_download["path"],
            "completeness": candidate_completeness,
            "validation_cache_hit": candidate_validation_cache_hit,
        }
        if candidate_completeness and candidate_completeness.get("complete") is False:
            attempt["disposition"] = (
                "deleted_staging"
                if discard_staged_candidate(candidate_download, paths.staging_downloads)
                else "retained_existing_file"
            )
            validation_attempts.append(attempt)
            continue
        if candidate_completeness and candidate_completeness.get("complete") is None:
            review_dir = paths.staging / "review"
            candidate_download = move_staged_candidate(
                candidate_download,
                review_dir,
                filename,
                str(url),
                paths.staging_downloads,
            )
            attempt["local_pdf_path"] = candidate_download["path"]
            attempt["disposition"] = "needs_review"
            if candidate_completeness is not None:
                candidate_completeness["path"] = candidate_download["path"]
            validation_attempts.append(attempt)
            continue
        candidate_download = move_staged_candidate(
            candidate_download,
            output_dir,
            filename,
            str(url),
            paths.staging_downloads,
        )
        attempt["local_pdf_path"] = candidate_download["path"]
        attempt["disposition"] = "accepted"
        if candidate_completeness is not None:
            candidate_completeness["path"] = candidate_download["path"]
        validation_attempts.append(attempt)
        selected = candidate
        meta = candidate_meta
        downloaded = candidate_download
        completeness = candidate_completeness
        extracted_pages = candidate_pages
        resolved_document_id = candidate_document_id
        validation_cache_hit = candidate_validation_cache_hit
        validation_cache_path = _write_validation_cache(
            paths,
            resolved_document_id,
            candidate_sha256,
            meta,
            completeness,
            str(url),
        )
        break

    if not selected or not meta or not downloaded or not resolved_document_id:
        latest_year_error = (
            f" Latest available report year {latest_report_year} did not pass validation; "
            "older-year fallback was blocked."
            if is_annual_report and report_year is None and latest_report_year is not None
            else ""
        )
        return {
            **located,
            "ok": False,
            "error": (
                "No complete annual report PDF passed validation." + latest_year_error
                if is_annual_report
                else "No complete prospectus PDF passed validation."
            ),
            "latest_report_year": latest_report_year,
            "older_year_fallback_blocked": bool(
                is_annual_report and report_year is None and latest_report_year is not None
            ),
            "validation_attempts": validation_attempts,
        }

    url = str(_candidate_source_url(selected) or "")
    store.link_filing_source_to_local_file(url, downloaded["path"], resolved_document_id)
    ingest_result: dict[str, Any] | None = None
    evidence = None
    ingest_ms = 0.0
    evidence_ms = 0.0
    if ingest_if_missing:
        ingest_started = time.perf_counter()
        ingest_result = ingest_pdf(
            downloaded["path"],
            document_id=resolved_document_id,
            meta=meta,
            ocr=ocr,
            pre_extracted_pages=extracted_pages,
            precomputed_md5=downloaded.get("md5"),
            precomputed_sha256=downloaded.get("sha256"),
        )
        ingest_ms = (time.perf_counter() - ingest_started) * 1000
        if extract_evidence:
            evidence_started = time.perf_counter()
            evidence = get_evidence_packet(
                query,
                market=market,
                symbol=symbol,
                document_id=resolved_document_id,
                max_pages=max_pages,
                max_chars=max_chars,
                include_structured_data=False,
                strategy=strategy,
                reconcile=False,
            )
            evidence_ms = (time.perf_counter() - evidence_started) * 1000
    execution = dict(located["execution_info"])
    source_timing_details = {
        key: value
        for key, value in dict(execution.get("timings_ms") or {}).items()
        if key != "total"
    }
    execution.update(
        {
            "pdf_cache_hit": bool(downloaded.get("existed")),
            "ingest_cache_hit": bool(ingest_result and ingest_result.get("ingest_cache_hit")),
            "downloaded": not bool(downloaded.get("existed")),
            "ingested": bool(ingest_result and ingest_result.get("ingested")),
            "evidence_skipped": not extract_evidence,
            "document_id": resolved_document_id,
            "document_cache_hit": False,
            "source_lookup_skipped": False,
            "validation_cache_hit": validation_cache_hit,
            "latest_report_year": latest_report_year,
            "timings_ms": {
                **source_timing_details,
                "source_lookup": source_ms,
                "download": round(download_ms, 2),
                "text_extraction": round(text_extraction_ms, 2),
                "completeness_check": round(completeness_check_ms, 2),
                "identity_check": round(identity_check_ms, 2),
                "validation": round(validation_ms, 2),
                "ingest": round(ingest_ms, 2),
                "evidence": round(evidence_ms, 2),
                "total": round((time.perf_counter() - started) * 1000, 2),
            },
        }
    )
    return {
        "ok": True,
        "requested_symbol": requested_symbol,
        "resolved_symbol": symbol,
        "symbol_resolution": symbol_resolution,
        "latest_report_year": latest_report_year,
        "older_year_fallback_blocked": False,
        "document_id": resolved_document_id,
        "local_pdf_path": downloaded["path"],
        "document": {
            **selected,
            "document_id": resolved_document_id,
            "local_pdf_path": downloaded["path"],
        },
        "download": downloaded,
        "completeness": completeness,
        "document_validation": completeness,
        "validation_cache_hit": validation_cache_hit,
        "validation_cache_path": validation_cache_path,
        "validation_attempts": validation_attempts,
        "ingest": ingest_result,
        "evidence_packet": evidence,
        "execution_info": execution,
    }


def prepare_filing(
    market: str,
    symbol: str,
    document_type: str,
    report_year: int | None = None,
    language: str | None = None,
    document_id: str | None = None,
    prefer_cache: bool = True,
    refresh_source: bool = False,
    offline: bool = False,
    ocr: str = "auto",
    hkex_stock_id: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    """Locate, validate, download, and ingest one filing without evidence retrieval."""
    return ensure_filing_evidence(
        query="",
        market=market,
        symbol=symbol,
        document_type=document_type,
        report_year=report_year,
        language=language,
        document_id=document_id,
        prefer_cache=prefer_cache,
        refresh_source=refresh_source,
        offline=offline,
        ingest_if_missing=True,
        ocr=ocr,
        hkex_stock_id=hkex_stock_id,
        company_name=company_name,
        extract_evidence=False,
    )
