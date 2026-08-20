from __future__ import annotations

import base64
import builtins
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from desktop_file_bridge import DesktopFileBridge  # noqa: E402


class FakeWebView:
    class FileDialog:
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
        self.root = ROOT / f".m4_7_desktop_bridge_{uuid.uuid4().hex}"
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


if __name__ == "__main__":
    unittest.main()
