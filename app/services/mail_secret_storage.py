"""Platform-native protection for persisted mail account secrets.

``settings.json`` contains an opaque DPAPI blob on Windows or a Keychain
reference on macOS. Plaintext is accepted only while a new setting is being
saved, or at the immediate IMAP/SMTP authentication boundary.
"""

from __future__ import annotations

import base64
import copy
import ctypes
import hashlib
import json
import sys
from ctypes import wintypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from runtime_paths import atomic_write_json, load_json_with_backup


DPAPI_SECRET_FORMAT = "dpapi-v1"
KEYCHAIN_SECRET_FORMAT = "keychain-v1"
SECRET_FORMAT = DPAPI_SECRET_FORMAT  # Existing Windows import compatibility.
KEYCHAIN_SERVICE = "com.kolconnect.app.mail"


class MailSecretProtectionError(RuntimeError):
    """A safe error that never includes the protected or plaintext value."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


class _KeychainBackendError(RuntimeError):
    def __init__(self, operation: str, status: int) -> None:
        self.operation = operation
        self.status = status
        super().__init__(f"Keychain {operation} failed ({status}).")


def _current_platform() -> str:
    """Keep platform selection local so test doubles cannot affect stdlib imports."""
    return sys.platform


def uses_macos_keychain() -> bool:
    """Expose the active native-secret path without leaking platform details to callers."""
    return _current_platform() == "darwin"


def is_protected_mail_secret(value: object) -> bool:
    """Recognize only known versioned protected-secret envelopes."""
    if not isinstance(value, dict):
        return False
    if value.get("format") == DPAPI_SECRET_FORMAT:
        return isinstance(value.get("data"), str) and bool(value["data"])
    if value.get("format") == KEYCHAIN_SECRET_FORMAT:
        return (
            value.get("service") == KEYCHAIN_SERVICE
            and isinstance(value.get("account"), str)
            and bool(value["account"])
        )
    return False


def _keychain_account_identity(account: dict[str, Any] | None) -> str:
    """Derive a non-display-name identifier for one configured mailbox."""
    if not isinstance(account, dict):
        raise MailSecretProtectionError("A mail account identity is required for Keychain storage.")
    parts = (
        str(account.get("email") or "").strip().lower(),
        str(account.get("username") or "").strip().lower(),
        str(account.get("imap_host") or "").strip().lower(),
        str(account.get("imap_port") or "").strip(),
    )
    if not any(parts):
        raise MailSecretProtectionError("A mail account identity is required for Keychain storage.")
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return f"mail-{digest}"


def protect_mail_secret(value: str, *, account: dict[str, Any] | None = None) -> dict[str, str]:
    """Protect a non-empty secret with the active platform-native backend."""
    if not isinstance(value, str) or not value:
        raise MailSecretProtectionError("Mail secret protection requires a non-empty value.")
    if _current_platform() == "win32":
        try:
            return {"format": DPAPI_SECRET_FORMAT, "data": _protect_bytes(value.encode("utf-8"))}
        except MailSecretProtectionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive native boundary
            raise MailSecretProtectionError("Windows mail secret protection failed.") from exc
    if _current_platform() == "darwin":
        keychain_account = _keychain_account_identity(account)
        try:
            _get_keychain_backend().store(KEYCHAIN_SERVICE, keychain_account, value)
            return {"format": KEYCHAIN_SECRET_FORMAT, "service": KEYCHAIN_SERVICE, "account": keychain_account}
        except _KeychainBackendError as exc:
            raise _keychain_error(exc) from exc
        except MailSecretProtectionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive native boundary
            raise MailSecretProtectionError("macOS Keychain mail secret protection failed.") from exc
    raise MailSecretProtectionError("Mail secret protection is unavailable on this platform.")


def unprotect_mail_secret(value: object, *, allow_transient_plaintext: bool = False) -> str:
    """Return plaintext only at the local IMAP/SMTP authentication boundary."""
    if value in (None, ""):
        return ""
    if not is_protected_mail_secret(value):
        if isinstance(value, str) and allow_transient_plaintext:
            return value
        if isinstance(value, str):
            raise MailSecretProtectionError("Stored mail secret is not protected.")
        raise MailSecretProtectionError("Mail secret is unavailable or has an invalid format.")
    if value["format"] == DPAPI_SECRET_FORMAT:
        if _current_platform() != "win32":
            raise MailSecretProtectionError("The stored Windows mail secret is unavailable on this platform.")
        try:
            return _unprotect_bytes(value["data"]).decode("utf-8")
        except MailSecretProtectionError:
            raise
        except Exception as exc:  # pragma: no cover - defensive native boundary
            raise MailSecretProtectionError("Windows mail secret could not be unprotected.") from exc
    if value["format"] == KEYCHAIN_SECRET_FORMAT:
        if _current_platform() != "darwin":
            raise MailSecretProtectionError("The stored macOS Keychain mail secret is unavailable on this platform.")
        try:
            return _get_keychain_backend().read(value["service"], value["account"])
        except _KeychainBackendError as exc:
            raise _keychain_error(exc) from exc
        except Exception as exc:  # pragma: no cover - defensive native boundary
            raise MailSecretProtectionError("macOS Keychain mail secret could not be read.") from exc
    raise MailSecretProtectionError("Mail secret is unavailable or has an invalid format.")


def protect_mail_state_for_storage(state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Copy state and replace only plaintext mail passwords with protected values."""
    protected = copy.deepcopy(state)
    changed = False
    mail = protected.get("mail") if isinstance(protected.get("mail"), dict) else {}
    accounts = mail.get("accounts") if isinstance(mail.get("accounts"), list) else []
    for account in accounts:
        if not isinstance(account, dict):
            continue
        password = account.get("password")
        if password in (None, "") or is_protected_mail_secret(password):
            continue
        if not isinstance(password, str):
            raise MailSecretProtectionError("Mail secret has an invalid format.")
        account["password"] = protect_mail_secret(password, account=account)
        changed = True
    return protected, changed


def normalize_pending_secret_cleanup(raw: object) -> list[dict[str, str]]:
    """Keep only non-secret, versioned Keychain references for later cleanup."""
    values = raw if isinstance(raw, list) else []
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        reference = _keychain_reference_from_value(item)
        if reference is None or reference in seen:
            continue
        seen.add(reference)
        normalized.append(_keychain_reference_payload(*reference))
    return normalized


def _keychain_reference_from_value(value: object) -> tuple[str, str] | None:
    if not isinstance(value, dict) or value.get("format") != KEYCHAIN_SECRET_FORMAT:
        return None
    service = value.get("service")
    account = value.get("account")
    if service != KEYCHAIN_SERVICE or not isinstance(account, str) or not account:
        return None
    return service, account


def _keychain_reference_payload(service: str, account: str) -> dict[str, str]:
    return {"format": KEYCHAIN_SECRET_FORMAT, "service": service, "account": account}


def _keychain_reference_for_account(account: dict[str, Any]) -> tuple[str, str]:
    return KEYCHAIN_SERVICE, _keychain_account_identity(account)


def _staged_keychain_reference_for_account(account: dict[str, Any]) -> tuple[str, str]:
    """Allocate a new physical item so a settings failure never overwrites the active item."""
    _service, logical_account = _keychain_reference_for_account(account)
    return KEYCHAIN_SERVICE, f"{logical_account}-{uuid4().hex}"


def mail_secret_recovery_path(settings_path: Path) -> Path:
    """Store non-secret compensation work beside the settings file, never in SQLite."""
    return settings_path.with_name(f"{settings_path.stem}.mail-secret-recovery.json")


def _read_keychain_secret_if_present(service: str, account: str) -> str | None:
    try:
        return _get_keychain_backend().read(service, account)
    except _KeychainBackendError as exc:
        if exc.status == -25300:
            return None
        raise _keychain_error(exc) from exc
    except Exception as exc:  # pragma: no cover - defensive native boundary
        raise MailSecretProtectionError("macOS Keychain mail secret could not be read.") from exc


def _delete_keychain_reference(service: str, account: str) -> bool:
    """Delete one reference; a missing item is already clean."""
    try:
        _get_keychain_backend().delete(service, account)
        return True
    except _KeychainBackendError as exc:
        if exc.status == -25300:
            return True
        return False
    except Exception:
        return False


@dataclass
class _KeychainWriteRollback:
    service: str
    account: str
    previous_secret: str | None


@dataclass
class MailSecretStateTransition:
    """In-memory compensation for Keychain writes before settings persistence."""

    protected_state: dict[str, Any]
    rollback_writes: list[_KeychainWriteRollback] = field(default_factory=list)
    pending_cleanup: set[tuple[str, str]] = field(default_factory=set)

    def rollback(self) -> list[dict[str, str]]:
        """Return every compensation reference that could not be restored or removed."""
        failed: list[dict[str, str]] = []
        for write in reversed(self.rollback_writes):
            if write.previous_secret is None:
                if not _delete_keychain_reference(write.service, write.account):
                    failed.append(_keychain_reference_payload(write.service, write.account))
                continue
            try:
                _get_keychain_backend().store(write.service, write.account, write.previous_secret)
            except Exception:
                failed.append(_keychain_reference_payload(write.service, write.account))
        return failed

    def finish_cleanup(self) -> bool:
        """Try post-commit deletion and retain only references that need another attempt."""
        remaining = {
            reference for reference in self.pending_cleanup
            if not _delete_keychain_reference(*reference)
        }
        self.pending_cleanup = remaining
        mail = self.protected_state.get("mail")
        if isinstance(mail, dict):
            if remaining:
                mail["pending_secret_cleanup"] = [
                    _keychain_reference_payload(*reference) for reference in sorted(remaining)
                ]
            else:
                mail.pop("pending_secret_cleanup", None)
        return not remaining


def prepare_macos_mail_secret_transition(
    state: dict[str, Any], previous_mail: dict[str, Any] | None = None
) -> MailSecretStateTransition:
    """Stage Keychain changes so settings persistence can safely commit or compensate them.

    Obsolete references are written as non-secret pending cleanup metadata *before*
    the settings write. A failed write can therefore restore the old Keychain state,
    while a later cleanup failure remains recoverable after a successful write.
    """
    if not uses_macos_keychain():
        protected, _changed = protect_mail_state_for_storage(state)
        return MailSecretStateTransition(protected)

    protected = copy.deepcopy(state)
    mail = protected.get("mail") if isinstance(protected.get("mail"), dict) else {}
    accounts = mail.get("accounts") if isinstance(mail.get("accounts"), list) else []
    transition = MailSecretStateTransition(protected)

    for account in accounts:
        if not isinstance(account, dict):
            continue
        password = account.get("password")
        existing_reference = _keychain_reference_from_value(password)
        previous_account = _account_with_keychain_reference(previous_mail, existing_reference)
        identity_changed = (
            previous_account is not None
            and _keychain_account_identity(previous_account) != _keychain_account_identity(account)
        )
        if existing_reference is not None and identity_changed:
            secret = unprotect_mail_secret(password)
            staged_reference = _staged_keychain_reference_for_account(account)
            _get_keychain_backend().store(*staged_reference, secret)
            transition.rollback_writes.append(_KeychainWriteRollback(*staged_reference, None))
            account["password"] = _keychain_reference_payload(*staged_reference)
            continue
        if password in (None, "") or existing_reference is not None:
            continue
        if not isinstance(password, str):
            raise MailSecretProtectionError("Mail secret has an invalid format.")
        staged_reference = _staged_keychain_reference_for_account(account)
        _get_keychain_backend().store(*staged_reference, password)
        transition.rollback_writes.append(_KeychainWriteRollback(*staged_reference, None))
        account["password"] = _keychain_reference_payload(*staged_reference)

    current_mail = protected.get("mail") if isinstance(protected.get("mail"), dict) else None
    pending = {
        reference
        for reference in (
            _keychain_reference_from_value(item)
            for item in (current_mail or {}).get("pending_secret_cleanup", [])
            if isinstance(current_mail, dict)
        )
        if reference is not None
    }
    pending.update(_keychain_references(previous_mail) - _keychain_references(current_mail))
    transition.pending_cleanup = pending
    if isinstance(current_mail, dict):
        if pending:
            current_mail["pending_secret_cleanup"] = [
                _keychain_reference_payload(*reference) for reference in sorted(pending)
            ]
        else:
            current_mail.pop("pending_secret_cleanup", None)
    return transition


def _account_with_keychain_reference(
    mail: dict[str, Any] | None, reference: tuple[str, str] | None
) -> dict[str, Any] | None:
    if reference is None:
        return None
    accounts = mail.get("accounts") if isinstance(mail, dict) else []
    if not isinstance(accounts, list):
        return None
    matches = [
        account for account in accounts
        if isinstance(account, dict) and _keychain_reference_from_value(account.get("password")) == reference
    ]
    return matches[0] if len(matches) == 1 else None


def record_failed_keychain_compensation(
    path: Path, references: list[dict[str, str]], *, operation: str
) -> None:
    """Durably retain only non-secret references when a failed write cannot compensate."""
    existing, _source = load_json_with_backup(path)
    existing_entries = existing.get("pending") if isinstance(existing, dict) else []
    pending = _normalize_recovery_entries(existing_entries)
    pending.extend(
        entry for entry in _normalize_recovery_entries(
            [{**reference, "operation": operation} for reference in references]
        ) if entry not in pending
    )
    try:
        atomic_write_json(path, {"version": 1, "pending": pending})
    except Exception as exc:
        raise MailSecretProtectionError("macOS Keychain compensation recovery could not be persisted.") from exc


def retry_failed_keychain_compensation(path: Path) -> bool:
    """Retry non-secret recovery work; failure is retained for a later safe lifecycle point."""
    data, _source = load_json_with_backup(path)
    entries = _normalize_recovery_entries(data.get("pending") if isinstance(data, dict) else [])
    if not entries:
        return True
    remaining = [
        entry for entry in entries
        if not _delete_keychain_reference(entry["service"], entry["account"])
    ]
    try:
        atomic_write_json(path, {"version": 1, "pending": remaining})
    except Exception as exc:
        raise MailSecretProtectionError("macOS Keychain compensation recovery could not be persisted.") from exc
    return not remaining


def _normalize_recovery_entries(raw: object) -> list[dict[str, str]]:
    entries = raw if isinstance(raw, list) else []
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in entries:
        reference = _keychain_reference_from_value(item)
        operation = str(item.get("operation") or "rollback_cleanup") if isinstance(item, dict) else ""
        if reference is None or operation not in {"rollback_cleanup", "restore_failure"}:
            continue
        key = (*reference, operation)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({**_keychain_reference_payload(*reference), "operation": operation})
    return normalized


def cleanup_removed_mail_secrets(previous_mail: dict[str, Any] | None, current_mail: dict[str, Any] | None) -> None:
    """Delete Keychain items no longer referenced by the saved mail configuration."""
    if _current_platform() != "darwin":
        return
    for service, account in _keychain_references(previous_mail) - _keychain_references(current_mail):
        if not _delete_keychain_reference(service, account):
            raise MailSecretProtectionError("macOS Keychain mail secret cleanup failed.")


def _keychain_references(mail: dict[str, Any] | None) -> set[tuple[str, str]]:
    accounts = mail.get("accounts") if isinstance(mail, dict) and isinstance(mail.get("accounts"), list) else []
    return {
        (password["service"], password["account"])
        for item in accounts if isinstance(item, dict)
        for password in [item.get("password")]
        if (reference := _keychain_reference_from_value(password)) is not None
        for service, account in [reference]
    }


def _keychain_error(exc: _KeychainBackendError) -> MailSecretProtectionError:
    if exc.status == -25300:
        return MailSecretProtectionError("The macOS Keychain mail secret was not found.")
    if exc.status in {-25293, -25308}:
        return MailSecretProtectionError("macOS Keychain access was denied.")
    if exc.operation == "delete":
        return MailSecretProtectionError("macOS Keychain mail secret cleanup failed.")
    if exc.operation == "store":
        return MailSecretProtectionError("macOS Keychain mail secret protection failed.")
    return MailSecretProtectionError("macOS Keychain mail secret could not be read.")


class _MacOSKeychainBackend:
    """Small ctypes wrapper around Security.framework generic-password APIs."""

    _SUCCESS = 0
    _DUPLICATE = -25299

    def __init__(self) -> None:
        if _current_platform() != "darwin":
            raise MailSecretProtectionError("macOS Keychain is unavailable on this platform.")
        self._security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
        self._core_foundation = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
        self._security.SecKeychainAddGenericPassword.restype = ctypes.c_int32
        self._security.SecKeychainFindGenericPassword.restype = ctypes.c_int32
        self._security.SecKeychainItemModifyAttributesAndData.restype = ctypes.c_int32
        self._security.SecKeychainItemDelete.restype = ctypes.c_int32
        self._security.SecKeychainItemFreeContent.restype = ctypes.c_int32
        self._security.SecKeychainAddGenericPassword.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
            ctypes.c_char_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p),
        ]
        self._security.SecKeychainFindGenericPassword.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.c_char_p, ctypes.c_uint32,
            ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._security.SecKeychainItemModifyAttributesAndData.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
        ]
        self._security.SecKeychainItemDelete.argtypes = [ctypes.c_void_p]
        self._security.SecKeychainItemFreeContent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self._core_foundation.CFRelease.argtypes = [ctypes.c_void_p]

    @staticmethod
    def _encoded(service: str, account: str) -> tuple[bytes, bytes]:
        return service.encode("utf-8"), account.encode("utf-8")

    def _find(self, service: str, account: str) -> tuple[ctypes.c_void_p, ctypes.c_void_p, int]:
        service_bytes, account_bytes = self._encoded(service, account)
        password_length = ctypes.c_uint32()
        password_data = ctypes.c_void_p()
        item = ctypes.c_void_p()
        status = self._security.SecKeychainFindGenericPassword(
            None, len(service_bytes), service_bytes, len(account_bytes), account_bytes,
            ctypes.byref(password_length), ctypes.byref(password_data), ctypes.byref(item),
        )
        if status != self._SUCCESS:
            raise _KeychainBackendError("read", status)
        return item, password_data, password_length.value

    def _release_find(self, item: ctypes.c_void_p, password_data: ctypes.c_void_p) -> None:
        if password_data:
            self._security.SecKeychainItemFreeContent(None, password_data)
        if item:
            self._core_foundation.CFRelease(item)

    def store(self, service: str, account: str, secret: str) -> None:
        secret_bytes = secret.encode("utf-8")
        buffer = ctypes.create_string_buffer(secret_bytes)
        service_bytes, account_bytes = self._encoded(service, account)
        item = ctypes.c_void_p()
        status = self._security.SecKeychainAddGenericPassword(
            None, len(service_bytes), service_bytes, len(account_bytes), account_bytes,
            len(secret_bytes), ctypes.cast(buffer, ctypes.c_void_p), ctypes.byref(item),
        )
        if status == self._SUCCESS:
            if item:
                self._core_foundation.CFRelease(item)
            return
        if status != self._DUPLICATE:
            raise _KeychainBackendError("store", status)
        item, password_data, _length = self._find(service, account)
        try:
            status = self._security.SecKeychainItemModifyAttributesAndData(
                item, None, len(secret_bytes), ctypes.cast(buffer, ctypes.c_void_p)
            )
            if status != self._SUCCESS:
                raise _KeychainBackendError("store", status)
        finally:
            self._release_find(item, password_data)

    def read(self, service: str, account: str) -> str:
        item, password_data, password_length = self._find(service, account)
        try:
            return ctypes.string_at(password_data, password_length).decode("utf-8")
        finally:
            self._release_find(item, password_data)

    def delete(self, service: str, account: str) -> None:
        item, password_data, _length = self._find(service, account)
        try:
            status = self._security.SecKeychainItemDelete(item)
            if status != self._SUCCESS:
                raise _KeychainBackendError("delete", status)
        finally:
            self._release_find(item, password_data)


_KEYCHAIN_BACKEND: _MacOSKeychainBackend | None = None


def _get_keychain_backend() -> _MacOSKeychainBackend:
    global _KEYCHAIN_BACKEND
    if _KEYCHAIN_BACKEND is None:
        _KEYCHAIN_BACKEND = _MacOSKeychainBackend()
    return _KEYCHAIN_BACKEND


def _blob_from_bytes(value: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(value)
    return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _protect_bytes(value: bytes) -> str:
    source, _source_buffer = _blob_from_bytes(value)
    destination = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptProtectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(destination)):
        raise MailSecretProtectionError("Windows mail secret protection failed.")
    try:
        payload = ctypes.string_at(destination.pbData, destination.cbData)
        return base64.b64encode(payload).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


def _unprotect_bytes(value: str) -> bytes:
    try:
        encoded = base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise MailSecretProtectionError("Mail secret has an invalid protected format.") from exc
    source, _source_buffer = _blob_from_bytes(encoded)
    destination = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    if not crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(destination)):
        raise MailSecretProtectionError("Windows mail secret could not be unprotected.")
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)
