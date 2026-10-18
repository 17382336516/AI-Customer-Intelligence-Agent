from __future__ import annotations

from app.agents.strategy_agent import StrategyAgent


def _card(category: str, question: str) -> dict:
    segment = {
        "segment_id": category,
        "name": f"{category}消费者人群",
        "statistics": {
            "main_category": category,
            "average_spend": 1000,
            "average_frequency": 5,
            "overall_average_spend": 1000,
            "overall_average_frequency": 5,
            "average_recency": 10,
            "overall_average_recency": 10,
        },
    }
    return StrategyAgent._base_card(
        segment,
        {},
        "",
        question=question,
    )


def test_campaign_strategy_is_different_by_category():
    question = "哪些用户人群最适合承接下一期专题页或营销活动？请给出差异化策略。"
    coffee = _card("咖啡·beans", question)
    travel = _card("旅行·luggage", question)
    pet = _card("萌宠·cat_food", question)

    assert len({coffee["marketing_goal"], travel["marketing_goal"], pet["marketing_goal"]}) == 3
    assert len({tuple(coffee["channels"]), tuple(travel["channels"]), tuple(pet["channels"])}) == 3
    assert len({tuple(coffee["product_mechanisms"]), tuple(travel["product_mechanisms"]), tuple(pet["product_mechanisms"])}) == 3
    assert "口味" in coffee["marketing_goal"]
    assert "高客单" in travel["marketing_goal"]
    assert "周期" in pet["marketing_goal"]


def test_business_question_changes_the_execution_plan():
    page = _card("旅行·luggage", "针对旅行箱人群设计专题页，包含页面模块、商品组合和指标。")
    push = _card("旅行·luggage", "针对旅行箱人群制定Push策略，包含发送时点、频控、文案和指标。")

    assert page["marketing_goal"] != push["marketing_goal"]
    assert page["channels"] != push["channels"]
    assert page["metrics"] != push["metrics"]
    assert "专题页" in page["marketing_goal"]
    assert "Push" in push["marketing_goal"]
