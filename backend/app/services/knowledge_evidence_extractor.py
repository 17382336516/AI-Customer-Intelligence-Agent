from __future__ import annotations

from typing import Any


FIELD_BY_TYPE = {
    "product": ["product_strategy", "content_strategy"],
    "brand": ["content_strategy"],
    "operation_rule": ["promotion_strategy"],
    "marketing_case": ["promotion_strategy", "channel"],
    "user_growth": ["content_strategy", "channel"],
}


def extract_knowledge_evidence(
    business_question: str,
    target_segment: str,
    retrieval_results: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for hit in retrieval_results or []:
        metadata = hit.get("metadata", {}) or {}
        source = str(hit.get("document_source") or hit.get("source") or "").replace("\\", "/")
        if not source:
            continue
        doc_type = str(hit.get("document_type") or metadata.get("document_type") or "")
        raw_keywords = metadata.get("keywords", "")
        keywords = [str(x).strip() for x in str(raw_keywords).replace("，", ",").split(",") if str(x).strip()]
        keywords.extend(str(x) for x in hit.get("matched_keywords", []) if str(x).strip())
        content = str(hit.get("retrieved_content") or hit.get("text") or "").strip()
        concepts = list(dict.fromkeys(keywords[:6]))
        if not concepts and content:
            concepts = [content.split("。", 1)[0][:40]]
        evidence.append({
            "document_source": source,
            "knowledge_type": doc_type,
            "business_goal": hit.get("business_goal") or metadata.get("business_goal", ""),
            "target_segment": hit.get("target_segment") or metadata.get("target_segment", target_segment),
            "key_concepts": concepts,
            "applicable_strategy_fields": FIELD_BY_TYPE.get(doc_type, []),
            "evidence_text": content[:240],
        })
    return evidence
