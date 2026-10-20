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


class CreatorDeleteImpactError(RuntimeError):
    code = "CREATOR_DELETE_IMPACT_FAILED"
    operation = "permanent_delete_impact"

    def __init__(
        self,
        exception_class: str,
        *,
        dependency_stage: str = "unknown",
        safe_error_code: str = "CREATOR_DELETE_IMPACT_FAILED",
    ) -> None:
        super().__init__("永久删除影响检查未完成，未执行任何删除。")
        self.exception_class = str(exception_class or "RuntimeError")
        self.dependency_stage = str(dependency_stage or "unknown")
        self.safe_error_code = str(
            safe_error_code or "CREATOR_DELETE_IMPACT_FAILED"
        )

    def to_response(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": {
                "code": self.code,
                "message": str(self),
                "details": {
                    "operation": self.operation,
                    "dependency_stage": self.dependency_stage,
                    "exception_class": self.exception_class,
                    "safe_error_code": self.safe_error_code,
                },
            },
        }


class CreatorDeleteImpactService:
    def __init__(
        self,
        impact_port_provider: Callable[[], CreatorDeleteImpactPort],
        *,
        error_logger: Callable[[str, BaseException], None] | None = None,
    ) -> None:
        self._impact_port_provider = impact_port_provider
        self._error_logger = error_logger or (lambda _message, _exc: None)

    def get_delete_impact(self, creator_id: str) -> dict[str, Any]:
        return self.inspect_delete_impact(creator_id)["preview"]

    def inspect_delete_impact(self, creator_id: str) -> dict[str, Any]:
        """Return the public preview and its scanner-owned internal delete plan."""
        try:
            return self._inspect_delete_impact(creator_id)
        except ValueError:
            raise
        except CreatorDeleteImpactError:
            raise
        except Exception as exc:
            dependency_stage = str(
                getattr(exc, "dependency_stage", "unknown") or "unknown"
            )
            exception_class = str(
                getattr(exc, "exception_class", type(exc).__name__)
                or type(exc).__name__
            )
            safe_error_code = str(
                getattr(exc, "safe_error_code", "CREATOR_DELETE_IMPACT_FAILED")
                or "CREATOR_DELETE_IMPACT_FAILED"
            )
            self._error_logger(
                "operation=permanent_delete_impact "
                f"dependency_stage={dependency_stage} "
                f"exception_class={exception_class} "
                f"safe_error_code={safe_error_code}",
                exc,
            )
            raise CreatorDeleteImpactError(
                exception_class,
                dependency_stage=dependency_stage,
                safe_error_code=safe_error_code,
            ) from exc

    def _inspect_delete_impact(self, creator_id: str) -> dict[str, Any]:
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
        preview = {
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
        return {"preview": preview, "snapshot": snapshot, "plan": plan}

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
            "mail_facts": "MAIL_FACTS_REQUIRE_RETENTION_POLICY",
            "mail_follow_up_preferences": "MAIL_FOLLOW_UP_REQUIRES_RETENTION_POLICY",
            "mail_dependency_unknown": "MAIL_DEPENDENCY_SCAN_UNAVAILABLE",
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
                if any(token in code for token in ("UNREADABLE", "INVALID", "UNAVAILABLE")):
                    message = "发现无法验证的历史数据，已阻止删除。"
                else:
                    message = f"{item.get('source') or 'resource'} 的定位或所有权不安全。"
                add(code, message)
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
