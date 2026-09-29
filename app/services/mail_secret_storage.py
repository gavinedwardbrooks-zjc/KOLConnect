"""Windows user-scoped protection for persisted mail account secrets.

Only opaque DPAPI blobs are suitable for ``settings.json``.  Plaintext is
accepted solely as a legacy migration input or an in-flight settings update;
callers resolve a protected blob immediately before authenticating with IMAP
or SMTP.
"""

from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes
from typing import Any


SECRET_FORMAT = "dpapi-v1"


class MailSecretProtectionError(RuntimeError):
    """A safe error that never includes the protected or plaintext value."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def is_protected_mail_secret(value: object) -> bool:
    return (
        isinstance(value, dict)
        and value.get("format") == SECRET_FORMAT
        and isinstance(value.get("data"), str)
        and bool(value["data"])
    )


def protect_mail_secret(value: str) -> dict[str, str]:
    """Protect a non-empty value with the current Windows user's DPAPI key."""
    if not isinstance(value, str) or not value:
        raise MailSecretProtectionError("Mail secret protection requires a non-empty value.")
    if sys.platform != "win32":
        raise MailSecretProtectionError("Mail secret protection is supported only on Windows.")
    try:
        return {"format": SECRET_FORMAT, "data": _protect_bytes(value.encode("utf-8"))}
    except MailSecretProtectionError:
        raise
    except Exception as exc:  # pragma: no cover - defensive native boundary
        raise MailSecretProtectionError("Windows mail secret protection failed.") from exc


def unprotect_mail_secret(value: object, *, allow_transient_plaintext: bool = False) -> str:
    """Return plaintext only at the local IMAP/SMTP authentication boundary."""
    if value in (None, ""):
        return ""
    if not is_protected_mail_secret(value):
        if isinstance(value, str):
            if allow_transient_plaintext:
                return value
            raise MailSecretProtectionError("Stored mail secret is not protected.")
        raise MailSecretProtectionError("Mail secret is unavailable or has an invalid format.")
    if sys.platform != "win32":
        raise MailSecretProtectionError("Mail secret protection is supported only on Windows.")
    try:
        return _unprotect_bytes(value["data"]).decode("utf-8")
    except MailSecretProtectionError:
        raise
    except Exception as exc:  # pragma: no cover - defensive native boundary
        raise MailSecretProtectionError("Windows mail secret could not be unprotected.") from exc


def protect_mail_state_for_storage(state: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Copy a state tree and replace only mail passwords with DPAPI blobs."""
    import copy

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
        account["password"] = protect_mail_secret(password)
        changed = True
    return protected, changed


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
