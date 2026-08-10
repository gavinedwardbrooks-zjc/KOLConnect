from __future__ import annotations

"""TaskPort adapter over the existing task_manager module."""

from copy import deepcopy
from pathlib import Path
from typing import Callable, Mapping

import task_manager
from ports.task_port import (
    CreatedTask,
    CreatorImportLinkage,
    ManualReviewTaskCommand,
    TaskSnapshot,
)


TasksDirectoryProvider = Callable[[], Path]


class TaskManagerAdapter:
    """Translate neutral task DTOs without exposing task files or manager state."""

    def __init__(self, tasks_directory_provider: TasksDirectoryProvider) -> None:
        self._tasks_directory_provider = tasks_directory_provider

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
            _response=deepcopy(dict(task)),
        )
