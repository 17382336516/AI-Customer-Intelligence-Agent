from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.knowledge_agent import KnowledgeAgent
from app.database import Base, Repository
from app.schemas import AnalysisResult
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
    assert result["evaluation_artifacts"]["data_agent"]["user_predictions"] == []


def test_workflow_emits_evaluation_artifacts(tmp_path):
    path = tmp_path / "demo.csv"
    _demo_frame().to_csv(path, index=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        analysis = repository.create_analysis(
            dataset_id="dataset-1",
            question="请为主要人群生成营销策略",
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
        saved_json = repository.finish_analysis(analysis.id, result).result_json

    artifacts = result["evaluation_artifacts"]
    assert artifacts["schema_version"] == "1.0"
    assert len(artifacts["data_agent"]["user_predictions"]) == 24
    assert sum(
        item["user_count"] for item in artifacts["data_agent"]["segment_distribution"]
    ) == 24
    assert len(artifacts["insight_agent"]["insight_records"]) == len(result["insights"])
    assert len(artifacts["strategy_agent"]["strategy_records"]) == len(result["strategy_cards"])
    assert AnalysisResult.model_validate(result).evaluation_artifacts.schema_version == "1.0"
    assert '"evaluation_artifacts"' in saved_json


def test_knowledge_artifacts_preserve_ranked_internal_sources():
    class StubKnowledgeBase:
        def search(self, *_args, **_kwargs):
            return [
                {
                    "path": "product/bi_bi_zan.md",
                    "source": "https://example.com/bi-bi-zan",
                    "text": "自动小额储蓄降低使用门槛",
                    "score": 0.82,
                    "metadata": {"type": "enterprise"},
                }
            ]

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        repository = Repository(session)
        analysis = repository.create_analysis(
            dataset_id="dataset-1",
            question="如何提升年轻用户转化？",
            strategy_goal="用户增长",
            brand_tone="稳健",
            route="full_strategy",
        )
        result = KnowledgeAgent(repository, StubKnowledgeBase()).run(
            {"analysis_id": analysis.id, "question": analysis.question, "segments": []}
        )

    hit = result["knowledge_agent_artifacts"]["retrieval_results"][0]
    assert hit == {
        "document_source": "product/bi_bi_zan.md",
        "source_reference": "https://example.com/bi-bi-zan",
        "rank": 1,
        "retrieval_score": 0.82,
        "retrieved_content": "自动小额储蓄降低使用门槛",
    }


def test_cached_data_does_not_reuse_cached_insights():
    class StubInsightAgent:
        def run(self, _state):
            return {
                "insights": [{"segment_id": "fresh"}],
                "insight_agent_artifacts": {"insight_records": [{"segment_name": "fresh"}]},
            }

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        workflow = CustomerIntelligenceWorkflow(Repository(session))
        workflow.insight_agent = StubInsightAgent()
        result = workflow._node_insight(
            {
                "analysis_id": "analysis-1",
                "cached_analysis": {"insights": [{"segment_id": "cached"}]},
            }
        )

    assert result["insights"] == [{"segment_id": "fresh"}]
