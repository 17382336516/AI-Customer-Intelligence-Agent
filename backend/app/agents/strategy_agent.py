from __future__ import annotations

import json
from typing import Any

from ..config import settings
from ..database import Repository
from ..services.data_tools import category_display
from ..services.llm import LLMClient
from ..services.strategy_knowledge_attribution import attribute_knowledge, build_knowledge_plan
from ..services.strategy_requirement_planner import plan_strategy_requirements
from ..services.knowledge_evidence_extractor import extract_knowledge_evidence
from ..services.strategy_knowledge_planner import build_strategy_knowledge_plan
from ..services.strategy_verifier import verify_strategy_grounding


REQUIRED_FIELDS = {
    "segment_id",
    "segment_name",
    "opportunity",
    "product_mechanisms",
    "benefits",
    "page",
    "slogans",
    "validation_metrics",
    "evidence_summary",
    "limitations",
}


class StrategyAgent:
    name = "strategy_agent"

    def __init__(self, repository: Repository, llm: LLMClient | None = None):
        self.repository = repository
        self.llm = llm or LLMClient()

    @staticmethod
    def _evaluation_artifacts(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        for card in cards:
            channels = card.get("channels") or []
            metrics = card.get("metrics") or []
            text_parts = [
                card.get("opportunity", ""),
                card.get("content_strategy", ""),
                card.get("product_strategy", ""),
                card.get("promotion_strategy", ""),
                "、".join(str(item) for item in channels),
                "、".join(str(item) for item in metrics),
            ]
            records.append(
                {
                    "target_segment": (card.get("lifecycle_tags") or [card.get("segment_name", "")])[0],
                    "lifecycle_tags": list(card.get("lifecycle_tags") or []),
                    "marketing_goal": card.get("marketing_goal", ""),
                    "content_strategy": card.get("content_strategy", ""),
                    "product_strategy": card.get("product_strategy", ""),
                    "promotion_strategy": card.get("promotion_strategy", ""),
                    "channel": "、".join(str(item) for item in channels),
                    "metrics": list(metrics),
                    "knowledge_plan": list(card.get("knowledge_plan") or []),
                    "strategy_requirement": dict(card.get("strategy_requirement") or {}),
                    "generated_strategy_text": "\n".join(
                        str(part).strip() for part in text_parts if str(part).strip()
                    ),
                    # 召回不等于采用；仅透传未来由策略生成结果显式声明的采用证据。
                    "used_knowledge_sources": list(card.get("used_knowledge_sources") or []),
                    "knowledge_applications": list(card.get("knowledge_applications") or []),
                    "strategy_knowledge_trace": list(card.get("strategy_knowledge_trace") or []),
                    "knowledge_evidence": list(card.get("knowledge_evidence") or []),
                    "strategy_verification": dict(card.get("strategy_verification") or {}),
                }
            )
        return {
            "strategy_records": records,
            "human_review_template": {
                "business_relevance": None,
                "actionability": None,
                "enterprise_knowledge_alignment": None,
                "scale": "1-5",
            },
        }

    @staticmethod
    def _base_card(
        segment: dict[str, Any],
        insight: dict[str, Any],
        brand_tone: str,
        knowledge_context: str = "",
        question: str = "",
        lifecycle_tags: list[str] | None = None,
        knowledge_plan: list[dict[str, str]] | None = None,
        strategy_requirement: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stats = segment.get("statistics", {}) or {}
        overall_monetary = float(stats.get("overall_average_spend", 0.0)) or 1.0
        monetary = float(stats.get("average_spend", 0.0))
        frequency = float(stats.get("average_frequency", 0.0))
        overall_frequency = float(stats.get("overall_average_frequency", 0.0)) or 1.0
        recency = float(stats.get("average_recency", 0.0))
        overall_recency = float(stats.get("overall_average_recency", 0.0)) or 1.0
        dominant = stats.get("main_category") or stats.get("dominant_category")
        spend_ratio = monetary / overall_monetary
        dominant_cn = category_display(str(dominant)) if dominant else "综合兴趣"
        income_profile = segment.get("income_profile") or {}
        avg_income = income_profile.get("average_income") if income_profile.get("available") else None
        lifecycle_tags = [str(tag) for tag in (lifecycle_tags or []) if str(tag).strip()]
        knowledge_plan = knowledge_plan or []
        strategy_requirement = strategy_requirement or {}
        required_concepts = list(strategy_requirement.get("must_include_concepts") or [])
        lifecycle_description = {
            "high_value_user": "高价值用户",
            "young_growth_user": "年轻成长用户",
            "price_sensitive_user": "价格敏感用户",
            "category_interest_user": "品类兴趣用户",
            "scenario_enhanced_churn_user": "场景增强沉默用户",
        }
        lifecycle_text = "、".join(lifecycle_description.get(tag, tag) for tag in lifecycle_tags)
        question_terms: list[str] = []
        if any(token in question for token in ("年轻", "增长", "转化")):
            question_terms.extend(["年轻用户", "低门槛", "持续参与"])
        if any(token in question for token in ("新品", "推荐")):
            question_terms.extend(["新品", "兴趣匹配", "低门槛"])
        if any(token in question for token in ("召回", "沉默", "流失")):
            question_terms.extend(["召回", "分层触达", "频控"])

        evidence = [
            f"{item.get('metric')}: {item.get('value')} ({item.get('benchmark', '')})"
            for item in segment.get("evidence", [])[:3]
        ]

        mechanisms: list[str] = []
        if spend_ratio >= 1.5:
            mechanisms.append("高客单专属券")
            mechanisms.append("满额赠礼")
        elif spend_ratio >= 1.1:
            mechanisms.append("品类满减券")
            mechanisms.append("加购返券")
        else:
            mechanisms.append("满减红包")
            mechanisms.append("代金券")
        if frequency >= overall_frequency * 1.1:
            mechanisms.append("复购返券")
        if recency <= overall_recency * 0.8:
            mechanisms.append("限时首发权益")
        if dominant:
            mechanisms.append(f"{dominant_cn}定向券")

        benefits: list[str] = []
        if dominant:
            benefits.append(f"专属{dominant_cn}券")
        if spend_ratio >= 1.1:
            benefits.append("会员积分加速")
        benefits.append("品类专属权益")

        modifiers: list[str] = []
        if spend_ratio >= 1.1:
            modifiers.append("高客单")
        if frequency >= overall_frequency * 1.1:
            modifiers.append("高频")
        if recency <= overall_recency * 0.8:
            modifiers.append("近期活跃")
        if avg_income is not None and avg_income >= 300000:
            modifiers.append("高收入")
        visual_keywords = ([dominant_cn] if dominant else ["综合兴趣"]) + modifiers
        visual_keywords = visual_keywords[:3]

        opportunity = (
            f"针对「{segment['name']}」（约 {round(segment.get('share', 0) * 100, 1)}%，"
            f"人均消费 ¥{monetary:.0f}、人均 {frequency:.1f} 次），"
            f"围绕{dominant_cn if dominant else '综合兴趣'}设计数据驱动的定向权益。"
        )

        # ---- 营销规划：定位 / 方向 / 主题 / 元素 / 商品 / 渠道（全部引用数据洞察）----
        # 目标人群定位：结合主品类、收入画像与消费特征。
        position_parts = []
        if avg_income is not None:
            position_parts.append("高收入" if avg_income >= 300000 else "大众收入")
        if spend_ratio >= 1.1:
            position_parts.append("高客单")
        if frequency >= overall_frequency * 1.1:
            position_parts.append("高频复购")
        position_parts.append(f"{dominant_cn if dominant else '综合'}消费")
        target_positioning = f"面向{'、'.join(position_parts)}的人群，追求明确的需求满足与品质体验。"
        if lifecycle_text:
            target_positioning = f"{lifecycle_text}：{target_positioning}"

        # 营销方向：依据活跃度/频次/客单给出差异化方向。
        if recency <= overall_recency * 0.8 and frequency >= overall_frequency * 1.1:
            marketing_direction = "趁近期活跃窗口，用复购权益锁定高频节奏，并做品类交叉推荐。"
        elif recency <= overall_recency * 0.8:
            marketing_direction = "抓住近期活跃期，用首发/限时权益快速转化。"
        elif spend_ratio >= 1.1:
            marketing_direction = "围绕高客单做专属权益与会员体系，提升客单与黏性。"
        else:
            marketing_direction = "用轻量券与兴趣内容培育，逐步提升转化。"

        ad_theme = f"为{dominant_cn if dominant else '你的兴趣'}而来" if dominant else "为你精选"
        ad_elements = list(visual_keywords)
        if dominant:
            ad_elements.append(f"{dominant_cn}场景")
        if avg_income is not None and avg_income >= 300000:
            ad_elements.append("品质感")
            ad_elements.append("品牌价值")

        # 推荐商品/服务：仅引用真实品类偏好与直接关联兴趣（禁止无依据扩展）。
        recommended_products: list[str] = []
        cat_pref = insight.get("category_preference") or []
        if dominant:
            recommended_products.append(f"{dominant_cn}主推款")
        for cp in cat_pref[:2]:
            # category_preference 形如 "主购买品类：智能手机（贡献占比 35%）"
            if "：" in cp and "主购买" not in cp:
                recommended_products.append(cp.split("：")[0])
        brands = insight.get("brand_preference") or []
        if brands:
            recommended_products.append(f"优先 {brands[0]} 等品牌")
        # 直接关联兴趣（来自真实购买品类/品牌）作为推荐依据。
        direct_interests = (insight.get("interest_profile") or {}).get("direct_interests") or []
        for di in direct_interests[:2]:
            if di not in recommended_products:
                recommended_products.append(di)

        # 触达渠道：依据活跃时段与人群特征推断。
        channels = ["APP push", "站内信"]
        if recency <= overall_recency * 0.8:
            channels.append("短信首发提醒")
        if avg_income is not None and avg_income >= 300000:
            channels.append("高端会员专享通道")
        channels.append("品类专题页")

        # ---- 完整营销方案：从用户画像 → 需求 → 目标 → 方案 的链路 ----
        # 1) 营销目标：结合用户阶段（新客/活跃/高频/复购）与品类。
        user_count = int(segment.get("user_count", 0) or 0)
        share_pct = round(float(segment.get("share", 0.0)) * 100, 0)
        goals: list[str] = []
        if dominant:
            goals.append(f"提升{dominant_cn}品类转化与成交")
        if frequency >= overall_frequency * 1.1:
            goals.append("提升复购与连带购买")
        elif recency <= overall_recency * 0.8:
            goals.append("趁活跃窗口快速转化首单")
        else:
            goals.append("培育兴趣并提升转化")
        if spend_ratio >= 1.1:
            goals.append("提升客单价与高价值商品渗透")
        marketing_goal = "；".join(goals[:3])

        # 2) 内容策略：场景化内容方向（不只有商品陈列），依据品类与行为。
        content_parts: list[str] = []
        if dominant:
            content_parts.append(f"围绕{dominant_cn}的真实使用场景做内容（如场景教程、用法攻略、搭配方案），而非单纯商品陈列")
        if frequency >= overall_frequency * 1.1:
            content_parts.append("用进阶玩法与会员专属内容维持高频用户的深度参与")
        if recency <= overall_recency * 0.8:
            content_parts.append("借近期活跃节点推送新品与场景化种草内容")
        if avg_income is not None and avg_income >= 300000:
            content_parts.append("强调品质、设计与长期价值，契合高收入人群的内容偏好")
        if lifecycle_text:
            content_parts.append(f"围绕{lifecycle_text}设计分层内容与可执行触达")
        if question_terms:
            content_parts.append("、".join(dict.fromkeys(question_terms)))
        if required_concepts:
            content_parts.append("策略要求覆盖：" + "、".join(required_concepts))
        for item in knowledge_plan:
            if item.get("strategy_field") in {"content_strategy", "channel"} and item.get("expected_concept"):
                content_parts.append(f"依据企业知识：{item['expected_concept']}")
        content_strategy = "。".join(content_parts[:5]) + ("。" if content_parts else "")

        # 3) 商品策略：组合与推荐方向（引用真实品类/品牌/直接兴趣，禁止只写券）。
        product_parts: list[str] = []
        if dominant:
            product_parts.append(f"主推{dominant_cn}主款，并搭配该品类周边/耗材形成组合")
        for di in direct_interests[:2]:
            product_parts.append(f"基于真实购买扩展「{di}」相关商品组合")
        if brands:
            product_parts.append(f"优先联动品牌「{brands[0]}」做联名/专供组合")
        if frequency >= overall_frequency * 1.1:
            product_parts.append("设计复购装与订阅式组合，锁定高频节奏")
        for item in knowledge_plan:
            if item.get("strategy_field") == "product_strategy" and item.get("expected_concept"):
                product_parts.append(f"结合企业产品机制：{item['expected_concept']}")
        product_strategy = "；".join(product_parts[:5])

        # 4) 促销策略：优惠方式 + 适配该人群的原因。
        promo_parts: list[str] = []
        for m in mechanisms[:2]:
            promo_parts.append(m)
        if spend_ratio >= 1.5:
            promo_parts.append("采用套装/满赠而非单纯降价，保护高客单人群的价格心智")
        elif dominant:
            promo_parts.append(f"以{dominant_cn}定向品类券+套装优惠承接，避免无差别大促稀释品类心智")
        else:
            promo_parts.append("用轻量券培育转化，控制补贴成本")
        for item in knowledge_plan:
            if item.get("strategy_field") == "promotion_strategy" and item.get("expected_concept"):
                promo_parts.append(f"依据企业知识：{item['expected_concept']}")
        if question_terms:
            promo_parts.append("、".join(dict.fromkeys(question_terms)))
        if required_concepts:
            promo_parts.append("；".join(required_concepts))
        promotion_strategy = "；".join(promo_parts[:5])

        # 5) 效果指标：覆盖点击/加购/转化/客单/连带。
        metrics = [
            "点击率",
            "加购率",
            "转化率",
            "客单价提升",
            "连带购买率",
        ]

        # 策略依据：必须可追溯，禁止生成无依据的营销建议。
        data_basis: list[str] = []
        if user_count:
            data_basis.append(f"用户规模 {user_count} 人（占全体 {share_pct:.0f}%）")
        if avg_income is not None:
            data_basis.append(f"人群平均年收入约 ¥{avg_income:.0f}（收入来自输入属性）")
        if spend_ratio >= 1.5:
            data_basis.append(f"用户平均消费（¥{monetary:.0f}）高于整体 {spend_ratio:.1f} 倍")
        elif spend_ratio >= 1.1:
            data_basis.append(f"用户平均消费（¥{monetary:.0f}）略高于整体 {spend_ratio:.1f} 倍")
        else:
            data_basis.append(f"用户平均消费（¥{monetary:.0f}）接近整体水平")
        if frequency >= overall_frequency * 1.1:
            data_basis.append(f"购买频次（{frequency:.1f} 次）高于整体 {overall_frequency:.1f} 次")
        if recency <= overall_recency * 0.8:
            data_basis.append(f"最近消费在 {recency:.0f} 天前，活跃度高于整体")
        if dominant:
            data_basis.append(
                f"主品类为{dominant_cn}（加权贡献占 {stats.get('main_category_ratio', 0):.0%}）"
            )
        if brands:
            data_basis.append(f"品牌偏好：{ '、'.join(brands[:2]) }")
        if not data_basis:
            data_basis.append("用户统计特征处于整体中位水平")

        knowledge_basis: list[str] = []
        if knowledge_context and knowledge_context.strip():
            # 从知识上下文中抽取可引用的要点（按来源块切分）。
            for block in knowledge_context.split("【来源"):
                block = block.strip()
                if not block:
                    continue
                first_line, _, body = block.partition("】")
                snippet = body.strip().splitlines()[0] if body.strip() else block
                knowledge_basis.append(f"[{first_line.strip() or '知识'}] {snippet[:80]}")

        strategy_basis = {
            "data": data_basis,
            "knowledge": knowledge_basis,
        }

        return {
            "segment_id": segment["segment_id"],
            "segment_name": segment["name"],
            "lifecycle_tags": lifecycle_tags,
            "knowledge_plan": knowledge_plan,
            "strategy_requirement": strategy_requirement,
            "opportunity": opportunity,
            "target_positioning": target_positioning,
            "marketing_goal": marketing_goal,
            "content_strategy": content_strategy,
            "product_strategy": product_strategy,
            "promotion_strategy": promotion_strategy,
            "marketing_direction": marketing_direction,
            "ad_theme": ad_theme,
            "ad_elements": ad_elements[:4],
            "recommended_products": recommended_products[:3],
            "channels": channels[:4],
            "metrics": metrics,
            "strategy_basis": strategy_basis,
            "product_mechanisms": mechanisms[:3],
            "benefits": benefits[:2],
            "page": {
                "theme": f"{segment['name']}定向承接页",
                "visual_keywords": visual_keywords,
                "modules": ["人群权益", "品类推荐", "验证指标"],
                "hero_title": ad_theme,
                "hero_subtitle": opportunity,
                "emotional_direction": brand_tone or "清晰、可信、有行动感",
            },
            "slogans": ["看清用户再承接"],
            "validation_metrics": ["权益领取率", "加购转化率"],
            "evidence_summary": evidence,
            "limitations": insight.get("limitations") or ["结论来自聚合行为，只能说明相关性。"],
        }

    @staticmethod
    def _valid_model_item(item: Any) -> bool:
        return (
            isinstance(item, dict)
            and isinstance(item.get("segment_id"), str)
            and isinstance(item.get("opportunity"), str)
            and isinstance(item.get("target_positioning"), str)
            and isinstance(item.get("marketing_goal"), str)
            and isinstance(item.get("content_strategy"), str)
            and isinstance(item.get("product_strategy"), str)
            and isinstance(item.get("promotion_strategy"), str)
            and isinstance(item.get("ad_theme"), str)
            and isinstance(item.get("product_mechanisms"), list)
            and isinstance(item.get("benefits"), list)
            and isinstance(item.get("slogans"), list)
            and isinstance(item.get("metrics"), list)
            and isinstance(item.get("visual_keywords"), list)
        )

    def _enhance_with_llm(
        self,
        *,
        state: dict[str, Any],
        cards: list[dict[str, Any]],
        memory_cases_count: int,
        knowledge_context: str = "",
        historical_cases: str = "",
        enterprise_context: str = "",
        knowledge_plan: list[dict[str, str]] | None = None,
        strategy_requirement: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        compact_insights = [
            {
                "segment_id": item.get("segment_id"),
                "segment_name": item.get("segment_name"),
                "top_tags": item.get("top_tags", [])[:3],
                "profile": item.get("profile", ""),
                "direct_interests": (item.get("interest_profile") or {}).get("direct_interests", [])[:3],
                "behavior_interests": (item.get("interest_profile") or {}).get("behavior_interests", [])[:3],
                "recommended_actions": item.get("recommended_actions", [])[:1],
            }
            for item in state.get("insights", [])[:3]
        ]
        schema = {
            "strategy_cards": [
                {
                    "segment_id": card["segment_id"],
                    "opportunity": "业务机会判断，结合增长类型（拉新/转化/复购/提客单/跨品类），少于30字",
                    "target_positioning": "该人群是什么类型消费者（结合主品类/消费行为/用户属性，少于40字）",
                    "marketing_goal": "营销目标（结合用户阶段：高频重留存、高客单重升级、新客重转化、低频重激活，少于50字）",
                    "content_strategy": "场景化内容方向：围绕用户已有消费场景+具体主题+原因，禁止只陈列商品或写空泛概念，少于70字",
                    "product_strategy": "商品组合/关联/升级/互补推荐，必须引用真实品类或品牌，禁止只写券，少于70字",
                    "promotion_strategy": "优惠与活动机制（组合购/会员权益/新品优先/品类激励/升级补贴）+为何适合该人群，少于70字",
                    "ad_theme": "广告主题：源自真实品类与画像，少于30字",
                    "ad_elements": ["视觉元素1", "视觉元素2", "视觉元素3"],
                    "product_mechanisms": ["具体策略1", "具体策略2"],
                    "benefits": ["代表性权益1", "代表性权益2"],
                    "metrics": ["效果指标1", "效果指标2", "效果指标3"],
                    "visual_keywords": ["页面关键词1", "页面关键词2", "页面关键词3"],
                    "slogans": ["15字以内文案"],
                }
                for card in cards
            ]
        }
        system = (
            "You are a senior marketing strategy agent specialized in consumer intelligence and business decision making.\n"
            "Your task is to transform user insights and business questions into executable marketing strategies.\n\n"
            "All recommendations must be strictly grounded in:\n"
            "- purchased categories\n- purchase behavior\n- consumption frequency\n"
            "- spending level\n- brand preference\n- user attributes\n"
            "- historical business cases\n- enterprise knowledge (brand positioning, product capability, marketing cases, growth direction, competition)\n\n"
            "Do NOT invent user interests, lifestyles, motivations, or scenarios that are not supported by data.\n"
            "Forbidden assumptions unless directly supported by purchased categories, brands, or user behavior:\n"
            "- Travel lovers\n- Luxury lifestyle\n- Outdoor enthusiasts\n- Fashion seekers\n\n"
            "Generated strategies MUST simultaneously consider:\n"
            "1. user insights (who they are, what they buy)\n"
            "2. enterprise business objectives (e.g. young-user penetration, saving-habit cultivation)\n"
            "3. product capability (reference real products/features, e.g. Yu'eBao, BiBiZan, PiggyBank)\n"
            "4. brand positioning (steady, inclusive, compliant — no exaggerated return or unverified internal metrics)\n"
            "5. historical marketing experience (reusable methodologies from cases)\n"
            "STRICTLY PROHIBITED: any strategy conflicting with the enterprise brand positioning, "
            "or any fabricated growth ratio / GMV uplift / conversion rate / internal operational metric.\n\n"
            "Every recommendation must answer: 'Why this audience?', 'Why this product?', 'Why this strategy?'\n\n"
            "Before generating the final strategy, internally complete:\n"
            "1. Audience diagnosis: who are these users, what they purchase, what consumption characteristics exist.\n"
            "2. Business opportunity: acquisition / conversion / repurchase / increasing customer value / cross-category.\n"
            "3. Strategy selection: match audience characteristics, business objective, and consumption behavior.\n"
            "Only output the final strategy result. Do not output internal reasoning."
        )
        prompt = (
            f"Business question:\n{state['question']}\n\n"
            f"Business objective:\n{state.get('strategy_goal', '') or '(未提供，请根据消费水平/购买频次/最近活跃/客户阶段自动推断合适目标)'}\n\n"
            f"Brand tone:\n{state.get('brand_tone', '') or '(未提供)'}\n\n"
            f"Historical cases (reusable count: {memory_cases_count}):\n"
            f"{historical_cases or '(未提供)'}\n\n"
            f"User insights (compact):\n{json.dumps(compact_insights, ensure_ascii=False)}\n\n"
            f"Enterprise knowledge (brand / product / case / growth / competition):\n"
            f"{enterprise_context[:2500] or '(未提供)'}\n\n"
            f"Other knowledge context:\n{knowledge_context[:1500] or '(未提供)'}\n\n"
            f"Strategy knowledge plan (must be reflected in the mapped field):\n{json.dumps(knowledge_plan or [], ensure_ascii=False)}\n\n"
            f"Strategy requirement (must cover fields and concepts):\n{json.dumps(strategy_requirement or {}, ensure_ascii=False)}\n\n"
            "Task:\n"
            "Based on the above, generate a complete marketing strategy for EACH audience. "
            "Do not generate the same strategy for all segments; different audience types need different strategies.\n\n"
            "For each audience:\n"
            "1. Audience positioning: what type of consumer (combine purchased category + behavior + attributes).\n"
            "2. Marketing goal: pick by stage — high-frequency=retention/loyalty, high-spending=premium/value-up, "
            "new=conversion, low-frequency=reactivation.\n"
            "3. Content strategy: scenario-based content (good: '围绕用户已有厨房电器消费场景展示智能烹饪方案'; "
            "bad: '打造品质生活方式'). Do not only describe products.\n"
            "4. Product strategy: reference real purchased categories/brands AND enterprise products (e.g. Yu'eBao, "
            "BiBiZan, PiggyBank); recommend combinations, related, upgrade, complementary products. "
            "Do not only recommend coupons.\n"
            "5. Promotion strategy: recommend suitable mechanisms (bundle, membership benefit, new-product priority, "
            "category incentive, upgrade subsidy) and explain why.\n"
            "6. Advertising/page design: if the business question involves landing page / campaign page / ad materials, "
            "also provide page positioning (target audience + core selling point), page structure (hero section, key "
            "modules, product display direction, CTA), and ad output (ad theme, visual elements, copy direction). "
            "All elements must come from purchased categories and behaviors.\n\n"
            "Enterprise constraint checklist (must satisfy all):\n"
            "- Strategy aligns with enterprise business objectives (e.g. young-user penetration, saving-habit cultivation).\n"
            "- Product knowledge must change product_strategy; operation_rule must change promotion_strategy; brand knowledge must change content_strategy; marketing_case must change promotion_strategy or channel.\n"
            "- Do not list a source as used unless its concept is explicitly reflected in the corresponding strategy field.\n"
            "- Product recommendations reference real enterprise product capabilities, not invented ones.\n"
            "- Brand tone stays steady / inclusive / compliant; no exaggerated-return or unverified-internal-metric claims.\n"
            "- Reuses validated methodologies from enterprise marketing cases where applicable.\n"
            "Output requirements: each field concise, every recommendation data-grounded, avoid generic marketing "
            "language, avoid repeated strategies between audiences, prefer actionable business decisions over creative copywriting."
        )
        response = self.llm.generate_json(
            system=system,
            prompt=prompt,
            schema_hint=schema,
            max_tokens=1800,
        )
        candidate = response.get("strategy_cards")
        if not (
            isinstance(candidate, list)
            and len(candidate) == len(cards)
            and all(self._valid_model_item(item) for item in candidate)
        ):
            raise RuntimeError("模型策略输出结构不合法，请重试或更换模型。")
        core_by_id = {item["segment_id"]: item for item in candidate}
        merged: list[dict[str, Any]] = []
        for card in cards:
            core = core_by_id.get(card["segment_id"])
            if core is None:
                raise RuntimeError("模型策略缺少部分人群结果，请重试。")
            merged.append(
                {
                    **card,
                    "opportunity": core["opportunity"],
                    "target_positioning": core["target_positioning"],
                    "marketing_goal": core["marketing_goal"],
                    "content_strategy": core["content_strategy"],
                    "product_strategy": core["product_strategy"],
                    "promotion_strategy": core["promotion_strategy"],
                    "ad_theme": core["ad_theme"],
                    "ad_elements": core["ad_elements"][:4],
                    "product_mechanisms": core["product_mechanisms"][:2],
                    "benefits": core["benefits"][:2],
                    "metrics": core["metrics"][:5],
                    "page": {
                        **card["page"],
                        "visual_keywords": core["visual_keywords"][:3],
                        "hero_title": core["ad_theme"] or core["slogans"][0],
                        "hero_subtitle": core["opportunity"],
                    },
                    "slogans": core["slogans"][:2],
                    "validation_metrics": core["metrics"][:2] if core.get("metrics") else card["validation_metrics"],
                }
            )
        return merged

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if state.get("blocked") or state.get("route") != "full_strategy":
            return {"strategy_cards": [], "strategy_agent_artifacts": {"strategy_records": []}}

        knowledge_support = state.get("knowledge_support") or {}
        knowledge_context = knowledge_support.get("context", "") if isinstance(knowledge_support, dict) else ""
        retrieval_results = (state.get("knowledge_agent_artifacts") or {}).get("retrieval_results", [])
        knowledge_plan = build_knowledge_plan(retrieval_results)
        enterprise_context = state.get("enterprise_context", "") or ""

        memory_cases = self.repository.recall("validated_strategy_case", limit=2)
        historical_cases_text = "\n".join(
            f"- {case.get('summary', '')}" for case in memory_cases if case.get("summary")
        ) if memory_cases else ""
        insight_by_id = {item["segment_id"]: item for item in state.get("insights", [])}
        artifact_records = (state.get("insight_agent_artifacts") or {}).get("insight_records", [])
        lifecycle_by_name = {
            item.get("segment_name", ""): list(item.get("lifecycle_tags") or [])
            for item in artifact_records
        }
        strategy_requirement = plan_strategy_requirements(
            state.get("question", ""),
            [tag for tags in lifecycle_by_name.values() for tag in tags],
        )
        cards = [
            self._base_card(
                segment,
                insight_by_id[segment["segment_id"]],
                state.get("brand_tone", ""),
                knowledge_context,
                state.get("question", ""),
                lifecycle_by_name.get(
                    insight_by_id[segment["segment_id"]].get("segment_name", ""),
                    insight_by_id[segment["segment_id"]].get("lifecycle_tags") or [],
                ),
                knowledge_plan,
                strategy_requirement,
            )
            for segment in state.get("segments", [])[:3]
            if segment["segment_id"] in insight_by_id
        ]
        model_mode = state.get("model_mode", "deterministic")

        open_task = any(token in str(state.get("question", "")) for token in ("打开页", "落地页", "页面设计", "视觉风格", "首页"))
        if (settings.llm_enhance_strategy or (settings.llm_fallback_open_tasks and open_task)) and self.llm.enabled and cards:
            cards = self._enhance_with_llm(
                state=state,
                cards=cards,
                memory_cases_count=len(memory_cases),
                knowledge_context=knowledge_context,
                historical_cases=historical_cases_text,
                enterprise_context=enterprise_context,
                knowledge_plan=knowledge_plan,
                strategy_requirement=strategy_requirement,
            )
            model_mode = "llm_enhanced"

        # Attribution is deterministic: a source is recorded only when it was
        # actually retrieved and one of its mapped concepts appears in a
        # concrete strategy field.
        cards = attribute_knowledge(cards, retrieval_results)
        grounded_cards: list[dict[str, Any]] = []
        for card in cards:
            target = str((card.get("lifecycle_tags") or [card.get("segment_name", "")])[0])
            evidence = extract_knowledge_evidence(state.get("question", ""), target, retrieval_results)
            planner_output = build_strategy_knowledge_plan(
                state.get("insights", [{}])[0] if state.get("insights") else {},
                target,
                evidence,
                state.get("question", ""),
            )
            verification = verify_strategy_grounding(card, evidence, card.get("strategy_knowledge_trace") or [])
            grounded_cards.append({
                **card,
                "knowledge_evidence": evidence,
                "knowledge_plan": card.get("knowledge_plan") or planner_output,
                "strategy_verification": verification,
            })
        cards = grounded_cards

        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "strategy_cards_created",
            {
                "count": len(cards),
                "model_mode": model_mode,
                "memory_cases_retrieved": len(memory_cases),
            },
        )
        return {
            "strategy_cards": cards,
            "strategy_agent_artifacts": self._evaluation_artifacts(cards),
            "model_mode": model_mode,
        }
