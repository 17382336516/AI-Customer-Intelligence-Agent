from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base, Repository
from app.workflow import CustomerIntelligenceWorkflow


def _demo_frame() -> pd.DataFrame:
    products = {
        "travel": ("机票", "旅行", 800),
        "tea": ("多肉葡萄", "奶茶", 28),
        "coffee": ("拿铁", "咖啡", 32),
        "home": ("香薰", "家居", 120),
    }
    rows = []
    order = 0
    now = datetime(2026, 7, 29, 12, 0, 0, tzinfo=UTC)
    for persona_index, (_, (product, category, amount)) in enumerate(products.items()):
        for user_index in range(6):
            for purchase_index in range(5):
                order += 1
                rows.append(
                    {
                        "order_id": f"O{order}",
                        "user_id": f"U{persona_index}-{user_index}",
                        "amount": amount + purchase_index,
                        "category": category,
                        "product": product,
                        "event_time": now - timedelta(days=user_index + purchase_index),
                        "status": "paid",
                    }
                )
    return pd.DataFrame(rows)


def test_full_workflow_produces_evidence_backed_strategy_cards(tmp_path):
    path = tmp_path / "demo.csv"
    _demo_frame().to_csv(path, index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        analysis = repository.create_analysis(
            dataset_id="dataset-1",
            question="哪些人群适合做专题页？请给出页面方向和 slogan",
            strategy_goal="产品策略",
            brand_tone="温暖可信",
            route="full_strategy",
        )
        result = CustomerIntelligenceWorkflow(repository).invoke(
            {
                "analysis_id": analysis.id,
                "dataset_id": "dataset-1",
                "dataset_path": str(path),
                "question": analysis.question,
                "strategy_goal": "产品策略",
                "brand_tone": "温暖可信",
                "analysis_window": "全部数据",
                "model_mode": "deterministic",
            }
        )

    assert result["route"] == "full_strategy"
    assert len(result["segments"]) == 4
    assert len(result["strategy_cards"]) == 4
    assert result["evaluation"]["completeness"] == 1.0
    assert all(card["evidence_summary"] for card in result["strategy_cards"])
    assert all(card["validation_metrics"] for card in result["strategy_cards"])


def test_quality_route_stops_before_segmentation(tmp_path):
    path = tmp_path / "demo.csv"
    _demo_frame().to_csv(path, index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        analysis = repository.create_analysis(
            dataset_id="dataset-1",
            question="检查字段缺失和数据质量",
            strategy_goal="",
            brand_tone="",
            route="quality_only",
        )
        result = CustomerIntelligenceWorkflow(repository).invoke(
            {
                "analysis_id": analysis.id,
                "dataset_id": "dataset-1",
                "dataset_path": str(path),
                "question": analysis.question,
                "strategy_goal": "",
                "brand_tone": "",
                "analysis_window": "全部数据",
                "model_mode": "deterministic",
            }
        )

    assert result["route"] == "quality_only"
    assert result["quality"]["can_analyze"] is True
    assert result["segments"] == []
    assert result["insights"] == []
    assert result["strategy_cards"] == []
