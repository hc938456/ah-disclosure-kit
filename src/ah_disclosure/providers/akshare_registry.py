from __future__ import annotations

from functools import lru_cache

from ah_disclosure.core.errors import OptionalDependencyError


A_INTERFACES = {
    "company_profile": "stock_profile_cninfo",
    "company_info": "stock_individual_info_em",
    "business_description": "stock_zyjs_ths",
    "business_composition": "stock_zygc_em",
    "balance_sheet": "stock_balance_sheet_by_report_em",
    "income_statement": "stock_profit_sheet_by_report_em",
    "cashflow_statement": "stock_cash_flow_sheet_by_report_em",
    "financial_indicators": "stock_financial_analysis_indicator",
    "financial_abstract": "stock_financial_abstract",
    "performance_report": "stock_yjbb_em",
    "performance_express": "stock_yjkb_em",
    "performance_forecast": "stock_yjyg_em",
    "dividends": "stock_dividend_cninfo",
    "shareholder_count": "stock_hold_num_cninfo",
    "top_float_shareholders": "stock_gdfx_free_holding_detail_em",
    "share_capital_change": "stock_share_change_cninfo",
    "management_holdings": "stock_hold_management_detail_em",
    "repurchase": "stock_repurchase_em",
    "general_meeting": "stock_gddh_em",
    "major_contract": "stock_zdhtmx_em",
    "esg": "stock_esg_hz_sina",
}

H_INTERFACES = {
    "security_profile": "stock_hk_security_profile_em",
    "company_profile": "stock_hk_company_profile_em",
    "financial_statement": "stock_financial_hk_report_em",
    "financial_indicators": "stock_financial_hk_analysis_indicator_em",
    "core_indicators": "stock_hk_financial_indicator_em",
    "dividends": "stock_hk_dividend_payout_em",
}

IPO_INTERFACES = {
    "all": "stock_register_all_em",
    "kcb": "stock_register_kcb",
    "科创板": "stock_register_kcb",
    "cyb": "stock_register_cyb",
    "创业板": "stock_register_cyb",
    "sh": "stock_register_sh",
    "沪主板": "stock_register_sh",
    "sz": "stock_register_sz",
    "深主板": "stock_register_sz",
    "bj": "stock_register_bj",
    "北交所": "stock_register_bj",
}


@lru_cache(maxsize=1)
def get_akshare_module():
    try:
        import akshare as ak
    except Exception as exc:  # pragma: no cover - depends on environment
        raise OptionalDependencyError("akshare is required. Install with: pip install akshare") from exc
    return ak


def get_akshare_function(name: str):
    ak = get_akshare_module()
    if not hasattr(ak, name):
        raise AttributeError(f"AKShare function {name!r} is not available in the installed version.")
    return getattr(ak, name)


def list_supported_interfaces() -> dict:
    return {"A": A_INTERFACES, "H": H_INTERFACES, "IPO": IPO_INTERFACES}
