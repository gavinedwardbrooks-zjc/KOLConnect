from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

from adapters import task_manager_adapter  # noqa: E402
from adapters.task_manager_adapter import TaskManagerAdapter  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


class _TaskRepositoryStub:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.requested_task_id = ""

    def _paths(self, task_id: str) -> dict[str, Path]:
        self.requested_task_id = task_id
        return {"root": self.root, "results": self.root / "results.csv"}

    def get_task(self, task_id: str) -> dict:
        self.requested_task_id = task_id
        return {"id": task_id}


class M485ResultFolderTests(unittest.TestCase):
    def _adapter_with_repository(self, repository: _TaskRepositoryStub) -> TaskManagerAdapter:
        adapter = TaskManagerAdapter(lambda: repository.root.parent)
        adapter._repository = mock.Mock(return_value=repository)
        return adapter

    def test_windows_opens_validated_task_directory_in_explorer(self) -> None:
        root = test_artifact_path("m4_8_5_task_1")
        repository = _TaskRepositoryStub(root)
        adapter = self._adapter_with_repository(repository)
        with mock.patch.object(Path, "is_dir", return_value=True), mock.patch.object(
            task_manager_adapter.os, "name", "nt"
        ), mock.patch.object(task_manager_adapter.subprocess, "Popen") as popen:
            adapter.open_task_result_folder("task_1")
        popen.assert_called_once_with(["explorer.exe", str(root)])
        self.assertEqual("task_1", repository.requested_task_id)

    def test_macos_opens_validated_task_directory_in_finder(self) -> None:
        root = test_artifact_path("m4_8_5_task_2")
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(Path, "is_dir", return_value=True), mock.patch.object(
            task_manager_adapter.os, "name", "posix"
        ), mock.patch.object(task_manager_adapter.sys, "platform", "darwin"), mock.patch.object(
            task_manager_adapter.subprocess, "run"
        ) as run:
            adapter.open_task_result_folder("task_2")
        run.assert_called_once_with(["open", str(root.resolve())], check=True)

    def test_missing_task_directory_fails_without_launching_file_manager(self) -> None:
        root = test_artifact_path("missing_m4_8_5_task")
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(task_manager_adapter.subprocess, "Popen") as popen:
            with self.assertRaisesRegex(ValueError, "结果文件夹不可用"):
                adapter.open_task_result_folder("task_missing")
        popen.assert_not_called()

    def test_missing_result_file_fails_without_opening_the_desktop_shell(self) -> None:
        root = test_artifact_path("missing_m4_8_5_result_file")
        root.mkdir(parents=True)
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(task_manager_adapter.subprocess, "Popen") as popen, mock.patch.object(
            task_manager_adapter.subprocess, "run"
        ) as run:
            with self.assertRaisesRegex(ValueError, "尚未生成结果文件"):
                adapter.open_task_results("task_missing_result")
        popen.assert_not_called()
        run.assert_not_called()

    def test_windows_opens_validated_result_file_in_explorer(self) -> None:
        root = test_artifact_path("m4_8_5_task_file_windows", "结果 file")
        root.mkdir(parents=True)
        result_file = root / "results.csv"
        result_file.write_text("ok", encoding="utf-8")
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(task_manager_adapter.os, "name", "nt"), mock.patch.object(
            task_manager_adapter.subprocess, "Popen"
        ) as popen:
            adapter.open_task_results("task_file_windows")
        popen.assert_called_once_with(["explorer.exe", str(result_file.resolve())])

    def test_macos_opens_validated_result_file_with_argv(self) -> None:
        root = test_artifact_path("m4_8_5_task_file_macos", "结果 文件")
        root.mkdir(parents=True)
        result_file = root / "results.csv"
        result_file.write_text("ok", encoding="utf-8")
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(task_manager_adapter.os, "name", "posix"), mock.patch.object(
            task_manager_adapter.sys, "platform", "darwin"
        ), mock.patch.object(task_manager_adapter.subprocess, "run") as run:
            adapter.open_task_results("task_file_macos")
        run.assert_called_once_with(["open", str(result_file.resolve())], check=True)

    def test_linux_opens_validated_task_directory_with_xdg_open(self) -> None:
        root = test_artifact_path("m4_8_5_task_linux")
        root.mkdir(parents=True)
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(task_manager_adapter.os, "name", "posix"), mock.patch.object(
            task_manager_adapter.sys, "platform", "linux"
        ), mock.patch.object(task_manager_adapter.subprocess, "run") as run:
            adapter.open_task_result_folder("task_linux")
        run.assert_called_once_with(["xdg-open", str(root.resolve())], check=True)

    def test_desktop_open_failure_returns_a_user_safe_error(self) -> None:
        root = test_artifact_path("m4_8_5_task_open_failure")
        root.mkdir(parents=True)
        adapter = self._adapter_with_repository(_TaskRepositoryStub(root))
        with mock.patch.object(task_manager_adapter.os, "name", "posix"), mock.patch.object(
            task_manager_adapter.sys, "platform", "darwin"
        ), mock.patch.object(
            task_manager_adapter.subprocess, "run", side_effect=task_manager_adapter.subprocess.CalledProcessError(1, "open")
        ):
            with self.assertRaisesRegex(ValueError, "无法打开结果文件"):
                adapter.open_task_result_folder("task_open_failure")


if __name__ == "__main__":
    unittest.main()
