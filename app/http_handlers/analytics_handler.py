"""Read-only advanced analytics endpoints."""


def handle(handler, request: dict, context: dict) -> bool:
    if request["method"] != "GET":
        return False

    path = request["path"]
    if path not in {
        "/api/analytics/platforms",
        "/api/analytics/geography",
        "/api/analytics/roi-trend",
    }:
        return False
    service = context["services"]["analytics"]

    try:
        if path == "/api/analytics/platforms":
            handler._json({"ok": True, **service.get_platform_analytics()})
        elif path == "/api/analytics/geography":
            handler._json({"ok": True, **service.get_geography_analytics()})
        elif path == "/api/analytics/roi-trend":
            handler._json({"ok": True, "trend": service.get_recorded_roi_trend()})
    except (OSError, RuntimeError, ValueError) as exc:
        handler._repository_error(exc)
    return True
