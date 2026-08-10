"""Creator Library, Agency, Extension, and legacy cooperation endpoints."""

import re


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    query = request["query"]
    services = context["services"]

    if method in {"POST", "PATCH", "PUT", "DELETE"} and context["config"][
        "legacy_cooperation_pattern"
    ].fullmatch(path):
        handler._error(context["config"]["legacy_cooperation_read_only_message"], status=403)
        return True

    if method == "GET" and path == "/api/creator-library":
        include_archived = query.get("include_archived", [""])[0].lower() == "true"
        try:
            payload = services["get_creator_library"](
                include_archived=include_archived,
                page=int(query.get("page", ["1"])[0]),
                page_size=int(query.get("page_size", ["24"])[0]),
                sort=str(query.get("sort", ["created_at"])[0]),
                order=str(query.get("order", ["desc"])[0]).lower(),
                filters={
                    key: query.get(key, [""])[0]
                    for key in (
                        "search", "platform", "country", "language", "content_category",
                        "agency_id", "tag", "insight_level", "status",
                    )
                    if query.get(key, [""])[0]
                },
            )
        except (TypeError, ValueError) as exc:
            handler._error(str(exc), status=400)
            return True
        handler._json({"ok": True, **payload})
        return True

    trend_match = re.fullmatch(r"/api/creator-library/([^/]+)/trend", path)
    if method == "GET" and trend_match:
        try:
            handler._json({"ok": True, **services["get_creator_library_trend"](trend_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    snapshots_match = re.fullmatch(r"/api/creator-library/([^/]+)/snapshots", path)
    if method == "GET" and snapshots_match:
        try:
            handler._json({"ok": True, **services["get_creator_library_snapshots"](snapshots_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    creator_match = re.fullmatch(r"/api/creator-library/([^/]+)", path)
    if method == "GET" and creator_match:
        try:
            handler._json({"ok": True, **services["get_creator_library_detail"](creator_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    if method == "GET" and path == "/api/local/agencies":
        handler._json({"ok": True, **services["get_local_agencies"]()})
        return True

    agency_match = re.fullmatch(r"/api/local/agencies/([^/]+)", path)
    if method == "GET" and agency_match:
        try:
            handler._json({"ok": True, **services["get_local_agency_detail"](agency_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    if method == "GET" and path == "/api/local/agency-contacts":
        handler._json({"ok": True, **services["get_local_agency_contacts"]()})
        return True

    if method == "GET" and path == "/api/agency-contacts":
        try:
            handler._ok(**services["get_agency_contact_options"]())
        except RuntimeError as exc:
            handler._error(str(exc))
        return True

    if method == "POST" and path == "/api/extension/import":
        payload = request["get_payload"]()
        try:
            result = services["import_extension_capture"](payload)
            creator = payload.get("creator") if isinstance(payload.get("creator"), dict) else {}
            services["record_diagnostic"](
                "last_extension_import",
                {
                    "status": "success",
                    "time": services["utc_now"](),
                    "creator": str(creator.get("creator_name") or "").strip(),
                    "platform": str(creator.get("platform") or "").strip(),
                },
            )
            context["logging"]["event"](
                "Extension",
                f"导入成功 | creator={creator.get('creator_name') or '--'} | platform={creator.get('platform') or '--'}",
            )
            handler._ok(**result)
        except (RuntimeError, ValueError) as exc:
            services["record_diagnostic"](
                "last_extension_import", {"status": "failed", "time": services["utc_now"]()}
            )
            handler._error(str(exc))
        return True

    status_match = re.fullmatch(r"/api/creator-library/([^/]+)/status", path)
    if method == "POST" and status_match:
        payload = request["get_payload"]()
        try:
            handler._ok(**services["update_creator_library_status"](status_match.group(1), payload.get("status")))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    relations_match = re.fullmatch(r"/api/creator-library/([^/]+)/relations", path)
    if method == "POST" and relations_match:
        payload = request["get_payload"]()
        try:
            handler._ok(**services["update_creator_local_relations"](relations_match.group(1), payload))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    if method == "POST" and path == "/api/local/agencies":
        try:
            handler._ok(**services["save_local_agency"](request["get_payload"]()))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    if method == "POST" and path == "/api/local/agency-contacts":
        try:
            handler._ok(**services["save_local_agency_contact"](request["get_payload"]()))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    create_task_match = re.fullmatch(r"/api/creator-library/([^/]+)/create-task", path)
    if method == "POST" and create_task_match:
        request["get_payload"]()
        try:
            handler._ok(**services["open_creator_library_collaboration_task"](create_task_match.group(1)))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    if method == "PATCH" and creator_match:
        payload = request["get_payload"]()
        try:
            handler._json({"ok": True, **services["update_creator_library_profile"](creator_match.group(1), payload)})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    return False
