from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))


def _close_app_logger() -> None:
    app_logging = sys.modules.get("app_logging")
    if app_logging is None:
        return
    logger = app_logging.logging.getLogger(app_logging.LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    app_logging._CONFIGURED = False


class ReleaseApiSmokeTests(unittest.TestCase):
    def test_release_read_endpoints_start_and_respond(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".m5_4_t4_") as temp_dir, mock.patch.dict(
            os.environ,
            {
                "APPDATA": temp_dir,
                "HOME": temp_dir,
                "XDG_DATA_HOME": temp_dir,
            },
        ):
            for module_name in (
                "server",
                "runtime_paths",
                "mail_sync",
                "task_manager",
                "dashboard_repository",
                "dashboard_service",
            ):
                sys.modules.pop(module_name, None)
            server = importlib.import_module("server")
            httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base_url = f"http://127.0.0.1:{httpd.server_port}"
            paths = (
                "/api/state",
                "/api/system/health",
                "/api/dashboard",
                "/api/risks",
                "/api/analytics/platforms",
                "/api/analytics/geography",
                "/api/analytics/roi-trend",
                "/api/creator-library",
                "/api/campaigns",
            )
            try:
                for path in paths:
                    with self.subTest(path=path):
                        with urllib.request.urlopen(base_url + path, timeout=15) as response:
                            payload = json.loads(response.read().decode("utf-8"))
                        self.assertEqual(200, response.status)
                        self.assertTrue(payload.get("ok", True), path)
            finally:
                httpd.shutdown()
                httpd.server_close()
                thread.join(timeout=5)
                _close_app_logger()


if __name__ == "__main__":
    unittest.main()
