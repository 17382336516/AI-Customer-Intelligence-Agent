from app.agents.orchestrator import OrchestratorAgent


def test_routes_strategy_questions_to_full_pipeline():
    assert (
        OrchestratorAgent.choose_route("请输出旅行人群的页面方向和 slogan")
        == "full_strategy"
    )


def test_routes_segment_only_questions_without_strategy():
    assert OrchestratorAgent.choose_route("这批用户有哪些人群？仅分群") == "segment_only"


def test_routes_quality_questions_to_quality_gate():
    assert OrchestratorAgent.choose_route("帮我检查字段缺失和数据质量") == "quality_only"

