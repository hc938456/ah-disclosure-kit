from __future__ import annotations

from ah_disclosure.services import filing_pipeline
from ah_disclosure.models import PdfPage
from ah_disclosure.pdf.downloader import file_sha256
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _candidate():
    return {
        "market": "H",
        "symbol": "00700",
        "title": "ANNUAL REPORT 2024",
        "document_type": "annual_report",
        "publish_time": "2025-04-08",
        "source": "HKEXnews",
        "pdf_url": "https://example.com/annual-report-2024.pdf",
    }


def test_find_filing_source_reports_remote_lookup(monkeypatch):
    calls = []

    def fake_search(*args, offline=False, refresh=False, **kwargs):
        calls.append((offline, refresh))
        if offline:
            raise RuntimeError("cache miss")
        return [_candidate()]

    monkeypatch.setattr(filing_pipeline, "_search_source", fake_search)

    result = filing_pipeline.find_filing_source("H", "00700", "annual_report", 2024)

    assert result["selected"]["pdf_url"].endswith(".pdf")
    assert result["execution_info"]["remote_source_queried"] is True
    assert result["execution_info"]["timings_ms"]["cache_lookup"] >= 0
    assert result["execution_info"]["timings_ms"]["remote_lookup"] >= 0
    assert result["execution_info"]["timings_ms"]["selection"] >= 0
    assert calls == [(True, False), (False, True)]


def test_find_filing_source_selects_latest_annual_report_when_year_is_omitted(monkeypatch):
    monkeypatch.setattr(
        filing_pipeline,
        "_search_source",
        lambda *args, **kwargs: [
            {
                "market": "H",
                "symbol": "00700",
                "title": "2024 ANNUAL REPORT",
                "document_type": "annual_report",
                "source": "HKEXnews",
                "publish_time": "2025-04-01",
                "pdf_url": "https://example.test/2024.pdf",
            },
            {
                "market": "H",
                "symbol": "00700",
                "title": "FISCAL YEAR 2025 ANNUAL REPORT",
                "document_type": "annual_report",
                "source": "HKEXnews",
                "publish_time": "2026-04-01",
                "pdf_url": "https://example.test/2025.pdf",
            },
        ],
    )

    result = filing_pipeline.find_filing_source(
        "H", "00700", "annual_report", report_year=None, prefer_cache=False
    )

    assert result["ambiguous"] is False
    assert result["selected"]["title"] == "FISCAL YEAR 2025 ANNUAL REPORT"


def test_find_filing_source_uses_cached_lookup(monkeypatch):
    monkeypatch.setattr(filing_pipeline, "_search_source", lambda *args, **kwargs: [_candidate()])

    result = filing_pipeline.find_filing_source("H", "00700", "annual_report", 2024)

    assert result["execution_info"]["source_cache_hit"] is True
    assert result["execution_info"]["remote_source_queried"] is False


def test_find_filing_source_respects_cached_empty_result(monkeypatch):
    calls = []

    def fake_search(*args, offline=False, **kwargs):
        calls.append(offline)
        if not offline:
            raise AssertionError("cached empty result should not trigger a remote query")
        return []

    monkeypatch.setattr(filing_pipeline, "_search_source", fake_search)

    result = filing_pipeline.find_filing_source("H", "02513", "prospectus")

    assert result["ok"] is False
    assert result["candidates"] == []
    assert result["execution_info"]["source_cache_hit"] is True
    assert result["execution_info"]["remote_source_queried"] is False
    assert calls == [True]


def test_find_filing_source_defaults_a_share_to_chinese(monkeypatch):
    captured = {}

    def fake_search(*args, **kwargs):
        captured["language"] = args[4]
        return [_candidate()]

    monkeypatch.setattr(filing_pipeline, "_search_source", fake_search)

    filing_pipeline.find_filing_source("A", "600519", "annual_report", 2024)

    assert captured["language"] == "ZH"


def test_exact_annual_report_title_beats_publication_notice(monkeypatch):
    rows = [
        {
            **_candidate(),
            "title": "NOTICE OF PUBLICATION OF 2024 ANNUAL REPORT AND REPLY FORM",
            "pdf_url": "https://example.com/notice.pdf",
        },
        _candidate(),
    ]
    monkeypatch.setattr(filing_pipeline, "_search_source", lambda *args, **kwargs: rows)

    result = filing_pipeline.find_filing_source("H", "00700", "annual_report", 2024)

    assert result["ambiguous"] is False
    assert result["selected"]["pdf_url"].endswith("annual-report-2024.pdf")


def test_latest_duplicate_exact_annual_report_is_selected(monkeypatch):
    older = {**_candidate(), "publish_time": "2025-03-01", "pdf_url": "https://example.com/old.pdf"}
    newer = {**_candidate(), "publish_time": "2025-04-01", "pdf_url": "https://example.com/new.pdf"}
    monkeypatch.setattr(filing_pipeline, "_search_source", lambda *args, **kwargs: [older, newer])

    result = filing_pipeline.find_filing_source("H", "00700", "annual_report", 2024)

    assert result["ambiguous"] is False
    assert result["selected"]["pdf_url"].endswith("new.pdf")


def test_later_complete_annual_report_with_parenthetical_suffix_is_preferred(monkeypatch):
    notice = {
        **_candidate(),
        "title": "2025 Annual Report and Accounts",
        "publish_time": "2026-02-26",
        "pdf_url": "https://example.com/notice.pdf",
    }
    complete = {
        **_candidate(),
        "title": "Annual Report and Accounts 2025 (with employee share plans)",
        "publish_time": "2026-03-27",
        "pdf_url": "https://example.com/complete.pdf",
    }
    monkeypatch.setattr(
        filing_pipeline, "_search_source", lambda *args, **kwargs: [notice, complete]
    )

    result = filing_pipeline.find_filing_source("H", "00005", "annual_report", 2025)

    assert result["selected"]["pdf_url"].endswith("complete.pdf")


def test_chinese_annual_report_beats_later_english_version(monkeypatch):
    chinese = {
        **_candidate(),
        "title": "示例公司2024年年度报告",
        "publish_time": "2025-04-01",
        "pdf_url": "https://example.com/chinese.pdf",
    }
    english = {
        **_candidate(),
        "title": "示例公司2024年年度报告（英文版）",
        "publish_time": "2025-05-01",
        "pdf_url": "https://example.com/english.pdf",
    }
    monkeypatch.setattr(filing_pipeline, "_search_source", lambda *args, **kwargs: [english, chinese])

    result = filing_pipeline.find_filing_source(
        "A", "600000", "annual_report", 2024, language="ZH"
    )

    assert result["selected"]["pdf_url"].endswith("chinese.pdf")


def test_a_share_annual_report_beats_h_share_announcement(monkeypatch):
    a_report = {
        **_candidate(),
        "title": "示例公司2024年年度报告",
        "pdf_url": "https://example.com/a-report.pdf",
    }
    h_announcement = {
        **_candidate(),
        "title": "港股公告：2024年年报",
        "publish_time": "2025-05-01",
        "pdf_url": "https://example.com/h-announcement.pdf",
    }
    monkeypatch.setattr(
        filing_pipeline, "_search_source", lambda *args, **kwargs: [h_announcement, a_report]
    )

    result = filing_pipeline.find_filing_source(
        "A", "688981", "annual_report", 2024, language="ZH"
    )

    assert result["selected"]["pdf_url"].endswith("a-report.pdf")


def test_a_share_annual_report_beats_cninfo_h_share_announcement(monkeypatch):
    a_report = {
        **_candidate(),
        "title": "建设银行2025年度报告",
        "pdf_url": "https://example.com/a-report.pdf",
    }
    h_announcement = {
        **_candidate(),
        "title": "建设银行H股公告-2025年年度报告",
        "publish_time": "2026-04-28",
        "pdf_url": "https://example.com/h-announcement.pdf",
    }
    monkeypatch.setattr(
        filing_pipeline,
        "_search_source",
        lambda *args, **kwargs: [h_announcement, a_report],
    )

    result = filing_pipeline.find_filing_source(
        "A", "601939", "annual_report", report_year=None, language="ZH"
    )

    assert result["ambiguous"] is False
    assert result["selected"]["pdf_url"].endswith("a-report.pdf")


def test_h_annual_report_rejects_overseas_regulatory_variant():
    assert filing_pipeline._is_overseas_regulatory_annual_report(
        {"title": "海外監管公告 2025年年度報告"}
    )
    assert not filing_pipeline._is_overseas_regulatory_annual_report(
        {"title": "二零二五年年報"}
    )


def test_a_annual_report_recognizes_h_share_announcement_variant():
    assert filing_pipeline._is_h_share_announcement(
        {"title": "建设银行H股公告-2025年年度报告"}
    )
    assert not filing_pipeline._is_h_share_announcement(
        {"title": "建设银行2025年度报告"}
    )


def test_ensure_uses_matching_local_document_without_source_lookup(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    document_id = "H_00700_2024_annual_report_EN_TENCENT"
    pdf_path = data_dir / "raw" / "hkex" / f"{document_id}.pdf"
    pages_path = data_dir / "parsed" / document_id / "pages.jsonl"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF placeholder")
    pages_path.write_text("", encoding="utf-8")
    store = SQLiteStore()
    store.upsert_document(
        {
            "document_id": document_id,
            "market": "H",
            "symbol": "00700",
            "document_type": "annual_report",
            "report_year": 2024,
            "title": "Annual Report 2024",
            "local_pdf_path": str(pdf_path),
            "pages_jsonl_path": str(pages_path),
        }
    )
    store.upsert_page(document_id, 12, "Revenue recognition accounting policy.")
    monkeypatch.setattr(
        filing_pipeline,
        "find_filing_source",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("source lookup called")),
    )
    evidence_options = {}

    def fake_evidence(*args, **kwargs):
        evidence_options.update(kwargs)
        return {"evidence_items": []}

    monkeypatch.setattr(filing_pipeline, "get_evidence_packet", fake_evidence)

    result = filing_pipeline.ensure_filing_evidence(
        "revenue recognition",
        "H",
        "00700",
        "annual_report",
        report_year=2024,
        language="EN",
    )

    assert result["ok"] is True
    assert result["document_id"] == document_id
    assert result["local_pdf_path"] == str(pdf_path)
    assert result["execution_info"]["document_cache_hit"] is True
    assert result["execution_info"]["source_lookup_skipped"] is True
    assert result["execution_info"]["timings_ms"]["evidence"] >= 0
    assert evidence_options["include_structured_data"] is False


def test_cached_document_is_rejected_when_pdf_hash_changes(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    document_id = "H_00700_2024_annual_report_EN_TENCENT"
    pdf_path = data_dir / "raw" / "hkex" / f"{document_id}.pdf"
    pages_path = data_dir / "parsed" / document_id / "pages.jsonl"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF original")
    pages_path.write_text('{"page_no":1,"text":"revenue"}\n', encoding="utf-8")
    store = SQLiteStore()
    store.upsert_document(
        {
            "document_id": document_id,
            "market": "H",
            "symbol": "00700",
            "document_type": "annual_report",
            "report_year": 2024,
            "title": "Annual Report 2024",
            "local_pdf_path": str(pdf_path),
            "pages_jsonl_path": str(pages_path),
            "sha256": file_sha256(pdf_path),
        }
    )
    pdf_path.write_bytes(b"%PDF replaced")

    cached = filing_pipeline._find_cached_document(
        store, "H", "00700", "annual_report", 2024, "EN", None
    )

    assert cached is None


def test_cached_document_is_rejected_when_sqlite_pages_are_missing(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    document_id = "H_00700_2024_annual_report_EN_TENCENT"
    pdf_path = data_dir / "raw" / "hkex" / f"{document_id}.pdf"
    pages_path = data_dir / "parsed" / document_id / "pages.jsonl"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF original")
    pages_path.write_text('{"page_no":1,"text":"revenue"}\n', encoding="utf-8")
    store = SQLiteStore()
    store.upsert_document(
        {
            "document_id": document_id,
            "market": "H",
            "symbol": "00700",
            "document_type": "annual_report",
            "report_year": 2024,
            "title": "Annual Report 2024",
            "local_pdf_path": str(pdf_path),
            "pages_jsonl_path": str(pages_path),
            "sha256": file_sha256(pdf_path),
            "page_count": 2,
        }
    )
    store.upsert_page(document_id, 1, "revenue")

    cached = filing_pipeline._find_cached_document(
        store, "H", "00700", "annual_report", 2024, "EN", None
    )

    assert cached is None


def test_offline_mode_does_not_download_missing_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        filing_pipeline,
        "find_filing_source",
        lambda *args, **kwargs: {
            "ok": True,
            "selected": _candidate(),
            "candidates": [_candidate()],
            "ambiguous": False,
            "execution_info": {
                "source_cache_hit": True,
                "remote_source_queried": False,
                "timings_ms": {"total": 0.1},
            },
        },
    )
    monkeypatch.setattr(
        filing_pipeline,
        "download_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("download called")),
    )

    result = filing_pipeline.ensure_filing_evidence(
        "revenue",
        "H",
        "00700",
        "annual_report",
        report_year=2024,
        language="EN",
        offline=True,
    )

    assert result["ok"] is False
    assert "No complete annual report" in result["error"]
    assert result["validation_attempts"][0]["error"].startswith("offline mode")


def test_refresh_source_bypasses_document_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    store = SQLiteStore()
    document_id = "H_00700_2024_annual_report_EN_TENCENT"
    pdf_path = tmp_path / "data" / "raw" / f"{document_id}.pdf"
    pages_path = tmp_path / "data" / "parsed" / document_id / "pages.jsonl"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pages_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF placeholder")
    pages_path.write_text("", encoding="utf-8")
    store.upsert_document(
        {
            "document_id": document_id,
            "market": "H",
            "symbol": "00700",
            "document_type": "annual_report",
            "report_year": 2024,
            "title": "Annual Report 2024",
            "local_pdf_path": str(pdf_path),
            "pages_jsonl_path": str(pages_path),
        }
    )
    called = {"source": False}

    def fake_find(*args, **kwargs):
        called["source"] = True
        return {
            "ok": False,
            "selected": None,
            "candidates": [],
            "ambiguous": False,
            "execution_info": {"timings_ms": {"total": 0.0}},
        }

    monkeypatch.setattr(filing_pipeline, "find_filing_source", fake_find)

    result = filing_pipeline.ensure_filing_evidence(
        "revenue",
        "H",
        "00700",
        "annual_report",
        report_year=2024,
        refresh_source=True,
    )

    assert called["source"] is True
    assert result["ok"] is False


def test_accepted_candidate_is_promoted_and_reuses_extracted_pages(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    candidate = _candidate()
    candidate["document_type"] = "annual_report"
    monkeypatch.setattr(
        filing_pipeline,
        "find_filing_source",
        lambda *args, **kwargs: {
            "ok": True,
            "selected": candidate,
            "candidates": [candidate],
            "ambiguous": False,
            "execution_info": {
                "run_id": "test-run",
                "source_cache_hit": False,
                "remote_source_queried": True,
                "timings_ms": {
                    "cache_lookup": 0.01,
                    "remote_lookup": 0.05,
                    "selection": 0.01,
                    "total": 0.1,
                },
            },
        },
    )

    def fake_download(url, output_dir, filename):
        path = output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF placeholder")
        sha256 = filing_pipeline.file_sha256(path)
        return {
            "path": str(path),
            "url": url,
            "existed": False,
            "md5": "download-md5",
            "sha256": sha256,
        }

    pages = [
        PdfPage(
            page_no=index,
            text="Sample Company Stock Code 700 Annual Report 2024 "
            "Independent auditor's report Notes to the financial statements "
            "Statement of financial position Statement of comprehensive income",
            char_count=200,
        )
        for index in range(1, 41)
    ]
    calls = {"extract": 0, "ingest": 0}

    def fake_extract(*args, **kwargs):
        calls["extract"] += 1
        return pages

    def fake_ingest(*args, **kwargs):
        calls["ingest"] += 1
        assert kwargs["pre_extracted_pages"] is (
            pages if calls["ingest"] == 1 else None
        )
        assert kwargs["precomputed_md5"] == "download-md5"
        assert kwargs["precomputed_sha256"] == filing_pipeline.file_sha256(args[0])
        return {"ingested": True, "ingest_cache_hit": False}

    monkeypatch.setattr(filing_pipeline, "download_file", fake_download)
    monkeypatch.setattr(filing_pipeline, "extract_pages", fake_extract)
    monkeypatch.setattr(filing_pipeline, "ingest_pdf", fake_ingest)
    evidence_options = {}

    def fake_evidence(*args, **kwargs):
        evidence_options.update(kwargs)
        return {}

    monkeypatch.setattr(filing_pipeline, "get_evidence_packet", fake_evidence)

    result = filing_pipeline.ensure_filing_evidence(
        "revenue", "H", "00700", "annual_report", report_year=2024
    )

    accepted_path = data_dir / "raw" / "hkex" / result["download"]["filename"]
    assert result["ok"] is True
    assert result["document_id"] == result["execution_info"]["document_id"]
    assert result["local_pdf_path"] == str(accepted_path)
    assert result["completeness"]["path"] == str(accepted_path)
    assert accepted_path.is_file()
    assert not list((data_dir / "staging" / "downloads").rglob("*.pdf"))
    assert calls == {"extract": 1, "ingest": 1}
    assert evidence_options["include_structured_data"] is False
    assert result["execution_info"]["timings_ms"]["cache_lookup"] == 0.01
    assert result["execution_info"]["timings_ms"]["remote_lookup"] == 0.05
    assert result["execution_info"]["timings_ms"]["selection"] == 0.01
    timings = result["execution_info"]["timings_ms"]
    assert timings["text_extraction"] >= 0
    assert timings["completeness_check"] >= 0
    assert timings["identity_check"] >= 0
    detail_total = (
        timings["text_extraction"]
        + timings["completeness_check"]
        + timings["identity_check"]
    )
    assert abs(timings["validation"] - detail_total) <= 0.02

    refreshed = filing_pipeline.ensure_filing_evidence(
        "revenue",
        "H",
        "00700",
        "annual_report",
        report_year=2024,
        refresh_source=True,
    )

    assert refreshed["ok"] is True
    assert refreshed["validation_cache_hit"] is True
    assert refreshed["execution_info"]["validation_cache_hit"] is True
    assert refreshed["execution_info"]["timings_ms"]["validation"] == 0.0
    assert calls == {"extract": 1, "ingest": 2}


def test_rejected_candidate_is_deleted_before_ingest(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(data_dir))
    candidate = {
        **_candidate(),
        "title": "GLOBAL OFFERING",
        "document_type": "prospectus",
    }
    monkeypatch.setattr(
        filing_pipeline,
        "find_filing_source",
        lambda *args, **kwargs: {
            "ok": True,
            "selected": candidate,
            "candidates": [candidate],
            "ambiguous": False,
            "execution_info": {"run_id": "test-run", "timings_ms": {"total": 0.1}},
        },
    )

    def fake_download(url, output_dir, filename):
        path = output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF placeholder")
        return {"path": str(path), "url": url, "existed": False}

    monkeypatch.setattr(filing_pipeline, "download_file", fake_download)
    monkeypatch.setattr(
        filing_pipeline,
        "extract_pages",
        lambda *args, **kwargs: [PdfPage(1, "GLOBAL OFFERING notice", 22)] * 9,
    )
    monkeypatch.setattr(
        filing_pipeline,
        "ingest_pdf",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("ingest called")),
    )

    result = filing_pipeline.ensure_filing_evidence(
        "business", "H", "09992", "prospectus", report_year=2020
    )

    assert result["ok"] is False
    assert result["validation_attempts"][0]["disposition"] == "deleted_staging"
    assert not list((data_dir / "staging" / "downloads").rglob("*.pdf"))
    assert not list((data_dir / "raw").rglob("*.pdf"))


def test_prepare_filing_skips_evidence_for_cached_document(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(
        filing_pipeline,
        "_find_cached_document",
        lambda *args, **kwargs: {
            "document_id": "H_02475_2026_prospectus_ZH_LUXSHARE_ICT",
            "local_pdf_path": "C:/data/luxshare.pdf",
        },
    )
    monkeypatch.setattr(
        filing_pipeline,
        "get_evidence_packet",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must be skipped")),
    )

    result = filing_pipeline.prepare_filing(
        "H",
        "02475",
        "prospectus",
        report_year=2026,
        language="ZH",
    )

    assert result["ok"] is True
    assert result["evidence_packet"] is None
    assert result["execution_info"]["evidence_skipped"] is True


def test_trusted_cninfo_prospectus_allows_prelisting_identity(monkeypatch):
    candidate = {
        "market": "A",
        "symbol": "688347",
        "company_name": "华虹公司",
        "title": "华虹公司首次公开发行股票并在科创板上市招股说明书",
        "source": "CNINFO",
    }
    identity = {"passed": False, "company_match": False, "symbol_match": False}

    assert filing_pipeline._trusted_a_prospectus_identity(
        candidate, "688347", identity
    ) is True


def test_trusted_cninfo_override_rejects_intent_letter(monkeypatch):
    candidate = {
        "market": "A",
        "symbol": "688347",
        "title": "华虹公司首次公开发行股票并在科创板上市招股意向书",
        "source": "CNINFO",
    }

    assert filing_pipeline._trusted_a_prospectus_identity(
        candidate, "688347", {"passed": False}
    ) is False


def test_bse_legacy_symbol_uses_provider_current_code():
    candidate = {"market": "A", "symbol": "920978", "source": "CNINFO"}

    assert filing_pipeline._canonical_candidate_symbol(
        "A", "832978", candidate
    ) == "920978"


def test_non_bse_symbol_keeps_requested_code():
    candidate = {"market": "A", "symbol": "600309", "source": "CNINFO"}

    assert filing_pipeline._canonical_candidate_symbol(
        "A", "600309", candidate
    ) == "600309"


def test_latest_annual_report_failure_does_not_fall_back_to_older_year(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    candidates = [
        {
            "market": "A",
            "symbol": "688396",
            "company_name": "华润微",
            "title": "2025年年度报告",
            "source": "CNINFO",
            "pdf_url": "https://example.com/2025.pdf",
        },
        {
            "market": "A",
            "symbol": "688396",
            "company_name": "华润微",
            "title": "2024年年度报告",
            "source": "CNINFO",
            "pdf_url": "https://example.com/2024.pdf",
        },
    ]
    monkeypatch.setattr(
        filing_pipeline,
        "find_filing_source",
        lambda *args, **kwargs: {
            "ok": True,
            "selected": candidates[0],
            "candidates": candidates,
            "ambiguous": False,
            "execution_info": {"run_id": "latest-year", "timings_ms": {}},
        },
    )
    downloaded_urls = []

    def fake_download(url, output_dir, filename):
        downloaded_urls.append(url)
        path = output_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF placeholder")
        return {"path": str(path), "url": url, "existed": False}

    monkeypatch.setattr(filing_pipeline, "download_file", fake_download)
    monkeypatch.setattr(
        filing_pipeline,
        "extract_pages",
        lambda *args, **kwargs: [PdfPage(1, "2025 annual report", 18)] * 10,
    )

    result = filing_pipeline.ensure_filing_evidence(
        "", "A", "688396", "annual_report", report_year=None
    )

    assert result["ok"] is False
    assert result["latest_report_year"] == 2025
    assert result["older_year_fallback_blocked"] is True
    assert downloaded_urls == ["https://example.com/2025.pdf"]
