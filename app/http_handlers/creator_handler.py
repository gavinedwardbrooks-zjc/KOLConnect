"""Creator Library, Agency, Extension, and legacy cooperation endpoints."""

import re


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    query = request["query"]
    services = context["services"]

    # POST /api/creator-library/{creator_id}/cooperations → 拒绝新增 Legacy Cooperation；{"ok": false, "error": "请使用 Campaign 创建新的合作。"}
    # PATCH /api/creator-library/{creator_id}/cooperations → 拒绝修改 Legacy Cooperation；{"ok": false, "error": "请使用 Campaign 创建新的合作。"}
    # PUT /api/creator-library/{creator_id}/cooperations → 拒绝替换 Legacy Cooperation；{"ok": false, "error": "请使用 Campaign 创建新的合作。"}
    # DELETE /api/creator-library/{creator_id}/cooperations → 拒绝删除 Legacy Cooperation；{"ok": false, "error": "请使用 Campaign 创建新的合作。"}
    if method in {"POST", "PATCH", "PUT", "DELETE"} and context["config"][
        "legacy_cooperation_pattern"
    ].fullmatch(path):
        handler._error(context["config"]["legacy_cooperation_read_only_message"], status=403)
        return True

    # GET /api/creator-library → 分页读取达人库；{"ok": true, "total": 0, "page": 1, "page_size": 24, "pages": 0, "creators": [...], "filter_options": {...}, "records": [...]}
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
    # GET /api/creator-library/{creator_id}/trend → 读取达人趋势；{"ok": true, "creator_id": "...", "snapshots": [...], "latest": {...}, "previous": {...}, "changes": {...}, "freshness": {...}}
    if method == "GET" and trend_match:
        try:
            handler._json({"ok": True, **services["get_creator_library_trend"](trend_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    snapshots_match = re.fullmatch(r"/api/creator-library/([^/]+)/snapshots", path)
    # GET /api/creator-library/{creator_id}/snapshots → 读取达人快照；{"ok": true, "creator_id": "...", "snapshots": [...]}
    if method == "GET" and snapshots_match:
        try:
            handler._json({"ok": True, **services["get_creator_library_snapshots"](snapshots_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    creator_match = re.fullmatch(r"/api/creator-library/([^/]+)", path)
    # GET /api/creator-library/{creator_id} → 读取达人详情；{"ok": true, "record": {...}, "analysis": {...}, "accounts": [...], "snapshots": [...], "trend": {...}, "history_analysis_times": [...], "cooperations": [...], "cooperation_statistics": {...}}
    if method == "GET" and creator_match:
        try:
            handler._json({"ok": True, **services["get_creator_library_detail"](creator_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    # GET /api/local/agencies → 读取本地 Agency；{"ok": true, "agencies": [...]}
    if method == "GET" and path == "/api/local/agencies":
        handler._json({"ok": True, **services["get_local_agencies"]()})
        return True

    agency_match = re.fullmatch(r"/api/local/agencies/([^/]+)", path)
    # GET /api/local/agencies/{agency_id} → 读取 Agency 详情；{"ok": true, "agency": {...}, "contacts": [...], "creators": [...]}
    if method == "GET" and agency_match:
        try:
            handler._json({"ok": True, **services["get_local_agency_detail"](agency_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    # GET /api/local/agency-contacts → 读取本地 Agency 联系人；{"ok": true, "contacts": [...]}
    if method == "GET" and path == "/api/local/agency-contacts":
        handler._json({"ok": True, **services["get_local_agency_contacts"]()})
        return True

    # GET /api/agency-contacts → 读取可选 Agency 联系人；{"ok": true, "configured": true, "contacts": [...]}
    if method == "GET" and path == "/api/agency-contacts":
        try:
            handler._ok(**services["get_agency_contact_options"]())
        except RuntimeError as exc:
            handler._error(str(exc))
        return True

    # POST /api/extension/import → 导入插件达人数据；{"ok": true, "duplicate": false, "is_new_creator": true, "task": {...}, "account_uid": "...", "analysis_id": "...", "account_id": "...", "snapshot_id": "..."}
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
    # POST /api/creator-library/{creator_id}/status → 更新达人状态；{"ok": true, "analysis_id": "...", "status": "...", "updated_at": "..."}
    if method == "POST" and status_match:
        payload = request["get_payload"]()
        try:
            handler._ok(**services["update_creator_library_status"](status_match.group(1), payload.get("status")))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    relations_match = re.fullmatch(r"/api/creator-library/([^/]+)/relations", path)
    # POST /api/creator-library/{creator_id}/relations → 更新达人 Agency 关系；{"ok": true, "creator_id": "...", "agency_id": "...", "current_contact_id": "...", "source_contact_id": "..."}
    if method == "POST" and relations_match:
        payload = request["get_payload"]()
        try:
            handler._ok(**services["update_creator_local_relations"](relations_match.group(1), payload))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    # POST /api/local/agencies → 保存本地 Agency；{"ok": true, "agency": {...}}
    if method == "POST" and path == "/api/local/agencies":
        try:
            handler._ok(**services["save_local_agency"](request["get_payload"]()))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    # POST /api/local/agency-contacts → 保存本地 Agency 联系人；{"ok": true, "contact": {...}}
    if method == "POST" and path == "/api/local/agency-contacts":
        try:
            handler._ok(**services["save_local_agency_contact"](request["get_payload"]()))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    create_task_match = re.fullmatch(r"/api/creator-library/([^/]+)/create-task", path)
    # POST /api/creator-library/{creator_id}/create-task → 打开达人关联审核任务；{"ok": true, "task": {...}, "created": false, "message": "..."}
    if method == "POST" and create_task_match:
        request["get_payload"]()
        try:
            handler._ok(**services["open_creator_library_collaboration_task"](create_task_match.group(1)))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    # PATCH /api/creator-library/{creator_id} → 更新达人资料；{"ok": true, "creator": {...}}
    if method == "PATCH" and creator_match:
        payload = request["get_payload"]()
        try:
            handler._json({"ok": True, **services["update_creator_library_profile"](creator_match.group(1), payload)})
        except ValueError as exc:
            handler._repository_error(exc)
        return True

    return False
