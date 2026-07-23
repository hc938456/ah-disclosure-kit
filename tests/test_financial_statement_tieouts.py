from ah_disclosure.services.calculation_service import verify_analysis_calculations


def _variable(name, value, evidence_id, **metadata):
    return {"name": name, "value": value, "evidence_id": evidence_id, **metadata}


def test_indirect_cash_flow_ties_net_profit_to_operating_cash_flow():
    values = {
        "net_profit": "35227979192.25",
        "asset_impairment": "92922139.64",
        "credit_impairment": "-18751517.60",
        "ppe_depreciation": "9022982211.16",
        "rou_amortisation": "11324269133.23",
        "intangible_amortisation": "422657232.83",
        "long_term_amortisation": "219922159.25",
        "disposal_gain": "-130927205.03",
        "scrapping_loss": "4940702.58",
        "fair_value_gain": "-32317683.69",
        "finance_cost": "4750216568.47",
        "investment_gain": "-5458552788.61",
        "deferred_tax_asset": "-150829744.99",
        "deferred_tax_liability": "901420362.51",
        "inventory_change": "19539735.99",
        "receivable_change": "-291904113.76",
        "payable_change": "-10360704373.58",
        "other": "2908420.58",
    }
    expression = " + ".join(values)
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "indirect_cfo_tieout",
                "expression": expression,
                "variables": [
                    _variable(name, value, "cashflow_note:p197-198", unit="RMB", period="2025 FY", scope="consolidated")
                    for name, value in values.items()
                ],
                "expected_value": "45545770431.23",
                "checks": {"same_unit": True, "same_period": True, "same_scope": True},
            }
        ]
    )

    assert result["status"] == "verified"


def test_financing_cash_flow_statement_ties_all_cash_lines_to_reported_net_total():
    values = {
        "borrowings_received": 2_675_863,
        "borrowings_repaid": -3_976_489,
        "nci_loans_repaid": -47_611,
        "share_repurchase": -6_560_757,
        "nci_transaction": 600_627,
        "nci_dividends": -3_697_701,
        "parent_dividends": -24_638_847,
        "share_option_proceeds": 1_434,
        "lease_principal": -14_513_408,
        "interest_paid": -1_611_418,
        "other": 31_018,
    }
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "financing_cashflow_tieout",
                "expression": " + ".join(values),
                "variables": [
                    _variable(name, value, "cashflow:p179", unit="RMB'000", period="2025 FY", scope="consolidated")
                    for name, value in values.items()
                ],
                "expected_value": -51_737_289,
                "checks": {"same_unit": True, "same_period": True, "same_scope": True},
            }
        ]
    )

    assert result["status"] == "verified"


def test_actual_debt_funding_distinguishes_gross_proceeds_repayments_and_total_financing_cashflow():
    evidence = "mengniu_cashflow:p161"
    calculations = [
        {
            "calculation_id": "gross_debt_proceeds",
            "expression": "short_term_paper + rmb_bonds + bank_loans",
            "variables": [
                _variable("short_term_paper", 17_698_989, evidence),
                _variable("rmb_bonds", 3_496_500, evidence),
                _variable("bank_loans", 22_894_455, evidence),
            ],
            "expected_value": 44_089_944,
        },
        {
            "calculation_id": "gross_debt_repayments",
            "expression": "paper_repaid + usd_bonds_repaid + bank_loans_repaid",
            "variables": [
                _variable("paper_repaid", 17_399_020, evidence),
                _variable("usd_bonds_repaid", 3_561_482, evidence),
                _variable("bank_loans_repaid", 31_737_134, evidence),
            ],
            "expected_value": 52_697_636,
        },
        {
            "calculation_id": "net_debt_principal_cashflow",
            "expression": "gross_proceeds - gross_repayments",
            "variables": [
                _variable("gross_proceeds", 44_089_944, evidence),
                _variable("gross_repayments", 52_697_636, evidence),
            ],
            "expected_value": -8_607_692,
        },
    ]

    result = verify_analysis_calculations(calculations)

    assert result["status"] == "verified"


def test_financing_liability_rollforward_separates_cash_fx_fair_value_and_other_changes():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "financing_liability_rollforward",
                "expression": "opening + financing_cash + fx + fair_value + other_changes",
                "variables": [
                    _variable("opening", 34_637_200, "financing_note:p281"),
                    _variable("financing_cash", -9_275_847, "financing_note:p281"),
                    _variable("fx", -500_965, "financing_note:p281"),
                    _variable("fair_value", 150_209, "financing_note:p281"),
                    _variable("other_changes", 378_139, "financing_note:p281"),
                ],
                "expected_value": 25_388_736,
            },
            {
                "calculation_id": "bank_loan_rollforward",
                "expression": "opening + financing_cash + fx + other_changes",
                "variables": [
                    _variable("opening", 27_162_692, "financing_note:p281"),
                    _variable("financing_cash", -9_143_622, "financing_note:p281"),
                    _variable("fx", -393_910, "financing_note:p281"),
                    _variable("other_changes", 346_424, "financing_note:p281"),
                ],
                "expected_value": 17_971_584,
            },
        ]
    )

    assert result["status"] == "verified"


def test_lease_liability_rollforward_includes_non_cash_new_leases_and_terminations():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "lease_liability_rollforward",
                "expression": "opening + financing_cash + fx + new_leases + disposal + termination + interest_expense",
                "variables": [
                    _variable("opening", 1_095_393, "lease_note:p281"),
                    _variable("financing_cash", -260_386, "lease_note:p281"),
                    _variable("fx", -695, "lease_note:p281"),
                    _variable("new_leases", 204_751, "lease_note:p280-281"),
                    _variable("disposal", -4_370, "lease_note:p281"),
                    _variable("termination", -361_507, "lease_note:p281"),
                    _variable("interest_expense", 48_624, "lease_note:p281"),
                ],
                "expected_value": 721_810,
            }
        ]
    )

    assert result["status"] == "verified"


def test_non_cash_new_lease_must_not_be_added_to_financing_cashflow():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "incorrect_cashflow_including_non_cash_lease",
                "expression": "reported_financing_cashflow + non_cash_new_lease",
                "variables": [
                    _variable("reported_financing_cashflow", -11_713_899, "cashflow:p161"),
                    _variable("non_cash_new_lease", 204_751, "cashflow_note:p280"),
                ],
                "expected_value": -11_713_899,
                "absolute_tolerance": 0,
            }
        ]
    )

    assert result["status"] == "discrepancy"
    assert result["results"][0]["difference"] == "204751"


def test_interest_expense_to_cash_paid_bridge_identifies_accrual_residual():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "interest_cash_residual",
                "expression": "interest_expense - financing_interest_paid - operating_interest_paid - lease_interest_paid",
                "variables": [
                    _variable("interest_expense", 970_752, "financing_note:p281"),
                    _variable("financing_interest_paid", 407_769, "cashflow:p161"),
                    _variable("operating_interest_paid", 431_487, "cashflow:p160"),
                    _variable("lease_interest_paid", 48_624, "cashflow:p161"),
                ],
                "expected_value": 82_872,
            }
        ]
    )

    assert result["status"] == "verified"


def test_cash_balance_bridge_and_a_h_presentation_difference_tie_out():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "cash_balance_bridge",
                "expression": "opening + cfo + cfi + cff + fx",
                "variables": [
                    _variable("opening", 184_189_078, "cashflow:p179"),
                    _variable("cfo", 45_545_770, "cashflow:p178"),
                    _variable("cfi", -25_378_766, "cashflow:p178"),
                    _variable("cff", -51_737_289, "cashflow:p179"),
                    _variable("fx", -1_737_192, "cashflow:p179"),
                ],
                "expected_value": 150_881_601,
            },
            {
                "calculation_id": "a_h_cash_change_presentation",
                "expression": "h_change_before_fx + h_fx - a_change",
                "variables": [
                    _variable("h_change_before_fx", -31_570_285, "h_cashflow:p179", scale=1000),
                    _variable("h_fx", -1_737_192, "h_cashflow:p179", scale=1000),
                    _variable("a_change", "-33307477024.27", "a_cashflow:p105"),
                ],
                "expected_value": 0,
                "absolute_tolerance": 500,
                "output_unit": "RMB",
            },
        ]
    )

    assert result["status"] == "verified"


def test_loss_to_positive_operating_cash_flow_bridge_is_recomputed_not_inferred():
    values = {
        "loss_before_tax": -2_058_191,
        "non_cash_and_finance_adjustments": 6_344_760,
        "working_capital_changes": 5_653_958,
    }
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "loss_to_cash_generated",
                "expression": " + ".join(values),
                "variables": [
                    _variable(name, value, "indirect_cashflow:p97") for name, value in values.items()
                ],
                "expected_value": 9_940_527,
            },
            {
                "calculation_id": "cash_generated_to_net_cfo",
                "expression": "cash_generated - tax_paid",
                "variables": [
                    _variable("cash_generated", 9_940_527, "indirect_cashflow:p97"),
                    _variable("tax_paid", 535_486, "indirect_cashflow:p97"),
                ],
                "expected_value": 9_405_041,
            },
        ]
    )

    assert result["status"] == "verified"


def test_borrowing_cashflow_and_liability_cash_change_difference_is_not_silently_forced_to_zero():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "borrowing_cash_scope_difference",
                "expression": "proceeds - repayments - liability_table_cash_change",
                "variables": [
                    _variable("proceeds", 94_708_940, "cashflow:p98"),
                    _variable("repayments", 96_213_305, "cashflow:p98"),
                    _variable("liability_table_cash_change", -1_485_481, "financing_note:p167"),
                ],
                "expected_value": 0,
                "absolute_tolerance": 1,
            }
        ]
    )

    assert result["status"] == "discrepancy"
    assert result["results"][0]["calculated_value"] == "-18884"
