from __future__ import annotations

import base64
import builtins
import shutil
import socket
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

from desktop_file_bridge import (  # noqa: E402
    DesktopFileBridge,
    _first_dialog_path,
    _is_inside_application_bundle,
    _resolve_save_target,
)
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


class FakeWebView:
    class FileDialog:
        OPEN = 10
        SAVE = 30


class FakeWindow:
    def __init__(self, selection) -> None:
        self.selection = selection
        self.calls = []

    def create_file_dialog(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.selection


class DesktopFileBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = test_artifact_path("m4_7_desktop_bridge", uuid.uuid4().hex)
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def payload(data: bytes = b"xlsx-bytes") -> str:
        return base64.b64encode(data).decode("ascii")

    def test_saves_user_selected_path_and_reports_it(self) -> None:
        target = self.root / "creator-export.xlsx"
        window = FakeWindow((str(target),))
        result = DesktopFileBridge(FakeWebView, window).save_xlsx("export.xlsx", self.payload())
        self.assertEqual({"saved": True, "canceled": False, "path": str(target)}, result)
        self.assertEqual(b"xlsx-bytes", target.read_bytes())
        self.assertEqual(FakeWebView.FileDialog.SAVE, window.calls[0][0][0])

    def test_macos_save_dialog_string_is_not_truncated_to_its_first_character(self) -> None:
        target = self.root / "导出 文件.xlsx"
        result = DesktopFileBridge(FakeWebView, FakeWindow(str(target))).save_xlsx(
            "export.xlsx", self.payload()
        )
        self.assertEqual({"saved": True, "canceled": False, "path": str(target)}, result)
        self.assertEqual(b"xlsx-bytes", target.read_bytes())

    def test_dialog_selection_normalizes_string_path_and_sequence(self) -> None:
        target = self.root / "selected.xlsx"
        self.assertEqual(str(target), _first_dialog_path(str(target)))
        self.assertEqual(str(target), _first_dialog_path((str(target),)))

    def test_cancel_returns_a_non_success_result(self) -> None:
        result = DesktopFileBridge(FakeWebView, FakeWindow(None)).save_xlsx("export.xlsx", self.payload())
        self.assertEqual({"saved": False, "canceled": True, "path": None}, result)

    def test_missing_extension_is_added_and_filename_cannot_inject_a_path(self) -> None:
        target = self.root / "chosen-name"
        window = FakeWindow((str(target),))
        bridge = DesktopFileBridge(FakeWebView, window)
        result = bridge.save_xlsx("..\\unsafe/path:name", self.payload())
        self.assertTrue(result["saved"])
        self.assertEqual(b"xlsx-bytes", (self.root / "chosen-name.xlsx").read_bytes())
        self.assertEqual("path_name.xlsx", window.calls[0][1]["save_filename"])

    def test_invalid_base64_and_write_error_never_report_success(self) -> None:
        window = FakeWindow((str(self.root / "write-error.xlsx"),))
        bridge = DesktopFileBridge(FakeWebView, window)
        invalid = bridge.save_xlsx("export.xlsx", "not base64!")
        self.assertEqual(False, invalid["saved"])
        self.assertEqual(False, invalid["canceled"])
        self.assertEqual([], window.calls)

        with mock.patch.object(builtins, "open", side_effect=OSError("denied")):
            failed = bridge.save_xlsx("export.xlsx", self.payload())
        self.assertEqual(False, failed["saved"])
        self.assertEqual(False, failed["canceled"])
        self.assertIn("error", failed)

    def test_existing_target_is_not_silently_overwritten(self) -> None:
        target = self.root / "existing.xlsx"
        target.write_bytes(b"existing")
        result = DesktopFileBridge(FakeWebView, FakeWindow((str(target),))).save_xlsx(
            "export.xlsx", self.payload(b"replacement")
        )
        self.assertEqual(False, result["saved"])
        self.assertEqual(b"existing", target.read_bytes())

    def test_directory_selection_generates_a_non_empty_export_filename(self) -> None:
        target = _resolve_save_target(self.root, "KOLConnect_Creator_Export.xlsx")
        self.assertEqual(self.root / "KOLConnect_Creator_Export.xlsx", target)
        self.assertTrue(target.name)

    def test_posix_root_selection_never_uses_empty_path_name(self) -> None:
        target = _resolve_save_target(Path("/"), "KOLConnect_Creator_Export.xlsx")
        self.assertEqual(Path("/KOLConnect_Creator_Export.xlsx"), target)
        self.assertEqual("KOLConnect_Creator_Export.xlsx", target.name)

    def test_explicit_unicode_filename_is_preserved(self) -> None:
        target = self.root / "导出 文件.xlsx"
        result = DesktopFileBridge(FakeWebView, FakeWindow((str(target),))).save_xlsx(
            "KOLConnect_Creator_Export.xlsx", self.payload()
        )
        self.assertEqual({"saved": True, "canceled": False, "path": str(target)}, result)
        self.assertEqual(b"xlsx-bytes", target.read_bytes())

    def test_open_xlsx_returns_bytes_and_filename_without_local_path(self) -> None:
        source = self.root / "达人 导入.xlsx"
        source.write_bytes(b"workbook-bytes")
        window = FakeWindow(str(source))
        result = DesktopFileBridge(FakeWebView, window).open_xlsx()
        self.assertEqual(True, result["selected"])
        self.assertEqual("达人 导入.xlsx", result["filename"])
        self.assertEqual(self.payload(b"workbook-bytes"), result["payload"])
        self.assertNotIn("path", result)
        self.assertEqual(FakeWebView.FileDialog.OPEN, window.calls[0][0][0])

    def test_open_xlsx_rejects_non_xlsx_and_handles_cancel(self) -> None:
        source = self.root / "not-workbook.txt"
        source.write_text("data", encoding="utf-8")
        invalid = DesktopFileBridge(FakeWebView, FakeWindow((str(source),))).open_xlsx()
        self.assertEqual("INVALID_FILE", invalid["error_code"])
        canceled = DesktopFileBridge(FakeWebView, FakeWindow(None)).open_xlsx()
        self.assertEqual({"selected": False, "canceled": True}, canceled)

    def test_packaged_app_bundle_is_not_an_export_destination(self) -> None:
        bundle = self.root / "KOLConnect.app"
        executable = bundle / "Contents" / "MacOS" / "KOLConnect"
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"binary")
        target = bundle / "Contents" / "KOLConnect_Creator_Export.xlsx"
        with mock.patch("desktop_file_bridge.sys.frozen", True, create=True), mock.patch(
            "desktop_file_bridge.sys.executable", str(executable)
        ):
            self.assertTrue(_is_inside_application_bundle(target))
            result = DesktopFileBridge(FakeWebView, FakeWindow((str(target),))).save_xlsx(
                "KOLConnect_Creator_Export.xlsx", self.payload()
            )
        self.assertEqual(False, result["saved"])
        self.assertIn("应用程序外", str(result["error"]))

    def test_local_service_diagnostics_use_launcher_url_and_backend_lifecycle(self) -> None:
        bridge = DesktopFileBridge(
            FakeWebView,
            service_url="http://127.0.0.1:8765/",
            backend_alive=lambda: False,
        )
        self.assertEqual(
            "LOCAL_SERVICE_BACKEND_EXITED",
            bridge.local_service_status("http://127.0.0.1:8765/settings")["code"],
        )

        bridge = DesktopFileBridge(
            FakeWebView,
            service_url="http://127.0.0.1:8765/",
            backend_alive=lambda: True,
        )
        self.assertEqual(
            "LOCAL_SERVICE_URL_MISMATCH",
            bridge.local_service_status("http://localhost:8765/settings")["code"],
        )
        with mock.patch("desktop_file_bridge.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = OSError("refused")
            self.assertEqual(
                "LOCAL_SERVICE_CONNECTION_REFUSED",
                bridge.local_service_status("http://127.0.0.1:8765/settings")["code"],
            )

        with mock.patch("desktop_file_bridge.build_opener") as build_opener:
            build_opener.return_value.open.side_effect = socket.timeout()
            self.assertEqual(
                "LOCAL_SERVICE_TIMEOUT",
                bridge.local_service_status("http://127.0.0.1:8765/settings")["code"],
            )

        response = mock.Mock()
        with mock.patch("desktop_file_bridge.build_opener") as build_opener:
            build_opener.return_value.open.return_value = response
            status = bridge.local_service_status("http://127.0.0.1:8765/settings")
        self.assertEqual({"reachable": True, "code": "LOCAL_SERVICE_READY", "origin": "http://127.0.0.1:8765"}, status)
        response.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
