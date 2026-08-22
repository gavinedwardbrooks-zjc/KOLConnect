"""Read-only advanced analytics endpoints."""


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "GET" or request["path"] != "/api/analytics/platforms":
        return False

    try:
        payload = context["services"]["analytics"].get_platform_analytics()
        handler._json({"ok": True, **payload})
    except (OSError, RuntimeError, ValueError) as exc:
        handler._repository_error(exc)
    return True
