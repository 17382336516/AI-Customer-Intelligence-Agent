from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

_ALIASES_PATH = Path(__file__).resolve().parents[1] / "category_alias_mapping.json"
_CATEGORY_ALIASES = json.loads(_ALIASES_PATH.read_text(encoding="utf-8"))


def normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower().replace(" ", "")
    for canonical, aliases in _CATEGORY_ALIASES.items():
        candidates = {
            canonical.lower(),
            *(str(alias).strip().lower().replace(" ", "") for alias in aliases),
        }
        if text in candidates or any(alias and alias in text for alias in candidates):
            return canonical
    return text.split(".", 1)[0]


def _resolve_customer_id(value: Any, expected_ids: list[str]) -> str:
    customer_id = str(value or "")
    if customer_id in expected_ids:
        return customer_id
    if customer_id.isdigit():
        index = int(customer_id)
        if 0 <= index < len(expected_ids):
            return expected_ids[index]
    return customer_id


def evaluate(
    data_artifacts: dict[str, Any],
    labels: list[dict[str, str]],
    benchmark_customer_ids: list[str] | None = None,
) -> dict[str, float]:
    expected = {
        str(item.get("customer_id", "")): normalize_category(item.get("category_ground_truth"))
        for item in labels
    }
    expected_ids = sorted(benchmark_customer_ids or expected)
    predictions = {
        _resolve_customer_id(item.get("customer_id"), expected_ids): normalize_category(item.get("predicted_category"))
        for item in data_artifacts.get("user_predictions", [])
    }
    correct = sum(predictions.get(customer_id) == category for customer_id, category in expected.items())
    accuracy = correct / len(expected) if expected else 0.0

    predicted_distribution: Counter[str] = Counter()
    for item in data_artifacts.get("segment_distribution", []):
        predicted_distribution[normalize_category(item.get("category"))] += float(item.get("share", 0) or 0)
    expected_counts = Counter(expected.values())
    expected_total = sum(expected_counts.values()) or 1
    categories = set(predicted_distribution) | set(expected_counts)
    total_variation = 0.5 * sum(
        abs(predicted_distribution[category] - expected_counts[category] / expected_total)
        for category in categories
    )
    distribution_similarity = max(0.0, 1.0 - total_variation)
    data_score = 0.7 * accuracy + 0.3 * distribution_similarity
    return {
        "consumption_preference_accuracy": round(accuracy * 100, 2),
        "distribution_similarity": round(distribution_similarity * 100, 2),
        "data_score": round(data_score * 100, 2),
    }
