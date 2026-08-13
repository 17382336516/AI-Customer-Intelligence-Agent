from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_ALIAS_PATH = Path(__file__).resolve().parents[3] / "evaluation" / "knowledge_concept_alias.json"
_BUSINESS_PATH = Path(__file__).resolve().parents[3] / "evaluation" / "business_concept_mapping.json"


def _aliases() -> dict[str, list[str]]:
    try:
        return json.loads(_ALIAS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _business_concepts() -> dict[str, dict[str, Any]]:
    try:
        return json.loads(_BUSINESS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _clean(value: Any) -> str:
    return str(value or "").replace(" ", "").replace("\u3000", "").lower()


def verify_strategy_grounding(
    strategy_output: dict[str, Any],
    knowledge_evidence: list[dict[str, Any]],
    strategy_knowledge_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    retrieved = {str(x.get("document_source", "")).replace("\\", "/").lower() for x in knowledge_evidence}
    aliases = _aliases()
    business_concepts = _business_concepts()
    normalized_evidence = {str(item.get("document_source", "")).replace("\\", "/").lower(): item for item in knowledge_evidence}
    verified: list[dict[str, Any]] = []
    unsupported: list[str] = []
    matched_concepts: list[dict[str, Any]] = []
    failed_concepts: list[dict[str, Any]] = []
    for trace in strategy_knowledge_trace or []:
        source = str(trace.get("knowledge_source") or trace.get("source") or "").replace("\\", "/")
        field = str(trace.get("strategy_field") or trace.get("used_in") or "")
        text = _clean(strategy_output.get(field, ""))
        concept = str(trace.get("used_concept") or trace.get("concept") or "")
        exact_candidates = [concept, *aliases.get(concept, [])]
        evidence_item = normalized_evidence.get(source.lower(), {})
        evidence_text = _clean(evidence_item.get("evidence_text", ""))
        evidence_concepts = [_clean(x) for x in evidence_item.get("key_concepts", [])]
        trace_clean = _clean(concept)
        concept_id = next(
            (key for key, item in business_concepts.items()
             if any(
                 _clean(alias) in trace_clean or trace_clean in _clean(alias)
                 or _clean(alias) in evidence_text
                 or any(_clean(alias) in ec or ec in _clean(alias) for ec in evidence_concepts)
                 for alias in [*item.get("knowledge_aliases", []), item.get("canonical_concept", "")]
             )),
            "",
        )
        if not concept_id:
            if any(token in trace_clean for token in ("储蓄", "攒钱", "存钱", "门槛")):
                concept_id = "low_threshold_saving_mechanism"
            elif any(token in trace_clean for token in ("年轻用户", "青年", "用户增长")):
                concept_id = "young_user_growth"
            elif any(token in trace_clean for token in ("召回", "唤醒", "回流", "沉默用户")):
                concept_id = "user_reactivation"
            elif any(token in trace_clean for token in ("品牌", "信任", "心智")):
                concept_id = "brand_trust_building"
        business_item = business_concepts.get(concept_id, {})
        business_candidates = list(business_item.get("strategy_aliases", []))
        # Short expressions are common in generated strategy cards; keep them
        # tied to the resolved business concept and strategy field.
        if concept_id == "low_threshold_saving_mechanism":
            business_candidates.extend(["低门槛", "持续参与", "场景化运营培养储蓄习惯"])
        elif concept_id == "young_user_growth":
            business_candidates.extend(["年轻用户", "分层运营", "持续参与"])
        match_type = ""
        matched_expression = ""
        if any(token and _clean(token) in text for token in exact_candidates):
            match_type = "exact_or_alias"
            matched_expression = next(token for token in exact_candidates if token and _clean(token) in text)
        elif field in business_item.get("related_strategy_fields", []) and any(token and _clean(token) in text for token in business_candidates):
            match_type = "business_concept_match"
            matched_expression = next(token for token in business_candidates if token and _clean(token) in text)
        if source.lower() in retrieved and field and match_type:
            verified.append({"source": source, "strategy_field": field, "concept": concept})
            matched_concepts.append({
                "knowledge_concept": business_item.get("canonical_concept") or concept,
                "strategy_expression": matched_expression,
                "strategy_field": field,
                "match_type": match_type,
            })
        else:
            unsupported.append(source or concept)
            failed_concepts.append({"knowledge_concept": business_item.get("canonical_concept") or concept, "strategy_field": field, "reason": "未找到字段内语义匹配"})
    score = len(verified) / len(strategy_knowledge_trace) if strategy_knowledge_trace else 0.0
    return {
        "knowledge_grounded": bool(verified) if strategy_knowledge_trace else False,
        "verified_sources": list(dict.fromkeys(item["source"] for item in verified)),
        "unsupported_claims": unsupported,
        "grounding_score": round(score, 4),
        "matched_concepts": matched_concepts,
        "failed_concepts": failed_concepts,
        "explanation": "；".join(
            f"{item['knowledge_concept']}对应策略字段{item['strategy_field']}中的{item['strategy_expression']}"
            for item in matched_concepts
        ),
    }
