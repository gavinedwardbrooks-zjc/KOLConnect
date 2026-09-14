from __future__ import annotations

"""SQLite-backed execution, brief, and human content-review read/write model."""

from datetime import date, datetime, timezone
import uuid
from typing import Any, Callable


TERMINAL_STAGES = frozenset({"completed", "cancelled", "rejected"})
WAITING_ON = frozenset({"creator", "internal", "client", "self", "none"})
REVIEW_STATUSES = frozenset({"pending", "approved", "changes_requested", "rejected"})
CONTENT_TYPES = frozenset({"script", "copy", "video_draft", "other"})


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date(value: object, label: str = "截止日期") -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(f"{label}必须为 YYYY-MM-DD 格式。") from exc
    return text


class CampaignExecutionService:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def update_execution(self, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = {"stage", "owner", "next_action", "due_date", "waiting_on", "need_my_decision"}
        if not isinstance(payload, dict) or not set(payload).issubset(allowed):
            raise ValueError("执行字段无效。")
        with self._connection_factory().write_transaction() as connection:
            row = connection.execute("SELECT * FROM campaign_creators WHERE id=?", (relation_id,)).fetchone()
            if row is None:
                raise ValueError("Campaign 达人记录不存在。")
            updates: dict[str, Any] = {}
            for key in ("stage", "owner", "next_action"):
                if key in payload:
                    updates[key] = str(payload[key] or "").strip() or None
            if "due_date" in payload:
                updates["due_date"] = _date(payload["due_date"])
            if "waiting_on" in payload:
                waiting = str(payload["waiting_on"] or "none").strip().lower() or "none"
                if waiting not in WAITING_ON:
                    raise ValueError("等待对象无效。")
                updates["waiting_on"] = waiting
            if "need_my_decision" in payload:
                updates["need_my_decision"] = 1 if bool(payload["need_my_decision"]) else 0
            meaningful = any(row[key] != value for key, value in updates.items())
            updates["updated_at"] = _now()
            if meaningful:
                updates["last_progress_at"] = updates["updated_at"]
            connection.execute(
                f"UPDATE campaign_creators SET {','.join(f'{key}=?' for key in updates)} WHERE id=?",
                tuple(updates.values()) + (relation_id,),
            )
        return self.execution_for(relation_id)

    def execution_for(self, relation_id: str) -> dict[str, Any]:
        with self._connection_factory().read_connection() as connection:
            row = connection.execute("SELECT * FROM campaign_creators WHERE id=?", (relation_id,)).fetchone()
        if row is None:
            raise ValueError("Campaign 达人记录不存在。")
        return self._execution(dict(row))

    def workspace(self) -> dict[str, list[dict[str, Any]]]:
        with self._connection_factory().read_connection() as connection:
            rows = [dict(row) for row in connection.execute(
                "SELECT cc.*, c.name AS campaign_name, cr.name AS creator_name FROM campaign_creators cc "
                "JOIN campaigns c ON c.campaign_id=cc.campaign_id JOIN creators cr ON cr.creator_id=cc.creator_id "
                "WHERE COALESCE(cc.archived_at, '')=''"
            )]
        items = [{**self._execution(row), "campaign_name": row["campaign_name"], "creator_name": row["creator_name"]} for row in rows]
        today = date.today().isoformat()
        return {
            "today": [item for item in items if item.get("due_date") == today],
            "due_soon": [item for item in items if item["due_soon"]],
            "overdue": [item for item in items if item["overdue"]],
            "stalled": [item for item in items if item["stalled"]],
            "waiting_creator": [item for item in items if item.get("waiting_on") == "creator"],
            "waiting_internal": [item for item in items if item.get("waiting_on") == "internal"],
            "need_my_decision": [item for item in items if item.get("need_my_decision")],
        }

    def get_brief(self, campaign_id: str) -> dict[str, Any] | None:
        with self._connection_factory().read_connection() as connection:
            row = connection.execute("SELECT * FROM campaign_briefs WHERE campaign_id=?", (campaign_id,)).fetchone()
        return dict(row) if row else None

    def save_brief(self, campaign_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        fields = ("title", "core_selling_points", "must_include", "must_avoid", "brand_requirements", "content_requirements", "publishing_requirements", "reference_notes", "platform_guidance")
        if not isinstance(payload, dict) or not set(payload).issubset(fields):
            raise ValueError("Brief 字段无效。")
        now = _now()
        with self._connection_factory().write_transaction() as connection:
            if connection.execute("SELECT 1 FROM campaigns WHERE campaign_id=?", (campaign_id,)).fetchone() is None:
                raise ValueError("Campaign 不存在。")
            existing = connection.execute("SELECT * FROM campaign_briefs WHERE campaign_id=?", (campaign_id,)).fetchone()
            values = {field: str(payload.get(field, existing[field] if existing else "") or "").strip() or None for field in fields}
            if existing:
                connection.execute(f"UPDATE campaign_briefs SET {','.join(f'{field}=?' for field in fields)}, updated_at=? WHERE campaign_id=?", tuple(values[field] for field in fields) + (now, campaign_id))
            else:
                connection.execute(f"INSERT INTO campaign_briefs(campaign_id,{','.join(fields)},created_at,updated_at) VALUES ({','.join('?' for _ in range(len(fields)+3))})", (campaign_id,) + tuple(values[field] for field in fields) + (now, now))
        return self.get_brief(campaign_id) or {}

    def list_submissions(self, relation_id: str) -> list[dict[str, Any]]:
        with self._connection_factory().read_connection() as connection:
            rows = connection.execute("SELECT * FROM content_submissions WHERE campaign_creator_id=? ORDER BY created_at DESC", (relation_id,)).fetchall()
        return [dict(row) for row in rows]

    def create_submission(self, relation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        content_type = str(payload.get("content_type") or "").strip()
        if content_type not in CONTENT_TYPES:
            raise ValueError("内容类型无效。")
        now = _now()
        record = {"submission_id": f"submission_{uuid.uuid4().hex[:16]}", "campaign_creator_id": relation_id, "account_uid": str(payload.get("account_uid") or "").strip() or None, "content_type": content_type, "content_reference": str(payload.get("content_reference") or "").strip() or None, "submitted_at": str(payload.get("submitted_at") or now).strip() or now, "submitted_by": str(payload.get("submitted_by") or "").strip() or None, "source": str(payload.get("source") or "manual").strip() or "manual", "review_status": "pending", "review_note": None, "created_at": now, "updated_at": now}
        with self._connection_factory().write_transaction() as connection:
            if connection.execute("SELECT 1 FROM campaign_creators WHERE id=?", (relation_id,)).fetchone() is None:
                raise ValueError("Campaign 达人记录不存在。")
            connection.execute(f"INSERT INTO content_submissions({','.join(record)}) VALUES ({','.join('?' for _ in record)})", tuple(record.values()))
        return record

    def review_submission(self, submission_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        status = str(payload.get("review_status") or "").strip()
        if status not in REVIEW_STATUSES:
            raise ValueError("人工审核状态无效。")
        with self._connection_factory().write_transaction() as connection:
            now = _now()
            cursor = connection.execute("UPDATE content_submissions SET review_status=?, review_note=?, updated_at=? WHERE submission_id=?", (status, str(payload.get("review_note") or "").strip() or None, now, submission_id))
            if cursor.rowcount != 1:
                raise ValueError("内容提交不存在。")
            row = connection.execute("SELECT * FROM content_submissions WHERE submission_id=?", (submission_id,)).fetchone()
        return dict(row)

    def ai_review_submission(self, submission_id: str) -> dict[str, Any]:
        """Persist deterministic first-pass findings without changing human review state."""
        with self._connection_factory().read_connection() as connection:
            submission = connection.execute("SELECT * FROM content_submissions WHERE submission_id=?", (submission_id,)).fetchone()
            if submission is None:
                raise ValueError("内容提交不存在。")
            campaign_id = connection.execute("SELECT campaign_id FROM campaign_creators WHERE id=?", (submission["campaign_creator_id"],)).fetchone()
            brief = connection.execute("SELECT * FROM campaign_briefs WHERE campaign_id=?", (campaign_id[0],)).fetchone() if campaign_id else None
        if not brief:
            return {"status": "unavailable", "reason": "brief_not_configured", "findings": []}
        text = str(submission["content_reference"] or "")
        findings = []
        for requirement in self._brief_lines(brief["must_include"]):
            if requirement.lower() not in text.lower():
                findings.append(self._finding("required_missing", requirement, "高", f"未发现必须包含项：{requirement}", "补充并由人工确认。"))
        for expression in self._brief_lines(brief["must_avoid"]):
            if expression.lower() in text.lower():
                findings.append(self._finding("forbidden_expression", expression, "高", f"发现禁止表达：{expression}", "删除或改写后由人工确认。"))
        now = _now()
        with self._connection_factory().write_transaction() as connection:
            # Re-running a first pass replaces only its derived findings, never the submission.
            connection.execute("DELETE FROM content_submission_ai_findings WHERE submission_id=?", (submission_id,))
            for finding in findings:
                connection.execute(
                    "INSERT INTO content_submission_ai_findings("
                    "finding_id,submission_id,location,finding_type,brief_requirement,risk_level,"
                    "description,suggestion,needs_human_confirmation,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"finding_{uuid.uuid4().hex[:16]}", submission_id,
                        finding["location"], finding["finding_type"], finding["brief_requirement"],
                        finding["risk_level"], finding["description"], finding["suggestion"],
                        1 if finding["needs_human_confirmation"] else 0, now,
                    ),
                )
        return {"status": "success", "findings": findings, "human_review_status": submission["review_status"]}

    @staticmethod
    def _brief_lines(value: object) -> list[str]:
        return [item.strip() for item in str(value or "").replace("\r", "").split("\n") if item.strip()]

    @staticmethod
    def _finding(finding_type: str, requirement: str, risk_level: str, description: str, suggestion: str) -> dict[str, Any]:
        return {"location": "content_reference", "finding_type": finding_type, "brief_requirement": requirement, "risk_level": risk_level, "description": description, "suggestion": suggestion, "needs_human_confirmation": True}

    @staticmethod
    def _execution(row: dict[str, Any]) -> dict[str, Any]:
        current = date.today()
        terminal = str(row.get("stage") or "") in TERMINAL_STAGES
        due = _date(row.get("due_date"))
        last = str(row.get("last_progress_at") or row.get("updated_at") or "")
        try:
            last_day = datetime.fromisoformat(last.replace("Z", "+00:00")).date()
        except ValueError:
            last_day = current
        return {"campaign_creator_id": row.get("id"), "campaign_id": row.get("campaign_id"), "creator_id": row.get("creator_id"), "stage": row.get("stage"), "owner": row.get("owner"), "next_action": row.get("next_action"), "due_date": due, "waiting_on": row.get("waiting_on") or "none", "last_progress_at": row.get("last_progress_at"), "need_my_decision": bool(row.get("need_my_decision")), "overdue": bool(due and due < current.isoformat() and not terminal), "due_soon": bool(due and current.isoformat() <= due <= current.fromordinal(current.toordinal() + 2).isoformat() and not terminal), "stalled": bool(not terminal and (current - last_day).days >= 3)}
