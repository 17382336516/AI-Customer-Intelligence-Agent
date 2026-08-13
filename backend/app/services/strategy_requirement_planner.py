from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PATH = Path(__file__).resolve().parents[3] / "evaluation" / "strategy_requirement_mapping.json"


def plan_strategy_requirements(question: str, lifecycle_tags: list[str] | None = None) -> dict[str, Any]:
    try:
        mapping = json.loads(_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        mapping = {}
    text = str(question or "")
    if any(token in text for token in ("召回", "沉默", "未购", "流失")):
        goal = "user_recall"
    elif any(token in text for token in ("复购", "会员", "留存")):
        goal = "retention"
    elif any(token in text for token in ("活动", "618", "春节", "周年")):
        goal = "activity_operation"
    elif any(token in text for token in ("推荐", "新品", "品类")):
        goal = "product_recommendation"
    else:
        goal = "young_user_growth"
    spec = mapping.get(goal, {})
    return {
        "business_goal": goal,
        "required_segments": list(lifecycle_tags or []),
        "required_strategy_fields": list(spec.get("required_fields", [])),
        "must_include_concepts": list(spec.get("required_keywords", [])),
        "required_knowledge_types": list(spec.get("required_knowledge_types", [])),
    }
