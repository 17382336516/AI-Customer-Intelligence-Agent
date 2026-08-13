from __future__ import annotations

from typing import Any


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _above(value: float | None, average: float | None) -> bool:
    return value is not None and average is not None and value > average


def _evidence(field: str, value: Any, rule: str) -> dict[str, Any]:
    return {"field": field, "value": value, "rule": rule}


def classify_segment_lifecycle(
    segment: dict[str, Any],
    user_features: Any = None,
) -> dict[str, list[dict[str, Any]] | list[str]]:
    """Apply transparent, non-LLM lifecycle rules to one existing segment."""
    stats = segment.get("statistics", {}) or {}
    rows = user_features
    segment_key = str(segment.get("segment_id", "")).removeprefix("cat::")
    if rows is not None and hasattr(rows, "columns") and "main_category_user" in rows.columns:
        segment_rows = rows[rows["main_category_user"].astype(str) == segment_key]
    else:
        segment_rows = None

    tags: list[str] = []
    evidence: list[dict[str, Any]] = []

    def means(field: str) -> tuple[float | None, float | None]:
        if segment_rows is None or field not in segment_rows.columns:
            return None, None
        segment_value = _number(segment_rows[field].mean())
        overall_value = _number(rows[field].mean()) if field in rows.columns else None
        return segment_value, overall_value

    total, overall_total = means("total_purchase_amount")
    aov, overall_aov = means("avg_order_value")
    frequency, overall_frequency = means("frequency")
    if (
        _above(total, overall_total)
        and _above(aov, overall_aov)
        and _above(frequency, overall_frequency)
    ):
        tags.append("high_value_user")
        evidence.extend(
            [
                _evidence("total_consumption", total, "above_average"),
                _evidence("average_order_value", aov, "above_average"),
                _evidence("purchase_frequency", frequency, "above_average"),
            ]
        )

    age, _overall_age = means("age")
    if age is not None and age <= 30:
        tags.append("young_growth_user")
        evidence.append(_evidence("age", age, "less_than_or_equal_30"))

    coupon, overall_coupon = means("coupon_usage")
    promotion, overall_promotion = means("promotion_behavior")
    price_evidence: list[dict[str, Any]] = []
    if aov is not None and overall_aov is not None and aov < overall_aov:
        price_evidence.append(_evidence("average_order_value", aov, "below_average"))
    if _above(coupon, overall_coupon):
        price_evidence.append(_evidence("coupon_usage", coupon, "above_average"))
    if _above(promotion, overall_promotion):
        price_evidence.append(_evidence("promotion_behavior", promotion, "above_average"))
    if price_evidence:
        tags.append("price_sensitive_user")
        evidence.extend(price_evidence)

    concentration = _number(stats.get("category_concentration"))
    main_share = _number(stats.get("main_category_ratio"))
    if (main_share is not None and main_share >= 0.5) or (
        concentration is not None and main_share is not None and main_share >= 0.4
    ):
        tags.append("category_interest_user")
        evidence.extend(
            [
                _evidence("category_concentration", concentration, "high_concentration"),
                _evidence("main_category_share", main_share, "high_main_category_share"),
            ]
        )

    recency = _number(stats.get("average_recency"))
    if recency is not None and recency > 90:
        tags.append("scenario_enhanced_churn_user")
        evidence.append(_evidence("last_purchase_days", recency, "above_90_days_scenario_enhanced"))

    return {"lifecycle_tags": tags, "lifecycle_evidence": evidence}
