from __future__ import annotations

"""Conservative, read-only policy evaluation for future Creator deletion."""

import hashlib
import json
from typing import Any, Callable

from ports.creator_delete_impact_port import CreatorDeleteImpactPort
from services.creator_delete_plan import POLICY_VERSION, build_creator_delete_plan


PUBLIC_POLICY_SOURCES = frozenset({
    "creator_snapshots", "video_snapshots", "cooperations",
    "campaign_creators", "follow_up_logs", "task_artifacts",
    "unmapped_task_artifacts", "data_protection", "legacy_sources",
    "embedded_analysis_references",
})

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
        plan = build_creator_delete_plan(snapshot)
        unresolved = [
            item for item in plan["decisions"]
            if item["source"] in PUBLIC_POLICY_SOURCES
        ]
        blockers = self._blockers(snapshot, plan)
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
                {
                    "source": item["source"],
                    "count": item["count"],
                    "classification": item["classification"],
                }
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
            "unresolved": [
                {"source": item["source"], "count": item["count"]}
                for item in unresolved
            ],
            "warnings": warnings,
            "blockers": blockers,
            "can_delete": not blockers,
            "preview_fingerprint": fingerprint,
        }

    @staticmethod
    def _blockers(
        snapshot: dict[str, Any], plan: dict[str, Any]
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
            "creators": "CREATOR_LOCATOR_CONFLICT",
            "creator_accounts": "CREATOR_ACCOUNT_LOCATOR_CONFLICT",
            "videos": "VIDEO_LOCATOR_CONFLICT",
            "insights": "INSIGHT_LOCATOR_CONFLICT",
            "analysis_data": "ANALYSIS_DATA_LOCATOR_CONFLICT",
            "creator_snapshots": "CREATOR_SNAPSHOT_LOCATOR_CONFLICT",
            "video_snapshots": "VIDEO_SNAPSHOT_OWNERSHIP_CONFLICT",
            "cooperations": "COOPERATION_RETENTION_ANONYMIZATION_GAP",
            "campaign_creators": "CAMPAIGN_RELATION_DELETE_BLOCKED",
            "follow_up_logs": "FOLLOWUP_DELETE_BLOCKED",
            "task_artifacts": "UNSAFE_TASK_ARTIFACT",
            "unmapped_task_artifacts": "UNRESOLVED_TASK_OWNERSHIP",
            "data_protection": "SHARED_DATA_PROTECTION_UID",
            "legacy_sources": "UNRELIABLE_LEGACY_IDENTITY",
            "embedded_analysis_references": "EMBEDDED_ANALYSIS_REFERENCE",
        }
        seen_codes: set[str] = set()
        for item in plan["decisions"]:
            if item["classification"] != "BLOCK":
                continue
            code = source_codes[item["source"]]
            if code not in seen_codes:
                add(code, f"{item['source']} 无法安全纳入硬删除计划。", item["count"])
                seen_codes.add(code)
        for item in snapshot.get("safety_blocks", []):
            code = str(item.get("code") or "DELETE_SAFETY_BLOCK")
            if code not in seen_codes:
                add(code, f"{item.get('source') or 'resource'} 的定位或所有权不安全。")
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
