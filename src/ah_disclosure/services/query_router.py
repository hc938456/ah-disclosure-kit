from __future__ import annotations


ACCOUNTING_EVIDENCE_HINTS = [
    "会计",
    "确认",
    "政策",
    "处理",
    "列报",
    "披露",
    "附注",
    "收入确认",
    "会计处理",
    "recognition",
    "accounting",
    "accounting policy",
    "accounting policies",
    "accounting treatment",
    "presentation",
]

PROFILE_HINTS = ["公司资料", "注册地", "上市日期", "profile", "company profile"]

FINANCIAL_STRUCTURED_HINTS = [
    "资产负债表",
    "利润表",
    "现金流量表",
    "roe",
    "毛利率",
    "财务指标",
    "financial",
    "收入",
    "营收",
    "净利润",
    "营业收入",
    "revenue",
    "net profit",
]

COMPANY_DATA_HINTS = ["分红", "派息", "股东", "股东户数", "股本", "高管持股"]

PROSPECTUS_HINTS = ["招股书", "招股说明书", "上市文件", "募集说明书", "phip", "prospectus", "application proof"]

FILING_HINTS = ["年报", "中报", "季报", "财报", "公告", "通函", "业绩公告", "annual report", "financial report"]

DOWNLOAD_HINTS = ["下载", "download"]

HK_IPO_SCOPE_HINTS = ["港股", "香港", "hk"]

IPO_HINTS = ["ipo", "新股", "新上市"]

IPO_LIST_HINTS = ["新增", "至今", "名单", "清单", "列表", "list", "全年", "所有", "全部", "公司list", "上市公司"]

LOCAL_EVIDENCE_HINTS = ["原因", "为什么", "风险", "业务模式", "管理层讨论", "募投项目", "变化解释"]

BUSINESS_MODEL_HINTS = [
    "收入模式",
    "收入来源",
    "业务分部",
    "业务板块",
    "产品结构",
    "分行业",
    "分产品",
    "主营业务",
    "revenue model",
    "revenue stream",
    "revenue breakdown",
    "operating segment",
    "reportable segment",
    "business segment",
]

LLM_REQUIRED_ROUTES = {"local_document_evidence", "hybrid_structured_and_filing_evidence", "unsupported_hk_ipo_annual_list"}


def _contains_any(text: str, hints: list[str]) -> bool:
    return any(hint in text for hint in hints)


def _is_unsupported_hk_ipo_list_query(text: str) -> bool:
    if _contains_any(text, PROSPECTUS_HINTS):
        return False
    return _contains_any(text, HK_IPO_SCOPE_HINTS) and _contains_any(text, IPO_HINTS) and _contains_any(text, IPO_LIST_HINTS)


def route_query(query: str) -> dict:
    q = str(query).lower()
    if _contains_any(q, PROSPECTUS_HINTS):
        route = "prospectus_search_download_ingest"
    elif _is_unsupported_hk_ipo_list_query(q):
        route = "unsupported_hk_ipo_annual_list"
    elif _contains_any(q, DOWNLOAD_HINTS) and _contains_any(q, FILING_HINTS):
        route = "filing_search_download_ingest"
    elif _contains_any(q, BUSINESS_MODEL_HINTS):
        route = "local_document_evidence"
    elif _contains_any(q, ACCOUNTING_EVIDENCE_HINTS):
        route = "local_document_evidence"
    elif _contains_any(q, PROFILE_HINTS):
        route = "structured_profile"
    elif _contains_any(q, FINANCIAL_STRUCTURED_HINTS):
        route = "structured_financials"
    elif _contains_any(q, COMPANY_DATA_HINTS):
        route = "structured_company_data"
    elif _contains_any(q, FILING_HINTS):
        route = "filing_search_download_ingest"
    elif _contains_any(q, LOCAL_EVIDENCE_HINTS):
        route = "local_document_evidence"
    else:
        route = "hybrid_structured_and_filing_evidence"
    return {"query": query, "route": route, "llm_required": route in LLM_REQUIRED_ROUTES}
