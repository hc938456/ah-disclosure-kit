from ah_disclosure.services.calculation_service import verify_analysis_calculations


def _evidence(name, value, evidence_id, *, period="2025 FY", unit="RMB'000"):
    return {
        "name": name,
        "value": value,
        "evidence_id": evidence_id,
        "period": period,
        "unit": unit,
        "currency": "RMB",
        "scope": "consolidated",
    }


def _derived(name, calculation_id):
    return {
        "name": name,
        "source_type": "calculation",
        "calculation_id": calculation_id,
    }


def test_effective_tax_rate_bridge_ties_to_reported_tax_expense():
    adjustments = {
        "tax_at_25_percent": 1_814_227,
        "non_taxable_income": -104_148,
        "non_deductible_expenses": 563_605,
        "prior_year_overprovision": -90_231,
        "rd_super_deduction": -138_491,
        "unrecognized_losses_and_temporary_differences": 371_654,
        "utilized_unrecognized_losses": -4_376,
        "newly_recognized_losses": 0,
        "concessionary_rates": -740_460,
        "deferred_tax_rate_change": 3_812,
        "different_jurisdiction_rates": -151_912,
    }
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "etr_tax_expense_bridge",
                "expression": " + ".join(adjustments),
                "variables": [
                    _evidence(name, value, "tax_note:p171")
                    for name, value in adjustments.items()
                ],
                "expected_value": 1_523_680,
                "absolute_tolerance": 0,
                "output_unit": "RMB'000",
                "checks": {
                    "same_unit": True,
                    "same_period": True,
                    "same_scope": True,
                },
            }
        ]
    )

    assert result["status"] == "verified"


def test_recomputed_effective_tax_rate_detects_mda_percentage_difference():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "recomputed_etr",
                "expression": "tax_expense / profit_before_tax * 100",
                "variables": [
                    _evidence("tax_expense", 1_523_680, "income_statement:p108"),
                    _evidence("profit_before_tax", 7_256_907, "income_statement:p108"),
                ],
                "expected_value": "21.6",
                "absolute_tolerance": "0.05",
                "output_unit": "%",
            }
        ]
    )

    calculation = result["results"][0]
    assert result["status"] == "discrepancy"
    assert calculation["calculated_value"].startswith("20.996")


def test_dupont_management_view_uses_average_assets_and_average_equity():
    calculations = [
        {
            "calculation_id": "average_assets",
            "expression": "(opening_assets + closing_assets) / 2",
            "variables": [
                _evidence("opening_assets", 56_977_435, "balance_sheet:p110-111", period="2024 YE"),
                _evidence("closing_assets", 63_696_738, "balance_sheet:p110-111", period="2025 YE"),
            ],
            "expected_value": "60337086.5",
        },
        {
            "calculation_id": "average_equity",
            "expression": "(opening_equity + closing_equity) / 2",
            "variables": [
                _evidence("opening_equity", 45_477_569, "balance_sheet:p111", period="2024 YE"),
                _evidence("closing_equity", 53_039_344, "balance_sheet:p111", period="2025 YE"),
            ],
            "expected_value": "49258456.5",
        },
        {
            "calculation_id": "net_margin",
            "expression": "profit / revenue",
            "variables": [
                _evidence("profit", 5_733_227, "income_statement:p108"),
                _evidence("revenue", 21_790_018, "income_statement:p108"),
            ],
        },
        {
            "calculation_id": "asset_turnover",
            "expression": "revenue / average_assets",
            "variables": [
                _evidence("revenue", 21_790_018, "income_statement:p108"),
                _derived("average_assets", "average_assets"),
            ],
        },
        {
            "calculation_id": "equity_multiplier",
            "expression": "average_assets / average_equity",
            "variables": [
                _derived("average_assets", "average_assets"),
                _derived("average_equity", "average_equity"),
            ],
        },
        {
            "calculation_id": "dupont_roe",
            "expression": "net_margin * asset_turnover * equity_multiplier * 100",
            "variables": [
                _derived("net_margin", "net_margin"),
                _derived("asset_turnover", "asset_turnover"),
                _derived("equity_multiplier", "equity_multiplier"),
            ],
            "expected_value": "11.6391",
            "absolute_tolerance": "0.0001",
            "output_unit": "%",
        },
        {
            "calculation_id": "direct_roe",
            "expression": "profit / average_equity * 100",
            "variables": [
                _evidence("profit", 5_733_227, "income_statement:p108"),
                _derived("average_equity", "average_equity"),
            ],
            "expected_value": "11.6391",
            "absolute_tolerance": "0.0001",
            "output_unit": "%",
        },
    ]
    result = verify_analysis_calculations(calculations)

    assert result["status"] == "calculated"
    assert result["results"][-2]["status"] == "verified"
    assert result["results"][-1]["status"] == "verified"
    assert result["results"][-2]["calculated_value"] == result["results"][-1]["calculated_value"]


def test_operating_working_capital_view_excludes_financing_and_flags_cashflow_gap():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "operating_nwc_2025",
                "expression": "inventory + receivables + contract_assets + contract_costs - payables - contract_liabilities - provisions",
                "variables": [
                    _evidence("inventory", 1_381_257, "balance_sheet:p110"),
                    _evidence("receivables", 8_852_792, "balance_sheet:p110"),
                    _evidence("contract_assets", 109_496, "balance_sheet:p110"),
                    _evidence("contract_costs", 2_010_157, "balance_sheet:p110"),
                    _evidence("payables", 3_287_418, "balance_sheet:p110"),
                    _evidence("contract_liabilities", 2_787_538, "balance_sheet:p110"),
                    _evidence("provisions", 185_656, "balance_sheet:p110"),
                ],
                "expected_value": 6_093_090,
            },
            {
                "calculation_id": "operating_nwc_2024",
                "expression": "inventory + receivables + contract_assets + contract_costs - payables - contract_liabilities - provisions",
                "variables": [
                    _evidence("inventory", 1_521_669, "balance_sheet:p110", period="2024 YE"),
                    _evidence("receivables", 6_240_747, "balance_sheet:p110", period="2024 YE"),
                    _evidence("contract_assets", 191_927, "balance_sheet:p110", period="2024 YE"),
                    _evidence("contract_costs", 1_492_931, "balance_sheet:p110", period="2024 YE"),
                    _evidence("payables", 2_778_195, "balance_sheet:p110", period="2024 YE"),
                    _evidence("contract_liabilities", 2_355_772, "balance_sheet:p110", period="2024 YE"),
                    _evidence("provisions", 0, "balance_sheet:p110", period="2024 YE"),
                ],
                "expected_value": 4_313_307,
            },
            {
                "calculation_id": "operating_nwc_increase",
                "expression": "closing_nwc - opening_nwc",
                "variables": [
                    _derived("closing_nwc", "operating_nwc_2025"),
                    _derived("opening_nwc", "operating_nwc_2024"),
                ],
                "expected_value": 1_779_783,
            },
            {
                "calculation_id": "cashflow_wc_effect",
                "expression": "inventory + contract_costs + receivables + contract_assets + contract_liabilities + payables",
                "variables": [
                    _evidence("inventory", 6_391, "cashflow:p115"),
                    _evidence("contract_costs", -367_644, "cashflow:p115"),
                    _evidence("receivables", -2_668_074, "cashflow:p115"),
                    _evidence("contract_assets", 78_377, "cashflow:p115"),
                    _evidence("contract_liabilities", 413_559, "cashflow:p115"),
                    _evidence("payables", 797_370, "cashflow:p115"),
                ],
                "expected_value": -1_740_021,
            },
            {
                "calculation_id": "balance_to_cashflow_wc_gap",
                "expression": "cashflow_effect + nwc_increase",
                "variables": [
                    _derived("cashflow_effect", "cashflow_wc_effect"),
                    _derived("nwc_increase", "operating_nwc_increase"),
                ],
                "expected_value": 0,
                "absolute_tolerance": 1,
            },
        ]
    )

    assert result["status"] == "discrepancy"
    assert result["results"][-1]["calculated_value"] == "39762"


def test_ppe_rollforward_ties_but_cash_capex_does_not_equal_accounting_additions():
    rollforward = verify_analysis_calculations(
        [
            {
                "calculation_id": "ppe_cost_rollforward",
                "expression": "opening + additions + cip_transfer + held_for_sale + disposals + fx",
                "variables": [
                    _evidence("opening", 30_608_816, "ppe_note:p177", period="2024 YE"),
                    _evidence("additions", 3_996_335, "ppe_note:p177"),
                    _evidence("cip_transfer", -16_061, "ppe_note:p177"),
                    _evidence("held_for_sale", -1_237_459, "ppe_note:p177"),
                    _evidence("disposals", -895_081, "ppe_note:p177"),
                    _evidence("fx", 871_519, "ppe_note:p177"),
                ],
                "expected_value": 33_328_069,
            },
            {
                "calculation_id": "ppe_accumulated_depreciation_rollforward",
                "expression": "opening + depreciation + cip_transfer + held_for_sale + disposals + fx",
                "variables": [
                    _evidence("opening", -4_538_358, "ppe_note:p177", period="2024 YE"),
                    _evidence("depreciation", -1_429_342, "ppe_note:p177"),
                    _evidence("cip_transfer", 16_061, "ppe_note:p177"),
                    _evidence("held_for_sale", 272_791, "ppe_note:p177"),
                    _evidence("disposals", 114_824, "ppe_note:p177"),
                    _evidence("fx", -25_128, "ppe_note:p177"),
                ],
                "expected_value": -5_589_152,
            },
            {
                "calculation_id": "ppe_net_carrying_value",
                "expression": "cost + accumulated_depreciation",
                "variables": [
                    _derived("cost", "ppe_cost_rollforward"),
                    _derived(
                        "accumulated_depreciation",
                        "ppe_accumulated_depreciation_rollforward",
                    ),
                ],
                "expected_value": 27_738_917,
            },
        ]
    )
    capex = verify_analysis_calculations(
        [
            {
                "calculation_id": "cash_capex_vs_accounting_additions",
                "expression": "accounting_additions - cash_purchases",
                "variables": [
                    _evidence("accounting_additions", 3_996_335, "ppe_note:p177"),
                    _evidence("cash_purchases", 3_685_115, "cashflow:p116"),
                ],
                "expected_value": 0,
                "absolute_tolerance": 0,
            }
        ]
    )

    assert rollforward["status"] == "verified"
    assert capex["status"] == "discrepancy"
    assert capex["results"][0]["calculated_value"] == "311220"


def test_provisional_roic_keeps_analyst_definition_as_an_explicit_assumption():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "provisional_ebit",
                "expression": "profit_before_tax + financing_cost",
                "variables": [
                    _evidence("profit_before_tax", 7_256_907, "income_statement:p108"),
                    _evidence("financing_cost", 143_059, "income_statement:p108"),
                ],
            },
            {
                "calculation_id": "provisional_nopat",
                "expression": "ebit * (1 - tax_rate)",
                "variables": [
                    _derived("ebit", "provisional_ebit"),
                    {
                        "name": "tax_rate",
                        "value": "0.2099627293005132903",
                        "source_type": "assumption",
                        "unit": "ratio",
                        "period": "2025 FY",
                        "scope": "consolidated",
                    },
                ],
            },
        ]
    )

    assert result["status"] == "calculated"
    assert result["assumption_based"] is True
    assert result["assumption_variables"] == ["provisional_nopat.tax_rate"]
