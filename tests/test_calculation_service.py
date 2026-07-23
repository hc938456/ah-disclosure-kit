from ah_disclosure.services.calculation_service import verify_analysis_calculations


def test_calculates_growth_rate_with_decimal_precision():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "revenue_growth",
                "expression": "(current - prior) / prior * 100",
                "variables": [
                    {"name": "current", "value": "21386059440.13", "evidence_id": "revenue:e1"},
                    {"name": "prior", "value": "20685528503.12", "evidence_id": "revenue:e1"},
                ],
                "expected_value": "3.39",
                "absolute_tolerance": "0.01",
                "output_unit": "%",
            }
        ]
    )

    calculation = result["results"][0]
    assert result["status"] == "verified"
    assert calculation["within_tolerance"] is True
    assert calculation["evidence_ids"] == ["revenue:e1"]


def test_reconciles_a_h_amounts_after_unit_scaling():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "a_h_reconcile",
                "expression": "a_amount - h_amount",
                "variables": [
                    {"name": "a_amount", "value": "219503805222.70", "scale": 1, "unit": "RMB", "evidence_id": "a:e1"},
                    {"name": "h_amount", "value": "219503805", "scale": 1000, "unit": "RMB'000", "evidence_id": "h:e1"},
                ],
                "expected_value": 0,
                "absolute_tolerance": 500,
                "output_unit": "RMB",
            }
        ]
    )

    calculation = result["results"][0]
    assert calculation["calculated_value"] == "222.7"
    assert calculation["within_tolerance"] is True


def test_calculates_option_intrinsic_value_and_dilution():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "option_intrinsic_value",
                "expression": "max(market_price - exercise_price, 0) * option_count",
                "variables": [
                    {"name": "market_price", "value": "42.50", "evidence_id": "option:e1"},
                    {"name": "exercise_price", "value": "18.75", "evidence_id": "option:e2"},
                    {"name": "option_count", "value": "1200000", "evidence_id": "option:e2"},
                ],
                "expected_value": "28500000",
            },
            {
                "calculation_id": "potential_dilution",
                "expression": "incremental_shares / weighted_shares * 100",
                "variables": [
                    {"name": "incremental_shares", "value": "750000", "evidence_id": "eps:e1"},
                    {"name": "weighted_shares", "value": "150000000", "evidence_id": "eps:e1"},
                ],
                "expected_value": "0.5",
            },
        ]
    )

    assert result["status"] == "verified"
    assert [item["calculated_value"] for item in result["results"]] == ["28500000", "0.5"]


def test_rejects_code_execution_and_division_by_zero():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "unsafe",
                "expression": "__import__('os').system('whoami')",
                "variables": [{"name": "x", "value": 1}],
            },
            {
                "calculation_id": "zero",
                "expression": "x / zero",
                "variables": [{"name": "x", "value": 1}, {"name": "zero", "value": 0}],
            },
        ]
    )

    assert result["status"] == "invalid"
    assert all(item["status"] == "invalid" for item in result["results"])


def test_requires_evidence_links_but_allows_explicit_assumptions():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "unlinked",
                "expression": "reported * scenario_rate",
                "variables": [
                    {"name": "reported", "value": 100},
                    {"name": "scenario_rate", "value": "1.1", "source_type": "assumption"},
                ],
            }
        ]
    )

    assert result["status"] == "unlinked"
    assert result["results"][0]["unlinked_variables"] == ["reported"]
    assert result["assumption_based"] is True
    assert result["assumption_variables"] == ["unlinked.scenario_rate"]


def test_rejects_unknown_variable_source_type():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "unsafe_source",
                "expression": "value",
                "variables": [
                    {"name": "value", "value": 1, "source_type": "model_guess"}
                ],
            }
        ]
    )

    assert result["status"] == "invalid"
    assert "unsupported source_type" in result["results"][0]["validation_errors"][0]


def test_detects_period_scope_or_currency_mismatch_when_requested():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "bad_comparison",
                "expression": "a - b",
                "variables": [
                    {
                        "name": "a",
                        "value": 100,
                        "period": "2025 FY",
                        "scope": "consolidated",
                        "currency": "RMB",
                        "evidence_id": "a:e1",
                    },
                    {
                        "name": "b",
                        "value": 90,
                        "period": "2024 H1",
                        "scope": "parent company",
                        "currency": "USD",
                        "evidence_id": "b:e1",
                    },
                ],
                "checks": {
                    "same_period": True,
                    "same_scope": True,
                    "same_currency": True,
                },
            }
        ]
    )

    calculation = result["results"][0]
    assert result["status"] == "context_mismatch"
    assert len(calculation["context_errors"]) == 3


def test_reports_discrepancy_outside_tolerance():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "bad_rollforward",
                "expression": "opening + granted - exercised - lapsed",
                "variables": [
                    {"name": "opening", "value": 100, "evidence_id": "e1"},
                    {"name": "granted", "value": 20, "evidence_id": "e1"},
                    {"name": "exercised", "value": 10, "evidence_id": "e1"},
                    {"name": "lapsed", "value": 5, "evidence_id": "e1"},
                ],
                "expected_value": 99,
                "absolute_tolerance": 1,
            }
        ]
    )

    assert result["status"] == "discrepancy"
    assert result["results"][0]["difference"] == "6"


def test_calculation_graph_reuses_prior_results_without_retyping_values():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "gross_proceeds",
                "expression": "loan + bond",
                "variables": [
                    {"name": "loan", "value": 80, "evidence_id": "financing:e1"},
                    {"name": "bond", "value": 20, "evidence_id": "financing:e1"},
                ],
                "expected_value": 100,
            },
            {
                "calculation_id": "net_funding",
                "expression": "proceeds - repayments",
                "variables": [
                    {
                        "name": "proceeds",
                        "source_type": "calculation",
                        "calculation_id": "gross_proceeds",
                    },
                    {"name": "repayments", "value": 70, "evidence_id": "financing:e2"},
                ],
                "expected_value": 30,
            },
        ],
        allowed_evidence_ids={"financing:e1", "financing:e2"},
    )

    assert result["status"] == "verified"
    assert result["results"][1]["calculation_dependencies"] == ["gross_proceeds"]
    assert result["results"][1]["evidence_ids"] == ["financing:e1", "financing:e2"]


def test_evidence_registry_rejects_plausible_but_unknown_ids():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "amount",
                "expression": "reported",
                "variables": [
                    {"name": "reported", "value": 100, "evidence_id": "claim:e99"}
                ],
                "expected_value": 100,
            }
        ],
        allowed_evidence_ids={"claim:e1"},
    )

    assert result["status"] == "unlinked"
    assert result["results"][0]["unknown_evidence_ids"] == ["claim:e99"]


def test_evidence_catalog_rejects_a_value_not_present_on_the_referenced_page():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "fabricated_value",
                "expression": "reported",
                "variables": [
                    {"name": "reported", "value": 999, "evidence_id": "claim:e1"}
                ],
                "expected_value": 999,
            }
        ],
        allowed_evidence_ids={"claim:e1"},
        evidence_catalog={"claim:e1": "Reported revenue was RMB123 million."},
    )

    calculation = result["results"][0]
    assert result["status"] == "unlinked"
    assert calculation["unbound_value_variables"] == ["reported"]


def test_evidence_matching_uses_complete_number_tokens_and_checks_zero():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "token_boundary",
                "expression": "reported + zero",
                "variables": [
                    {"name": "reported", "value": 123, "evidence_id": "e1"},
                    {"name": "zero", "value": 0, "evidence_id": "e2"},
                ],
                "expected_value": 123,
            }
        ],
        evidence_catalog={"e1": "The value is 1234.", "e2": "The balance was 0."},
    )

    calculation = result["results"][0]
    assert result["status"] == "unlinked"
    assert calculation["unbound_value_variables"] == ["reported"]
    assert calculation["variables"][0]["source_value_status"] == "not_found"
    assert calculation["variables"][0]["source_value_verified"] is False
    assert calculation["variables"][1]["source_value_status"] == "matched"
    assert calculation["variables"][1]["source_value_verified"] is True


def test_evidence_matching_supports_accounting_parentheses():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "accounting_negative",
                "expression": "loss",
                "variables": [
                    {"name": "loss", "value": -1234, "evidence_id": "e1"},
                ],
                "expected_value": -1234,
            }
        ],
        evidence_catalog={"e1": "Loss for the year was (1,234)."},
    )

    variable = result["results"][0]["variables"][0]
    assert result["status"] == "verified"
    assert variable["source_value_status"] == "matched"
    assert variable["source_value_match_type"] == "equal"


def test_explicit_percent_ratio_and_complement_source_matching():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "source_formats",
                "expression": "percent_value + ratio_value + minority_ratio",
                "variables": [
                    {
                        "name": "percent_value",
                        "value": "12.5",
                        "evidence_id": "e1",
                        "source_value_format": "percent",
                    },
                    {
                        "name": "ratio_value",
                        "value": "0.125",
                        "evidence_id": "e1",
                        "source_value_format": "ratio",
                    },
                    {
                        "name": "minority_ratio",
                        "value": "0.25",
                        "evidence_id": "e2",
                        "source_value_format": "ratio",
                        "source_value_relation": "complement",
                    },
                ],
                "expected_value": "12.875",
            }
        ],
        evidence_catalog={"e1": "The rate was 12.5%.", "e2": "The parent held 75%."},
    )

    variables = result["results"][0]["variables"]
    assert result["status"] == "verified"
    assert [item["source_value_status"] for item in variables] == ["matched"] * 3
    assert variables[2]["source_value_match_type"] == "complement"


def test_source_failure_precedes_arithmetic_discrepancy_but_preserves_it():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "bad_source_and_math",
                "expression": "reported",
                "variables": [
                    {"name": "reported", "value": 100, "evidence_id": "e1"},
                ],
                "expected_value": 90,
            }
        ],
        evidence_catalog={"e1": "Reported value was 80."},
    )

    calculation = result["results"][0]
    assert result["status"] == "unlinked"
    assert calculation["status"] == "unlinked"
    assert calculation["arithmetic_status"] == "discrepancy"


def test_infers_rounding_tolerance_only_from_decimal_expected_value_text():
    inferred = verify_analysis_calculations(
        [
            {
                "calculation_id": "rounded",
                "expression": "value",
                "variables": [{"name": "value", "value": "1.234", "source_type": "assumption"}],
                "expected_value": "1.23",
            }
        ]
    )["results"][0]
    strict_integer = verify_analysis_calculations(
        [
            {
                "calculation_id": "strict_integer",
                "expression": "value",
                "variables": [{"name": "value", "value": "10.4", "source_type": "assumption"}],
                "expected_value": 10,
            }
        ]
    )["results"][0]
    explicit_precision = verify_analysis_calculations(
        [
            {
                "calculation_id": "rounded_integer",
                "expression": "value",
                "variables": [{"name": "value", "value": "10.4", "source_type": "assumption"}],
                "expected_value": 10,
                "expected_precision": 0,
            }
        ]
    )["results"][0]
    explicit_zero = verify_analysis_calculations(
        [
            {
                "calculation_id": "explicit_zero",
                "expression": "value",
                "variables": [{"name": "value", "value": "1.234", "source_type": "assumption"}],
                "expected_value": "1.23",
                "absolute_tolerance": 0,
            }
        ]
    )["results"][0]

    assert inferred["absolute_tolerance"] == "0.005"
    assert inferred["effective_absolute_tolerance"] == "0.005"
    assert inferred["tolerance_source"] == "reported_precision"
    assert inferred["arithmetic_status"] == "verified"
    assert strict_integer["absolute_tolerance"] == "0"
    assert strict_integer["arithmetic_status"] == "discrepancy"
    assert explicit_precision["absolute_tolerance"] == "0.5"
    assert explicit_precision["arithmetic_status"] == "verified"
    assert explicit_zero["absolute_tolerance"] == "0"
    assert explicit_zero["tolerance_source"] == "explicit"
    assert explicit_zero["arithmetic_status"] == "discrepancy"


def test_calculation_summary_reports_source_binding_status():
    verified = verify_analysis_calculations(
        [
            {
                "calculation_id": "bound",
                "expression": "value",
                "variables": [{"name": "value", "value": 10, "evidence_id": "e1"}],
                "expected_value": 10,
            }
        ],
        evidence_catalog={"e1": "The reported value was 10."},
    )
    assumptions_only = verify_analysis_calculations(
        [
            {
                "calculation_id": "assumption",
                "expression": "value",
                "variables": [{"name": "value", "value": 10, "source_type": "assumption"}],
            }
        ]
    )

    assert verified["source_binding_status"] == "verified"
    assert assumptions_only["source_binding_status"] == "not_applicable"


def test_empty_and_non_object_calculations_are_invalid():
    empty = verify_analysis_calculations([])
    malformed = verify_analysis_calculations(["not-an-object"])

    assert empty["status"] == "invalid"
    assert "non-empty" in empty["validation_errors"][0]
    assert malformed["status"] == "invalid"
    assert "must be an object" in malformed["validation_errors"][0]


def test_duplicate_calculation_ids_are_rejected_before_graph_execution():
    result = verify_analysis_calculations(
        [
            {
                "calculation_id": "duplicate",
                "expression": "value",
                "variables": [{"name": "value", "value": 1, "source_type": "assumption"}],
            },
            {
                "calculation_id": "duplicate",
                "expression": "value",
                "variables": [{"name": "value", "value": 2, "source_type": "assumption"}],
            },
        ]
    )

    assert result["status"] == "invalid"
    assert result["results"] == []
    assert result["validation_errors"] == ["duplicate calculation_id: duplicate"]
