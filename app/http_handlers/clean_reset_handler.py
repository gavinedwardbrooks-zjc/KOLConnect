from __future__ import annotations

"""Explicit Settings endpoints for the local business-data clean reset."""

from services.clean_reset_service import CleanResetError


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "POST":
        return False
    path = request["path"]
    if path not in {
        "/api/settings/clean-reset/preview",
        "/api/settings/clean-reset/execute",
    }:
        return False

    service = context["services"]["clean_reset"]
    try:
        if path.endswith("/preview"):
            result = service.preview()
        else:
            payload = request["get_payload"]()
            result = service.execute(
                confirm=payload.get("confirm") if isinstance(payload, dict) else False
            )
        handler._json({"ok": result.get("status") == "success", **result})
    except ValueError as exc:
        if str(exc) == "CLEAN_RESET_CONFIRMATION_REQUIRED":
            handler._json(
                {"ok": False, "status": "blocked", "error": str(exc)}, status=400
            )
        else:
            handler._error("数据重置请求无效。")
    except CleanResetError as exc:
        context["logging"]["error"]("CleanReset", "本地业务数据重置失败", exc)
        handler._json(
            {"ok": False, "status": "failed", "error": str(exc)}, status=500
        )
    return True
