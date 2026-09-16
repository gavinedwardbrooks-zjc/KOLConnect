"""Regression contract for the retired standalone Browser Mode."""

from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPOSITORY_ROOT / "app"


class BrowserModeRetirementTests(unittest.TestCase):
    def test_launcher_keeps_desktop_startup_without_browser_mode_entrypoints(self) -> None:
        source = (APP_ROOT / "launcher.py").read_text(encoding="utf-8")

        self.assertIn("def run_desktop", source)
        self.assertIn('start_local_runtime("desktop")', source)
        self.assertNotIn("def run_browser", source)
        self.assertNotIn('"--browser"', source)
        self.assertNotIn("import webbrowser", source)

    def test_browser_shutdown_surface_is_absent_but_desktop_shutdown_remains(self) -> None:
        server_source = (APP_ROOT / "server.py").read_text(encoding="utf-8")
        security_source = (APP_ROOT / "local_request_security.py").read_text(encoding="utf-8")

        self.assertIn('HOST = "127.0.0.1"', server_source)
        self.assertIn("request_runtime_shutdown", server_source)
        self.assertNotIn("/api/runtime/shutdown", server_source)
        self.assertNotIn("browser_shutdown_allowed", security_source)


if __name__ == "__main__":
    unittest.main()
