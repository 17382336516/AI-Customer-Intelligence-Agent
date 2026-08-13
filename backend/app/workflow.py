from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .agents import DataAgent, InsightAgent, KnowledgeAgent, OrchestratorAgent, StrategyAgent
from .database import Repository
from .services.evaluation import evaluate_result


class WorkflowState(TypedDict, total=False):
    analysis_id: str
    dataset_id: str
    dataset_path: str
    question: str
    strategy_goal: str
    brand_tone: str
    analysis_window: str
    session_id: str
    conversation_id: str
    session_context: dict[str, Any]
    cached_analysis: dict[str, Any]
    route: str
    intent: str
    agents: list[str]
    reasoning: str
    plan: list[str]
    agent_delegation: dict[str, bool]
    quality: dict[str, Any]
    cleaning_stats: dict[str, Any]
    category_debug: dict[str, Any]
    category_warning: str | None
    segments: list[dict[str, Any]]
    cluster_quality: dict[str, Any]
    segment_method: str
    income_profile: dict[str, Any]
    overall_consumption_insight: dict[str, Any]
    insights: list[dict[str, Any]]
    strategy_cards: list[dict[str, Any]]
    knowledge_support: dict[str, Any]
    enterprise_context: str
    enterprise_sources: list[str]
    data_agent_artifacts: dict[str, Any]
    insight_agent_artifacts: dict[str, Any]
    knowledge_agent_artifacts: dict[str, Any]
    strategy_agent_artifacts: dict[str, Any]
    agent_trace: list[dict[str, Any]]
    evaluation: dict[str, Any]
    model_mode: str
    blocked: bool
    warnings: list[str]
    executive_summary: str
    _cleaned_df: Any
    _features_df: Any


class CustomerIntelligenceWorkflow:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.orchestrator = OrchestratorAgent(repository)
        self.data_agent = DataAgent(repository)
        self.insight_agent = InsightAgent(repository)
        self.strategy_agent = StrategyAgent(repository)
        self.knowledge_agent = KnowledgeAgent(repository)
        self.graph = self._build()

    # ------------------------------------------------------------------
    # 节点包装：在调用 Agent 后追加结构化执行轨迹（agent_trace）。
    # ------------------------------------------------------------------
    def _trace(self, state: WorkflowState, agent: str, action: str, output: str) -> dict[str, Any]:
        trace = list(state.get("agent_trace") or [])
        trace.append({"agent": agent, "action": action, "output": output})
        # 持久化 Agent Trace 到 messages 表（支持 Workspace 历史追溯）
        session_id = state.get("session_id")
        conversation_id = state.get("conversation_id") or ""
        if session_id:
            self.repository.add_message(
                session_id=session_id,
                conversation_id=conversation_id,
                agent=agent,
                event_type=action,
                payload={"action": action, "output": output},
            )
        return {"agent_trace": trace}

    def _node_orchestrator(self, state: WorkflowState) -> dict[str, Any]:
        result = self.orchestrator.run(state)
        trace = self._trace(
            state, "orchestrator", "规划任务与 Agent 委派",
            f"intent={result.get('intent')}; agents={','.join(result.get('agents', []))}",
        )
        return {**result, **trace}

    def _node_data(self, state: WorkflowState) -> dict[str, Any]:
        # 数据资产复用：若已注入数据集分析缓存，直接读取既有分群/趋势，跳过清洗与重算。
        cached = state.get("cached_analysis")
        cached_evaluation = cached.get("evaluation_artifacts", {}) if cached else {}
        cached_data_artifacts = cached_evaluation.get("data_agent", {})
        if (
            state.get("route") != "quality_only"
            and cached
            and cached.get("segments")
            and cached_data_artifacts.get("user_predictions")
        ):
            trace = self._trace(
                state, "data_agent", "读取数据集分析缓存（复用既有分群与消费趋势）",
                f"segments={len(cached.get('segments', []))}; "
                f"method={cached.get('segment_method')}",
            )
            return {
                "segments": cached.get("segments", []),
                "quality": cached.get("quality", {}),
                "cluster_quality": cached.get("cluster_quality", {}),
                "segment_method": cached.get("segment_method", "category_preference"),
                "income_profile": cached.get("income_profile", {}),
                "overall_consumption_insight": cached.get("overall_consumption_insight", {}),
                "data_agent_artifacts": cached_data_artifacts,
                **trace,
            }
        result = self.data_agent.run(state)
        trace = self._trace(
            state, "data_agent", "读取/清洗/品类偏好分群",
            f"segments={len(result.get('segments', []))}; "
            f"method={result.get('segment_method')}",
        )
        return {**result, **trace}

    def _node_insight(self, state: WorkflowState) -> dict[str, Any]:
        # Insight 与业务问题相关，每次分析都重新执行；仅 Data Agent 资产允许复用。
        result = self.insight_agent.run(state)
        trace = self._trace(
            state, "insight_agent", "生成客户洞察",
            f"insights={len(result.get('insights', []))}",
        )
        return {**result, **trace}

    def _node_knowledge(self, state: WorkflowState) -> dict[str, Any]:
        result = self.knowledge_agent.run(state)
        support = result.get("knowledge_support") or {}
        trace = self._trace(
            state, "knowledge_agent", "检索企业知识",
            f"sources={len(support.get('sources', []))}",
        )
        return {**result, **trace}

    def _node_strategy(self, state: WorkflowState) -> dict[str, Any]:
        result = self.strategy_agent.run(state)
        trace = self._trace(
            state, "strategy_agent", "生成策略卡",
            f"cards={len(result.get('strategy_cards', []))}",
        )
        return {**result, **trace}

    # ------------------------------------------------------------------
    def _build(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("orchestrator", self._node_orchestrator)
        builder.add_node("data_agent", self._node_data)
        builder.add_node("insight_agent", self._node_insight)
        builder.add_node("knowledge_agent", self._node_knowledge)
        builder.add_node("strategy_agent", self._node_strategy)
        builder.add_node("evaluation", self._evaluate)

        builder.add_edge(START, "orchestrator")
        builder.add_edge("orchestrator", "data_agent")

        # 按 Orchestrator 委派动态路由：不再使用固定 workflow。
        builder.add_conditional_edges(
            "data_agent",
            self._after_data,
            {"insight": "insight_agent", "evaluate": "evaluation"},
        )
        builder.add_conditional_edges(
            "insight_agent",
            self._after_insight,
            {
                "knowledge": "knowledge_agent",
                "strategy": "strategy_agent",
                "evaluate": "evaluation",
            },
        )
        builder.add_conditional_edges(
            "knowledge_agent",
            self._after_knowledge,
            {"strategy": "strategy_agent", "evaluate": "evaluation"},
        )
        builder.add_edge("strategy_agent", "evaluation")
        builder.add_edge("evaluation", END)
        return builder.compile()

    @staticmethod
    def _needs(state: WorkflowState, agent: str) -> bool:
        agents = state.get("agents") or []
        mapping = {
            "insight_agent": "InsightAgent",
            "knowledge_agent": "KnowledgeAgent",
            "strategy_agent": "StrategyAgent",
        }
        return mapping.get(agent) in agents

    @staticmethod
    def _after_data(state: WorkflowState) -> str:
        if state.get("blocked") or state.get("route") == "quality_only":
            return "evaluate"
        if CustomerIntelligenceWorkflow._needs(state, "insight_agent"):
            return "insight"
        if CustomerIntelligenceWorkflow._needs(state, "strategy_agent"):
            return "strategy"
        return "evaluate"

    @staticmethod
    def _after_insight(state: WorkflowState) -> str:
        # 洞察之后：若需要知识检索则先知识，否则若需要策略则策略，否则结束。
        if CustomerIntelligenceWorkflow._needs(state, "knowledge_agent"):
            return "knowledge"
        if CustomerIntelligenceWorkflow._needs(state, "strategy_agent"):
            return "strategy"
        return "evaluate"

    @staticmethod
    def _after_knowledge(state: WorkflowState) -> str:
        if CustomerIntelligenceWorkflow._needs(state, "strategy_agent"):
            return "strategy"
        return "evaluate"

    def _evaluate(self, state: WorkflowState) -> dict[str, Any]:
        evaluation = evaluate_result(dict(state))
        segments = state.get("segments", [])
        route = state.get("route", "full_strategy")
        if state.get("blocked"):
            summary = "当前数据质量未达到分析门槛，请先按质量报告补齐字段或修正数据。"
        elif route == "quality_only":
            summary = (
                f"数据可分析性评分为 {state['quality']['analyzability_score']} 分，"
                f"共识别 {state['quality']['user_count']} 位用户。"
            )
        elif route == "segment_only":
            summary = f"已按用户真实消费品类识别 {len(segments)} 类主要人群，并输出品类贡献与消费特征。"
        else:
            summary = (
                f"已识别 {len(segments)} 类主要人群，并生成对应的产品策略、页面方向、"
                "slogan 与验证指标。"
            )
        return {
            "evaluation": evaluation,
            "warnings": evaluation["warnings"],
            "executive_summary": summary,
            "model_mode": state.get("model_mode", "deterministic"),
        }

    def invoke(self, initial_state: WorkflowState) -> dict[str, Any]:
        state = self.graph.invoke(initial_state)
        return {
            "route": state["route"],
            "intent": state.get("intent", ""),
            "reasoning": state.get("reasoning", ""),
            "executive_summary": state["executive_summary"],
            "quality": state["quality"],
            "segments": state.get("segments", []),
            "insights": state.get("insights", []),
            "strategy_cards": state.get("strategy_cards", []),
            "knowledge_support": state.get("knowledge_support", {}),
            "enterprise_context": state.get("enterprise_context", ""),
            "enterprise_sources": state.get("enterprise_sources", []),
            "evaluation": state["evaluation"],
            "cluster_quality": state.get("cluster_quality", {}),
            "segment_method": state.get("segment_method", "category_preference"),
            "income_profile": state.get("income_profile", {}),
            "overall_consumption_insight": state.get("overall_consumption_insight", {}),
            "category_debug": state.get("category_debug", {}),
            "category_warning": state.get("category_warning"),
            "agent_plan": state.get("plan", []),
            "agent_delegation": state.get("agent_delegation", {}),
            "agent_trace": state.get("agent_trace", []),
            "model_mode": state.get("model_mode", "deterministic"),
            "warnings": state.get("warnings", []),
            "evaluation_artifacts": {
                "schema_version": "1.0",
                "data_agent": state.get(
                    "data_agent_artifacts",
                    {"user_predictions": [], "segment_distribution": []},
                ),
                "insight_agent": state.get(
                    "insight_agent_artifacts",
                    {"insight_records": []},
                ),
                "knowledge_agent": state.get(
                    "knowledge_agent_artifacts",
                    {"retrieval_results": []},
                ),
                "strategy_agent": state.get(
                    "strategy_agent_artifacts",
                    {"strategy_records": []},
                ),
            },
        }
