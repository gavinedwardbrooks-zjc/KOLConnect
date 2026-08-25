from __future__ import annotations

"""Localhost-only M7.3 assistant endpoints."""

from api_contract import error_payload, success_payload


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    if path not in {
        "/api/assistant/capabilities",
        "/api/assistant/message",
        "/api/assistant/confirm",
    }:
        return False
    service = context["services"]["assistant"]
    trace_id = str(request.get("trace_id") or context["request"].get("trace_id") or "")
    if method == "GET" and path == "/api/assistant/capabilities":
        result = service.capabilities(trace_id)
    elif method == "POST" and path == "/api/assistant/message":
        payload = request["get_payload"]()
        result = service.message(payload.get("message"), payload.get("session_id"), trace_id)
    elif method == "POST" and path == "/api/assistant/confirm":
        payload = request["get_payload"]()
        result = service.confirm(
            payload.get("confirmation_token"),
            payload.get("confirm"),
            payload.get("session_id"),
            trace_id,
        )
    else:
        return False
    if result.get("ok"):
        handler._json(success_payload(result, legacy=result))
    else:
        error = result.get("error") if isinstance(result.get("error"), dict) else {}
        code = str(error.get("code") or "TOOL_EXECUTION_FAILED")
        status = 409 if code in {
            "AMBIGUOUS_CREATOR", "AMBIGUOUS_CAMPAIGN", "TOOL_CONFLICT",
            "CONFIRMATION_EXPIRED", "CONFIRMATION_MISMATCH", "CONFIRMATION_ALREADY_USED",
        } else 400
        handler._json(
            error_payload(
                code,
                str(error.get("message") or "助手操作未完成。"),
                details=result.get("data"),
                legacy={"intent": result.get("intent", "")},
            ),
            status=status,
        )
    return True
