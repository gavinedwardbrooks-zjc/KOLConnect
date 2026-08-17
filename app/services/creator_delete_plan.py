from __future__ import annotations

"""Build a mutation-free Creator delete plan from scanner-owned facts."""

from typing import Any


POLICY_VERSION = "m4.6b-delete-safety-v1"


def _decision(source: str, count: int, classification: str) -> dict[str, Any]:
    return {
        "source": source,
        "count": int(count),
        "classification": classification,
    }


def build_creator_delete_plan(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Classify exact locators without performing any persistence mutation."""
    impact = snapshot["impact"]
    locators = snapshot.get("resource_locators", {})
    safety_blocks = list(snapshot.get("safety_blocks", []))
    blocked_sources = {str(item.get("source") or "") for item in safety_blocks}

    decisions: list[dict[str, Any]] = []
    fixed = (
        ("creators", impact["creators"], "DELETE"),
        ("creator_accounts", impact["creator_accounts"], "DELETE"),
        ("videos", impact["videos"], "DELETE"),
        ("insights", impact["insights"], "DELETE"),
        ("analysis_data", impact["analysis_data"], "DELETE"),
        ("creator_snapshots", impact["creator_snapshots"], "DELETE"),
        ("video_snapshots", impact["video_snapshots"]["total"], "DELETE"),
        ("cooperations", impact["cooperations"], "BLOCK"),
        ("campaign_creators", impact["campaign_creators"]["total"], "DELETE"),
        ("follow_up_logs", impact["follow_up_logs"], "DELETE"),
        ("data_protection", impact["data_protection"], "DELETE"),
        ("embedded_analysis_references", impact["embedded_analysis_references"], "BLOCK"),
    )
    for source, count, desired in fixed:
        if not count:
            continue
        classification = "BLOCK" if source in blocked_sources else desired
        decisions.append(_decision(source, count, classification))

    task_locators = list(locators.get("task_artifacts", []))
    if task_locators:
        task_classification = (
            "DELETE"
            if all(item.get("ownership") == "exclusive" for item in task_locators)
            else "BLOCK"
        )
        decisions.append(_decision("task_artifacts", len(task_locators), task_classification))
    unmapped_count = int(impact.get("unmapped_task_artifacts") or 0)
    if unmapped_count:
        decisions.append(_decision("unmapped_task_artifacts", unmapped_count, "BLOCK"))

    legacy_locators = list(locators.get("legacy_sources", []))
    if legacy_locators:
        legacy_classification = (
            "DELETE"
            if all(item.get("ownership") == "exclusive" for item in legacy_locators)
            else "BLOCK"
        )
        decisions.append(_decision("legacy_sources", len(legacy_locators), legacy_classification))

    delete_locators: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    decisions_by_source = {item["source"]: item for item in decisions}
    for source, items in locators.items():
        decision = decisions_by_source.get(source)
        if decision is None:
            continue
        if decision["classification"] == "DELETE":
            delete_locators.extend(items)
        elif decision["classification"] == "RETAIN":
            retained.extend(items)
        else:
            blocked.extend(items)
    blocked.extend(safety_blocks)
    return {
        "policy_version": POLICY_VERSION,
        "decisions": decisions,
        "delete_locators": delete_locators,
        "retained": retained,
        "blocked": blocked,
    }
