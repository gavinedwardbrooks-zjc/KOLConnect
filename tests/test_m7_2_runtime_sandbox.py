from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "app"))

from test_support.runtime_sandbox import (  # noqa: E402
    assert_not_production_runtime,
    assert_not_production_workbook,
    isolated_runtime,
    production_app_data_path,
    test_runtime_sandbox,
)
import runtime_paths


class RuntimeSandboxTests(unittest.TestCase):
    def test_runtime_and_temp_are_workspace_local(self):
        previous_appdata = os.environ.get("APPDATA")
        with isolated_runtime("paths") as root:
            appdata = Path(os.environ["APPDATA"])
            temp = Path(tempfile.gettempdir())
            self.assertTrue(appdata.is_relative_to(ROOT))
            self.assertTrue(temp.is_relative_to(ROOT))
            self.assertTrue(appdata.is_relative_to(root))
            self.assertTrue(temp.is_relative_to(root))
        self.assertEqual(previous_appdata, os.environ.get("APPDATA"))

    def test_production_runtime_guard_fails_closed(self):
        with self.assertRaisesRegex(
            AssertionError, "TEST_RUNTIME_POINTS_TO_PRODUCTION_DATA"
        ):
            assert_not_production_runtime(production_app_data_path())

    def test_production_workbook_guard_fails_before_mutation(self):
        workbook = production_app_data_path() / "Creator_Library.xlsx"
        with self.assertRaisesRegex(
            AssertionError, "TEST_RUNTIME_POINTS_TO_PRODUCTION_WORKBOOK"
        ):
            assert_not_production_workbook(workbook)

    def test_nested_runtime_restores_outer_then_process_environment(self):
        original = {key: os.environ.get(key) for key in ("APPDATA", "TEMP")}
        with test_runtime_sandbox("outer") as outer:
            self.assertEqual(str(outer.appdata), os.environ["APPDATA"])
            with test_runtime_sandbox("inner") as inner:
                self.assertEqual(str(inner.appdata), os.environ["APPDATA"])
                self.assertNotEqual(outer.root, inner.root)
            self.assertEqual(str(outer.appdata), os.environ["APPDATA"])
            self.assertEqual(str(outer.temp), tempfile.gettempdir())
        self.assertEqual(original["APPDATA"], os.environ.get("APPDATA"))
        self.assertEqual(original["TEMP"], os.environ.get("TEMP"))

    def test_runtime_exposes_isolated_storage_contract(self):
        with test_runtime_sandbox("contract") as runtime:
            for path in (
                runtime.data_root,
                runtime.lock_root,
                runtime.backup_root,
                runtime.settings_path.parent,
                runtime.workbook_path.parent,
            ):
                self.assertTrue(path.is_relative_to(runtime.root))
            self.assertFalse(runtime.settings_path.exists())
            self.assertFalse(runtime.workbook_path.exists())

    def test_macos_native_path_uses_sandbox_home(self):
        with test_runtime_sandbox("darwin_contract") as runtime:
            with (
                mock.patch.object(runtime_paths.sys, "platform", "darwin"),
                mock.patch.object(runtime_paths.Path, "home", return_value=runtime.home),
            ):
                self.assertEqual(
                    runtime.home / "Library" / "Application Support" / "KOLConnect",
                    runtime_paths.get_app_data_dir(),
                )

    def test_fixture_home_override_keeps_native_platform_contract(self):
        with test_runtime_sandbox("darwin_fixture") as runtime:
            fixture_home = runtime.root / "fixture_home"
            with (
                mock.patch.object(runtime_paths.sys, "platform", "darwin"),
                mock.patch.object(runtime_paths.Path, "home", return_value=fixture_home),
                mock.patch.dict(os.environ, {"HOME": str(fixture_home)}),
            ):
                self.assertEqual(
                    fixture_home / "Library" / "Application Support" / "KOLConnect",
                    runtime_paths.get_app_data_dir(),
                )

    def test_windows_style_unicode_and_spaces_are_safe(self):
        with test_runtime_sandbox("Windows 路径 with spaces") as runtime:
            target = runtime.data_root / "nested folder" / "状态.json"
            target.parent.mkdir(parents=True)
            target.write_text("{}", encoding="utf-8")
            self.assertEqual("{}", target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
