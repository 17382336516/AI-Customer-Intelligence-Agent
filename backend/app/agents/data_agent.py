from __future__ import annotations

from typing import Any

from ..database import Repository
from ..services.data_tools import analyze_file, build_quality_report, read_dataset


class DataAgent:
    name = "data_agent"

    def __init__(self, repository: Repository):
        self.repository = repository

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "tool_started",
            {"tool": "data_quality_and_segmentation"},
        )
        if state.get("route") == "quality_only":
            quality = build_quality_report(read_dataset(state["dataset_path"]))
            self.repository.add_event(
                state["analysis_id"],
                self.name,
                "tool_completed",
                {
                    "quality_score": quality["analyzability_score"],
                    "can_analyze": quality["can_analyze"],
                    "segment_count": 0,
                    "cleaning_stats": {},
                },
            )
            return {
                "quality": quality,
                "segments": [],
                "cleaning_stats": {},
                "blocked": not quality["can_analyze"],
            }

        output = analyze_file(state["dataset_path"])
        self.repository.add_event(
            state["analysis_id"],
            self.name,
            "tool_completed",
            {
                "quality_score": output.quality["analyzability_score"],
                "can_analyze": output.quality["can_analyze"],
                "segment_count": len(output.segments),
                "cleaning_stats": output.cleaning_stats,
            },
        )
        return {
            "quality": output.quality,
            "segments": output.segments,
            "cluster_quality": output.cluster_quality,
            "segment_method": output.segment_method,
            "category_debug": output.category_debug,
            "category_warning": output.category_warning,
            "income_profile": output.income_profile,
            "overall_consumption_insight": output.overall_consumption_insight,
            "_cleaned_df": output.cleaned,
            "_features_df": output.features,
            "cleaning_stats": output.cleaning_stats,
            "blocked": not output.quality["can_analyze"],
        }
