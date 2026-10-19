from __future__ import annotations

import sys
import unittest
import gzip
import json
import socket
import ssl
import tempfile
from pathlib import Path
from unittest import mock
from urllib import error as urllib_error
from urllib import request as urllib_request

import certifi


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from feishu_client import (  # noqa: E402
    FeishuClient,
    FeishuClientError,
    build_verified_ssl_context,
    resolve_ca_bundle,
)


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
        if isinstance(self._payload, BaseException):
            raise self._payload
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


class UrlResponse:
    def __init__(self, payload, *, status=200, headers=None, raw=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def getcode(self):
        return self.status

    def read(self):
        return self.raw if self.raw is not None else json.dumps(self.payload).encode("utf-8")


class QueueUrlOpen:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, request, timeout, **kwargs):
        self.calls.append((request, timeout, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FeishuClientTests(unittest.TestCase):
    def test_packaged_macos_uses_bundled_ca_for_requests_and_urllib(self):
        ca_bundle = certifi.where()
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({}, status=400),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({"code": 0, "data": {"items": [], "has_more": False}}),
        ])
        result = FeishuClient(
            CONFIG,
            transport=transport,
            fallback_urlopen=fallback,
            packaged_macos=True,
            ca_bundle_resolver=lambda: ca_bundle,
        ).fetch_fields("creator-table")

        self.assertTrue(result.ok)
        self.assertTrue(result.used_fallback)
        self.assertTrue(all(call[2]["verify"] == ca_bundle for call in transport.calls))
        self.assertIsInstance(fallback.calls[0][2]["context"], ssl.SSLContext)
        self.assertEqual(ssl.CERT_REQUIRED, fallback.calls[0][2]["context"].verify_mode)
        self.assertTrue(fallback.calls[0][2]["context"].check_hostname)

    def test_ca_bundle_resolution_prefers_packaged_resource(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bundled = Path(temp_dir) / "certifi" / "cacert.pem"
            bundled.parent.mkdir(parents=True)
            bundled.write_text("synthetic bundle marker", encoding="utf-8")
            with mock.patch.object(sys, "_MEIPASS", temp_dir, create=True):
                self.assertEqual(str(bundled), resolve_ca_bundle())

    def test_missing_ca_bundle_fails_explicitly(self):
        missing = str(ROOT / "does-not-exist" / "cacert.pem")
        with self.assertRaises(FeishuClientError) as caught:
            FeishuClient(
                CONFIG,
                packaged_macos=True,
                ca_bundle_resolver=lambda: missing,
            )
        self.assertEqual("TLS_CONFIGURATION_ERROR", caught.exception.code)
        self.assertEqual("CA_BUNDLE_MISSING", caught.exception.transport_reason_category)
        self.assertNotIn(CONFIG["app_secret"], repr(caught.exception))

    def test_verified_ssl_context_uses_certificate_verification(self):
        context = build_verified_ssl_context(certifi.where())
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertTrue(context.check_hostname)

    def test_windows_transport_behavior_does_not_force_ca_arguments(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            OSError("primary unavailable"),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({"code": 0, "data": {"items": [], "has_more": False}}),
        ])
        result = FeishuClient(
            CONFIG,
            transport=transport,
            fallback_urlopen=fallback,
            packaged_macos=False,
        ).fetch_fields("creator-table")
        self.assertTrue(result.ok)
        self.assertTrue(all("verify" not in call[2] for call in transport.calls))
        self.assertEqual({}, fallback.calls[0][2])

    def test_default_fallback_preserves_urllib_proxy_handling(self):
        client = FeishuClient(CONFIG, packaged_macos=False)
        self.assertIs(urllib_request.urlopen, client._fallback_urlopen)

    def test_field_url_and_query_are_https_and_safely_encoded(self):
        config = dict(CONFIG, app_token="base token/[x]")
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            OSError("primary unavailable"),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({"code": 0, "data": {"items": [], "has_more": False}}),
        ])
        result = FeishuClient(
            config, transport=transport, fallback_urlopen=fallback
        ).fetch_fields("table id/[y]")
        self.assertTrue(result.ok)
        url = fallback.calls[0][0].full_url
        self.assertTrue(url.startswith("https://open.feishu.cn/open-apis/bitable/v1/apps/"))
        self.assertIn("base%20token%2F%5Bx%5D/tables/table%20id%2F%5By%5D/fields", url)
        self.assertIn("page_size=500", url)
        self.assertNotIn("[", url)
        self.assertNotIn("]", url)

    def test_urlerror_reasons_are_safely_classified(self):
        cases = (
            (
                urllib_error.URLError(
                    ssl.SSLCertVerificationError(1, "certificate secret-value")
                ),
                "CERTIFICATE_VERIFY_FAILED",
                "SSLCertVerificationError",
            ),
            (
                urllib_error.URLError(socket.gaierror(-2, "dns secret-value")),
                "DNS_FAILURE",
                "gaierror",
            ),
            (urllib_error.URLError(TimeoutError("timeout secret-value")), "TIMEOUT", "TimeoutError"),
        )
        for failure, category, reason_type in cases:
            with self.subTest(category=category):
                transport = QueueTransport([
                    Response({"code": 0, "tenant_access_token": "token"}),
                    OSError("primary unavailable"),
                ])
                result = FeishuClient(
                    CONFIG,
                    transport=transport,
                    fallback_urlopen=QueueUrlOpen([failure]),
                ).fetch_fields("creator-table")
                self.assertFalse(result.ok)
                error = result.fallback_error
                self.assertEqual(category, error.transport_reason_category)
                self.assertEqual(reason_type, error.transport_reason_type)
                self.assertNotIn("secret-value", repr(error))

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

    def test_nonzero_api_errors_preserve_code_and_use_conservative_categories(self):
        cases = (
            (1254302, "request denied", "PERMISSION_DENIED"),
            (9001, "table not found", "TABLE_NOT_FOUND"),
            (9002, "field value invalid", "INVALID_FIELD_VALUE"),
            (9003, "relation value invalid", "INVALID_RELATION_VALUE"),
            (9004, "record not exist", "RECORD_NOT_FOUND"),
            (9005, "unexpected provider failure", "REMOTE_ERROR"),
        )
        for api_code, message, expected in cases:
            with self.subTest(api_code=api_code):
                transport = QueueTransport([
                    Response({"code": 0, "tenant_access_token": "token"}),
                    Response({"code": api_code, "msg": message}),
                ])
                with self.assertRaises(FeishuClientError) as caught:
                    FeishuClient(CONFIG, transport=transport).list_records("creator-table")
                self.assertEqual(expected, caught.exception.code)
                self.assertEqual(api_code, caught.exception.api_code)
                self.assertNotIn(message, caught.exception.to_safe_dict().values())

    def test_safe_error_context_excludes_remote_payload_and_credentials(self):
        error = FeishuClientError(
            "REMOTE_ERROR", "飞书请求失败。", api_code=98765,
            failure_stage="api", http_status=200,
        ).with_operation_context(
            operation="creator_record_list",
            endpoint_category="bitable_record_list",
            table_role="creator",
        )
        safe = error.to_safe_dict()
        self.assertEqual(98765, safe["feishu_api_code"])
        self.assertEqual("creator_record_list", safe["operation"])
        self.assertEqual("bitable_record_list", safe["endpoint_category"])
        self.assertEqual("creator", safe["table_role"])
        serialized = json.dumps(safe, ensure_ascii=False)
        self.assertNotIn(CONFIG["app_secret"], serialized)
        self.assertNotIn(CONFIG["app_token"], serialized)

    def test_network_failure_is_transient_and_sanitized(self):
        transport = QueueTransport([OSError("network includes secret-value")])
        with self.assertRaises(FeishuClientError) as caught:
            FeishuClient(CONFIG, transport=transport).authenticate()
        self.assertEqual("TRANSIENT_NETWORK_ERROR", caught.exception.code)
        self.assertNotIn("secret-value", str(caught.exception))

    def test_batch_delete_uses_exact_table_and_record_ids(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({
                "code": 0,
                "data": {"records": [{"deleted": True, "record_id": "legacy-1"}]},
            }),
        ])
        deleted = FeishuClient(CONFIG, transport=transport).batch_delete(
            "creator-table", ["legacy-1"]
        )
        self.assertEqual(["legacy-1"], [item["record_id"] for item in deleted])
        self.assertIn("/creator-table/records/batch_delete", transport.calls[1][1])
        self.assertEqual({"records": ["legacy-1"]}, transport.calls[1][2]["json"])
        self.assertFalse(hasattr(FeishuClient(CONFIG, transport=transport), "delete"))

    def test_field_fetch_primary_success_does_not_use_fallback(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({"code": 0, "data": {"items": [], "has_more": False}}),
        ])
        fallback = QueueUrlOpen([])
        result = FeishuClient(
            CONFIG, transport=transport, fallback_urlopen=fallback
        ).fetch_fields("creator-table")
        self.assertTrue(result.ok)
        self.assertFalse(result.used_fallback)
        self.assertEqual((), result.fields)
        self.assertEqual([], fallback.calls)

    def test_invalid_primary_uses_read_only_paginated_fallback(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({}, status=400),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({
                "code": 0,
                "data": {
                    "items": [{
                        "field_name": "社媒账号",
                        "type": 21,
                        "property": {"table_id": "accounts", "multiple": True},
                    }],
                    "has_more": True,
                    "page_token": "next-page",
                },
            }),
            UrlResponse({
                "code": 0,
                "data": {
                    "items": [{"field_name": "达人名称", "type": 1}],
                    "has_more": False,
                },
            }),
        ])
        result = FeishuClient(
            CONFIG, transport=transport, fallback_urlopen=fallback
        ).fetch_fields("creator-table")
        self.assertTrue(result.ok)
        self.assertTrue(result.used_fallback)
        self.assertEqual("INVALID_REQUEST", result.primary_error.code)
        self.assertEqual(["社媒账号", "达人名称"], [item["field_name"] for item in result.fields])
        relation = result.fields[0]
        self.assertEqual(21, relation["type"])
        self.assertEqual("accounts", relation["property"]["table_id"])
        self.assertTrue(relation["property"]["multiple"])
        self.assertEqual(2, result.pagination_pages)
        self.assertEqual("GET", fallback.calls[0][0].method)
        self.assertIn("page_token=next-page", fallback.calls[1][0].full_url)
        self.assertEqual("KOLConnect/2.0.0", fallback.calls[0][0].get_header("User-agent"))

    def test_malformed_primary_and_fallback_return_explicit_failure(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({"code": 0, "data": {"has_more": False}}),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({"code": 0, "data": {"has_more": False}}),
        ])
        result = FeishuClient(
            CONFIG, transport=transport, fallback_urlopen=fallback
        ).fetch_fields("creator-table")
        self.assertFalse(result.ok)
        self.assertTrue(result.used_fallback)
        self.assertEqual("REMOTE_ERROR", result.primary_error.code)
        self.assertEqual("REMOTE_ERROR", result.fallback_error.code)
        diagnostic = repr(result)
        self.assertNotIn(CONFIG["app_secret"], diagnostic)
        self.assertNotIn(CONFIG["app_token"], diagnostic)

    def test_primary_transport_json_shape_and_api_failures_use_fallback(self):
        primary_failures = (
            OSError("transport secret-value"),
            Response(ValueError("invalid json secret-value")),
            Response({"code": 0, "data": {"has_more": False}}),
            Response({"code": 999, "msg": "request rejected secret-value"}),
        )
        expected_stages = ("transport", "json", "shape", "api")
        for failure, expected_stage in zip(primary_failures, expected_stages):
            with self.subTest(stage=expected_stage):
                responses = [Response({"code": 0, "tenant_access_token": "token"})]
                if isinstance(failure, Response):
                    responses.append(failure)
                else:
                    responses.append(failure)
                fallback = QueueUrlOpen([
                    UrlResponse({
                        "code": 0,
                        "data": {
                            "items": [{"field_name": "达人名称", "type": 1}],
                            "has_more": False,
                        },
                    }),
                ])
                result = FeishuClient(
                    CONFIG,
                    transport=QueueTransport(responses),
                    fallback_urlopen=fallback,
                ).fetch_fields("creator-table")
                self.assertTrue(result.ok)
                self.assertTrue(result.used_fallback)
                self.assertEqual(expected_stage, result.primary_error.failure_stage)
                self.assertEqual("达人名称", result.fields[0]["field_name"])

    def test_fallback_decodes_gzip_and_preserves_chinese_relation_metadata(self):
        payload = {
            "code": 0,
            "data": {
                "items": [{
                    "field_name": "社媒账号",
                    "type": 21,
                    "property": {"table_id": "accounts", "multiple": True},
                }],
                "has_more": False,
            },
        }
        compressed = gzip.compress(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            OSError("primary unavailable"),
        ])
        result = FeishuClient(
            CONFIG,
            transport=transport,
            fallback_urlopen=QueueUrlOpen([
                UrlResponse(None, headers={"Content-Encoding": "gzip"}, raw=compressed),
            ]),
        ).fetch_fields("creator-table")
        self.assertTrue(result.ok)
        self.assertEqual("社媒账号", result.fields[0]["field_name"])
        self.assertEqual(21, result.fields[0]["type"])
        self.assertTrue(result.fields[0]["property"]["multiple"])

    def test_repeated_page_token_fails_boundedly_then_uses_fallback(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            Response({
                "code": 0,
                "data": {"items": [], "has_more": True, "page_token": "repeat"},
            }),
            Response({
                "code": 0,
                "data": {"items": [], "has_more": True, "page_token": "repeat"},
            }),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({
                "code": 0,
                "data": {"items": [], "has_more": False},
            }),
        ])
        result = FeishuClient(
            CONFIG, transport=transport, fallback_urlopen=fallback
        ).fetch_fields("creator-table")
        self.assertTrue(result.ok)
        self.assertTrue(result.used_fallback)
        self.assertEqual("pagination", result.primary_error.failure_stage)
        self.assertEqual(2, result.primary_error.pagination_pages)
        self.assertEqual(1, result.pagination_pages)

    def test_repeated_fallback_page_token_fails_boundedly(self):
        transport = QueueTransport([
            Response({"code": 0, "tenant_access_token": "token"}),
            OSError("primary unavailable"),
        ])
        fallback = QueueUrlOpen([
            UrlResponse({
                "code": 0,
                "data": {"items": [], "has_more": True, "page_token": "repeat"},
            }),
            UrlResponse({
                "code": 0,
                "data": {"items": [], "has_more": True, "page_token": "repeat"},
            }),
        ])
        result = FeishuClient(
            CONFIG, transport=transport, fallback_urlopen=fallback
        ).fetch_fields("creator-table")
        self.assertFalse(result.ok)
        self.assertEqual("pagination", result.fallback_error.failure_stage)
        self.assertEqual(2, result.fallback_error.pagination_pages)
        self.assertEqual(2, len(fallback.calls))


if __name__ == "__main__":
    unittest.main()
