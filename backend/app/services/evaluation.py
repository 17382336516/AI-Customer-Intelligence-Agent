from __future__ import annotations

from typing import Any


def evaluate_result(state: dict[str, Any]) -> dict[str, Any]:
    segments = state.get("segments", [])
    insights = state.get("insights", [])
    cards = state.get("strategy_cards", [])
    route = state.get("route", "full_strategy")
    warnings: list[str] = []

    expected_cards = len(segments) if route == "full_strategy" else 0
    completeness_parts = [
        bool(state.get("quality")),
        bool(segments) or route == "quality_only",
        bool(insights) or route == "quality_only",
        len(cards) == expected_cards if route == "full_strategy" else True,
    ]
    completeness = sum(completeness_parts) / len(completeness_parts)

    evidence_items = sum(len(segment.get("evidence", [])) for segment in segments)
    evidence_coverage = min(1.0, evidence_items / max(1, len(segments) * 3))

    actionable_cards = sum(
        bool(card.get("product_mechanisms"))
        and bool(card.get("validation_metrics"))
        and bool(card.get("page", {}).get("modules"))
        for card in cards
    )
    actionability = (
        actionable_cards / len(cards) if cards else (1.0 if route != "full_strategy" else 0.0)
    )

    hero_titles = {card.get("page", {}).get("hero_title", "") for card in cards}
    slogans = {
        slogan
        for card in cards
        for slogan in card.get("slogans", [])
        if slogan
    }
    differentiation = 1.0
    if cards:
        differentiation = min(1.0, (len(hero_titles) + len(slogans)) / (len(cards) * 3))

    if state.get("quality", {}).get("analyzability_score", 100) < 70:
        warnings.append("数据可分析性评分低于 70，策略仅适合作为探索性方向。")

    cluster_quality = state.get("cluster_quality") or {}
    silhouette = cluster_quality.get("silhouette_score")
    if isinstance(silhouette, (int, float)) and 0 <= silhouette < 0.25:
        warnings.append(
            f"聚类轮廓系数偏低（{silhouette:.2f}），人群边界可能不清晰，结论需谨慎解读。"
        )

    return {
        "completeness": round(completeness, 4),
        "evidence_coverage": round(evidence_coverage, 4),
        "strategy_actionability": round(actionability, 4),
        "differentiation": round(differentiation, 4),
        "warnings": warnings,
    }

