from __future__ import annotations

"""HTTP adapter for explicit single-publication browser capture."""

import re

from services.publication_capture_service import PublicationCaptureError


CREATE_PATH = re.compile(r"^/api/campaign-creators/([^/]+)/publications/([^/]+)/capture-request$")
STATUS_PATH = re.compile(r"^/api/publication-capture/requests/([^/]+)$")
RESULT_PATH = "/api/extension/publication-capture/result"
BATCH_CREATE_PATH = re.compile(r"^/api/campaigns/([^/]+)/publication-capture-batches$")
BATCH_ACTIVE_PATH = re.compile(r"^/api/campaigns/([^/]+)/publication-capture-batches/active$")
BATCH_STATUS_PATH = re.compile(r"^/api/publication-capture/batches/([^/]+)$")
BATCH_ACTION_PATH = re.compile(r"^/api/publication-capture/batches/([^/]+)/(pause|resume|cancel)$")
BATCH_RETRY_PATH = re.compile(r"^/api/publication-capture/batches/([^/]+)/items/([^/]+)/retry$")
EXTENSION_BATCH_PATH = re.compile(r"^/api/extension/publication-capture/batches/([^/]+)/(claim|next|state)$")


def _port(handler) -> int:
    return int(handler.server.server_port)


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    create_match = CREATE_PATH.fullmatch(path)
    status_match = STATUS_PATH.fullmatch(path)
    batch_create = BATCH_CREATE_PATH.fullmatch(path)
    batch_active = BATCH_ACTIVE_PATH.fullmatch(path)
    batch_status = BATCH_STATUS_PATH.fullmatch(path)
    batch_action = BATCH_ACTION_PATH.fullmatch(path)
    batch_retry = BATCH_RETRY_PATH.fullmatch(path)
    extension_batch = EXTENSION_BATCH_PATH.fullmatch(path)
    if not (create_match or status_match or batch_create or batch_active or batch_status or batch_action or batch_retry
            or extension_batch or path in {RESULT_PATH, "/api/publication-capture/security/session"}):
        return False
    service = context["services"]["publication_capture"]
    batch_service = context["services"]["publication_capture_batch"]
    sessions = context["services"]["publication_capture_sessions"]
    try:
        if method == "GET" and path == "/api/publication-capture/security/session":
            issued = sessions.issue(handler.headers, _port(handler))
            handler._json_with_headers(
                {"ok": True, "csrf_token": issued["csrf_token"], "expires_in": 1800},
                {"Set-Cookie": issued["set_cookie"]},
            )
            return True
        if method == "POST" and create_match:
            sessions.validate(handler.headers, _port(handler))
            capture_request = service.create_request(create_match.group(1), create_match.group(2))
            handler._json({"ok": True, "capture_request": capture_request}, status=201)
            return True
        if method == "GET" and status_match:
            sessions.validate(handler.headers, _port(handler))
            handler._json({"ok": True, **service.get_request(status_match.group(1))})
            return True
        if method == "POST" and path == RESULT_PATH:
            payload = request["get_payload"]()
            result = batch_service.submit_result(payload)
            handler._json({"ok": True, **result})
            return True
        if method == "POST" and batch_create:
            sessions.validate(handler.headers, _port(handler))
            result = batch_service.create(batch_create.group(1))
            token = result.pop("claim_token")
            claim_url = f"http://127.0.0.1:{_port(handler)}/#publication-capture-claim={result['batch']['batch_run_id']}.{token}"
            try:
                context["services"]["open_publication_batch_claim"](claim_url)
            except Exception as exc:
                batch_service.interrupt(result["batch"]["batch_run_id"], "BATCH_BROWSER_LAUNCH_FAILED")
                raise PublicationCaptureError(
                    "BATCH_BROWSER_LAUNCH_FAILED", "Chrome 未能启动，请检查所选 Profile 后继续任务。", status=503
                ) from exc
            handler._json({"ok": True, **result}, status=201)
            return True
        if method == "GET" and batch_status:
            sessions.validate(handler.headers, _port(handler))
            handler._json({"ok": True, **batch_service.status(batch_status.group(1))})
            return True
        if method == "GET" and batch_active:
            sessions.validate(handler.headers, _port(handler))
            active = batch_service.active_for_campaign(batch_active.group(1))
            handler._json({"ok": True, "active": active})
            return True
        if method == "POST" and batch_action:
            sessions.validate(handler.headers, _port(handler))
            action = batch_action.group(2)
            result = getattr(batch_service, action)(batch_action.group(1))
            if action == "resume":
                token = result.pop("claim_token")
                claim_url = f"http://127.0.0.1:{_port(handler)}/#publication-capture-claim={result['batch']['batch_run_id']}.{token}"
                try:
                    context["services"]["open_publication_batch_claim"](claim_url)
                except Exception as exc:
                    batch_service.interrupt(result["batch"]["batch_run_id"], "BATCH_BROWSER_LAUNCH_FAILED")
                    raise PublicationCaptureError(
                        "BATCH_BROWSER_LAUNCH_FAILED", "Chrome 未能启动，请检查所选 Profile 后重试。", status=503
                    ) from exc
            handler._json({"ok": True, **result})
            return True
        if method == "POST" and batch_retry:
            sessions.validate(handler.headers, _port(handler))
            handler._json({"ok": True, **batch_service.retry(batch_retry.group(1), batch_retry.group(2))})
            return True
        if method == "POST" and extension_batch:
            payload = request["get_payload"]()
            origin = handler.headers.get("Origin")
            action = extension_batch.group(2)
            if action == "claim":
                result = batch_service.claim(extension_batch.group(1), payload.get("claim_token"), origin)
            elif action == "next":
                result = batch_service.next_item(extension_batch.group(1), payload.get("executor_token"), origin)
            else:
                result = batch_service.executor_state(
                    extension_batch.group(1), payload.get("executor_token"), origin, payload.get("request_id"),
                )
            handler._json({"ok": True, **result})
            return True
        return False
    except PublicationCaptureError as exc:
        handler._api_error(exc.code, str(exc), status=exc.status)
        return True
