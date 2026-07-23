from __future__ import annotations

import pytest

from ah_disclosure.models import FilingRecord
from ah_disclosure.core.time_utils import current_date_yyyymmdd
from ah_disclosure.services import disclosure_service, prospectus_service
from ah_disclosure.storage.sqlite_store import SQLiteStore


def _filing(symbol: str = "600519", market: str = "A") -> FilingRecord:
    return FilingRecord(
        market=market,
        symbol=symbol,
        company_name="Sample Company",
        title="2024 Annual Report" if market == "H" else "2024 年年度报告",
        publish_time="2025-04-01",
        document_type="annual_report",
        source="HKEXnews" if market == "H" else "CNINFO",
        detail_url="https://example.com/report.pdf",
        pdf_url="https://example.com/report.pdf",
        raw_id="report-2024",
    )


def test_source_query_cache_round_trips_empty_results(tmp_path):
    store = SQLiteStore(tmp_path / "test.sqlite")
    store.put_source_query(
        "market=A|symbol=000001|type=prospectus",
        [],
        source="CNINFO",
        ttl_seconds=3600,
    )

    cached = store.get_source_query("market=A|symbol=000001|type=prospectus")

    assert cached is not None
    assert cached["records"] == []
    assert cached["cache_status"] == "hit"


def test_source_query_cache_enriches_linked_local_pdf(tmp_path):
    store = SQLiteStore(tmp_path / "test.sqlite")
    record = _filing(market="H").to_dict()
    signature = "market=H|symbol=00005|type=annual_report"
    store.put_source_query(signature, [record], source="HKEXnews", ttl_seconds=3600)
    store.link_filing_source_to_local_file(
        record["pdf_url"], "C:/data/full-report.pdf", "H_00005_2024_annual_report_EN_HSBC"
    )

    cached = store.get_source_query(signature)

    assert cached["records"][0]["local_pdf_path"] == "C:/data/full-report.pdf"
    assert cached["records"][0]["document_id"].startswith("H_00005")


def test_a_filing_search_uses_persistent_query_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = {"count": 0}

    def fake_search(self, **kwargs):
        calls["count"] += 1
        return [_filing()]

    monkeypatch.setattr(disclosure_service.CninfoClient, "search_filings", fake_search)

    first = disclosure_service.search_a_filings("600519", max_rows=5)
    second = disclosure_service.search_a_filings("600519", max_rows=5)

    assert first == second
    assert calls["count"] == 1


def test_a_filing_default_end_date_uses_current_system_date(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    captured = {}

    def fake_search(self, **kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(disclosure_service.CninfoClient, "search_filings", fake_search)

    disclosure_service.search_a_filings("600519", prefer_cache=False)

    assert captured["end_date"] == current_date_yyyymmdd()


def test_a_filing_refresh_bypasses_query_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = {"count": 0}

    def fake_search(self, **kwargs):
        calls["count"] += 1
        return [_filing()]

    monkeypatch.setattr(disclosure_service.CninfoClient, "search_filings", fake_search)

    disclosure_service.search_a_filings("600519", max_rows=5)
    disclosure_service.search_a_filings("600519", max_rows=5, refresh=True)

    assert calls["count"] == 2


def test_a_filing_refresh_preserves_linked_local_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    record = _filing().to_dict()
    monkeypatch.setattr(
        disclosure_service.CninfoClient,
        "search_filings",
        lambda self, **kwargs: [FilingRecord(**record)],
    )
    first = disclosure_service.search_a_filings("600519", max_rows=5)
    SQLiteStore().link_filing_source_to_local_file(
        first[0]["pdf_url"],
        "C:/data/a-report.pdf",
        "A_600519_2024_annual_report_ZH_SAMPLE",
    )

    refreshed = disclosure_service.search_a_filings("600519", max_rows=5, refresh=True)

    assert refreshed[0]["local_pdf_path"] == "C:/data/a-report.pdf"
    assert refreshed[0]["document_id"].startswith("A_600519")


def test_h_filing_refresh_preserves_linked_local_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    record = _filing(symbol="00005", market="H")
    monkeypatch.setattr(
        disclosure_service,
        "resolve_hkex_stock_id",
        lambda *args, **kwargs: {
            "symbol": "00005",
            "hkex_stock_id": "123",
            "company_name": "Sample Company",
        },
    )
    monkeypatch.setattr(
        disclosure_service.HkexClient,
        "search_filings",
        lambda self, *args, **kwargs: [record],
    )
    first = disclosure_service.search_h_filings("00005", max_rows=5)
    SQLiteStore().link_filing_source_to_local_file(
        first[0]["pdf_url"],
        "C:/data/h-report.pdf",
        "H_00005_2024_annual_report_EN_SAMPLE",
    )

    refreshed = disclosure_service.search_h_filings("00005", max_rows=5, refresh=True)

    assert refreshed[0]["local_pdf_path"] == "C:/data/h-report.pdf"
    assert refreshed[0]["document_id"].startswith("H_00005")


def test_h_filing_cache_is_shared_across_row_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))
    calls = []
    records = [
        FilingRecord(
            **{
                **_filing(symbol="02513", market="H").to_dict(),
                "title": f"GLOBAL OFFERING {index}",
                "pdf_url": f"https://example.com/{index}.pdf",
                "detail_url": f"https://example.com/{index}.pdf",
                "raw_id": str(index),
            }
        )
        for index in range(30)
    ]
    monkeypatch.setattr(
        disclosure_service,
        "resolve_hkex_stock_id",
        lambda *args, **kwargs: {"symbol": "02513", "hkex_stock_id": "123"},
    )

    def fake_search(self, *args, **kwargs):
        calls.append(kwargs["max_rows"])
        return records[: kwargs["max_rows"]]

    monkeypatch.setattr(disclosure_service.HkexClient, "search_filings", fake_search)

    first = disclosure_service.search_h_filings(
        "02513", title_keyword="Global Offering", max_rows=20
    )
    second = disclosure_service.search_h_filings(
        "02513", title_keyword="Global Offering", max_rows=10
    )

    assert len(first) == 20
    assert len(second) == 10
    assert calls == [disclosure_service.HKEX_CACHE_FETCH_ROWS]


def test_a_filing_offline_cache_miss_is_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))

    with pytest.raises(RuntimeError, match="Offline source cache miss"):
        disclosure_service.search_a_filings("600519", max_rows=5, offline=True)


def test_remote_failure_returns_stale_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("AH_DISCLOSURE_DATA_DIR", str(tmp_path / "data"))

    monkeypatch.setattr(
        disclosure_service.CninfoClient,
        "search_filings",
        lambda self, **kwargs: [_filing()],
    )
    disclosure_service.search_a_filings("600519", max_rows=5)

    def fail(self, **kwargs):
        raise ConnectionError("upstream unavailable")

    monkeypatch.setattr(disclosure_service.CninfoClient, "search_filings", fail)
    rows = disclosure_service.search_a_filings("600519", max_rows=5, refresh=True)

    assert rows[0]["cache_stale"] is True


def test_h_prospectus_stops_after_first_direct_pdf(monkeypatch):
    calls: list[str] = []

    def fake_search_h_filings(symbol, **kwargs):
        calls.append(kwargs["title_keyword"])
        return [
            {
                "market": "H",
                "symbol": symbol,
                "title": "GLOBAL OFFERING",
                "source": "HKEXnews",
                "pdf_url": "https://example.com/global-offering.pdf",
            }
        ]

    monkeypatch.setattr(prospectus_service, "search_h_filings", fake_search_h_filings)

    rows = prospectus_service.search_h_prospectus(symbol="01024", max_rows=5)

    assert len(rows) == 1
    assert calls == ["Global Offering"]
