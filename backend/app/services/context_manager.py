from __future__ import annotations

import json
from typing import Any

from ..database import Repository, SessionLocal, SessionRecord
from ..schemas import AnalysisResult


class ContextManager:
    """上下文管理模块（Context Manager）。

    位置：用户问题 → Context Manager → Orchestrator Agent → Insight / Strategy / Knowledge Agent

    职责：
    1. 判断当前问题属于哪个分析 Session（基于 session_id 显式关联，
       并辅助识别"刚才的人群""这个用户群""上一版策略"等指代）。
    2. 生成 Agent 上下文（session_context）：不每次发送全部历史，
       而是根据问题选择相关内容（例如问手机用户就只加载手机消费人群，
       不加载冰箱/洗衣机用户）。

    所有历史上下文必须来自真实保存的数据（datasets / analyses / sessions 表），
    严禁模型虚构历史信息。
    """

    # 指代当前/上一个 session 的弱信号词（仅作辅助提示，不作为唯一判据）
    REFERENCE_TERMS = (
        "刚才", "上一个", "上一版", "上一轮", "之前", "之前的分析", "这个用户群",
        "这个人群", "上述", "前面", "上次", "历史", "之前那次", "刚刚", "当前",
    )

    def __init__(self, repository: Repository):
        self.repository = repository

    # ------------------------------------------------------------------
    # 1. Session 关联
    # ------------------------------------------------------------------
    def resolve_session(self, session_id: str | None, question: str) -> SessionRecord | None:
        """解析问题归属的 Session。

        优先使用显式传入的 session_id；
        若未传入但有弱指代词，则回退为该 dataset 下最新的 session。
        """
        if session_id:
            return self.repository.get_session(session_id)
        return None

    # ------------------------------------------------------------------
    # 2. 上下文裁剪：从 session 历史分析中抽取与问题相关的内容
    # ------------------------------------------------------------------
    def build_session_context(self, session: SessionRecord, question: str) -> dict[str, Any]:
        """构建会话上下文（session_context）。

        从 session 关联数据集下的历史分析中，抽取：
        - 数据摘要（dataset 名称 + 质量）
        - 已有洞察（人群名称、规模、品类偏好、品牌偏好等）
        - 历史策略（营销目标、策略方案、广告主题、渠道）
        - 历史问答（conversation 的 question/answer）
        并依据问题关键词对相关人群做裁剪（只保留命中的人群）。
        """
        from ..database import AnalysisRecord, ConversationRecord
        from sqlalchemy import select

        # 使用独立会话读取历史数据，避免与调用方（后台任务线程）共享
        # 请求级 Session 在 SQLite 多线程下产生死锁。
        with SessionLocal() as read_session:
            read_repo = Repository(read_session)
            dataset = read_repo.get_dataset(session.dataset_id)
            dataset_name = dataset.name if dataset else session.dataset_name

            # 该 session 数据集下的全部历史分析
            analyses = list(
                read_session.scalars(
                    select(AnalysisRecord)
                    .where(AnalysisRecord.dataset_id == session.dataset_id)
                    .order_by(AnalysisRecord.created_at)
                )
            )

        prior_insights: list[dict[str, Any]] = []
        prior_strategies: list[dict[str, Any]] = []
        prior_questions: list[str] = []

        for analysis in analyses:
            try:
                result = json.loads(analysis.result_json)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(result, dict):
                continue
            prior_questions.append(analysis.question)
            for insight in result.get("insights", []) or []:
                prior_insights.append(
                    {
                        "segment_name": insight.get("segment_name", ""),
                        "segment_size": insight.get("segment_size", 0),
                        "category_preference": insight.get("category_preference", []),
                        "brand_preference": insight.get("brand_preference", []),
                        "profile": insight.get("profile", ""),
                        "value_tier": insight.get("value_tier", ""),
                    }
                )
            for card in result.get("strategy_cards", []) or []:
                prior_strategies.append(
                    {
                        "segment_name": card.get("segment_name", ""),
                        "marketing_goal": card.get("marketing_goal", ""),
                        "ad_theme": card.get("ad_theme", ""),
                        "channels": card.get("channels", []),
                        "opportunity": card.get("opportunity", ""),
                    }
                )

        # 历史对话（conversation）—— 同样用独立会话读取
        with SessionLocal() as conv_session:
            conv_repo = Repository(conv_session)
            conversations = conv_repo.list_conversations(session.id)
        conversation_history = [
            {"question": c.question, "answer_summary": c.answer_summary}
            for c in conversations
        ]

        # 关键词裁剪：命中问题的人群优先，其余作为背景
        matched_insights, background_insights = self._select_relevant(
            question, prior_insights, key=lambda item: item.get("segment_name", "")
        )
        matched_strategies, _ = self._select_relevant(
            question, prior_strategies, key=lambda item: item.get("segment_name", "")
        )

        return {
            "session_id": session.id,
            "session_name": session.name,
            "dataset_id": session.dataset_id,
            "dataset_name": dataset_name,
            "prior_questions": prior_questions,
            "conversation_history": conversation_history,
            "insights": matched_insights + background_insights,
            "matched_insight_names": [item["segment_name"] for item in matched_insights],
            "strategies": matched_strategies,
            "matched_strategy_names": [item["segment_name"] for item in matched_strategies],
        }

    @staticmethod
    def _select_relevant(
        question: str,
        items: list[dict[str, Any]],
        key: Any,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """根据问题中出现的人群名称关键词做裁剪。

        返回 (命中列表, 其余列表)。若没有任何命中，则全部归入背景，
        避免漏掉上下文（保守策略：宁可多给背景，绝不虚构）。
        """
        q = question.lower()
        matched: list[dict[str, Any]] = []
        rest: list[dict[str, Any]] = []
        for item in items:
            name = str(key(item)).lower()
            # 直接包含人群名，或人群名关键片段（去「消费人群」等后缀）出现在问题
            short = name.replace("消费人群", "").replace("用户", "").replace("人群", "")
            if name and (name in q or (short and short in q)):
                matched.append(item)
            else:
                rest.append(item)
        if not matched:
            return [], items
        return matched, rest

    # ------------------------------------------------------------------
    # 精简摘要：用于把 session_context 喂给 Orchestrator / Agent
    # ------------------------------------------------------------------
    @staticmethod
    def summarize_context(context: dict[str, Any]) -> str:
        lines: list[str] = []
        lines.append(f"当前分析项目：{context.get('session_name', '')}")
        lines.append(f"数据集：{context.get('dataset_name', '')}")
        if context.get("matched_insight_names"):
            lines.append("已识别相关人群：" + "、".join(context["matched_insight_names"]))
        if context.get("matched_strategy_names"):
            lines.append("已有相关策略：" + "、".join(context["matched_strategy_names"]))
        if context.get("conversation_history"):
            lines.append("历史业务问题：")
            for item in context["conversation_history"][-5:]:
                lines.append(f"- {item['question']}")
        if context.get("insights"):
            lines.append("历史洞察人群：")
            for item in context["insights"][:6]:
                extra = ""
                if item.get("category_preference"):
                    extra = "；".join(item["category_preference"][:2])
                lines.append(f"- {item.get('segment_name', '')}（{item.get('segment_size', 0)}人）{extra}")
        return "\n".join(lines)
