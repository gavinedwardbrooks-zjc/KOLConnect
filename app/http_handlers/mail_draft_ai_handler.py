from __future__ import annotations

"""Same-origin HTTP adapter for multilingual templates and AI draft candidates."""

import re

from services.mail_ai_draft_service import MailAIDraftError
from services.mail_send_service import MailSendError
from services.mail_template_service import MailTemplateError


TEMPLATE_PATH = re.compile(r"^/api/mail/templates/([^/]+)$")
RENDER_PATH = re.compile(r"^/api/mail/templates/([^/]+)/render$")
CANDIDATE_PATH = re.compile(r"^/api/mail/ai-draft-candidates/([^/]+)$")
ADOPT_PATH = re.compile(r"^/api/mail/ai-draft-candidates/([^/]+)/adopt$")


def _session(handler, context: dict) -> str:
    return context["services"]["mail_send_sessions"].validate(handler.headers, int(handler.server.server_port))


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    if not (path.startswith("/api/mail/templates") or path.startswith("/api/mail/ai-draft-candidates")):
        return False
    templates = context["services"]["mail_templates"]
    ai_drafts = context["services"]["mail_ai_drafts"]
    try:
        _session(handler, context)
        template_match = TEMPLATE_PATH.fullmatch(path)
        render_match = RENDER_PATH.fullmatch(path)
        candidate_match = CANDIDATE_PATH.fullmatch(path)
        adopt_match = ADOPT_PATH.fullmatch(path)

        if method == "GET" and path == "/api/mail/templates":
            query = request["query"]
            items = templates.list_templates(
                draft_type=query.get("draft_type", [""])[0],
                language=query.get("language", [""])[0],
                include_inactive=query.get("include_inactive", [""])[0].lower() == "true",
            )
            handler._json({"ok": True, "templates": items})
            return True
        if method == "GET" and template_match:
            handler._json({"ok": True, "template": templates.get_template(template_match.group(1))})
            return True
        if method == "POST" and path == "/api/mail/templates":
            handler._json({"ok": True, "template": templates.create_template(request["get_payload"]())}, status=201)
            return True
        if method == "PUT" and template_match:
            handler._json({"ok": True, "template": templates.update_template(template_match.group(1), request["get_payload"]())})
            return True
        if method == "DELETE" and template_match:
            payload = request["get_payload"]()
            handler._json({"ok": True, "template": templates.deactivate_template(
                template_match.group(1), payload.get("template_version")
            )})
            return True
        if method == "POST" and render_match:
            payload = request["get_payload"]()
            handler._json({"ok": True, "rendered": templates.render(render_match.group(1), payload.get("variables"))})
            return True
        if method == "POST" and path == "/api/mail/ai-draft-candidates":
            result = ai_drafts.generate_candidate(request["get_payload"](), trace_id=request["trace_id"])
            handler._json({"ok": result.get("candidate") is not None, **result}, status=201 if result.get("candidate") else 503)
            return True
        if method == "GET" and candidate_match:
            handler._json({"ok": True, "candidate": ai_drafts.get_candidate(candidate_match.group(1))})
            return True
        if method == "POST" and adopt_match:
            handler._json({"ok": True, **ai_drafts.adopt_candidate(adopt_match.group(1), request["get_payload"]())})
            return True
        return False
    except (MailTemplateError, MailAIDraftError, MailSendError) as exc:
        handler._api_error(exc.code, str(exc), status=exc.status)
        return True
