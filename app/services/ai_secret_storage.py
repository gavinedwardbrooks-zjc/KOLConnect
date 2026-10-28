from __future__ import annotations

"""Independent native secret storage for generative AI provider credentials."""

import os
import re
import sys
from pathlib import Path
from typing import Any, Callable

from runtime_paths import atomic_write_json, load_json_with_backup
from services.mail_secret_storage import (
    _KeychainBackendError,
    _get_keychain_backend,
    _protect_bytes,
    _unprotect_bytes,
)


AI_DPAPI_FORMAT = "ai-dpapi-v1"
AI_KEYCHAIN_FORMAT = "ai-keychain-v1"
AI_KEYCHAIN_SERVICE = "com.kolconnect.app.ai-provider"
AI_KEYCHAIN_ACCOUNT = "generation-api-key"


class AISecretStorageError(RuntimeError):
    """Safe storage error that never includes secret material."""


class AISecretStorage:
    def __init__(
        self,
        path: Path,
        *,
        platform: str | None = None,
        protect_bytes: Callable[[bytes], str] = _protect_bytes,
        unprotect_bytes: Callable[[str], bytes] = _unprotect_bytes,
        keychain_backend: Any | None = None,
        profile_id: str = "openai",
    ) -> None:
        self.path = Path(path)
        self.platform = platform or sys.platform
        self._protect_bytes = protect_bytes
        self._unprotect_bytes = unprotect_bytes
        self._keychain_backend = keychain_backend
        normalized_profile = str(profile_id or "openai").strip().casefold()
        if not re.fullmatch(r"[a-z0-9_-]{1,40}", normalized_profile):
            raise AISecretStorageError("AI credential profile is invalid.")
        self.profile_id = normalized_profile
        self.keychain_account = (
            AI_KEYCHAIN_ACCOUNT
            if normalized_profile == "openai"
            else f"{AI_KEYCHAIN_ACCOUNT}:{normalized_profile}"
        )

    def is_configured(
        self,
        *,
        expected_endpoint_identity: str | None = None,
        allow_legacy_unbound: bool = True,
    ) -> bool:
        envelope = self._load_envelope()
        return envelope is not None and self._binding_matches(
            envelope,
            expected_endpoint_identity,
            allow_legacy_unbound=allow_legacy_unbound,
        )

    def read(
        self,
        *,
        expected_endpoint_identity: str | None = None,
        allow_legacy_unbound: bool = True,
    ) -> str:
        envelope = self._load_envelope()
        if envelope is None:
            raise AISecretStorageError("AI provider credential is not configured.")
        if not self._binding_matches(
            envelope,
            expected_endpoint_identity,
            allow_legacy_unbound=allow_legacy_unbound,
        ):
            raise AISecretStorageError("AI provider credential endpoint binding does not match.")
        try:
            if envelope.get("format") == AI_DPAPI_FORMAT:
                if self.platform != "win32":
                    raise AISecretStorageError("Windows AI credential is unavailable on this platform.")
                return self._unprotect_bytes(str(envelope["data"])).decode("utf-8")
            if envelope.get("format") == AI_KEYCHAIN_FORMAT:
                if self.platform != "darwin":
                    raise AISecretStorageError("macOS AI credential is unavailable on this platform.")
                return self._keychain().read(
                    AI_KEYCHAIN_SERVICE,
                    self.keychain_account,
                    allow_interaction=False,
                )
        except AISecretStorageError:
            raise
        except Exception as exc:
            raise AISecretStorageError("AI provider credential could not be read securely.") from exc
        raise AISecretStorageError("AI provider credential has an invalid protected format.")

    def replace(self, secret: str, *, endpoint_identity: str | None = None) -> None:
        if not isinstance(secret, str) or not secret:
            raise AISecretStorageError("AI provider credential must be non-empty.")
        self._validate_endpoint_identity(endpoint_identity)
        previous_envelope = self._load_envelope()
        previous_secret: str | None = None
        if previous_envelope is not None:
            previous_secret = self.read()
        try:
            envelope = self._protect(secret, endpoint_identity=endpoint_identity)
            atomic_write_json(self.path, envelope)
            self._restrict_file_permissions()
        except Exception as exc:
            if self.platform == "darwin":
                self._restore_keychain(previous_secret)
            if isinstance(exc, AISecretStorageError):
                raise
            raise AISecretStorageError("AI provider credential could not be saved securely.") from exc

    def delete(self) -> None:
        envelope = self._load_envelope()
        if envelope is None:
            return
        previous_secret: str | None = None
        if envelope.get("format") == AI_KEYCHAIN_FORMAT:
            if self.platform != "darwin":
                raise AISecretStorageError("macOS AI credential is unavailable on this platform.")
            try:
                previous_secret = self.read()
                self._keychain().delete(
                    AI_KEYCHAIN_SERVICE,
                    self.keychain_account,
                    allow_interaction=False,
                )
            except _KeychainBackendError as exc:
                if exc.status != -25300:
                    raise AISecretStorageError("AI provider credential could not be deleted securely.") from exc
            except Exception as exc:
                raise AISecretStorageError("AI provider credential could not be deleted securely.") from exc
        try:
            self.path.unlink(missing_ok=True)
            self.path.with_suffix(f"{self.path.suffix}.bak").unlink(missing_ok=True)
        except OSError as exc:
            if previous_secret is not None:
                try:
                    self._keychain().store(
                        AI_KEYCHAIN_SERVICE,
                        self.keychain_account,
                        previous_secret,
                        allow_interaction=False,
                    )
                except Exception as rollback_exc:
                    raise AISecretStorageError("AI credential delete rollback failed.") from rollback_exc
            raise AISecretStorageError("AI provider credential reference could not be deleted.") from exc

    def binding_identity(self) -> str | None:
        envelope = self._load_envelope()
        if envelope is None:
            return None
        identity = envelope.get("endpoint_identity")
        return str(identity) if isinstance(identity, str) and identity else None

    def _protect(self, secret: str, *, endpoint_identity: str | None) -> dict[str, str]:
        if self.platform == "win32":
            try:
                envelope = {"format": AI_DPAPI_FORMAT, "data": self._protect_bytes(secret.encode("utf-8"))}
                if endpoint_identity is not None:
                    envelope["endpoint_identity"] = endpoint_identity
                return envelope
            except Exception as exc:
                raise AISecretStorageError("Windows AI credential protection failed.") from exc
        if self.platform == "darwin":
            try:
                self._keychain().store(
                    AI_KEYCHAIN_SERVICE,
                    self.keychain_account,
                    secret,
                    allow_interaction=False,
                )
            except Exception as exc:
                raise AISecretStorageError("macOS AI credential protection failed.") from exc
            envelope = {
                "format": AI_KEYCHAIN_FORMAT,
                "service": AI_KEYCHAIN_SERVICE,
                "account": self.keychain_account,
            }
            if endpoint_identity is not None:
                envelope["endpoint_identity"] = endpoint_identity
            return envelope
        raise AISecretStorageError("Secure AI credential storage is unavailable on this platform.")

    def _restore_keychain(self, previous_secret: str | None) -> None:
        try:
            if previous_secret is None:
                self._keychain().delete(
                    AI_KEYCHAIN_SERVICE,
                    self.keychain_account,
                    allow_interaction=False,
                )
            else:
                self._keychain().store(
                    AI_KEYCHAIN_SERVICE,
                    self.keychain_account,
                    previous_secret,
                    allow_interaction=False,
                )
        except Exception as exc:
            raise AISecretStorageError("AI credential rollback failed.") from exc

    def _load_envelope(self) -> dict[str, Any] | None:
        raw, _source = load_json_with_backup(self.path)
        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise AISecretStorageError("AI provider credential has an invalid protected format.")
        self._validate_endpoint_identity(raw.get("endpoint_identity"))
        if raw.get("format") == AI_DPAPI_FORMAT and isinstance(raw.get("data"), str) and raw["data"]:
            return raw
        if (
            raw.get("format") == AI_KEYCHAIN_FORMAT
            and raw.get("service") == AI_KEYCHAIN_SERVICE
            and raw.get("account") == self.keychain_account
        ):
            return raw
        raise AISecretStorageError("AI provider credential has an invalid protected format.")

    @staticmethod
    def _validate_endpoint_identity(value: object) -> None:
        if value is None:
            return
        if not isinstance(value, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise AISecretStorageError("AI provider credential endpoint binding is invalid.")

    @staticmethod
    def _binding_matches(
        envelope: dict[str, Any],
        expected: str | None,
        *,
        allow_legacy_unbound: bool,
    ) -> bool:
        if expected is None:
            return True
        actual = envelope.get("endpoint_identity")
        if actual is None:
            return allow_legacy_unbound
        return actual == expected

    def _keychain(self) -> Any:
        return self._keychain_backend or _get_keychain_backend()

    def _restrict_file_permissions(self) -> None:
        if self.platform != "win32":
            try:
                os.chmod(self.path, 0o600)
            except OSError as exc:
                raise AISecretStorageError("AI credential reference permissions could not be secured.") from exc
