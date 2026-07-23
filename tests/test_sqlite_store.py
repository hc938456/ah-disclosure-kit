from concurrent.futures import ThreadPoolExecutor

from ah_disclosure.storage.sqlite_store import SQLiteStore
from ah_disclosure.models import PdfPage


def test_sqlite_schema(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    db.upsert_page("doc1", 1, "This page discusses revenue and risk.")
    assert db.search_pages("revenue")


def test_phrase_search_filters_loose_token_matches(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    db.upsert_page("doc1", 1, "The incentives are deducted from revenues.")
    db.upsert_page("doc1", 2, "Costs are deducted from its revenues.")

    rows = db.search_pages("deducted from revenues", "doc1", 10)

    assert [row["page_no"] for row in rows] == [1]


def test_phrase_search_falls_back_when_exact_filter_would_drop_all_hits(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    db.upsert_page("doc1", 1, "The cost details of wages and other items affected revenues.")

    rows = db.search_pages("cost of revenues", "doc1", 10)

    assert [row["page_no"] for row in rows] == [1]


def test_chinese_search_falls_back_when_fts_returns_no_hits(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "贵州茅台年报"})
    db.upsert_page("doc1", 56, "营业收入是公司关键业绩指标，可能存在不恰当的收入确认风险。")

    rows = db.search_pages("收入确认", "doc1", 10)

    assert [row["page_no"] for row in rows] == [56]
    assert "收入确认" in rows[0]["snippet"]


def test_compact_chinese_search_merges_substring_hits_when_fts_has_partial_hits(tmp_path, monkeypatch):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "年度报告"})
    db.upsert_page("doc1", 9, "王亚歌先生为公司首席财务官。")
    db.upsert_page("doc1", 39, "王亚歌，毕业于中国财政科学研究院，具有注册会计师资格。")

    original = db._search_pages_substring
    calls = []

    def tracked_substring(conn, query, document_id=None, limit=8):
        calls.append((query, document_id, limit))
        return original(conn, query, document_id, limit)

    monkeypatch.setattr(db, "_search_pages_substring", tracked_substring)
    rows = db.search_pages("王亚歌", "doc1", 24)

    assert calls, "已有 FTS 命中时，短中文词仍应执行子串补召回"
    assert [row["page_no"] for row in rows] == [9, 39]
    assert "中国财政科学研究院" in rows[1]["snippet"]


def test_chinese_multi_term_search_ranks_page_matching_more_terms(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "招股说明书"})
    db.upsert_page("doc1", 1, "主营业务收入和经营成果分析。")
    db.upsert_page(
        "doc1",
        20,
        "2023年度 传输类产品144471.46万元 音视频类产品94987.60万元 充电类产品155718.17万元",
    )

    rows = db.search_pages(
        "2023年度 传输类产品 音视频类产品 充电类产品",
        "doc1",
        5,
    )

    assert rows[0]["page_no"] == 20
    assert rows[0]["score"] >= 4


def test_long_llm_query_merges_partial_term_pages_even_when_fts_has_an_exact_hit(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "Prospectus"})
    db.upsert_page(
        "doc1",
        10,
        "Our business model earns revenue from interactive marketing services and merchandise sales through vending machines.",
    )
    db.upsert_page(
        "doc1",
        12,
        "We derive revenue primarily from marketing services offered to brand customers.",
    )

    rows = db.search_pages(
        "business model revenue interactive marketing services merchandise sales vending machines",
        "doc1",
        8,
    )

    assert [row["page_no"] for row in rows] == [10, 12]


def test_filing_insert_replaces_same_record(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    row = {
        "market": "H",
        "symbol": "03690",
        "title": "GLOBAL OFFERING",
        "publish_time": "2018-09-07",
        "detail_url": "https://example.com/doc.pdf",
        "pdf_url": "https://example.com/doc.pdf",
        "raw_id": "198419",
        "company_name": "MEITUAN-W",
    }

    db.insert_filing(row)
    db.insert_filing({**row, "company_name": "MEITUAN"})

    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM filings").fetchall()

    assert len(rows) == 1
    assert rows[0]["company_name"] == "MEITUAN"


def test_company_data_insert_replaces_same_interface(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    result = {
        "market": "H",
        "symbol": "00700",
        "data_type": "financial_statement",
        "interface": "stock_financial_hk_report_em",
        "source": "AKShare",
        "fetched_at": "t1",
        "columns": ["指标"],
        "rows": [{"指标": "收入"}],
    }

    db.insert_company_data(result)
    db.insert_company_data({**result, "fetched_at": "t2", "rows": [{"指标": "净利润"}]})

    with db.connection() as conn:
        rows = conn.execute("SELECT * FROM company_data").fetchall()

    assert len(rows) == 1
    assert rows[0]["fetched_at"] == "t2"


def test_replace_pages_replaces_page_and_fts_rows(tmp_path):
    db = SQLiteStore(tmp_path / "test.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    db.replace_pages(
        "doc1",
        [PdfPage(1, "old revenue", 11), PdfPage(2, "old profit", 10)],
    )

    count = db.replace_pages("doc1", [PdfPage(1, "new cash flow", 13)])

    assert count == 1
    assert db.count_document_pages("doc1") == 1
    assert db.search_pages("new cash flow", "doc1", 5)[0]["page_no"] == 1
    assert db.search_pages("old profit", "doc1", 5) == []


def test_concurrent_document_ingest_serializes_sqlite_writes(tmp_path):
    path = tmp_path / "test.sqlite"
    SQLiteStore(path)

    def ingest_document(index: int) -> int:
        db = SQLiteStore(path)
        document_id = f"doc{index}"
        db.upsert_document({"document_id": document_id, "title": f"Doc {index}"})
        pages = [
            PdfPage(page_no, f"document {index} revenue page {page_no}" * 20, 0)
            for page_no in range(1, 151)
        ]
        return db.replace_pages(document_id, pages)

    with ThreadPoolExecutor(max_workers=4) as executor:
        counts = list(executor.map(ingest_document, range(4)))

    assert counts == [150, 150, 150, 150]
    db = SQLiteStore(path)
    assert [db.count_document_pages(f"doc{index}") for index in range(4)] == [150] * 4


def test_schema_initializes_once_per_database_path(monkeypatch, tmp_path):
    path = tmp_path / "init-once.sqlite"
    calls = 0
    original = SQLiteStore.init_schema

    def counted(self):
        nonlocal calls
        calls += 1
        return original(self)

    monkeypatch.setattr(SQLiteStore, "init_schema", counted)

    SQLiteStore(path)
    SQLiteStore(path)

    assert calls == 1


def test_trigram_index_stays_in_sync_with_page_replacement(tmp_path):
    db = SQLiteStore(tmp_path / "trigram.sqlite")
    db.upsert_document({"document_id": "doc1", "title": "年度报告"})
    db.replace_pages("doc1", [PdfPage(1, "营业收入确认政策", 8)])

    assert db.search_pages("收入确认", "doc1", 5)[0]["page_no"] == 1

    db.replace_pages("doc1", [PdfPage(1, "现金流量信息", 6)])

    assert db.search_pages("收入确认", "doc1", 5) == []
    with db.connection() as conn:
        count = conn.execute(
            "SELECT count(*) FROM document_pages_trigram WHERE document_id='doc1'"
        ).fetchone()[0]
    assert count == 1


def test_document_consistency_checks_fts_and_trigram_indexes(tmp_path):
    db = SQLiteStore(tmp_path / "consistent.sqlite")
    db.upsert_document(
        {"document_id": "doc1", "title": "Doc 1", "sha256": "abc", "page_count": 1}
    )
    db.replace_pages("doc1", [PdfPage(1, "revenue", 7)])

    assert db.document_index_is_consistent("doc1", "abc", 1) is True
    with db.write_connection() as conn:
        conn.execute("DELETE FROM document_pages_fts WHERE document_id='doc1'")
    assert db.document_index_is_consistent("doc1", "abc", 1) is False

    db.replace_pages("doc1", [PdfPage(1, "revenue", 7)])
    with db.write_connection() as conn:
        conn.execute("DELETE FROM document_pages_trigram WHERE document_id='doc1'")
    assert db.document_index_is_consistent("doc1", "abc", 1) is False


def test_future_schema_version_is_not_downgraded(tmp_path):
    path = tmp_path / "future.sqlite"
    db = SQLiteStore(path)
    with db.write_connection() as conn:
        conn.execute("UPDATE schema_meta SET value='999' WHERE key='schema_version'")

    db.init_schema()

    with db.connection() as conn:
        version = conn.execute(
            "SELECT value FROM schema_meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert version == "999"


def test_store_degrades_when_trigram_table_is_unavailable(tmp_path, monkeypatch):
    path = tmp_path / "without-trigram.sqlite"
    original = SQLiteStore._ensure_trigram_table
    monkeypatch.setattr(SQLiteStore, "_ensure_trigram_table", lambda self, conn: False)
    db = SQLiteStore(path)
    monkeypatch.setattr(SQLiteStore, "_ensure_trigram_table", original)

    db.upsert_document(
        {"document_id": "doc1", "title": "Doc 1", "sha256": "abc", "page_count": 1}
    )
    db.replace_pages("doc1", [PdfPage(1, "营业收入确认", 6)])

    assert db.search_pages("收入确认", "doc1", 5)[0]["page_no"] == 1
    assert db.document_index_is_consistent("doc1", "abc", 1) is True


def test_store_operations_release_database_file_handle(tmp_path):
    path = tmp_path / "releasable.sqlite"
    db = SQLiteStore(path)
    db.upsert_document({"document_id": "doc1", "title": "Doc 1"})
    db.replace_pages("doc1", [PdfPage(1, "收入确认", 4)])
    assert db.search_pages("收入确认", "doc1", 5)

    path.unlink()

    assert not path.exists()


def test_document_table_structure_metadata_is_persisted(tmp_path):
    db = SQLiteStore(tmp_path / "tables.sqlite")
    db.replace_document_tables(
        "doc1",
        [
            {
                "page_no": 7,
                "table_index": 1,
                "table_path": "page_7_table_1.csv",
                "structure_path": "page_7_table_1.json",
                "quality_flags": ["header_inferred"],
            }
        ],
    )

    rows = db.get_document_tables("doc1", [7])

    assert rows[0]["structure_path"] == "page_7_table_1.json"
    assert rows[0]["quality_flags"] == ["header_inferred"]
