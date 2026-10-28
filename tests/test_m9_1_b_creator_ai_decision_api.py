from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from http_handlers import creator_handler  # noqa: E402


class Handler:
    def __init__(self):
        self.responses = []

    def _json(self, payload, status=200):
        self.responses.append((status, payload))

    def _api_error(self, code, message, *, status=400, **_kwargs):
        self.responses.append((status, {"ok": False, "error": {"code": code, "message": message}}))

    def _error(self, message, status=400):
        self.responses.append((status, {"ok": False, "error": message}))

    def _repository_error(self, exc):
        self._error(str(exc), 500)


class DecisionService:
    def __init__(self):
        self.preview_calls = []
        self.generate_calls = []

    def get_capability_and_facts(self, creator_id):
        self.preview_calls.append(creator_id)
        return {"mode": "deterministic_preview", "status": "ready", "decision": None}

    def generate_decision(self, creator_id, *, trace_id, decision_context=None):
        self.generate_calls.append((creator_id, trace_id, decision_context))
        return {
            "mode": "ai",
            "status": "success",
            "trace_id": trace_id,
            "decision": {"recommendation": "consider"},
        }


class CreatorAIDecisionApiTests(unittest.TestCase):
    def context(self, service):
        return {
            "request": {"trace_id": "trace_context"},
            "services": {
                "creator": object(),
                "agency": object(),
                "creator_delete_impact": object(),
                "creator_hard_delete": object(),
                "creator_ai_decision": service,
            },
            "config": {"legacy_cooperation_pattern": re.compile(r"$^")},
        }

    def test_get_is_read_only_and_post_is_the_only_generation_trigger(self):
        service = DecisionService()
        handler = Handler()
        self.assertTrue(creator_handler.handle(handler, {
            "method": "GET",
            "path": "/api/creator-library/creator_one/ai-decision",
            "query": {},
        }, self.context(service)))
        self.assertEqual(["creator_one"], service.preview_calls)
        self.assertEqual([], service.generate_calls)
        self.assertEqual(200, handler.responses[0][0])

        handler = Handler()
        creator_handler.handle(handler, {
            "method": "POST",
            "path": "/api/creator-library/creator_one/ai-decision",
            "query": {},
            "trace_id": "trace_post",
            "get_payload": lambda: {"decision_context": {"objective": "awareness"}},
        }, self.context(service))
        self.assertEqual([("creator_one", "trace_post", {"objective": "awareness"})], service.generate_calls)
        self.assertEqual(200, handler.responses[0][0])

    def test_post_rejects_unknown_request_fields_before_generation(self):
        service = DecisionService()
        handler = Handler()
        creator_handler.handle(handler, {
            "method": "POST",
            "path": "/api/creator-library/creator_one/ai-decision",
            "query": {},
            "get_payload": lambda: {"auto_send": True},
        }, self.context(service))
        self.assertEqual([], service.generate_calls)
        self.assertEqual(400, handler.responses[0][0])
        self.assertEqual("INVALID_AI_DECISION_REQUEST", handler.responses[0][1]["error"]["code"])

    def test_provider_error_keeps_fallback_payload_and_safe_error_code(self):
        class FailedService(DecisionService):
            def generate_decision(self, creator_id, *, trace_id, decision_context=None):
                return {
                    "mode": "deterministic_fallback",
                    "status": "provider_error",
                    "provider_error": {"code": "AI_PROVIDER_TIMEOUT", "retryable": True},
                    "decision": None,
                    "deterministic": {"data_status": "partial"},
                }

        handler = Handler()
        creator_handler.handle(handler, {
            "method": "POST",
            "path": "/api/creator-library/creator_one/ai-decision",
            "query": {},
            "trace_id": "trace_post",
            "get_payload": lambda: {},
        }, self.context(FailedService()))
        self.assertEqual(503, handler.responses[0][0])
        self.assertEqual("AI_PROVIDER_TIMEOUT", handler.responses[0][1]["error"]["code"])
        self.assertEqual("partial", handler.responses[0][1]["deterministic"]["data_status"])


if __name__ == "__main__":
    unittest.main()
