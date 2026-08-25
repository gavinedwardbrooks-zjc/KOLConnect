from __future__ import annotations

from pathlib import Path
import sys
import unittest
import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from http_handlers import assistant_handler  # noqa: E402


class FakeHandler:
    def __init__(self):
        self.payload = None
        self.status = None

    def _json(self, payload, status=200):
        self.payload = payload
        self.status = status


class FakeService:
    def capabilities(self, trace_id):
        return {"ok": True, "mode": "deterministic", "intents": [], "trace_id": trace_id}

    def message(self, message, session_id, trace_id):
        return {"ok": True, "reply": "safe", "intent": "daily_summary", "requires_confirmation": False, "trace_id": trace_id}

    def confirm(self, token, confirm, session_id, trace_id):
        return {"ok": False, "error": {"code": "CONFIRMATION_MISMATCH", "message": "safe"}, "trace_id": trace_id}


class AssistantApiTests(unittest.TestCase):
    def request(self, method, path, payload=None):
        handler = FakeHandler()
        request = {"method": method, "path": path, "trace_id": "trace_api", "get_payload": lambda: payload or {}}
        handled = assistant_handler.handle(handler, request, {"request": {"trace_id": "trace_api"}, "services": {"assistant": FakeService()}})
        return handled, handler.status, handler.payload

    def test_capabilities_and_message_use_m72_envelope_and_trace(self):
        for method, path, payload in (
            ("GET", "/api/assistant/capabilities", None),
            ("POST", "/api/assistant/message", {"message": "日报", "session_id": "s1"}),
        ):
            with self.subTest(path=path):
                handled, status, body = self.request(method, path, payload)
                self.assertTrue(handled)
                self.assertEqual(200, status)
                self.assertTrue(body["ok"])
                self.assertEqual("trace_api", body["trace_id"])
                self.assertIn("data", body)

    def test_confirmation_error_is_structured_and_sanitized(self):
        handled, status, body = self.request("POST", "/api/assistant/confirm", {"confirmation_token": "bad", "confirm": True, "session_id": "s1", "app_secret": "never"})
        self.assertTrue(handled)
        self.assertEqual(409, status)
        self.assertEqual("CONFIRMATION_MISMATCH", body["error"]["code"])
        self.assertNotIn("never", str(body))

    def test_openapi_and_server_register_only_the_narrow_assistant_surface(self):
        spec = yaml.safe_load((ROOT / "docs" / "openapi.yaml").read_text(encoding="utf-8"))
        assistant_paths = sorted(path for path in spec["paths"] if path.startswith("/api/assistant/"))
        self.assertEqual(
            ["/api/assistant/capabilities", "/api/assistant/confirm", "/api/assistant/message"],
            assistant_paths,
        )
        server_source = (ROOT / "app" / "server.py").read_text(encoding="utf-8-sig")
        self.assertIn("assistant_handler", server_source)
        self.assertIn('"assistant": get_assistant_service()', server_source)

    def test_assistant_layer_has_no_store_filesystem_shell_or_generic_http_access(self):
        sources = "\n".join(
            path.read_text(encoding="utf-8-sig")
            for path in (ROOT / "app" / "services").glob("assistant_*.py")
        )
        for forbidden in (
            "openpyxl", "CreatorRepository", "CampaignRepository", "TaskRepository",
            "subprocess", "requests.", "urllib.request", "sqlite3", "os.system",
        ):
            self.assertNotIn(forbidden, sources)


if __name__ == "__main__":
    unittest.main()
