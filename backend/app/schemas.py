from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class QualityIssue(BaseModel):
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    field: str | None = None


class QualityReport(BaseModel):
    row_count: int
    usable_row_count: int
    user_count: int
    analyzability_score: int = Field(ge=0, le=100)
    field_mapping: dict[str, str]
    missing_rates: dict[str, float]
    category_coverage: float
    issues: list[QualityIssue]
    can_analyze: bool


class DatasetPreviewInsight(BaseModel):
    title: str
    summary: str
    evidence: list[str]


class DatasetTopProduct(BaseModel):
    name: str
    count: int


class IncomeBand(BaseModel):
    label: str
    share: float


class IncomeProfile(BaseModel):
    available: bool = False
    average_income: float | None = None
    median_income: float | None = None
    high_income_share: float | None = None
    income_bands: list[IncomeBand] = []
    note: str = ""


class CategoryContribution(BaseModel):
    category: str
    category_cn: str
    spend: float = 0.0
    spend_share: float = 0.0
    user_count: int = 0
    user_share: float = 0.0


class RecentActivityPattern(BaseModel):
    last_event_days_ago: int = 0
    recent_30d_event_share: float = 0.0
    peak_hours: list[int] = []
    high_ticket_category: str | None = None
    high_ticket_category_value: float | None = None


class OverallConsumptionInsight(BaseModel):
    available: bool = False
    summary: str = ""
    top_categories: list[CategoryContribution] = []
    category_spend_distribution: list[CategoryContribution] = []
    category_user_distribution: list[CategoryContribution] = []
    recent_activity_pattern: RecentActivityPattern = RecentActivityPattern()
    segment_count: int = 0


class DatasetPreview(BaseModel):
    sample_row_count: int = 0
    segments: list[dict[str, Any]] = []
    insights: list[DatasetPreviewInsight] = []
    top_products: list[DatasetTopProduct] = []
    date_range: str = ""
    avg_order_value: float = 0.0
    total_amount: float = 0.0
    income_profile: IncomeProfile = IncomeProfile()
    overall_consumption_insight: OverallConsumptionInsight = OverallConsumptionInsight()


class DatasetResponse(BaseModel):
    id: str
    name: str
    display_name: str = ""
    file_type: str
    row_count: int
    quality: QualityReport
    created_at: datetime
    preview: DatasetPreview | None = None
    record_count: int = 0


class DatasetAssetResponse(BaseModel):
    """数据集级分析资产：沉淀一次完整客户洞察后供所有业务问题复用的基础结果。"""
    dataset_id: str
    dataset_name: str = ""
    quality: dict[str, Any] = {}
    segments: list[dict[str, Any]] = []
    insights: list[dict[str, Any]] = []
    overall_consumption_insight: dict[str, Any] = {}
    income_profile: dict[str, Any] = {}
    cluster_quality: dict[str, Any] = {}
    segment_method: str = "category_preference"
    has_asset: bool = False


class EvidenceItem(BaseModel):
    metric: str
    value: str
    benchmark: str = ""
    interpretation: str


class AnalysisCreate(BaseModel):
    dataset_id: str
    question: str = Field(min_length=2, max_length=1000)
    strategy_goal: str = Field(default="", max_length=255)
    brand_tone: str = Field(default="", max_length=255)
    analysis_window: str = Field(default="全部数据", max_length=100)

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        cleaned = (value or "").strip()
        # 拒绝空白、纯问号或纯标点（无实际业务语义）的问题，避免脏数据入库
        if not cleaned or not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in cleaned):
            raise ValueError("业务问题不能为空或仅包含标点/问号，请填写有效的业务问题。")
        return cleaned

class SegmentResult(BaseModel):
    segment_id: str
    cluster_id: int | None = None
    name: str
    user_count: int
    share: float
    income_profile: IncomeProfile = IncomeProfile()
    statistics: dict[str, Any] = {}
    key_features: list[str]
    evidence: list[EvidenceItem]
    recommended_strategy: str = ""
    rule_basis: list[str]
    opportunity_score: float = 0.0
    opportunity_level: str = "low"
    opportunity_reason: list[str] = []


class InterestProfile(BaseModel):
    """兴趣分级（约束：仅来自真实数据，禁止无依据扩展）。

    - direct_interests：直接关联兴趣，来源为用户实际购买品类 / 品牌。
    - behavior_interests：行为推断兴趣，来源为消费模式（高频、高客单等），
      不指向具体未购买的生活方式标签。
    """
    direct_interests: list[str] = []
    behavior_interests: list[str] = []


class InsightResult(BaseModel):
    segment_id: str
    segment_name: str
    segment_size: int = 0
    income_profile: IncomeProfile = IncomeProfile()
    top_tags: list[str] = []
    persona_tags: list[str] = []
    profile: str = ""
    predicted_interests: list[str] = []
    interests: list[str] = []
    interest_profile: InterestProfile = InterestProfile()
    value_tier: str = ""
    behavior_profile: list[str] = []
    consumption_features: list[str] = []
    category_preference: list[str] = []
    brand_preference: list[str] = []
    motivation: str
    needs: list[str]
    trend_explanation: str
    decision_implications: list[str] = []
    recommended_actions: list[str] = []
    alternative_explanations: list[str]
    limitations: list[str]


class PageDirection(BaseModel):
    theme: str
    visual_keywords: list[str]
    modules: list[str]
    hero_title: str
    hero_subtitle: str
    emotional_direction: str


class StrategyBasis(BaseModel):
    data: list[str] = []
    knowledge: list[str] = []


class StrategyCard(BaseModel):
    segment_id: str
    segment_name: str
    opportunity: str
    # ---- 完整营销方案字段（增量新增，向后兼容）----
    target_positioning: str = ""
    marketing_goal: str = ""
    content_strategy: str = ""
    product_strategy: str = ""
    promotion_strategy: str = ""
    marketing_direction: str = ""
    ad_theme: str = ""
    ad_elements: list[str] = []
    recommended_products: list[str] = []
    channels: list[str] = []
    # metrics：效果衡量指标（与 validation_metrics 并存，前者为完整方案字段）
    metrics: list[str] = []
    strategy_basis: StrategyBasis = StrategyBasis()
    product_mechanisms: list[str]
    benefits: list[str]
    page: PageDirection
    slogans: list[str]
    validation_metrics: list[str]
    evidence_summary: list[str]
    limitations: list[str]


class EvaluationResult(BaseModel):
    completeness: float
    evidence_coverage: float
    strategy_actionability: float
    differentiation: float
    warnings: list[str]


class DataAgentEvaluationArtifacts(BaseModel):
    user_predictions: list[dict[str, Any]] = []
    segment_distribution: list[dict[str, Any]] = []


class InsightAgentEvaluationArtifacts(BaseModel):
    insight_records: list[dict[str, Any]] = []


class KnowledgeAgentEvaluationArtifacts(BaseModel):
    retrieval_results: list[dict[str, Any]] = []


class StrategyAgentEvaluationArtifacts(BaseModel):
    strategy_records: list[dict[str, Any]] = []
    human_review_template: dict[str, Any] = {}


class EvaluationArtifacts(BaseModel):
    schema_version: str = "1.0"
    data_agent: DataAgentEvaluationArtifacts = DataAgentEvaluationArtifacts()
    insight_agent: InsightAgentEvaluationArtifacts = InsightAgentEvaluationArtifacts()
    knowledge_agent: KnowledgeAgentEvaluationArtifacts = KnowledgeAgentEvaluationArtifacts()
    strategy_agent: StrategyAgentEvaluationArtifacts = StrategyAgentEvaluationArtifacts()


class AnalysisResult(BaseModel):
    route: Literal["quality_only", "segment_only", "full_strategy"]
    intent: str = ""
    reasoning: str = ""
    executive_summary: str
    quality: QualityReport
    segments: list[SegmentResult] = []
    insights: list[InsightResult] = []
    strategy_cards: list[StrategyCard] = []
    knowledge_support: dict[str, Any] = {}
    evaluation: EvaluationResult
    cluster_quality: dict[str, Any] = {}
    segment_method: str = "category_preference"
    category_debug: dict[str, Any] = {}
    category_warning: str | None = None
    overall_consumption_insight: OverallConsumptionInsight = OverallConsumptionInsight()
    income_profile: IncomeProfile = IncomeProfile()
    agent_plan: list[str] = []
    agent_delegation: dict[str, bool] = {}
    agent_trace: list[dict[str, Any]] = []
    model_mode: Literal["deterministic", "llm_enhanced"]
    warnings: list[str] = []
    evaluation_artifacts: EvaluationArtifacts = EvaluationArtifacts()


class AnalysisResponse(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str = ""
    question: str
    status: str
    route: str
    result: AnalysisResult | dict[str, Any]
    error_message: str
    created_at: datetime
    updated_at: datetime


class AuditEventResponse(BaseModel):
    agent: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


# ----------------------------------------------------------------------
# Analysis Workspace：分析项目 / 会话历史 / 继续分析
# ----------------------------------------------------------------------
class SessionSummary(BaseModel):
    segment_count: int = 0
    insight_count: int = 0
    strategy_count: int = 0
    conversation_count: int = 0


class SessionResponse(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str = ""
    name: str
    status: str
    summary: str
    created_at: datetime
    updated_at: datetime
    stats: SessionSummary = SessionSummary()
    question: str = ""


class ConversationResponse(BaseModel):
    id: str
    session_id: str
    analysis_id: str
    question: str
    answer_summary: str
    insight_result: list[dict[str, Any]] = []
    strategy_result: list[dict[str, Any]] = []
    agent_trace: list[dict[str, Any]] = []
    created_at: datetime


class MessageResponse(BaseModel):
    id: str
    session_id: str
    conversation_id: str
    agent: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class SessionDetailResponse(BaseModel):
    session: SessionResponse
    conversations: list[ConversationResponse] = []
    messages: list[MessageResponse] = []


class ContinueAnalysisCreate(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    strategy_goal: str = Field(default="", max_length=255)
    brand_tone: str = Field(default="", max_length=255)
    analysis_window: str = Field(default="全部数据", max_length=100)

    @field_validator("question")
    @classmethod
    def _validate_question(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned or not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in cleaned):
            raise ValueError("业务问题不能为空或仅包含标点/问号，请填写有效的业务问题。")
        return cleaned
