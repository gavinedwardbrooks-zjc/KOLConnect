from __future__ import annotations

"""Same-origin session and CSRF protection dedicated to SMTP send capabilities."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import threading
from typing import Callable, Mapping
from urllib.parse import urlparse

from services.mail_send_service import MailSendError


COOKIE_NAME = "kolconnect_mail_send_session"
CSRF_HEADER = "X-KOLConnect-Mail-CSRF"
SESSION_TTL_SECONDS = 1800


@dataclass
class MailSendSession:
    session_id: str
    csrf_hash: str
    expires_at: datetime


def _header(headers: Mapping[str, object], name: str) -> str:
    getter = getattr(headers, "get", None)
    return str(getter(name, "") if callable(getter) else "").strip()


def _same_origin(value: str, port: int, *, allow_path: bool) -> bool:
    try:
        parsed = urlparse(value)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            return False
        if parsed.port != port or parsed.username or parsed.password:
            return False
        if not allow_path and (parsed.path or parsed.query or parsed.fragment):
            return False
        return True
    except ValueError:
        return False


def _cookie_value(raw_cookie: str, name: str) -> str:
    for part in raw_cookie.split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            return value.strip()
    return ""


class MailSendSessionStore:
    def __init__(self, *, now: Callable[[], datetime] | None = None, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, MailSendSession] = {}
        self._lock = threading.RLock()

    def issue(self, headers: Mapping[str, object], port: int) -> dict[str, str]:
        origin = _header(headers, "Origin")
        referer = _header(headers, "Referer")
        fetch_site = _header(headers, "Sec-Fetch-Site").lower()
        if fetch_site and fetch_site != "same-origin":
            raise MailSendError("MAIL_SEND_ORIGIN_REJECTED", "邮件发送安全会话只能由本地页面创建。", status=403)
        origin_allowed = _same_origin(origin, port, allow_path=False) if origin else None
        referer_allowed = _same_origin(referer, port, allow_path=True) if referer else False
        if origin_allowed is False or (origin_allowed is None and not referer_allowed):
            raise MailSendError("MAIL_SEND_ORIGIN_REJECTED", "邮件发送安全会话只能由本地页面创建。", status=403)
        session_id = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        with self._lock:
            self._discard_expired()
            self._sessions[session_id] = MailSendSession(
                session_id=session_id,
                csrf_hash=hashlib.sha256(csrf_token.encode("utf-8")).hexdigest(),
                expires_at=self._now() + timedelta(seconds=self._ttl_seconds),
            )
        return {
            "session_id": session_id,
            "csrf_token": csrf_token,
            "set_cookie": (
                f"{COOKIE_NAME}={session_id}; Path=/; Max-Age={self._ttl_seconds}; "
                "HttpOnly; SameSite=Strict"
            ),
        }

    def validate(self, headers: Mapping[str, object], port: int) -> str:
        origin = _header(headers, "Origin")
        referer = _header(headers, "Referer")
        fetch_site = _header(headers, "Sec-Fetch-Site").lower()
        if fetch_site and fetch_site != "same-origin":
            raise MailSendError("MAIL_SEND_ORIGIN_REJECTED", "邮件发送请求来源无效。", status=403)
        origin_allowed = _same_origin(origin, port, allow_path=False) if origin else None
        referer_allowed = _same_origin(referer, port, allow_path=True) if referer else False
        if origin_allowed is False or (origin_allowed is None and not referer_allowed):
            raise MailSendError("MAIL_SEND_ORIGIN_REJECTED", "邮件发送请求来源无效。", status=403)
        session_id = _cookie_value(_header(headers, "Cookie"), COOKIE_NAME)
        csrf_token = _header(headers, CSRF_HEADER)
        if not session_id or not csrf_token:
            raise MailSendError("MAIL_SEND_CSRF_REQUIRED", "邮件发送安全凭据缺失。", status=403)
        with self._lock:
            self._discard_expired()
            session = self._sessions.get(session_id)
            if session is None:
                raise MailSendError("MAIL_SEND_SESSION_INVALID", "邮件发送会话已失效。", status=403)
            supplied = hashlib.sha256(csrf_token.encode("utf-8")).hexdigest()
            if not hmac.compare_digest(session.csrf_hash, supplied):
                raise MailSendError("MAIL_SEND_CSRF_INVALID", "邮件发送安全凭据无效。", status=403)
            session.expires_at = self._now() + timedelta(seconds=self._ttl_seconds)
            return session.session_id

    def _discard_expired(self) -> None:
        now = self._now()
        expired = [session_id for session_id, record in self._sessions.items() if now >= record.expires_at]
        for session_id in expired:
            self._sessions.pop(session_id, None)
