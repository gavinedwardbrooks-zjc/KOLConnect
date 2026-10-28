from __future__ import annotations

"""Durable, human-authorized SMTP sending with conservative failure semantics."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.headerregistry import Address
from email.policy import SMTP
from email.utils import formataddr, make_msgid
import hashlib
import json
import re
import secrets
import smtplib
from typing import Any, Callable, Mapping
import uuid

from services.mail_connection_service import (
    MAIL_CONNECTION_TIMEOUT_SECONDS,
    create_mail_ssl_context,
    mail_tls_mode,
    normalize_gmail_app_password,
    parse_mail_port,
)
from services.mail_inbox_facts import mail_account_identity
from services.mail_secret_storage import unprotect_mail_secret


ALLOWED_AUTHORIZATION_SOURCES = {"human_direct", "human_approved_ai_proposal"}
RESERVED_AUTHORIZATION_SOURCE = "future_scoped_ai_authorization"
ATTEMPT_OUTCOMES = {"started", "accepted", "failed", "unknown"}
EMAIL_LIMIT = 320
SUBJECT_LIMIT = 998
BODY_LIMIT = 1_000_000
MAX_RECIPIENTS = 50
PREVIEW_TTL_SECONDS = 900
AUTHORIZATION_TTL_SECONDS = 300
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{16,128}$")
MESSAGE_ID_PATTERN = re.compile(r"^<[^<>\s]+@[^<>\s]+>$")


class MailSendError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(value: object) -> datetime:
    return datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def session_hash(session_id: object) -> str:
    value = str(session_id or "")
    if not value:
        raise MailSendError("MAIL_SEND_SESSION_REQUIRED", "邮件发送会话无效。", status=403)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_text(value: object, *, name: str, maximum: int, allow_empty: bool = True) -> str:
    text = str(value or "")
    if "\r" in text or "\n" in text:
        raise MailSendError("MAIL_HEADER_INJECTION", f"{name} 不能包含换行符。")
    if not allow_empty and not text.strip():
        raise MailSendError("MAIL_FIELD_REQUIRED", f"{name} 不能为空。")
    if len(text) > maximum:
        raise MailSendError("MAIL_FIELD_TOO_LONG", f"{name} 超出长度限制。")
    return text


def normalize_address(value: object, *, name: str = "邮箱地址") -> str:
    text = _safe_text(value, name=name, maximum=EMAIL_LIMIT, allow_empty=False).strip()
    try:
        parsed = Address(addr_spec=text)
    except (TypeError, ValueError) as exc:
        raise MailSendError("MAIL_ADDRESS_INVALID", f"{name}格式无效。") from exc
    normalized = parsed.addr_spec.lower()
    if normalized != text.lower() or "@" not in normalized:
        raise MailSendError("MAIL_ADDRESS_INVALID", f"{name}格式无效。")
    return normalized


def normalize_addresses(value: object, *, name: str, required: bool) -> list[str]:
    if not isinstance(value, list):
        raise MailSendError("MAIL_ADDRESS_LIST_INVALID", f"{name}必须是邮箱地址列表。")
    if len(value) > MAX_RECIPIENTS:
        raise MailSendError("MAIL_RECIPIENT_LIMIT", "收件人数量超出限制。")
    result: list[str] = []
    for item in value:
        address = normalize_address(item, name=name)
        if address not in result:
            result.append(address)
    if required and not result:
        raise MailSendError("MAIL_RECIPIENT_REQUIRED", "请至少选择一位收件人。")
    return result


def _message_id(value: object) -> str:
    text = _safe_text(value, name="Message-ID", maximum=998, allow_empty=False).strip()
    if not text.startswith("<"):
        text = f"<{text}>"
    if not MESSAGE_ID_PATTERN.fullmatch(text):
        raise MailSendError("MAIL_THREAD_ID_INVALID", "回复邮件缺少可靠的 Message-ID。")
    return text


def _reference_ids(value: object) -> list[str]:
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(str(value)) if isinstance(value, str) else value
    except json.JSONDecodeError:
        parsed = []
    if not isinstance(parsed, list):
        return []
    result: list[str] = []
    for item in parsed[-20:]:
        try:
            normalized = _message_id(item)
        except MailSendError:
            continue
        if normalized not in result:
            result.append(normalized)
    return result


def _snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    return _hash({key: snapshot[key] for key in (
        "draft_id", "draft_version", "mail_account_id", "from_address", "to_addresses",
        "cc_addresses", "reply_to_address", "subject", "body_text", "in_reply_to", "reference_ids",
    )})


def _envelope_hash(snapshot: Mapping[str, Any]) -> str:
    return _hash({key: snapshot[key] for key in (
        "mail_account_id", "from_address", "to_addresses", "cc_addresses", "reply_to_address",
    )})


@dataclass(frozen=True)
class SMTPExecutionResult:
    outcome: str
    stage: str
    safe_error_code: str | None
    recipients: tuple[dict[str, Any], ...]


class SMTPExecutor:
    """The only component allowed to resolve a mail secret and enter SMTP DATA."""

    def __init__(
        self,
        *,
        smtp_factory: Callable | None = None,
        smtp_ssl_factory: Callable | None = None,
        secret_resolver: Callable[[object], str] | None = None,
        timeout: int = MAIL_CONNECTION_TIMEOUT_SECONDS,
    ) -> None:
        self.smtp_factory = smtp_factory
        self.smtp_ssl_factory = smtp_ssl_factory
        self.secret_resolver = secret_resolver or (lambda value: unprotect_mail_secret(value))
        self.timeout = timeout

    def send(self, account: Mapping[str, object], snapshot: Mapping[str, Any], message_id: str) -> SMTPExecutionResult:
        host = str(account.get("smtp_host") or "").strip()
        username = str(account.get("username") or "").strip()
        configured_from = normalize_address(account.get("email"), name="发送邮箱")
        if configured_from != snapshot["from_address"]:
            raise MailSendError("MAIL_FROM_MISMATCH", "发件地址与已配置邮箱不一致。", status=409)
        port = parse_mail_port(account.get("smtp_port"), 587)
        mode = mail_tls_mode("smtp", port)
        try:
            password = self.secret_resolver(account.get("password"))
        except Exception as exc:
            raise MailSendError("MAIL_SMTP_SECRET_UNAVAILABLE", "SMTP 凭据不可用。", status=409) from exc
        password = normalize_gmail_app_password(account, password)
        if not host or not username or not password:
            raise MailSendError("MAIL_SMTP_CONFIG_INCOMPLETE", "SMTP 配置不完整。", status=409)

        message = EmailMessage(policy=SMTP)
        sender_name = _safe_text(account.get("sender_name"), name="发件人名称", maximum=200).strip()
        message["From"] = formataddr((sender_name, configured_from)) if sender_name else configured_from
        message["To"] = ", ".join(snapshot["to_addresses"])
        if snapshot["cc_addresses"]:
            message["Cc"] = ", ".join(snapshot["cc_addresses"])
        if snapshot["reply_to_address"]:
            message["Reply-To"] = snapshot["reply_to_address"]
        message["Subject"] = snapshot["subject"]
        message["Message-ID"] = message_id
        if snapshot["in_reply_to"]:
            message["In-Reply-To"] = snapshot["in_reply_to"]
        if snapshot["reference_ids"]:
            message["References"] = " ".join(snapshot["reference_ids"])
        message.set_content(snapshot["body_text"], subtype="plain", charset="utf-8")

        client = None
        stage = "connect"
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        recipient_rows = [
            {"recipient_type": kind, "position": position, "recipient_address": address}
            for kind, addresses in (("to", snapshot["to_addresses"]), ("cc", snapshot["cc_addresses"]))
            for position, address in enumerate(addresses)
        ]
        try:
            context = create_mail_ssl_context()
            if mode == "implicit_tls":
                constructor = self.smtp_ssl_factory or smtplib.SMTP_SSL
                kwargs = {"timeout": self.timeout}
                if self.smtp_ssl_factory is None:
                    kwargs["context"] = context
                client = constructor(host, port, **kwargs)
                code, _response = client.ehlo()
                if int(code) >= 400:
                    return SMTPExecutionResult("failed", "connect", "MAIL_SMTP_EHLO_FAILED", tuple())
            else:
                constructor = self.smtp_factory or smtplib.SMTP
                client = constructor(host, port, timeout=self.timeout)
                code, _response = client.ehlo()
                if int(code) >= 400:
                    return SMTPExecutionResult("failed", "connect", "MAIL_SMTP_EHLO_FAILED", tuple())
                stage = "tls"
                if not client.has_extn("starttls"):
                    return SMTPExecutionResult("failed", stage, "MAIL_SMTP_TLS_REQUIRED", tuple())
                try:
                    client.starttls(context=context)
                except TypeError:
                    client.starttls()
                code, _response = client.ehlo()
                if int(code) >= 400:
                    return SMTPExecutionResult("failed", "tls", "MAIL_SMTP_EHLO_FAILED", tuple())
            stage = "auth"
            client.login(username, password)
            stage = "mail"
            code, _response = client.mail(configured_from)
            if not 200 <= int(code) < 300:
                return SMTPExecutionResult("failed", stage, "MAIL_SMTP_SENDER_REJECTED", tuple())
            stage = "rcpt"
            for row in recipient_rows:
                code, _response = client.rcpt(row["recipient_address"])
                accepted_recipient = 200 <= int(code) < 300
                target = accepted if accepted_recipient else rejected
                target.append({**row, "outcome": "accepted" if accepted_recipient else "rejected", "smtp_code": int(code),
                               "safe_error_code": None if accepted_recipient else "MAIL_SMTP_RECIPIENT_REJECTED"})
            if not accepted:
                return SMTPExecutionResult("failed", stage, "MAIL_SMTP_ALL_RECIPIENTS_REJECTED", tuple(rejected))
            stage = "data"
            code, _response = client.data(message.as_bytes(policy=SMTP))
            if not 200 <= int(code) < 300:
                rows = tuple({**row, "outcome": "rejected", "smtp_code": int(code),
                              "safe_error_code": "MAIL_SMTP_DATA_REJECTED"} for row in accepted) + tuple(rejected)
                return SMTPExecutionResult("failed", stage, "MAIL_SMTP_DATA_REJECTED", rows)
            return SMTPExecutionResult("accepted", stage, None, tuple(accepted + rejected))
        except (TimeoutError, OSError, smtplib.SMTPServerDisconnected):
            outcome = "unknown" if stage == "data" else "failed"
            code = "MAIL_SMTP_RESULT_UNKNOWN" if outcome == "unknown" else "MAIL_SMTP_CONNECTION_FAILED"
            pending = tuple({**row, "outcome": "unknown" if outcome == "unknown" else "rejected",
                             "smtp_code": None, "safe_error_code": code} for row in recipient_rows)
            return SMTPExecutionResult(outcome, stage, code, pending)
        except smtplib.SMTPResponseException as exc:
            rows = tuple({**row, "outcome": "rejected", "smtp_code": int(exc.smtp_code),
                          "safe_error_code": "MAIL_SMTP_REJECTED"} for row in recipient_rows)
            return SMTPExecutionResult("failed", stage, "MAIL_SMTP_REJECTED", rows)
        except smtplib.SMTPException:
            outcome = "unknown" if stage == "data" else "failed"
            code = "MAIL_SMTP_RESULT_UNKNOWN" if outcome == "unknown" else "MAIL_SMTP_PROTOCOL_FAILED"
            rows = tuple({**row, "outcome": "unknown" if outcome == "unknown" else "rejected",
                          "smtp_code": None, "safe_error_code": code} for row in recipient_rows)
            return SMTPExecutionResult(outcome, stage, code, rows)
        finally:
            if client is not None:
                try:
                    client.quit()
                except Exception:
                    pass


class MailSendService:
    def __init__(
        self,
        factory_provider: Callable[[], Any],
        account_resolver: Callable[[str], Mapping[str, object]],
        *,
        executor: SMTPExecutor | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._factory_provider = factory_provider
        self._account_resolver = account_resolver
        self._executor = executor or SMTPExecutor()
        self._now = now or _utc_now

    def recover_interrupted_attempts(self) -> int:
        now = _iso(self._now())
        with self._factory_provider().write_transaction() as connection:
            cursor = connection.execute(
                "UPDATE mail_send_attempts SET outcome='unknown',smtp_stage='recovery',"
                "safe_error_code='MAIL_SMTP_RESULT_UNKNOWN',completed_at=?,updated_at=? WHERE outcome='started'",
                (now, now),
            )
            connection.execute(
                "UPDATE mail_send_recipient_results SET outcome='unknown',safe_error_code='MAIL_SMTP_RESULT_UNKNOWN' "
                "WHERE outcome='pending' AND attempt_id IN (SELECT attempt_id FROM mail_send_attempts WHERE outcome='unknown')"
            )
            return int(cursor.rowcount)

    def create_draft(self, payload: Mapping[str, object]) -> dict[str, Any]:
        values = self._validated_draft(payload)
        draft_id = f"draft_{uuid.uuid4().hex}"
        now = _iso(self._now())
        factory = self._factory_provider()
        account = self._account_resolver(values["mail_account_id"])
        account_id, identity = mail_account_identity(dict(account))
        if account_id != values["mail_account_id"]:
            raise MailSendError("MAIL_ACCOUNT_MISMATCH", "发送邮箱身份已发生变化。", status=409)
        with factory.write_transaction() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES (?,?,?)",
                (account_id, identity, now),
            )
            connection.execute(
                "INSERT INTO mail_drafts(draft_id,context_type,reply_mail_message_id,mail_account_id,"
                "from_address,to_addresses,cc_addresses,reply_to_address,subject,body_text,in_reply_to,"
                "reference_ids,version,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (draft_id, values["context_type"], values["reply_mail_message_id"], account_id,
                 values["from_address"], _json(values["to_addresses"]), _json(values["cc_addresses"]),
                 values["reply_to_address"], values["subject"], values["body_text"], values["in_reply_to"],
                 _json(values["reference_ids"]), now, now),
            )
        return self.get_draft(draft_id)

    def update_draft(self, draft_id: object, payload: Mapping[str, object]) -> dict[str, Any]:
        draft_id = str(draft_id or "").strip()
        expected_version = payload.get("version")
        if not isinstance(expected_version, int) or expected_version < 1:
            raise MailSendError("MAIL_DRAFT_VERSION_REQUIRED", "必须提供当前草稿版本。")
        with self._factory_provider().read_connection() as connection:
            current_row = connection.execute("SELECT * FROM mail_drafts WHERE draft_id=?", (draft_id,)).fetchone()
        if current_row is None:
            raise MailSendError("MAIL_DRAFT_NOT_FOUND", "草稿不存在。", status=404)
        current = self._draft_row(current_row)
        if current.get("content_deleted_at"):
            raise MailSendError("MAIL_DRAFT_CONTENT_DELETED", "草稿内容已删除。", status=409)
        if current["version"] != expected_version:
            raise MailSendError("MAIL_DRAFT_VERSION_CONFLICT", "草稿已更新，请重新加载。", status=409)
        merged = {**current, **{key: value for key, value in payload.items() if key != "version"}}
        values = self._validated_draft(merged)
        if values["mail_account_id"] != current["mail_account_id"]:
            account = self._account_resolver(values["mail_account_id"])
            account_id, identity = mail_account_identity(dict(account))
            if account_id != values["mail_account_id"]:
                raise MailSendError("MAIL_ACCOUNT_MISMATCH", "发送邮箱身份已发生变化。", status=409)
        now = _iso(self._now())
        with self._factory_provider().write_transaction() as connection:
            if values["mail_account_id"] != current["mail_account_id"]:
                connection.execute(
                    "INSERT OR IGNORE INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES (?,?,?)",
                    (account_id, identity, now),
                )
            cursor = connection.execute(
                "UPDATE mail_drafts SET context_type=?,reply_mail_message_id=?,mail_account_id=?,from_address=?,"
                "to_addresses=?,cc_addresses=?,reply_to_address=?,subject=?,body_text=?,in_reply_to=?,"
                "reference_ids=?,version=version+1,updated_at=? WHERE draft_id=? AND version=?",
                (values["context_type"], values["reply_mail_message_id"], values["mail_account_id"],
                 values["from_address"], _json(values["to_addresses"]), _json(values["cc_addresses"]),
                 values["reply_to_address"], values["subject"], values["body_text"], values["in_reply_to"],
                 _json(values["reference_ids"]), now, draft_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise MailSendError("MAIL_DRAFT_VERSION_CONFLICT", "草稿已更新，请重新加载。", status=409)
            connection.execute(
                "UPDATE mail_send_previews SET invalidated_at=? WHERE draft_id=? AND invalidated_at IS NULL",
                (now, draft_id),
            )
        return self.get_draft(draft_id)

    def get_draft(self, draft_id: object) -> dict[str, Any]:
        with self._factory_provider().read_connection() as connection:
            row = connection.execute("SELECT * FROM mail_drafts WHERE draft_id=?", (str(draft_id or ""),)).fetchone()
        if row is None:
            raise MailSendError("MAIL_DRAFT_NOT_FOUND", "草稿不存在。", status=404)
        return self._draft_row(row)

    def delete_draft(self, draft_id: object, expected_version: object) -> dict[str, Any]:
        draft_id = str(draft_id or "").strip()
        if not isinstance(expected_version, int) or expected_version < 1:
            raise MailSendError("MAIL_DRAFT_VERSION_REQUIRED", "必须提供当前草稿版本。")
        now = _iso(self._now())
        with self._factory_provider().write_transaction() as connection:
            row = connection.execute("SELECT version,content_deleted_at FROM mail_drafts WHERE draft_id=?", (draft_id,)).fetchone()
            if row is None:
                raise MailSendError("MAIL_DRAFT_NOT_FOUND", "草稿不存在。", status=404)
            if int(row["version"]) != expected_version:
                raise MailSendError("MAIL_DRAFT_VERSION_CONFLICT", "草稿已更新，请重新加载。", status=409)
            attempt_count = int(connection.execute(
                "SELECT COUNT(*) FROM mail_send_attempts WHERE draft_id=?", (draft_id,)
            ).fetchone()[0])
            if attempt_count == 0:
                connection.execute("DELETE FROM mail_drafts WHERE draft_id=?", (draft_id,))
                return {"draft_id": draft_id, "deleted": True, "content_redacted": False}
            connection.execute(
                "UPDATE mail_drafts SET subject='',body_text='',to_addresses='[]',cc_addresses='[]',"
                "reply_to_address=NULL,content_deleted_at=?,updated_at=? WHERE draft_id=?",
                (now, now, draft_id),
            )
            connection.execute(
                "UPDATE mail_send_previews SET subject='',body_text='',to_addresses='[]',cc_addresses='[]',"
                "reply_to_address=NULL,invalidated_at=COALESCE(invalidated_at,?),content_deleted_at=? WHERE draft_id=?",
                (now, now, draft_id),
            )
            connection.execute(
                "UPDATE mail_send_authorizations SET consumed_at=COALESCE(consumed_at,?) WHERE draft_id=?",
                (now, draft_id),
            )
            return {"draft_id": draft_id, "deleted": True, "content_redacted": True}

    def create_preview(self, draft_id: object) -> dict[str, Any]:
        draft = self.get_draft(draft_id)
        if draft.get("content_deleted_at"):
            raise MailSendError("MAIL_DRAFT_CONTENT_DELETED", "草稿内容已删除。", status=409)
        now_dt = self._now()
        snapshot = {**draft, "draft_version": draft["version"]}
        content_hash = _snapshot_hash(snapshot)
        preview_id = f"preview_{uuid.uuid4().hex}"
        expires_at = _iso(now_dt + timedelta(seconds=PREVIEW_TTL_SECONDS))
        with self._factory_provider().write_transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM mail_send_previews WHERE draft_id=? AND draft_version=? AND content_hash=?",
                (draft["draft_id"], draft["version"], content_hash),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "INSERT INTO mail_send_previews(preview_id,draft_id,draft_version,mail_account_id,from_address,"
                    "to_addresses,cc_addresses,reply_to_address,subject,body_text,in_reply_to,reference_ids,"
                    "content_hash,expires_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (preview_id, draft["draft_id"], draft["version"], draft["mail_account_id"],
                     draft["from_address"], _json(draft["to_addresses"]), _json(draft["cc_addresses"]),
                     draft["reply_to_address"], draft["subject"], draft["body_text"], draft["in_reply_to"],
                     _json(draft["reference_ids"]), content_hash, expires_at, _iso(now_dt)),
                )
            else:
                preview_id = str(existing["preview_id"])
                connection.execute(
                    "UPDATE mail_send_previews SET expires_at=? WHERE preview_id=? AND invalidated_at IS NULL",
                    (expires_at, preview_id),
                )
        return self.get_preview(preview_id)

    def authorize_preview(self, preview_id: object, session_id: object, source: object) -> dict[str, Any]:
        preview = self.get_preview(preview_id)
        source = str(source or "").strip()
        if source == RESERVED_AUTHORIZATION_SOURCE:
            raise MailSendError("MAIL_FUTURE_AUTHORIZATION_DISABLED", "自动发信授权尚未启用。", status=403)
        if source not in ALLOWED_AUTHORIZATION_SOURCES:
            raise MailSendError("MAIL_AUTHORIZATION_SOURCE_INVALID", "发送授权来源无效。", status=403)
        now = self._now()
        if preview["invalidated_at"] or now >= _parse_iso(preview["expires_at"]):
            raise MailSendError("MAIL_PREVIEW_EXPIRED", "预览已失效，请重新生成。", status=409)
        draft = self.get_draft(preview["draft_id"])
        if draft["version"] != preview["draft_version"] or _snapshot_hash({**draft, "draft_version": draft["version"]}) != preview["content_hash"]:
            raise MailSendError("MAIL_PREVIEW_CHANGED", "草稿内容已变化，请重新预览。", status=409)
        token = f"mail_confirm_{secrets.token_urlsafe(32)}"
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        authorization_id = f"mail_auth_{uuid.uuid4().hex}"
        expires_at = _iso(now + timedelta(seconds=AUTHORIZATION_TTL_SECONDS))
        with self._factory_provider().write_transaction() as connection:
            connection.execute(
                "INSERT INTO mail_send_authorizations(authorization_id,preview_id,token_hash,session_hash,"
                "authorization_source,mail_account_id,draft_id,draft_version,preview_hash,envelope_hash,"
                "expires_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (authorization_id, preview["preview_id"], token_hash, session_hash(session_id), source,
                 preview["mail_account_id"], preview["draft_id"], preview["draft_version"], preview["content_hash"],
                 _envelope_hash(preview), expires_at, _iso(now)),
            )
        return {"authorization_id": authorization_id, "confirmation_token": token, "expires_at": expires_at,
                "authorization_source": source, "preview_id": preview["preview_id"]}

    def send(self, payload: Mapping[str, object], session_id: object) -> dict[str, Any]:
        preview_id = str(payload.get("preview_id") or "").strip()
        token = str(payload.get("confirmation_token") or "")
        idempotency_key = str(payload.get("idempotency_key") or "").strip()
        if not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
            raise MailSendError("MAIL_IDEMPOTENCY_KEY_INVALID", "幂等键无效。")
        attempt, should_execute = self._begin_attempt(preview_id, token, idempotency_key, session_id)
        if not should_execute:
            return attempt
        preview = self.get_preview(preview_id)
        account = self._account_resolver(preview["mail_account_id"])
        try:
            result = self._executor.send(account, preview, attempt["rfc_message_id"])
        except MailSendError as exc:
            result = SMTPExecutionResult("failed", "config", exc.code, tuple())
        except Exception:
            result = SMTPExecutionResult("unknown", "executor", "MAIL_SMTP_RESULT_UNKNOWN", tuple())
        self._finish_attempt(attempt["attempt_id"], result)
        return self.get_attempt(attempt["attempt_id"], session_id)

    def get_attempt(self, attempt_id: object, session_id: object) -> dict[str, Any]:
        with self._factory_provider().read_connection() as connection:
            row = connection.execute(
                "SELECT a.* FROM mail_send_attempts a JOIN mail_send_authorizations z "
                "ON z.authorization_id=a.authorization_id WHERE a.attempt_id=? AND z.session_hash=?",
                (str(attempt_id or ""), session_hash(session_id)),
            ).fetchone()
            if row is None:
                raise MailSendError("MAIL_SEND_ATTEMPT_NOT_FOUND", "发送记录不存在。", status=404)
            recipients = [dict(item) for item in connection.execute(
                "SELECT recipient_type,position,recipient_address,outcome,smtp_code,safe_error_code "
                "FROM mail_send_recipient_results WHERE attempt_id=? ORDER BY recipient_type,position",
                (row["attempt_id"],),
            )]
        result = dict(row)
        result["recipients"] = recipients
        return result

    def get_preview(self, preview_id: object) -> dict[str, Any]:
        with self._factory_provider().read_connection() as connection:
            row = connection.execute("SELECT * FROM mail_send_previews WHERE preview_id=?", (str(preview_id or ""),)).fetchone()
        if row is None:
            raise MailSendError("MAIL_PREVIEW_NOT_FOUND", "预览不存在。", status=404)
        result = dict(row)
        result["to_addresses"] = json.loads(result["to_addresses"])
        result["cc_addresses"] = json.loads(result["cc_addresses"])
        result["reference_ids"] = json.loads(result["reference_ids"])
        return result

    def _begin_attempt(self, preview_id: str, token: str, idempotency_key: str, session_id: object) -> tuple[dict[str, Any], bool]:
        now_dt = self._now()
        now = _iso(now_dt)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        factory = self._factory_provider()
        with factory.write_transaction() as connection:
            existing = connection.execute("SELECT * FROM mail_send_attempts WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing is not None:
                if str(existing["preview_id"]) != preview_id:
                    raise MailSendError("MAIL_IDEMPOTENCY_CONFLICT", "幂等键已用于其他发送。", status=409)
                existing_session = connection.execute(
                    "SELECT session_hash FROM mail_send_authorizations WHERE authorization_id=?",
                    (existing["authorization_id"],),
                ).fetchone()
                if existing_session is None or existing_session["session_hash"] != session_hash(session_id):
                    raise MailSendError("MAIL_CONFIRMATION_SESSION_MISMATCH", "发送记录不属于当前会话。", status=403)
                return dict(existing), False
            authorization = connection.execute(
                "SELECT * FROM mail_send_authorizations WHERE preview_id=? AND token_hash=?",
                (preview_id, token_hash),
            ).fetchone()
            if authorization is None:
                raise MailSendError("MAIL_CONFIRMATION_INVALID", "发送确认无效。", status=403)
            if authorization["authorization_source"] not in ALLOWED_AUTHORIZATION_SOURCES:
                raise MailSendError("MAIL_FUTURE_AUTHORIZATION_DISABLED", "自动发信授权尚未启用。", status=403)
            if authorization["consumed_at"]:
                raise MailSendError("MAIL_CONFIRMATION_USED", "发送确认已使用。", status=409)
            if authorization["session_hash"] != session_hash(session_id):
                raise MailSendError("MAIL_CONFIRMATION_SESSION_MISMATCH", "发送确认不属于当前会话。", status=403)
            if now_dt >= _parse_iso(authorization["expires_at"]):
                raise MailSendError("MAIL_CONFIRMATION_EXPIRED", "发送确认已过期。", status=403)
            preview_row = connection.execute("SELECT * FROM mail_send_previews WHERE preview_id=?", (preview_id,)).fetchone()
            draft_row = connection.execute("SELECT * FROM mail_drafts WHERE draft_id=?", (authorization["draft_id"],)).fetchone()
            if preview_row is None or draft_row is None or preview_row["invalidated_at"]:
                raise MailSendError("MAIL_PREVIEW_CHANGED", "发送预览已失效。", status=409)
            preview = self._preview_row(preview_row)
            draft = self._draft_row(draft_row)
            if (
                draft["version"] != authorization["draft_version"]
                or preview["content_hash"] != authorization["preview_hash"]
                or _snapshot_hash(preview) != preview["content_hash"]
                or _snapshot_hash({**draft, "draft_version": draft["version"]}) != preview["content_hash"]
                or _envelope_hash(preview) != authorization["envelope_hash"]
            ):
                raise MailSendError("MAIL_PREVIEW_CHANGED", "发送内容已变化，请重新确认。", status=409)
            attempt_id = f"send_attempt_{uuid.uuid4().hex}"
            message_id = make_msgid(domain="kolconnect.local")
            connection.execute("UPDATE mail_send_authorizations SET consumed_at=? WHERE authorization_id=? AND consumed_at IS NULL",
                               (now, authorization["authorization_id"]))
            connection.execute(
                "INSERT INTO mail_send_attempts(attempt_id,preview_id,authorization_id,idempotency_key,rfc_message_id,"
                "draft_id,draft_version,mail_account_id,authorization_source,outcome,smtp_stage,started_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'started','queued',?,?)",
                (attempt_id, preview_id, authorization["authorization_id"], idempotency_key, message_id,
                 authorization["draft_id"], authorization["draft_version"], authorization["mail_account_id"],
                 authorization["authorization_source"], now, now),
            )
            for kind, addresses in (("to", preview["to_addresses"]), ("cc", preview["cc_addresses"])):
                for position, address in enumerate(addresses):
                    connection.execute(
                        "INSERT INTO mail_send_recipient_results(attempt_id,position,recipient_type,recipient_address,outcome) "
                        "VALUES (?,?,?,?, 'pending')",
                        (attempt_id, position, kind, address),
                    )
            return dict(connection.execute("SELECT * FROM mail_send_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()), True

    def _finish_attempt(self, attempt_id: str, result: SMTPExecutionResult) -> None:
        if result.outcome not in ATTEMPT_OUTCOMES - {"started"}:
            result = SMTPExecutionResult("unknown", "executor", "MAIL_SMTP_RESULT_UNKNOWN", tuple())
        now = _iso(self._now())
        with self._factory_provider().write_transaction() as connection:
            connection.execute(
                "UPDATE mail_send_attempts SET outcome=?,smtp_stage=?,safe_error_code=?,completed_at=?,updated_at=? "
                "WHERE attempt_id=? AND outcome='started'",
                (result.outcome, result.stage, result.safe_error_code, now, now, attempt_id),
            )
            for row in result.recipients:
                connection.execute(
                    "UPDATE mail_send_recipient_results SET outcome=?,smtp_code=?,safe_error_code=? "
                    "WHERE attempt_id=? AND recipient_type=? AND position=?",
                    (row["outcome"], row.get("smtp_code"), row.get("safe_error_code"), attempt_id,
                     row["recipient_type"], row["position"]),
                )
            fallback = "unknown" if result.outcome == "unknown" else "rejected" if result.outcome == "failed" else "accepted"
            connection.execute(
                "UPDATE mail_send_recipient_results SET outcome=?,safe_error_code=COALESCE(safe_error_code,?) "
                "WHERE attempt_id=? AND outcome='pending'",
                (fallback, result.safe_error_code, attempt_id),
            )

    def _validated_draft(self, payload: Mapping[str, object]) -> dict[str, Any]:
        context_type = str(payload.get("context_type") or "initial").strip().lower()
        if context_type not in {"initial", "reply"}:
            raise MailSendError("MAIL_DRAFT_CONTEXT_INVALID", "邮件上下文无效。")
        mail_account_id = str(payload.get("mail_account_id") or "").strip()
        if not mail_account_id:
            raise MailSendError("MAIL_ACCOUNT_REQUIRED", "请选择发送邮箱。")
        account = self._account_resolver(mail_account_id)
        if not account.get("enabled"):
            raise MailSendError("MAIL_ACCOUNT_DISABLED", "发送邮箱未启用。", status=409)
        from_address = normalize_address(payload.get("from_address"), name="发件地址")
        if from_address != normalize_address(account.get("email"), name="已配置发件地址"):
            raise MailSendError("MAIL_FROM_MISMATCH", "发件地址与已配置邮箱不一致。", status=409)
        to_addresses = normalize_addresses(payload.get("to_addresses"), name="收件地址", required=True)
        cc_addresses = normalize_addresses(payload.get("cc_addresses", []), name="抄送地址", required=False)
        if set(to_addresses) & set(cc_addresses):
            raise MailSendError("MAIL_RECIPIENT_DUPLICATE", "同一地址不能同时出现在收件人与抄送中。")
        reply_to_raw = payload.get("reply_to_address")
        reply_to = normalize_address(reply_to_raw, name="Reply-To") if str(reply_to_raw or "").strip() else None
        subject = _safe_text(payload.get("subject"), name="主题", maximum=SUBJECT_LIMIT, allow_empty=False).strip()
        body = str(payload.get("body_text") or "")
        if not body.strip():
            raise MailSendError("MAIL_BODY_REQUIRED", "邮件正文不能为空。")
        if len(body.encode("utf-8")) > BODY_LIMIT:
            raise MailSendError("MAIL_BODY_TOO_LARGE", "邮件正文超出大小限制。")
        reply_message_id = str(payload.get("reply_mail_message_id") or "").strip() or None
        in_reply_to = None
        references: list[str] = []
        if context_type == "reply":
            if not reply_message_id:
                raise MailSendError("MAIL_REPLY_FACT_REQUIRED", "回复邮件必须关联已有邮件事实。")
            with self._factory_provider().read_connection() as connection:
                row = connection.execute(
                    "SELECT mail_account_id,rfc_message_id,reference_ids FROM mail_messages WHERE mail_message_id=?",
                    (reply_message_id,),
                ).fetchone()
            if row is None or str(row["mail_account_id"]) != mail_account_id:
                raise MailSendError("MAIL_REPLY_FACT_MISMATCH", "回复邮件与发送邮箱不匹配。", status=409)
            in_reply_to = _message_id(row["rfc_message_id"])
            references = _reference_ids(row["reference_ids"])
            if in_reply_to not in references:
                references.append(in_reply_to)
        elif reply_message_id:
            raise MailSendError("MAIL_REPLY_CONTEXT_INVALID", "初次建联不能绑定回复邮件。")
        return {
            "context_type": context_type, "reply_mail_message_id": reply_message_id,
            "mail_account_id": mail_account_id, "from_address": from_address,
            "to_addresses": to_addresses, "cc_addresses": cc_addresses, "reply_to_address": reply_to,
            "subject": subject, "body_text": body, "in_reply_to": in_reply_to, "reference_ids": references,
        }

    @staticmethod
    def _draft_row(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["to_addresses"] = json.loads(result["to_addresses"])
        result["cc_addresses"] = json.loads(result["cc_addresses"])
        result["reference_ids"] = json.loads(result["reference_ids"])
        return result

    @staticmethod
    def _preview_row(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["to_addresses"] = json.loads(result["to_addresses"])
        result["cc_addresses"] = json.loads(result["cc_addresses"])
        result["reference_ids"] = json.loads(result["reference_ids"])
        return result
