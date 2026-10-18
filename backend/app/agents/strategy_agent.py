from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)


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
        question_focus = {
            "push": any(token in question.lower() for token in ("push", "推送", "触达", "短信", "站内信")),
            "page": any(token in question for token in ("专题页", "落地页", "页面", "首页", "视觉")),
            "campaign": any(token in question for token in ("营销活动", "活动方案", "活动策略", "campaign")),
            "timing": any(token in question for token in ("时点", "时间", "时机", "节点", "什么时候")),
            "copy": any(token in question for token in ("文案", "标题", "slogan", "话术")),
            "differentiation": any(token in question for token in ("差异化", "分别", "不同人群")),
        }
        dominant_key = str(dominant or "").lower()
        if any(token in dominant_key or token in dominant_cn.lower() for token in ("coffee", "beans", "咖啡")):
            category_play = "coffee"
        elif any(token in dominant_key or token in dominant_cn.lower() for token in ("luggage", "travel", "旅行", "行李")):
            category_play = "travel"
        elif any(token in dominant_key or token in dominant_cn.lower() for token in ("cat_food", "pet", "萌宠", "猫粮")):
            category_play = "pet_food"
        else:
            category_play = "general"
        question_terms: list[str] = []
        if any(token in question for token in ("年轻", "增长", "转化")):
            question_terms.extend(["年轻用户", "低门槛", "持续参与"])
        if any(token in question for token in ("新品", "推荐")):
            question_terms.extend(["新品", "兴趣匹配", "低门槛"])
        if any(token in question for token in ("召回", "沉默", "流失")):
            question_terms.extend(["召回", "分层触达", "频控"])
        if question_focus["push"]:
            question_terms.extend(["分层Push", "发送时点", "频控与退订"])
        if question_focus["page"] or question_focus["campaign"]:
            question_terms.extend(["首屏承接", "品类推荐模块", "转化路径"])

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
        if category_play == "coffee":
            target_positioning = "咖啡豆明确偏好人群：客单低于整体但有稳定购买频次，适合做口味/规格升级与复购培育。"
        elif category_play == "travel":
            target_positioning = "旅行箱高客单决策人群：购买频次较低但单次价值较高，重点解决比较成本并提升套装与配件连带。"
        elif category_play == "pet_food":
            target_positioning = "猫粮高频补货人群：购买频次高但客单较低，重点建立周期补货和连续购买习惯。"

        # 营销方向：依据活跃度/频次/客单给出差异化方向。
        if recency <= overall_recency * 0.8 and frequency >= overall_frequency * 1.1:
            marketing_direction = "趁近期活跃窗口，用复购权益锁定高频节奏，并做品类交叉推荐。"
        elif recency <= overall_recency * 0.8:
            marketing_direction = "抓住近期活跃期，用首发/限时权益快速转化。"
        elif spend_ratio >= 1.1:
            marketing_direction = "围绕高客单做专属权益与会员体系，提升客单与黏性。"
        else:
            marketing_direction = "用轻量券与兴趣内容培育，逐步提升转化。"
        if category_play == "coffee":
            marketing_direction = "以复购周期提醒承接稳定需求，再用相邻口味/规格试用推动品类升级。"
        elif category_play == "travel":
            marketing_direction = "围绕高客单决策做内容比较和套装承接，优先提升连带购买而非频繁打折。"
        elif category_play == "pet_food":
            marketing_direction = "以消耗周期预测和提前补货降低断购，用周期购/订阅提升连续复购。"

        ad_theme = f"为{dominant_cn if dominant else '你的兴趣'}而来" if dominant else "为你精选"
        if category_play == "coffee":
            ad_theme = "咖啡豆复购与口味升级"
        elif category_play == "travel":
            ad_theme = "一套旅行装备，减少出发前决策"
        elif category_play == "pet_food":
            ad_theme = "按周期补货，安心养宠"
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
        if question_focus["push"]:
            goals.insert(0, "提升分层 Push 的打开、点击与回流转化")
        elif question_focus["page"] or question_focus["campaign"]:
            goals.insert(0, "提升专题页承接效率与活动转化")
        if category_play == "coffee":
            goals.insert(0, "提升咖啡豆复购，并通过口味/规格差异化带动升级")
        elif category_play == "travel":
            goals.insert(0, "提升高客单旅行装备的组合购买与决策转化")
        elif category_play == "pet_food":
            goals.insert(0, "建立猫粮周期补货习惯，提升复购和连续购买")
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
        if question_focus["push"]:
            if "旅行" in question or "luggage" in question.lower() or "行李" in question:
                content_parts.append("旅行·luggage人群采用出行准备场景：出发前补购清单、轻量收纳技巧与目的地适配建议，Push 只承接一个明确动作")
            else:
                content_parts.append("Push 内容按人群阶段拆分：高频用户强调补购/升级，沉默用户强调低门槛回流，正文只保留一个明确行动按钮")
        if category_play == "coffee":
            content_parts.append("围绕咖啡豆的口味、烘焙度、规格和复购周期做选择内容，用已购买品类做相邻口味/规格升级，不泛化为生活方式兴趣")
        elif category_play == "travel":
            content_parts.append("围绕旅行箱容量、收纳分区、耐用材质与出行前准备做决策内容，先解决高客单用户的比较成本，再承接组合购买")
        elif category_play == "pet_food":
            content_parts.append("围绕猫粮消耗周期、规格组合和补货提醒做连续内容，把高频购买转化为稳定补货计划，不只依赖一次性红包")
        if question_focus["page"] or question_focus["campaign"]:
            content_parts.append("专题页按首屏利益点→人群专属商品→权益说明→行动按钮组织，页面内容与人群主品类保持一一对应")
        if question_focus["differentiation"]:
            content_parts.append(f"针对{lifecycle_text or '该人群'}单独设置利益点、商品组合和验证指标，不复用其他人群的通用话术")
        if required_concepts:
            content_parts.append("策略要求覆盖：" + "、".join(required_concepts))
        for item in knowledge_plan:
            if item.get("strategy_field") in {"content_strategy", "channel"} and item.get("expected_concept"):
                content_parts.append(f"依据企业知识：{item['expected_concept']}")
        content_strategy = "。".join(content_parts[:7]) + ("。" if content_parts else "")

        # 3) 商品策略：组合与推荐方向（引用真实品类/品牌/直接兴趣，禁止只写券）。
        product_parts: list[str] = []
        if dominant:
            product_parts.append(f"主推{dominant_cn}主款，并搭配该品类周边/耗材形成组合")
        if category_play == "coffee":
            product_parts.append("以当前咖啡豆为基准推荐相邻口味/烘焙度或规格组合，设置尝鲜装→常规装→囤货装的升级路径")
        elif category_play == "travel":
            product_parts.append("以旅行·luggage主款搭配收纳配件/保护配件形成套装，按容量和使用场景给出清晰的升级梯度")
        elif category_play == "pet_food":
            product_parts.append("以猫粮主款搭配多周期装或补货组合，按预计消耗周期提供 30/60 天选择，减少断粮风险")
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
        if question_focus["push"]:
            if question_focus["timing"]:
                promo_parts.append("建议在用户历史活跃时段前 1 小时发送首触达；未打开者 24 小时后仅补发 1 次，7 天内同类消息不超过 2 次")
            else:
                promo_parts.append("采用分层 Push：高频人群推复购/升级，低频人群推低门槛权益；每次只绑定一个落地页动作并设置频控")
            if question_focus["copy"]:
                if "旅行" in question or "luggage" in question.lower() or "行李" in question:
                    promo_parts.append("旅行人群文案示例：‘出发前，把常用装备一次备齐’；按钮：‘查看旅行装备清单’；避免泛化为旅游兴趣推断")
                else:
                    promo_parts.append("文案结构使用‘人群场景 + 品类利益 + 单一行动’：例如‘你的咖啡豆快补货了｜查看本周复购权益’")
        if category_play == "coffee":
            promo_parts.append("咖啡豆采用第二件/组合装阶梯优惠与复购券，优先引导相邻口味尝鲜，避免对低客单人群直接投入高额补贴")
        elif category_play == "travel":
            promo_parts.append("旅行·luggage采用套装立减、配件加购优惠和分期/会员权益，减少单品降价，围绕高客单决策提供明确的购买理由")
        elif category_play == "pet_food":
            promo_parts.append("猫粮采用周期购、订阅优惠和提前补货提醒，高频用户给连续购买权益，避免只发一次性红包造成补贴浪费")
        if question_focus["page"] or question_focus["campaign"]:
            promo_parts.append("专题页/活动采用人群专属入口，首屏展示主品类权益，中段展示组合商品，底部以领取权益或加入购物车作为唯一主 CTA")
        if required_concepts:
            promo_parts.append("；".join(required_concepts))
        promotion_strategy = "；".join(promo_parts[:7])

        # 5) 效果指标：覆盖点击/加购/转化/客单/连带。
        metrics = [
            "点击率",
            "加购率",
            "转化率",
            "客单价提升",
            "连带购买率",
        ]
        if question_focus["push"]:
            metrics.extend(["Push送达率", "Push打开率", "Push点击率", "退订率"])
        if question_focus["page"] or question_focus["campaign"]:
            metrics.extend(["专题页到达率", "权益领取率", "页面 CTA 点击率"])
        if category_play == "coffee":
            metrics.extend(["咖啡豆复购率", "相邻口味尝鲜率", "组合装购买率"])
        elif category_play == "travel":
            metrics.extend(["套装购买率", "配件连带率", "高客单转化率"])
        elif category_play == "pet_food":
            metrics.extend(["周期购开通率", "30/60 天复购率", "断购率"])

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

        page = {
            "theme": f"{segment['name']}定向承接页",
            "visual_keywords": visual_keywords,
            "modules": ["人群权益", "品类推荐", "验证指标"],
            "hero_title": ad_theme,
            "hero_subtitle": opportunity,
            "emotional_direction": brand_tone or "清晰、可信、有行动感",
        }
        category_label = {
            "coffee": "咖啡豆",
            "travel": "旅行箱/旅行装备",
            "pet_food": "猫粮",
        }.get(category_play, dominant_cn if dominant else "该品类")

        # 业务问题是策略主线，不只是补充关键词。不同任务类型必须切换
        # 完整的执行方案，避免同一数据集的所有追问只得到换名后的通用卡片。
        if question_focus["push"]:
            push_category_plan = {
                "coffee": "围绕咖啡豆复购周期，在预计补货前 3 天提醒；优先推荐相邻口味尝鲜或常规装升级，按钮统一指向复购/换口味页。",
                "travel": "围绕旅行箱低频高客单决策，在用户浏览或购买相关品类后的 7 天内做一次装备补充提醒；优先推荐收纳、保护配件和套装，按钮指向旅行装备清单页。",
                "pet_food": "围绕猫粮消耗周期，在预计用尽前 5-7 天提醒；优先推荐周期装/订阅续购，按钮指向快速补货页，避免用泛化活动打扰高频用户。",
                "general": "围绕该人群最近购买品类和预计复购窗口触达，单次只推荐一个明确动作，避免泛化推送。",
            }[category_play]
            push_copy = (
                "文案示例：出发前，把旅行装备一次备齐｜查看装备清单"
                if category_play == "travel"
                else "文案结构：品类/场景提醒 + 具体利益 + 单一按钮"
            )
            opportunity = f"{category_label}人群 Push 触达机会：用消费节奏匹配发送时机，而不是统一群发。"
            marketing_goal = {
                "coffee": "把咖啡豆补货提醒转成复购与口味升级：优先提升补货点击、复购率和相邻口味尝鲜率。",
                "travel": "用旅行箱 Push 把低频高客单用户从单品浏览推进到旅行装备套装：优先提升清单点击、配件连带和套装成交。",
                "pet_food": "把猫粮高频消耗转成稳定补货习惯：优先提升补货点击、周期购开通和 30/60 天连续复购。",
                "general": "提升 Push 打开与点击，并把点击转化为一个明确的复购、补货或组合购买动作。",
            }[category_play]
            content_strategy = f"{push_category_plan} {push_copy}"
            promotion_strategy = "首次触达在历史活跃时段前 1 小时发送；未打开者 24 小时后最多补发 1 次；7 天内同类消息不超过 2 次，并提供退订/免打扰控制。"
            channels = {
                "coffee": ["APP Push（预计补货前3天）", "复购/换口味页", "站内信补发"],
                "travel": ["APP Push（浏览/购买后7天内）", "旅行装备清单页", "站内信补发"],
                "pet_food": ["APP Push（预计用尽前5-7天）", "快速补货/周期购页", "站内信补发"],
                "general": ["APP Push", "单一行动落地页", "站内信补发"],
            }[category_play]
            metrics = {
                "coffee": ["送达率", "补货点击率", "咖啡豆复购率", "相邻口味尝鲜率", "退订率"],
                "travel": ["送达率", "装备清单点击率", "配件连带率", "套装购买率", "退订率"],
                "pet_food": ["送达率", "补货点击率", "周期购开通率", "30/60天复购率", "断购率"],
                "general": ["送达率", "打开率", "点击率", "目标动作转化率", "退订率"],
            }[category_play]
            mechanisms = {
                "coffee": ["复购券", "相邻口味尝鲜装", "常规装升级权益"],
                "travel": ["套装立减", "配件加购优惠", "会员/分期权益"],
                "pet_food": ["周期购折扣", "订阅续购权益", "提前补货提醒"],
                "general": ["品类定向券", "组合优惠", "频控规则"],
            }[category_play]
            page = {
                **page,
                "theme": f"{category_label} Push 承接页",
                "modules": ["Push利益点", "品类/组合推荐", "单一CTA", "频控与退订"],
                "hero_title": ad_theme,
                "hero_subtitle": opportunity,
            }
        elif question_focus["page"] or question_focus["campaign"]:
            opportunity = f"{category_label}人群专题页承接机会：把人群差异转成页面内容、商品组合和行动路径。"
            marketing_goal = {
                "coffee": "用专题页把咖啡豆兴趣转成口味/规格升级：提升尝鲜装领取、咖啡豆加购和复购成交。",
                "travel": "用专题页降低旅行箱高客单比较成本：提升装备清单浏览、配件连带和套装成交，而非单纯打折。",
                "pet_food": "用专题页建立猫粮周期补货路径：提升补货权益领取、周期购开通和连续复购，降低断购率。",
                "general": "提升专题页到达后的权益领取、商品加购和活动转化，避免只追求曝光。",
            }[category_play]
            content_strategy = {
                "coffee": "首屏展示口味/烘焙度选择；中段放相邻口味尝鲜装与常规装升级路径；底部主CTA为‘选口味并复购’，避免泛化生活方式内容。",
                "travel": "首屏展示容量与出行场景对照；中段展示旅行箱、收纳和保护配件套装；底部主CTA为‘查看装备清单’，先解决比较成本再促成成交。",
                "pet_food": "首屏展示猫粮消耗周期；中段提供30/60天规格、周期购和补货提醒；底部主CTA为‘按周期补货’，避免只用一次性红包刺激。",
                "general": f"首屏展示{category_label}核心利益点；中段按人群特征展示商品/组合和使用理由；底部只保留一个主CTA。",
            }[category_play]
            promotion_strategy = {
                "coffee": "用第二件/组合装阶梯优惠和复购券承接，尝鲜装负责降低试错，常规装负责提升复购，不对低客单人群投入高额补贴。",
                "travel": "用套装立减、配件加购和会员/分期权益降低高客单决策压力，保持主品价格心智，不用全场券替代商品组合。",
                "pet_food": "用周期购折扣、订阅续购和提前补货权益锁定消耗周期，把补贴绑定到连续购买，不只发一次性红包。",
                "general": f"为{category_label}设置专属权益；按到达、领取、加购、成交漏斗优化，不复用其他人群的通用话术。",
            }[category_play]
            channels = {
                "coffee": ["咖啡豆口味专题页", "复购提醒Push", "站内信复购召回"],
                "travel": ["旅行装备清单页", "高客单浏览召回Push", "会员/内容频道"],
                "pet_food": ["猫粮周期补货页", "预计用尽提醒Push", "订阅续购入口"],
                "general": ["人群专题页", "APP Push 引流", "站内信召回"],
            }[category_play]
            metrics = {
                "coffee": ["口味选择点击率", "尝鲜装领取率", "咖啡豆加购率", "复购率", "组合装购买率"],
                "travel": ["装备清单到达率", "容量筛选使用率", "配件加购率", "套装购买率", "高客单转化率"],
                "pet_food": ["补货页到达率", "周期购开通率", "30/60天复购率", "断购率", "连续购买率"],
                "general": ["专题页到达率", "权益领取率", "商品加购率", "活动转化率", "客单/连带提升"],
            }[category_play]
            mechanisms = {
                "coffee": ["口味尝鲜装", "复购券", "组合装阶梯优惠"],
                "travel": ["套装立减", "配件加购", "会员/分期权益"],
                "pet_food": ["30/60天周期购", "订阅续购优惠", "提前补货权益"],
                "general": ["人群专属权益", "组合优惠", "漏斗分层优化"],
            }[category_play]
            page = {
                **page,
                "theme": f"{category_label}人群专题页",
                "modules": ["人群利益点", "专属商品组合", "权益说明", "行动CTA", "验证指标"],
                "hero_title": ad_theme,
                "hero_subtitle": opportunity,
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
            "page": page,
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

        question_text = str(state.get("question", ""))
        open_task = any(token in question_text for token in ("打开页", "落地页", "页面设计", "视觉风格", "首页"))
        # Push、专题页、营销活动、时点/文案等问题需要严格执行上面的
        # 任务型策略分流。不要让通用 LLM 改写成同一套模板，否则不同
        # 业务问题最终只剩下人群名称不同。
        deterministic_task = any(token in question_text.lower() for token in (
            "push", "推送", "专题页", "落地页", "页面", "营销活动", "活动",
            "发送时点", "频控", "文案", "话术", "承接",
        ))
        if (not deterministic_task and (settings.llm_enhance_strategy or (settings.llm_fallback_open_tasks and open_task))
                and self.llm.enabled and cards):
            try:
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
            except Exception as exc:
                logger.warning("Strategy LLM enhancement failed; using deterministic fallback: %s", exc)

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
