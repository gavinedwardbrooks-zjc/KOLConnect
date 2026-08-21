"""Read-only campaign publishing and data-risk endpoints."""

import re


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "GET":
        return False

    service = context["services"]["risk"]
    if request["path"] == "/api/risks":
        try:
            handler._json({"ok": True, **service.get_risks()})
        except (OSError, RuntimeError, ValueError) as exc:
            handler._repository_error(exc)
        return True

    match = re.fullmatch(r"/api/campaigns/([^/]+)/missing-publish-links", request["path"])
    if not match:
        return False
    try:
        handler._json({
            "ok": True,
            "missing_publish_links": service.get_missing_publish_links(match.group(1)),
        })
    except (OSError, RuntimeError, ValueError) as exc:
        handler._repository_error(exc)
    return True
