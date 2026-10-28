from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from http_handlers import ai_provider_handler  # noqa: E402
from local_request_security import allowed_host_header, allowed_mutation_origin  # noqa: E402
from services.ai_provider_configuration import AIProviderConfigurationError  # noqa: E402


class Handler:
    def __init__(self):
        self.responses = []

    def _json(self, payload, status=200):
        self.responses.append((status, payload))

    def _api_error(self, code, message, *, status=400, **_kwargs):
        self.responses.append((status, {"ok": False, "error": {"code": code, "message": message}}))


class Service:
    def __init__(self):
        self.calls = []
        self.configuration = {
            "provider": "openai_compatible",
            "base_url": "https://api.openai.com/v1",
            "model": "model-1",
            "timeout": 30,
            "max_retries": 2,
            "enabled": True,
            "key_configured": True,
        }

    def client_configuration(self):
        self.calls.append("read")
        return dict(self.configuration)

    def update(self, payload):
        self.calls.append(("update", dict(payload)))
        return dict(self.configuration)

    def health_check(self, *, remote=False):
        self.calls.append(("health", remote))
        return {"ok": True, "status": "available" if remote else "configured", "remote": remote}


class AIProviderApiTests(unittest.TestCase):
    def context(self, service):
        return {
            "services": {"ai_provider_configuration": service},
            "logging": {"error": lambda *_args: None},
        }

    def test_get_is_redacted_and_post_requires_explicit_payload(self):
        service = Service()
        handler = Handler()
        self.assertTrue(ai_provider_handler.handle(handler, {
            "method": "GET",
            "path": "/api/settings/ai-provider",
        }, self.context(service)))
        self.assertNotIn("api_key", handler.responses[0][1]["configuration"])

        handler = Handler()
        payload = {"model": "model-2", "api_key": "transient-test-key"}
        ai_provider_handler.handle(handler, {
            "method": "POST",
            "path": "/api/settings/ai-provider",
            "get_payload": lambda: payload,
        }, self.context(service))
        self.assertEqual(("update", payload), service.calls[-1])
        self.assertNotIn("transient-test-key", repr(handler.responses))

    def test_remote_health_requires_explicit_user_request(self):
        service = Service()
        for payload in ({}, {"remote": False}):
            handler = Handler()
            ai_provider_handler.handle(handler, {
                "method": "POST",
                "path": "/api/settings/ai-provider/health",
                "get_payload": lambda payload=payload: payload,
            }, self.context(service))
            self.assertEqual(400, handler.responses[-1][0])
            self.assertNotIn(("health", True), service.calls)
        handler = Handler()
        ai_provider_handler.handle(handler, {
            "method": "POST",
            "path": "/api/settings/ai-provider/health",
            "get_payload": lambda: {"remote": True},
        }, self.context(service))
        self.assertEqual(("health", True), service.calls[-1])

    def test_endpoint_rebind_failure_uses_safe_specific_error_code(self):
        service = Service()

        def reject(_payload):
            raise AIProviderConfigurationError(
                "internal safe detail",
                code="AI_PROVIDER_ENDPOINT_KEY_REBIND_REQUIRED",
            )

        service.update = reject
        handler = Handler()
        ai_provider_handler.handle(handler, {
            "method": "POST",
            "path": "/api/settings/ai-provider",
            "get_payload": lambda: {"provider": "custom"},
        }, self.context(service))
        status, payload = handler.responses[-1]
        self.assertEqual(400, status)
        self.assertEqual("AI_PROVIDER_ENDPOINT_KEY_REBIND_REQUIRED", payload["error"]["code"])
        self.assertNotIn("internal safe detail", repr(payload))

    def test_existing_local_request_security_covers_configuration_writes(self):
        path = "/api/settings/ai-provider"
        self.assertTrue(allowed_host_header("127.0.0.1:8765", 8765))
        self.assertTrue(allowed_mutation_origin("http://localhost:8765", path, 8765))
        self.assertFalse(allowed_host_header("example.com:8765", 8765))
        self.assertFalse(allowed_mutation_origin("https://example.com", path, 8765))

    def test_foundation_does_not_expand_assistant_or_feishu_write_allowlists(self):
        assistant_router = (APP_DIR / "services" / "assistant_intent_router.py").read_text(encoding="utf-8")
        assistant_provider = (APP_DIR / "services" / "assistant_provider.py").read_text(encoding="utf-8")
        ai_provider = (APP_DIR / "services" / "ai_provider.py").read_text(encoding="utf-8")
        self.assertNotIn("AIProvider", assistant_provider)
        self.assertNotIn("ai_provider", assistant_router.casefold())
        for forbidden in ("sqlite", "subprocess", "send_mail", "full_sync", "repository"):
            self.assertNotIn(forbidden, ai_provider.casefold())


if __name__ == "__main__":
    unittest.main()
