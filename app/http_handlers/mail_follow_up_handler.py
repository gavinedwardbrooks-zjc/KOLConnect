"""Local HTTP adapter for the frozen Mail Follow-up read model and preferences."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from services import mail_follow_up_preferences as preferences


CSV_CONTENT_TYPE = "text/csv; charset=utf-8"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_FILENAMES = {
    "csv": "KOLConnect_Mail_Follow_Up_Queue.csv",
    "xlsx": "KOLConnect_Mail_Follow_Up_Queue.xlsx",
}


def _factory(context: dict):
    return context["services"]["get_mail_connection_factory"]()


def _group(payload: dict) -> tuple[object, object]:
    return payload.get("creator_id"), payload.get("correspondent_email")


def _with_creator_names(factory, groups: list[dict]) -> list[dict]:
    """Add read-only display metadata without changing derived Mail groups."""
    rows = [dict(group) for group in groups]
    creator_ids = sorted({str(row.get("creator_id") or "").strip() for row in rows if row.get("creator_id")})
    if not creator_ids:
        return rows
    placeholders = ",".join("?" for _creator_id in creator_ids)
    with factory.read_connection() as connection:
        names = {
            str(row["creator_id"]): str(row["name"] or "")
            for row in connection.execute(
                f"SELECT creator_id,name FROM creators WHERE creator_id IN ({placeholders})", creator_ids
            )
        }
    for row in rows:
        row["creator_name"] = names.get(str(row.get("creator_id") or ""), "")
    return rows


def _snooze_until(value: object) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("请选择未来的提醒时间。")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("提醒时间格式无效。") from exc


def _export(handler, factory, export_format: str) -> None:
    writer = {
        "csv": preferences.write_export_csv,
        "xlsx": preferences.write_export_xlsx,
    }.get(export_format)
    if writer is None:
        handler._json({"ok": False, "error": "EXPORT_FORMAT_INVALID"}, status=400)
        return
    with TemporaryDirectory(prefix="kolconnect_mail_followup_") as directory:
        target = writer(factory, Path(directory) / EXPORT_FILENAMES[export_format])
        handler._binary(target.read_bytes(),
                        CSV_CONTENT_TYPE if export_format == "csv" else XLSX_CONTENT_TYPE,
                        EXPORT_FILENAMES[export_format])


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    if not path.startswith("/api/mail/follow-up"):
        return False

    try:
        factory = _factory(context)
        if method == "GET" and path == "/api/mail/follow-up":
            groups = preferences.follow_up_state(factory)
            actionable_groups = preferences.actionable_follow_up_queue(factory)
            handler._json({
                "ok": True,
                "groups": _with_creator_names(factory, groups),
                "actionable_groups": _with_creator_names(factory, actionable_groups),
            })
            return True
        if method == "GET" and path == "/api/mail/follow-up/export-queue":
            handler._json({"ok": True, "groups": preferences.export_queue(factory)})
            return True
        if method == "GET" and path == "/api/mail/follow-up/export":
            export_format = str((request.get("query", {}).get("format") or [""])[0]).lower()
            _export(handler, factory, export_format)
            return True
        if method != "POST" or path != "/api/mail/follow-up/actions":
            return False

        payload = request["get_payload"]()
        if not isinstance(payload, dict):
            payload = {}
        creator_id, email = _group(payload)
        action = str(payload.get("action") or "").strip().lower()
        if action == "snooze":
            preferences.set_snooze(factory, creator_id, email, _snooze_until(payload.get("until")))
        elif action == "clear_snooze":
            preferences.clear_snooze(factory, creator_id, email)
        elif action == "stop":
            preferences.stop_follow_up(factory, creator_id, email)
        elif action == "resume":
            preferences.resume_follow_up(factory, creator_id, email)
        elif action == "export_add":
            preferences.add_to_export_queue(factory, creator_id, email)
        elif action == "export_remove":
            preferences.remove_from_export_queue(factory, creator_id, email)
        else:
            handler._json({"ok": False, "error": "FOLLOW_UP_ACTION_INVALID"}, status=400)
            return True
        handler._json({"ok": True, "groups": preferences.follow_up_state(factory)})
    except (OSError, RuntimeError, ValueError) as exc:
        handler._json({"ok": False, "error": str(exc)}, status=400)
    return True
