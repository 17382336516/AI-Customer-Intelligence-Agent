from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any

from .data_evaluator import normalize_category

_FIELD_ALIASES = {
    "category_preference": "product_category",
    "average_spend": "total_consumption",
    "average_frequency": "purchase_frequency",
    "average_recency": "last_purchase_days",
    "average_income": "income",
}


def _text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _canonical_segment(value: Any, aliases: dict[str, list[str]]) -> str:
    normalized = _text(value)
    for canonical, names in aliases.items():
        candidates = {_text(canonical), *(_text(name) for name in names)}
        if normalized in candidates or any(name and name in normalized for name in candidates):
            return canonical
    return normalized


def _record_segment_signals(record: dict[str, Any]) -> list[str]:
    values: list[Any] = [record.get("segment_name"), record.get("value_tier")]
    for field in ("lifecycle_tags", "top_tags", "behavior_profile", "recommended_actions"):
        value = record.get(field, [])
        values.extend(value if isinstance(value, list) else [value])
    values.extend([record.get("profile"), record.get("insight_text")])
    return [str(value) for value in values if value not in (None, "")]


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _close(actual: Any, expected: float) -> bool:
    value = _number(actual)
    return value is not None and abs(value - expected) <= max(abs(expected) * 0.05, 0.01)


def _customer_rows(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {str(row.get("customer_id", "")): row for row in rows}


def _expected_statistics(
    rows: list[dict[str, str]], data_artifacts: dict[str, Any]
) -> tuple[dict[str, dict[str, float]], set[str]]:
    customers = _customer_rows(rows)
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for item in data_artifacts.get("user_predictions", []):
        customer = customers.get(str(item.get("customer_id", "")))
        if customer:
            grouped[normalize_category(item.get("predicted_category"))].append(customer)

    mapping = {
        "average_spend": "total_consumption",
        "average_frequency": "purchase_frequency",
        "average_recency": "last_purchase_days",
        "average_income": "income",
    }
    result: dict[str, dict[str, float]] = {}
    for category, users in grouped.items():
        values: dict[str, float] = {}
        for output_field, input_field in mapping.items():
            numbers = [_number(user.get(input_field)) for user in users]
            available = [number for number in numbers if number is not None]
            if available:
                values[output_field] = mean(available)
        result[category] = values
    return result, set(rows[0]) if rows else set()


def evaluate(
    insight_artifacts: dict[str, Any],
    golden: dict[str, Any],
    aliases: dict[str, list[str]],
    benchmark_rows: list[dict[str, str]],
    data_artifacts: dict[str, Any],
) -> dict[str, Any]:
    records = insight_artifacts.get("insight_records", [])
    expected_segments = {_canonical_segment(item, aliases) for item in golden.get("expected_segments", [])}
    recognized: set[str] = set()
    for record in records:
        signals = _record_segment_signals(record)
        for canonical in expected_segments:
            if any(_canonical_segment(signal, aliases) == canonical for signal in signals):
                recognized.add(canonical)
    segment_rate = len(recognized) / len(expected_segments) if expected_segments else 1.0

    expected_stats, available_fields = _expected_statistics(benchmark_rows, data_artifacts)
    record_scores: list[float] = []
    for record in records:
        checks: list[bool] = []
        for field in record.get("evidence_fields", []):
            checks.append(_FIELD_ALIASES.get(str(field), str(field)) in available_fields)

        reference = record.get("statistics_reference", {}) or {}
        category = normalize_category(reference.get("main_category"))
        if reference.get("main_category") not in (None, ""):
            checks.append(category in expected_stats)
        for field in ("average_spend", "average_frequency", "average_recency", "average_income"):
            if reference.get(field) in (None, ""):
                continue
            expected = expected_stats.get(category, {}).get(field)
            checks.append(expected is not None and _close(reference.get(field), expected))
        record_scores.append(sum(checks) / len(checks) if checks else 0.0)

    grounding_rate = mean(record_scores) if record_scores else 0.0
    insight_score = 0.4 * segment_rate + 0.6 * grounding_rate
    return {
        "segment_recognition_rate": round(segment_rate * 100, 2),
        "insight_grounding_rate": round(grounding_rate * 100, 2),
        "insight_score": round(insight_score * 100, 2),
    }
