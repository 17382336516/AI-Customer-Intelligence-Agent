from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..config import settings
from ..database import Repository
from ..services.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class KnowledgeAgent:
    """RAG 知识检索 Agent。

    职责：根据业务问题与人群画像（segment_profile）检索企业知识库，
    输出可解释的知识上下文（context）与来源（sources）。

    知识库为本地文件（markdown / txt / json），通过可替换的向量检索实现。
    当前默认使用 TF-IDF + 余弦相似度（无需额外依赖）；若后续引入
    sentence-transformers / FAISS / Chroma，只需替换 KnowledgeBase 的
    embed 实现即可，本 Agent 逻辑不变。
    """

    name = "knowledge_agent"

    def __init__(self, repository: Repository, knowledge_base: KnowledgeBase | None = None):
        self.repository = repository
        self.kb = knowledge_base or KnowledgeBase(settings.knowledge_dir)

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

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        question = state.get("question", "")
        segments = state.get("segments", []) or []
        segment_profile = self._summarize_segments(segments)

        try:
            hits = self.kb.search(question, segment_profile=segment_profile, top_k=3)
        except Exception as exc:  # 检索失败不应阻断主流程
            logger.warning("Knowledge retrieval failed: %s", exc)
            hits = []

        context = "\n\n".join(
            f"【来源 {hit['source']}】\n{hit['text']}" for hit in hits
        )
        sources = [hit["source"] for hit in hits]

        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "knowledge_retrieved",
            {
                "query": question,
                "sources": sources,
                "context_length": len(context),
            },
        )
        return {
            "knowledge_support": {
                "context": context,
                "sources": sources,
            }
        }
