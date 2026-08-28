from __future__ import annotations

import ast
import contextlib
import errno
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

import local_storage_lock as storage_lock  # noqa: E402
import launcher  # noqa: E402
import runtime_paths  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402
import services.creator_service as creator_service_module  # noqa: E402
from excel_workbook_store import ExcelWorkbookStore  # noqa: E402
from ports.creator_port import ManualTaskProtectionCommand  # noqa: E402
from repositories.task_repository import TaskRepository  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
import staged_delete_transaction  # noqa: E402


class CrossProcessStorageLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = test_artifact_path("m4_6c_test", uuid.uuid4().hex)
        self.root.mkdir()
        self.appdata = self.root / "appdata"
        self.appdata.mkdir()
        self.environment = mock.patch.dict(
            os.environ,
            {
                "APPDATA": str(self.appdata),
                "HOME": str(self.appdata),
                "XDG_DATA_HOME": str(self.appdata),
            },
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def child_env(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["PYTHONPATH"] = os.pathsep.join(
            [str(APP_DIR), environment.get("PYTHONPATH", "")]
        )
        return environment

    def run_child(self, source: str, *, timeout: float = 10.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-u", "-c", source],
            cwd=ROOT,
            env=self.child_env(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def start_holder(self, seconds: float = 5.0) -> subprocess.Popen[str]:
        source = (
            "import time\n"
            "from local_storage_lock import shared_storage_lock\n"
            f"with shared_storage_lock(timeout=2):\n print('READY', flush=True)\n time.sleep({seconds})\n"
        )
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", source],
            cwd=ROOT,
            env=self.child_env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("READY", process.stdout.readline().strip())
        return process

    def test_module_has_no_unconditional_fcntl_import(self) -> None:
        source = (APP_DIR / "local_storage_lock.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        top_level_imports = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertNotIn("fcntl", top_level_imports)
        self.assertNotIn("fcntl", sys.modules if os.name == "nt" else ())

    def test_stable_path_and_lockable_persistent_carrier(self) -> None:
        if sys.platform == "win32":
            expected_root = self.appdata / "KOLConnect"
        elif sys.platform == "darwin":
            expected_root = Path.home() / "Library" / "Application Support" / "KOLConnect"
        else:
            expected_root = Path(os.environ["XDG_DATA_HOME"]) / "KOLConnect"
        expected = expected_root / "locks" / "shared_storage.lock"
        self.assertEqual(20.0, storage_lock.DEFAULT_SHARED_STORAGE_LOCK_TIMEOUT)
        self.assertEqual(0.05, storage_lock.SHARED_STORAGE_LOCK_POLL_INTERVAL)
        self.assertEqual(expected, storage_lock.get_shared_storage_lock_path())
        with storage_lock.shared_storage_lock(timeout=2):
            self.assertTrue(storage_lock.shared_storage_lock_held())
        self.assertTrue(expected.is_file())
        self.assertGreaterEqual(expected.stat().st_size, 1)
        with storage_lock.shared_storage_lock(timeout=2):
            pass
        self.assertTrue(expected.exists())

    def test_same_process_reentrant_acquire(self) -> None:
        with storage_lock.shared_storage_lock(timeout=2):
            with storage_lock.shared_storage_lock(timeout=2):
                self.assertTrue(storage_lock.shared_storage_lock_held())
            self.assertTrue(storage_lock.shared_storage_lock_held())
        self.assertFalse(storage_lock.shared_storage_lock_held())

    def test_nested_release_does_not_admit_another_thread(self) -> None:
        outer_entered = threading.Event()
        inner_released = threading.Event()
        release_outer = threading.Event()
        contender_entered = threading.Event()

        def owner() -> None:
            with storage_lock.shared_storage_lock(timeout=2):
                with storage_lock.shared_storage_lock(timeout=2):
                    outer_entered.set()
                inner_released.set()
                release_outer.wait(2)

        def contender() -> None:
            outer_entered.wait(2)
            with storage_lock.shared_storage_lock(timeout=2):
                contender_entered.set()

        owner_thread = threading.Thread(target=owner)
        contender_thread = threading.Thread(target=contender)
        owner_thread.start()
        contender_thread.start()
        self.assertTrue(inner_released.wait(2))
        self.assertFalse(contender_entered.wait(0.2))
        release_outer.set()
        self.assertTrue(contender_entered.wait(2))
        owner_thread.join(2)
        contender_thread.join(2)

    def test_two_process_contention_times_out_then_release_allows_acquire(self) -> None:
        holder = self.start_holder(1.5)
        try:
            contender = self.run_child(
                "from local_storage_lock import SharedStorageLockTimeout, shared_storage_lock\n"
                "try:\n with shared_storage_lock(timeout=0.3): pass\n"
                "except SharedStorageLockTimeout: print('TIMEOUT')\n"
                "else: print('ACQUIRED')\n"
            )
            self.assertEqual(0, contender.returncode, contender.stderr)
            self.assertEqual("TIMEOUT", contender.stdout.strip())
            holder_stdout, holder_stderr = holder.communicate(timeout=5)
            self.assertEqual(0, holder.returncode, holder_stdout + holder_stderr)
            released = self.run_child(
                "from local_storage_lock import shared_storage_lock\n"
                "with shared_storage_lock(timeout=1): print('ACQUIRED')\n"
            )
            self.assertEqual("ACQUIRED", released.stdout.strip(), released.stderr)
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait(timeout=5)

    def test_process_crash_releases_os_lock(self) -> None:
        holder = self.start_holder(30)
        holder.kill()
        holder.communicate(timeout=5)
        acquired = self.run_child(
            "from local_storage_lock import shared_storage_lock\n"
            "with shared_storage_lock(timeout=1): print('ACQUIRED')\n"
        )
        self.assertEqual(0, acquired.returncode, acquired.stderr)
        self.assertEqual("ACQUIRED", acquired.stdout.strip())

    def test_subprocesses_resolve_identical_lock_path(self) -> None:
        source = (
            "from local_storage_lock import get_shared_storage_lock_path\n"
            "print(get_shared_storage_lock_path())\n"
        )
        first = self.run_child(source)
        second = self.run_child(source)
        self.assertEqual(0, first.returncode, first.stderr)
        self.assertEqual(first.stdout.strip(), second.stdout.strip())
        self.assertEqual(
            str(storage_lock.get_shared_storage_lock_path()), first.stdout.strip()
        )

    @unittest.skipUnless(os.name == "nt", "Windows lock-region contract")
    def test_windows_lock_region_always_seeks_zero_and_locks_one_byte(self) -> None:
        with mock.patch.object(storage_lock.os, "lseek") as seek:
            with mock.patch("msvcrt.locking") as locking:
                storage_lock._try_lock_windows(17)
                storage_lock._unlock_windows(17)
        self.assertEqual(
            [mock.call(17, 0, os.SEEK_SET), mock.call(17, 0, os.SEEK_SET)],
            seek.call_args_list,
        )
        self.assertEqual(1, locking.call_args_list[0].args[2])
        self.assertEqual(1, locking.call_args_list[1].args[2])

    def test_only_contention_errors_are_retryable(self) -> None:
        contention = OSError(errno.EACCES, "locked")
        unexpected = OSError(errno.EBADF, "bad handle")
        self.assertTrue(
            storage_lock._is_lock_contention_error(contention, platform="nt")
        )
        self.assertFalse(
            storage_lock._is_lock_contention_error(unexpected, platform="nt")
        )

    def test_unexpected_os_error_is_immediately_reraised(self) -> None:
        carrier = self.root / "carrier.lock"
        with mock.patch.object(storage_lock, "_try_lock_windows") as lock_once:
            lock_once.side_effect = OSError(errno.EBADF, "bad handle")
            with mock.patch.object(storage_lock.os, "name", "nt"):
                with self.assertRaises(OSError) as caught:
                    storage_lock._acquire_os_lock(carrier, 2)
        self.assertEqual(errno.EBADF, caught.exception.errno)
        self.assertEqual(1, lock_once.call_count)

    @unittest.skipIf(os.name == "nt", "POSIX flock contract")
    def test_posix_nonblocking_lock_path(self) -> None:
        with storage_lock.shared_storage_lock(timeout=2):
            self.assertTrue(storage_lock.shared_storage_lock_held())

    def test_posix_helper_uses_exclusive_nonblocking_flock(self) -> None:
        fake_fcntl = mock.Mock()
        fake_fcntl.LOCK_EX = 2
        fake_fcntl.LOCK_NB = 4
        fake_fcntl.LOCK_UN = 8
        with mock.patch.dict(sys.modules, {"fcntl": fake_fcntl}):
            storage_lock._try_lock_posix(23)
            storage_lock._unlock_posix(23)
        self.assertEqual(
            [mock.call(23, 6), mock.call(23, 8)],
            fake_fcntl.flock.call_args_list,
        )

    def test_common_mutation_boundaries_enter_shared_lock(self) -> None:
        json_path = self.root / "settings.json"
        with mock.patch.object(
            runtime_paths, "shared_storage_lock", wraps=storage_lock.shared_storage_lock
        ) as json_lock:
            runtime_paths.atomic_write_json(json_path, {"ok": True})
        self.assertTrue(json_lock.called)

        workbook_path = self.root / "store.xlsx"
        store = ExcelWorkbookStore(workbook_path)
        with mock.patch(
            "excel_workbook_store.shared_storage_lock",
            wraps=storage_lock.shared_storage_lock,
        ) as workbook_lock:
            with store.workbook(write=True):
                pass
        self.assertTrue(workbook_lock.called)

        tasks_dir = self.root / "tasks"
        repository = TaskRepository(tasks_dir)
        task = repository.create_task(["https://example.com"], [], 1)
        with mock.patch(
            "repositories.task_repository.shared_storage_lock",
            wraps=storage_lock.shared_storage_lock,
        ) as task_lock:
            repository.delete_task(task["id"])
        self.assertTrue(task_lock.called)

    def test_recovery_enters_shared_lock(self) -> None:
        with mock.patch.object(
            staged_delete_transaction,
            "shared_storage_lock",
            wraps=storage_lock.shared_storage_lock,
        ) as recovery_lock:
            self.assertEqual(
                [],
                staged_delete_transaction.recover_pending_delete_transactions(
                    self.root / "runtime"
                ),
            )
        self.assertTrue(recovery_lock.called)

    def test_data_protection_read_modify_write_enters_shared_lock(self) -> None:
        saved: list[dict] = []
        service = CreatorService(
            lambda: None,
            lambda: None,
            lambda: {},
            lambda value: saved.append(value),
        )
        command = ManualTaskProtectionCommand(
            task_id="task_20260817T000000Z_12345678",
            account_uid="creator-account-1",
            values={"邮箱": "creator@example.test"},
            updated_at="2026-08-17T00:00:00Z",
        )
        with mock.patch.object(
            creator_service_module,
            "shared_storage_lock",
            wraps=storage_lock.shared_storage_lock,
        ) as protection_lock:
            service.commit_manual_task_protection(command)
        self.assertTrue(protection_lock.called)
        self.assertEqual(1, len(saved))

    def test_legacy_migration_and_startup_backup_enter_shared_lock(self) -> None:
        migration_source = (APP_DIR / "migrate_scrape_status.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("with shared_storage_lock():", migration_source)

        workbook = self.root / "Creator_Library.xlsx"
        workbook.write_bytes(b"workbook-fixture")
        with mock.patch.object(
            launcher, "shared_storage_lock", wraps=storage_lock.shared_storage_lock
        ) as backup_lock:
            backup = launcher.backup_creator_library(workbook)
        self.assertTrue(backup_lock.called)
        self.assertIsNotNone(backup)

    def test_cross_process_fixture_mutations_do_not_lose_updates(self) -> None:
        counter = self.root / "counter.json"
        counter.write_text('{"value": 0}', encoding="utf-8")
        source = (
            "import json, os, time\n"
            "from pathlib import Path\n"
            "from local_storage_lock import shared_storage_lock\n"
            "from runtime_paths import atomic_write_json\n"
            "path = Path(os.environ['M4_6C_COUNTER'])\n"
            "with shared_storage_lock(timeout=2):\n"
            " data = json.loads(path.read_text(encoding='utf-8'))\n"
            " time.sleep(0.2)\n"
            " atomic_write_json(path, {'value': data['value'] + 1})\n"
        )
        environment = self.child_env()
        environment["M4_6C_COUNTER"] = str(counter)
        processes = [
            subprocess.Popen(
                [sys.executable, "-u", "-c", source],
                cwd=ROOT,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        for process in processes:
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(0, process.returncode, stdout + stderr)
        self.assertEqual(2, json.loads(counter.read_text(encoding="utf-8"))["value"])


if __name__ == "__main__":
    unittest.main()
