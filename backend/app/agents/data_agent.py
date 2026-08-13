from __future__ import annotations

from typing import Any

import pandas as pd

from ..database import Repository
from ..services.data_tools import (
    analyze_file,
    build_quality_report,
    read_dataset,
    normalize_category,
    user_category_score_details,
)
from ..services.user_lifecycle_classifier import FIELDS, classify_users


class DataAgent:
    name = "data_agent"

    def __init__(self, repository: Repository):
        self.repository = repository

    @staticmethod
    def _evaluation_artifacts(features: Any) -> dict[str, Any]:
        if (
            features is None
            or "main_category_user" not in features.columns
            or "user_id" not in features.columns
        ):
            return {
                "user_predictions": [],
                "segment_distribution": [],
                "customer_features": [],
                "customer_lifecycle_predictions": [],
            }

        score_details = user_category_score_details(features)

        predictions = [
            {
                "customer_id": str(customer_id),
                "predicted_category": normalize_category(detail["predicted_category"]),
                "confidence": detail["confidence"],
                "evidence": detail["evidence"],
            }
            for customer_id, detail in zip(
                features["user_id"], score_details, strict=False
            )
        ]
        normalized_categories = [item["predicted_category"] for item in predictions]
        counts = pd.Series(normalized_categories, dtype=object).value_counts(dropna=False)
        total = len(features) or 1
        distribution = [
            {
                "category": category if isinstance(category, str) else "",
                "user_count": int(count),
                "share": round(int(count) / total, 4),
            }
            for category, count in counts.items()
        ]
        customer_features: list[dict[str, Any]] = []
        for _, row in features.iterrows():
            item: dict[str, Any] = {"customer_id": str(row.get("user_id", ""))}
            for field in FIELDS[1:]:
                source = {
                    "age": "age",
                    "total_consumption": "total_purchase_amount",
                    "average_order_value": "average_purchase_value",
                    "purchase_frequency": "purchase_order_count",
                    "last_purchase_days": "recency_days",
                    "category_diversity": "unique_category_count",
                    "coupon_usage": "coupon_usage",
                    "recent_activity": "active_days",
                }[field]
                value = row.get(source)
                item[field] = None if value is None else (float(value) if isinstance(value, (int, float)) else value)
            customer_features.append(item)
        lifecycle_predictions = classify_users(customer_features)
        return {
            "user_predictions": predictions,
            "segment_distribution": distribution,
            "customer_features": customer_features,
            "customer_lifecycle_predictions": lifecycle_predictions,
        }

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "tool_started",
            {"tool": "data_quality_and_segmentation"},
        )
        if state.get("route") == "quality_only":
            quality = build_quality_report(read_dataset(state["dataset_path"]))
            self.repository.add_event(
                state["analysis_id"],
                self.name,
                "tool_completed",
                {
                    "quality_score": quality["analyzability_score"],
                    "can_analyze": quality["can_analyze"],
                    "segment_count": 0,
                    "cleaning_stats": {},
                },
            )
            return {
                "quality": quality,
                "segments": [],
                "cleaning_stats": {},
                "data_agent_artifacts": {
                    "user_predictions": [],
                    "segment_distribution": [],
                    "customer_features": [],
                    "customer_lifecycle_predictions": [],
                },
                "blocked": not quality["can_analyze"],
            }

        output = analyze_file(state["dataset_path"])
        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "tool_completed",
            {
                "quality_score": output.quality["analyzability_score"],
                "can_analyze": output.quality["can_analyze"],
                "segment_count": len(output.segments),
                "cleaning_stats": output.cleaning_stats,
            },
        )
        return {
            "quality": output.quality,
            "segments": output.segments,
            "cluster_quality": output.cluster_quality,
            "segment_method": output.segment_method,
            "category_debug": output.category_debug,
            "category_warning": output.category_warning,
            "income_profile": output.income_profile,
            "overall_consumption_insight": output.overall_consumption_insight,
            "_cleaned_df": output.cleaned,
            "_features_df": output.features,
            "cleaning_stats": output.cleaning_stats,
            "data_agent_artifacts": self._evaluation_artifacts(output.features),
            "blocked": not output.quality["can_analyze"],
        }
