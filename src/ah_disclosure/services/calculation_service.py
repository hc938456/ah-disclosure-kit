from __future__ import annotations

import ast
import re
import unicodedata
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any


MAX_CALCULATIONS = 30
MAX_VARIABLES = 40
MAX_EXPRESSION_LENGTH = 500
_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_.,(])"
    r"(?P<open>\()?\s*(?P<sign>[+-])?\s*"
    r"(?P<number>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+)"
    r"\s*(?P<percent>%?)\s*(?P<close>\))?"
    r"(?![A-Za-z0-9_)]|[.,]\d)"
)
_SOURCE_VALUE_FORMATS = {"number", "percent", "ratio"}
_SOURCE_VALUE_RELATIONS = {"equal", "complement"}


def _decimal(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{field} must be numeric")
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not number.is_finite():
        raise ValueError(f"{field} must be finite")
    return number


def _format_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return format(normalized, "f")
    return format(normalized, "f").rstrip("0").rstrip(".")


def _source_target(
    value: Decimal,
    source_value_format: str,
    source_value_relation: str,
) -> Decimal:
    if source_value_relation == "equal":
        target = value
    elif source_value_format == "percent":
        target = Decimal(100) - value
    else:
        target = Decimal(1) - value
    return target * 100 if source_value_format == "ratio" else target


def _evidence_contains_number(
    text: str,
    value: Decimal,
    *,
    source_value_format: str = "number",
    source_value_relation: str = "equal",
) -> bool:
    body = unicodedata.normalize("NFKC", str(text or "")).translate(
        str.maketrans("−–—（）", "---()")
    )
    body = body.replace("，", ",")
    target = _source_target(value, source_value_format, source_value_relation)
    for match in _NUMBER_TOKEN_RE.finditer(body):
        opening = bool(match.group("open"))
        closing = bool(match.group("close"))
        if opening != closing:
            continue
        has_percent = bool(match.group("percent"))
        if source_value_format == "number" and has_percent:
            continue
        if source_value_format in {"percent", "ratio"} and not has_percent:
            continue
        token_value = Decimal(match.group("number").replace(",", ""))
        if match.group("sign") == "-" or opening:
            token_value = -token_value
        if token_value == target:
            return True
    return False


def _expected_decimal_precision(value: Any) -> int | None:
    text = str(value).replace(",", "").strip()
    match = re.fullmatch(r"[+-]?(?:\d+)(?:\.(\d+))?(?:[eE]([+-]?\d+))?", text)
    if not match or match.group(1) is None:
        return None
    fractional_digits = len(match.group(1))
    exponent = int(match.group(2) or 0)
    return max(fractional_digits - exponent, 0)


def _rounding_tolerance(precision: int) -> Decimal:
    return Decimal("0.5").scaleb(-precision)


def _evaluate(node: ast.AST, variables: dict[str, Decimal]) -> Decimal:
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, variables)
    if isinstance(node, ast.Name):
        if node.id not in variables:
            raise ValueError(f"unknown variable: {node.id}")
        return variables[node.id]
    if isinstance(node, ast.Constant):
        return _decimal(node.value, "numeric literal")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _evaluate(node.operand, variables)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _evaluate(node.left, variables)
        right = _evaluate(node.right, variables)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ValueError("division by zero")
            return left / right
        if isinstance(node.op, ast.Pow):
            if right != right.to_integral() or abs(right) > 12:
                raise ValueError("power exponent must be an integer between -12 and 12")
            return left ** int(right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.keywords:
            raise ValueError("keyword arguments are not allowed")
        args = [_evaluate(argument, variables) for argument in node.args]
        if node.func.id == "abs" and len(args) == 1:
            return abs(args[0])
        if node.func.id == "min" and args:
            return min(args)
        if node.func.id == "max" and args:
            return max(args)
        if node.func.id == "round" and len(args) in {1, 2}:
            digits = int(args[1]) if len(args) == 2 else 0
            if len(args) == 2 and args[1] != args[1].to_integral():
                raise ValueError("round digits must be an integer")
            if abs(digits) > 12:
                raise ValueError("round digits must be between -12 and 12")
            return args[0].quantize(Decimal(1).scaleb(-digits))
    raise ValueError(f"unsupported expression element: {type(node).__name__}")


def verify_calculation(
    calculation: dict[str, Any],
    index: int = 1,
    *,
    derived_results: dict[str, dict[str, Any]] | None = None,
    allowed_evidence_ids: set[str] | None = None,
    evidence_catalog: dict[str, str] | None = None,
) -> dict[str, Any]:
    calculation_id = str(calculation.get("calculation_id") or f"calculation_{index}")[:80]
    expression = str(calculation.get("expression") or "").strip()
    result: dict[str, Any] = {
        "calculation_id": calculation_id,
        "expression": expression,
        "status": "invalid",
        "evidence_ids": [],
        "validation_errors": [],
    }
    try:
        if not expression or len(expression) > MAX_EXPRESSION_LENGTH:
            raise ValueError(f"expression must contain 1-{MAX_EXPRESSION_LENGTH} characters")
        raw_variables = calculation.get("variables")
        if not isinstance(raw_variables, list) or not raw_variables:
            raise ValueError("variables must be a non-empty array")
        if len(raw_variables) > MAX_VARIABLES:
            raise ValueError(f"variables exceed max_variables={MAX_VARIABLES}")

        variables: dict[str, Decimal] = {}
        variable_details: list[dict[str, Any]] = []
        evidence_ids: list[str] = []
        unlinked_variables: list[str] = []
        unknown_evidence_ids: list[str] = []
        unbound_value_variables: list[str] = []
        assumption_variables: list[str] = []
        calculation_dependencies: list[str] = []
        for raw in raw_variables:
            if not isinstance(raw, dict):
                raise ValueError("each variable must be an object")
            name = str(raw.get("name") or "").strip()
            if not _NAME_RE.fullmatch(name):
                raise ValueError(f"invalid variable name: {name!r}")
            if name in variables:
                raise ValueError(f"duplicate variable: {name}")
            source_type = str(raw.get("source_type") or "evidence").strip().casefold()
            if source_type not in {"evidence", "assumption", "calculation"}:
                raise ValueError(f"unsupported source_type for {name}: {source_type!r}")
            if source_type == "assumption":
                assumption_variables.append(name)
            dependency_id = str(raw.get("calculation_id") or "").strip()
            upstream_evidence_ids: list[str] = []
            if source_type == "calculation":
                upstream = (derived_results or {}).get(dependency_id)
                if not dependency_id or upstream is None:
                    raise ValueError(f"{name} references unknown prior calculation: {dependency_id!r}")
                if upstream.get("status") not in {"verified", "calculated"}:
                    raise ValueError(
                        f"{name} references unusable calculation {dependency_id!r} "
                        f"with status {upstream.get('status')!r}"
                    )
                value = _decimal(upstream.get("calculated_value"), f"{name}.calculation_value")
                upstream_evidence_ids = [str(item) for item in upstream.get("evidence_ids") or []]
                if dependency_id not in calculation_dependencies:
                    calculation_dependencies.append(dependency_id)
            else:
                value = _decimal(raw.get("value"), f"{name}.value")
            scale = _decimal(raw.get("scale", 1), f"{name}.scale")
            scaled_value = value * scale
            variables[name] = scaled_value
            evidence_id = str(raw.get("evidence_id") or "").strip()
            if evidence_id and evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
            for upstream_evidence_id in upstream_evidence_ids:
                if upstream_evidence_id not in evidence_ids:
                    evidence_ids.append(upstream_evidence_id)
            if (
                evidence_id
                and allowed_evidence_ids is not None
                and evidence_id not in allowed_evidence_ids
                and evidence_id not in unknown_evidence_ids
            ):
                unknown_evidence_ids.append(evidence_id)
            source_value_verified: bool | None = None
            source_value_status = (
                "not_applicable"
                if source_type in {"assumption", "calculation"}
                else "not_checked"
            )
            source_value_match_type: str | None = None
            source_value_format = str(raw.get("source_value_format") or "number").strip().casefold()
            source_value_relation = str(raw.get("source_value_relation") or "equal").strip().casefold()
            if source_value_format not in _SOURCE_VALUE_FORMATS:
                raise ValueError(
                    f"unsupported source_value_format for {name}: {source_value_format!r}"
                )
            if source_value_relation not in _SOURCE_VALUE_RELATIONS:
                raise ValueError(
                    f"unsupported source_value_relation for {name}: {source_value_relation!r}"
                )
            if (
                source_type == "evidence"
                and evidence_id
                and evidence_catalog is not None
                and evidence_id in evidence_catalog
            ):
                source_value_verified = _evidence_contains_number(
                    evidence_catalog[evidence_id],
                    value,
                    source_value_format=source_value_format,
                    source_value_relation=source_value_relation,
                )
                source_value_status = "matched" if source_value_verified else "not_found"
                if source_value_verified:
                    source_value_match_type = source_value_relation
                if source_value_verified is False:
                    unbound_value_variables.append(name)
            if not evidence_id and source_type not in {"assumption", "calculation"}:
                unlinked_variables.append(name)
            variable_details.append(
                {
                    "name": name,
                    "source_value": _format_decimal(value),
                    "scale": _format_decimal(scale),
                    "calculation_value": _format_decimal(scaled_value),
                    "unit": raw.get("unit"),
                    "period": raw.get("period"),
                    "scope": raw.get("scope"),
                    "currency": raw.get("currency"),
                    "evidence_id": evidence_id or None,
                    "source_type": source_type,
                    "calculation_id": dependency_id or None,
                    "source_value_format": source_value_format,
                    "source_value_relation": source_value_relation,
                    "source_value_status": source_value_status,
                    "source_value_match_type": source_value_match_type,
                    "source_value_verified": source_value_verified,
                }
            )

        tree = ast.parse(expression, mode="eval")
        with localcontext() as context:
            context.prec = 38
            calculated = _evaluate(tree, variables)
        expected_raw = calculation.get("expected_value")
        expected = _decimal(expected_raw, "expected_value") if expected_raw is not None else None
        has_explicit_tolerance = (
            "absolute_tolerance" in calculation or "relative_tolerance" in calculation
        )
        absolute_tolerance = abs(
            _decimal(calculation.get("absolute_tolerance", 0), "absolute_tolerance")
        )
        relative_tolerance = abs(
            _decimal(calculation.get("relative_tolerance", 0), "relative_tolerance")
        )
        expected_precision: int | None = None
        if calculation.get("expected_precision") is not None:
            precision_decimal = _decimal(calculation["expected_precision"], "expected_precision")
            if precision_decimal != precision_decimal.to_integral() or not 0 <= precision_decimal <= 12:
                raise ValueError("expected_precision must be an integer between 0 and 12")
            expected_precision = int(precision_decimal)
        elif expected_raw is not None:
            expected_precision = _expected_decimal_precision(expected_raw)
        if expected is not None and not has_explicit_tolerance and expected_precision is not None:
            absolute_tolerance = _rounding_tolerance(expected_precision)
        tolerance_source = (
            "explicit"
            if has_explicit_tolerance
            else "reported_precision"
            if expected is not None and expected_precision is not None
            else "strict_default"
        )
        difference = abs(calculated - expected) if expected is not None else None
        within_tolerance = None
        if expected is not None:
            assert difference is not None
            relative_difference = difference / abs(expected) if expected != 0 else None
            within_tolerance = difference <= absolute_tolerance or (
                relative_difference is not None and relative_difference <= relative_tolerance
            )
        arithmetic_status = (
            "verified"
            if within_tolerance is True
            else "discrepancy"
            if within_tolerance is False
            else "calculated"
        )
        result.update(
            {
                "status": arithmetic_status,
                "arithmetic_status": arithmetic_status,
                "variables": variable_details,
                "calculated_value": _format_decimal(calculated),
                "expected_value": _format_decimal(expected) if expected is not None else None,
                "difference": _format_decimal(difference) if difference is not None else None,
                "absolute_tolerance": _format_decimal(absolute_tolerance),
                "effective_absolute_tolerance": _format_decimal(absolute_tolerance),
                "relative_tolerance": _format_decimal(relative_tolerance),
                "tolerance_source": tolerance_source,
                "expected_precision": expected_precision,
                "within_tolerance": within_tolerance,
                "output_unit": calculation.get("output_unit"),
                "evidence_ids": evidence_ids,
                "unlinked_variables": unlinked_variables,
                "unknown_evidence_ids": unknown_evidence_ids,
                "unbound_value_variables": unbound_value_variables,
                "assumption_variables": assumption_variables,
                "assumption_based": bool(assumption_variables),
                "calculation_dependencies": calculation_dependencies,
                "context": calculation.get("context") if isinstance(calculation.get("context"), dict) else {},
            }
        )
        raw_checks = calculation.get("checks")
        checks: dict[str, Any] = raw_checks if isinstance(raw_checks, dict) else {}
        context_errors: list[str] = []
        for field in ("unit", "period", "scope", "currency"):
            if checks.get(f"same_{field}") is True:
                values = {str(item.get(field) or "").strip() for item in variable_details}
                if "" in values:
                    context_errors.append(f"same_{field} check requires {field} on every variable")
                elif len(values) > 1:
                    context_errors.append(f"same_{field} check failed: {sorted(values)}")
        required_metadata = checks.get("required_metadata")
        if isinstance(required_metadata, list):
            allowed_fields = {"unit", "period", "scope", "currency"}
            for field in [str(item) for item in required_metadata if str(item) in allowed_fields]:
                missing = [item["name"] for item in variable_details if not item.get(field)]
                if missing:
                    context_errors.append(f"missing {field}: {', '.join(missing)}")
        result["context_checks"] = checks
        result["context_errors"] = context_errors
        if unlinked_variables or unknown_evidence_ids or unbound_value_variables:
            result["status"] = "unlinked"
            if unlinked_variables:
                result["validation_errors"].append(
                    "variables require evidence_id unless source_type is assumption or calculation: "
                    + ", ".join(unlinked_variables)
                )
            if unknown_evidence_ids:
                result["validation_errors"].append(
                    "evidence_ids are not present in the supplied evidence registry: "
                    + ", ".join(unknown_evidence_ids)
                )
            if unbound_value_variables:
                result["validation_errors"].append(
                    "source values were not found in their referenced evidence text: "
                    + ", ".join(unbound_value_variables)
                )
        elif context_errors:
            result["status"] = "context_mismatch"
            result["validation_errors"].extend(context_errors)
    except (SyntaxError, ValueError, ArithmeticError, InvalidOperation) as exc:
        result["validation_errors"].append(str(exc))
    return result


def verify_analysis_calculations(
    calculations: Any,
    *,
    allowed_evidence_ids: set[str] | None = None,
    evidence_catalog: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Execute bounded, evidence-linked decimal calculations without eval()."""
    if not isinstance(calculations, list):
        return {
            "status": "invalid",
            "results": [],
            "validation_errors": ["calculations must be an array"],
        }
    if not calculations:
        return {
            "status": "invalid",
            "results": [],
            "validation_errors": ["calculations must be a non-empty array"],
        }
    if len(calculations) > MAX_CALCULATIONS:
        return {
            "status": "invalid",
            "results": [],
            "validation_errors": [
                f"calculations exceed max_calculations={MAX_CALCULATIONS}"
            ],
        }
    invalid_indexes = [
        str(index)
        for index, item in enumerate(calculations)
        if not isinstance(item, dict)
    ]
    if invalid_indexes:
        return {
            "status": "invalid",
            "results": [],
            "validation_errors": [
                "each calculation must be an object; invalid indexes: "
                + ", ".join(invalid_indexes)
            ],
        }
    calculation_ids = [
        str(item.get("calculation_id") or f"calculation_{index}")[:80]
        for index, item in enumerate(calculations, start=1)
    ]
    duplicate_ids = sorted(
        {item for item in calculation_ids if calculation_ids.count(item) > 1}
    )
    if duplicate_ids:
        return {
            "status": "invalid",
            "results": [],
            "validation_errors": [
                "duplicate calculation_id: " + ", ".join(duplicate_ids)
            ],
        }
    bounded = calculations[:MAX_CALCULATIONS]
    results: list[dict[str, Any]] = []
    derived_results: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(bounded, start=1):
        result = verify_calculation(
            item,
            index,
            derived_results=derived_results,
            allowed_evidence_ids=allowed_evidence_ids,
            evidence_catalog=evidence_catalog,
        )
        results.append(result)
        derived_results[result["calculation_id"]] = result
    errors: list[str] = []
    statuses = {item["status"] for item in results}
    if "invalid" in statuses:
        status = "invalid"
    elif "unlinked" in statuses:
        status = "unlinked"
    elif "context_mismatch" in statuses:
        status = "context_mismatch"
    elif "discrepancy" in statuses:
        status = "discrepancy"
    elif results and statuses == {"verified"}:
        status = "verified"
    else:
        status = "calculated"
    assumption_variables = [
        f"{item['calculation_id']}.{name}"
        for item in results
        for name in item.get("assumption_variables") or []
    ]
    source_statuses = [
        variable.get("source_value_status")
        for result in results
        for variable in result.get("variables") or []
        if variable.get("source_type") == "evidence"
    ]
    if "not_found" in source_statuses:
        source_binding_status = "failed"
    elif source_statuses and set(source_statuses) == {"matched"}:
        source_binding_status = "verified"
    elif source_statuses:
        source_binding_status = "not_checked"
    else:
        source_binding_status = "not_applicable"
    return {
        "status": status,
        "results": results,
        "assumption_based": bool(assumption_variables),
        "assumption_variables": assumption_variables,
        "provenance_status": "not_checked" if allowed_evidence_ids is None else "checked",
        "source_binding_status": source_binding_status,
        "validation_errors": errors,
    }
