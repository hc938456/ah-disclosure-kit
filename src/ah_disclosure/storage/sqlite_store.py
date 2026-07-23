from __future__ import annotations

import json
import re
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from ah_disclosure.core.file_utils import normalized_path_key
from ah_disclosure.core.naming import infer_language, infer_report_year, normalize_document_type
from ah_disclosure.core.paths import get_index_path
from ah_disclosure.core.time_utils import now_iso


PHRASE_STOPWORDS = {"a", "an", "and", "for", "from", "in", "of", "or", "the", "to", "with"}
_SQLITE_WRITE_LOCK = threading.RLock()
_SCHEMA_INIT_LOCK = threading.Lock()
_INITIALIZED_DATABASES: set[str] = set()
SCHEMA_VERSION = 4


def _normalize_phrase(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _should_exact_phrase_filter(query: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+", str(query or "").casefold())
    if len(words) < 3:
        return False
    return any(word in PHRASE_STOPWORDS for word in words)


def _should_merge_cjk_substring(query: str) -> bool:
    """Supplement FTS for compact CJK terms that unicode61 may tokenize unevenly."""
    text = str(query or "").strip()
    compact = re.sub(r"\s+", "", text)
    return bool(compact) and not re.search(r"\s", text) and len(compact) <= 24 and bool(
        re.search(r"[\u3400-\u9fff]", compact)
    )


def _should_merge_relaxed_substring(query: str) -> bool:
    """Supplement long natural-language searches with partial-term recall.

    FTS5 treats an unquoted multi-term query as an implicit AND.  That is useful
    for precision, but a flexible LLM-authored query can have one good exact hit
    and still omit the more explanatory pages that contain only a subset of its
    terms.  Keep the exact hits and add bounded, coverage-ranked partial hits.
    """
    text = str(query or "").strip()
    parts = [part for part in re.split(r"\s+", text) if len(part) >= 2]
    return 4 <= len(parts) <= 24 and len(text) <= 400


def _substring_terms(query: str) -> list[str]:
    text = str(query or "").strip()
    if not text:
        return []
    parts = [part.strip() for part in re.split(r"\s+", text) if part.strip()]
    terms: list[str] = []
    for term in [text, *parts]:
        if term and term not in terms:
            terms.append(term)
    return terms


def _substring_snippet(text: str, terms: list[str], max_len: int = 800) -> str:
    body = str(text or "")
    if len(body) <= max_len:
        return body
    lowered = body.casefold()
    positions = [lowered.find(term.casefold()) for term in terms if term]
    positions = [pos for pos in positions if pos >= 0]
    start = max(0, min(positions) - 160) if positions else 0
    end = min(len(body), start + max_len)
    return body[start:end]


class SQLiteStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.path = Path(db_path) if db_path else get_index_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        database_key = normalized_path_key(self.path)
        with _SCHEMA_INIT_LOCK:
            if database_key not in _INITIALIZED_DATABASES or not self.path.exists():
                self.init_schema()
                _INITIALIZED_DATABASES.add(database_key)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a read connection and always release its file handle."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def write_connection(self) -> Iterator[sqlite3.Connection]:
        # FTS page replacement can hold a write transaction for several seconds.
        # Serialize writers within the process while retaining concurrent reads.
        with _SQLITE_WRITE_LOCK:
            conn = self.connect()
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def init_schema(self) -> None:
        with self.write_connection() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS schema_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS companies (
                    market TEXT,
                    symbol TEXT,
                    company_name TEXT,
                    exchange TEXT,
                    cninfo_org_id TEXT,
                    hkex_stock_id TEXT,
                    aliases_json TEXT,
                    updated_at TEXT,
                    PRIMARY KEY(market, symbol)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    market TEXT,
                    symbol TEXT,
                    company_name TEXT,
                    document_type TEXT,
                    report_year INTEGER,
                    title TEXT,
                    publish_time TEXT,
                    source TEXT,
                    detail_url TEXT,
                    pdf_url TEXT,
                    local_pdf_path TEXT,
                    meta_path TEXT,
                    pages_jsonl_path TEXT,
                    markdown_path TEXT,
                    full_text_path TEXT,
                    md5 TEXT,
                    sha256 TEXT,
                    page_count INTEGER,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS document_pages (
                    document_id TEXT,
                    page_no INTEGER,
                    text TEXT,
                    char_count INTEGER,
                    section_title TEXT,
                    ocr_used INTEGER,
                    quality_score REAL,
                    created_at TEXT,
                    PRIMARY KEY(document_id, page_no)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS document_pages_fts
                USING fts5(document_id, page_no UNINDEXED, text, tokenize='unicode61');
                CREATE TABLE IF NOT EXISTS filings (
                    market TEXT,
                    symbol TEXT,
                    company_name TEXT,
                    title TEXT,
                    publish_time TEXT,
                    document_type TEXT,
                    source TEXT,
                    detail_url TEXT,
                    pdf_url TEXT,
                    raw_id TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS filing_sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_key TEXT NOT NULL UNIQUE,
                    market TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    company_name TEXT,
                    document_type TEXT,
                    report_year INTEGER,
                    language TEXT,
                    title TEXT NOT NULL,
                    publish_time TEXT,
                    source TEXT NOT NULL,
                    raw_id TEXT,
                    detail_url TEXT,
                    pdf_url TEXT,
                    local_pdf_path TEXT,
                    document_id TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    record_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS source_queries (
                    query_signature TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_count INTEGER NOT NULL,
                    records_json TEXT NOT NULL,
                    error TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_filing_sources_lookup
                ON filing_sources(market, symbol, document_type, report_year, language);
                CREATE INDEX IF NOT EXISTS idx_filing_sources_document
                ON filing_sources(document_id);
                CREATE TABLE IF NOT EXISTS prospectuses (
                    market TEXT,
                    company_name TEXT,
                    symbol TEXT,
                    board TEXT,
                    stage TEXT,
                    document_type TEXT,
                    title TEXT,
                    publish_date TEXT,
                    status TEXT,
                    sponsor TEXT,
                    law_firm TEXT,
                    accounting_firm TEXT,
                    source TEXT,
                    source_url TEXT,
                    pdf_url TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS company_data (
                    market TEXT,
                    symbol TEXT,
                    data_type TEXT,
                    interface TEXT,
                    source TEXT,
                    fetched_at TEXT,
                    columns_json TEXT,
                    rows_json TEXT
                );
                CREATE TABLE IF NOT EXISTS document_tables (
                    document_id TEXT,
                    page_no INTEGER,
                    table_index INTEGER,
                    table_path TEXT,
                    structure_path TEXT,
                    quality_flags_json TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS download_log (
                    url TEXT,
                    path TEXT,
                    status TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS ingest_log (
                    document_id TEXT,
                    pdf_path TEXT,
                    status TEXT,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS llm_answer_cache (
                    query_hash TEXT,
                    prompt_version TEXT,
                    evidence_hash TEXT,
                    model_name TEXT,
                    created_at TEXT,
                    answer TEXT,
                    citations_json TEXT,
                    PRIMARY KEY(query_hash, prompt_version, evidence_hash, model_name)
                );
                """
            )
            trigram_available = self._ensure_trigram_table(conn)
            version_row = conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()
            try:
                previous_version = int(version_row["value"]) if version_row else 0
            except (TypeError, ValueError):
                previous_version = 0
            if previous_version < 3 and trigram_available:
                conn.execute("DELETE FROM document_pages_trigram")
                conn.execute(
                    "INSERT INTO document_pages_trigram(document_id,page_no,text) "
                    "SELECT document_id,page_no,text FROM document_pages"
                )
            table_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(document_tables)").fetchall()
            }
            if "structure_path" not in table_columns:
                conn.execute("ALTER TABLE document_tables ADD COLUMN structure_path TEXT")
            if "quality_flags_json" not in table_columns:
                conn.execute("ALTER TABLE document_tables ADD COLUMN quality_flags_json TEXT")
            if previous_version < SCHEMA_VERSION:
                conn.execute(
                    "INSERT INTO schema_meta(key,value) VALUES('schema_version',?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (str(SCHEMA_VERSION),),
                )

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        return bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name=? LIMIT 1",
                (table_name,),
            ).fetchone()
        )

    def _ensure_trigram_table(self, conn: sqlite3.Connection) -> bool:
        if self._table_exists(conn, "document_pages_trigram"):
            return True
        try:
            conn.execute(
                "CREATE VIRTUAL TABLE document_pages_trigram "
                "USING fts5(document_id UNINDEXED, page_no UNINDEXED, text, tokenize='trigram')"
            )
            return True
        except sqlite3.OperationalError:
            return False

    def upsert_document(self, row: dict[str, Any]) -> None:
        row = {**row, "created_at": row.get("created_at") or now_iso()}
        cols = list(row)
        placeholders = ",".join(f":{col}" for col in cols)
        updates = ",".join(f"{col}=excluded.{col}" for col in cols if col != "document_id")
        with self.write_connection() as conn:
            conn.execute(
                f"INSERT INTO documents ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(document_id) DO UPDATE SET {updates}",
                row,
            )

    def upsert_page(self, document_id: str, page_no: int, text: str, ocr_used: bool = False, quality_score: float | None = None, section_title: str | None = None) -> None:
        with self.write_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO document_pages "
                "(document_id,page_no,text,char_count,section_title,ocr_used,quality_score,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (document_id, page_no, text, len(text or ""), section_title, int(ocr_used), quality_score, now_iso()),
            )
            conn.execute("DELETE FROM document_pages_fts WHERE document_id=? AND page_no=?", (document_id, page_no))
            conn.execute("INSERT INTO document_pages_fts(document_id,page_no,text) VALUES (?,?,?)", (document_id, page_no, text or ""))
            if self._table_exists(conn, "document_pages_trigram"):
                conn.execute("DELETE FROM document_pages_trigram WHERE document_id=? AND page_no=?", (document_id, page_no))
                conn.execute("INSERT INTO document_pages_trigram(document_id,page_no,text) VALUES (?,?,?)", (document_id, page_no, text or ""))

    def replace_pages(self, document_id: str, pages: list[Any]) -> int:
        created_at = now_iso()
        page_rows: list[tuple[Any, ...]] = []
        search_rows: list[tuple[Any, ...]] = []
        for page in pages:
            if isinstance(page, dict):
                page_no = int(page.get("page_no") or 0)
                text = str(page.get("text") or "")
                ocr_used = bool(page.get("ocr_used"))
                quality_score = page.get("quality_score")
                section_title = page.get("section_title")
            else:
                page_no = int(getattr(page, "page_no", 0) or 0)
                text = str(getattr(page, "text", "") or "")
                ocr_used = bool(getattr(page, "ocr_used", False))
                quality_score = getattr(page, "quality_score", None)
                section_title = getattr(page, "section_title", None)
            if page_no <= 0:
                continue
            page_rows.append(
                (
                    document_id,
                    page_no,
                    text,
                    len(text),
                    section_title,
                    int(ocr_used),
                    quality_score,
                    created_at,
                )
            )
            search_rows.append((document_id, page_no, text))
        with self.write_connection() as conn:
            conn.execute("DELETE FROM document_pages WHERE document_id=?", (document_id,))
            conn.execute("DELETE FROM document_pages_fts WHERE document_id=?", (document_id,))
            trigram_available = self._table_exists(conn, "document_pages_trigram")
            if trigram_available:
                conn.execute("DELETE FROM document_pages_trigram WHERE document_id=?", (document_id,))
            conn.executemany(
                "INSERT OR REPLACE INTO document_pages "
                "(document_id,page_no,text,char_count,section_title,ocr_used,quality_score,created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                page_rows,
            )
            conn.executemany(
                "INSERT INTO document_pages_fts(document_id,page_no,text) VALUES (?,?,?)",
                search_rows,
            )
            if trigram_available:
                conn.executemany(
                    "INSERT INTO document_pages_trigram(document_id,page_no,text) VALUES (?,?,?)",
                    search_rows,
                )
            return len(page_rows)

    def replace_document_tables(self, document_id: str, table_results: list[dict[str, Any]]) -> int:
        with self.write_connection() as conn:
            conn.execute("DELETE FROM document_tables WHERE document_id=?", (document_id,))
            count = 0
            for table in table_results:
                if table.get("table_path"):
                    conn.execute(
                        """
                        INSERT INTO document_tables(
                            document_id, page_no, table_index, table_path,
                            structure_path, quality_flags_json, created_at
                        ) VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            document_id,
                            table.get("page_no"),
                            table.get("table_index"),
                            table.get("table_path"),
                            table.get("structure_path"),
                            json.dumps(table.get("quality_flags") or [], ensure_ascii=False),
                            now_iso(),
                        ),
                    )
                    count += 1
            return count

    def get_document_tables(
        self,
        document_id: str,
        page_numbers: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        params: list[Any] = [document_id]
        where = "document_id=?"
        if page_numbers:
            placeholders = ",".join("?" for _ in page_numbers)
            where += f" AND page_no IN ({placeholders})"
            params.extend(int(page_no) for page_no in page_numbers)
        with self.connection() as conn:
            rows = conn.execute(
                f"SELECT * FROM document_tables WHERE {where} ORDER BY page_no, table_index",
                params,
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["quality_flags"] = json.loads(item.pop("quality_flags_json") or "[]")
            except json.JSONDecodeError:
                item["quality_flags"] = ["invalid_quality_flags_json"]
            results.append(item)
        return results

    def insert_filing(self, row: dict[str, Any]) -> None:
        with self.write_connection() as conn:
            conn.execute(
                """
                DELETE FROM filings
                WHERE coalesce(market,'')=coalesce(?,'')
                  AND coalesce(symbol,'')=coalesce(?,'')
                  AND coalesce(title,'')=coalesce(?,'')
                  AND coalesce(publish_time,'')=coalesce(?,'')
                  AND coalesce(detail_url,'')=coalesce(?,'')
                  AND coalesce(pdf_url,'')=coalesce(?,'')
                  AND coalesce(raw_id,'')=coalesce(?,'')
                """,
                (
                    row.get("market"),
                    row.get("symbol"),
                    row.get("title"),
                    row.get("publish_time"),
                    row.get("detail_url"),
                    row.get("pdf_url"),
                    row.get("raw_id"),
                ),
            )
            conn.execute(
                "INSERT INTO filings "
                "(market,symbol,company_name,title,publish_time,document_type,source,detail_url,pdf_url,raw_id,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row.get("market"), row.get("symbol"), row.get("company_name"), row.get("title"), row.get("publish_time"),
                    row.get("document_type"), row.get("source"), row.get("detail_url"), row.get("pdf_url"), row.get("raw_id"), now_iso(),
                ),
            )

    @staticmethod
    def _filing_source_key(row: dict[str, Any]) -> str:
        source = str(row.get("source") or "unknown").strip().casefold()
        identity = row.get("pdf_url") or row.get("detail_url")
        if not identity:
            identity = "|".join(
                str(row.get(key) or "")
                for key in ("raw_id", "market", "symbol", "publish_time", "title")
            )
        return f"{source}|{str(identity).strip()}"

    def upsert_filing_sources(self, records: list[dict[str, Any]]) -> int:
        now = now_iso()
        count = 0
        with self.write_connection() as conn:
            for original in records:
                row = dict(original)
                market = str(row.get("market") or "").strip().upper()
                symbol = str(row.get("symbol") or "").strip()
                title = str(row.get("title") or "").strip()
                source = str(row.get("source") or "").strip()
                if not market or not symbol or not title or not source:
                    continue
                doc_type = normalize_document_type(row.get("document_type"), title)
                report_year = infer_report_year(title, row.get("publish_time"), row.get("report_year"))
                language = infer_language(title, row.get("language"))
                source_key = self._filing_source_key(row)
                conn.execute(
                    """
                    INSERT INTO filing_sources (
                        source_key,market,symbol,company_name,document_type,report_year,language,
                        title,publish_time,source,raw_id,detail_url,pdf_url,local_pdf_path,
                        document_id,status,first_seen_at,last_seen_at,record_json
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(source_key) DO UPDATE SET
                        market=excluded.market,
                        symbol=excluded.symbol,
                        company_name=excluded.company_name,
                        document_type=excluded.document_type,
                        report_year=excluded.report_year,
                        language=excluded.language,
                        title=excluded.title,
                        publish_time=excluded.publish_time,
                        raw_id=excluded.raw_id,
                        detail_url=excluded.detail_url,
                        pdf_url=excluded.pdf_url,
                        last_seen_at=excluded.last_seen_at,
                        record_json=excluded.record_json
                    """,
                    (
                        source_key,
                        market,
                        symbol,
                        row.get("company_name"),
                        doc_type,
                        int(report_year) if str(report_year).isdigit() else None,
                        language,
                        title,
                        row.get("publish_time"),
                        source,
                        row.get("raw_id"),
                        row.get("detail_url"),
                        row.get("pdf_url"),
                        row.get("local_pdf_path"),
                        row.get("document_id"),
                        row.get("status") or "active",
                        now,
                        now,
                        json.dumps(row, ensure_ascii=False, default=str),
                    ),
                )
                count += 1
        return count

    def put_source_query(
        self,
        query_signature: str,
        records: list[dict[str, Any]],
        source: str,
        ttl_seconds: int,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        self.upsert_filing_sources(records)
        fetched = datetime.now(timezone.utc).astimezone()
        expires = fetched + timedelta(seconds=max(int(ttl_seconds), 0))
        with self.write_connection() as conn:
            conn.execute(
                """
                INSERT INTO source_queries (
                    query_signature,source,fetched_at,expires_at,status,result_count,records_json,error
                ) VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(query_signature) DO UPDATE SET
                    source=excluded.source,
                    fetched_at=excluded.fetched_at,
                    expires_at=excluded.expires_at,
                    status=excluded.status,
                    result_count=excluded.result_count,
                    records_json=excluded.records_json,
                    error=excluded.error
                """,
                (
                    query_signature,
                    source,
                    fetched.isoformat(timespec="seconds"),
                    expires.isoformat(timespec="seconds"),
                    status,
                    len(records),
                    json.dumps(records, ensure_ascii=False, default=str),
                    error,
                ),
            )

    def get_source_query(
        self,
        query_signature: str,
        max_age_seconds: int | None = None,
        include_stale: bool = False,
    ) -> dict[str, Any] | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM source_queries WHERE query_signature=?",
                (query_signature,),
            ).fetchone()
        if not row:
            return None
        item = dict(row)
        now = datetime.now(timezone.utc).astimezone()
        fetched = datetime.fromisoformat(item["fetched_at"])
        expires = datetime.fromisoformat(item["expires_at"])
        stale = now > expires
        if max_age_seconds is not None:
            stale = stale or (now - fetched).total_seconds() > max_age_seconds
        if stale and not include_stale:
            return None
        records = json.loads(item["records_json"])
        pdf_urls = [str(record.get("pdf_url")) for record in records if record.get("pdf_url")]
        local_by_url: dict[str, dict[str, Any]] = {}
        if pdf_urls:
            placeholders = ",".join("?" for _ in pdf_urls)
            with self.connection() as conn:
                linked_rows = conn.execute(
                    f"SELECT pdf_url,local_pdf_path,document_id FROM filing_sources "
                    f"WHERE pdf_url IN ({placeholders})",
                    pdf_urls,
                ).fetchall()
            local_by_url = {str(linked["pdf_url"]): dict(linked) for linked in linked_rows}
        enriched_records = []
        for original in records:
            record = dict(original)
            linked = local_by_url.get(str(record.get("pdf_url") or ""))
            if linked and linked.get("local_pdf_path"):
                record["local_pdf_path"] = linked["local_pdf_path"]
            if linked and linked.get("document_id"):
                record["document_id"] = linked["document_id"]
            enriched_records.append(record)
        return {
            **item,
            "records": enriched_records,
            "stale": stale,
            "cache_status": "stale" if stale else "hit",
        }

    def search_filing_sources(
        self,
        market: str,
        symbol: str,
        document_type: str | None = None,
        report_year: int | None = None,
        language: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses = ["upper(market)=upper(?)", "symbol=?", "status='active'"]
        params: list[Any] = [market, symbol]
        if document_type:
            clauses.append("document_type=?")
            params.append(normalize_document_type(document_type))
        if report_year is not None:
            clauses.append("report_year=?")
            params.append(report_year)
        if language:
            clauses.append("language=?")
            params.append(infer_language(document_language=language))
        params.append(limit)
        sql = (
            "SELECT record_json,local_pdf_path,document_id FROM filing_sources WHERE "
            + " AND ".join(clauses)
            + " ORDER BY publish_time DESC LIMIT ?"
        )
        with self.connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        result = []
        for row in rows:
            record = json.loads(row["record_json"])
            if row["local_pdf_path"]:
                record["local_pdf_path"] = row["local_pdf_path"]
            if row["document_id"]:
                record["document_id"] = row["document_id"]
            result.append(record)
        return result

    def link_filing_source_to_local_file(
        self,
        pdf_url: str,
        local_pdf_path: str,
        document_id: str | None = None,
    ) -> None:
        with self.write_connection() as conn:
            conn.execute(
                "UPDATE filing_sources SET local_pdf_path=?, document_id=? WHERE pdf_url=?",
                (local_pdf_path, document_id, pdf_url),
            )

    def insert_company_data(self, result: dict[str, Any]) -> None:
        with self.write_connection() as conn:
            conn.execute(
                """
                DELETE FROM company_data
                WHERE coalesce(market,'')=coalesce(?,'')
                  AND coalesce(symbol,'')=coalesce(?,'')
                  AND coalesce(data_type,'')=coalesce(?,'')
                  AND coalesce(interface,'')=coalesce(?,'')
                """,
                (result.get("market"), result.get("symbol"), result.get("data_type"), result.get("interface")),
            )
            conn.execute(
                "INSERT INTO company_data "
                "(market,symbol,data_type,interface,source,fetched_at,columns_json,rows_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    result.get("market"), result.get("symbol"), result.get("data_type"), result.get("interface"), result.get("source"),
                    result.get("fetched_at"), json.dumps(result.get("columns", []), ensure_ascii=False),
                    json.dumps(result.get("rows", []), ensure_ascii=False, default=str),
                ),
            )

    def log_download(self, url: str, path: str, status: str, created_at: str | None = None) -> None:
        with self.write_connection() as conn:
            conn.execute(
                "INSERT INTO download_log (url,path,status,created_at) VALUES (?,?,?,?)",
                (url, path, status, created_at or now_iso()),
            )

    def get_latest_download_for_path(self, path: str) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM download_log WHERE path=? ORDER BY created_at DESC LIMIT 1",
                (path,),
            ).fetchone()
        return dict(row) if row else {}

    def log_ingest(self, document_id: str, pdf_path: str, status: str) -> None:
        with self.write_connection() as conn:
            conn.execute(
                "INSERT INTO ingest_log (document_id,pdf_path,status,created_at) VALUES (?,?,?,?)",
                (document_id, pdf_path, status, now_iso()),
            )

    def list_documents(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connection() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]

    def list_documents_by_company(self, market: str, symbol: str) -> list[dict[str, Any]]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE upper(market)=upper(?) AND symbol=? ORDER BY created_at DESC",
                (market, symbol),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_document_meta(self, document_id: str) -> dict[str, Any]:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()
        return dict(row) if row else {}

    def count_document_pages(self, document_id: str) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT count(*) AS page_count FROM document_pages WHERE document_id=?",
                (document_id,),
            ).fetchone()
        return int(row["page_count"] if row else 0)

    def document_index_is_consistent(
        self,
        document_id: str,
        sha256: str,
        page_count: int,
    ) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT d.sha256,
                       d.page_count,
                       (SELECT count(*) FROM document_pages p
                        WHERE p.document_id=d.document_id) AS indexed_pages,
                       (SELECT count(*) FROM document_pages_fts f
                        WHERE f.document_id=d.document_id) AS fts_pages
                FROM documents d
                WHERE d.document_id=?
                """,
                (document_id,),
            ).fetchone()
            trigram_pages = None
            if row and self._table_exists(conn, "document_pages_trigram"):
                trigram_pages = conn.execute(
                    "SELECT count(*) FROM document_pages_trigram WHERE document_id=?",
                    (document_id,),
                ).fetchone()[0]
        return bool(
            row
            and str(row["sha256"] or "") == str(sha256 or "")
            and int(row["page_count"] or 0) == int(page_count)
            and int(row["indexed_pages"] or 0) == int(page_count)
            and int(row["fts_pages"] or 0) == int(page_count)
            and (trigram_pages is None or int(trigram_pages) == int(page_count))
        )

    def delete_document_records(self, document_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        meta = self.get_document_meta(document_id)
        with self.write_connection() as conn:
            cur = conn.execute(
                "UPDATE filing_sources SET local_pdf_path=NULL, document_id=NULL WHERE document_id=?",
                (document_id,),
            )
            counts["filing_sources_unlinked"] = max(cur.rowcount, 0)
            tables = ["document_pages_fts", "document_pages", "document_tables", "documents", "ingest_log"]
            if self._table_exists(conn, "document_pages_trigram"):
                tables.insert(1, "document_pages_trigram")
            for table in tables:
                cur = conn.execute(f"DELETE FROM {table} WHERE document_id=?", (document_id,))
                counts[table] = max(cur.rowcount, 0)
            local_pdf_path = meta.get("local_pdf_path")
            pdf_url = meta.get("pdf_url")
            if local_pdf_path or pdf_url:
                cur = conn.execute(
                    "DELETE FROM download_log WHERE path=? OR url=?",
                    (local_pdf_path, pdf_url),
                )
                counts["download_log"] = max(cur.rowcount, 0)
        return counts

    def delete_company_records(self, market: str, symbol: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        with self.write_connection() as conn:
            for table in ["company_data", "filings", "filing_sources"]:
                cur = conn.execute(
                    f"DELETE FROM {table} WHERE upper(market)=upper(?) AND symbol=?",
                    (market, symbol),
                )
                counts[table] = max(cur.rowcount, 0)
            cur = conn.execute(
                "DELETE FROM prospectuses WHERE upper(market)=upper(?) AND symbol=?",
                (market, symbol),
            )
            counts["prospectuses"] = max(cur.rowcount, 0)
            signature_pattern = f'%"market":"{market.upper()}"%"symbol":"{symbol}"%'
            cur = conn.execute(
                "DELETE FROM source_queries WHERE query_signature LIKE ?",
                (signature_pattern,),
            )
            counts["source_queries"] = max(cur.rowcount, 0)
        return counts

    def search_pages(self, query: str, document_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
        with self.connection() as conn:
            try:
                if document_id:
                    rows = conn.execute(
                        "SELECT document_id,page_no,snippet(document_pages_fts,2,'[',']','...',16) AS snippet "
                        "FROM document_pages_fts WHERE document_pages_fts MATCH ? AND document_id=? LIMIT ?",
                        (query, document_id, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT document_id,page_no,snippet(document_pages_fts,2,'[',']','...',16) AS snippet "
                        "FROM document_pages_fts WHERE document_pages_fts MATCH ? LIMIT ?",
                        (query, limit),
                    ).fetchall()
                result = [dict(row) for row in rows]
                if not result:
                    return self._search_pages_substring(conn, query, document_id, limit)
                if _should_merge_cjk_substring(query):
                    # FTS5 unicode61 can return some, but not all, pages for the same
                    # Chinese name/phrase.  Substring search is authoritative for a
                    # compact exact CJK term, so put those hits first and retain any
                    # additional FTS-only pages within the caller's budget.
                    substring_rows = self._search_pages_substring(
                        conn,
                        query,
                        document_id,
                        max(limit, 50),
                    )
                    merged: dict[tuple[str, int], dict[str, Any]] = {}
                    for row in [*substring_rows, *result]:
                        key = (str(row.get("document_id") or ""), int(row.get("page_no") or 0))
                        if key not in merged:
                            merged[key] = row
                    result = list(merged.values())[:limit]
                elif _should_merge_relaxed_substring(query):
                    relaxed_rows = self._search_pages_substring(
                        conn,
                        query,
                        document_id,
                        max(limit, 24),
                        relax_components=True,
                    )
                    merged = {}
                    for row in [*result, *relaxed_rows]:
                        key = (str(row.get("document_id") or ""), int(row.get("page_no") or 0))
                        if key not in merged:
                            merged[key] = row
                    result = list(merged.values())[:limit]
                if _should_exact_phrase_filter(query):
                    phrase = _normalize_phrase(query)
                    filtered = []
                    for row in result:
                        page = conn.execute(
                            "SELECT text FROM document_pages WHERE document_id=? AND page_no=?",
                            (row.get("document_id"), row.get("page_no")),
                        ).fetchone()
                        if page and phrase in _normalize_phrase(page["text"]):
                            filtered.append(row)
                    if filtered:
                        return filtered
                    return result
                return result
            except sqlite3.OperationalError:
                return self._search_pages_substring(conn, query, document_id, limit)

    def _search_pages_substring(
        self,
        conn: sqlite3.Connection,
        query: str,
        document_id: str | None = None,
        limit: int = 8,
        *,
        relax_components: bool = False,
    ) -> list[dict[str, Any]]:
        terms = _substring_terms(query)
        if not terms:
            return []
        normalized_terms = [
            re.sub(r"\s+", "", term).casefold()
            for term in terms
            if term
        ]

        def fetch_rows(search_terms: list[str]) -> list[sqlite3.Row]:
            trigram_terms = [term for term in search_terms if len(term) >= 3]
            if trigram_terms:
                match_query = " OR ".join(
                    f'"{term.replace(chr(34), chr(34) * 2)}"'
                    for term in trigram_terms
                )
                candidate_limit = max(100, min(1000, limit * 25))
                try:
                    if document_id:
                        rows = conn.execute(
                            "SELECT document_id,page_no,text FROM document_pages_trigram "
                            "WHERE document_pages_trigram MATCH ? AND document_id=? "
                            "ORDER BY rank LIMIT ?",
                            (match_query, document_id, candidate_limit),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT document_id,page_no,text FROM document_pages_trigram "
                            "WHERE document_pages_trigram MATCH ? ORDER BY rank LIMIT ?",
                            (match_query, candidate_limit),
                        ).fetchall()
                    if rows:
                        return rows
                except sqlite3.OperationalError:
                    # Older/custom SQLite builds may not provide the trigram tokenizer.
                    pass
            predicates = " OR ".join("text LIKE ?" for _ in search_terms)
            patterns = [f"%{term}%" for term in search_terms]
            if document_id:
                return conn.execute(
                    "SELECT document_id,page_no,text FROM document_pages "
                    f"WHERE document_id=? AND ({predicates}) ORDER BY page_no",
                    (document_id, *patterns),
                ).fetchall()
            return conn.execute(
                "SELECT document_id,page_no,text FROM document_pages "
                f"WHERE {predicates} ORDER BY document_id,page_no",
                patterns,
            ).fetchall()

        rows = fetch_rows([terms[0]])
        if (not rows or relax_components) and len(terms) > 1:
            component_terms = [term for term in terms[1:17] if len(term) >= 2]
            if component_terms:
                component_rows = fetch_rows(component_terms)
                if rows:
                    merged_rows = {
                        (str(row["document_id"]), int(row["page_no"])): row for row in rows
                    }
                    for row in component_rows:
                        merged_rows.setdefault(
                            (str(row["document_id"]), int(row["page_no"])), row
                        )
                    rows = list(merged_rows.values())
                else:
                    rows = component_rows
        results: list[dict[str, Any]] = []
        for row in rows:
            text = str(row["text"] or "")
            normalized_text = re.sub(r"\s+", "", text).casefold()
            counts = [normalized_text.count(term) for term in normalized_terms]
            coverage = sum(1 for count in counts if count > 0)
            score = coverage * 100 + sum(min(count, 20) for count in counts)
            results.append(
                {
                    "document_id": row["document_id"],
                    "page_no": row["page_no"],
                    "snippet": _substring_snippet(text, terms),
                    "score": score,
                }
            )
        results.sort(key=lambda item: (-int(item.get("score") or 0), int(item.get("page_no") or 0)))
        return results[:limit]

    def get_pages(self, document_id: str, pages: list[int] | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self.connection() as conn:
            if pages:
                qs = ",".join("?" for _ in pages)
                rows = conn.execute(
                    f"SELECT * FROM document_pages WHERE document_id=? AND page_no IN ({qs}) ORDER BY page_no",
                    (document_id, *pages),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM document_pages WHERE document_id=? ORDER BY page_no LIMIT ?",
                    (document_id, limit),
                ).fetchall()
            return [dict(row) for row in rows]
