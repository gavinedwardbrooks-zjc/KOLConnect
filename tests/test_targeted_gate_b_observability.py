from __future__ import annotations

import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import app_logging  # noqa: E402
import server  # noqa: E402
from api_contract import set_trace_id  # noqa: E402


class _ExplodingEndpoint:
    @staticmethod
    def handle(_handler, _request, _context) -> bool:
        raise RuntimeError("synthetic-password=do-not-log")


class _KnownErrorEndpoint:
    @staticmethod
    def handle(handler, _request, _context) -> bool:
        handler._api_error("KNOWN_DOMAIN_ERROR", "Specific safe domain error.", status=409)
        return True


class ApiExceptionBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.scope = patch.object(server.Handler, "_repository_request_scope", return_value=nullcontext())
        self.scope.start()

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.scope.stop()

    def _request_failure(self) -> tuple[int, dict]:
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(self.base_url + "/api/diagnostic-failure", timeout=5)
        response = raised.exception
        try:
            return response.code, json.loads(response.read().decode("utf-8"))
        finally:
            response.close()

    def test_unexpected_get_exception_returns_sanitized_traceable_json(self) -> None:
        with patch.object(server, "HANDLERS", [_ExplodingEndpoint]), patch.object(
            server, "log_sanitized_exception"
        ) as log_exception:
            status, payload = self._request_failure()

        self.assertEqual(500, status)
        self.assertFalse(payload["ok"])
        self.assertEqual("INTERNAL_SERVER_ERROR", payload["error"]["code"])
        self.assertRegex(payload["trace_id"], r"^trace_[0-9a-f]{32}$")
        serialized = json.dumps(payload)
        self.assertNotIn("synthetic-password", serialized)
        self.assertNotIn("Traceback", serialized)
        log_exception.assert_called_once()
        self.assertEqual("GET", log_exception.call_args.args[1].split("method=")[1].split(" ")[0])

    def test_known_domain_error_remains_specific(self) -> None:
        with patch.object(server, "HANDLERS", [_KnownErrorEndpoint]):
            status, payload = self._request_failure()

        self.assertEqual(409, status)
        self.assertEqual("KNOWN_DOMAIN_ERROR", payload["error"]["code"])
        self.assertEqual("Specific safe domain error.", payload["error"]["message"])

    def test_sanitized_exception_log_keeps_traceback_without_secret(self) -> None:
        set_trace_id("trace_test_sanitized")
        try:
            raise RuntimeError("synthetic-password=do-not-log")
        except RuntimeError as exc:
            with patch.object(app_logging, "get_logger") as get_logger:
                app_logging.log_sanitized_exception("API", "request failed", exc)

        args = get_logger.return_value.error.call_args.args
        kwargs = get_logger.return_value.error.call_args.kwargs
        self.assertNotIn("synthetic-password", str(args))
        self.assertIn("trace_id=trace_test_sanitized", str(args))
        exception_type, safe_exception, traceback = kwargs["exc_info"]
        self.assertIs(RuntimeError, exception_type)
        self.assertNotIn("synthetic-password", str(safe_exception))
        self.assertIsNotNone(traceback)
        set_trace_id("")


if __name__ == "__main__":
    unittest.main()
