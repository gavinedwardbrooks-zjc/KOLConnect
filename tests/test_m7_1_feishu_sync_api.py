from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from http_handlers import feishu_sync_handler  # noqa: E402
from local_request_security import allowed_host_header, allowed_mutation_origin  # noqa: E402


class Handler:
    def __init__(self):
        self.responses = []

    def _json(self, payload, status=200):
        self.responses.append((status, payload))

    def _error(self, message, status=400):
        self.responses.append((status, {"ok": False, "error": message}))


class Service:
    def __init__(self):
        self.calls = []

    def validate_connection(self):
        self.calls.append("validate")
        return {"status": "success", "connection_ok": True}

    def dry_run(self):
        self.calls.append("dry-run")
        return {"status": "success", "creator_create_count": 1}

    def full_sync(self, *, confirm):
        self.calls.append(("full-sync", confirm))
        if confirm is not True:
            raise ValueError("FEISHU_SYNC_CONFIRMATION_REQUIRED")
        return {"status": "success", "creator_created": 1}


class FeishuSyncApiTests(unittest.TestCase):
    def context(self, service):
        return {
            "services": {"feishu_sync": service},
            "logging": {"error": lambda *_args: None},
        }

    def test_validate_dry_run_and_confirmed_full_sync_routes(self):
        service = Service()
        for path, payload in (
            ("/api/feishu-sync/validate", {}),
            ("/api/feishu-sync/dry-run", {}),
            ("/api/feishu-sync/full-sync", {"confirm": True}),
        ):
            handler = Handler()
            request = {
                "method": "POST",
                "path": path,
                "get_payload": lambda payload=payload: payload,
            }
            self.assertTrue(feishu_sync_handler.handle(handler, request, self.context(service)))
            self.assertEqual(200, handler.responses[0][0])
            self.assertTrue(handler.responses[0][1]["ok"])
        self.assertEqual(["validate", "dry-run", ("full-sync", True)], service.calls)

    def test_full_sync_without_confirmation_is_blocked(self):
        handler = Handler()
        request = {
            "method": "POST",
            "path": "/api/feishu-sync/full-sync",
            "get_payload": lambda: {},
        }
        feishu_sync_handler.handle(handler, request, self.context(Service()))
        self.assertEqual(400, handler.responses[0][0])
        self.assertEqual(
            "FEISHU_SYNC_CONFIRMATION_REQUIRED",
            handler.responses[0][1]["error"]["code"],
        )
        self.assertEqual(
            "FEISHU_SYNC_CONFIRMATION_REQUIRED",
            handler.responses[0][1]["legacy_error"],
        )

    def test_existing_local_host_and_origin_security_applies(self):
        path = "/api/feishu-sync/full-sync"
        self.assertTrue(allowed_host_header("127.0.0.1:8765", 8765))
        self.assertTrue(allowed_mutation_origin("http://localhost:8765", path, 8765))
        self.assertFalse(allowed_host_header("example.com:8765", 8765))
        self.assertFalse(allowed_mutation_origin("https://example.com", path, 8765))

    def test_no_lifecycle_or_hard_delete_hook_was_added(self):
        for relative in (
            "services/creator_service.py",
            "services/creator_hard_delete_service.py",
            "repositories/creator_hard_delete_repository.py",
            "staged_delete_transaction.py",
        ):
            source = (APP_DIR / relative).read_text(encoding="utf-8-sig")
            self.assertNotIn("feishu_sync", source.casefold(), relative)


if __name__ == "__main__":
    unittest.main()
