from __future__ import annotations

from ah_disclosure.models import EvidenceItem, EvidencePacket
from ah_disclosure.storage.sqlite_store import SQLiteStore
from ah_disclosure.core.time_utils import now_iso
from ah_disclosure.services.cleanup_service import cleanup_company, cleanup_document, reconcile_local_documents


ACCOUNTING_POLICY_BASE_QUERIES: list[tuple[str, str]] = [
    ("revenue recognition", "accounting_policy"),
    ("收入确认", "accounting_policy"),
    ("summary of material accounting policies", "policy_section"),
    ("significant accounting policies", "policy_section"),
    ("critical accounting estimates", "critical_estimate"),
    ("management discussion and analysis", "mda"),
    ("expenses by nature", "expense_note"),
    ("cost of revenues", "cost_of_revenues"),
    ("selling and marketing expenses", "mda"),
    ("segment information", "segment_note"),
]

INCENTIVE_ACCOUNTING_QUERIES: list[tuple[str, str]] = [
    ("incentives", "incentive"),
    ("user incentives", "incentive"),
    ("transacting user incentives", "accounting_policy"),
    ("transacting users incentives", "accounting_policy"),
    ("not in exchange for a distinct good or service", "accounting_policy"),
    ("deducted from revenues", "net_revenue"),
    ("courier incentives", "cost_of_revenues"),
    ("promotion advertising user incentives", "expense_note"),
    ("subsidy", "incentive"),
    ("subsidies", "incentive"),
    ("coupons", "incentive"),
    ("vouchers", "incentive"),
    ("补贴", "incentive"),
    ("优惠券", "incentive"),
    ("骑手", "cost_of_revenues"),
]

FINANCIAL_ANALYSIS_QUERIES: list[tuple[str, str]] = [
    ("management discussion and analysis", "mda"),
    ("revenues by segment and type", "revenue_breakdown"),
    ("revenues by type", "revenue_breakdown"),
    ("Core Local Commerce", "segment_note"),
    ("New Initiatives", "segment_note"),
    ("Delivery services", "revenue_breakdown"),
    ("Commission", "revenue_breakdown"),
    ("Online marketing services", "revenue_breakdown"),
    ("Other services and sales", "revenue_breakdown"),
    ("cost of revenues", "cost_of_revenues"),
    ("selling and marketing expenses", "mda"),
    ("operating loss from the Core Local Commerce", "segment_note"),
    ("operating loss from the Core Local Commerce segment was", "segment_note"),
    ("operating profit from the Core Local Commerce", "segment_note"),
    ("operating loss and operating margin in 2025", "segment_note"),
    ("operating margin", "segment_note"),
    ("Number of On-demand Delivery transactions", "kpi_driver"),
    ("GTV", "kpi_driver"),
    ("expenses by nature", "expense_note"),
    ("promotion advertising user incentives", "expense_note"),
    ("courier incentives", "cost_of_revenues"),
    ("deducted from revenues", "net_revenue"),
]

ACCOUNTING_QUERY_HINTS = [
    "会计",
    "确认",
    "政策",
    "处理",
    "列报",
    "披露",
    "附注",
    "记账",
    "accounting",
    "recognition",
    "recognize",
    "recognised",
    "recognized",
    "policy",
    "policies",
    "treatment",
    "presentation",
    "disclosure",
]

INCENTIVE_QUERY_HINTS = [
    "补贴",
    "优惠券",
    "代金券",
    "消费券",
    "激励",
    "外卖",
    "骑手",
    "subsid",
    "incentive",
    "coupon",
    "voucher",
    "courier",
]

FINANCIAL_ANALYSIS_HINTS = [
    "fp&a",
    "fpa",
    "预算",
    "预测",
    "滚动",
    "驱动",
    "分析师",
    "经营",
    "利润",
    "盈利",
    "亏损",
    "margin",
    "driver",
    "forecast",
    "budget",
    "p&l",
]

EVIDENCE_TYPE_PRIORITY = {
    "accounting_policy": 100,
    "net_revenue": 95,
    "revenue_breakdown": 90,
    "expense_note": 85,
    "cost_of_revenues": 85,
    "mda": 80,
    "kpi_driver": 75,
    "segment_note": 65,
    "critical_estimate": 55,
    "incentive": 50,
    "user_query": 45,
    "policy_section": 30,
    "adjacent": 20,
}

EVIDENCE_TYPE_ORDER = [
    "accounting_policy",
    "net_revenue",
    "revenue_breakdown",
    "cost_of_revenues",
    "expense_note",
    "mda",
    "kpi_driver",
    "segment_note",
    "critical_estimate",
    "incentive",
    "user_query",
    "policy_section",
    "adjacent",
]

EVIDENCE_TYPE_QUOTAS = {
    "accounting_policy": 4,
    "net_revenue": 2,
    "revenue_breakdown": 3,
    "cost_of_revenues": 2,
    "expense_note": 2,
    "mda": 2,
    "kpi_driver": 2,
    "segment_note": 1,
    "critical_estimate": 1,
    "incentive": 2,
    "user_query": 1,
    "policy_section": 1,
    "adjacent": 0,
}


def _dedupe_queries(queries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for query, evidence_type in queries:
        clean = " ".join(str(query or "").split())
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append((clean, evidence_type))
    return result


def _should_use_accounting_strategy(query: str, strategy: str) -> bool:
    normalized = (strategy or "basic").strip().lower()
    if normalized in {"accounting_policy", "accounting", "filing_analysis"}:
        return True
    if normalized != "auto":
        return False
    query_lower = query.casefold()
    return any(hint.casefold() in query_lower for hint in ACCOUNTING_QUERY_HINTS)


def _should_use_financial_strategy(query: str, strategy: str) -> bool:
    normalized = (strategy or "basic").strip().lower()
    if normalized in {"financial_analysis", "financial", "fpna", "fpa", "fp&a"}:
        return True
    if normalized != "auto":
        return False
    query_lower = query.casefold()
    return any(hint.casefold() in query_lower for hint in FINANCIAL_ANALYSIS_HINTS)


def _accounting_policy_queries(query: str) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = [(query, "user_query")]
    queries.extend(ACCOUNTING_POLICY_BASE_QUERIES)
    query_lower = query.casefold()
    if any(hint.casefold() in query_lower for hint in INCENTIVE_QUERY_HINTS):
        queries.extend(INCENTIVE_ACCOUNTING_QUERIES)
    return _dedupe_queries(queries)


def _financial_analysis_queries(query: str) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = [(query, "user_query")]
    queries.extend(FINANCIAL_ANALYSIS_QUERIES)
    query_lower = query.casefold()
    if any(hint.casefold() in query_lower for hint in INCENTIVE_QUERY_HINTS):
        queries.extend(INCENTIVE_ACCOUNTING_QUERIES)
    return _dedupe_queries(queries)


def _best_evidence_type(evidence_types: set[str]) -> str:
    if not evidence_types:
        return "page"
    return max(evidence_types, key=lambda item: EVIDENCE_TYPE_PRIORITY.get(item, 0))


def _select_diverse_hits(hits: list[dict], max_pages: int) -> list[dict]:
    def sort_key(item: dict) -> tuple[int, int, int]:
        evidence_priority = max((EVIDENCE_TYPE_PRIORITY.get(et, 0) for et in item["evidence_types"]), default=0)
        direct_hit = 0 if item.get("is_adjacent") else 1
        return (evidence_priority, direct_hit, len(item["matched_queries"]))

    def type_sort_key(item: dict, evidence_type: str) -> tuple[int, int, int, int]:
        matched = {str(query).casefold() for query in item["matched_queries"]}
        snippets = " ".join(str(snippet) for snippet in item.get("snippets", [])).casefold()
        type_bonus = 0
        if evidence_type == "accounting_policy":
            if "transacting user incentives" in matched:
                type_bonus += 60
            if "transacting users incentives" in matched:
                type_bonus += 60
            if "not in exchange for a distinct good or service" in matched:
                type_bonus += 80
            if "revenue recognition" in matched or "收入确认" in matched:
                type_bonus += 40
        elif evidence_type == "revenue_breakdown":
            if "revenues by segment and type" in matched or "revenues by type" in matched:
                type_bonus += 80
            if "delivery services" in matched:
                type_bonus += 50
            if "core local commerce" in matched:
                type_bonus += 30
        elif evidence_type == "expense_note":
            if "expenses by nature" in matched:
                type_bonus += 80
            if "promotion advertising user incentives" in matched:
                type_bonus += 40
        elif evidence_type == "cost_of_revenues":
            if "courier incentives" in matched:
                type_bonus += 60
            if "cost of revenues" in matched:
                type_bonus += 30
        elif evidence_type == "net_revenue":
            if "deducted from revenues" in matched:
                type_bonus += 60
        elif evidence_type == "mda":
            if "management discussion and analysis" in matched:
                type_bonus += 40
        elif evidence_type == "kpi_driver":
            if "number of on-demand delivery transactions" in matched:
                type_bonus += 60
            if "gtv" in matched:
                type_bonus += 50
        elif evidence_type == "segment_note":
            if "year ended" in snippets or " in 2025" in snippets:
                type_bonus += 120
            if "fourth quarter" in snippets:
                type_bonus -= 40
            if "operating loss and operating margin in 2025" in matched:
                type_bonus += 90
            if "operating loss from the core local commerce segment was" in matched:
                type_bonus += 80
            if "operating loss from the core local commerce" in matched:
                type_bonus += 70
            if "operating profit from the core local commerce" in matched:
                type_bonus += 60
            if "core local commerce" in matched:
                type_bonus += 40
        direct_hit = 0 if item.get("is_adjacent") else 1
        return (type_bonus, direct_hit, len(item["matched_queries"]), sort_key(item)[0])

    ordered_hits = sorted(hits, key=sort_key, reverse=True)
    selected: list[dict] = []
    selected_keys: set[tuple[str | None, int]] = set()

    def add_hit(hit: dict) -> bool:
        key = (hit.get("document_id"), int(hit["page_no"]))
        if key in selected_keys:
            return False
        selected.append(hit)
        selected_keys.add(key)
        return len(selected) >= max_pages

    for evidence_type in EVIDENCE_TYPE_ORDER:
        quota = EVIDENCE_TYPE_QUOTAS.get(evidence_type, 1)
        if quota <= 0:
            continue
        used = 0
        type_hits = [hit for hit in ordered_hits if evidence_type in hit["evidence_types"]]
        type_hits.sort(key=lambda hit: type_sort_key(hit, evidence_type), reverse=True)
        for hit in type_hits:
            if add_hit(hit):
                return selected
            used += 1
            if used >= quota:
                break

    for hit in ordered_hits:
        if add_hit(hit):
            break
    return selected


def _excerpt_around_terms(text: str, terms: list[str], max_len: int) -> str:
    compact = str(text or "")
    if len(compact) <= max_len:
        return compact
    lowered = compact.casefold()
    hit_index = -1
    for term in terms:
        clean = str(term or "").strip()
        if not clean:
            continue
        idx = lowered.find(clean.casefold())
        if idx >= 0:
            hit_index = idx
            break
    if hit_index < 0:
        return compact[:max_len]
    start = max(0, hit_index - max_len // 3)
    end = min(len(compact), start + max_len)
    start = max(0, end - max_len)
    prefix = "..." if start else ""
    suffix = "..." if end < len(compact) else ""
    return f"{prefix}{compact[start:end]}{suffix}"


def _useful_adjacent_text(text: str, page_no: int) -> bool:
    compact = " ".join(str(text or "").split())
    if page_no <= 1 or len(compact) < 200:
        return False
    return True


def _estimate_structured_tokens(structured_data: dict) -> int:
    return max(1, len(str(structured_data)) // 3)


class LocalSearchService:
    def __init__(self) -> None:
        self.store = SQLiteStore()

    def search(self, query: str, document_id: str | None = None, limit: int = 8, reconcile: bool = True) -> list[dict]:
        if reconcile:
            reconcile_local_documents(scan_raw=False, remove_orphan_parsed=False)
        return self.store.search_pages(query, document_id, limit)

    def get_pages(self, document_id: str, pages: list[int] | None = None, limit: int = 20, reconcile: bool = True) -> list[dict]:
        if reconcile:
            reconcile_local_documents(scan_raw=False, remove_orphan_parsed=False)
        return self.store.get_pages(document_id, pages, limit)

    def list_documents(self, limit: int = 100, reconcile: bool = True) -> list[dict]:
        if reconcile:
            reconcile_local_documents(scan_raw=False, remove_orphan_parsed=False)
        return self.store.list_documents(limit)

    def get_document_meta(self, document_id: str, reconcile: bool = True) -> dict:
        if reconcile:
            reconcile_local_documents(scan_raw=False, remove_orphan_parsed=False)
        return self.store.get_document_meta(document_id)

    def evidence_packet(self, query: str, market: str | None = None, symbol: str | None = None, company_name: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, structured_data: dict | None = None, strategy: str = "auto", include_retrieval_plan: bool = False) -> dict:
        if _should_use_accounting_strategy(query, strategy):
            return self.accounting_policy_evidence_packet(
                query,
                market=market,
                symbol=symbol,
                company_name=company_name,
                document_id=document_id,
                max_pages=max_pages,
                max_chars=max_chars,
                structured_data=structured_data,
                strategy=strategy,
                include_retrieval_plan=include_retrieval_plan,
            )
        if _should_use_financial_strategy(query, strategy):
            return self.financial_analysis_evidence_packet(
                query,
                market=market,
                symbol=symbol,
                company_name=company_name,
                document_id=document_id,
                max_pages=max_pages,
                max_chars=max_chars,
                structured_data=structured_data,
                strategy=strategy,
                include_retrieval_plan=include_retrieval_plan,
            )
        results = self.search(query, document_id, max_pages)
        items: list[EvidenceItem] = []
        total_chars = 0
        truncated = False
        for result in results:
            text = str(result.get("snippet") or "")
            if total_chars + len(text) > max_chars:
                text = text[: max(0, max_chars - total_chars)]
                truncated = True
            if text:
                items.append(
                    EvidenceItem(
                        source_type="page",
                        document_id=result.get("document_id"),
                        market=market,
                        symbol=symbol,
                        company_name=company_name,
                        page_no=int(result.get("page_no") or 0),
                        text=text,
                        score=result.get("score"),
                        token_estimate=max(1, len(text) // 3),
                    )
                )
                total_chars += len(text)
            if total_chars >= max_chars:
                truncated = True
                break
        structured_tokens = 0
        if structured_data:
            structured_tokens = _estimate_structured_tokens(structured_data)
            items.insert(0, EvidenceItem(source_type="structured_data", market=market, symbol=symbol, company_name=company_name, structured_payload=structured_data, token_estimate=structured_tokens))
        packet = EvidencePacket(query=query, route="local_document", market=market, symbol=symbol, company_name=company_name, evidence_items=items, token_estimate=max(1, total_chars // 3 + structured_tokens), max_chars=max_chars, truncated=truncated, generated_at=now_iso())
        return packet.to_dict()

    def accounting_policy_evidence_packet(self, query: str, market: str | None = None, symbol: str | None = None, company_name: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, structured_data: dict | None = None, strategy: str = "accounting_policy", include_retrieval_plan: bool = False) -> dict:
        return self.planned_evidence_packet(
            query,
            queries=_accounting_policy_queries(query),
            resolved_strategy="accounting_policy" if strategy == "auto" else strategy,
            market=market,
            symbol=symbol,
            company_name=company_name,
            document_id=document_id,
            max_pages=max_pages,
            max_chars=max_chars,
            structured_data=structured_data,
            include_retrieval_plan=include_retrieval_plan,
        )

    def financial_analysis_evidence_packet(self, query: str, market: str | None = None, symbol: str | None = None, company_name: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, structured_data: dict | None = None, strategy: str = "financial_analysis", include_retrieval_plan: bool = False) -> dict:
        return self.planned_evidence_packet(
            query,
            queries=_financial_analysis_queries(query),
            resolved_strategy="financial_analysis" if strategy == "auto" else strategy,
            market=market,
            symbol=symbol,
            company_name=company_name,
            document_id=document_id,
            max_pages=max_pages,
            max_chars=max_chars,
            structured_data=structured_data,
            include_retrieval_plan=include_retrieval_plan,
        )

    def planned_evidence_packet(self, query: str, queries: list[tuple[str, str]], resolved_strategy: str, market: str | None = None, symbol: str | None = None, company_name: str | None = None, document_id: str | None = None, max_pages: int = 8, max_chars: int = 12000, structured_data: dict | None = None, include_retrieval_plan: bool = False) -> dict:
        reconcile_summary = reconcile_local_documents(scan_raw=False, remove_orphan_parsed=False)
        per_query_limit = max(3, min(8, max_pages))
        page_hits: dict[tuple[str | None, int], dict] = {}

        for search_query, evidence_type in queries:
            for result in self.search(search_query, document_id, per_query_limit, reconcile=False):
                page_no = int(result.get("page_no") or 0)
                if page_no <= 0:
                    continue
                result_document_id = result.get("document_id")
                key = (result_document_id, page_no)
                hit = page_hits.setdefault(
                    key,
                    {
                        "document_id": result_document_id,
                        "page_no": page_no,
                        "matched_queries": set(),
                        "evidence_types": set(),
                        "snippets": [],
                        "is_adjacent": False,
                    },
                )
                hit["matched_queries"].add(search_query)
                hit["evidence_types"].add(evidence_type)
                if result.get("snippet"):
                    hit["snippets"].append(result.get("snippet"))

        seed_keys = list(page_hits.keys())
        for hit_document_id, page_no in seed_keys:
            for adjacent_page in (page_no - 1, page_no + 1):
                if adjacent_page <= 0:
                    continue
                key = (hit_document_id, adjacent_page)
                page_hits.setdefault(
                    key,
                    {
                        "document_id": hit_document_id,
                        "page_no": adjacent_page,
                        "matched_queries": set(),
                        "evidence_types": {"adjacent"},
                        "snippets": [],
                        "is_adjacent": True,
                        "adjacent_to": page_no,
                    },
                )

        selected_hits = _select_diverse_hits(list(page_hits.values()), max_pages)
        pages_by_document: dict[str, list[int]] = {}
        for hit in selected_hits:
            hit_document_id = hit.get("document_id") or document_id
            if not hit_document_id:
                continue
            pages_by_document.setdefault(str(hit_document_id), []).append(int(hit["page_no"]))

        pages: dict[tuple[str, int], dict] = {}
        for hit_document_id, page_numbers in pages_by_document.items():
            for page in self.get_pages(hit_document_id, sorted(set(page_numbers)), limit=max_pages, reconcile=False):
                pages[(hit_document_id, int(page.get("page_no") or 0))] = page

        meta_cache: dict[str, dict] = {}
        items: list[EvidenceItem] = []
        included_hits: list[dict] = []
        total_chars = 0
        truncated = False
        per_page_chars = max(800, min(2500, max_chars // max(1, max_pages)))

        for hit in selected_hits:
            hit_document_id = str(hit.get("document_id") or document_id or "")
            if not hit_document_id:
                continue
            page_no = int(hit["page_no"])
            page = pages.get((hit_document_id, page_no))
            if not page:
                continue
            if hit.get("is_adjacent") and not _useful_adjacent_text(str(page.get("text") or ""), page_no):
                continue
            matched_queries = sorted(hit["matched_queries"])
            evidence_type = _best_evidence_type(set(hit["evidence_types"]))
            remaining_chars = max_chars - total_chars
            if remaining_chars <= 0:
                truncated = True
                break
            text_limit = min(per_page_chars, remaining_chars)
            text = _excerpt_around_terms(str(page.get("text") or ""), matched_queries or [query], text_limit)
            if len(text) >= remaining_chars:
                truncated = True
            meta = meta_cache.get(hit_document_id)
            if meta is None:
                meta = self.get_document_meta(hit_document_id, reconcile=False)
                meta_cache[hit_document_id] = meta
            items.append(
                EvidenceItem(
                    source_type="page",
                    document_id=hit_document_id,
                    market=market or meta.get("market"),
                    symbol=symbol or meta.get("symbol"),
                    company_name=company_name or meta.get("company_name"),
                    page_no=page_no,
                    section_title=f"{evidence_type}; matched={', '.join(matched_queries) if matched_queries else 'adjacent'}",
                    text=text,
                    source_url=meta.get("pdf_url") or meta.get("detail_url"),
                    local_pdf_path=meta.get("local_pdf_path"),
                    token_estimate=max(1, len(text) // 3),
                )
            )
            included_hits.append(hit)
            total_chars += len(text)

        structured_tokens = 0
        if structured_data:
            structured_tokens = _estimate_structured_tokens(structured_data)
            items.insert(0, EvidenceItem(source_type="structured_data", market=market, symbol=symbol, company_name=company_name, structured_payload=structured_data, token_estimate=structured_tokens))

        packet = EvidencePacket(
            query=query,
            route="local_document",
            market=market,
            symbol=symbol,
            company_name=company_name,
            evidence_items=items,
            token_estimate=max(1, total_chars // 3 + structured_tokens),
            max_chars=max_chars,
            truncated=truncated,
            generated_at=now_iso(),
        ).to_dict()
        packet["strategy"] = resolved_strategy
        selected_types = sorted({et for hit in selected_hits for et in hit["evidence_types"]})
        compact_plan = {
            "strategy": packet["strategy"],
            "search_query_count": len(queries),
            "seed_hit_count": len(seed_keys),
            "expanded_hit_count": len(page_hits),
            "selected_page_count": len(selected_hits),
            "included_page_count": len(included_hits),
            "selected_evidence_types": selected_types,
            "reconcile": {
                "stale_count": reconcile_summary.get("stale_count"),
                "orphan_parsed_count": reconcile_summary.get("orphan_parsed_count"),
            },
        }
        if include_retrieval_plan:
            compact_plan.update(
                {
                    "search_queries": [{"query": search_query, "evidence_type": evidence_type} for search_query, evidence_type in queries],
                    "selected_pages": [
                        {
                            "document_id": hit.get("document_id"),
                            "page_no": hit.get("page_no"),
                            "matched_queries": sorted(hit["matched_queries"]),
                            "evidence_types": sorted(hit["evidence_types"]),
                            "is_adjacent": bool(hit.get("is_adjacent")),
                        }
                        for hit in selected_hits
                    ],
                    "included_pages": [
                        {
                            "document_id": hit.get("document_id"),
                            "page_no": hit.get("page_no"),
                            "matched_queries": sorted(hit["matched_queries"]),
                            "evidence_types": sorted(hit["evidence_types"]),
                            "is_adjacent": bool(hit.get("is_adjacent")),
                        }
                        for hit in included_hits
                    ],
                }
            )
        else:
            compact_plan["detail_omitted"] = "set include_retrieval_plan=true for search queries and page-level matches"
        packet["retrieval_plan"] = compact_plan
        return packet


def list_local_documents(limit: int = 100) -> list[dict]:
    return LocalSearchService().list_documents(limit)


def search_local_document_text(query: str, document_id: str | None = None, limit: int = 8) -> list[dict]:
    return LocalSearchService().search(query, document_id, limit)


def get_document_pages(document_id: str, page_numbers: list[int] | None = None, limit: int = 20) -> list[dict]:
    return LocalSearchService().get_pages(document_id, page_numbers, limit)


def get_document_meta(document_id: str) -> dict:
    return LocalSearchService().get_document_meta(document_id)


def cleanup_local_document(document_id: str, delete_pdf: bool = True, delete_parsed: bool = True, dry_run: bool = False) -> dict:
    return cleanup_document(document_id, delete_pdf=delete_pdf, delete_parsed=delete_parsed, dry_run=dry_run)


def cleanup_local_company(market: str, symbol: str, delete_pdfs: bool = True, delete_parsed: bool = True, delete_company_cache: bool = False, dry_run: bool = False) -> dict:
    return cleanup_company(market, symbol, delete_pdfs=delete_pdfs, delete_parsed=delete_parsed, delete_company_cache=delete_company_cache, dry_run=dry_run)


def reconcile_local_document_index(dry_run: bool = False) -> dict:
    return reconcile_local_documents(dry_run=dry_run)
