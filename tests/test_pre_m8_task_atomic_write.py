from __future__ import annotations

import os
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import runtime_paths  # noqa: E402
from repositories.task_repository import TaskRepository  # noqa: E402


def windows_permission_error(winerror: int) -> PermissionError:
    error = PermissionError(f"synthetic WinError {winerror}")
    error.winerror = winerror
    return error


class TaskAtomicWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory(prefix="pre_m8_task_atomic_")
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_first_overwrite_binary_empty_and_restart_read(self) -> None:
        path = self.root / "nested runtime" / "task.bin"
        for payload in (b"first", bytes(range(256)), b""):
            TaskRepository._atomic_write_bytes(path, payload)
            self.assertEqual(payload, Path(str(path)).read_bytes())
        self.assertEqual([], list(path.parent.glob(f"{path.name}.*.tmp")))

    def test_unique_sibling_temps_rapid_writes_unicode_and_spaces(self) -> None:
        path = self.root / "space dir" / "\u4efb\u52a1 data.bin"
        observed: list[Path] = []
        real_open = runtime_paths._open_sibling_temp

        def capture(target: Path):
            fd, temp_path = real_open(target)
            observed.append(temp_path)
            return fd, temp_path

        with mock.patch.object(runtime_paths, "_open_sibling_temp", side_effect=capture):
            for index in range(100):
                TaskRepository._atomic_write_bytes(path, f"payload-{index}".encode())

        self.assertEqual(b"payload-99", path.read_bytes())
        self.assertEqual(100, len(observed))
        self.assertEqual(100, len(set(observed)))
        self.assertTrue(all(item.parent == path.parent for item in observed))
        self.assertTrue(all(not item.exists() for item in observed))

    def test_transient_windows_replace_errors_retry_then_succeed(self) -> None:
        for winerror in (5, 32, 33):
            with self.subTest(winerror=winerror):
                path = self.root / f"retry-{winerror}.bin"
                real_replace = runtime_paths.os.replace
                calls = 0

                def replace_once(source, destination):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        raise windows_permission_error(winerror)
                    return real_replace(source, destination)

                with mock.patch.object(runtime_paths, "_is_windows_transient_replace_error", return_value=True), mock.patch.object(
                    runtime_paths.os, "replace", side_effect=replace_once
                ), mock.patch.object(runtime_paths.time, "sleep") as sleep:
                    TaskRepository._atomic_write_bytes(path, b"new")

                self.assertEqual(b"new", path.read_bytes())
                self.assertEqual(2, calls)
                sleep.assert_called_once_with(0.05)

    def test_non_retryable_failure_is_immediate_and_preserves_original(self) -> None:
        path = self.root / "task.bin"
        path.write_bytes(b"OLD_BYTES")
        error = PermissionError("not transient")
        error.winerror = 13
        with mock.patch.object(runtime_paths.os, "replace", side_effect=error), mock.patch.object(
            runtime_paths, "_is_windows_transient_replace_error", return_value=False
        ), mock.patch.object(runtime_paths.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                TaskRepository._atomic_write_bytes(path, b"NEW_BYTES")
        self.assertEqual(b"OLD_BYTES", path.read_bytes())
        sleep.assert_not_called()
        self.assertEqual([], list(self.root.glob("task.bin.*.tmp")))

    def test_transient_retries_exhausted_preserve_original_and_cleanup(self) -> None:
        path = self.root / "task.bin"
        path.write_bytes(b"OLD_BYTES")
        error = windows_permission_error(32)
        with mock.patch.object(runtime_paths.os, "replace", side_effect=error) as replace, mock.patch.object(
            runtime_paths, "_is_windows_transient_replace_error", return_value=True
        ), mock.patch.object(runtime_paths.time, "sleep") as sleep:
            with self.assertRaises(PermissionError):
                TaskRepository._atomic_write_bytes(path, b"NEW_BYTES")
        self.assertEqual(runtime_paths.WINDOWS_REPLACE_MAX_RETRIES + 1, replace.call_count)
        self.assertEqual(list(runtime_paths.WINDOWS_REPLACE_RETRY_DELAYS), [call.args[0] for call in sleep.call_args_list])
        self.assertEqual(b"OLD_BYTES", path.read_bytes())
        self.assertEqual([], list(self.root.glob("task.bin.*.tmp")))

    def test_concurrent_writers_never_publish_partial_bytes(self) -> None:
        path = self.root / "concurrent" / "task.bin"
        payloads = [bytes([index]) * 32_768 for index in range(16)]
        started = threading.Barrier(len(payloads))

        def write(payload: bytes) -> None:
            started.wait()
            TaskRepository._atomic_write_bytes(path, payload)

        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            list(pool.map(write, payloads))

        self.assertIn(path.read_bytes(), payloads)
        self.assertEqual([], list(path.parent.glob(f"{path.name}.*.tmp")))

    def test_type_contract_is_deterministic(self) -> None:
        with self.assertRaisesRegex(TypeError, "data must be bytes"):
            runtime_paths.atomic_write_bytes(self.root / "bad.bin", bytearray(b"bad"))

    def test_windows_error_classifier_remains_platform_and_code_specific(self) -> None:
        with mock.patch.object(runtime_paths.os, "name", "nt"):
            for winerror in (5, 32, 33):
                self.assertTrue(runtime_paths._is_windows_transient_replace_error(windows_permission_error(winerror)))
            self.assertFalse(runtime_paths._is_windows_transient_replace_error(windows_permission_error(13)))
        with mock.patch.object(runtime_paths.os, "name", "posix"):
            self.assertFalse(runtime_paths._is_windows_transient_replace_error(windows_permission_error(5)))


if __name__ == "__main__":
    unittest.main()
