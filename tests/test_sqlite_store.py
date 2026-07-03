from ah_disclosure.storage.sqlite_store import SQLiteStore


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

    with db.connect() as conn:
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

    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM company_data").fetchall()

    assert len(rows) == 1
    assert rows[0]["fetched_at"] == "t2"
