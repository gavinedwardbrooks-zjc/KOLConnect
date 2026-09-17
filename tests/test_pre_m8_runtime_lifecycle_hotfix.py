from __future__ import annotations

import sys
import os
import subprocess
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import launcher
from services.feishu_chat_transport import FeishuChatTransport
sys.path.insert(0, str(ROOT / "tests"))
from test_support.runtime_sandbox import test_artifact_path


class _Event:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class _Thread:
    def __init__(self) -> None:
        self.join_calls = 0
        self.alive = True

    def join(self, timeout=None) -> None:
        del timeout
        self.join_calls += 1
        self.alive = False

    def is_alive(self) -> bool:
        return self.alive


class RuntimeLifecycleHotfixTests(unittest.TestCase):
    def test_windows_bundle_keeps_lark_modules_but_not_duplicate_python_data(self) -> None:
        spec = (ROOT / "packaging" / "spec" / "KOLConnect.spec").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("collect_all('lark_oapi')", spec)
        self.assertIn("hiddenimports += tmp_ret[2]", spec)
        self.assertIn("if not item[0].lower().endswith('.py')", spec)

    def test_windows_release_contract_is_versioned_onedir_zip(self) -> None:
        spec = (ROOT / "packaging" / "spec" / "KOLConnect.spec").read_text(
            encoding="utf-8-sig"
        )
        build = (ROOT / "packaging" / "build_release.ps1").read_text(
            encoding="utf-8-sig"
        )
        installer = (ROOT / "packaging" / "installer" / "KOLConnect.iss").read_text(
            encoding="utf-8-sig"
        )
        self.assertIn("exclude_binaries=True", spec)
        self.assertIn("COLLECT(", spec)
        self.assertIn('RELEASE_NAME = "KOLConnect_v1.0.0"', spec)
        self.assertIn('Write-Host "RELEASE_FORMAT = ONEDIR"', build)
        self.assertIn('$release = Join-Path $root "release"', build)
        self.assertIn('$releaseDirectory = Join-Path $release $releaseName', build)
        self.assertIn('$releaseZip = Join-Path $release "$releaseName.zip"', build)
        self.assertIn("[System.IO.Compression.ZipFile]::CreateFromDirectory(", build)
        self.assertIn('$stagingRoot = Join-Path $release ".staging-', build)
        self.assertIn('Get-ChildItem -LiteralPath $release -Directory -Filter ".staging-*"', build)
        self.assertIn('Move-Item -LiteralPath $stagingDirectory -Destination $releaseDirectory', build)
        self.assertIn('Move-Item -LiteralPath $stagingZip -Destination $releaseZip', build)
        self.assertIn('OutputDir={#SourcePath}\\..\\..\\release', installer)
        self.assertNotIn("GetEnv('USERPROFILE')", installer)
        self.assertIn("Expected exactly one packaged sqlite3.dll", build)

    def test_desktop_close_and_finalizer_share_idempotent_runtime_shutdown(self) -> None:
        shutdown = mock.Mock(return_value=True)
        thread = _Thread()
        runtime = launcher.LocalRuntime(
            SimpleNamespace(request_runtime_shutdown=shutdown), thread
        )
        window = SimpleNamespace(
            width=1200,
            height=800,
            events=SimpleNamespace(
                resized=_Event(), maximized=_Event(), restored=_Event(), closing=_Event()
            ),
        )
        with mock.patch.object(launcher, "atomic_write_json"):
            launcher.install_window_state_handlers(window, on_close=runtime.shutdown)
            window.events.closing.handlers[0](window)
        self.assertTrue(runtime.shutdown())
        shutdown.assert_called_once_with()
        self.assertEqual(2, thread.join_calls)

    def test_sqlite_authority_skips_legacy_excel_startup_backup(self) -> None:
        fake_server = SimpleNamespace(
            STATE={"creator_library": {"workbook_path": "C:/Data/Creator_Library.xlsx"}},
            DEFAULT_CREATOR_LIBRARY_WORKBOOK=Path("C:/Data/Creator_Library.xlsx"),
            DATA_DIR=Path("C:/Data"),
            run=lambda: None,
            _record_last_error=lambda _message: None,
            request_runtime_shutdown=lambda: True,
        )
        fake_thread = mock.Mock()
        with (
            mock.patch.object(launcher, "server_is_ready", return_value=False),
            mock.patch.object(launcher, "wait_for_server", return_value=True),
            mock.patch.object(launcher.threading, "Thread", return_value=fake_thread),
            mock.patch.object(launcher, "backup_creator_library") as backup,
            mock.patch.object(launcher, "log_event"),
            mock.patch("storage.migration.resolve_authority", return_value="sqlite_active"),
        ):
            launcher.start_local_runtime("desktop", server_module=fake_server)
        backup.assert_not_called()

    def test_feishu_executor_close_is_idempotent(self) -> None:
        transport = FeishuChatTransport(
            lambda: {}, lambda: None, trace_id_provider=lambda: "trace"
        )
        worker_name = transport._executor.submit(
            lambda: threading.current_thread().name
        ).result(timeout=5)
        self.assertTrue(worker_name.startswith("feishu-assistant"))
        with mock.patch.object(transport, "stop") as stop:
            transport.close()
            transport.close()
        stop.assert_called_once_with()
        self.assertFalse(
            any(
                thread.is_alive() and thread.name.startswith("feishu-assistant")
                for thread in threading.enumerate()
            )
        )

    def test_server_coordinator_releases_test_port_and_never_kills_unrelated_listener(self) -> None:
        runtime = test_artifact_path("pre_m8_lifecycle_subprocess")
        runtime.mkdir(parents=True, exist_ok=True)
        script = r'''
import sys
print("CHILD_START", file=sys.stderr, flush=True)
import socket
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path.cwd() / "app"))
print("BEFORE_SERVER_IMPORT", file=sys.stderr, flush=True)
import server
print("AFTER_SERVER_IMPORT", file=sys.stderr, flush=True)

def checkpoint(label):
    print(label, file=sys.stderr, flush=True)

class TestHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        checkpoint("SERVER_BIND_ENTER")
        checkpoint("TCP_BIND_START")
        socketserver.TCPServer.server_bind(self)
        checkpoint("TCP_BIND_END")
        host, port = self.server_address[:2]
        checkpoint("GETFQDN_START")
        self.server_name = socket.getfqdn(host)
        checkpoint("GETFQDN_END")
        self.server_port = port
        checkpoint("SERVER_BIND_EXIT")

    def server_activate(self):
        checkpoint("SERVER_ACTIVATE_START")
        super().server_activate()
        checkpoint("SERVER_ACTIVATE_END")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def finish(self):
        try:
            super().finish()
        finally:
            handler_finished.set()

def cycle(port):
    global handler_finished
    handler_finished = threading.Event()
    httpd = None
    thread = None
    try:
        checkpoint("BEFORE_HTTP_SERVER_CREATE")
        httpd = TestHTTPServer(("127.0.0.1", port), Handler)
        checkpoint("AFTER_HTTP_SERVER_CREATE")
        checkpoint("CYCLE_CREATED")
        with server._RUNTIME_SERVER_LOCK:
            server._RUNTIME_SERVER = httpd
            server._RUNTIME_SHUTDOWN_THREAD = None
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        checkpoint("SERVE_STARTED")
        # Prove serve_forever is accepting requests before asking it to shut down.
        with socket.create_connection(("127.0.0.1", port), timeout=5) as client:
            client.sendall(b"GET / HTTP/1.0\r\nHost: 127.0.0.1\r\n\r\n")
            response = bytearray()
            while chunk := client.recv(4096):
                response.extend(chunk)
            assert response.startswith(b"HTTP/1.0 200")
        assert handler_finished.wait(5)
        checkpoint("REQUEST_COMPLETED")
        assert server.request_runtime_shutdown()
        checkpoint("SHUTDOWN_1_RETURNED")
        assert server.request_runtime_shutdown()
        checkpoint("SHUTDOWN_2_RETURNED")
        thread.join(5)
        assert not thread.is_alive()
        checkpoint("SERVE_THREAD_JOINED")
        shutdown_thread = server._RUNTIME_SHUTDOWN_THREAD
        assert shutdown_thread is not None
        shutdown_thread.join(5)
        assert not shutdown_thread.is_alive()
    finally:
        # Bound failure cleanup so the original assertion can reach the parent.
        if httpd is not None and thread is not None and thread.is_alive():
            cleanup = threading.Thread(target=httpd.shutdown, daemon=True)
            cleanup.start()
            cleanup.join(5)
        if httpd is not None:
            checkpoint("SERVER_CLOSE_START")
            httpd.server_close()
            checkpoint("SERVER_CLOSE_END")
        if thread is not None:
            thread.join(5)
        with server._RUNTIME_SERVER_LOCK:
            server._RUNTIME_SERVER = None
            server._RUNTIME_SHUTDOWN_THREAD = None
        checkpoint("CYCLE_END")

probe = socket.socket()
checkpoint("BEFORE_PROBE_BIND")
probe.bind(("127.0.0.1", 0))
checkpoint("AFTER_PROBE_BIND")
port = probe.getsockname()[1]
probe.close()
checkpoint("BEFORE_FIRST_CYCLE")
for _ in range(3):
    cycle(port)

unrelated = socket.socket()
unrelated.bind(("127.0.0.1", 0))
unrelated.listen(1)
with server._RUNTIME_SERVER_LOCK:
    server._RUNTIME_SERVER = None
assert server.request_runtime_shutdown() is False
assert unrelated.getsockname()[1] > 0
unrelated.close()
checkpoint("PROCESS_END")
'''
        environment = os.environ.copy()
        environment["APPDATA"] = str(runtime / "appdata")
        environment["TEMP"] = str(runtime / "temp")
        environment["TMP"] = str(runtime / "temp")
        Path(environment["TEMP"]).mkdir(parents=True, exist_ok=True)
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stderr = exc.stderr or b""
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            self.fail(f"Lifecycle child timed out; last checkpoints:\n{stderr}")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
