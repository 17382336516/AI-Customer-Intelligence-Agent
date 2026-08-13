from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_MAPPING_PATH = Path(__file__).resolve().parents[3] / "evaluation" / "knowledge_concept_mapping.json"


def _text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _source(value: Any) -> str:
    return str(value or "").replace("\\", "/").lstrip("./").lower()


def _load_mapping() -> dict[str, list[dict[str, Any]]]:
    try:
        return json.loads(_MAPPING_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_knowledge_plan(retrieval_results: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Plan fields only for documents actually returned by Knowledge Agent."""
    mapping = _load_mapping()
    field_by_type = {
        "product": "product_strategy",
        "marketing_case": "promotion_strategy",
        "brand": "content_strategy",
        "operation_rule": "promotion_strategy",
        "user_growth": "content_strategy",
    }
    plan: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for hit in retrieval_results or []:
        raw_source = str(hit.get("document_source") or hit.get("source") or "")
        source = _source(raw_source)
        knowledge_type = source.split("/", 1)[0]
        field = field_by_type.get(knowledge_type)
        if not field:
            continue
        concepts = mapping.get(source) or [{"concept": source.rsplit("/", 1)[-1].rsplit(".", 1)[0]}]
        concept = str(concepts[0].get("concept", ""))
        key = (source, field, concept)
        if key in seen:
            continue
        seen.add(key)
        plan.append({
            "document_source": raw_source,
            "knowledge_type": knowledge_type,
            "strategy_field": field,
            "expected_concept": concept,
            "purpose": {
                "product": "解释产品机制",
                "brand": "约束品牌表达",
                "marketing_case": "提供营销案例依据",
                "user_growth": "支持用户增长运营",
                "operation_rule": "遵守运营规则",
            }.get(knowledge_type, "补充策略依据"),
            "target_field": field,
        })
    return plan


def _field_texts(card: dict[str, Any]) -> dict[str, str]:
    return {
        "product_strategy": _text(card.get("product_strategy")),
        "content_strategy": _text(card.get("content_strategy")),
        "promotion_strategy": _text(card.get("promotion_strategy")),
        "channel": _text(" ".join(str(v) for v in card.get("channels", []) or [])),
    }


def attribute_knowledge(
    cards: list[dict[str, Any]],
    retrieval_results: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Attribute only retrieved documents whose concepts occur in strategy fields."""
    mapping = _load_mapping()
    results = retrieval_results or []
    enriched: list[dict[str, Any]] = []
    for card in cards:
        fields = _field_texts(card)
        applications: list[dict[str, Any]] = []
        used_sources: list[str] = []
        strategy_all = _text(" ".join(fields.values()))
        for hit in results:
            raw_source = hit.get("document_source") or hit.get("source") or ""
            canonical_source = _source(raw_source)
            concepts = mapping.get(canonical_source, [])
            content = _text(hit.get("retrieved_content") or hit.get("text"))
            for item in concepts:
                keywords = [_text(k) for k in item.get("keywords", []) if _text(k)]
                concept = _text(item.get("concept"))
                candidates = keywords + ([concept] if concept else [])
                matched = next((keyword for keyword in candidates if keyword in content and keyword in strategy_all), "")
                if not matched:
                    continue
                field = next((name for name, value in fields.items() if matched in value), "")
                if not field:
                    continue
                evidence = next(
                    (str(card.get(field.replace("channel", "channels"), ""))[:240] for _ in [0]),
                    "",
                )
                app = {
                    "document_source": raw_source,
                    "applied_concept": item.get("concept", ""),
                    "strategy_field": field,
                    "evidence_text": evidence,
                }
                if app not in applications:
                    applications.append(app)
                if raw_source not in used_sources:
                    used_sources.append(raw_source)
                break
        enriched.append({
            **card,
            "used_knowledge_sources": used_sources,
            "knowledge_applications": applications,
            "strategy_knowledge_trace": [
                {
                    "source": item["document_source"],
                    "concept": item["applied_concept"],
                    "used_in": item["strategy_field"],
                    "evidence": item["evidence_text"],
                }
                for item in applications
            ],
        })
    return enriched
