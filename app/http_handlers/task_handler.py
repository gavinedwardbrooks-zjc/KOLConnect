"""Task, scrape lifecycle, and task-result HTTP endpoints."""

import re
import subprocess


def handle(handler, request: dict, context: dict) -> bool:
    method = request["method"]
    path = request["path"]
    services = context["services"]

    if method == "GET" and path == "/api/tasks":
        handler._json({"ok": True, **services["get_task_list"]()})
        return True

    task_details_match = re.fullmatch(r"/api/tasks/([^/]+)/details", path)
    if method == "GET" and task_details_match:
        try:
            handler._json({"ok": True, **services["get_task_details"](task_details_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    task_results_match = re.fullmatch(r"/api/tasks/([^/]+)/results", path)
    if method == "GET" and task_results_match:
        try:
            handler._json({"ok": True, **services["get_task_review_results"](task_results_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc))
        return True

    task_analysis_match = re.fullmatch(r"/api/tasks/([^/]+)/creator-analysis", path)
    if method == "GET" and task_analysis_match:
        try:
            handler._json({"ok": True, **services["get_task_creator_analysis"](task_analysis_match.group(1))})
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    if method == "GET" and path == "/api/scrape/status":
        handler._json(context["scrape_job"].snapshot())
        return True

    task_match = re.fullmatch(r"/api/tasks/([^/]+)", path)
    if method == "DELETE" and task_match:
        try:
            handler._ok(**services["delete_local_task"](task_match.group(1)))
        except RuntimeError as exc:
            handler._error(str(exc), status=409)
        except ValueError as exc:
            handler._error(str(exc), status=404)
        return True

    if method != "POST":
        return False

    task_links_match = re.fullmatch(r"/api/tasks/([^/]+)/links", path)
    if task_links_match:
        payload = request["get_payload"]()
        result = services["update_task_links"](
            task_links_match.group(1),
            action=payload.get("action"),
            index=payload.get("index"),
            url=payload.get("url"),
        )
        handler._ok(**result)
        return True

    task_resume_match = re.fullmatch(r"/api/tasks/([^/]+)/resume", path)
    if task_resume_match:
        request["get_payload"]()
        handler._ok(**services["resume_task"](task_resume_match.group(1)))
        return True

    task_stop_match = re.fullmatch(r"/api/tasks/([^/]+)/stop", path)
    if task_stop_match:
        request["get_payload"]()
        handler._ok(**services["stop_task"](task_stop_match.group(1)))
        return True

    task_result_update_match = re.fullmatch(r"/api/tasks/([^/]+)/results/update", path)
    if task_result_update_match:
        payload = request["get_payload"]()
        try:
            result = services["update_task_review_result"](
                task_result_update_match.group(1), payload.get("account_uid"), payload.get("fields")
            )
            handler._ok(**result)
        except (ValueError, RuntimeError) as exc:
            handler._error(str(exc))
        return True

    task_retry_match = re.fullmatch(r"/api/tasks/([^/]+)/results/retry-failed", path)
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

    task_sync_match = re.fullmatch(r"/api/tasks/([^/]+)/sync-four-tables", path)
    if task_sync_match:
        request["get_payload"]()
        try:
            result = services["sync_task_results_to_four_tables"](task_sync_match.group(1))
            if result["sync_status"] != "success":
                handler._json({"ok": False, "error": "任务四表同步失败。", **result}, status=400)
            else:
                handler._ok(**result)
        except (ValueError, RuntimeError) as exc:
            handler._error(str(exc))
        return True

    task_open_results_match = re.fullmatch(r"/api/tasks/([^/]+)/results/open", path)
    if task_open_results_match:
        request["get_payload"]()
        try:
            _task, task_paths = context["task_manager"].load_task(
                context["paths"]["tasks"], task_open_results_match.group(1)
            )
            if not task_paths["results"].exists():
                handler._error("当前任务尚未生成结果文件。")
            else:
                subprocess.Popen(["explorer.exe", str(task_paths["results"])])
                handler._ok()
        except ValueError as exc:
            handler._error(str(exc))
        return True

    task_rename_match = re.fullmatch(r"/api/tasks/([^/]+)/rename", path)
    if task_rename_match:
        payload = request["get_payload"]()
        try:
            handler._ok(task=services["rename_task"](task_rename_match.group(1), payload.get("name")))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    if path == "/api/normalize-links":
        payload = request["get_payload"]()
        if isinstance(payload.get("links"), list):
            raw_links = [str(item or "").strip() for item in payload.get("links", [])]
        else:
            text = str(payload.get("text") or "")
            raw_links = [line.strip() for line in text.splitlines() if line.strip()]
        normalized = context["modules"]["scraper"].build_normalize_payload(raw_links)
        handler._ok(
            normalized_links=normalized.get("normalized_links", []),
            invalid_links=normalized.get("invalid_links", []),
        )
        return True

    if path == "/api/tasks/manual":
        payload = request["get_payload"]()
        try:
            handler._ok(**services["create_manual_task"](payload))
        except ValueError as exc:
            handler._error(str(exc))
        return True

    if path == "/api/tasks/email-recheck/scan":
        request["get_payload"]()
        try:
            handler._ok(**services["create_email_recheck_task"]())
        except (RuntimeError, ValueError) as exc:
            handler._error(str(exc))
        return True

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
        task = context["task_manager"].create_task(
            context["paths"]["tasks"],
            prepared["normalized_links"],
            prepared["invalid_links"],
            len(raw_links),
            name=payload.get("name"),
            target_platform=prepared["target_platform"],
            platforms=prepared["platforms"],
            platform_summary=prepared["platform_summary"],
            filtered_links=prepared["filtered_links"],
        )
        handler._ok(task=task, invalid_links=prepared["invalid_links"], filtered_links=prepared["filtered_links"])
        return True

    scrape_actions = {
        "/api/scrape/start": ("start_scrape", True),
        "/api/scrape/stop": ("request_stop_scrape", False),
        "/api/scrape/pause": ("pause_scrape", False),
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
