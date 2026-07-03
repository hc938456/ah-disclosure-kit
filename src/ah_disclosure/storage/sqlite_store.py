from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from ah_disclosure.core.paths import get_index_path
from ah_disclosure.core.time_utils import now_iso


PHRASE_STOPWORDS = {"a", "an", "and", "for", "from", "in", "of", "or", "the", "to", "with"}


def _normalize_phrase(text: str) -> str:
    return " ".join(str(text or "").casefold().split())


def _should_exact_phrase_filter(query: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+", str(query or "").casefold())
    if len(words) < 3:
        return False
    return any(word in PHRASE_STOPWORDS for word in words)


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
        self.init_schema()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
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

    def upsert_document(self, row: dict[str, Any]) -> None:
        row = {**row, "created_at": row.get("created_at") or now_iso()}
        cols = list(row)
        placeholders = ",".join(f":{col}" for col in cols)
        updates = ",".join(f"{col}=excluded.{col}" for col in cols if col != "document_id")
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO documents ({','.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(document_id) DO UPDATE SET {updates}",
                row,
            )

    def upsert_page(self, document_id: str, page_no: int, text: str, ocr_used: bool = False, quality_score: float | None = None, section_title: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO document_pages VALUES (?,?,?,?,?,?,?,?)",
                (document_id, page_no, text, len(text or ""), section_title, int(ocr_used), quality_score, now_iso()),
            )
            conn.execute("DELETE FROM document_pages_fts WHERE document_id=? AND page_no=?", (document_id, page_no))
            conn.execute("INSERT INTO document_pages_fts(document_id,page_no,text) VALUES (?,?,?)", (document_id, page_no, text or ""))

    def replace_pages(self, document_id: str, pages: list[Any]) -> int:
        with self.connect() as conn:
            conn.execute("DELETE FROM document_pages WHERE document_id=?", (document_id,))
            conn.execute("DELETE FROM document_pages_fts WHERE document_id=?", (document_id,))
            created_at = now_iso()
            count = 0
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
                conn.execute(
                    "INSERT OR REPLACE INTO document_pages VALUES (?,?,?,?,?,?,?,?)",
                    (document_id, page_no, text, len(text), section_title, int(ocr_used), quality_score, created_at),
                )
                conn.execute(
                    "INSERT INTO document_pages_fts(document_id,page_no,text) VALUES (?,?,?)",
                    (document_id, page_no, text),
                )
                count += 1
            return count

    def replace_document_tables(self, document_id: str, table_results: list[dict[str, Any]]) -> int:
        with self.connect() as conn:
            conn.execute("DELETE FROM document_tables WHERE document_id=?", (document_id,))
            count = 0
            for table in table_results:
                if table.get("table_path"):
                    conn.execute(
                        "INSERT INTO document_tables VALUES (?,?,?,?,?)",
                        (document_id, table.get("page_no"), table.get("table_index"), table.get("table_path"), now_iso()),
                    )
                    count += 1
            return count

    def insert_filing(self, row: dict[str, Any]) -> None:
        with self.connect() as conn:
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
                "INSERT INTO filings VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    row.get("market"), row.get("symbol"), row.get("company_name"), row.get("title"), row.get("publish_time"),
                    row.get("document_type"), row.get("source"), row.get("detail_url"), row.get("pdf_url"), row.get("raw_id"), now_iso(),
                ),
            )

    def insert_company_data(self, result: dict[str, Any]) -> None:
        with self.connect() as conn:
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
                "INSERT INTO company_data VALUES (?,?,?,?,?,?,?,?)",
                (
                    result.get("market"), result.get("symbol"), result.get("data_type"), result.get("interface"), result.get("source"),
                    result.get("fetched_at"), json.dumps(result.get("columns", []), ensure_ascii=False),
                    json.dumps(result.get("rows", []), ensure_ascii=False, default=str),
                ),
            )

    def log_download(self, url: str, path: str, status: str, created_at: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO download_log VALUES (?,?,?,?)", (url, path, status, created_at or now_iso()))

    def log_ingest(self, document_id: str, pdf_path: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute("INSERT INTO ingest_log VALUES (?,?,?,?)", (document_id, pdf_path, status, now_iso()))

    def list_documents(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()]

    def list_documents_by_company(self, market: str, symbol: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE upper(market)=upper(?) AND symbol=? ORDER BY created_at DESC",
                (market, symbol),
            ).fetchall()
            return [dict(row) for row in rows]

    def get_document_meta(self, document_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM documents WHERE document_id=?", (document_id,)).fetchone()
            return dict(row) if row else {}

    def delete_document_records(self, document_id: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        meta = self.get_document_meta(document_id)
        with self.connect() as conn:
            for table in ["document_pages_fts", "document_pages", "document_tables", "documents", "ingest_log"]:
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
        with self.connect() as conn:
            for table in ["company_data", "filings"]:
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
        return counts

    def search_pages(self, query: str, document_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
        with self.connect() as conn:
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

    def _search_pages_substring(self, conn: sqlite3.Connection, query: str, document_id: str | None = None, limit: int = 8) -> list[dict[str, Any]]:
        terms = _substring_terms(query)
        if not terms:
            return []
        primary = terms[0]
        pattern = f"%{primary}%"
        if document_id:
            rows = conn.execute(
                "SELECT document_id,page_no,text FROM document_pages WHERE document_id=? AND text LIKE ? ORDER BY page_no",
                (document_id, pattern),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT document_id,page_no,text FROM document_pages WHERE text LIKE ? ORDER BY document_id,page_no",
                (pattern,),
            ).fetchall()
        results: list[dict[str, Any]] = []
        for row in rows:
            text = str(row["text"] or "")
            lowered = text.casefold()
            score = sum(lowered.count(term.casefold()) for term in terms if term)
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
        with self.connect() as conn:
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
