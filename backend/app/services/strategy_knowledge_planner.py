from __future__ import annotations

from typing import Any


FIELD_BY_TYPE = {
    "product": "product_strategy",
    "brand": "content_strategy",
    "operation_rule": "promotion_strategy",
    "marketing_case": "promotion_strategy",
    "user_growth": "content_strategy",
}


def build_strategy_knowledge_plan(
    insight: dict[str, Any] | None,
    target_segment: str,
    knowledge_evidence: list[dict[str, Any]],
    business_question: str,
) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for item in knowledge_evidence:
        field = (item.get("applicable_strategy_fields") or [FIELD_BY_TYPE.get(item.get("knowledge_type", ""), "")])[0]
        if not field:
            continue
        concepts = list(item.get("key_concepts") or [])
        plan.append({
            "strategy_field": field,
            "knowledge_source": item.get("document_source", ""),
            "evidence": item.get("evidence_text", ""),
            "planned_application": f"围绕{target_segment or '目标用户'}应用：{'、'.join(concepts[:3])}",
            "required_concept": concepts[:3],
        })
    return plan
