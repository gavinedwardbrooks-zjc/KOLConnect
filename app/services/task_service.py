from __future__ import annotations

"""Dependency boundary for future Task workflow extraction."""

from typing import Callable

from ports.creator_port import CreatorPort
from ports.task_port import TaskPort


TaskPortProvider = Callable[[], TaskPort]
CreatorPortProvider = Callable[[], CreatorPort]
TaskRepositoryProvider = Callable[[], object]


class TaskService:
    """Declare future Task dependencies without executing Task workflows."""

    def __init__(
        self,
        get_task_port: TaskPortProvider,
        get_creator_port: CreatorPortProvider,
        get_task_repository: TaskRepositoryProvider,
    ) -> None:
        self._get_task_port = get_task_port
        self._get_creator_port = get_creator_port
        self._get_task_repository = get_task_repository
