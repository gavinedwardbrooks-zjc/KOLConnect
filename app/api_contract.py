from __future__ import annotations

"""Small API envelope and request-correlation primitives."""

from contextvars import ContextVar
from typing import Any, Mapping
import uuid


_TRACE_ID: ContextVar[str] = ContextVar("kolconnect_trace_id", default="")


def new_trace_id() -> str:
    return f"trace_{uuid.uuid4().hex}"


def set_trace_id(trace_id: str) -> None:
    _TRACE_ID.set(str(trace_id or "").strip())


def get_trace_id() -> str:
    return _TRACE_ID.get()


def success_payload(
    data: Any = None, *, legacy: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True, "data": data}
    if legacy:
        payload.update(dict(legacy))
    return payload


def error_payload(
    code: str,
    message: str,
    *,
    details: Any = None,
    legacy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": str(code or "INTERNAL_ERROR"),
        "message": str(message or "请求处理失败。"),
    }
    if details is not None:
        error["details"] = details
    payload: dict[str, Any] = {"ok": False, "error": error}
    if legacy:
        payload.update(dict(legacy))
    return payload


def status_error_code(status: int) -> str:
    return {
        400: "INVALID_REQUEST",
        401: "AUTHENTICATION_ERROR",
        403: "PERMISSION_ERROR",
        404: "NOT_FOUND",
        409: "CONFLICT",
        423: "LOCK_TIMEOUT",
        429: "RATE_LIMITED",
        502: "REMOTE_SERVICE_ERROR",
        503: "TRANSIENT_NETWORK_ERROR",
    }.get(int(status), "INTERNAL_ERROR" if int(status) >= 500 else "VALIDATION_ERROR")
