from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


def _text(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "")


def _source(value: Any) -> str:
    return str(PurePosixPath(str(value or "").replace("\\", "/"))).lower()


def _canonical_segment(value: Any, aliases: dict[str, list[str]]) -> str:
    normalized = _text(value)
    for canonical, names in aliases.items():
        if normalized in {_text(canonical), *(_text(name) for name in names)}:
            return canonical
    return normalized


def _risk_terms(rule: Any) -> set[str]:
    text = _text(rule)
    terms = {text} if text else set()
    for prefix in ("不得", "禁止", "避免", "不能"):
        if text.startswith(prefix) and len(text) > len(prefix):
            terms.add(text.removeprefix(prefix))
    return terms


def evaluate(
    strategy_artifacts: dict[str, Any],
    golden: dict[str, Any],
    aliases: dict[str, list[str]],
) -> dict[str, Any]:
    records = strategy_artifacts.get("strategy_records", [])
    expected_segments = {
        _canonical_segment(item, aliases) for item in golden.get("expected_segments", [])
    }
    predicted_segments = {
        _canonical_segment(item.get("target_segment"), aliases) for item in records
    }
    target_coverage = (
        len(expected_segments & predicted_segments) / len(expected_segments)
        if expected_segments
        else 1.0
    )

    parsed = [
        [line.strip() for line in str(item.get("generated_strategy_text", "")).splitlines() if line.strip()]
        for item in records
    ]
    structural_checks = [
        target_coverage,
        float(any(len(lines) > 2 and lines[2] for lines in parsed)),
        float(any(len(lines) > 1 and lines[1] for lines in parsed)),
        float(any(len(lines) > 4 and lines[4] for lines in parsed)),
        float(any(len(lines) > 5 and lines[5] for lines in parsed)),
    ]
    structural_coverage = sum(structural_checks) / len(structural_checks)
    combined_text = _text(
        "\n".join(
            f"{item.get('target_segment', '')}\n{item.get('generated_strategy_text', '')}"
            for item in records
        )
    )
    required_keywords = [_text(item) for item in golden.get("must_include_keywords", []) if item]
    semantic_coverage = (
        sum(keyword in combined_text for keyword in required_keywords) / len(required_keywords)
        if required_keywords
        else 1.0
    )
    golden_rule_coverage = 0.5 * structural_coverage + 0.5 * semantic_coverage

    expected_sources = {
        _source(item) for item in golden.get("expected_knowledge_sources", []) if item
    }
    valid_applications: set[str] = set()
    for record in records:
        for application in record.get("knowledge_applications", []) or []:
            source = _source(application.get("document_source"))
            if (
                source in expected_sources
                and str(application.get("applied_concept", "")).strip()
                and str(application.get("strategy_field", "")).strip()
            ):
                valid_applications.add(source)
    if expected_sources:
        adoption_rate = len(valid_applications) / len(expected_sources)
    else:
        adoption_rate = float(not any(record.get("knowledge_applications") for record in records))

    risk_rules = list(
        dict.fromkeys(
            [
                *golden.get("forbidden_keywords", []),
                *golden.get("risk_constraints", []),
            ]
        )
    )
    violations = [
        str(rule)
        for rule in risk_rules
        if any(term and term in combined_text for term in _risk_terms(rule))
    ]
    risk_violation_rate = len(violations) / len(risk_rules) if risk_rules else 0.0
    strategy_score = (
        0.6 * golden_rule_coverage
        + 0.25 * adoption_rate
        + 0.15 * (1.0 - risk_violation_rate)
    )
    return {
        "golden_rule_coverage": round(golden_rule_coverage * 100, 2),
        "structural_coverage": round(structural_coverage * 100, 2),
        "semantic_coverage": round(semantic_coverage * 100, 2),
        "knowledge_adoption_rate": round(adoption_rate * 100, 2),
        "risk_violation_rate": round(risk_violation_rate * 100, 2),
        "violations": violations,
        "strategy_score": round(strategy_score * 100, 2),
    }
