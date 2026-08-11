from __future__ import annotations

"""TaskPort adapter over the existing task_manager module."""

import csv
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

import scraper as scraper_module
import task_manager
from ports.task_port import (
    CreatedTask,
    CreatorImportLinkage,
    ManualReviewTaskCommand,
    RetryFailedResultsCommand,
    TaskLinksUpdateCommand,
    TaskReadResult,
    TaskSnapshot,
)


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
        task = task_manager.create_task(
            self._tasks_directory_provider(),
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

    def get_task(self, task_id: str) -> TaskSnapshot:
        task, _paths = task_manager.load_task(self._tasks_directory_provider(), task_id)
        return self._snapshot(task)

    def get_tasks(self) -> TaskReadResult:
        items: list[dict[str, object]] = []
        for task in task_manager.list_tasks(self._tasks_directory_provider()):
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
                "platforms": task_manager.normalize_platforms(
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
        task, paths = task_manager.load_task(self._tasks_directory_provider(), task_id)
        links = self._read_links(paths["links"])
        progress_by_url = scraper_module.load_progress(str(paths["progress"]))
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
        task, paths = task_manager.load_task(self._tasks_directory_provider(), task_id)
        if not paths["results"].exists():
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
        rows = self._read_csv(paths["results"])
        records = [self._review_record(row) for row in rows]
        platform_results = {platform: 0 for platform in _PLATFORMS}
        for record in records:
            platform = str(record.get(scraper_module.FIELD_PLATFORM) or "").strip()
            if platform in platform_results:
                platform_results[platform] += 1
        return TaskReadResult(
            {
                "task_id": task_id,
                "platforms": task_manager.normalize_platforms(
                    task.get("platforms"),
                    task.get("platform") or task.get("target_platform"),
                ),
                "platform_results": platform_results,
                "creator_analysis_available": bool(task.get("creator_analysis_id")),
                "records": records,
            }
        )

    def get_scrape_status(self) -> TaskReadResult:
        response = self._scrape_status_provider() if self._scrape_status_provider else {}
        return TaskReadResult(response)

    def resume_task(self, task_id: str) -> TaskSnapshot:
        task, _paths = task_manager.load_task(
            self._tasks_directory_provider(), task_id
        )
        return self._snapshot(task)

    def stop_task(self, task_id: str) -> TaskSnapshot:
        task = task_manager.update_task(
            self._tasks_directory_provider(),
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
        task = task_manager.update_task(
            self._tasks_directory_provider(), task_id, name=name
        )
        return self._snapshot(task)

    def update_task_links(
        self, task_id: str, command: TaskLinksUpdateCommand
    ) -> TaskReadResult:
        task, paths = task_manager.load_task(
            self._tasks_directory_provider(), task_id
        )
        links = self._read_links(paths["links"])
        done_urls = set(scraper_module.load_progress(str(paths["progress"])))
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

        self._write_links(paths["links"], links)
        task_manager.update_task(
            self._tasks_directory_provider(),
            task_id,
            valid_count=len(links),
            input_count=max(int(task.get("input_count") or 0), len(links)),
            platform_summary=self._platform_summary_from_links(links),
            current_item=self._next_pending_item(paths),
        )
        return self.get_task_details(task_id)

    def retry_failed_results(
        self, task_id: str, command: RetryFailedResultsCommand
    ) -> TaskReadResult:
        task, paths = task_manager.load_task(
            self._tasks_directory_provider(), task_id
        )
        rows = self._read_csv(paths["results"])
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
        retry_task = task_manager.update_task(
            self._tasks_directory_provider(),
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
        task = task_manager.update_task(
            self._tasks_directory_provider(),
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

    def delete_task(self, task_id: str) -> None:
        task_manager.delete_task(self._tasks_directory_provider(), task_id)

    def _task_progress(self, task_id: str, fallback_total: int = 0) -> dict[str, object]:
        try:
            _task, paths = task_manager.load_task(
                self._tasks_directory_provider(), task_id
            )
        except ValueError:
            return {
                "total_links": fallback_total,
                "completed_links": 0,
                "failed_links": 0,
                "pending_links": fallback_total,
                "progress": 0,
            }
        try:
            links = self._read_links(paths["links"])
        except (OSError, ValueError):
            links = []
        total_links = len(links) or fallback_total
        task_urls = set(links)
        latest_status_by_url: dict[str, str] = {}
        if paths["progress"].exists():
            try:
                with paths["progress"].open(
                    encoding="utf-8-sig", newline="", errors="ignore"
                ) as handle:
                    for row in csv.DictReader(handle):
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
        try:
            _task, paths = task_manager.load_task(
                self._tasks_directory_provider(), task_id
            )
            if not paths["results"].exists():
                return {"email_found_count": 0, "email_failed_count": 0}
            rows = self._read_csv(paths["results"])
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
    def _read_links(path: Path) -> list[str]:
        if not path.exists():
            raise ValueError("未找到任务链接文件。")
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @staticmethod
    def _write_links(path: Path, links: list[str]) -> None:
        temp_path = path.with_suffix(f"{path.suffix}.tmp")
        try:
            temp_path.write_text(
                "\n".join(links) + ("\n" if links else ""), encoding="utf-8"
            )
            temp_path.replace(path)
        finally:
            temp_path.unlink(missing_ok=True)

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
    def _next_pending_item(cls, paths: Mapping[str, Path]) -> str:
        try:
            links = cls._read_links(paths["links"])
        except (OSError, ValueError):
            return ""
        completed = set(scraper_module.load_progress(str(paths["progress"])))
        return next((url for url in links if url not in completed), "")

    @staticmethod
    def _utc_now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _read_csv(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            raise ValueError(f"未找到任务文件：{path.name}")
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValueError(f"任务文件格式无效：{path.name}")
            return [dict(row) for row in reader]

    @staticmethod
    def _review_value(row: Mapping[str, object], field: str) -> str:
        if field == _REVIEW_FIELD_DATA_STATUS:
            return str(row.get(field) or "待检查")
        return str(row.get(field) or "")

    @classmethod
    def _review_record(cls, row: Mapping[str, object]) -> dict[str, str]:
        result = scraper_module.row_to_result(dict(row))
        return {
            "account_uid": scraper_module.build_creator_uid(result),
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
            scraper_module.FIELD_SCRAPE_STATUS: str(
                result.get("scrape_status") or "success"
            ),
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
