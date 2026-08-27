from __future__ import annotations

"""Sanitized mail-authentication error classification."""

import socket


class MailAuthenticationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def classify_imap_error(exc: BaseException) -> MailAuthenticationError:
    raw = str(exc or "")
    lowered = raw.casefold()
    if "basic authentication is disabled" in lowered or "basic auth" in lowered and "disabled" in lowered:
        return MailAuthenticationError(
            "IMAP_BASIC_AUTH_REJECTED",
            "IMAP 服务器不接受当前 Basic 登录方式。配置已保存；请确认该服务商是否支持密码或授权码登录。",
        )
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in lowered:
        return MailAuthenticationError("MAIL_AUTH_TIMEOUT", "邮箱验证超时，请检查网络和服务器地址。")
    if isinstance(exc, OSError) and not isinstance(exc, PermissionError):
        return MailAuthenticationError("MAIL_NETWORK_ERROR", "无法连接邮箱服务器，请检查网络、Host 和端口。")
    return MailAuthenticationError(
        "MAIL_CREDENTIAL_REJECTED",
        "邮箱服务器拒绝当前登录凭据。配置保存状态不受影响。",
    )
