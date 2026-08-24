from __future__ import annotations

"""Explicit preview and execute routes for one-time legacy Creator cleanup."""


PREVIEW_PATH = "/api/feishu-sync/legacy-creator-cleanup/preview"
EXECUTE_PATH = "/api/feishu-sync/legacy-creator-cleanup/execute"


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "POST" or request["path"] not in {PREVIEW_PATH, EXECUTE_PATH}:
        return False
    service = context["services"]["legacy_creator_cleanup"]
    try:
        if request["path"] == PREVIEW_PATH:
            result = service.preview()
        else:
            payload = request["get_payload"]()
            result = service.execute(
                confirm=payload.get("confirm") if isinstance(payload, dict) else False
            )
        handler._json({"ok": result.get("status") == "success", **result})
    except ValueError as exc:
        if str(exc) == "FEISHU_LEGACY_CREATOR_CLEANUP_CONFIRMATION_REQUIRED":
            handler._json(
                {"ok": False, "status": "blocked", "error": str(exc)}, status=400
            )
        else:
            handler._error("飞书遗留 Creator 清理请求无效。")
    except Exception as exc:
        context["logging"]["error"](
            "FeishuLegacyCreatorCleanup", "飞书遗留 Creator 清理失败", exc
        )
        handler._json({
            "ok": False,
            "status": "failed",
            "error": "FEISHU_LEGACY_CREATOR_CLEANUP_FAILED",
            "error_codes": ["UNKNOWN_ERROR"],
        }, status=500)
    return True
