"""Task, scrape lifecycle, and task-result HTTP endpoints."""

import re

from services.task_service import TaskReviewError


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    services = context["services"]
    task_service = services["task"]

    # GET /api/tasks → 读取任务列表；{"ok": true, "tasks": [...]}
    if method == "GET" and path == "/api/tasks":
        handler._json({"ok": True, **task_service.get_tasks()})
        return True

    task_details_match = re.fullmatch(r"/api/tasks/([^/]+)/details", path)
    # GET /api/tasks/{task_id}/details → 读取任务详情；{"ok": true, "task": {...}, "links": [...]}
    if method == "GET" and task_details_match:
        try:
            handler._json({"ok": True, **task_service.get_task_details(task_details_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    task_results_match = re.fullmatch(r"/api/tasks/([^/]+)/results", path)
    # GET /api/tasks/{task_id}/results → 读取任务审核结果；{"ok": true, "task_id": "...", "platforms": [...], "platform_results": {...}, "creator_analysis_available": false, "records": [...]}
    if method == "GET" and task_results_match:
        try:
            handler._json({"ok": True, **task_service.get_task_results(task_results_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc))
        return True

    task_analysis_match = re.fullmatch(r"/api/tasks/([^/]+)/creator-analysis", path)
    # GET /api/tasks/{task_id}/creator-analysis → 读取任务达人分析；{"ok": true, "available": false}
    if method == "GET" and task_analysis_match:
        try:
            handler._json({"ok": True, **task_service.get_task_creator_analysis(task_analysis_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    # GET /api/scrape/status → 读取当前抓取状态；{"running": false, "status": "idle", "pause_requested": false, "stop_requested": false, "logs": "", "has_results": false, "task_id": ""}
    if method == "GET" and path == "/api/scrape/status":
        handler._json(task_service.get_scrape_status())
        return True

    task_match = re.fullmatch(r"/api/tasks/([^/]+)", path)
    # DELETE /api/tasks/{task_id} → 删除本地任务；{"ok": true, "task_id": "...", "deleted": true}
    if method == "DELETE" and task_match:
        try:
            handler._ok(**task_service.delete_task(task_match.group(1)))
        except RuntimeError as exc:
            handler._error(str(exc), status=409)
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    if method != "POST":
        return False

    task_links_match = re.fullmatch(r"/api/tasks/([^/]+)/links", path)
    # POST /api/tasks/{task_id}/links → 修改任务链接；{"ok": true, "task": {...}, "links": [...]}
    if task_links_match:
        payload = request["get_payload"]()
        result = task_service.update_task_links(
            task_links_match.group(1),
            action=payload.get("action"),
            index=payload.get("index"),
            url=payload.get("url"),
        )
        handler._ok(**result)
        return True

    task_resume_match = re.fullmatch(r"/api/tasks/([^/]+)/resume", path)
    # POST /api/tasks/{task_id}/resume → 恢复任务；{"ok": true, "task_id": "..."}
    if task_resume_match:
        request["get_payload"]()
        handler._ok(**services["resume_task"](task_resume_match.group(1)))
        return True

    task_stop_match = re.fullmatch(r"/api/tasks/([^/]+)/stop", path)
    # POST /api/tasks/{task_id}/stop → 停止任务；{"ok": true, "task_id": "...", "status": "stopped"}
    if task_stop_match:
        request["get_payload"]()
        handler._ok(**services["stop_task"](task_stop_match.group(1)))
        return True

    task_result_update_match = re.fullmatch(r"/api/tasks/([^/]+)/results/update", path)
    # POST /api/tasks/{task_id}/results/update → 保存审核结果；{"ok": true, "task_id": "...", "account_uid": "...", "modified_fields": {...}, "data_status": "待同步", "modified_at": "...", "creator_library_import": {...}}
    if task_result_update_match:
        payload = request["get_payload"]()
        try:
            result = task_service.update_task_results(
                task_result_update_match.group(1), payload.get("account_uid"), payload.get("fields")
            )
            handler._ok(**result)
        except (ValueError, RuntimeError) as exc:
            handler._error(str(exc))
        return True

    task_result_review_match = re.fullmatch(r"/api/tasks/([^/]+)/results/review", path)
    # POST /api/tasks/{task_id}/results/review → 审核一个结果；支持 reject/approve/edit_approve。
    if task_result_review_match:
        payload = request["get_payload"]()
        action = str(payload.get("action") or "").strip()
        if not action:
            handler._json({"ok": False, "error": "REVIEW_ACTION_REQUIRED"}, status=400)
            return True
        if action not in {"reject", "approve", "edit_approve"}:
            handler._json({"ok": False, "error": "REVIEW_ACTION_UNSUPPORTED"}, status=400)
            return True
        try:
            task_id = task_result_review_match.group(1)
            if action == "reject":
                if payload.get("fields") not in (None, {}):
                    raise TaskReviewError("REVIEW_FIELDS_NOT_ALLOWED")
                result = task_service.reject_task_result(
                    task_id, payload.get("account_uid"), payload.get("rejection_reason")
                )
            elif action == "approve":
                if payload.get("fields") not in (None, {}):
                    raise TaskReviewError("REVIEW_FIELDS_NOT_ALLOWED")
                result = task_service.approve_task_result(task_id, payload.get("account_uid"))
            else:
                result = task_service.edit_approve_task_result(
                    task_id, payload.get("account_uid"), payload.get("fields")
                )
            handler._json({"ok": True, **result})
        except TaskReviewError as exc:
            handler._json(exc.to_response(), status=exc.status)
        return True

    task_retry_match = re.fullmatch(r"/api/tasks/([^/]+)/results/retry-failed", path)
    # POST /api/tasks/{task_id}/results/retry-failed → 重试失败结果；{"ok": true, "task": {...}, "retried_count": 0, "retry_round": 1, "started": true}
    if task_retry_match:
        payload = request["get_payload"]()
        try:
            selected = payload.get("account_uids")
            account_uids = selected if isinstance(selected, list) else []
            result = services["retry_failed_task_results"](task_retry_match.group(1), account_uids)
            services["start_scrape"](
                {"taskId": task_retry_match.group(1), "profile": payload.get("profile")}
            )
            handler._ok(**result, started=True)
        except (ValueError, RuntimeError) as exc:
            handler._error(str(exc))
        return True

    task_open_results_match = re.fullmatch(r"/api/tasks/([^/]+)/results/open", path)
    # POST /api/tasks/{task_id}/results/open → 在 Explorer 打开结果文件；{"ok": true}
    if task_open_results_match:
        request["get_payload"]()
        try:
            task_service.open_task_results(task_open_results_match.group(1))
            handler._ok()
        except ValueError as exc:
            handler._error(str(exc))
        return True

    task_open_result_folder_match = re.fullmatch(r"/api/tasks/([^/]+)/results/open-folder", path)
    # POST /api/tasks/{task_id}/results/open-folder → 打开受控任务结果目录；{"ok": true}
    if task_open_result_folder_match:
        request["get_payload"]()
        try:
            task_service.open_task_result_folder(task_open_result_folder_match.group(1))
            handler._ok()
        except ValueError as exc:
            handler._error(str(exc))
        return True

    task_rename_match = re.fullmatch(r"/api/tasks/([^/]+)/rename", path)
    # POST /api/tasks/{task_id}/rename → 重命名任务；{"ok": true, "task": {...}}
    if task_rename_match:
        payload = request["get_payload"]()
        try:
            handler._ok(task=task_service.rename_task(task_rename_match.group(1), payload.get("name")))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    # POST /api/normalize-links → 标准化达人链接并返回逐行处理明细。
    if path == "/api/normalize-links":
        payload = request["get_payload"]()
        if isinstance(payload.get("links"), list):
            source_lines = [str(item or "") for item in payload.get("links", [])]
        else:
            text = str(payload.get("text") or "")
            source_lines = text.splitlines()
        numbered_links = [
            (line_number, value.strip())
            for line_number, value in enumerate(source_lines, start=1)
            if value.strip()
        ]
        normalized = context["modules"]["scraper"].build_normalize_payload(
            [value for _line_number, value in numbered_links],
            [line_number for line_number, _value in numbered_links],
        )
        handler._ok(
            normalized_links=normalized.get("normalized_links", []),
            invalid_links=normalized.get("invalid_links", []),
            link_results=normalized.get("link_results", []),
            summary=normalized.get("summary", {}),
        )
        return True

    # POST /api/tasks/manual → 创建人工任务；{"ok": true, "task": {...}, "account_uid": "...", "creator_library_import": {...}}
    if path == "/api/tasks/manual":
        payload = request["get_payload"]()
        try:
            handler._ok(**services["create_manual_task"](payload))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    # POST /api/tasks/email-recheck/scan → 创建邮箱补全任务；{"ok": true, "task": {...}, "scanned_accounts": 0, "created_count": 0, "skipped_count": 0, "skipped": [...], "duplicate_uids": [...]}
    if path == "/api/tasks/email-recheck/scan":
        request["get_payload"]()
        try:
            handler._ok(**task_service.create_email_recheck_task())
        except (RuntimeError, ValueError) as exc:
            handler._error(str(exc))
        return True

    # POST /api/tasks → 创建抓取任务；{"ok": true, "task": {...}, "invalid_links": [...], "filtered_links": [...]}
    if path == "/api/tasks":
        payload = request["get_payload"]()
        text = str(payload.get("text") or "")
        raw_links = [line.strip() for line in text.splitlines() if line.strip()]
        if not raw_links:
            handler._error("请粘贴至少一个链接。")
            return True
        prepared = services["prepare_task_links"](raw_links, payload.get("platforms") if isinstance(payload.get("platforms"), list) else payload.get("platform") or payload.get("target_platform"))
        if not prepared["normalized_links"]:
            handler._error("没有符合目标平台的有效链接。")
            return True
        task = task_service.create_scrape_task(
            normalized_links=prepared["normalized_links"],
            invalid_links=prepared["invalid_links"],
            input_count=len(raw_links),
            name=payload.get("name"),
            target_platform=prepared["target_platform"],
            platforms=prepared["platforms"],
            platform_summary=prepared["platform_summary"],
            filtered_links=prepared["filtered_links"],
        )
        handler._ok(task=task, invalid_links=prepared["invalid_links"], filtered_links=prepared["filtered_links"])
        return True

    scrape_actions = {
        # POST /api/scrape/start → 启动抓取；{"ok": true, "task_id": "..."}
        "/api/scrape/start": ("start_scrape", True),
        # POST /api/scrape/stop → 请求停止抓取；{"ok": true, "task_id": "...", "status": "stopping"}
        "/api/scrape/stop": ("request_stop_scrape", False),
        # POST /api/scrape/pause → 暂停抓取；{"ok": true, "task_id": "...", "status": "paused"}
        "/api/scrape/pause": ("pause_scrape", False),
        # POST /api/scrape/resume → 恢复抓取；{"ok": true, "task_id": "...", "status": "running"}
        "/api/scrape/resume": ("resume_scrape", False),
    }
    if path in scrape_actions:
        payload = request["get_payload"]()
        service_name, accepts_payload = scrape_actions[path]
        try:
            result = services[service_name](payload) if accepts_payload else services[service_name]()
            handler._ok(**result)
        except RuntimeError as exc:
            handler._error(str(exc), status=409)
        return True

    return False
