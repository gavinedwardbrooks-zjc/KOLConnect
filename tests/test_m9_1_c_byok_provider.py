from __future__ import annotations

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

from services.ai_provider import AIProviderError, UnavailableAIProvider  # noqa: E402
from services.ai_provider_configuration import (  # noqa: E402
    AI_CONFIGURATION_SCHEMA_VERSION,
    AIProviderConfigurationError,
    AIProviderConfigurationService,
)
from services.ai_secret_storage import AISecretStorage  # noqa: E402
from services.openai_compatible_ai_provider import validate_provider_base_url  # noqa: E402
from services.safe_ai_http_transport import SafePinnedHTTPSession, resolve_public_endpoint  # noqa: E402


class Provider:
    builds = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.__class__.builds.append(kwargs)

    def health_check(self, *, remote=False):
        return {"ok": True, "remote": remote, "provider": self.kwargs.get("provider_name")}


class Response:
    status = 200

    def read(self, _amount):
        return b'{"ok":true}'


class Connection:
    calls = []

    def __init__(self, hostname, port, pinned_ip, timeout, context):
        self.values = (hostname, port, pinned_ip, timeout, context)
        self.__class__.calls.append(("connect", self.values))

    def request(self, method, path, *, body, headers):
        self.__class__.calls.append(("request", method, path, body, headers))

    def getresponse(self):
        return Response()

    def close(self):
        self.__class__.calls.append(("close",))


class ByokProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        Provider.builds = []
        Connection.calls = []

    def tearDown(self):
        self.temp.cleanup()

    def storage(self, provider):
        return AISecretStorage(
            self.root / f"{provider}.secret.json",
            platform="win32",
            profile_id=provider,
            protect_bytes=lambda value: value[::-1].hex(),
            unprotect_bytes=lambda value: bytes.fromhex(value)[::-1],
        )

    def service(self):
        return AIProviderConfigurationService(
            self.root / "ai_provider.json",
            self.storage("openai"),
            secret_storage_factory=self.storage,
            provider_builders={"openai_compatible": Provider},
        )

    def test_catalog_exposes_fixed_official_presets_and_manual_custom_profile(self):
        config = self.service().client_configuration()
        catalog = {item["id"]: item for item in config["provider_catalog"]}
        self.assertEqual("https://api.openai.com/v1", catalog["openai"]["base_url"])
        self.assertEqual("https://api.deepseek.com", catalog["deepseek"]["base_url"])
        self.assertEqual("https://dashscope.aliyuncs.com/compatible-mode/v1", catalog["qwen"]["base_url"])
        self.assertTrue(catalog["custom"]["custom_endpoint"])
        self.assertEqual([], catalog["custom"]["model_suggestions"])

    def test_provider_switch_keeps_keys_and_models_isolated(self):
        service = self.service()
        service.update({"provider": "openai", "model": "gpt-test", "api_key": "openai-key", "enabled": True})
        service.update({"provider": "deepseek", "model": "deepseek-test", "api_key": "deepseek-key", "enabled": True})
        self.assertEqual("deepseek-key", self.storage("deepseek").read())
        self.assertEqual("openai-key", self.storage("openai").read())
        service.update({"provider": "openai"})
        config = service.client_configuration()
        self.assertEqual("gpt-test", config["model"])
        self.assertTrue(config["profiles"]["deepseek"]["key_configured"])
        provider = service.create_provider()
        self.assertEqual("openai-key", provider.kwargs["api_key"])
        self.assertEqual("openai", provider.kwargs["provider_name"])

    def test_clearing_one_provider_key_does_not_delete_another(self):
        service = self.service()
        service.update({"provider": "openai", "api_key": "openai-key"})
        service.update({"provider": "qwen", "api_key": "qwen-key"})
        service.update({"provider": "qwen", "clear_api_key": True})
        self.assertFalse(self.storage("qwen").is_configured())
        self.assertEqual("openai-key", self.storage("openai").read())

    def test_macos_keychain_accounts_are_namespaced_per_provider(self):
        openai = AISecretStorage(self.root / "openai.json", platform="darwin", profile_id="openai", keychain_backend=object())
        deepseek = AISecretStorage(self.root / "deepseek.json", platform="darwin", profile_id="deepseek", keychain_backend=object())
        self.assertEqual("generation-api-key", openai.keychain_account)
        self.assertEqual("generation-api-key:deepseek", deepseek.keychain_account)

    def test_saving_configuration_never_builds_or_calls_provider(self):
        service = self.service()
        service.update({"provider": "deepseek", "model": "deepseek-test", "api_key": "key", "enabled": True})
        self.assertEqual([], Provider.builds)
        self.assertTrue(service.health_check(remote=False)["ok"])
        self.assertEqual([], Provider.builds)
        self.assertTrue(service.health_check(remote=True)["ok"])
        self.assertEqual(1, len(Provider.builds))

    def test_preset_endpoint_cannot_be_overridden(self):
        with self.assertRaises(AIProviderConfigurationError):
            self.service().update({
                "provider": "deepseek", "base_url": "https://evil.example/v1", "model": "deepseek-test",
            })

    def test_custom_endpoint_offline_validation_is_strict(self):
        for url in (
            "http://ai.example.com/v1",
            "https://127.0.0.1/v1",
            "https://localhost/v1",
            "https://ai.example.com/not-compatible",
            "https://user:pass@ai.example.com/v1",
        ):
            with self.subTest(url=url), self.assertRaises(AIProviderError):
                validate_provider_base_url(url, custom_endpoint=True)
        self.assertEqual(
            "https://ai.example.com/openai/v1",
            validate_provider_base_url("https://ai.example.com/openai/v1", custom_endpoint=True),
        )

    def test_custom_profile_can_be_saved_without_dns_or_network(self):
        service = self.service()
        config = service.update({
            "provider": "custom",
            "base_url": "https://ai.example.com/openai/v1",
            "model": "model-1",
            "api_key": "custom-key",
            "enabled": True,
        })
        self.assertEqual("custom", config["provider"])
        self.assertEqual([], Provider.builds)
        saved = json.loads(service.path.read_text(encoding="utf-8"))
        self.assertEqual(AI_CONFIGURATION_SCHEMA_VERSION, saved["schema_version"])
        self.assertNotIn("custom-key", service.path.read_text(encoding="utf-8"))

    def test_dns_policy_rejects_private_or_mixed_results(self):
        def records(*addresses):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]

        with self.assertRaises(Exception):
            resolve_public_endpoint("ai.example.com", 443, resolver=lambda *_args, **_kwargs: records("127.0.0.1"))
        with self.assertRaises(Exception):
            resolve_public_endpoint(
                "ai.example.com", 443,
                resolver=lambda *_args, **_kwargs: records("93.184.216.34", "10.0.0.1"),
            )
        self.assertEqual(
            "93.184.216.34",
            resolve_public_endpoint(
                "ai.example.com", 443,
                resolver=lambda *_args, **_kwargs: records("93.184.216.34"),
            ),
        )

    def test_custom_transport_connects_to_validated_ip_with_original_tls_hostname(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        session = SafePinnedHTTPSession(
            resolver=lambda *_args, **_kwargs: records,
            connection_factory=Connection,
        )
        response = session.post(
            "https://ai.example.com/openai/v1/chat/completions",
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            json={"model": "model-1"}, timeout=10, allow_redirects=False,
        )
        self.assertEqual(200, response.status_code)
        connect = Connection.calls[0][1]
        self.assertEqual("ai.example.com", connect[0])
        self.assertEqual("93.184.216.34", connect[2])
        self.assertEqual("/openai/v1/chat/completions", Connection.calls[1][2])

    def test_custom_transport_rejects_private_dns_before_connection_or_credential_send(self):
        records = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 443))]
        session = SafePinnedHTTPSession(
            resolver=lambda *_args, **_kwargs: records,
            connection_factory=Connection,
        )
        with self.assertRaises(Exception):
            session.post(
                "https://ai.example.com/openai/v1/chat/completions",
                headers={"Authorization": "Bearer must-not-send", "Content-Type": "application/json"},
                json={"model": "model-1"}, timeout=10, allow_redirects=False,
            )
        self.assertEqual([], Connection.calls)

    def test_provider_builder_type_error_fails_closed_without_second_attempt(self):
        builds = []

        def broken_builder(**kwargs):
            builds.append(kwargs)
            raise TypeError("synthetic adapter error")

        service = AIProviderConfigurationService(
            self.root / "ai_provider.json",
            self.storage("openai"),
            secret_storage_factory=self.storage,
            provider_builders={"openai_compatible": broken_builder},
        )
        service.update({"provider": "deepseek", "model": "deepseek-test", "api_key": "key", "enabled": True})
        self.assertIsInstance(service.create_provider(), UnavailableAIProvider)
        self.assertEqual(1, len(builds))

    def test_legacy_single_profile_is_read_without_eager_mutation(self):
        path = self.root / "ai_provider.json"
        path.write_text(json.dumps({
            "provider": "openai_compatible", "base_url": "https://api.openai.com/v1",
            "model": "legacy-model", "enabled": False,
        }), encoding="utf-8")
        service = AIProviderConfigurationService(path, self.storage("openai"), secret_storage_factory=self.storage)
        self.assertEqual("openai", service.load().provider)
        self.assertEqual("legacy-model", service.load().model)
        self.assertNotIn("schema_version", json.loads(path.read_text(encoding="utf-8")))

    def test_unknown_fields_and_unsafe_model_ids_fail_closed(self):
        with self.assertRaises(AIProviderConfigurationError):
            self.service().update({"provider": "openai", "surprise": True})
        with self.assertRaises(AIProviderConfigurationError):
            self.service().update({"provider": "openai", "model": "model\nignore-system"})


if __name__ == "__main__":
    unittest.main()
