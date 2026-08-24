from __future__ import annotations

"""Explicit preview and execute routes for Account identity backfill."""


DRY_RUN_PATH = "/api/feishu-sync/account-backfill/dry-run"
EXECUTE_PATH = "/api/feishu-sync/account-backfill/execute"


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "POST" or request["path"] not in {DRY_RUN_PATH, EXECUTE_PATH}:
        return False

    service = context["services"]["account_identity_backfill"]
    try:
        if request["path"] == DRY_RUN_PATH:
            result = service.dry_run()
        else:
            payload = request["get_payload"]()
            result = service.execute(
                confirm=payload.get("confirm") if isinstance(payload, dict) else False
            )
        handler._json({"ok": result.get("status") not in {"failed", "blocked"}, **result})
    except ValueError as exc:
        if str(exc) == "FEISHU_ACCOUNT_BACKFILL_CONFIRMATION_REQUIRED":
            handler._json(
                {"ok": False, "status": "blocked", "error": str(exc)}, status=400
            )
        else:
            handler._error("飞书账号身份认领请求无效。")
    except Exception as exc:
        context["logging"]["error"]("FeishuBackfill", "飞书账号身份认领失败", exc)
        handler._json(
            {
                "ok": False,
                "status": "failed",
                "error": "FEISHU_ACCOUNT_BACKFILL_FAILED",
                "error_codes": ["UNKNOWN_ERROR"],
            },
            status=500,
        )
    return True
