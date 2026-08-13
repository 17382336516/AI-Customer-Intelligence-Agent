"""本地知识库检索（TF-IDF + 余弦相似度）。

支持多根目录加载（用户消费知识 + 企业知识），并从 Markdown 的 YAML
frontmatter 解析 metadata（type / company / product / category / source）。
默认实现无需额外依赖；若引入 sentence-transformers / FAISS / Chroma，
只需替换 ``embed`` 与 ``_build_index`` 即可，Agent 层逻辑不变。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import jieba
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_META_KEY_RE = re.compile(r"^([A-Za-z_]+):\s*(.*)$")


@dataclass
class KnowledgeDoc:
    text: str
    source: str
    path: str
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeBase:
    def __init__(self, roots: list[Path] | Path, *, top_k: int = 3):
        self.roots = [roots] if isinstance(roots, Path) else list(roots)
        self.top_k = top_k
        self._docs: list[KnowledgeDoc] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._build_index()

    @property
    def document_count(self) -> int:
        return len(self._docs)

    # ---- 索引构建 ----------------------------------------------------------
    def _build_index(self) -> None:
        docs: list[KnowledgeDoc] = []
        for root in self.roots:
            if not root or not Path(root).exists():
                logger.warning("Knowledge root missing, skipped: %s", root)
                continue
            for path in sorted(Path(root).rglob("*")):
                if path.suffix.lower() not in {".md", ".txt", ".json"}:
                    continue
                if path.is_dir():
                    continue
                try:
                    raw = path.read_text(encoding="utf-8")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed reading %s: %s", path, exc)
                    continue
                text, meta = self._parse_frontmatter(raw)
                if not text.strip():
                    continue
                rel = str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
                meta = self._normalize_metadata(meta, rel, text)
                docs.append(
                    KnowledgeDoc(
                        text=text,
                        source=meta.get("source") or rel,
                        path=rel,
                        metadata=meta,
                    )
                )
        self._docs = docs
        if not docs:
            logger.warning("No knowledge documents loaded from %s", self.roots)
            self._vectorizer = None
            self._matrix = None
            return
        self._vectorizer = TfidfVectorizer(tokenizer=_jieba_tokenize, lowercase=False)
        self._matrix = self._vectorizer.fit_transform([d.text for d in docs])
        logger.info("Knowledge index built with %d docs", len(docs))

    @staticmethod
    def _parse_frontmatter(raw: str) -> tuple[str, dict[str, Any]]:
        meta: dict[str, Any] = {}
        m = _FRONTMATTER_RE.match(raw)
        if not m:
            return raw, meta
        block = m.group(1)
        for line in block.splitlines():
            km = _META_KEY_RE.match(line.strip())
            if km:
                meta[km.group(1).lower()] = km.group(2).strip()
        return raw[m.end():], meta

    @staticmethod
    def _normalize_metadata(meta: dict[str, Any], relative_path: str, text: str) -> dict[str, Any]:
        """Fill the v2 metadata contract while remaining compatible with old frontmatter."""
        result = dict(meta)
        path = relative_path.replace("\\", "/").lower()
        parent = path.split("/", 1)[0] if "/" in path else "general"
        type_map = {"case": "marketing_case", "growth": "user_growth"}
        raw_type = result.get("document_type") or result.get("category") or parent
        document_type = type_map.get(str(raw_type), type_map.get(parent, str(raw_type)))
        result["document_type"] = document_type
        result.setdefault("product_name", result.get("product") or "Yu'eBao")
        result.setdefault("business_goal", {
            "user_growth": "young_user_growth",
            "marketing_case": "campaign_conversion",
            "operation_rule": "campaign_conversion",
            "product": "product_activation",
            "brand": "brand_consistency",
        }.get(document_type, "general_marketing"))
        result.setdefault("target_segment", {
            "user_growth": "young_growth_user",
            "product": "young_growth_user",
            "marketing_case": "young_growth_user",
        }.get(document_type, ""))
        result.setdefault("marketing_scenario", {
            "user_growth": "activation",
            "product": "activation",
            "marketing_case": "campaign",
            "operation_rule": "campaign",
            "brand": "brand_positioning",
        }.get(document_type, "general"))
        existing_keywords = str(result.get("keywords", ""))
        headings = " ".join(line.lstrip("# ") for line in text.splitlines() if line.startswith("#"))
        result["keywords"] = ",".join(dict.fromkeys(
            item.strip() for item in (existing_keywords + "," + headings).split(",") if item.strip()
        ))
        result["source_path"] = relative_path.replace("\\", "/")
        return result

    @staticmethod
    def _route_and_expand(query: str) -> tuple[list[str], list[str]]:
        text = str(query or "")
        if any(token in text for token in ("城市", "潜力", "信任")):
            return ["brand", "marketing_case", "user_growth"], ["年轻用户", "城市", "信任", "潜力用户", "分层运营", "用户增长"]
        if any(token in text for token in ("年轻", "增长", "转化", "拉新")):
            return ["user_growth", "product", "marketing_case"], ["年轻用户", "低门槛", "自动储蓄", "笔笔攒", "消费后攒钱", "用户增长"]
        if any(token in text for token in ("品牌", "定位", "合规")):
            return ["brand", "marketing_case", "operation_rule"], ["品牌定位", "稳健", "普惠", "合规", "信任"]
        if any(token in text for token in ("活动", "618", "春节", "节点", "促销", "新品", "推荐")):
            return ["user_growth", "marketing_case", "operation_rule"], ["新品", "兴趣匹配", "低门槛", "活动机制", "分层权益", "触达", "转化"]
        if any(token in text for token in ("产品", "余额宝", "笔笔攒", "自动储蓄", "储蓄")):
            return ["product", "operation_rule", "user_growth"], ["产品机制", "自动储蓄", "低门槛", "目标储蓄", "资金流动性"]
        if any(token in text for token in ("召回", "复购", "会员", "留存")):
            return ["operation_rule", "marketing_case", "product"], ["召回", "复购", "会员权益", "分层触达", "频控"]
        return ["operation_rule", "product", "marketing_case"], ["营销策略", "用户分层", "转化", "复购"]

    # ---- 检索 --------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        segment_profile: str = "",
        top_k: int | None = None,
        category: str | None = None,
        preferred_document_types: list[str] | None = None,
        preferred_business_goals: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self._vectorizer is None or self._matrix is None or not self._docs:
            return []
        k = top_k or self.top_k
        priorities, expansions = self._route_and_expand(query)
        if preferred_document_types:
            priorities = list(dict.fromkeys(preferred_document_types + priorities))
        combined = f"{query}\n{' '.join(expansions)}\n{segment_profile}"
        q_vec = self._vectorizer.transform([combined])
        sims = cosine_similarity(q_vec, self._matrix).ravel()
        def rerank_score(i: int) -> float:
            doc_type = str(self._docs[i].metadata.get("document_type", ""))
            meta = self._docs[i].metadata
            goal_match = float(bool(preferred_business_goals and str(meta.get("business_goal", "")) in preferred_business_goals))
            type_match = float(bool(preferred_document_types and doc_type in preferred_document_types))
            segment_match = float(bool(segment_profile and any(token in segment_profile for token in str(meta.get("target_segment", "")).split(","))))
            route_bonus = max(0, len(priorities) - priorities.index(doc_type)) * 0.02 if doc_type in priorities else 0.0
            return float(sims[i]) + 0.2 * goal_match + 0.15 * type_match + 0.15 * segment_match + route_bonus

        ranked = sorted(
            range(len(self._docs)),
            key=rerank_score,
            reverse=True,
        )
        # Metadata-aware diversity: reserve the best positive hit for each
        # routed knowledge type before filling remaining slots by score.
        diversified: list[int] = []
        for wanted_type in priorities:
            candidate = next(
                (i for i in ranked if i not in diversified
                 and self._docs[i].metadata.get("document_type") == wanted_type
                 and rerank_score(i) > 0),
                None,
            )
            if candidate is not None:
                diversified.append(candidate)
        ranked = diversified + [i for i in ranked if i not in diversified]
        hits: list[dict[str, Any]] = []
        for i in ranked:
            if len(hits) >= k:
                break
            doc = self._docs[i]
            if category and doc.metadata.get("category") != category:
                continue
            score = rerank_score(i)
            if score <= 0:
                continue
            doc_text = doc.text.lower()
            matched_keywords = [word for word in expansions if word.lower() in doc_text]
            headings = [line.lstrip("# ").strip() for line in doc.text.splitlines() if line.startswith("#")]
            hits.append(
                {
                    "source": doc.source,
                    "path": doc.path,
                    "text": doc.text,
                    "score": round(score, 4),
                    "original_score": round(float(sims[i]), 4),
                    "rerank_score": round(score, 4),
                    "metadata": doc.metadata,
                    "document_type": doc.metadata.get("document_type", ""),
                    "chunk_id": f"{doc.path}#document",
                    "section_title": headings[0] if headings else "document",
                    "matched_keywords": matched_keywords,
                }
            )
        return hits


def _jieba_tokenize(text: str) -> list[str]:
    return [tok for tok in jieba.lcut(text) if len(tok.strip()) > 1]
