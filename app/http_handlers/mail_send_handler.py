"""HTTP adapter for M9.2 native SMTP drafts, confirmation, and send attempts."""

from __future__ import annotations

import re

from services.mail_send_service import MailSendError


DRAFT_PATH = re.compile(r"^/api/mail/drafts/([^/]+)$")
PREVIEW_PATH = re.compile(r"^/api/mail/drafts/([^/]+)/preview$")
ATTEMPT_PATH = re.compile(r"^/api/mail/send-attempts/([^/]+)$")


def _port(handler) -> int:
    return int(handler.server.server_port)


def _session(handler, context: dict) -> str:
    return context["services"]["mail_send_sessions"].validate(handler.headers, _port(handler))


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    if not path.startswith("/api/mail/"):
        return False

    sessions = context["services"]["mail_send_sessions"]
    service = context["services"]["mail_send"]
    try:
        if method == "GET" and path == "/api/mail/send-security/session":
            issued = sessions.issue(handler.headers, _port(handler))
            handler._json_with_headers(
                {"ok": True, "csrf_token": issued["csrf_token"], "expires_in": 1800},
                {"Set-Cookie": issued["set_cookie"]},
            )
            return True

        draft_match = DRAFT_PATH.fullmatch(path)
        preview_match = PREVIEW_PATH.fullmatch(path)
        attempt_match = ATTEMPT_PATH.fullmatch(path)

        if method == "POST" and path == "/api/mail/drafts":
            _session(handler, context)
            handler._json({"ok": True, "draft": service.create_draft(request["get_payload"]())}, status=201)
            return True
        if method == "PUT" and draft_match:
            _session(handler, context)
            handler._json({"ok": True, "draft": service.update_draft(draft_match.group(1), request["get_payload"]())})
            return True
        if method == "DELETE" and draft_match:
            _session(handler, context)
            payload = request["get_payload"]()
            handler._json({"ok": True, **service.delete_draft(draft_match.group(1), payload.get("version"))})
            return True
        if method == "POST" and preview_match:
            session_id = _session(handler, context)
            payload = request["get_payload"]()
            if payload.get("confirm") is True:
                preview_id = payload.get("preview_id")
                result = service.authorize_preview(preview_id, session_id, payload.get("authorization_source"))
                handler._json({"ok": True, "authorization": result})
            else:
                handler._json({"ok": True, "preview": service.create_preview(preview_match.group(1))}, status=201)
            return True
        if method == "POST" and path == "/api/mail/send":
            session_id = _session(handler, context)
            handler._json({"ok": True, "attempt": service.send(request["get_payload"](), session_id)})
            return True
        if method == "GET" and attempt_match:
            session_id = _session(handler, context)
            handler._json({"ok": True, "attempt": service.get_attempt(attempt_match.group(1), session_id)})
            return True
        return False
    except MailSendError as exc:
        handler._api_error(exc.code, str(exc), status=exc.status)
        return True
