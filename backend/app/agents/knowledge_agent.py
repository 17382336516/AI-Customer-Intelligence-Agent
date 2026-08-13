from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config import settings
from ..database import Repository
from ..services.knowledge_base import KnowledgeBase

_INTENT_PATH = Path(__file__).resolve().parents[3] / "evaluation" / "business_intent_mapping.json"

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    """RAG 知识检索 Agent。

    职责：根据业务问题与人群画像（segment_profile）检索知识库，
    输出可解释的知识上下文（context）、企业专属上下文（enterprise_context）
    与来源（sources）。

    知识库为本地文件（markdown / txt / json），通过可替换的向量检索实现。
    当前默认使用 TF-IDF + 余弦相似度（无需额外依赖）；若后续引入
    sentence-transformers / FAISS / Chroma，只需替换 KnowledgeBase 的
    embed 实现即可，本 Agent 逻辑不变。

    知识来源区分：
    - 用户消费知识（User Data）：来自 settings.knowledge_dir
    - 企业知识（Enterprise Knowledge）：来自 settings.enterprise_knowledge_dir
      带 metadata: type=enterprise, company, product, category, source
    """

    name = "knowledge_agent"

    def __init__(self, repository: Repository, knowledge_base: KnowledgeBase | None = None):
        self.repository = repository
        roots = [
            root
            for root in (settings.knowledge_dir, settings.enterprise_knowledge_dir)
            if root and Path(root).exists()
        ]
        self.kb = knowledge_base or KnowledgeBase(roots)

    @staticmethod
    def _summarize_segments(segments: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for segment in segments[:3]:
            stats = segment.get("statistics", {}) or {}
            name = segment.get("name", "")
            dominant = stats.get("main_category") or stats.get("dominant_category")
            spend = stats.get("average_spend")
            freq = stats.get("average_frequency")
            parts = [f"人群「{name}」"]
            if dominant:
                parts.append(f"主品类={dominant}")
            if isinstance(spend, (int, float)):
                parts.append(f"人均消费={spend}")
            if isinstance(freq, (int, float)):
                parts.append(f"购买频次={freq}")
            lines.append("；".join(parts))
        return "\n".join(lines)

    @staticmethod
    def _format_hit(hit: dict[str, Any]) -> str:
        meta = hit.get("metadata", {}) or {}
        prefix = f"【来源 {hit['source']}"
        if meta.get("category"):
            prefix += f" | 类别:{meta['category']}"
        if meta.get("company"):
            prefix += f" | 企业:{meta['company']}"
        prefix += "】"
        return f"{prefix}\n{hit['text']}"

    @staticmethod
    def _route_intent(question: str) -> tuple[str, list[str], list[str]]:
        try:
            mapping = json.loads(_INTENT_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            mapping = {}
        if any(t in question for t in ("城市", "非一线", "信任")):
            intent = "young_user_growth"
            preferred_types = ["brand", "marketing_case", "user_growth", "product"]
            preferred_goals = ["young_user_growth", "activation"]
            return intent, preferred_types, preferred_goals
        if any(t in question for t in ("召回", "沉默", "未购", "流失")):
            intent = "user_recall"
        elif any(t in question for t in ("活动", "618", "春节", "周年")):
            intent = "activity_operation"
        elif any(t in question for t in ("新品", "冷启动", "尝试门槛")):
            intent = "young_user_growth"
        elif any(t in question for t in ("推荐", "品类")):
            intent = "product_recommendation"
        elif any(t in question for t in ("复购", "会员", "留存")):
            intent = "retention"
        else:
            intent = "young_user_growth"
        spec = mapping.get(intent, {})
        return intent, list(spec.get("document_types", [])), list(spec.get("business_goals", []))

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        question = state.get("question", "")
        segments = state.get("segments", []) or []
        segment_profile = self._summarize_segments(segments)
        intent, preferred_types, preferred_goals = self._route_intent(question)
        expand = getattr(self.kb, "_route_and_expand", lambda value: ([], []))
        _, expanded_terms = expand(question)

        try:
            hits = self.kb.search(
                question,
                segment_profile=segment_profile,
                top_k=6,
                preferred_document_types=preferred_types,
                preferred_business_goals=preferred_goals,
            )
        except Exception as exc:  # 检索失败不应阻断主流程
            logger.warning("Knowledge retrieval failed: %s", exc)
            hits = []

        enterprise_hits = [h for h in hits if (h.get("metadata", {}) or {}).get("type") == "enterprise"]
        user_hits = [h for h in hits if (h.get("metadata", {}) or {}).get("type") != "enterprise"]

        context = "\n\n".join(self._format_hit(h) for h in hits)
        enterprise_context = "\n\n".join(self._format_hit(h) for h in enterprise_hits)
        sources = [h["source"] for h in hits]
        enterprise_sources = [h["source"] for h in enterprise_hits]
        retrieval_results = [
            {
                "document_source": hit.get("path", ""),
                "document_type": hit.get("document_type") or (hit.get("metadata", {}) or {}).get("document_type", ""),
                "chunk_id": hit.get("chunk_id", ""),
                "section_title": hit.get("section_title", "document"),
                "source_reference": hit.get("source", ""),
                "rank": rank,
                "retrieval_score": hit.get("score", 0.0),
                "original_score": hit.get("original_score", hit.get("score", 0.0)),
                "rerank_score": hit.get("rerank_score", hit.get("score", 0.0)),
                "business_goal": (hit.get("metadata", {}) or {}).get("business_goal", ""),
                "target_segment": (hit.get("metadata", {}) or {}).get("target_segment", ""),
                "matched_keywords": list(hit.get("matched_keywords") or []),
                "retrieved_content": hit.get("text", ""),
            }
            for rank, hit in enumerate(hits, start=1)
        ]

        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "knowledge_retrieved",
            {
                "query": question,
                "sources": sources,
                "enterprise_sources": enterprise_sources,
                "context_length": len(context),
                "enterprise_context_length": len(enterprise_context),
            },
        )
        return {
            "knowledge_support": {
                "context": context,
                "sources": sources,
            },
            "enterprise_context": enterprise_context,
            "enterprise_sources": enterprise_sources,
            "user_knowledge_context": "\n\n".join(self._format_hit(h) for h in user_hits),
            "knowledge_agent_artifacts": {
                "query": question,
                "expanded_query_terms": expanded_terms,
                "intent": intent,
                "preferred_document_types": preferred_types,
                "preferred_business_goals": preferred_goals,
                "knowledge_type_distribution": dict(__import__("collections").Counter(item.get("document_type", "") for item in retrieval_results)),
                "retrieval_results": retrieval_results,
                "knowledge_documents_loaded": getattr(self.kb, "document_count", 0),
            },
        }
