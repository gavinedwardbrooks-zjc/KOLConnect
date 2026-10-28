from __future__ import annotations

"""Versioned BYOK profiles and the single provider-construction boundary."""

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
from typing import Any, Callable, Mapping

from local_storage_lock import SharedStorageLockTimeout, shared_storage_lock
from runtime_paths import atomic_write_json, load_json_with_backup
from services.ai_provider import AIProvider, AIProviderError, UnavailableAIProvider
from services.ai_secret_storage import AISecretStorage, AISecretStorageError
from services.openai_compatible_ai_provider import OpenAICompatibleAIProvider, validate_provider_base_url


AI_CONFIGURATION_SCHEMA_VERSION = "m9.1-d-profiles-v2"
LEGACY_PROFILE_SCHEMA_VERSION = "m9.1-c-profiles-v1"
DEFAULT_PROVIDER = "openai"
PROVIDER_ALIASES = {"openai_compatible": "openai"}
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI", "base_url": "https://api.openai.com/v1",
        "model_suggestions": ["gpt-4.1-mini", "gpt-4.1"], "custom_endpoint": False,
    },
    "deepseek": {
        "label": "DeepSeek", "base_url": "https://api.deepseek.com",
        "model_suggestions": ["deepseek-flash", "deepseek-v4-pro"], "custom_endpoint": False,
    },
    "qwen": {
        "label": "阿里云百炼 / 通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model_suggestions": ["qwen-plus", "qwen-max"], "custom_endpoint": False,
    },
    "custom": {
        "label": "自定义 OpenAI-compatible", "base_url": "",
        "model_suggestions": [], "custom_endpoint": True,
    },
}


@dataclass(frozen=True)
class AIProviderConfiguration:
    provider: str = DEFAULT_PROVIDER
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    timeout: float = 30.0
    max_retries: int = 2
    enabled: bool = False
    custom_endpoint: bool = False
    endpoint_identity: str = ""


class AIProviderConfigurationError(ValueError):
    def __init__(self, message: str, *, code: str = "AI_PROVIDER_CONFIGURATION_INVALID") -> None:
        super().__init__(message)
        self.code = code


def endpoint_identity(base_url: str) -> str:
    """Return a non-secret identity for one canonical provider endpoint."""
    if not base_url:
        return ""
    return f"sha256:{hashlib.sha256(base_url.encode('utf-8')).hexdigest()}"


class AIProviderConfigurationService:
    def __init__(
        self,
        path: Path,
        secret_storage: AISecretStorage,
        *,
        secret_storage_factory: Callable[[str], AISecretStorage] | None = None,
        provider_builders: Mapping[str, Callable[..., AIProvider]] | None = None,
        observer: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.path = Path(path)
        self.secret_storage = secret_storage
        self._secret_storage_factory = secret_storage_factory
        self._builders = dict(provider_builders or {"openai_compatible": OpenAICompatibleAIProvider})
        self._observer = observer or (lambda _event: None)

    def load(self) -> AIProviderConfiguration:
        try:
            with shared_storage_lock():
                return self._load_locked()
        except SharedStorageLockTimeout as exc:
            raise AIProviderConfigurationError("AI provider configuration is temporarily unavailable.") from exc

    def client_configuration(self) -> dict[str, Any]:
        try:
            with shared_storage_lock():
                return self._client_configuration_locked()
        except SharedStorageLockTimeout as exc:
            raise AIProviderConfigurationError("AI provider configuration is temporarily unavailable.") from exc

    def update(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise AIProviderConfigurationError("AI provider configuration payload must be an object.")
        allowed = {"provider", "base_url", "model", "timeout", "max_retries", "enabled", "api_key", "clear_api_key"}
        if set(payload) - allowed:
            raise AIProviderConfigurationError("AI provider configuration contains unsupported fields.")
        try:
            with shared_storage_lock():
                return self._update_locked(payload)
        except SharedStorageLockTimeout as exc:
            raise AIProviderConfigurationError("AI provider configuration is temporarily unavailable.") from exc

    def _update_locked(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        document = self._load_document()
        profiles = dict(document.get("profiles") or {})
        current_provider = self._provider_id(document.get("selected_provider") or DEFAULT_PROVIDER)
        provider_id = self._provider_id(payload.get("provider") or current_provider)
        current_profile = dict(profiles.get(provider_id) or {})
        config_fields = {
            key: payload[key]
            for key in ("base_url", "model", "timeout", "max_retries", "enabled")
            if key in payload
        }
        desired_profile = {"provider": provider_id, **current_profile, **config_fields}
        if "base_url" in payload:
            desired_profile.pop("endpoint_identity", None)
        current = self._normalize({"provider": provider_id, **current_profile})
        updated = self._normalize(desired_profile)
        api_key_supplied = "api_key" in payload
        clear_api_key = payload.get("clear_api_key") is True
        if api_key_supplied and clear_api_key:
            raise AIProviderConfigurationError("AI provider credential update is ambiguous.")
        api_key = payload.get("api_key")
        if api_key_supplied and (not isinstance(api_key, str) or not api_key.strip() or len(api_key) > 4096):
            raise AIProviderConfigurationError("AI provider credential must be non-empty.")
        if (
            updated.custom_endpoint
            and current.base_url
            and current.endpoint_identity != updated.endpoint_identity
            and not api_key_supplied
        ):
            raise AIProviderConfigurationError(
                "A new API Key must be explicitly bound to the changed custom endpoint.",
                code="AI_PROVIDER_ENDPOINT_KEY_REBIND_REQUIRED",
            )

        storage = self._storage(provider_id)
        old_secret = storage.read() if storage.is_configured() else None
        old_binding = storage.binding_identity()
        secret_changed = api_key_supplied or clear_api_key
        profiles[provider_id] = {
            key: value for key, value in asdict(updated).items() if key not in {"provider", "custom_endpoint"}
        }
        next_document = {
            "schema_version": AI_CONFIGURATION_SCHEMA_VERSION,
            "selected_provider": provider_id,
            "profiles": profiles,
        }
        try:
            if api_key_supplied:
                storage.replace(str(api_key).strip(), endpoint_identity=updated.endpoint_identity)
            elif clear_api_key:
                storage.delete()
            atomic_write_json(self.path, next_document)
        except Exception as exc:
            if secret_changed:
                try:
                    if old_secret is None:
                        storage.delete()
                    else:
                        storage.replace(old_secret, endpoint_identity=old_binding)
                except AISecretStorageError as rollback_exc:
                    raise AIProviderConfigurationError("AI provider configuration rollback failed.") from rollback_exc
            if isinstance(exc, (AIProviderConfigurationError, AISecretStorageError)):
                raise
            raise AIProviderConfigurationError("AI provider configuration could not be saved.") from exc
        return self._client_configuration_locked()

    def create_provider(self) -> AIProvider:
        try:
            with shared_storage_lock():
                config = self._load_locked()
                storage = self._storage(config.provider)
                if not config.enabled:
                    return UnavailableAIProvider(reason="disabled", disabled=True)
                allow_legacy = not config.custom_endpoint
                if (
                    not config.model
                    or not config.base_url
                    or not storage.is_configured(
                        expected_endpoint_identity=config.endpoint_identity,
                        allow_legacy_unbound=allow_legacy,
                    )
                ):
                    return UnavailableAIProvider(reason="configuration_incomplete")
                builder = self._builders.get(config.provider) or self._builders.get("openai_compatible")
                if builder is None:
                    return UnavailableAIProvider(reason="unavailable")
                arguments = {
                    "api_key": storage.read(
                        expected_endpoint_identity=config.endpoint_identity,
                        allow_legacy_unbound=allow_legacy,
                    ),
                    "base_url": config.base_url, "model": config.model,
                    "timeout": config.timeout, "max_retries": config.max_retries, "observer": self._observer,
                    "custom_endpoint": config.custom_endpoint, "provider_name": config.provider,
                }
                return builder(**arguments)
        except (AISecretStorageError, AIProviderError, AIProviderConfigurationError, SharedStorageLockTimeout, TypeError):
            return UnavailableAIProvider(reason="unavailable")

    def health_check(self, *, remote: bool = False) -> dict[str, Any]:
        config = self.client_configuration()
        if not remote:
            if not config["enabled"]:
                return {"ok": False, "status": "disabled", "remote": False, "provider": config["provider"]}
            missing = [key for key in ("model", "base_url") if not config[key]]
            if not config["key_configured"]:
                missing.append("api_key")
            return {
                "ok": not missing,
                "status": "configured" if not missing else "configuration_incomplete",
                "remote": False, "provider": config["provider"], "missing": missing,
            }
        provider = self.create_provider()
        return provider.health_check(remote=True)

    def _load_document(self) -> dict[str, Any]:
        raw, _source = load_json_with_backup(self.path)
        if raw is None:
            return {"schema_version": AI_CONFIGURATION_SCHEMA_VERSION, "selected_provider": DEFAULT_PROVIDER, "profiles": {}}
        if not isinstance(raw, dict):
            raise AIProviderConfigurationError("AI provider configuration is invalid.")
        if raw.get("schema_version") in {AI_CONFIGURATION_SCHEMA_VERSION, LEGACY_PROFILE_SCHEMA_VERSION}:
            if not isinstance(raw.get("profiles"), dict):
                raise AIProviderConfigurationError("AI provider profiles are invalid.")
            return raw
        legacy_provider = self._provider_id(raw.get("provider") or DEFAULT_PROVIDER)
        legacy = {key: raw[key] for key in ("base_url", "model", "timeout", "max_retries", "enabled") if key in raw}
        return {
            "schema_version": AI_CONFIGURATION_SCHEMA_VERSION,
            "selected_provider": legacy_provider,
            "profiles": {legacy_provider: legacy},
        }

    def _normalize(self, raw: Mapping[str, Any]) -> AIProviderConfiguration:
        provider = self._provider_id(raw.get("provider") or DEFAULT_PROVIDER)
        preset = PROVIDER_PRESETS[provider]
        configured_url = str(raw.get("base_url") or preset["base_url"]).strip()
        if not preset["custom_endpoint"] and configured_url.rstrip("/") != str(preset["base_url"]).rstrip("/"):
            raise AIProviderConfigurationError("Preset AI provider endpoint cannot be changed.")
        if preset["custom_endpoint"] and not configured_url:
            base_url = ""
        else:
            try:
                base_url = validate_provider_base_url(configured_url, custom_endpoint=bool(preset["custom_endpoint"]))
            except AIProviderError as exc:
                raise AIProviderConfigurationError(str(exc)) from exc
        model = str(raw.get("model") or "").strip()
        if model and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", model):
            raise AIProviderConfigurationError("AI provider model ID is invalid.")
        try:
            timeout = float(raw.get("timeout", 30.0))
            max_retries = int(raw.get("max_retries", 2))
        except (TypeError, ValueError) as exc:
            raise AIProviderConfigurationError("AI provider retry configuration is invalid.") from exc
        if not 1 <= timeout <= 120 or not 0 <= max_retries <= 3:
            raise AIProviderConfigurationError("AI provider retry configuration is invalid.")
        return AIProviderConfiguration(
            provider=provider, base_url=base_url, model=model, timeout=timeout,
            max_retries=max_retries, enabled=bool(raw.get("enabled")),
            custom_endpoint=bool(preset["custom_endpoint"]),
            endpoint_identity=self._validated_identity(raw.get("endpoint_identity"), base_url),
        )

    def _load_locked(self) -> AIProviderConfiguration:
        document = self._load_document()
        selected = self._provider_id(document.get("selected_provider") or DEFAULT_PROVIDER)
        profiles = document.get("profiles") if isinstance(document.get("profiles"), dict) else {}
        return self._normalize({"provider": selected, **dict(profiles.get(selected) or {})})

    def _client_configuration_locked(self) -> dict[str, Any]:
        config = self._load_locked()
        document = self._load_document()
        profiles = document.get("profiles") if isinstance(document.get("profiles"), dict) else {}
        profile_states = {}
        for provider_id in PROVIDER_PRESETS:
            profile = self._normalize({"provider": provider_id, **dict(profiles.get(provider_id) or {})})
            state = asdict(profile)
            state.pop("endpoint_identity", None)
            state["key_configured"] = self._storage(provider_id).is_configured(
                expected_endpoint_identity=profile.endpoint_identity,
                allow_legacy_unbound=not profile.custom_endpoint,
            )
            profile_states[provider_id] = state
        selected_state = asdict(config)
        selected_state.pop("endpoint_identity", None)
        return {
            **selected_state,
            "schema_version": AI_CONFIGURATION_SCHEMA_VERSION,
            "key_configured": profile_states[config.provider]["key_configured"],
            "profiles": profile_states,
            "provider_catalog": [
                {
                    "id": provider_id, "label": preset["label"], "base_url": preset["base_url"],
                    "custom_endpoint": preset["custom_endpoint"],
                    "model_suggestions": list(preset["model_suggestions"]),
                }
                for provider_id, preset in PROVIDER_PRESETS.items()
            ],
        }

    @staticmethod
    def _validated_identity(stored: object, base_url: str) -> str:
        computed = endpoint_identity(base_url)
        if stored in (None, ""):
            return computed
        if not isinstance(stored, str) or stored != computed:
            raise AIProviderConfigurationError("AI provider endpoint identity is invalid.")
        return stored

    @staticmethod
    def _provider_id(value: object) -> str:
        provider = str(value or DEFAULT_PROVIDER).strip().casefold()
        provider = PROVIDER_ALIASES.get(provider, provider)
        if provider not in PROVIDER_PRESETS:
            raise AIProviderConfigurationError("AI provider is not supported.")
        return provider

    def _storage(self, provider_id: str) -> AISecretStorage:
        if self._secret_storage_factory is not None:
            return self._secret_storage_factory(provider_id)
        return self.secret_storage
