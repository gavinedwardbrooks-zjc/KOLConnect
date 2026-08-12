from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import chromedriver_resolver
import scraper


class ChromeDriverResolverTests(unittest.TestCase):
    def _driver_file(self, directory: str) -> Path:
        path = Path(directory) / ("chromedriver.exe" if sys.platform == "win32" else "chromedriver")
        path.write_bytes(b"driver")
        if sys.platform != "win32":
            path.chmod(0o755)
        return path

    def test_resolver_returns_webdriver_manager_path(self):
        with tempfile.TemporaryDirectory() as directory:
            driver_path = self._driver_file(directory)
            with mock.patch.object(chromedriver_resolver, "ChromeDriverManager") as manager:
                manager.return_value.install.return_value = str(driver_path)
                resolved = chromedriver_resolver.resolve_chromedriver()

        self.assertEqual(resolved, driver_path)
        manager.assert_called_once_with()
        manager.return_value.install.assert_called_once_with()

    def test_manager_failure_becomes_project_error_without_fallback(self):
        with mock.patch.object(chromedriver_resolver, "ChromeDriverManager") as manager:
            manager.return_value.install.side_effect = RuntimeError("third-party detail")
            with self.assertRaises(chromedriver_resolver.ChromeDriverResolutionError) as raised:
                chromedriver_resolver.resolve_chromedriver()

        message = str(raised.exception)
        self.assertIn("ChromeDriver 自动匹配失败", message)
        self.assertIn("网络连接", message)
        self.assertNotIn("third-party detail", message)

    def test_invalid_cached_or_downloaded_path_is_rejected(self):
        missing_path = Path(tempfile.gettempdir()) / "missing-kolconnect-chromedriver"
        with mock.patch.object(chromedriver_resolver, "ChromeDriverManager") as manager:
            manager.return_value.install.return_value = str(missing_path)
            with self.assertRaises(chromedriver_resolver.ChromeDriverResolutionError):
                chromedriver_resolver.resolve_chromedriver()

    def test_non_executable_driver_is_rejected_on_macos(self):
        with tempfile.TemporaryDirectory() as directory:
            driver_path = self._driver_file(directory)
            with (
                mock.patch.object(chromedriver_resolver, "ChromeDriverManager") as manager,
                mock.patch.object(chromedriver_resolver.sys, "platform", "darwin"),
                mock.patch.object(chromedriver_resolver.os, "access", return_value=False),
            ):
                manager.return_value.install.return_value = str(driver_path)
                with self.assertRaises(chromedriver_resolver.ChromeDriverResolutionError) as raised:
                    chromedriver_resolver.resolve_chromedriver()

        self.assertIn("没有执行权限", str(raised.exception))

    def test_scraper_uses_resolved_service_and_preserves_profile_options(self):
        with tempfile.TemporaryDirectory() as directory:
            profile_root = Path(directory) / "Chrome"
            (profile_root / "Default").mkdir(parents=True)
            driver_path = self._driver_file(directory)
            fake_driver = mock.Mock()

            with (
                mock.patch.object(scraper, "resolve_chromedriver", return_value=driver_path),
                mock.patch.object(scraper, "should_use_direct_profile", return_value=True),
                mock.patch.object(scraper, "Service") as service_type,
                mock.patch.object(scraper.webdriver, "Chrome", return_value=fake_driver) as chrome,
            ):
                result = scraper.make_chrome_driver(str(profile_root), "Default")

        service_type.assert_called_once_with(str(driver_path))
        options = chrome.call_args.kwargs["options"]
        self.assertIs(chrome.call_args.kwargs["service"], service_type.return_value)
        self.assertIn(f"--user-data-dir={profile_root}", options.arguments)
        self.assertIn("--profile-directory=Default", options.arguments)
        self.assertIn("--remote-debugging-port=0", options.arguments)
        self.assertIs(result, fake_driver)

    def test_resolution_failure_uses_existing_browser_error_boundary(self):
        resolution_error = chromedriver_resolver.ChromeDriverResolutionError("friendly resolver error")
        with mock.patch.object(scraper, "resolve_chromedriver", side_effect=resolution_error):
            with self.assertRaises(scraper.BrowserStartError) as raised:
                scraper.make_chrome_driver()

        self.assertEqual(str(raised.exception), "friendly resolver error")

    def test_selenium_version_mismatch_has_specific_browser_error(self):
        mismatch = scraper.WebDriverException(
            "session not created: This version of ChromeDriver only supports Chrome version 114"
        )
        with (
            mock.patch.object(scraper, "resolve_chromedriver", return_value=Path("driver")),
            mock.patch.object(scraper, "Service"),
            mock.patch.object(scraper.webdriver, "Chrome", side_effect=mismatch),
        ):
            with self.assertRaises(scraper.BrowserStartError) as raised:
                scraper.make_chrome_driver()

        self.assertIn("与当前 Chrome 版本不兼容", str(raised.exception))

    def test_project_does_not_delete_webdriver_manager_cache(self):
        source = (APP_DIR / "chromedriver_resolver.py").read_text(encoding="utf-8")
        self.assertNotIn("rmtree", source)
        self.assertNotIn("unlink", source)
        self.assertNotIn("cache_valid_range", source)


if __name__ == "__main__":
    unittest.main()
