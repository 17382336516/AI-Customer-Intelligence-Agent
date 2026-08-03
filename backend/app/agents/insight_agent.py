from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..database import Repository
from ..services.data_tools import category_display
from ..services.llm import LLMClient


class InsightAgent:
    name = "insight_agent"

    def __init__(self, repository: Repository, llm: LLMClient | None = None):
        self.repository = repository
        self.llm = llm or LLMClient()

    def _base_insight(self, segment: dict[str, Any], cleaned: Any = None) -> dict[str, Any]:
        stats = segment.get("statistics", {}) or {}
        overall_monetary = float(stats.get("overall_average_spend", 0.0)) or 1.0
        monetary = float(stats.get("average_spend", 0.0))
        frequency = float(stats.get("average_frequency", 0.0))
        overall_frequency = float(stats.get("overall_average_frequency", 0.0)) or 1.0
        recency = float(stats.get("average_recency", 0.0))
        overall_recency = float(stats.get("overall_average_recency", 0.0)) or 1.0
        dominant = stats.get("main_category") or stats.get("dominant_category")
        category_distribution = stats.get("category_distribution", {}) or {}
        spend_ratio = monetary / overall_monetary
        dominant_cn = category_display(str(dominant)) if dominant else "综合兴趣"

        # 人群级收入画像（输入属性，直接透传）
        income_profile = segment.get("income_profile") or {"available": False}

        tags: list[str] = []
        if dominant:
            tags.append(f"{dominant_cn}偏好用户")
            tags.append(f"{dominant_cn}消费突出")
        else:
            tags.append("综合兴趣用户")
            tags.append("多品类浏览")
        if spend_ratio >= 1.1:
            tags.append("高客单用户")
        elif frequency >= overall_frequency * 1.1:
            tags.append("高频复购用户")
        if income_profile.get("available") and (income_profile.get("average_income") or 0) >= 300000:
            tags.append("高收入人群")
        tags = tags[:3]

        # 兴趣分级（约束：仅来自真实数据，禁止无依据扩展）。
        # 一级 direct_interests：来自用户实际购买品类 / 品牌。
        # 二级 behavior_interests：来自消费模式（高频、高客单等），不指向未购买生活方式。
        # 注意：brand_preference 在下方"品牌偏好"段才定义，品牌追加逻辑也放在其后。
        direct_interests: list[str] = [
            f"{category_display(str(category))}商品"
            for category, _share in sorted(
                category_distribution.items(), key=lambda kv: kv[1], reverse=True
            )[:3]
        ]

        behavior_interests: list[str] = []
        if frequency >= overall_frequency * 1.1:
            behavior_interests.append("高频复购消费")
        if spend_ratio >= 1.1:
            behavior_interests.append("高客单品质消费")
        if recency <= overall_recency * 0.8:
            behavior_interests.append("近期活跃消费")
        if not behavior_interests:
            behavior_interests.append("常规稳定消费")

        # 向后兼容：interests 合并两级（供旧前端/下游使用）。
        interests = (direct_interests + behavior_interests)[:3]

        value_tier = (
            "高客单人群" if spend_ratio >= 1.5
            else "中高客单人群" if spend_ratio >= 1.1
            else "常规客单人群"
        )

        # 消费特征（真实统计）
        consumption_features = [
            f"平均消费金额 ¥{monetary:.0f}（{spend_ratio:.1f} 倍于整体）",
            f"总消费金额 ¥{float(stats.get('total_purchase_amount', 0.0)):.0f}",
            f"平均订单金额 ¥{float(stats.get('avg_order_value', 0.0)):.0f}",
            f"平均消费频率 {frequency:.1f} 次",
            f"最近一次消费约 {recency:.0f} 天前",
        ]

        # 品类偏好：主购买品类 + 品类贡献比例（真实统计）
        category_preference: list[str] = []
        if dominant:
            category_preference.append(
                f"主购买品类：{dominant_cn}（贡献占比 {stats.get('main_category_ratio', 0):.0%}）"
            )
        for category, share in sorted(category_distribution.items(), key=lambda kv: kv[1], reverse=True)[:3]:
            category_preference.append(f"{category_display(str(category))}：{share:.0%}")

        # 品牌偏好：若该人群有 brand 字段，统计 Top 品牌（真实统计）
        brand_preference: list[str] = []
        if cleaned is not None and "brand" in cleaned.columns and "normalized_category" in cleaned.columns:
            seg_dominant = dominant
            mask = (
                cleaned["normalized_category"] == seg_dominant
                if seg_dominant
                else cleaned["normalized_category"].notna()
            )
            seg_brands = cleaned.loc[mask, "brand"].dropna().astype(str)
            seg_brands = seg_brands[~seg_brands.isin(["", "nan", "None"])]
            if not seg_brands.empty:
                brand_preference = list(seg_brands.value_counts().head(3).index)

        # 品牌作为直接关联兴趣（来自真实 brand 字段，禁止无依据扩展）。
        for brand in brand_preference[:2]:
            direct_interests.append(f"{brand}生态产品")

        evidence_summary = [
            f"{item.get('metric')}: {item.get('value')} ({item.get('benchmark', '')})"
            for item in segment.get("evidence", [])[:4]
        ]
        return {
            "segment_id": segment["segment_id"],
            "segment_name": segment["name"],
            "segment_size": int(segment.get("user_count", 0)),
            "income_profile": income_profile,
            "top_tags": tags,
            "persona_tags": tags,
            "profile": (
                f"该人群约占 {round(segment.get('share', 0) * 100, 1)}%，"
                f"平均消费 ¥{monetary:.0f}（{spend_ratio:.1f} 倍于整体），"
                f"主要由{dominant_cn}消费驱动。"
                + (
                    f"平均年收入约 ¥{income_profile.get('average_income', 0):.0f}。"
                    if income_profile.get("available") else ""
                )
            ),
            "predicted_interests": interests,
            "interests": interests,
            "interest_profile": {
                "direct_interests": direct_interests,
                "behavior_interests": behavior_interests,
            },
            "value_tier": value_tier,
            "behavior_profile": segment.get("key_features", [])[:3],
            "consumption_features": consumption_features,
            "category_preference": category_preference,
            "brand_preference": brand_preference,
            "motivation": (
                "近期消费活跃且品类集中，存在明确的需求信号。"
                if recency <= overall_recency * 0.8
                else "基于消费金额、频次与品类偏好的综合信号判断。"
            ),
            "needs": ["更清晰的商品比较", "更直接的利益点", "更顺滑的转化路径"],
            "trend_explanation": "该人群在样本中具有相对清晰的统计特征，可作为运营分层切入点。",
            "decision_implications": ["优先配置品类化内容", "围绕兴趣标签做推荐与活动"],
            "recommended_actions": ["设计定向商品集合", "投放更具体的兴趣标签内容"],
            "alternative_explanations": ["结果可能受到促销、季节、渠道或样本窗口影响。"],
            "limitations": ["结论来自聚合行为数据，只能说明相关性，不能解释因果。"],
        }

    @staticmethod
    def _valid_model_item(item: Any) -> bool:
        return (
            isinstance(item, dict)
            and isinstance(item.get("segment_id"), str)
            and isinstance(item.get("top_tags"), list)
            and len(item["top_tags"]) == 3
            and isinstance(item.get("direct_interests"), list)
            and isinstance(item.get("behavior_interests"), list)
            and isinstance(item.get("profile"), str)
        )

    def _enhance_with_llm(
        self,
        *,
        state: dict[str, Any],
        target_segments: list[dict[str, Any]],
        base_insights: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        safe_summary = [
            {
                "segment_id": segment["segment_id"],
                "segment_name": segment["name"],
                "user_count": segment["user_count"],
                "share": segment["share"],
                "key_features": segment.get("key_features", [])[:2],
                "income_profile": segment.get("income_profile", {}),
                "category_preference": segment.get("statistics", {}).get("category_distribution", {}),
                "evidence": [
                    {
                        "metric": item.get("metric"),
                        "value": item.get("value"),
                    }
                    for item in segment.get("evidence", [])[:2]
                ],
            }
            for segment in target_segments
        ]
        schema = {
            "insights": [
                {
                    "segment_id": item["segment_id"],
                    "segment_name": item["segment_name"],
                    "top_tags": item["top_tags"],
                    "profile": "一句话画像，少于40字",
                    "direct_interests": item["interest_profile"]["direct_interests"],
                    "behavior_interests": item["interest_profile"]["behavior_interests"],
                    "motivation": "一句话动机，少于30字",
                    "recommended_actions": ["动作1", "动作2"],
                }
                for item in base_insights
            ]
        }
        response = self.llm.generate_json(
            system=(
                "You are a customer insight agent. Interests MUST derive ONLY from the given "
                "segment evidence: purchased categories, brands, and consumption patterns. "
                "Do NOT invent lifestyle labels (e.g. travel, luxury, cars, hobbies) that are not "
                "supported by the data. direct_interests = purchased categories/brands; "
                "behavior_interests = consumption patterns (high frequency, high ticket, recent activity)."
            ),
            prompt=(
                f"Business question: {state['question']}\n"
                f"Segment evidence: {json.dumps(safe_summary, ensure_ascii=False)}\n"
                "For each segment return exactly 3 top_tags. "
                "Return direct_interests ONLY from purchased categories/brands shown in evidence, "
                "and behavior_interests ONLY from consumption patterns. "
                "Use short concrete labels, for example: 手机换新者、家电换新用户."
            ),
            schema_hint=schema,
            max_tokens=900,
        )
        candidate = response.get("insights")
        if not (
            isinstance(candidate, list)
            and len(candidate) == len(base_insights)
            and all(self._valid_model_item(item) for item in candidate)
        ):
            raise RuntimeError("模型洞察输出结构不合法，请重试或更换模型。")

        core_by_id = {item["segment_id"]: item for item in candidate}
        merged: list[dict[str, Any]] = []
        for base in base_insights:
            core = core_by_id.get(base["segment_id"])
            if core is None:
                raise RuntimeError("模型洞察缺少部分人群结果，请重试。")
            top_tags = core["top_tags"][:3]
            direct = (core.get("direct_interests") or base["interest_profile"]["direct_interests"])[:3]
            behavior = (core.get("behavior_interests") or base["interest_profile"]["behavior_interests"])[:3]
            interests = (direct + behavior)[:3]
            merged.append(
                {
                    **base,
                    "segment_name": core.get("segment_name") or base["segment_name"],
                    "top_tags": top_tags,
                    "persona_tags": top_tags,
                    "profile": core["profile"],
                    "predicted_interests": interests,
                    "interests": interests,
                    "interest_profile": {
                        "direct_interests": direct,
                        "behavior_interests": behavior,
                    },
                    "motivation": core.get("motivation") or base["motivation"],
                    "recommended_actions": core.get("recommended_actions") or base["recommended_actions"],
                }
            )
        return merged

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("blocked") or state.get("route") == "quality_only":
            return {"insights": []}

        target_segments = state.get("segments", [])[:3]
        cleaned = state.get("_cleaned_df")
        insights = [self._base_insight(segment, cleaned) for segment in target_segments]
        model_mode = "deterministic"

        if settings.llm_enhance_insights and self.llm.enabled and target_segments:
            insights = self._enhance_with_llm(
                state=state,
                target_segments=target_segments,
                base_insights=insights,
            )
            model_mode = "llm_enhanced"

        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "insights_created",
            {"count": len(insights), "model_mode": model_mode},
        )
        return {"insights": insights, "model_mode": model_mode}
