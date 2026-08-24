from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import FeishuClient, FeishuClientError  # noqa: E402


CONFIG = {
    "app_id": "app-id",
    "app_secret": "secret-value",
    "app_token": "base-token",
    "creator_table_id": "creator-table",
    "account_table_id": "account-table",
}


class Response:
    def __init__(self, payload, *, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return self._payload


class QueueTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FeishuClientTests(unittest.TestCase):
    def test_token_success_and_secret_is_only_in_auth_request(self):
        transport = QueueTransport([Response({"code": 0, "tenant_access_token": "token"})])
        client = FeishuClient(CONFIG, transport=transport)
        client.authenticate()
        self.assertEqual("secret-value", transport.calls[0][2]["json"]["app_secret"])
        self.assertNotIn("secret-value", repr(client.__dict__.get("_access_token")))

    def test_token_failure_is_sanitized(self):
        transport = QueueTransport([Response({"code": 100, "msg": "bad app_secret secret-value"})])
        with self.assertRaises(FeishuClientError) as caught:
            FeishuClient(CONFIG, transport=transport).authenticate()
        self.assertEqual("REMOTE_ERROR", caught.exception.code)
        self.assertNotIn("secret-value", str(caught.exception))

    def test_pagination_reads_all_pages(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({"code": 0, "data": {"items": [{"record_id": "1"}], "has_more": True, "page_token": "next"}}),
            Response({"code": 0, "data": {"items": [{"record_id": "2"}], "has_more": False}}),
        ])
        records = FeishuClient(CONFIG, transport=transport).list_records("creator-table")
        self.assertEqual(["1", "2"], [item["record_id"] for item in records])
        self.assertEqual("next", transport.calls[2][2]["params"]["page_token"])

    def test_batch_create_and_update(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({"code": 0, "data": {"records": [{"record_id": "new"}]}}),
            Response({"code": 0, "data": {"records": [{"record_id": "new"}]}}),
        ])
        client = FeishuClient(CONFIG, transport=transport)
        self.assertEqual("new", client.batch_create("creator-table", [{"ID": "one"}])[0]["record_id"])
        client.batch_update("creator-table", [{"record_id": "new", "fields": {"ID": "one"}}])
        self.assertIn("batch_create", transport.calls[1][1])
        self.assertIn("batch_update", transport.calls[2][1])

    def test_permission_and_rate_limit_are_classified(self):
        for response, expected in (
            (Response({}, status=403), "PERMISSION_DENIED"),
            (Response({}, status=429, headers={"Retry-After": "2"}), "RATE_LIMITED"),
        ):
            with self.subTest(expected=expected):
                transport = QueueTransport([
                    Response({"code": 0, "tenant_access_token": "token"}), response,
                ])
                with self.assertRaises(FeishuClientError) as caught:
                    FeishuClient(CONFIG, transport=transport).list_records("creator-table")
                self.assertEqual(expected, caught.exception.code)
                if expected == "RATE_LIMITED":
                    self.assertEqual("2", caught.exception.retry_after)

    def test_network_failure_is_transient_and_sanitized(self):
        transport = QueueTransport([OSError("network includes secret-value")])
        with self.assertRaises(FeishuClientError) as caught:
            FeishuClient(CONFIG, transport=transport).authenticate()
        self.assertEqual("TRANSIENT_NETWORK_ERROR", caught.exception.code)
        self.assertNotIn("secret-value", str(caught.exception))

    def test_no_remote_delete_capability_exists(self):
        client = FeishuClient(CONFIG, transport=QueueTransport([]))
        self.assertFalse(hasattr(client, "delete"))
        self.assertFalse(hasattr(client, "batch_delete"))


if __name__ == "__main__":
    unittest.main()
