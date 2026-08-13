from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "evaluation" / "reports"
DATASETS = ["dataset_01_general", "dataset_02_growth_campaign", "dataset_03_retention_interest"]
INPUT_FILES = ["evaluation_v7_dataset_01.json", "evaluation_v7_dataset_02.json", "evaluation_v7_dataset_03.json"]


def load_results():
    results = []
    for filename in INPUT_FILES:
        payload = json.loads((REPORTS / filename).read_text(encoding="utf-8"))
        results.extend(payload["results"])
    return results


def average(results, path):
    values = []
    for item in results:
        value = item
        for key in path:
            value = value[key]
        values.append(float(value))
    return round(sum(values) / len(values), 2)


def main():
    results = load_results()
    grounding_scores = []
    matched, failed = [], []
    for item in results:
        artifact = Path(item["artifact_path"]) / "strategy_agent.json"
        payload = json.loads(artifact.read_text(encoding="utf-8"))
        for record in payload.get("strategy_records", []):
            verification = record.get("strategy_verification", {})
            grounding_scores.append(float(verification.get("grounding_score", 0)))
            matched.extend(verification.get("matched_concepts", []))
            failed.extend(verification.get("failed_concepts", []))

    metric_details = {
        "D1_consumption_preference_accuracy": average(results, ("metric_details", "data", "consumption_preference_accuracy")),
        "D2_distribution_similarity": average(results, ("metric_details", "data", "distribution_similarity")),
        "I1_lifecycle_recognition": average(results, ("metric_details", "insight", "segment_recognition_rate")),
        "I2_insight_grounding": average(results, ("metric_details", "insight", "insight_grounding_rate")),
        "K1_recall_at_3": average(results, ("metric_details", "knowledge", "recall_at_3")),
        "K2_mrr": average(results, ("metric_details", "knowledge", "mrr")),
        "S1_golden_coverage": average(results, ("metric_details", "strategy", "golden_rule_coverage")),
        "S2_knowledge_adoption": average(results, ("metric_details", "strategy", "knowledge_adoption_rate")),
        "S3_risk_violation": average(results, ("metric_details", "strategy", "risk_violation_rate")),
    }
    scores = {
        "DataScore": average(results, ("metrics", "data_score")),
        "InsightScore": average(results, ("metrics", "insight_score")),
        "KnowledgeScore": average(results, ("metrics", "knowledge_score")),
        "StrategyScore": average(results, ("metrics", "strategy_score")),
        "OverallScore": average(results, ("metrics", "overall_score")),
    }
    grounding = {
        "average": round(sum(grounding_scores) / len(grounding_scores) * 100, 2),
        "minimum": round(min(grounding_scores) * 100, 2),
        "maximum": round(max(grounding_scores) * 100, 2),
        "failed_record_count": sum(score < 1 for score in grounding_scores),
        "record_count": len(grounding_scores),
        "matched_concepts": matched,
        "failed_concepts": failed,
        "match_type_counts": dict(Counter(item.get("match_type", "") for item in matched)),
        "failure_reason_counts": dict(Counter(item.get("reason", "") for item in failed)),
    }
    metadata = {
        "evaluation_run_id": f"evaluation_v7_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "evaluation_version": "v7",
        "benchmark_version": "v1",
        "model_mode": "deterministic_fallback",
        "model_version": "qwen3.7-plus",
        "prompt_version": "v1",
        "knowledge_base_version": "enterprise_rag_v3",
        "grounding_version": "business_concept_alignment_v2",
        "evaluation_time": datetime.now(timezone.utc).isoformat(),
        "datasets": DATASETS,
        "questions": len(results),
    }
    (REPORTS / "evaluation_run_metadata_v7.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    output = {
        "evaluation_run_metadata": metadata,
        "scope": {"datasets": DATASETS, "questions": len(results), "users": 12000},
        "metrics": {**metric_details, **scores, "GroundingScore": grounding["average"]},
        "e2e_pass_rate": round(sum(bool(item["e2e_pass"]) for item in results) / len(results) * 100, 2),
        "e2e_pass_count": sum(bool(item["e2e_pass"]) for item in results),
        "grounding": grounding,
        "dataset_summaries": {
            dataset_id: {
                "questions": len([x for x in results if x["dataset_id"] == dataset_id]),
                "average_overall_score": average([x for x in results if x["dataset_id"] == dataset_id], ("metrics", "overall_score")),
                "e2e_pass_count": sum(bool(x["e2e_pass"]) for x in results if x["dataset_id"] == dataset_id),
            } for dataset_id in DATASETS
        },
        "question_results": results,
    }
    (REPORTS / "evaluation_v7_results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    comparison = """# Evaluation v6 vs v7\n\n|指标|v6|v7|变化|\n|-|-|-|-|\n|DataScore|93.43|93.43|0.00|\n|InsightScore|100.00|100.00|0.00|\n|KnowledgeScore|65.17|65.17|0.00|\n|StrategyScore|75.37|75.37|0.00|\n|OverallScore|83.10|83.10|0.00|\n|E2E Pass Rate|15.56%|13.33%|-2.23pp|\n|Grounding Score（v6 q01-q03基线）|54.44%|89.63%（全45题）|+35.19pp*|\n\n*Grounding 的 v6 数值来自 q01-q03 traceability smoke test，v7 为完整45题统计，范围不同，不能当作严格同口径提升。v7 未修改Evaluator，因此核心分数保持不变；E2E差异来自本次完整运行的真实题目结果。\n"""
    (REPORTS / "evaluation_v6_v7_comparison.md").write_text(comparison, encoding="utf-8")

    failure = f"""# Failure Analysis v7\n\n## 总览\n\n- 题目数：45\n- E2E通过：{sum(bool(item['e2e_pass']) for item in results)}/45（{output['e2e_pass_rate']}%）\n- Grounding记录：{grounding['record_count']}，平均 {grounding['average']}%，最低 {grounding['minimum']}%，最高 {grounding['maximum']}%\n- Grounding未完全通过记录：{grounding['failed_record_count']}\n\n## Grounding失败模式\n\n|模式|判断|\n|-|-|\n|knowledge retrieved but not applied|由 failed_concepts 中未找到字段语义匹配的记录体现；不能把召回自动算采用。|\n|concept matched but strategy field missing|需要同时满足 related_strategy_fields 和字段文本匹配，本轮仍有部分失败。|\n|strategy generated without knowledge support|source 不在真实 retrieval/evidence 中的追踪不会计入 verified。|\n|alias missing|仍有未覆盖的企业概念表达，主要表现为字段内语义匹配失败。|\n\n失败原因计数：`{json.dumps(grounding['failure_reason_counts'], ensure_ascii=False)}`。匹配类型：`{json.dumps(grounding['match_type_counts'], ensure_ascii=False)}`。\n\n## Knowledge失败模式\n\n完整评估的平均 Recall@3 为 {metric_details['K1_recall_at_3']}%，MRR 为 {metric_details['K2_mrr']}%。失败仍集中在正确 primary source 未进入 Top3；这属于检索覆盖问题，不是 grounding verifier 造成。\n\n## Strategy失败模式\n\nS1 Golden Coverage 为 {metric_details['S1_golden_coverage']}%，S2 Knowledge Adoption 为 {metric_details['S2_knowledge_adoption']}%。部分策略字段和业务关键词覆盖不足；但本轮未修改 Strategy 生成逻辑。\n\n## 新瓶颈判断\n\nData 与 Insight 已稳定（分别为 {scores['DataScore']} 和 {scores['InsightScore']}）。当前主要瓶颈仍是 Knowledge Retrieval 与 Strategy Requirement Coverage；Grounding 对 q01-q03 的提升已在完整45题中保持较高平均值，但仍存在业务概念边界case。\n"""
    (REPORTS / "failure_analysis_v7.md").write_text(failure, encoding="utf-8")

    resume = f"""# Resume Metrics v3\n\n构建企业级 Customer Intelligence Agent Evaluation Framework，基于 3 套 Benchmark 数据集、12000 用户和 45 个营销任务。\n\n- Consumption Preference Accuracy：{metric_details['D1_consumption_preference_accuracy']}%\n- Insight Grounding：{metric_details['I2_insight_grounding']}%\n- Enterprise RAG Recall@3：{metric_details['K1_recall_at_3']}%\n- Knowledge → Strategy Grounding：{grounding['average']}%\n- Strategy Golden Coverage：{metric_details['S1_golden_coverage']}%\n- Overall Score：{scores['OverallScore']}\n- E2E Pass Rate：{output['e2e_pass_rate']}%\n\n实验模式：deterministic_fallback；以上为离线 Evaluation baseline，不代表线上商业收益或真实转化提升。\n"""
    (REPORTS / "resume_metrics_v3.md").write_text(resume, encoding="utf-8")


if __name__ == "__main__":
    main()
