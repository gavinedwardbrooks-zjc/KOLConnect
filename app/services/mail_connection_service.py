from __future__ import annotations

"""Shared, stage-aware IMAP/SMTP connectivity for validation and synchronization."""

import imaplib
import re
import smtplib
import ssl
import time
from typing import Callable, Mapping

from services.mail_auth_service import (
    MailAuthenticationError,
    classify_imap_error,
    classify_smtp_error,
)
from services.mail_secret_storage import unprotect_mail_secret


MAIL_CONNECTION_TIMEOUT_SECONDS = 10
_GMAIL_APP_PASSWORD = re.compile(r"^[A-Za-z0-9]{16}$")


def parse_mail_port(value: object, default: int) -> int:
    try:
        port = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return port if 0 < port <= 65535 else default


def mail_tls_mode(protocol: str, port: int) -> str:
    if protocol == "imap":
        return "implicit_tls" if port == 993 else "starttls"
    return "implicit_tls" if port == 465 else "starttls"


def normalize_gmail_app_password(account: Mapping[str, object], password: str) -> str:
    host = str(account.get("imap_host") or account.get("smtp_host") or "").strip().casefold()
    provider = str(account.get("provider") or "").strip().casefold()
    if provider != "gmail" and host not in {"imap.gmail.com", "smtp.gmail.com"}:
        return password
    compact = password.replace(" ", "")
    return compact if " " in password and _GMAIL_APP_PASSWORD.fullmatch(compact) else password


def create_mail_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except (ImportError, OSError):
        return ssl.create_default_context()


def _secret(account: Mapping[str, object], *, allow_transient_plaintext: bool) -> str:
    password = unprotect_mail_secret(
        account.get("password"), allow_transient_plaintext=allow_transient_plaintext
    )
    return normalize_gmail_app_password(account, password)


def _validate_host(host: str, protocol: str) -> None:
    if host.casefold() == "map.qiye.aliyun.com":
        expected = "imap.qiye.aliyun.com" if protocol == "imap" else "smtp.qiye.aliyun.com"
        raise MailAuthenticationError(
            f"MAIL_{protocol.upper()}_HOST_TYPO",
            f"邮箱服务器地址疑似拼写错误，请使用 {expected}。",
            protocol=protocol,
            stage="config",
        )


def _result(protocol: str, host: str, port: int, mode: str, *, status: str,
            stage: str, elapsed_ms: int, error: MailAuthenticationError | None = None) -> dict:
    result = {
        "protocol": protocol,
        "status": status,
        "stage": stage,
        "host": host,
        "port": port,
        "tls_mode": mode,
        "elapsed_ms": elapsed_ms,
    }
    if error is not None:
        result.update({"code": error.code, "message": str(error)})
    return result


def open_imap_connection(
    account: Mapping[str, object],
    *,
    folder: str | None = None,
    imap_factory: Callable | None = None,
    timeout: int = MAIL_CONNECTION_TIMEOUT_SECONDS,
    allow_transient_plaintext: bool = False,
):
    host = str(account.get("imap_host") or "").strip()
    username = str(account.get("username") or "").strip()
    port = parse_mail_port(account.get("imap_port"), 993)
    mode = mail_tls_mode("imap", port)
    _validate_host(host, "imap")
    password = _secret(account, allow_transient_plaintext=allow_transient_plaintext)
    if not host or not username or not password:
        raise MailAuthenticationError(
            "MAIL_IMAP_CONFIG_INCOMPLETE",
            "请完整填写 IMAP Host、IMAP Port、用户名和密码/授权码。",
            protocol="imap",
            stage="config",
        )
    if (str(account.get("provider") or "").casefold() == "gmail" or host.casefold() == "imap.gmail.com") and "@" not in username:
        raise MailAuthenticationError(
            "GMAIL_USERNAME_MUST_BE_FULL_EMAIL",
            "Gmail 用户名必须填写完整邮箱地址。",
            protocol="imap",
            stage="config",
        )

    started = time.monotonic()
    mailbox = None
    stage = "connect"
    try:
        constructor = imap_factory or (imaplib.IMAP4_SSL if mode == "implicit_tls" else imaplib.IMAP4)
        kwargs = {"timeout": timeout}
        if imap_factory is None and mode == "implicit_tls":
            kwargs["ssl_context"] = create_mail_ssl_context()
        mailbox = constructor(host, port, **kwargs)
        if mode == "starttls":
            stage = "tls"
            context = create_mail_ssl_context()
            try:
                mailbox.starttls(ssl_context=context)
            except TypeError:
                mailbox.starttls()
        stage = "auth"
        mailbox.login(username, password)
        if folder:
            stage = "folder"
            select_status, _ = mailbox.select(folder, readonly=True)
            if select_status != "OK":
                raise MailAuthenticationError(
                    "MAIL_IMAP_FOLDER_ACCESS_FAILED",
                    f"IMAP 登录成功，但无法访问 {folder} 文件夹。",
                    protocol="imap",
                    stage="folder",
                )
        elapsed = int((time.monotonic() - started) * 1000)
        return mailbox, _result("imap", host, port, mode, status="pass", stage=stage, elapsed_ms=elapsed)
    except MailAuthenticationError:
        if mailbox is not None:
            try:
                mailbox.logout()
            except Exception:
                pass
        raise
    except Exception as exc:
        if mailbox is not None:
            try:
                mailbox.logout()
            except Exception:
                pass
        raise classify_imap_error(exc, account=account, stage=stage) from exc


def test_imap_connection(account: Mapping[str, object], *, imap_factory: Callable | None = None) -> dict:
    started = time.monotonic()
    mailbox = None
    try:
        mailbox, result = open_imap_connection(
            account, folder="INBOX", imap_factory=imap_factory, allow_transient_plaintext=True
        )
        return result
    except MailAuthenticationError as exc:
        host = str(account.get("imap_host") or "").strip()
        port = parse_mail_port(account.get("imap_port"), 993)
        return _result(
            "imap", host, port, mail_tls_mode("imap", port), status="fail",
            stage=exc.stage or "unknown", elapsed_ms=int((time.monotonic() - started) * 1000), error=exc,
        )
    finally:
        if mailbox is not None:
            try:
                mailbox.logout()
            except Exception:
                pass


def test_smtp_connection(account: Mapping[str, object], *, smtp_factory: Callable | None = None,
                         smtp_ssl_factory: Callable | None = None) -> dict:
    host = str(account.get("smtp_host") or "").strip()
    username = str(account.get("username") or "").strip()
    port = parse_mail_port(account.get("smtp_port"), 587)
    mode = mail_tls_mode("smtp", port)
    started = time.monotonic()
    if not host:
        return _result("smtp", host, port, mode, status="not_configured", stage="config", elapsed_ms=0)
    client = None
    stage = "config"
    try:
        _validate_host(host, "smtp")
        password = _secret(account, allow_transient_plaintext=True)
        if not username or not password:
            raise MailAuthenticationError(
                "MAIL_SMTP_CONFIG_INCOMPLETE",
                "SMTP 未完整配置；这不影响当前 IMAP 收件同步。",
                protocol="smtp",
                stage="config",
            )
        stage = "connect"
        context = create_mail_ssl_context()
        if mode == "implicit_tls":
            constructor = smtp_ssl_factory or smtplib.SMTP_SSL
            kwargs = {"timeout": MAIL_CONNECTION_TIMEOUT_SECONDS}
            if smtp_ssl_factory is None:
                kwargs["context"] = context
            client = constructor(host, port, **kwargs)
            client.ehlo()
        else:
            constructor = smtp_factory or smtplib.SMTP
            client = constructor(host, port, timeout=MAIL_CONNECTION_TIMEOUT_SECONDS)
            client.ehlo()
            stage = "tls"
            if not client.has_extn("starttls"):
                raise MailAuthenticationError(
                    "MAIL_SMTP_TLS_FAILED",
                    "SMTP 服务器未提供 STARTTLS；请检查端口和加密方式。",
                    protocol="smtp",
                    stage="tls",
                )
            try:
                client.starttls(context=context)
            except TypeError:
                client.starttls()
            client.ehlo()
        stage = "auth"
        client.login(username, password)
        return _result(
            "smtp", host, port, mode, status="pass", stage="auth",
            elapsed_ms=int((time.monotonic() - started) * 1000),
        )
    except MailAuthenticationError as exc:
        return _result(
            "smtp", host, port, mode, status="fail", stage=exc.stage or stage,
            elapsed_ms=int((time.monotonic() - started) * 1000), error=exc,
        )
    except Exception as exc:
        classified = classify_smtp_error(exc, account=account, stage=stage)
        return _result(
            "smtp", host, port, mode, status="fail", stage=classified.stage or stage,
            elapsed_ms=int((time.monotonic() - started) * 1000), error=classified,
        )
    finally:
        if client is not None:
            try:
                client.quit()
            except Exception:
                pass


def validate_mail_account(account: Mapping[str, object], *, imap_factory: Callable | None = None,
                          smtp_factory: Callable | None = None,
                          smtp_ssl_factory: Callable | None = None) -> dict:
    started = time.monotonic()
    imap = test_imap_connection(account, imap_factory=imap_factory)
    smtp = test_smtp_connection(
        account, smtp_factory=smtp_factory, smtp_ssl_factory=smtp_ssl_factory
    )
    usable = imap["status"] == "pass"
    warning = ""
    if usable and smtp["status"] == "fail":
        warning = "收件同步连接成功，但 SMTP 验证失败。不影响邮件同步；发送邮件前必须修复 SMTP 配置。"
    return {
        "usable": usable,
        "imap": imap,
        "smtp": smtp,
        "warning": warning,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
