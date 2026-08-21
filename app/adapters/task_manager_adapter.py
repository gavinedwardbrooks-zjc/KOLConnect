from __future__ import annotations

"""TaskPort adapter over task persistence and existing scrape domain helpers."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import subprocess
import sys
from typing import Callable, Mapping

import scraper as scraper_module
from ports.task_port import (
    CreatedTask,
    CreatorImportLinkage,
    EmailRecheckTaskCommand,
    ManualTaskCreateCommand,
    ManualTaskCreationResult,
    ManualTaskInitializationCommand,
    ManualReviewTaskCommand,
    RetryFailedResultsCommand,
    ScrapeTaskCreateCommand,
    TaskLinksUpdateCommand,
    TaskReadResult,
    TaskResultImportLinkage,
    TaskSyncStatusUpdate,
    TaskSnapshot,
    TaskRuntimeSnapshot,
    TaskRuntimeDocuments,
    TaskSummaryDocuments,
    RuntimeProgressUpdate,
    TaskFinalizationDocuments,
)
from repositories.task_repository import TaskCsvDocument, TaskRepository


TasksDirectoryProvider = Callable[[], Path]
ScrapeStatusProvider = Callable[[], Mapping[str, object]]

_REVIEW_FIELD_WHATSAPP = "WhatsApp"
_REVIEW_FIELD_NOTE = "备注"
_REVIEW_FIELD_DATA_STATUS = "数据状态"
_REVIEW_FIELD_MODIFIED_AT = "最后修改时间"
_PLATFORMS = ("TikTok", "Instagram", "YouTube")
_RETRYABLE_SCRAPE_STATUSES = {
    "missing_data",
    "failed",
    "login_required",
    "platform_error",
}


class TaskManagerAdapter:
    """Translate neutral task DTOs without exposing task files or manager state."""

    def __init__(
        self,
        tasks_directory_provider: TasksDirectoryProvider,
        scrape_status_provider: ScrapeStatusProvider | None = None,
        heartbeat_interval: int = 240,
    ) -> None:
        self._tasks_directory_provider = tasks_directory_provider
        self._scrape_status_provider = scrape_status_provider
        self._heartbeat_interval = heartbeat_interval

    def create_manual_review_task(
        self, command: ManualReviewTaskCommand
    ) -> CreatedTask:
        task = self._repository().create_task(
            list(command.normalized_links),
            list(command.invalid_links),
            command.input_count,
            name=command.name,
            target_platform=command.target_platform,
            platforms=list(command.platforms),
            platform_summary=dict(command.platform_summary),
            task_type="manual",
        )
        return CreatedTask(task=self._snapshot(task))

    def create_scrape_task(self, command: ScrapeTaskCreateCommand) -> CreatedTask:
        task = self._repository().create_task(
            list(command.normalized_links),
            list(command.invalid_links),
            command.input_count,
            name=command.name,
            target_platform=command.target_platform,
            platforms=list(command.platforms),
            platform_summary=dict(command.platform_summary),
            filtered_links=[dict(item) for item in command.filtered_links],
            task_type="scrape",
        )
        return CreatedTask(task=self._snapshot(task))

    def open_task_results(self, task_id: str) -> None:
        paths = self._repository()._paths(task_id)
        self._repository().get_task(task_id)
        if not paths["results"].exists():
            raise ValueError("当前任务尚未生成结果文件。")
        subprocess.Popen(["explorer.exe", str(paths["results"])])

    def open_task_result_folder(self, task_id: str) -> None:
        paths = self._repository()._paths(task_id)
        self._repository().get_task(task_id)
        task_directory = paths["root"]
        if not task_directory.is_dir():
            raise ValueError("当前任务结果文件夹不可用。")
        if os.name == "nt":
            command = ["explorer.exe", str(task_directory)]
        elif sys.platform == "darwin":
            command = ["open", str(task_directory)]
        else:
            command = ["xdg-open", str(task_directory)]
        subprocess.Popen(command)

    def create_manual_task(self, command: ManualTaskCreateCommand) -> CreatedTask:
        task = self._repository().create_task(
            [command.normalized_url],
            [],
            1,
            name=command.task_name,
            target_platform=command.platform,
            platform_summary=dict(command.platform_summary),
            task_type="manual",
        )
        return CreatedTask(task=self._snapshot(task))

    def initialize_manual_task(
        self, task_id: str, command: ManualTaskInitializationCommand
    ) -> ManualTaskCreationResult:
        now = self._utc_now()
        result = scraper_module.build_result(
            url=command.profile_url,
            platform=command.platform,
            name=command.creator_name,
            emails=(
                []
                if not command.email
                else [item.strip() for item in command.email.split(",") if item.strip()]
            ),
            email_source="人工录入" if command.email else "",
            follower_count=command.follower_count,
            status="手动录入",
            whatsapp=command.whatsapp,
            note=command.note,
            data_status="待检查",
            last_modified_at=now,
        )
        account_uid = scraper_module.build_creator_uid(result)
        result_row = scraper_module.result_to_row(result)
        progress_row = dict(result_row)
        progress_row[scraper_module.FIELD_STATUS] = "待补充抓取"
        manual_values = {
            field: value
            for field, value in {
                scraper_module.FIELD_NAME: command.creator_name,
                scraper_module.FIELD_EMAIL: command.email,
                scraper_module.FIELD_FOLLOWER_COUNT: command.follower_count,
                _REVIEW_FIELD_WHATSAPP: command.whatsapp,
                _REVIEW_FIELD_NOTE: command.note,
            }.items()
            if value
        }
        modifications = []
        if manual_values:
            modifications.append(
                {
                    "account_uid": account_uid,
                    "modified_fields": {
                        field: {"old": "", "new": value}
                        for field, value in manual_values.items()
                    },
                    "status": "pending_sync",
                    "time": now,
                    "source": "manual_task",
                }
            )
        metadata_changes: dict[str, object] = {
            "status": "manual_created",
            "completed_count": 0,
            "modified_count": len(modifications),
            "last_modified_time": now if manual_values else "",
            "source_contact_record_id": command.source_contact_record_id,
            "local_source_contact_id": command.local_source_contact_id,
        }
        if command.source_contact_record_id:
            metadata_changes["source_contact_name"] = command.source_contact_name
        task = self._repository().write_task_documents(
            task_id,
            results=TaskCsvDocument(
                tuple(scraper_module.OUTPUT_FIELDS), (result_row,)
            ),
            progress=TaskCsvDocument(
                tuple(scraper_module.PROGRESS_FIELDS), (progress_row,)
            ),
            modifications=modifications,
            metadata_changes=metadata_changes,
        )
        return ManualTaskCreationResult(
            task=self._snapshot(task),
            account_uid=account_uid,
            modified_at=now,
        )

    def create_email_recheck_task(
        self, command: EmailRecheckTaskCommand
    ) -> CreatedTask:
        rows: list[dict[str, object]] = []
        for item in command.items:
            result = scraper_module.build_result(
                url=item.profile_url,
                platform=item.platform,
                name=item.username,
                status="待补全",
                data_status="待检查",
            )
            rows.append(scraper_module.result_to_row(result))

        repository = self._repository()
        task = repository.create_task(
            [item.profile_url for item in command.items],
            [],
            len(command.items),
            name=command.name,
            target_platform="全部",
            platform_summary=dict(command.platform_summary),
            task_type="email_recheck",
        )
        progress_rows = [
            dict(row, **{scraper_module.FIELD_STATUS: "待补全"}) for row in rows
        ]
        task = repository.write_task_documents(
            task["id"],
            results=TaskCsvDocument(
                tuple(scraper_module.OUTPUT_FIELDS), tuple(rows)
            ),
            progress=TaskCsvDocument(
                tuple(scraper_module.PROGRESS_FIELDS), tuple(progress_rows)
            ),
            modifications=[],
            metadata_changes={
                "status": "email_recheck_created",
                "email_recheck_source": "local_account_empty_email",
                "scan_skipped_count": command.skipped_count,
            },
        )
        return CreatedTask(task=self._snapshot(task))

    def get_task(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._repository().get_task(task_id))

    def get_runtime_task_snapshot(self, task_id: str) -> TaskRuntimeSnapshot:
        return self._runtime_snapshot(self._repository().get_task(task_id))

    def get_runtime_documents(self, task_id: str) -> TaskRuntimeDocuments:
        repository = self._repository()
        repository.get_task(task_id)
        paths = repository._paths(task_id)
        return TaskRuntimeDocuments(
            links_file=str(paths["links"]), progress_file=str(paths["progress"]),
            results_file=str(paths["results"]), metadata_file=str(paths["metadata"]),
        )

    def get_task_summary_documents(self, task_id: str) -> TaskSummaryDocuments:
        repository = self._repository()
        repository.get_task(task_id)
        try:
            links = tuple(repository.read_links(task_id))
        except OSError:
            links = ()
        progress = tuple(repository.read_progress(task_id))
        available = repository.results_exist(task_id)
        rows = tuple(repository.read_results(task_id)) if available else ()
        return TaskSummaryDocuments(links, progress, rows, available)

    def list_recovery_candidates(self) -> tuple[TaskRuntimeSnapshot, ...]:
        return tuple(self._runtime_snapshot(task) for task in self._repository().list_tasks())

    def recover_stopping_task(self, task_id: str, *, finished_at: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(
            task_id, status="stopped", stop_requested=False, pause_requested=False,
            browser_status="closed", worker_status="stopped", current_item="", finished_at=finished_at,
        ))

    def mark_task_interrupted(self, task_id: str, *, interrupted_at: str, reason: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(
            task_id, status="interrupted", pause_requested=False, stop_requested=False,
            browser_status="closed", worker_status="stopped", interrupted_time=interrupted_at,
            interrupted_reason=reason,
        ))

    def start_runtime_task(self, task_id: str, *, profile: str, started_at: str, heartbeat_interval: int, completed_count: int, current_item: str, last_progress_time: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(
            task_id, status="running", started_at=started_at, finished_at="", profile=profile,
            feishu_enabled=False, last_error="", sync_status="not_requested", sync_summary={},
            sync_errors=[], pause_requested=False, stop_requested=False, heartbeat_time=started_at,
            heartbeat_interval=heartbeat_interval, last_progress_time=last_progress_time,
            current_item=current_item, completed_count=completed_count,
            last_successful_index=completed_count, browser_status="starting", worker_status="starting",
            interrupted_time="", interrupted_reason="", instagram_error_count=0,
            instagram_status="", instagram_message="",
        ))

    def mark_runtime_worker_running(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(
            task_id, status="running", browser_status="running", worker_status="running"
        ))

    def persist_runtime_progress(self, task_id: str, update: RuntimeProgressUpdate) -> TaskSnapshot:
        changes = {
            "completed_count": update.completed_count,
            "last_successful_index": update.last_successful_index,
            "current_item": update.current_item,
            "last_progress_time": update.last_progress_time,
            "heartbeat_time": update.heartbeat_time,
            "instagram_error_count": update.instagram_error_count,
            "instagram_status": update.instagram_status,
            "instagram_message": update.instagram_message,
        }
        return self._snapshot(self._repository().update_task(task_id, **{key: value for key, value in changes.items() if value != "" or key in {"current_item", "heartbeat_time"}}))

    def mark_runtime_paused(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(task_id, status="paused", pause_requested=True, browser_status="open", worker_status="sleep"))

    def mark_runtime_resumed(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(task_id, status="running", pause_requested=False, browser_status="running", worker_status="running"))

    def request_runtime_stop(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(task_id, status="stopping", pause_requested=False, stop_requested=True, worker_status="stopping"))

    def mark_runtime_finalizing(self, task_id: str, *, metadata_changes: Mapping[str, object]) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(task_id, status="finalizing", **dict(metadata_changes)))

    def complete_runtime_task(self, task_id: str, *, finished_at: str, metadata_changes: Mapping[str, object]) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(task_id, status="completed", finished_at=finished_at, last_error="", **dict(metadata_changes)))

    def fail_runtime_task(self, task_id: str, *, finished_at: str, error: str, metadata_changes: Mapping[str, object]) -> TaskSnapshot:
        return self._snapshot(self._repository().update_task(task_id, status="failed", finished_at=finished_at, last_error=error, **dict(metadata_changes)))

    def get_task_documents(self, task_id: str) -> TaskFinalizationDocuments:
        repository = self._repository()
        repository.get_task(task_id)
        return TaskFinalizationDocuments(
            results=repository.read_results_document(task_id),
            progress=repository.read_progress_document(task_id),
            modifications=tuple(repository.read_modifications(task_id)),
            metadata_changes={},
        )

    def finalize_task_documents(self, task_id: str, documents: TaskFinalizationDocuments) -> TaskSnapshot:
        task = self._repository().write_task_documents(
            task_id, results=documents.results, progress=documents.progress,
            modifications=[dict(item) for item in documents.modifications],
            metadata_changes=dict(documents.metadata_changes),
        )
        return self._snapshot(task)

    def get_tasks(self) -> TaskReadResult:
        items: list[dict[str, object]] = []
        repository = self._repository()
        for task in repository.list_tasks():
            task_id = str(task.get("id") or "")
            progress = self._task_progress(task_id, int(task.get("valid_count") or 0))
            task_type = str(task.get("task_type") or "scrape")
            item: dict[str, object] = {
                "id": task_id,
                "name": str(task.get("name") or "未命名任务"),
                "task_type": task_type
                if task_type in {"manual", "email_recheck"}
                else "scrape",
                "target_platform": str(task.get("target_platform") or "全部"),
                "platforms": repository.normalize_platforms(
                    task.get("platforms"),
                    task.get("platform") or task.get("target_platform"),
                ),
                "status": str(task.get("status") or "created"),
                "heartbeat_time": str(task.get("heartbeat_time") or ""),
                "heartbeat_interval": int(
                    task.get("heartbeat_interval") or self._heartbeat_interval
                ),
                "last_progress_time": str(task.get("last_progress_time") or ""),
                "current_item": str(task.get("current_item") or ""),
                "last_successful_index": int(task.get("last_successful_index") or 0),
                "browser_status": str(task.get("browser_status") or "closed"),
                "worker_status": str(task.get("worker_status") or "idle"),
                "interrupted_time": str(task.get("interrupted_time") or ""),
                "interrupted_reason": str(task.get("interrupted_reason") or ""),
                "instagram_error_count": int(task.get("instagram_error_count") or 0),
                "instagram_status": str(task.get("instagram_status") or ""),
                "instagram_message": str(task.get("instagram_message") or ""),
                "retry_round": int(task.get("retry_round") or 0),
                "retry_history": task.get("retry_history")
                if isinstance(task.get("retry_history"), list)
                else [],
                "created_at": str(task.get("created_at") or ""),
                "platform_summary": task.get("platform_summary")
                if isinstance(task.get("platform_summary"), dict)
                else {},
                "filtered_count": int(task.get("filtered_count") or 0),
                **progress,
            }
            if task_type == "email_recheck":
                item.update(self._email_recheck_summary(task_id))
            items.append(item)
        return TaskReadResult({"tasks": items})

    def get_task_details(self, task_id: str) -> TaskReadResult:
        repository = self._repository()
        task = repository.get_task(task_id)
        links = repository.read_links(task_id)
        progress_by_url = self._completed_progress(repository, task_id)
        current_item = str(task.get("current_item") or "")
        records: list[dict[str, object]] = []
        for index, link in enumerate(links, start=1):
            progress = progress_by_url.get(link)
            if progress:
                status = "已完成"
            elif link == current_item and str(task.get("status") or "") in {
                "running",
                "stopping",
            }:
                status = "处理中"
            else:
                status = "等待"
            platform = str(
                scraper_module.normalize_link_record(link).get("platform") or ""
            )
            records.append(
                {"index": index, "url": link, "platform": platform, "status": status}
            )
        progress = self._task_progress(task_id, len(links))
        return TaskReadResult(
            {"task": {**task, **progress, "total_links": len(links)}, "links": records}
        )

    def get_task_results(self, task_id: str) -> TaskReadResult:
        repository = self._repository()
        task = repository.get_task(task_id)
        if not repository.results_exist(task_id):
            return TaskReadResult(
                {
                    "task_id": task_id,
                    "platforms": task.get("platforms", []),
                    "platform_results": {},
                    "creator_analysis_available": bool(
                        task.get("creator_analysis_id")
                    ),
                    "records": [],
                }
            )
        rows = repository.read_results(task_id)
        review_rows = repository.read_review_state(task_id).get("rows", {})
        records = [self._review_record(row, review_rows) for row in rows]
        platform_results = {platform: 0 for platform in _PLATFORMS}
        for record in records:
            platform = str(record.get(scraper_module.FIELD_PLATFORM) or "").strip()
            if platform in platform_results:
                platform_results[platform] += 1
        return TaskReadResult(
            {
                "task_id": task_id,
                "platforms": repository.normalize_platforms(
                    task.get("platforms"),
                    task.get("platform") or task.get("target_platform"),
                ),
                "platform_results": platform_results,
                "creator_analysis_available": bool(task.get("creator_analysis_id")),
                "records": records,
                "review_total": sum(record["review_eligible"] for record in records),
                "reviewed_count": sum(
                    record["review_eligible"]
                    and record["review_state"] in {"approved", "rejected"}
                    for record in records
                ),
                "pending_count": sum(
                    record["review_eligible"] and record["review_state"] == "pending"
                    for record in records
                ),
            }
        )

    def get_scrape_status(self) -> TaskReadResult:
        response = self._scrape_status_provider() if self._scrape_status_provider else {}
        return TaskReadResult(response)

    def resume_task(self, task_id: str) -> TaskSnapshot:
        return self._snapshot(self._repository().get_task(task_id))

    def stop_task(self, task_id: str) -> TaskSnapshot:
        task = self._repository().update_task(
            task_id,
            status="stopped",
            pause_requested=False,
            stop_requested=False,
            browser_status="closed",
            worker_status="stopped",
            current_item="",
            finished_at=self._utc_now(),
        )
        return self._snapshot(task)

    def rename_task(self, task_id: str, name: str) -> TaskSnapshot:
        task = self._repository().update_task(task_id, name=name)
        return self._snapshot(task)

    def update_task_links(
        self, task_id: str, command: TaskLinksUpdateCommand
    ) -> TaskReadResult:
        repository = self._repository()
        task = repository.get_task(task_id)
        links = repository.read_links(task_id)
        done_urls = set(self._completed_progress(repository, task_id))
        normalized_url = ""
        if command.action in {"add", "update"}:
            record = scraper_module.normalize_link_record(command.url)
            if not record.get("valid"):
                raise ValueError(str(record.get("reason") or "链接无效。"))
            normalized_url = str(record.get("normalized_url") or "")
            if not normalized_url:
                raise ValueError("链接无效。")

        if command.action == "add":
            if normalized_url in links:
                raise ValueError("该链接已在任务中。")
            links.append(normalized_url)
        else:
            try:
                position = int(command.index) - 1
            except (TypeError, ValueError) as exc:
                raise ValueError("链接编号无效。") from exc
            if position < 0 or position >= len(links):
                raise ValueError("链接编号不存在。")
            old_url = links[position]
            if old_url in done_urls:
                raise RuntimeError("已完成的链接不能修改或删除。")
            if command.action == "delete":
                links.pop(position)
            elif command.action == "update":
                if normalized_url != old_url and normalized_url in links:
                    raise ValueError("该链接已在任务中。")
                links[position] = normalized_url
            else:
                raise ValueError("不支持的链接操作。")

        repository.write_links(task_id, links)
        repository.update_task(
            task_id,
            valid_count=len(links),
            input_count=max(int(task.get("input_count") or 0), len(links)),
            platform_summary=self._platform_summary_from_links(links),
            current_item=self._next_pending_item(repository, task_id, links),
        )
        return self.get_task_details(task_id)

    def retry_failed_results(
        self, task_id: str, command: RetryFailedResultsCommand
    ) -> TaskReadResult:
        repository = self._repository()
        task = repository.get_task(task_id)
        rows = repository.read_results(task_id)
        requested = set(command.account_uids)
        retry_rows: list[dict[str, str]] = []
        for row in rows:
            result = scraper_module.row_to_result(row)
            scrape_status = str(
                result.get("scrape_status") or "success"
            ).strip()
            if scrape_status not in _RETRYABLE_SCRAPE_STATUSES:
                continue
            account_uid = scraper_module.build_creator_uid(result)
            if requested and account_uid not in requested:
                continue
            retry_rows.append(row)

        if not retry_rows:
            raise ValueError("没有可重新抓取的失败记录。")

        links = [
            str(row.get(scraper_module.FIELD_URL) or "").strip()
            for row in retry_rows
        ]
        links = list(dict.fromkeys(link for link in links if link))
        if not links:
            raise ValueError("失败记录缺少有效主页链接。")

        next_retry_round = max(0, int(task.get("retry_round") or 0)) + 1
        retry_task = repository.update_task(
            task_id,
            status="created",
            retry_round=next_retry_round,
            retry_requested_urls=links,
            retry_requested_at=self._utc_now(),
            retry_reason="抓取状态异常",
            last_error="",
        )
        return TaskReadResult(
            {
                "task": retry_task,
                "retried_count": len(links),
                "retry_round": next_retry_round,
            }
        )

    def attach_creator_import(
        self, task_id: str, linkage: CreatorImportLinkage
    ) -> TaskSnapshot:
        task = self._repository().update_task(
            task_id,
            creator_analysis_id=linkage.creator_id,
            creator_snapshot_id=linkage.snapshot_id,
            creator_analysis_imported_at=linkage.imported_at,
            extension_crm={
                "country": linkage.country,
                "language": linkage.language,
                "content_category": linkage.content_category,
            },
        )
        return self._snapshot(task)

    def attach_task_result_import(
        self, task_id: str, linkage: TaskResultImportLinkage
    ) -> TaskSnapshot:
        task = self._repository().update_task(
            task_id,
            creator_library_imported_at=linkage.imported_at,
            creator_library_creator_ids=list(linkage.creator_ids),
            creator_library_account_ids=list(linkage.account_ids),
            creator_library_import_summary=dict(linkage.summary),
            creator_library_import_error="",
        )
        return self._snapshot(task)

    def update_sync_status(
        self, task_id: str, update: TaskSyncStatusUpdate
    ) -> TaskSnapshot:
        changes: dict[str, object] = {
            "sync_status": update.status,
            "sync_time": update.synced_at,
            "sync_summary": dict(update.summary),
            "sync_errors": list(update.errors),
            "sync_warnings": list(update.warnings),
            "sync_skipped": list(update.skipped),
        }
        if update.data_source:
            changes["last_sync_source"] = update.data_source
        if update.sync_log is not None:
            changes["sync_log"] = [dict(item) for item in update.sync_log]
        task = self._repository().update_task(task_id, **changes)
        return self._snapshot(task)

    def delete_task(self, task_id: str) -> None:
        self._repository().delete_task(task_id)

    def _task_progress(self, task_id: str, fallback_total: int = 0) -> dict[str, object]:
        repository = self._repository()
        try:
            repository.get_task(task_id)
        except ValueError:
            return {
                "total_links": fallback_total,
                "completed_links": 0,
                "failed_links": 0,
                "pending_links": fallback_total,
                "progress": 0,
            }
        try:
            links = repository.read_links(task_id)
        except (OSError, ValueError):
            links = []
        total_links = len(links) or fallback_total
        task_urls = set(links)
        latest_status_by_url: dict[str, str] = {}
        try:
            for row in repository.read_progress(task_id):
                url = str(row.get(scraper_module.FIELD_URL) or "").strip()
                if url and (not task_urls or url in task_urls):
                    latest_status_by_url[url] = str(
                        row.get(scraper_module.FIELD_STATUS) or ""
                    ).strip()
        except OSError:
            pass
        completed = sum(
            1 for status in latest_status_by_url.values() if status == "完成"
        )
        failed = sum(
            1 for status in latest_status_by_url.values() if status == "失败"
        )
        completed = min(completed, total_links)
        failed = min(failed, max(0, total_links - completed))
        pending = max(0, total_links - completed - failed)
        progress = (
            round(((completed + failed) / total_links) * 100, 1)
            if total_links
            else 0
        )
        return {
            "total_links": total_links,
            "completed_links": completed,
            "failed_links": failed,
            "pending_links": pending,
            "progress": progress,
        }

    def _email_recheck_summary(self, task_id: str) -> dict[str, int]:
        repository = self._repository()
        try:
            repository.get_task(task_id)
            if not repository.results_exist(task_id):
                return {"email_found_count": 0, "email_failed_count": 0}
            rows = repository.read_results(task_id)
        except (OSError, ValueError):
            return {"email_found_count": 0, "email_failed_count": 0}
        found = sum(
            1
            for row in rows
            if str(row.get(scraper_module.FIELD_EMAIL) or "").strip()
            not in {"", scraper_module.NO_EMAIL}
        )
        return {
            "email_found_count": found,
            "email_failed_count": max(0, len(rows) - found),
        }

    @staticmethod
    def _platform_summary_from_links(links: list[str]) -> dict[str, int]:
        summary = {"TikTok": 0, "Instagram": 0, "YouTube": 0}
        for link in links:
            platform = str(
                scraper_module.normalize_link_record(link).get("platform") or ""
            )
            if platform in summary:
                summary[platform] += 1
        return summary

    @classmethod
    def _next_pending_item(
        cls, repository: TaskRepository, task_id: str, links: list[str]
    ) -> str:
        completed = set(cls._completed_progress(repository, task_id))
        return next((url for url in links if url not in completed), "")

    @staticmethod
    def _completed_progress(
        repository: TaskRepository, task_id: str
    ) -> dict[str, dict]:
        done: dict[str, dict] = {}
        for row in repository.read_progress(task_id):
            if row.get(scraper_module.FIELD_STATUS) != "完成":
                continue
            result = scraper_module.row_to_result(row)
            if result["url"]:
                done[result["url"]] = result
        return done

    @staticmethod
    def _utc_now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    def _repository(self) -> TaskRepository:
        return TaskRepository(self._tasks_directory_provider())

    @staticmethod
    def _review_value(row: Mapping[str, object], field: str) -> str:
        if field == _REVIEW_FIELD_DATA_STATUS:
            return str(row.get(field) or "待检查")
        return str(row.get(field) or "")

    @classmethod
    def _review_record(cls, row: Mapping[str, object], review_rows: Mapping[str, object] | None = None) -> dict[str, object]:
        result = scraper_module.row_to_result(dict(row))
        account_uid = scraper_module.build_creator_uid(result)
        stored = (review_rows or {}).get(account_uid)
        stored = stored if isinstance(stored, Mapping) else {}
        state = str(stored.get("review_state") or "pending")
        if state not in {"pending", "approved", "rejected"}:
            state = "pending"
        scrape_status = str(result.get("scrape_status") or "success")
        # The read-model status is reclassified for data usability. Review
        # eligibility must retain the CSV's original access outcome instead.
        source_scrape_status = str(
            row.get(scraper_module.FIELD_SCRAPE_STATUS) or "success"
        ).strip()
        return {
            "account_uid": account_uid,
            scraper_module.FIELD_NAME: str(row.get(scraper_module.FIELD_NAME) or ""),
            scraper_module.FIELD_PLATFORM: str(
                row.get(scraper_module.FIELD_PLATFORM) or ""
            ),
            scraper_module.FIELD_URL: str(row.get(scraper_module.FIELD_URL) or ""),
            scraper_module.FIELD_EMAIL: str(row.get(scraper_module.FIELD_EMAIL) or ""),
            scraper_module.FIELD_EMAIL_SOURCE: str(
                row.get(scraper_module.FIELD_EMAIL_SOURCE) or ""
            ),
            scraper_module.FIELD_EXTERNAL_LINK: str(
                row.get(scraper_module.FIELD_EXTERNAL_LINK) or ""
            ),
            scraper_module.FIELD_EXTERNAL_SOURCE: str(
                row.get(scraper_module.FIELD_EXTERNAL_SOURCE) or ""
            ),
            scraper_module.FIELD_LATEST_DATE: str(
                row.get(scraper_module.FIELD_LATEST_DATE) or ""
            ),
            scraper_module.FIELD_FOLLOWER_COUNT: str(
                row.get(scraper_module.FIELD_FOLLOWER_COUNT) or ""
            ),
            scraper_module.FIELD_STATUS: str(row.get(scraper_module.FIELD_STATUS) or ""),
            scraper_module.FIELD_SCRAPE_STATUS: scrape_status,
            "review_state": state,
            "reviewed_at": str(stored.get("reviewed_at") or ""),
            "rejection_reason": str(stored.get("rejection_reason") or ""),
            "review_eligible": source_scrape_status not in _RETRYABLE_SCRAPE_STATUSES,
            scraper_module.FIELD_STATUS_REASON: str(result.get("status_reason") or ""),
            scraper_module.FIELD_LAST_SCRAPE_TIME: str(
                row.get(scraper_module.FIELD_LAST_SCRAPE_TIME) or ""
            ),
            scraper_module.FIELD_RETRY_COUNT: str(
                row.get(scraper_module.FIELD_RETRY_COUNT) or "0"
            ),
            _REVIEW_FIELD_WHATSAPP: cls._review_value(row, _REVIEW_FIELD_WHATSAPP),
            _REVIEW_FIELD_NOTE: cls._review_value(row, _REVIEW_FIELD_NOTE),
            _REVIEW_FIELD_DATA_STATUS: cls._review_value(
                row, _REVIEW_FIELD_DATA_STATUS
            ),
            _REVIEW_FIELD_MODIFIED_AT: cls._review_value(
                row, _REVIEW_FIELD_MODIFIED_AT
            ),
        }

    @staticmethod
    def _snapshot(task: Mapping[str, object]) -> TaskSnapshot:
        extension_crm = task.get("extension_crm")
        crm = extension_crm if isinstance(extension_crm, dict) else {}
        platforms = task.get("platforms")
        return TaskSnapshot(
            task_id=str(task.get("id") or ""),
            name=str(task.get("name") or ""),
            task_type=str(task.get("task_type") or "scrape"),
            status=str(task.get("status") or ""),
            created_at=str(task.get("created_at") or ""),
            started_at=str(task.get("started_at") or ""),
            finished_at=str(task.get("finished_at") or ""),
            input_count=int(task.get("input_count") or 0),
            valid_count=int(task.get("valid_count") or 0),
            invalid_count=int(task.get("invalid_count") or 0),
            target_platform=str(task.get("target_platform") or "全部"),
            platforms=tuple(str(value) for value in platforms)
            if isinstance(platforms, list)
            else (),
            creator_analysis_id=str(task.get("creator_analysis_id") or ""),
            creator_snapshot_id=str(task.get("creator_snapshot_id") or ""),
            creator_analysis_imported_at=str(
                task.get("creator_analysis_imported_at") or ""
            ),
            extension_country=str(crm.get("country") or ""),
            extension_language=str(crm.get("language") or ""),
            extension_content_category=str(crm.get("content_category") or ""),
            profile=str(task.get("profile") or ""),
            _response=deepcopy(dict(task)),
        )

    @staticmethod
    def _runtime_snapshot(task: Mapping[str, object]) -> TaskRuntimeSnapshot:
        retry_urls = task.get("retry_requested_urls")
        return TaskRuntimeSnapshot(
            task_id=str(task.get("id") or ""), status=str(task.get("status") or ""),
            task_type=str(task.get("task_type") or "scrape"), profile=str(task.get("profile") or ""),
            started_at=str(task.get("started_at") or ""), finished_at=str(task.get("finished_at") or ""),
            heartbeat_time=str(task.get("heartbeat_time") or ""),
            stop_requested=bool(task.get("stop_requested")), pause_requested=bool(task.get("pause_requested")),
            retry_round=int(task.get("retry_round") or 0),
            retry_requested_urls=tuple(str(value) for value in retry_urls) if isinstance(retry_urls, list) else (),
        )
