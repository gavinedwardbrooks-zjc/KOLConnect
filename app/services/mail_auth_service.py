from __future__ import annotations

"""Sanitized mail-authentication error classification."""

import socket
import ssl
from typing import Mapping


class MailAuthenticationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_gmail_account(account: Mapping[str, object] | None, host_key: str) -> bool:
    if not isinstance(account, Mapping):
        return False
    return str(account.get(host_key) or "").strip().casefold() == host_key.replace("_host", ".gmail.com")


def _gmail_auth_error(raw: str) -> MailAuthenticationError:
    lowered = raw.casefold()
    if "application-specific password" in lowered or "app password" in lowered:
        return MailAuthenticationError(
            "GMAIL_APP_PASSWORD_MAY_BE_REQUIRED",
            "Gmail 可能要求应用专用密码。KOLConnect 当前使用 IMAP/SMTP 密码登录；如账号支持，请在密码/授权码字段填写 Google 应用专用密码。",
        )
    if "web login required" in lowered or "please log in via your web browser" in lowered:
        return MailAuthenticationError(
            "GMAIL_WEB_LOGIN_REQUIRED",
            "Gmail 要求先在网页中完成登录或安全验证。完成后请重试；普通账号密码可能仍无法用于 IMAP/SMTP 登录。",
        )
    return MailAuthenticationError(
        "GMAIL_AUTH_REJECTED",
        "Gmail 拒绝当前登录凭据。KOLConnect 当前使用 IMAP/SMTP 密码登录；普通 Google 账号密码可能无法使用。如账号支持，请使用 Google 应用专用密码；OAuth2 暂不支持。",
    )


def classify_mail_auth_error(
    exc: BaseException,
    *,
    account: Mapping[str, object] | None = None,
    host_key: str = "imap_host",
) -> MailAuthenticationError:
    raw = str(exc or "")
    lowered = raw.casefold()
    is_gmail = _is_gmail_account(account, host_key)
    if "basic authentication is disabled" in lowered or "basic auth" in lowered and "disabled" in lowered:
        return MailAuthenticationError(
            "IMAP_BASIC_AUTH_REJECTED",
            "IMAP 服务器不接受当前 Basic 登录方式。配置已保存；请确认该服务商是否支持密码或授权码登录。",
        )
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in lowered:
        return MailAuthenticationError("MAIL_AUTH_TIMEOUT", "邮箱验证超时，请检查网络和服务器地址。")
    if isinstance(exc, ssl.SSLError) or any(token in lowered for token in ("tls", "ssl", "certificate verify")):
        return MailAuthenticationError("MAIL_TLS_FAILED", "邮箱服务器 TLS 连接失败，请检查 Host、端口和证书配置。")
    if isinstance(exc, OSError) and not isinstance(exc, PermissionError):
        return MailAuthenticationError("MAIL_NETWORK_ERROR", "无法连接邮箱服务器，请检查网络、Host 和端口。")
    if is_gmail:
        return _gmail_auth_error(raw)
    return MailAuthenticationError(
        "MAIL_CREDENTIAL_REJECTED",
        "邮箱服务器拒绝当前登录凭据。配置保存状态不受影响。",
    )


def classify_imap_error(
    exc: BaseException,
    *,
    account: Mapping[str, object] | None = None,
) -> MailAuthenticationError:
    return classify_mail_auth_error(exc, account=account, host_key="imap_host")


def classify_smtp_error(
    exc: BaseException,
    *,
    account: Mapping[str, object] | None = None,
) -> MailAuthenticationError:
    return classify_mail_auth_error(exc, account=account, host_key="smtp_host")
