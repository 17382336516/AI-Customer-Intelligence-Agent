from __future__ import annotations

from typing import Any


FIELDS = (
    "customer_id",
    "age",
    "total_consumption",
    "average_order_value",
    "purchase_frequency",
    "last_purchase_days",
    "category_diversity",
    "coupon_usage",
    "recent_activity",
)


def _number(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def classify_users(customer_features: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Classify users with transparent rules; no category-to-lifecycle inference."""
    numeric = {
        field: [_number(row.get(field)) for row in customer_features]
        for field in FIELDS[1:]
    }
    averages = {
        field: sum(v for v in values if v is not None) / max(1, len([v for v in values if v is not None]))
        for field, values in numeric.items()
    }
    predictions: list[dict[str, Any]] = []
    for row in customer_features:
        tags: list[str] = []
        evidence: list[dict[str, Any]] = []
        total = _number(row.get("total_consumption"))
        aov = _number(row.get("average_order_value"))
        frequency = _number(row.get("purchase_frequency"))
        if all(value is not None and value > averages[field] for field, value in (
            ("total_consumption", total),
            ("average_order_value", aov),
            ("purchase_frequency", frequency),
        )):
            tags.append("high_value_user")
            for field, value in (("total_consumption", total), ("average_order_value", aov), ("purchase_frequency", frequency)):
                evidence.append({"field": field, "value": value, "rule": "above_overall_average"})

        age = _number(row.get("age"))
        activity = _number(row.get("recent_activity"))
        diversity = _number(row.get("category_diversity"))
        exploration = diversity is not None and diversity >= averages.get("category_diversity", 0.0)
        active = activity is not None and activity >= averages.get("recent_activity", 0.0)
        if age is not None and age <= 35 and (active or exploration):
            tags.append("young_growth_user")
            evidence.append({"field": "age", "value": age, "rule": "less_than_or_equal_35"})
            if active:
                evidence.append({"field": "recent_activity", "value": activity, "rule": "above_overall_average"})
            if exploration:
                evidence.append({"field": "category_diversity", "value": diversity, "rule": "exploration_signal"})

        price_evidence: list[dict[str, Any]] = []
        if aov is not None and aov < averages.get("average_order_value", aov):
            price_evidence.append({"field": "average_order_value", "value": aov, "rule": "below_overall_average"})
        coupon = _number(row.get("coupon_usage"))
        if coupon is not None and coupon > averages.get("coupon_usage", coupon):
            price_evidence.append({"field": "coupon_usage", "value": coupon, "rule": "above_overall_average"})
        if price_evidence:
            tags.append("price_sensitive_user")
            evidence.extend(price_evidence)

        recency = _number(row.get("last_purchase_days"))
        if recency is not None and recency > 90 and (total or 0) > 0:
            tags.append("scenario_enhanced_churn_user")
            evidence.append({"field": "last_purchase_days", "value": recency, "rule": "above_90_days_with_history"})

        predictions.append({
            "customer_id": str(row.get("customer_id", "")),
            "lifecycle_tags": tags,
            "lifecycle_evidence": evidence,
        })
    return predictions
