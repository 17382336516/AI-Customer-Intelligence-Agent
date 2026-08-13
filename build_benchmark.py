"""Build three leak-free benchmark datasets, 45 questions and Golden Labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from augment_customer_features import (
    INPUT_COLUMNS,
    build_augmented_dataset,
    load_behavior_summary,
    validate_isolation,
)

MAX_FILE_BYTES = 24 * 1024 * 1024
SOURCE = {
    "name": "淘宝APP用户行为数据集（阿里巴巴移动电商推荐算法大赛）",
    "dataset_url": "https://tianchi.aliyun.com/dataset/dataDetail?dataId=46",
    "competition_url": "https://tianchi.aliyun.com/competition/entrance/532043/information",
    "source_type": "public_real_behavior_plus_business_enhancement",
}

SCENARIOS = [
    {
        "dataset_id": "dataset_01_general",
        "name": "综合消费基准",
        "seed_offset": 0,
        "ratios": {
            "high_value": 0.19,
            "young_growth": 0.31,
            "price_sensitive": 0.20,
            "category_interest": 0.17,
            "scenario_churn": 0.13,
        },
    },
    {
        "dataset_id": "dataset_02_growth_campaign",
        "name": "年轻增长与促销基准",
        "seed_offset": 101,
        "ratios": {
            "high_value": 0.17,
            "young_growth": 0.35,
            "price_sensitive": 0.22,
            "category_interest": 0.16,
            "scenario_churn": 0.10,
        },
    },
    {
        "dataset_id": "dataset_03_retention_interest",
        "name": "留存与品类兴趣基准",
        "seed_offset": 202,
        "ratios": {
            "high_value": 0.24,
            "young_growth": 0.26,
            "price_sensitive": 0.16,
            "category_interest": 0.19,
            "scenario_churn": 0.15,
        },
    },
]

QUESTION_SPECS: list[dict[str, Any]] = [
    {
        "type": "用户增长",
        "question": "如何提升{scenario}中年轻成长用户的首次转化和持续参与？",
        "segments": ["年轻成长用户"],
        "must": ["年轻用户", "低门槛", "持续参与"],
        "forbidden": ["保证收益", "稳赚不赔"],
        "sources": ["user_growth/young_user_growth.md", "product/bi_bi_zan.md"],
        "evidence": ["引用年轻用户年龄、频次或客单价证据", "策略与低门槛产品机制对应"],
    },
    {
        "type": "用户增长",
        "question": "{scenario}中哪些用户适合新品冷启动，应该如何降低尝试门槛？",
        "segments": ["年轻成长用户", "品类兴趣用户"],
        "must": ["新品", "兴趣匹配", "低门槛"],
        "forbidden": ["全量用户无差别触达", "虚构转化率"],
        "sources": [],
        "evidence": ["使用品类偏好和活跃度筛选人群", "说明试投放与验证指标"],
    },
    {
        "type": "用户增长",
        "question": "如何在{scenario}中识别并运营年轻、非一线城市的潜力用户？",
        "segments": ["年轻成长用户"],
        "must": ["年轻用户", "城市", "信任", "分层运营"],
        "forbidden": ["地域歧视", "推断职业"],
        "sources": ["brand/brand_profile.md", "marketing_case/case_001.md"],
        "evidence": ["同时使用年龄、城市和消费活跃证据", "不得把城市直接等同于收入"],
    },
    {
        "type": "复购提升",
        "question": "如何提升{scenario}中高价值用户的复购并避免过度补贴？",
        "segments": ["高价值用户"],
        "must": ["高价值用户", "复购", "权益", "补贴控制"],
        "forbidden": ["大额无差别优惠", "虚构ROI"],
        "sources": ["operation_rule/marketing_rule.md"],
        "evidence": ["引用总消费、客单价和购买频次", "权益必须与用户价值相匹配"],
    },
    {
        "type": "复购提升",
        "question": "{scenario}中哪些用户适合会员升级运营，如何设置触发条件？",
        "segments": ["高价值用户", "品类兴趣用户"],
        "must": ["会员", "频次", "客单价", "触发条件"],
        "forbidden": ["自动承诺升级", "未提供的会员成本"],
        "sources": [],
        "evidence": ["给出可由数据字段验证的会员筛选规则", "区分高价值和兴趣专一用户"],
    },
    {
        "type": "复购提升",
        "question": "如何提升{scenario}中价格敏感用户的复购而不形成优惠依赖？",
        "segments": ["价格敏感用户"],
        "must": ["优惠券", "价格敏感", "复购", "分阶段"],
        "forbidden": ["永久低价", "无限补贴"],
        "sources": ["operation_rule/marketing_rule.md"],
        "evidence": ["引用优惠券使用和平均客单价", "包含优惠退出或递减机制"],
    },
    {
        "type": "用户召回",
        "question": "如何召回{scenario}中的长期未购用户，并控制打扰风险？",
        "segments": ["scenario_enhanced_churn_user"],
        "must": ["长期未购", "召回", "分层触达", "频控"],
        "forbidden": ["真实流失用户", "高频轰炸"],
        "sources": ["operation_rule/marketing_rule.md"],
        "evidence": ["明确该人群是场景增强标签", "使用最近购买天数作为召回证据"],
    },
    {
        "type": "用户召回",
        "question": "{scenario}中哪些长期未购用户值得优先召回？",
        "segments": ["scenario_enhanced_churn_user", "高价值用户"],
        "must": ["历史价值", "最近购买天数", "召回优先级"],
        "forbidden": ["所有沉默用户同一策略", "保证召回成功"],
        "sources": [],
        "evidence": ["综合历史消费和最近购买天数排序", "不能只按单一字段下结论"],
    },
    {
        "type": "用户召回",
        "question": "如何用历史品类偏好召回{scenario}中的长期未购用户？",
        "segments": ["scenario_enhanced_churn_user", "品类兴趣用户"],
        "must": ["历史偏好", "个性化召回", "品类"],
        "forbidden": ["无关品类推荐", "敏感属性推断"],
        "sources": [],
        "evidence": ["召回商品必须匹配category_ground_truth", "提出小流量验证方案"],
    },
    {
        "type": "活动运营",
        "question": "{scenario}中哪些用户适合618活动，权益应如何分层？",
        "segments": ["高价值用户", "年轻成长用户", "价格敏感用户"],
        "must": ["618", "分层权益", "高价值", "价格敏感"],
        "forbidden": ["全员同券", "虚构活动预算"],
        "sources": [],
        "evidence": ["至少区分三类人群的权益差异", "给出活动效果验证指标"],
    },
    {
        "type": "活动运营",
        "question": "如何为{scenario}设计兼顾年轻用户与家庭用户的春节活动？",
        "segments": ["年轻成长用户", "高价值用户"],
        "must": ["春节", "年轻用户", "家庭场景", "攒钱"],
        "forbidden": ["承诺固定收益", "照搬案例数据"],
        "sources": ["marketing_case/case_003.md", "product/xiao_zhu_zan_qian_guan.md"],
        "evidence": ["说明案例机制如何迁移而非直接复制", "策略需连接具体用户证据"],
    },
    {
        "type": "活动运营",
        "question": "{scenario}适合怎样的年轻化周年节点活动？",
        "segments": ["年轻成长用户", "品类兴趣用户"],
        "must": ["年轻化", "节点", "仪式感", "社交传播"],
        "forbidden": ["虚构品牌历史", "夸大传播效果"],
        "sources": ["marketing_case/case_002.md", "marketing_case/case_006.md"],
        "evidence": ["引用可复用的节点机制", "包含明确的实验或传播指标"],
    },
    {
        "type": "商品推荐",
        "question": "{scenario}中哪些用户适合电子产品新品推荐？",
        "segments": ["年轻成长用户", "品类兴趣用户"],
        "categories": ["电子产品偏好用户"],
        "must": ["电子产品", "品类偏好", "年轻用户"],
        "forbidden": ["向无偏好用户强推", "虚构设备品牌偏好"],
        "sources": [],
        "evidence": ["使用真实主消费品类和年龄证据", "区分偏好证据与品牌猜测"],
    },
    {
        "type": "商品推荐",
        "question": "如何为{scenario}中的美妆或家居兴趣用户做关联推荐？",
        "segments": ["品类兴趣用户"],
        "categories": ["美妆偏好用户", "家居偏好用户"],
        "must": ["品类兴趣", "关联推荐", "客单价"],
        "forbidden": ["推断性别决定美妆需求", "跨品类无依据推荐"],
        "sources": [],
        "evidence": ["根据category_ground_truth选择目标用户", "不得使用性别刻板印象"],
    },
    {
        "type": "商品推荐",
        "question": "基于{scenario}的消费行为，哪些用户适合推荐低门槛攒钱产品？",
        "segments": ["年轻成长用户", "价格敏感用户"],
        "must": ["低门槛", "笔笔攒", "目标储蓄", "消费行为"],
        "forbidden": ["保本承诺", "固定高收益", "高风险杠杆"],
        "sources": [
            "product/bi_bi_zan.md",
            "product/xiao_zhu_zan_qian_guan.md",
            "product/yu_e_bao.md",
            "operation_rule/marketing_rule.md",
        ],
        "evidence": ["将产品机制与消费频次或客单价对应", "说明金融营销限制"],
    },
]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def questions_and_golden(scenario: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    questions: list[dict[str, Any]] = []
    golden: list[dict[str, Any]] = []
    common_risks = ["不得虚构数据集中不存在的指标", "不得推断敏感身份属性"]
    for number, spec in enumerate(QUESTION_SPECS, start=1):
        question_id = f"{scenario['dataset_id']}_q{number:02d}"
        question = spec["question"].format(scenario=scenario["name"])
        questions.append(
            {
                "question_id": question_id,
                "dataset_id": scenario["dataset_id"],
                "business_category": spec["type"],
                "question": question,
            }
        )
        golden.append(
            {
                "question_id": question_id,
                "dataset_id": scenario["dataset_id"],
                "question": question,
                "expected_segments": spec["segments"],
                "expected_category_ground_truth": spec.get("categories", []),
                "must_include_keywords": spec["must"],
                "forbidden_keywords": spec["forbidden"],
                "expected_knowledge_sources": spec["sources"],
                "evidence_rules": spec["evidence"],
                "risk_constraints": common_risks + spec["forbidden"],
            }
        )
    return questions, golden


def validate_output(path: Path, frame: pd.DataFrame, labels: pd.DataFrame) -> None:
    size = path.stat().st_size
    users = frame["customer_id"].nunique()
    if not 3_000 <= users <= 5_000:
        raise AssertionError(f"User count out of range: {users}")
    if not 10_000 <= len(frame) <= 30_000:
        raise AssertionError(f"Order count out of range: {len(frame)}")
    if not 20 <= len(frame.columns) <= 25:
        raise AssertionError(f"Column count out of range: {len(frame.columns)}")
    if size > MAX_FILE_BYTES:
        raise AssertionError(f"Upload file exceeds the 24 MiB safety limit: {size} bytes")
    if not frame["amount"].equals(frame["purchase_amount"]):
        raise AssertionError("amount compatibility field differs from purchase_amount")
    if not frame["event_time"].equals(frame["purchase_date"]):
        raise AssertionError("event_time compatibility field differs from purchase_date")
    if not frame["category"].equals(frame["product_category"]):
        raise AssertionError("category compatibility field differs from product_category")
    if users != labels["customer_id"].nunique():
        raise AssertionError("Input and label files contain different customer counts")


def build(cleaned: Path, output_root: Path, total_users: int, seed: int) -> dict[str, Any]:
    summary = load_behavior_summary(cleaned)
    output_root.mkdir(parents=True, exist_ok=True)
    metadata_entries: list[dict[str, Any]] = []
    all_questions: list[dict[str, Any]] = []
    all_golden: list[dict[str, Any]] = []

    for scenario in SCENARIOS:
        dataset_seed = seed + scenario["seed_offset"]
        frame, labels, diagnostics = build_augmented_dataset(
            summary,
            scenario["dataset_id"],
            scenario["ratios"],
            total_users=total_users,
            seed=dataset_seed,
        )
        validate_isolation(frame, labels)
        dataset_dir = output_root / scenario["dataset_id"]
        dataset_dir.mkdir(parents=True, exist_ok=True)
        input_path = dataset_dir / "customer_behavior_benchmark_input.csv"
        label_path = dataset_dir / "benchmark_labels.csv"
        frame.to_csv(input_path, index=False, encoding="utf-8-sig")
        labels.to_csv(label_path, index=False, encoding="utf-8-sig")
        validate_output(input_path, frame, labels)

        questions, golden = questions_and_golden(scenario)
        all_questions.extend(questions)
        all_golden.extend(golden)
        total_label_users = max(1, len(labels))
        lifecycle_segments = [
            {
                "segment_name": name,
                "proportion": round(count / total_label_users, 4),
                "user_count": int(count),
                "characteristics": "scenario_enhanced"
                if name == "scenario_enhanced_churn_user"
                else "rule_derived_from_behavior_and_business_enhancement",
            }
            for name, count in labels["lifecycle_ground_truth"].value_counts().items()
        ]
        metadata_entries.append(
            {
                "dataset_id": scenario["dataset_id"],
                "dataset_name": scenario["name"],
                "source": SOURCE,
                "total_users": int(frame["customer_id"].nunique()),
                "total_orders": len(frame),
                "file_size": f"{input_path.stat().st_size / 1024 / 1024:.2f} MiB",
                "file_size_bytes": input_path.stat().st_size,
                "field_count": len(INPUT_COLUMNS),
                "segments": lifecycle_segments,
                "category_segments": diagnostics["category_distribution"],
                "business_questions": [item["question_id"] for item in questions],
                "business_test_targets": [
                    "Data Agent商品偏好分群准确性",
                    "Insight Agent生命周期理解真实性",
                    "Enterprise Knowledge RAG召回与引用",
                    "Strategy Agent策略匹配与风险控制",
                ],
                "scenario_enhanced_churn_user_note": (
                    "该标签为业务场景增强，不代表原始数据中的真实流失用户；"
                    "用户内部行为间隔保留，但历史时间块被平移至观察日前91至180天。"
                ),
                "label_isolation": (
                    "上传文件不包含ground_truth_segment、category_ground_truth或"
                    "lifecycle_ground_truth；标签仅保存在benchmark_labels.csv。"
                ),
            }
        )

    if len(all_questions) != 45 or len(all_golden) != 45:
        raise AssertionError("Expected exactly 45 business questions and Golden Labels.")
    type_counts = pd.Series([item["business_category"] for item in all_questions]).value_counts()
    if any(type_counts.get(category, 0) != 9 for category in ("用户增长", "复购提升", "用户召回", "活动运营", "商品推荐")):
        raise AssertionError("Each business category must contain exactly nine questions across three datasets.")

    metadata = {
        "dataset_name": "customer_intelligence_agent_benchmark_v1",
        "source": SOURCE,
        "dataset_count": len(metadata_entries),
        "total_users": sum(item["total_users"] for item in metadata_entries),
        "total_orders": sum(item["total_orders"] for item in metadata_entries),
        "file_size": f"{sum(item['file_size_bytes'] for item in metadata_entries) / 1024 / 1024:.2f} MiB",
        "segments": sorted(
            {segment["segment_name"] for item in metadata_entries for segment in item["segments"]}
        ),
        "business_questions": [item["question_id"] for item in all_questions],
        "datasets": metadata_entries,
        "field_lineage": {
            "source_derived": ["customer_id", "order_id"],
            "derived": [
                "purchase_frequency",
                "total_consumption",
                "average_order_value",
                "category_diversity",
                "activity_frequency",
            ],
            "scenario_time_enhanced": ["purchase_date", "last_purchase_days"],
            "business_enhanced": [
                "age",
                "gender",
                "city",
                "income_level",
                "membership_level",
                "product_category",
                "product_brand",
                "product_name",
                "purchase_amount",
                "quantity",
                "coupon_usage",
                "preferred_channel",
            ],
            "lineage_note": (
                "真实user_id、item_id、behavior_type和时间顺序保存在processed数据；"
                "最终ID经过稳定脱敏，purchase_date按场景整体平移，业务类目和金额为增强字段。"
            ),
        },
    }
    write_json(output_root / "benchmark_metadata.json", metadata)
    write_json(output_root / "benchmark_business_questions.json", all_questions)
    write_json(output_root / "golden_labels.json", all_golden)
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the three-dataset Evaluation Benchmark.")
    parser.add_argument(
        "cleaned",
        type=Path,
        nargs="?",
        default=Path("data/processed/taobao_behavior_clean.csv"),
    )
    parser.add_argument("--output-root", type=Path, default=Path("data/benchmark"))
    parser.add_argument("--users", type=int, default=4_000)
    parser.add_argument("--seed", type=int, default=20260810)
    args = parser.parse_args()

    metadata = build(args.cleaned, args.output_root, args.users, args.seed)
    print(json.dumps({"output": str(args.output_root.resolve()), **metadata}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
