from __future__ import annotations

"""Task workflow facade over narrow task and creator ports."""

from dataclasses import dataclass, field
from typing import Callable

from ports.creator_port import CreatorPort
from ports.task_port import RetryFailedResultsCommand, TaskLinksUpdateCommand, TaskPort


TaskPortProvider = Callable[[], TaskPort]
CreatorPortProvider = Callable[[], CreatorPort]
TaskRepositoryProvider = Callable[[], object]


@dataclass(frozen=True)
class TaskLifecyclePlan:
    runtime_action: str = ""
    profile: str = ""
    response: dict[str, object] = field(default_factory=dict)


class TaskService:
    """Resolve operation-scoped dependencies for Task domain workflows."""

    def __init__(
        self,
        get_task_port: TaskPortProvider,
        get_creator_port: CreatorPortProvider,
        get_task_repository: TaskRepositoryProvider,
    ) -> None:
        self._get_task_port = get_task_port
        self._get_creator_port = get_creator_port
        self._get_task_repository = get_task_repository

    def get_tasks(self) -> dict[str, object]:
        return self._get_task_port().get_tasks().to_response()

    def get_task_details(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().get_task_details(task_id).to_response()

    def get_task_results(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().get_task_results(task_id).to_response()

    def get_task_creator_analysis(self, task_id: str) -> dict[str, object]:
        task = self._get_task_port().get_task(task_id)
        if not task.creator_analysis_id:
            return {"available": False}
        analysis = self._get_creator_port().get_creator_analysis(
            task.creator_analysis_id
        )
        return {
            "available": True,
            "analysis": dict(analysis.analysis),
            "recovered_from_backup": False,
        }

    def get_scrape_status(self) -> dict[str, object]:
        return self._get_task_port().get_scrape_status().to_response()

    def delete_task(self, task_id: str) -> dict[str, object]:
        if self._task_is_running(task_id):
            raise RuntimeError("任务正在运行，不能删除。")
        self._get_task_port().delete_task(task_id)
        return {"task_id": task_id, "deleted": True}

    def rename_task(self, task_id: str, name: object) -> dict[str, object]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("任务名称不能为空。")
        if len(normalized_name) > 100:
            raise ValueError("任务名称不能超过100个字符。")
        return self._get_task_port().rename_task(
            task_id, normalized_name
        ).to_response()

    def update_task_links(
        self,
        task_id: str,
        action: object,
        index: object = None,
        url: object = None,
    ) -> dict[str, object]:
        if self._task_is_running(task_id):
            raise RuntimeError("任务正在运行，不能修改链接。")
        command = TaskLinksUpdateCommand(
            action=str(action or "").strip(),
            index=index,
            url=str(url or "").strip(),
        )
        return self._get_task_port().update_task_links(
            task_id, command
        ).to_response()

    def retry_failed_results(
        self, task_id: str, account_uids: list[object] | None = None
    ) -> dict[str, object]:
        requested = tuple(
            str(value or "").strip()
            for value in (account_uids or [])
            if str(value or "").strip()
        )
        command = RetryFailedResultsCommand(account_uids=requested)
        return self._get_task_port().retry_failed_results(
            task_id, command
        ).to_response()

    def resume_task(
        self,
        task_id: str,
        *,
        runtime_running: bool,
        runtime_task_id: str,
    ) -> TaskLifecyclePlan:
        task = self._get_task_port().resume_task(task_id)
        if runtime_running:
            if runtime_task_id != task_id:
                raise RuntimeError("已有任务正在运行。")
            return TaskLifecyclePlan(runtime_action="resume")
        if task.status not in {
            "paused",
            "interrupted",
            "stopped",
            "created",
            "failed",
        }:
            raise RuntimeError("当前任务不需要恢复。")
        return TaskLifecyclePlan(profile=task.profile)

    def stop_task(
        self, task_id: str, *, runtime_active: bool
    ) -> TaskLifecyclePlan:
        task = self._get_task_port().get_task(task_id)
        if task.status == "finalizing":
            raise RuntimeError("任务已经完成抓取，正在处理中。")
        if runtime_active:
            return TaskLifecyclePlan(runtime_action="stop")
        if task.status not in {"paused", "interrupted", "running", "stopping"}:
            raise RuntimeError("当前任务无需停止。")
        self._get_task_port().stop_task(task_id)
        return TaskLifecyclePlan(
            response={"task_id": task_id, "status": "stopped"}
        )

    def _task_is_running(self, task_id: str) -> bool:
        status = self._get_task_port().get_scrape_status().to_response()
        return bool(status.get("running")) and status.get("task_id") == task_id
