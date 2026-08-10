"""Dashboard HTTP endpoints."""


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "GET" or request["path"] != "/api/dashboard":
        return False

    try:
        handler._json({"ok": True, **context["services"]["get_dashboard_data"]()})
    except (OSError, RuntimeError, ValueError) as exc:
        handler._error(f"无法读取工作台数据：{exc}", status=500)
    return True
