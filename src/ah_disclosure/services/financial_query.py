from __future__ import annotations


INDICATOR_HINTS = ["roe", "毛利率", "财务指标", "margin", "指标"]

STATEMENT_HINTS: list[tuple[str, str, list[str]]] = [
    ("balance_sheet", "balance", ["资产负债表", "balance sheet", "balance"]),
    ("cashflow_statement", "cashflow", ["现金流量表", "现金流", "cash flow", "cashflow"]),
    ("income_statement", "income", ["利润表", "损益表", "income statement", "profit statement", "p&l"]),
    ("financial_statements", "all", ["三张表", "财务报表", "financial statements"]),
]


def wants_financial_indicators(query: str) -> bool:
    q = str(query or "").casefold()
    return any(term in q for term in INDICATOR_HINTS)


def requested_financial_statement(query: str) -> tuple[str, str] | None:
    q = str(query or "").casefold()
    for result_key, statement, hints in STATEMENT_HINTS:
        if any(hint in q for hint in hints):
            return result_key, statement
    return None
