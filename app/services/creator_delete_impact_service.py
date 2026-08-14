from __future__ import annotations

"""Conservative, read-only policy evaluation for future Creator deletion."""

import hashlib
import json
from typing import Any, Callable

from ports.creator_delete_impact_port import CreatorDeleteImpactPort


POLICY_VERSION = "m4.2-delete-impact-v1"


class CreatorDeleteImpactService:
    def __init__(
        self,
        impact_port_provider: Callable[[], CreatorDeleteImpactPort],
    ) -> None:
        self._impact_port_provider = impact_port_provider

    def get_delete_impact(self, creator_id: str) -> dict[str, Any]:
        snapshot = self._impact_port_provider().scan_creator_delete_impact(creator_id)
        impact = snapshot["impact"]
        retained = snapshot["retained"]
        unresolved = self._unresolved(impact)
        blockers = self._blockers(snapshot, unresolved)
        warnings = [
            {
                "code": "READ_ONLY_PREVIEW",
                "message": "此结果仅用于影响预览，不会删除或修改任何数据。",
            }
        ]
        fingerprint_state = {
            "policy_version": POLICY_VERSION,
            "creator_id": snapshot["creator_id"],
            "creator_updated_at": snapshot["creator_updated_at"],
            "is_archived": snapshot["is_archived"],
            "impact": impact,
            "retained": retained,
            "unresolved": [
                {"source": item["source"], "count": item["count"]}
                for item in unresolved
            ],
            "blockers": [item["code"] for item in blockers],
            "structural_ids": snapshot["structural_ids"],
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_state,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "creator": {
                "creator_id": snapshot["creator_id"],
                "display_name": snapshot["display_name"],
                "is_archived": snapshot["is_archived"],
            },
            "impact": impact,
            "retained": retained,
            "unresolved": unresolved,
            "warnings": warnings,
            "blockers": blockers,
            "can_delete": not blockers,
            "preview_fingerprint": fingerprint,
        }

    @staticmethod
    def _unresolved(impact: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = (
            ("creator_snapshots", impact["creator_snapshots"]),
            ("video_snapshots", impact["video_snapshots"]["total"]),
            ("cooperations", impact["cooperations"]),
            ("campaign_creators", impact["campaign_creators"]["total"]),
            ("follow_up_logs", impact["follow_up_logs"]),
            ("task_artifacts", impact["task_artifacts"]),
            ("unmapped_task_artifacts", impact["unmapped_task_artifacts"]),
            ("data_protection", impact["data_protection"]),
            ("legacy_sources", impact["legacy_sources"]),
            ("embedded_analysis_references", impact["embedded_analysis_references"]),
        )
        return [
            {"source": source, "count": count, "classification": "UNRESOLVED"}
            for source, count in candidates
            if count
        ]

    @staticmethod
    def _blockers(
        snapshot: dict[str, Any], unresolved: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        blockers: list[dict[str, Any]] = []

        def add(code: str, message: str, count: int = 0) -> None:
            item: dict[str, Any] = {"code": code, "message": message}
            if count:
                item["count"] = count
            blockers.append(item)

        if not snapshot["is_archived"]:
            add("CREATOR_NOT_ARCHIVED", "Creator 必须先归档才能进入硬删除评估。")
        active = snapshot["impact"]["campaign_creators"]["active"]
        if active:
            add("ACTIVE_CAMPAIGN_RELATION", "存在未归档的 Campaign Creator 关系。", active)
        source_codes = {
            "creator_snapshots": "UNRESOLVED_SNAPSHOT_RETENTION",
            "video_snapshots": "UNRESOLVED_SNAPSHOT_RETENTION",
            "cooperations": "UNRESOLVED_COOPERATION_RETENTION",
            "campaign_creators": "UNRESOLVED_CAMPAIGN_RELATION_RETENTION",
            "follow_up_logs": "UNRESOLVED_FOLLOWUP_RETENTION",
            "task_artifacts": "UNRESOLVED_TASK_ARTIFACT",
            "unmapped_task_artifacts": "UNRESOLVED_TASK_ARTIFACT",
            "data_protection": "UNRESOLVED_DATA_PROTECTION",
            "legacy_sources": "UNRESOLVED_LEGACY_SOURCE",
            "embedded_analysis_references": "UNRESOLVED_EMBEDDED_REFERENCE",
        }
        seen_codes: set[str] = set()
        for item in unresolved:
            code = source_codes[item["source"]]
            if code not in seen_codes:
                add(code, f"{item['source']} 的保留策略尚未冻结。", item["count"])
                seen_codes.add(code)
        unknown_followups = snapshot["unknown_followup_reference_count"]
        if unknown_followups:
            add(
                "UNKNOWN_FOLLOWUP_OBJECT_TYPE",
                "存在 object_type 无法确认的同 ID FollowUpLog。",
                unknown_followups,
            )
        broken = len(snapshot["broken_references"])
        if broken:
            add("BROKEN_REFERENCE", "发现确定性的断裂引用。", broken)
        return blockers
