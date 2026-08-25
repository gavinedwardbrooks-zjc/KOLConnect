from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import api_contract  # noqa: E402
import app_logging  # noqa: E402
from http_handlers import feishu_sync_handler  # noqa: E402


class _HttpHandler:
    def __init__(self):
        self.responses = []

    def _json(self, payload, status=200):
        self.responses.append((status, payload))

    def _error(self, message, status=400):
        self.responses.append((status, {"error": message}))


class _FeishuService:
    def validate_connection(self):
        return {"status": "success", "connection_ok": True}

    def dry_run(self):
        return {"status": "success", "creator_create_count": 2}

    def full_sync(self, *, confirm):
        if confirm is not True:
            raise ValueError("FEISHU_SYNC_CONFIRMATION_REQUIRED")
        return {"status": "success", "creator_created": 2}


class ApiContractTests(unittest.TestCase):
    def tearDown(self):
        api_contract.set_trace_id("")

    def test_envelope_shapes_are_stable(self):
        self.assertEqual(
            {"ok": True, "data": {"value": 1}},
            api_contract.success_payload({"value": 1}),
        )
        payload = api_contract.error_payload(
            "VALIDATION_ERROR", "输入无效。", details={"field": "name"}
        )
        self.assertFalse(payload["ok"])
        self.assertEqual("VALIDATION_ERROR", payload["error"]["code"])
        self.assertEqual("输入无效。", payload["error"]["message"])
        self.assertEqual({"field": "name"}, payload["error"]["details"])

    def test_request_json_adds_trace_to_body_header_and_log(self):
        runtime = ROOT / ".test_runtime" / "m7_2" / "api_contract_subprocess"
        runtime.mkdir(parents=True, exist_ok=True)
        script = r'''
import io, json, sys
sys.path.insert(0, sys.argv[1])
import server
handler = server.Handler.__new__(server.Handler)
handler.path = "/api/example"
handler.command = "GET"
handler.wfile = io.BytesIO()
handler.send_response = lambda status: None
headers = {}
handler.send_header = headers.__setitem__
handler.end_headers = lambda: None
handler._json({"value": 1})
body = json.loads(handler.wfile.getvalue().decode("utf-8"))
error_handler = server.Handler.__new__(server.Handler)
error_handler.path = "/api/example"
error_handler.command = "GET"
error_handler.wfile = io.BytesIO()
error_handler.send_response = lambda status: None
error_headers = {}
error_handler.send_header = error_headers.__setitem__
error_handler.end_headers = lambda: None
error_handler._json(server.error_payload("INTERNAL_ERROR", "安全错误。"), status=500)
error_body = json.loads(error_handler.wfile.getvalue().decode("utf-8"))
log_text = server.RUN_LOG_FILE.read_text(encoding="utf-8")
print(json.dumps({"body": body, "header": headers["X-Trace-ID"], "logged": body["trace_id"] in log_text, "error_body": error_body}))
'''
        env = os.environ.copy()
        env["APPDATA"] = str(runtime)
        env["XDG_DATA_HOME"] = str(runtime)
        completed = subprocess.run(
            [sys.executable, "-c", script, str(APP_DIR)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        result = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertRegex(result["body"]["trace_id"], r"^trace_[0-9a-f]{32}$")
        self.assertEqual(result["body"]["trace_id"], result["header"])
        self.assertTrue(result["logged"])
        self.assertFalse(result["error_body"]["ok"])
        self.assertEqual("INTERNAL_ERROR", result["error_body"]["error"]["code"])
        self.assertEqual(result["body"]["trace_id"], result["error_body"]["trace_id"])

    def test_unique_server_trace_ids_and_no_client_value_reuse(self):
        first = api_contract.new_trace_id()
        second = api_contract.new_trace_id()
        self.assertNotEqual(first, second)
        source = (APP_DIR / "server.py").read_text(encoding="utf-8-sig")
        self.assertNotIn('headers.get("X-Trace-ID")', source)

    def test_log_context_contains_same_trace_id(self):
        api_contract.set_trace_id("trace_test")
        with patch.object(app_logging, "get_logger") as get_logger:
            app_logging.log_event("API", "request complete")
        args = get_logger.return_value.log.call_args.args
        self.assertIn("trace_id=trace_test", args[-1])

    def test_feishu_endpoint_preserves_legacy_fields_inside_standard_envelope(self):
        handler = _HttpHandler()
        request = {
            "method": "POST",
            "path": "/api/feishu-sync/validate",
            "get_payload": lambda: {},
        }
        context = {
            "services": {"feishu_sync": _FeishuService()},
            "logging": {"error": lambda *_args: None},
        }
        self.assertTrue(feishu_sync_handler.handle(handler, request, context))
        payload = handler.responses[0][1]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["data"]["status"], payload["status"])
        self.assertTrue(payload["connection_ok"])

    def test_feishu_confirmation_error_uses_safe_structured_contract(self):
        handler = _HttpHandler()
        request = {
            "method": "POST",
            "path": "/api/feishu-sync/full-sync",
            "get_payload": lambda: {},
        }
        context = {
            "services": {"feishu_sync": _FeishuService()},
            "logging": {"error": lambda *_args: None},
        }
        feishu_sync_handler.handle(handler, request, context)
        status, payload = handler.responses[0]
        self.assertEqual(400, status)
        self.assertFalse(payload["ok"])
        self.assertEqual("FEISHU_SYNC_CONFIRMATION_REQUIRED", payload["error"]["code"])
        self.assertNotIn("secret", json.dumps(payload).casefold())


if __name__ == "__main__":
    unittest.main()
