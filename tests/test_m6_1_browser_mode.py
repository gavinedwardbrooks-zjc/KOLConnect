from __future__ import annotations

import ast
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import launcher  # noqa: E402
import local_request_security as security  # noqa: E402


class _FakeThread:
    def __init__(self, *, target=None, args=(), name="", daemon=False) -> None:
        self.target = target
        self.args = args
        self.name = name
        self.daemon = daemon
        self.started = False
        self.joined = False

    def start(self) -> None:
        self.started = True

    def join(self) -> None:
        self.joined = True


def _fake_server(workbook: Path | None = None):
    workbook = workbook or Path("Creator_Library.xlsx")
    return SimpleNamespace(
        STATE={"creator_library": {"workbook_path": str(workbook)}},
        DEFAULT_CREATOR_LIBRARY_WORKBOOK=workbook,
        run=lambda: None,
        _record_last_error=lambda _message: None,
    )


class BrowserModeStartupTests(unittest.TestCase):
    def test_server_import_is_static_and_pyinstaller_discoverable(self) -> None:
        source = (APP_DIR / "launcher.py").read_text(encoding="utf-8-sig")
        tree = ast.parse(source)
        start_function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "start_local_runtime"
        )
        imported_modules = {
            alias.name
            for node in ast.walk(start_function)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        self.assertIn("server", imported_modules)
        self.assertNotIn('importlib.import_module("server")', source)

    def test_default_startup_remains_desktop_and_browser_flag_selects_browser(self) -> None:
        with (
            mock.patch.object(launcher, "get_logs_dir"),
            mock.patch.object(launcher, "run_desktop") as desktop,
            mock.patch.object(launcher, "run_browser") as browser,
        ):
            launcher.main([])
            desktop.assert_called_once_with()
            browser.assert_not_called()

            desktop.reset_mock()
            launcher.main(["--browser"])
            browser.assert_called_once_with()
            desktop.assert_not_called()

    def test_browser_and_desktop_share_server_readiness_and_backup_path(self) -> None:
        workbook = Path("C:/Data/Creator_Library.xlsx")
        fake_server = _fake_server(workbook)
        created_threads: list[_FakeThread] = []

        def create_thread(**kwargs):
            thread = _FakeThread(**kwargs)
            created_threads.append(thread)
            return thread

        for mode in ("desktop", "browser"):
            with (
                self.subTest(mode=mode),
                mock.patch.dict(os.environ, {}, clear=False),
                mock.patch.object(launcher, "server_is_ready", return_value=False),
                mock.patch.object(launcher, "wait_for_server", return_value=True) as readiness,
                mock.patch.object(launcher.threading, "Thread", side_effect=create_thread),
                mock.patch.object(launcher, "backup_creator_library") as backup,
            ):
                runtime = launcher.start_local_runtime(mode, server_module=fake_server)
                self.assertIs(fake_server, runtime.server_module)
                self.assertTrue(runtime.server_thread.started)
                self.assertEqual("kolconnect-server", runtime.server_thread.name)
                readiness.assert_called_once()
                backup.assert_called_once_with(workbook)
                self.assertEqual("1", os.environ.get(f"KOLCONNECT_{mode.upper()}"))

    def test_browser_opens_once_only_after_ready_and_tests_can_skip_join(self) -> None:
        events: list[str] = []
        thread = _FakeThread()
        runtime = launcher.LocalRuntime(_fake_server(), thread)

        def start_runtime(mode):
            self.assertEqual("browser", mode)
            events.append("ready")
            return runtime

        def open_browser(url):
            events.append("open")
            self.assertEqual(launcher.APP_URL, url)

        with mock.patch.object(launcher, "start_local_runtime", side_effect=start_runtime):
            launcher.run_browser(browser_opener=open_browser, wait_for_exit=False)
        self.assertEqual(["ready", "open"], events)
        self.assertFalse(thread.joined)

    def test_readiness_failure_never_opens_browser(self) -> None:
        opener = mock.Mock()
        with mock.patch.object(
            launcher, "start_local_runtime", side_effect=RuntimeError("本地服务启动超时")
        ):
            with self.assertRaisesRegex(RuntimeError, "启动超时"):
                launcher.run_browser(browser_opener=opener, wait_for_exit=False)
        opener.assert_not_called()

    def test_port_conflict_is_readable_and_does_not_start_another_server(self) -> None:
        fake_server = _fake_server()
        with (
            mock.patch.object(launcher, "server_is_ready", return_value=True),
            mock.patch.object(launcher, "_record_startup_error") as record_error,
            mock.patch.object(launcher.threading, "Thread") as thread,
        ):
            with self.assertRaisesRegex(RuntimeError, "端口 8765 被占用"):
                launcher.start_local_runtime("browser", server_module=fake_server)
        record_error.assert_called_once()
        thread.assert_not_called()

    def test_server_binding_is_fixed_to_loopback(self) -> None:
        self.assertEqual("127.0.0.1", launcher.HOST)
        self.assertEqual(8765, launcher.PORT)
        self.assertNotEqual("0.0.0.0", launcher.HOST)
        source = (APP_DIR / "server.py").read_text(encoding="utf-8-sig")
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {"HOST", "PORT"}
        }
        self.assertEqual({"HOST": "127.0.0.1", "PORT": 8765}, assignments)
        self.assertNotIn('HOST = "0.0.0.0"', source)


class LocalRequestSecurityTests(unittest.TestCase):
    def test_local_hosts_and_origins_are_allowed(self) -> None:
        for host in ("127.0.0.1:8765", "localhost:8765", "LOCALHOST:8765"):
            self.assertTrue(security.allowed_host_header(host, 8765))
        for origin in ("http://127.0.0.1:8765", "http://localhost:8765", ""):
            self.assertTrue(security.allowed_mutation_origin(origin, "/api/settings/ui", 8765))

    def test_unexpected_host_and_external_mutation_origin_are_rejected(self) -> None:
        self.assertFalse(security.allowed_host_header("example.com:8765", 8765))
        self.assertFalse(security.allowed_host_header("127.0.0.1:9000", 8765))
        self.assertFalse(
            security.allowed_mutation_origin("https://example.com", "/api/settings/ui", 8765)
        )

    def test_extension_origin_is_limited_to_existing_import_path(self) -> None:
        extension_origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
        self.assertTrue(
            security.allowed_mutation_origin(
                extension_origin, "/api/extension/import", 8765
            )
        )
        self.assertFalse(
            security.allowed_mutation_origin(extension_origin, "/api/settings/ui", 8765)
        )


class BrowserModeShutdownTests(unittest.TestCase):
    def test_shutdown_route_is_browser_only_and_runs_after_response(self) -> None:
        self.assertTrue(
            security.browser_shutdown_allowed("/api/runtime/shutdown", "1")
        )
        self.assertFalse(
            security.browser_shutdown_allowed("/api/runtime/shutdown", "")
        )
        self.assertFalse(
            security.browser_shutdown_allowed("/api/runtime/shutdown", "0")
        )
        self.assertFalse(
            security.browser_shutdown_allowed("/api/settings/ui", "1")
        )
        self.assertTrue(security.allowed_host_header("127.0.0.1:8765", 8765))
        self.assertTrue(
            security.allowed_mutation_origin(
                "http://127.0.0.1:8765", "/api/runtime/shutdown", 8765
            )
        )
        self.assertFalse(security.allowed_host_header("example.com:8765", 8765))
        self.assertFalse(
            security.allowed_mutation_origin(
                "https://example.com", "/api/runtime/shutdown", 8765
            )
        )
        source = (APP_DIR / "server.py").read_text(encoding="utf-8-sig")
        self.assertIn('path != "/api/runtime/shutdown"', source)
        self.assertIn('os.environ.get("KOLCONNECT_BROWSER") != "1"', source)
        response_position = source.index("self._ok(shutting_down=True)")
        shutdown_position = source.index("target=self.server.shutdown")
        self.assertLess(response_position, shutdown_position)
        self.assertIn("if not self._allow_local_request():", source)

    def test_shutdown_route_is_not_exposed_by_desktop_mode(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            launcher._configure_runtime_mode("desktop")
            self.assertEqual("1", os.environ.get("KOLCONNECT_DESKTOP"))
            self.assertIsNone(os.environ.get("KOLCONNECT_BROWSER"))
            self.assertFalse(
                security.browser_shutdown_allowed(
                    "/api/runtime/shutdown", os.environ.get("KOLCONNECT_BROWSER")
                )
            )


if __name__ == "__main__":
    unittest.main()
