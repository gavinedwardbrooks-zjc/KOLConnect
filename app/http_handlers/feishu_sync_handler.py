from __future__ import annotations

"""Manual M7.1 Feishu synchronization endpoints."""

from api_contract import error_payload, success_payload


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "POST":
        return False
    path = request["path"]
    if path not in {
        "/api/feishu-sync/validate",
        "/api/feishu-sync/dry-run",
        "/api/feishu-sync/full-sync",
    }:
        return False

    service = context["services"]["feishu_sync"]
    try:
        if path == "/api/feishu-sync/validate":
            result = service.validate_connection()
        elif path == "/api/feishu-sync/dry-run":
            result = service.dry_run()
        else:
            payload = request["get_payload"]()
            result = service.full_sync(
                confirm=payload.get("confirm") if isinstance(payload, dict) else False
            )
        if result.get("status") == "failed":
            code = next(iter(result.get("error_codes") or []), "FEISHU_SYNC_FAILED")
            handler._json(
                error_payload(
                    code,
                    "飞书同步操作失败。",
                    details={"error_codes": list(result.get("error_codes") or [])},
                    legacy=result,
                )
            )
        else:
            handler._json(success_payload(result, legacy=result))
    except ValueError as exc:
        if str(exc) == "FEISHU_SYNC_CONFIRMATION_REQUIRED":
            handler._json(
                error_payload(
                    str(exc),
                    "执行飞书全量同步前需要明确确认。",
                    legacy={
                        "status": "blocked",
                        "legacy_error": str(exc),
                    },
                ),
                status=400,
            )
        else:
            handler._error("飞书同步请求无效。")
    except Exception as exc:
        context["logging"]["error"]("FeishuSync", "飞书同步失败", exc)
        handler._json(
            error_payload(
                "FEISHU_SYNC_FAILED",
                "飞书同步操作失败。",
                legacy={
                    "status": "failed",
                    "legacy_error": "FEISHU_SYNC_FAILED",
                    "error_codes": ["UNKNOWN_ERROR"],
                },
            ),
            status=500,
        )
    return True
