from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def _source(value: Any) -> str:
    return str(PurePosixPath(str(value or "").replace("\\", "/"))).lower()


def evaluate(knowledge_artifacts: dict[str, Any], golden: dict[str, Any]) -> dict[str, float]:
    expected_set = golden.get("expected_knowledge_set") or []
    if expected_set:
        expected = {_source(item.get("source") if isinstance(item, dict) else item) for item in expected_set if item}
        primary = {
            _source(item.get("source") if isinstance(item, dict) else item)
            for item in expected_set
            if isinstance(item, dict) and item.get("relevance", "primary") == "primary"
        }
        secondary = {
            _source(item.get("source") if isinstance(item, dict) else item)
            for item in expected_set
            if isinstance(item, dict) and item.get("relevance") == "secondary"
        }
    else:
        expected = {_source(item) for item in golden.get("expected_knowledge_sources", []) if item}
        primary, secondary = expected, set()
    results = knowledge_artifacts.get("retrieval_results", [])
    ranked = [
        (_source(item.get("document_source")), int(item.get("rank", index)))
        for index, item in enumerate(results, start=1)
    ]

    if not expected:
        recall_at_3 = 1.0
        mrr = 1.0
    else:
        top_three = {source for source, rank in ranked if rank <= 3}
        recall_at_3 = len(expected & top_three) / len(expected)
        knowledge_coverage = (len(primary & top_three) + len(secondary & top_three)) / len(expected)
        relevant_ranks = [rank for source, rank in ranked if source in expected]
        mrr = 1 / min(relevant_ranks) if relevant_ranks else 0.0
    if not expected:
        knowledge_coverage = 1.0

    knowledge_score = 0.7 * knowledge_coverage + 0.3 * mrr
    return {
        "recall_at_3": round(recall_at_3 * 100, 2),
        "mrr": round(mrr * 100, 2),
        "knowledge_coverage_score": round(knowledge_coverage * 100, 2),
        "primary_recall": round((len(primary & {source for source, rank in ranked if rank <= 3}) / len(primary)) * 100, 2) if primary else 100.0,
        "secondary_recall": round((len(secondary & {source for source, rank in ranked if rank <= 3}) / len(secondary)) * 100, 2) if secondary else 100.0,
        "knowledge_score": round(knowledge_score * 100, 2),
    }
