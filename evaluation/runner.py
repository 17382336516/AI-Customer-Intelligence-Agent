from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
ARTIFACT_ROOT = ROOT / "evaluation" / "reports" / "artifacts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.agents import (
    DataAgent,
    InsightAgent,
    KnowledgeAgent,
    StrategyAgent,
)
from app.config import settings
from app.database import Base, Repository

from evaluation.evaluators.data_evaluator import evaluate as evaluate_data
from evaluation.evaluators.insight_evaluator import evaluate as evaluate_insight
from evaluation.evaluators.knowledge_evaluator import evaluate as evaluate_knowledge
from evaluation.evaluators.strategy_evaluator import evaluate as evaluate_strategy

_FAILURE_RULES = (
    (
        "D1 Consumption Preference Accuracy",
        "data",
        "consumption_preference_accuracy",
        80.0,
        "min",
        "检查品类归一化、用户级预测和category_ground_truth映射。",
    ),
    (
        "D2 Distribution Similarity",
        "data",
        "distribution_similarity",
        85.0,
        "min",
        "检查分群占比与Benchmark标签分布差异。",
    ),
    (
        "I1 Segment Recognition Rate",
        "insight",
        "segment_recognition_rate",
        80.0,
        "min",
        "检查生命周期标签输出和segment_alias_mapping归一化结果。",
    ),
    (
        "I2 Insight Grounding Rate",
        "insight",
        "insight_grounding_rate",
        90.0,
        "min",
        "检查洞察证据字段和statistics_reference是否来自真实统计。",
    ),
    (
        "K1 Recall@3",
        "knowledge",
        "recall_at_3",
        80.0,
        "min",
        "检查查询表达、知识文档路径和Golden知识源配置。",
    ),
    (
        "K2 MRR",
        "knowledge",
        "mrr",
        60.0,
        "min",
        "检查正确知识文档是否出现在更靠前的检索位置。",
    ),
    (
        "S1 Strategy Golden Rule Coverage",
        "strategy",
        "golden_rule_coverage",
        85.0,
        "min",
        "检查目标人群、商品机制、内容、渠道、指标和必含关键词。",
    ),
    (
        "S2 Knowledge Adoption Rate",
        "strategy",
        "knowledge_adoption_rate",
        80.0,
        "min",
        "检查knowledge_applications是否包含Golden知识源、采用概念和策略字段。",
    ),
    (
        "S3 Risk Violation Rate",
        "strategy",
        "risk_violation_rate",
        0.0,
        "max",
        "检查命中的禁止词和风险约束，避免不合规策略表达。",
    ),
    (
        "OverallScore",
        "metrics",
        "overall_score",
        80.0,
        "min",
        "按分项失败指标定位短板后重新验证完整链路。",
    ),
)

_DATASET_IDS = {
    "dataset_01_general",
    "dataset_02_growth_campaign",
    "dataset_03_retention_interest",
}
_INPUT_FIELDS = {
    "customer_id",
    "age",
    "gender",
    "city",
    "income_level",
    "membership_level",
    "order_id",
    "purchase_date",
    "product_category",
    "product_brand",
    "product_name",
    "purchase_amount",
    "quantity",
    "purchase_frequency",
    "total_consumption",
    "average_order_value",
    "last_purchase_days",
    "category_diversity",
    "coupon_usage",
    "activity_frequency",
    "preferred_channel",
    "amount",
    "event_time",
    "category",
}
_LABEL_FIELDS = {
    "dataset_id",
    "customer_id",
    "category_ground_truth",
    "lifecycle_ground_truth",
    "label_source",
}
_LEAKAGE_FIELDS = {
    "ground_truth_segment",
    "category_ground_truth",
    "lifecycle_ground_truth",
}
_QUESTION_FIELDS = {"question_id", "dataset_id", "business_category", "question"}
_GOLDEN_FIELDS = {
    "question_id",
    "dataset_id",
    "question",
    "expected_segments",
    "must_include_keywords",
    "forbidden_keywords",
    "expected_knowledge_sources",
    "evidence_rules",
    "risk_constraints",
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _select_dataset_id(labels: list[dict[str, str]], requested: str) -> str:
    available = sorted({row.get("dataset_id", "") for row in labels if row.get("dataset_id")})
    if requested in available:
        return requested
    matches = [item for item in available if item.startswith(requested)]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"Dataset {requested!r} not found; available={available}")


def _validate_inputs(
    dataset_id: str,
    benchmark_rows: list[dict[str, str]],
    labels: list[dict[str, str]],
    questions: list[dict[str, Any]],
    golden: list[dict[str, Any]],
) -> None:
    if not benchmark_rows or not labels:
        raise ValueError("Benchmark input and labels must both contain data rows.")
    input_fields = set(benchmark_rows[0])
    label_fields = set(labels[0])
    leaked = input_fields & _LEAKAGE_FIELDS
    if leaked:
        raise ValueError(f"Ground Truth leaked into benchmark input: {sorted(leaked)}")
    if input_fields != _INPUT_FIELDS:
        raise ValueError(f"Benchmark input fields mismatch: missing={sorted(_INPUT_FIELDS - input_fields)}, extra={sorted(input_fields - _INPUT_FIELDS)}")
    if label_fields != _LABEL_FIELDS:
        raise ValueError(f"Benchmark label fields mismatch: missing={sorted(_LABEL_FIELDS - label_fields)}, extra={sorted(label_fields - _LABEL_FIELDS)}")

    input_users = {row["customer_id"] for row in benchmark_rows}
    label_users = [row["customer_id"] for row in labels]
    if len(label_users) != len(set(label_users)):
        raise ValueError("benchmark_labels.csv contains duplicate customer_id values.")
    if input_users != set(label_users):
        raise ValueError("Benchmark input and labels contain different customer_id sets.")
    if {row["dataset_id"] for row in labels} != {dataset_id}:
        raise ValueError("benchmark_labels.csv contains an unexpected dataset_id.")

    if len(questions) != 45 or len(golden) != 45:
        raise ValueError("Formal Benchmark requires exactly 45 questions and 45 Golden Labels.")
    if {item.get("dataset_id") for item in questions} != _DATASET_IDS:
        raise ValueError("Benchmark questions do not cover the three required dataset_id values.")
    if {item.get("dataset_id") for item in golden} != _DATASET_IDS:
        raise ValueError("Golden Labels do not cover the three required dataset_id values.")
    for item in questions:
        if not _QUESTION_FIELDS.issubset(item):
            raise ValueError(f"Question fields mismatch for {item.get('question_id', '<unknown>')}.")
    for item in golden:
        if not _GOLDEN_FIELDS.issubset(item):
            raise ValueError(f"Golden Label fields mismatch for {item.get('question_id', '<unknown>')}.")
    question_ids = [item["question_id"] for item in questions]
    golden_ids = [item["question_id"] for item in golden]
    if len(question_ids) != len(set(question_ids)) or len(golden_ids) != len(set(golden_ids)):
        raise ValueError("Question or Golden Label IDs are duplicated.")
    if set(question_ids) != set(golden_ids):
        raise ValueError("Benchmark questions and Golden Labels have different question_id sets.")


def _persist_artifacts(dataset_id: str, question_id: str, artifacts: dict[str, Any]) -> Path:
    output_dir = ARTIFACT_ROOT / dataset_id / question_id
    output_dir.mkdir(parents=True, exist_ok=True)
    for agent_name in ("data_agent", "insight_agent", "knowledge_agent", "strategy_agent"):
        (output_dir / f"{agent_name}.json").write_text(
            json.dumps(artifacts.get(agent_name, {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return output_dir


def execute_agents(
    dataset_id: str,
    dataset_path: Path,
    questions: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    outputs: dict[str, dict[str, Any]] = {}
    with Session(engine) as session:
        repository = Repository(session)
        data_agent = DataAgent(repository)
        insight_agent = InsightAgent(repository)
        knowledge_agent = KnowledgeAgent(repository)
        strategy_agent = StrategyAgent(repository)
        knowledge_documents_loaded = knowledge_agent.kb.document_count
        print(json.dumps({"knowledge_base_loaded_documents_count": knowledge_documents_loaded}))
        if knowledge_documents_loaded == 0:
            raise RuntimeError("Knowledge base loaded 0 documents; Evaluation stopped.")

        first = questions[0]
        first_analysis = repository.create_analysis(
            dataset_id=dataset_id,
            question=first["question"],
            strategy_goal="Benchmark Evaluation",
            brand_tone="",
            route="full_strategy",
        )
        data_output = data_agent.run(
            {
                "analysis_id": first_analysis.id,
                "dataset_id": dataset_id,
                "dataset_path": str(dataset_path),
                "route": "full_strategy",
            }
        )
        if data_output.get("blocked"):
            raise RuntimeError("Data Agent blocked the benchmark dataset; inspect its quality report.")

        for index, question in enumerate(questions):
            analysis = first_analysis if index == 0 else repository.create_analysis(
                dataset_id=dataset_id,
                question=question["question"],
                strategy_goal="Benchmark Evaluation",
                brand_tone="",
                route="full_strategy",
            )
            state = {
                **data_output,
                "analysis_id": analysis.id,
                "dataset_id": dataset_id,
                "dataset_path": str(dataset_path),
                "question": question["question"],
                "strategy_goal": "Benchmark Evaluation",
                "brand_tone": "",
                "route": "full_strategy",
                "model_mode": "deterministic",
            }
            insight_output = insight_agent.run(state)
            state.update(insight_output)
            knowledge_output = knowledge_agent.run(state)
            state.update(knowledge_output)
            strategy_output = strategy_agent.run(state)
            state.update(strategy_output)

            insight_records = insight_output.get("insight_agent_artifacts", {}).get("insight_records", [])
            raw_insights = insight_output.get("insights", [])
            enriched_records = []
            for record, raw in zip(insight_records, raw_insights):
                enriched_records.append(
                    {
                        **record,
                        **{
                            field: raw.get(field, [])
                            for field in ("top_tags", "value_tier", "behavior_profile", "recommended_actions")
                            if field in raw
                        },
                    }
                )
            artifacts = {
                "schema_version": "1.0",
                "data_agent": data_output.get("data_agent_artifacts", {}),
                "insight_agent": {
                    **insight_output.get("insight_agent_artifacts", {}),
                    "insight_records": enriched_records,
                },
                "knowledge_agent": knowledge_output.get("knowledge_agent_artifacts", {}),
                "strategy_agent": strategy_output.get("strategy_agent_artifacts", {}),
            }
            _persist_artifacts(dataset_id, question["question_id"], artifacts)
            repository.finish_analysis(
                analysis.id,
                {
                    "segments": data_output.get("segments", []),
                    "insights": insight_output.get("insights", []),
                    "knowledge_support": knowledge_output.get("knowledge_support", {}),
                    "strategy_cards": strategy_output.get("strategy_cards", []),
                    "evaluation_artifacts": artifacts,
                },
            )
            outputs[question["question_id"]] = artifacts
    return outputs, {"knowledge_documents_loaded": knowledge_documents_loaded}


def evaluate_question(
    dataset_id: str,
    question_id: str,
    artifacts: dict[str, Any],
    golden: dict[str, Any],
    labels: list[dict[str, str]],
    benchmark_rows: list[dict[str, str]],
    aliases: dict[str, list[str]],
) -> dict[str, Any]:
    data = evaluate_data(
        artifacts.get("data_agent", {}),
        labels,
        benchmark_customer_ids=sorted({str(row.get("customer_id", "")) for row in benchmark_rows}),
    )
    insight = evaluate_insight(
        artifacts.get("insight_agent", {}),
        golden,
        aliases,
        benchmark_rows,
        artifacts.get("data_agent", {}),
    )
    knowledge = evaluate_knowledge(artifacts.get("knowledge_agent", {}), golden)
    strategy = evaluate_strategy(artifacts.get("strategy_agent", {}), golden, aliases)
    overall = round(
        0.20 * data["data_score"]
        + 0.25 * insight["insight_score"]
        + 0.20 * knowledge["knowledge_score"]
        + 0.35 * strategy["strategy_score"],
        2,
    )
    e2e_pass = all(
        (
            data["consumption_preference_accuracy"] >= 80,
            data["distribution_similarity"] >= 85,
            insight["segment_recognition_rate"] >= 80,
            insight["insight_grounding_rate"] >= 90,
            knowledge["recall_at_3"] >= 80,
            strategy["golden_rule_coverage"] >= 85,
            strategy["risk_violation_rate"] == 0,
            overall >= 80,
        )
    )
    return {
        "dataset_id": dataset_id,
        "question_id": question_id,
        "metrics": {
            "data_score": data["data_score"],
            "insight_score": insight["insight_score"],
            "knowledge_score": knowledge["knowledge_score"],
            "strategy_score": strategy["strategy_score"],
            "overall_score": overall,
        },
        "metric_details": {
            "data": data,
            "insight": insight,
            "knowledge": knowledge,
            "strategy": strategy,
        },
        "e2e_pass": e2e_pass,
        "agent_status": {
            "data": True,
            "insight": True,
            "knowledge": True,
            "strategy": True,
        },
    }


def _failed_cases(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for result in results:
        for metric, section, field, threshold, direction, suggestion in _FAILURE_RULES:
            source = result["metrics"] if section == "metrics" else result["metric_details"][section]
            score = float(source[field])
            failed = score < threshold if direction == "min" else score > threshold
            if failed:
                comparator = "低于" if direction == "min" else "高于"
                failures.append(
                    {
                        "dataset_id": result["dataset_id"],
                        "question_id": result["question_id"],
                        "failed_metric": metric,
                        "score": score,
                        "reason": f"{metric}为{score:.2f}，{comparator}通过阈值{threshold:.2f}。",
                        "suggestion": suggestion,
                    }
                )
    return failures


def run(args: argparse.Namespace) -> dict[str, Any]:
    run_time = datetime.now(UTC).isoformat()
    dataset_path = args.dataset_dir / "customer_behavior_benchmark_input.csv"
    labels_path = args.dataset_dir / "benchmark_labels.csv"
    required = [dataset_path, labels_path, args.questions, args.golden, args.aliases]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Benchmark files missing: {missing}")

    all_labels = _csv(labels_path)
    dataset_id = _select_dataset_id(all_labels, args.dataset_id)
    labels = [row for row in all_labels if row.get("dataset_id") == dataset_id]
    benchmark_rows = _csv(dataset_path)
    all_questions = _json(args.questions)
    all_golden = _json(args.golden)
    _validate_inputs(dataset_id, benchmark_rows, labels, all_questions, all_golden)
    question_items = [
        item for item in all_questions if item.get("dataset_id") == dataset_id
    ][: args.limit]
    golden_by_id = {
        item["question_id"]: item
        for item in all_golden
        if item.get("dataset_id") == dataset_id
    }
    if not question_items:
        raise ValueError(f"No business questions found for {dataset_id}")
    missing_golden = [item["question_id"] for item in question_items if item["question_id"] not in golden_by_id]
    if missing_golden:
        raise ValueError(f"Golden Labels missing for questions: {missing_golden}")

    aliases = _json(args.aliases)
    artifacts_by_question, execution_meta = execute_agents(dataset_id, dataset_path, question_items)
    results = [
        evaluate_question(
            dataset_id,
            item["question_id"],
            artifacts_by_question[item["question_id"]],
            golden_by_id[item["question_id"]],
            labels,
            benchmark_rows,
            aliases,
        )
        for item in question_items
    ]
    for result in results:
        result["knowledge_documents_loaded"] = execution_meta["knowledge_documents_loaded"]
        result["artifact_path"] = str(ARTIFACT_ROOT / dataset_id / result["question_id"])
    report = {
        "schema_version": "1.0",
        "run_mode": "agent_execution",
        "evaluation_run_metadata": {
            "evaluation_version": args.evaluation_version,
            "dataset_version": args.dataset_version,
            "model_version": args.model_version,
            "prompt_version": args.prompt_version,
            "knowledge_base_version": args.knowledge_base_version,
            "run_time": run_time,
        },
        "dataset_id": dataset_id,
        "knowledge_base_loaded_documents_count": execution_meta["knowledge_documents_loaded"],
        "question_count": len(results),
        "generated_at": run_time,
        "summary": {
            "average_overall_score": round(mean(item["metrics"]["overall_score"] for item in results), 2),
            "e2e_pass_count": sum(item["e2e_pass"] for item in results),
            "e2e_pass_rate": round(sum(item["e2e_pass"] for item in results) / len(results) * 100, 2),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    args.failed_output.parent.mkdir(parents=True, exist_ok=True)
    args.failed_output.write_text(
        json.dumps(_failed_cases(results), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Evaluation Benchmark v1 for dataset_01.")
    parser.add_argument("--dataset-id", default="dataset_01")
    parser.add_argument(
        "--dataset-dir",
        type=Path,
        default=ROOT / "data/benchmark/dataset_01_general",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=ROOT / "data/benchmark/benchmark_business_questions.json",
    )
    parser.add_argument(
        "--golden",
        type=Path,
        default=ROOT / "data/benchmark/golden_labels.json",
    )
    parser.add_argument(
        "--aliases",
        type=Path,
        default=ROOT / "evaluation/segment_alias_mapping.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evaluation/reports/evaluation_results.json",
    )
    parser.add_argument(
        "--failed-output",
        type=Path,
        default=ROOT / "evaluation/reports/failed_cases.json",
    )
    parser.add_argument("--evaluation-version", default="1.0")
    parser.add_argument("--dataset-version", default="1.0")
    parser.add_argument("--model-version", default=settings.llm_model or "deterministic")
    parser.add_argument("--prompt-version", default="1.0")
    parser.add_argument("--knowledge-base-version", default="1.0")
    parser.add_argument("--limit", type=int, default=3, choices=range(1, 16))
    args = parser.parse_args()
    try:
        report = run(args)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
