import pandas as pd

from app.agents.data_agent import DataAgent
from app.services.data_tools import user_category_score_details


def _features(categories):
    values = {"user_id": ["C001"]}
    for category, amount in categories.items():
        values[f"{category}_purchase_amount"] = [amount]
        values[f"{category}_weighted"] = [amount]
        values[f"{category}_share"] = [amount / sum(categories.values())]
        values[f"{category}_recent_share"] = [amount / sum(categories.values())]
    values["main_category_user"] = [next(iter(categories))]
    return pd.DataFrame(values)


def test_single_category_prediction():
    for category in ("electronics", "beauty", "apparel"):
        result = user_category_score_details(_features({category: 100.0}))[0]
        assert result["predicted_category"] == category


def test_multi_category_prediction_keeps_score_logic():
    result = user_category_score_details(
        _features({"electronics": 80.0, "beauty": 20.0})
    )[0]
    assert result["predicted_category"] in {"electronics", "beauty"}


def test_category_score_emits_confidence_and_evidence():
    features = pd.DataFrame(
        {
            "user_id": ["C001"],
            "electronics.mobile_weighted": [80.0],
            "electronics.mobile_share": [0.5],
            "electronics.mobile_recent_share": [0.2],
            "beauty_weighted": [20.0],
            "beauty_share": [0.5],
            "beauty_recent_share": [0.8],
            "main_category_user": ["electronics.mobile"],
        }
    )
    detail = user_category_score_details(features)[0]
    assert detail["predicted_category"] == "electronics.mobile"
    assert 0 <= detail["confidence"] <= 1
    assert any("消费金额占比" in item for item in detail["evidence"])

    artifact = DataAgent._evaluation_artifacts(features)
    prediction = artifact["user_predictions"][0]
    assert prediction["customer_id"] == "C001"
    assert prediction["predicted_category"] == "electronics"
    assert "confidence" in prediction and "evidence" in prediction
    assert "segment_distribution" in artifact
