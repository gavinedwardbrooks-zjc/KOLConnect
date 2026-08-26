from __future__ import annotations

"""Local Settings endpoints for explicit production SQLite migration."""

from services.production_migration_service import ProductionMigrationError


PATHS = {
    "/api/settings/storage-migration/status",
    "/api/settings/storage-migration/prepare",
    "/api/settings/storage-migration/confirm",
    "/api/settings/storage-migration/cancel",
    "/api/settings/storage-migration/recover",
}


def handle(handler, request: dict, context: dict) -> bool:
    path = request["path"]
    method = request["method"]
    if path not in PATHS:
        return False
    if method == "GET" and path.endswith("/status"):
        handler._json({"ok": True, **context["services"]["storage_migration"].status()})
        return True
    if method != "POST" or path.endswith("/status"):
        return False
    payload = request["get_payload"]()
    service = context["services"]["storage_migration"]
    try:
        if path.endswith("/prepare"):
            result = service.prepare(session_id=payload.get("session_id"))
        elif path.endswith("/confirm"):
            if payload.get("confirm") is not True:
                raise ProductionMigrationError("SQLITE_MIGRATION_CONFIRMATION_REQUIRED")
            result = service.confirm(
                migration_id=str(payload.get("migration_id") or ""),
                token=str(payload.get("confirmation_token") or ""),
                session_id=str(payload.get("session_id") or ""),
            )
        elif path.endswith("/cancel"):
            result = service.cancel(
                migration_id=str(payload.get("migration_id") or ""),
                token=str(payload.get("confirmation_token") or ""),
                session_id=str(payload.get("session_id") or ""),
            )
        else:
            result = service.recover(str(payload.get("migration_id") or ""))
        handler._json({"ok": result.get("status") in {"success", "ready_for_activation", "cancelled"}, **result})
    except ProductionMigrationError as exc:
        handler._json(
            {"ok": False, "status": "blocked", "error": exc.code},
            status=409 if exc.code != "MIGRATION_SESSION_REQUIRED" else 400,
        )
    return True
