from __future__ import annotations

import pandas as pd

from app.agents.data_agent import DataAgent
from app.services.lifecycle_classifier import classify_segment_lifecycle


def test_data_artifacts_keep_real_customer_ids() -> None:
    features = pd.DataFrame(
        {
            "user_id": ["C001", "C002"],
            "main_category_user": ["electronics", "home"],
        }
    )
    artifacts = DataAgent._evaluation_artifacts(features)
    assert [item["customer_id"] for item in artifacts["user_predictions"]] == ["C001", "C002"]


def test_lifecycle_classifier_requires_age_for_young_tag() -> None:
    segment = {
        "segment_id": "cat::electronics",
        "statistics": {
            "average_recency": 20,
            "main_category_ratio": 0.7,
            "category_concentration": 0.6,
        },
    }
    features = pd.DataFrame(
        {
            "main_category_user": ["electronics", "electronics", "home"],
            "total_purchase_amount": [200.0, 300.0, 20.0],
            "avg_order_value": [100.0, 150.0, 10.0],
            "frequency": [2.0, 3.0, 1.0],
        }
    )
    result = classify_segment_lifecycle(segment, features)
    assert "young_growth_user" not in result["lifecycle_tags"]
    assert "high_value_user" in result["lifecycle_tags"]
