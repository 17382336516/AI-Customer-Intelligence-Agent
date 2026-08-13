from backend.app.services.user_lifecycle_classifier import classify_users


def test_user_level_lifecycle_rules_are_evidence_based():
    rows = [
        {"customer_id": "C1", "age": 25, "total_consumption": 1000, "average_order_value": 100, "purchase_frequency": 10, "last_purchase_days": 10, "category_diversity": 4, "coupon_usage": 0, "recent_activity": 10},
        {"customer_id": "C2", "age": 50, "total_consumption": 100, "average_order_value": 20, "purchase_frequency": 2, "last_purchase_days": 120, "category_diversity": 1, "coupon_usage": 10, "recent_activity": 1},
    ]
    result = {item["customer_id"]: item for item in classify_users(rows)}
    assert "high_value_user" in result["C1"]["lifecycle_tags"]
    assert "young_growth_user" in result["C1"]["lifecycle_tags"]
    assert "scenario_enhanced_churn_user" in result["C2"]["lifecycle_tags"]
    assert result["C2"]["lifecycle_evidence"]
