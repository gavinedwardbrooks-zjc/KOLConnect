from __future__ import annotations

"""Safe status and bounded manual reconciliation for lifecycle delete intents."""


def handle(handler, request: dict, context: dict) -> bool:
    path = request["path"]
    if path not in {
        "/api/feishu-delete-intents/status",
        "/api/feishu-delete-intents/reconcile",
    }:
        return False
    service = context["services"]["feishu_delete_reconciliation"]
    if request["method"] == "GET" and path.endswith("/status"):
        handler._json({"ok": True, "data": service.status()})
        return True
    if request["method"] == "POST" and path.endswith("/reconcile"):
        payload = request["get_payload"]()
        if not isinstance(payload, dict) or payload.get("confirm") is not True:
            handler._json({"ok": False, "error": "FEISHU_DELETE_RECONCILIATION_CONFIRMATION_REQUIRED"}, status=400)
            return True
        handler._json({"ok": True, "data": service.reconcile(max_intents=10)})
        return True
    return False
