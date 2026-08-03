from __future__ import annotations

from typing import Any

from ..database import Repository


class OrchestratorAgent:
    """真正的任务规划 Agent（Agent Planning）。

    不再使用固定 workflow：根据用户业务问题动态识别意图（intent），
    决定需要调用哪些 Agent（agents），并给出推理链（reasoning）。
    workflow 依据本 Agent 返回的 plan 动态执行。
    """

    name = "orchestrator"

    # ---- 意图识别关键词（按优先级从上到下匹配）----
    # 1) 数据分析意图：只想知道"用户有哪些类型/分群"。
    ANALYSIS_TERMS = (
        "哪些用户", "客户类型", "用户类型", "人群类型", "有什么人群", "有哪几类",
        "有哪些类型", "有哪些类", "主要有哪些", "有哪些人群", "用户有哪些", "客户有哪些",
        "识别人群", "用户分类", "分群结果", "人群细分", "客户分层", "怎么分群",
        "用户画像", "客户画像", "都是什么人", "用户结构", "客户主要", "人群主要",
    )
    # 2) 市场研究意图：需要结合行业/品类知识或外部基准。
    RESEARCH_TERMS = (
        "行业趋势", "行业", "趋势", "benchmark", "基准", "对标", "竞品",
        "市场", "品类知识", "常识", "最佳实践", "案例", "方法论", "外部",
    )
    # 3) 营销策略意图：需要洞察 + 策略（默认）。
    STRATEGY_TERMS = (
        "策略", "方案", "活动", "营销", "权益", "专题", "页面", "slogan",
        "文案", "产品", "增长", "转化", "推广", "承接", "设计",
    )

    AGENT_LABELS = {
        "insight_agent": "Insight Agent",
        "strategy_agent": "Strategy Agent",
        "knowledge_agent": "Knowledge Agent",
        "data_agent": "Data Agent",
    }

    def __init__(self, repository: Repository):
        self.repository = repository

    # ------------------------------------------------------------------
    # 意图识别
    # ------------------------------------------------------------------
    @classmethod
    def classify_intent(cls, question: str, strategy_goal: str = "") -> str:
        text = f"{question} {strategy_goal}".lower()
        # 数据分析意图优先级最高：明确只问"有哪些类型/画像"。
        if any(term in text for term in cls.ANALYSIS_TERMS) and not any(
            term in text for term in cls.STRATEGY_TERMS
        ):
            return "customer_analysis"
        # 市场研究意图：涉及行业/趋势/基准/知识。
        if any(term in text for term in cls.RESEARCH_TERMS):
            return "market_research"
        # 默认：营销策略意图。
        return "marketing_strategy"

    @classmethod
    def route_for_intent(cls, intent: str) -> str:
        return {
            "customer_analysis": "segment_only",
            "marketing_strategy": "full_strategy",
            "market_research": "full_strategy",
        }.get(intent, "full_strategy")

    # ------------------------------------------------------------------
    # 真正的任务规划：返回 intent / agents / reasoning
    # ------------------------------------------------------------------
    @classmethod
    def plan_task(cls, question: str, strategy_goal: str = "") -> dict[str, Any]:
        intent = cls.classify_intent(question, strategy_goal)

        if intent == "customer_analysis":
            agents = ["InsightAgent"]
            reasoning = (
                "用户问题聚焦在「客户有哪些类型」，只需先做数据分群并生成洞察，"
                "无需生成营销策略，因此仅委派 Insight Agent。"
            )
        elif intent == "market_research":
            agents = ["InsightAgent", "KnowledgeAgent", "StrategyAgent"]
            reasoning = (
                "问题涉及行业/市场/品类知识，需要先分析用户群体（Insight Agent），"
                "再检索企业知识库与外部基准（Knowledge Agent），"
                "最后结合数据洞察与知识生成策略（Strategy Agent）。"
            )
        else:  # marketing_strategy
            agents = ["InsightAgent", "StrategyAgent"]
            reasoning = (
                "需要可执行的营销策略，因此先分析用户群体并生成洞察（Insight Agent），"
                "再基于洞察产出产品机制、页面方向与验证指标（Strategy Agent）。"
            )

        return {
            "intent": intent,
            "agents": agents,
            "reasoning": reasoning,
        }

    # ------------------------------------------------------------------
    # 兼容旧入口：供 main.py 创建分析记录时快速路由
    # ------------------------------------------------------------------
    @classmethod
    def choose_route(cls, question: str, strategy_goal: str = "") -> str:
        return cls.route_for_intent(cls.classify_intent(question, strategy_goal))

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        question = state.get("question", "")
        strategy_goal = state.get("strategy_goal", "")
        plan = self.plan_task(question, strategy_goal)
        intent = plan["intent"]
        agents = plan["agents"]
        route = self.route_for_intent(intent)

        # 委派映射：data_agent 始终需要（分群前置）。
        agent_delegation = {
            "data_agent": True,
            "insight_agent": "InsightAgent" in agents,
            "knowledge_agent": "KnowledgeAgent" in agents,
            "strategy_agent": "StrategyAgent" in agents,
        }

        # 会话上下文摘要（来自 Context Manager，仅引用真实保存的历史数据）
        session_context = state.get("session_context") or {}
        context_note = ""
        if session_context.get("session_name"):
            matched = session_context.get("matched_insight_names") or []
            context_note = (
                f" 已加载分析项目「{session_context.get('session_name')}」的上下文"
                + (f"，关联人群：{', '.join(matched)}" if matched else "（未做人群裁剪）")
                + "。"
            )

        # 人类可读的执行步骤。
        step_plan = [
            "数据读取", "字段校验", "数据清洗", "特征工程",
            "消费趋势分析", "品类偏好分群",
        ]
        if agent_delegation["insight_agent"]:
            step_plan.append("用户洞察生成")
        if agent_delegation["knowledge_agent"]:
            step_plan.append("知识检索支撑")
        if agent_delegation["strategy_agent"]:
            step_plan.extend(["营销策略", "页面方向", "slogan", "结果评估"])
        else:
            step_plan.append("结果评估")

        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "plan_created",
            {
                "intent": intent,
                "agents": agents,
                "reasoning": plan["reasoning"] + context_note,
                "route": route,
                "plan": step_plan,
                "delegation": agent_delegation,
                "session_context_summary": session_context.get("session_name", ""),
            },
        )
        return {
            "intent": intent,
            "agents": agents,
            "reasoning": plan["reasoning"] + context_note,
            "route": route,
            "plan": step_plan,
            "agent_delegation": agent_delegation,
        }
