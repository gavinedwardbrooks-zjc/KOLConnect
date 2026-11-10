"""HTTP adapter for bounded Chrome Extension workspace operations."""

from __future__ import annotations

from services.extension_workspace_service import ExtensionWorkspaceError
from services.mail_send_service import MailSendError
from services.mail_template_service import MailTemplateError


def handle(handler, request: dict, context: dict) -> bool:
    path = request["path"]
    method = request["method"]
    if not path.startswith("/api/extension/workspace/") and path != "/api/extension/discovery/candidates/lookup":
        return False
    service = context["services"]["extension_workspace"]
    try:
        if method == "GET" and path == "/api/extension/workspace/options":
            query = request["query"]
            result = service.options(
                platform=query.get("platform", [""])[0], profile_url=query.get("profile_url", [""])[0],
                audience_type=query.get("audience_type", [""])[0], language=query.get("language", [""])[0],
            )
            handler._json({"ok": True, **result})
            return True
        if method == "POST" and path == "/api/extension/workspace/template-preview":
            handler._json({"ok": True, **service.render(request["get_payload"]())})
            return True
        if method == "POST" and path == "/api/extension/workspace/drafts":
            handler._json({"ok": True, **service.create_draft(request["get_payload"]())}, status=201)
            return True
        if method == "POST" and path == "/api/extension/discovery/candidates/lookup":
            payload = request["get_payload"]()
            handler._json({"ok": True, "candidates": service.lookup_candidates(payload.get("profile_urls"))})
            return True
        return False
    except (ExtensionWorkspaceError, MailTemplateError, MailSendError) as exc:
        handler._api_error(exc.code, str(exc), status=exc.status)
        return True
