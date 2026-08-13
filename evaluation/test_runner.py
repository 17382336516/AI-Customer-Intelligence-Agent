from __future__ import annotations

import unittest

from evaluation.runner import (
    _DATASET_IDS,
    _INPUT_FIELDS,
    _LABEL_FIELDS,
    _failed_cases,
    _validate_inputs,
    evaluate_question,
)


class EvaluationRunnerSmokeTest(unittest.TestCase):
    def test_formal_input_contract_and_label_isolation(self) -> None:
        benchmark_rows = [{field: "" for field in _INPUT_FIELDS}]
        benchmark_rows[0]["customer_id"] = "C1"
        labels = [{field: "" for field in _LABEL_FIELDS}]
        labels[0].update({"dataset_id": "dataset_01_general", "customer_id": "C1"})
        questions = []
        golden = []
        for dataset_id in sorted(_DATASET_IDS):
            for number in range(1, 16):
                question_id = f"{dataset_id}_q{number:02d}"
                questions.append(
                    {
                        "question_id": question_id,
                        "dataset_id": dataset_id,
                        "business_category": "用户增长",
                        "question": "测试问题",
                    }
                )
                golden.append(
                    {
                        "question_id": question_id,
                        "dataset_id": dataset_id,
                        "question": "测试问题",
                        "expected_segments": [],
                        "must_include_keywords": [],
                        "forbidden_keywords": [],
                        "expected_knowledge_sources": [],
                        "evidence_rules": [],
                        "risk_constraints": [],
                    }
                )

        _validate_inputs("dataset_01_general", benchmark_rows, labels, questions, golden)
        leaked_rows = [{**benchmark_rows[0], "lifecycle_ground_truth": "young_growth_user"}]
        with self.assertRaisesRegex(ValueError, "Ground Truth leaked"):
            _validate_inputs("dataset_01_general", leaked_rows, labels, questions, golden)

    def test_dataset_01_three_question_scoring(self) -> None:
        labels = [
            {
                "dataset_id": "dataset_01",
                "customer_id": "C1",
                "category_ground_truth": "电子产品偏好用户",
                "lifecycle_ground_truth": "young_growth_user",
            },
            {
                "dataset_id": "dataset_01",
                "customer_id": "C2",
                "category_ground_truth": "家居偏好用户",
                "lifecycle_ground_truth": "category_interest_user",
            },
        ]
        rows = [
            {
                "customer_id": "C1",
                "total_consumption": "100",
                "purchase_frequency": "2",
                "last_purchase_days": "5",
                "product_category": "电子产品",
            },
            {
                "customer_id": "C2",
                "total_consumption": "50",
                "purchase_frequency": "1",
                "last_purchase_days": "10",
                "product_category": "家居",
            },
        ]
        artifacts = {
            "data_agent": {
                "user_predictions": [
                    {"customer_id": "C1", "predicted_category": "electronics"},
                    {"customer_id": "C2", "predicted_category": "home"},
                ],
                "segment_distribution": [
                    {"category": "electronics", "user_count": 1, "share": 0.5},
                    {"category": "home", "user_count": 1, "share": 0.5},
                ],
            },
            "insight_agent": {
                "insight_records": [
                    {
                        "segment_name": "年轻成长用户",
                        "insight_text": "年轻用户消费活跃。",
                        "evidence_fields": [
                            "total_consumption",
                            "purchase_frequency",
                            "last_purchase_days",
                            "product_category",
                        ],
                        "statistics_reference": {
                            "main_category": "electronics",
                            "average_spend": 100,
                            "average_frequency": 2,
                            "average_recency": 5,
                            "average_income": None,
                        },
                    }
                ]
            },
            "knowledge_agent": {
                "retrieval_results": [
                    {
                        "document_source": "product/bi_bi_zan.md",
                        "rank": 1,
                        "retrieval_score": 0.9,
                        "retrieved_content": "低门槛产品机制",
                    }
                ]
            },
            "strategy_agent": {
                "strategy_records": [
                    {
                        "target_segment": "年轻成长用户",
                        "generated_strategy_text": (
                            "提升年轻用户转化\n"
                            "用低门槛内容说明产品价值\n"
                            "推荐低门槛攒钱产品\n"
                            "采用小额体验机制\n"
                            "APP push\n"
                            "首次转化率"
                        ),
                        "used_knowledge_sources": ["product/bi_bi_zan.md"],
                        "knowledge_applications": [
                            {
                                "document_source": "product/bi_bi_zan.md",
                                "applied_concept": "低门槛体验",
                                "strategy_field": "product_strategy",
                            }
                        ],
                    }
                ]
            },
        }
        aliases = {"young_growth_user": ["年轻成长用户", "青年潜力用户"]}
        golden = {
            "expected_segments": ["年轻成长用户"],
            "must_include_keywords": ["年轻用户", "低门槛"],
            "forbidden_keywords": ["保证收益"],
            "expected_knowledge_sources": ["product/bi_bi_zan.md"],
            "risk_constraints": ["不得保证收益"],
        }

        results = [
            evaluate_question(
                "dataset_01",
                f"dataset_01_q{number:02d}",
                artifacts,
                golden,
                labels,
                rows,
                aliases,
            )
            for number in range(1, 4)
        ]

        self.assertEqual(len(results), 3)
        self.assertTrue(all(item["e2e_pass"] for item in results))
        self.assertTrue(all(item["metrics"]["overall_score"] == 100 for item in results))
        self.assertEqual(_failed_cases(results), [])

        results[0]["metric_details"]["knowledge"]["recall_at_3"] = 50
        failure = _failed_cases(results)[0]
        self.assertEqual(failure["question_id"], "dataset_01_q01")
        self.assertEqual(failure["failed_metric"], "K1 Recall@3")


if __name__ == "__main__":
    unittest.main()
