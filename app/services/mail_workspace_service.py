"""On-demand mail body reads and strict Sent reconciliation for M9.2-D."""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import re
from typing import Any, Callable, Mapping

from services.mail_auth_service import MailAuthenticationError
from services.mail_connection_service import open_imap_connection
from services.mail_inbox_facts import _fetch_payload, _uidvalidity, mail_account_identity
from services.mail_send_service import MailSendError


MAX_RAW_BODY_BYTES = 2 * 1024 * 1024
MAX_BODY_TEXT_CHARS = 200_000
MESSAGE_SIZE_PATTERN = re.compile(r"RFC822\.SIZE\s+(\d+)", re.IGNORECASE)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.suppressed += 1
        elif not self.suppressed and tag.lower() in {"br", "p", "div", "li", "tr", "blockquote"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self.suppressed:
            self.suppressed -= 1
        elif not self.suppressed and tag.lower() in {"p", "div", "li", "tr", "blockquote"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.suppressed:
            self.parts.append(data)

    def text(self) -> str:
        value = "".join(self.parts).replace("\r", "")
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


def _part_text(part) -> str:
    try:
        return part.get_content()
    except (LookupError, UnicodeError, ValueError):
        payload = part.get_payload(decode=True) or b""
        charset = part.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")


def safe_message_text(raw: bytes) -> tuple[str, str]:
    if len(raw) > MAX_RAW_BODY_BYTES:
        raise MailSendError("MAIL_BODY_TOO_LARGE", "邮件正文超出安全读取限制。", status=413)
    message = BytesParser(policy=policy.default).parsebytes(raw)
    plain: list[str] = []
    html: list[str] = []
    parts = message.walk() if message.is_multipart() else (message,)
    for part in parts:
        if part.is_multipart() or part.get_content_disposition() == "attachment":
            continue
        content_type = part.get_content_type().lower()
        if content_type == "text/plain":
            plain.append(_part_text(part))
        elif content_type == "text/html":
            parser = _HTMLTextExtractor()
            parser.feed(_part_text(part))
            html.append(parser.text())
    source = "plain" if any(item.strip() for item in plain) else "html_text"
    text = "\n\n".join(item.strip() for item in (plain if source == "plain" else html) if item.strip())
    if len(text) > MAX_BODY_TEXT_CHARS:
        text = text[:MAX_BODY_TEXT_CHARS]
    return text, source


def _message_size(mailbox, uid: str) -> int:
    status, response = mailbox.uid("fetch", uid, "(RFC822.SIZE)")
    if status != "OK" or not response:
        raise RuntimeError("IMAP message size is unavailable.")
    for item in response:
        metadata = item[0] if isinstance(item, tuple) and item else item
        if isinstance(metadata, bytes):
            metadata = metadata.decode("ascii", errors="replace")
        match = MESSAGE_SIZE_PATTERN.search(str(metadata or ""))
        if match:
            return int(match.group(1))
    raise RuntimeError("IMAP message size is unavailable.")


class MailWorkspaceService:
    def __init__(self, factory_provider: Callable[[], Any], account_resolver: Callable[[str], Mapping[str, object]], *, imap_factory=None) -> None:
        self._factory_provider = factory_provider
        self._account_resolver = account_resolver
        self._imap_factory = imap_factory

    def read_body(self, mail_message_id: object) -> dict[str, Any]:
        identifier = str(mail_message_id or "").strip()
        if not identifier:
            raise MailSendError("MAIL_MESSAGE_ID_REQUIRED", "请选择要读取的邮件。")
        with self._factory_provider().read_connection() as connection:
            rows = connection.execute(
                "SELECT m.mail_message_id,m.mail_account_id,m.subject,m.rfc_message_id,m.in_reply_to,m.reference_ids,"
                "o.uidvalidity,o.imap_uid,s.folder_name,s.uidvalidity AS current_uidvalidity "
                "FROM mail_messages m JOIN mail_message_observations o ON o.mail_message_id=m.mail_message_id "
                "JOIN mailbox_sync_states s ON s.mailbox_id=o.mailbox_id WHERE m.mail_message_id=?",
                (identifier,),
            ).fetchall()
        if not rows:
            raise MailSendError("MAIL_MESSAGE_NOT_FOUND", "邮件事实不存在。", status=404)
        if len(rows) != 1:
            raise MailSendError("MAIL_BODY_OBSERVATION_AMBIGUOUS", "邮件存在多个观察位置，请重新同步后再试。", status=409)
        row = dict(rows[0])
        if not row["current_uidvalidity"] or str(row["current_uidvalidity"]) != str(row["uidvalidity"]):
            raise MailSendError("MAIL_BODY_UIDVALIDITY_CHANGED", "邮箱文件夹身份已变化，请重新同步邮件。", status=409)
        account = dict(self._account_resolver(row["mail_account_id"]))
        resolved_id, _identity = mail_account_identity(account)
        if resolved_id != row["mail_account_id"]:
            raise MailSendError("MAIL_ACCOUNT_MISMATCH", "邮箱账户身份已变化。", status=409)
        try:
            mailbox, _connection = open_imap_connection(
                account, folder=row["folder_name"], imap_factory=self._imap_factory, timeout=15
            )
        except MailAuthenticationError as exc:
            raise MailSendError("MAIL_BODY_CONNECTION_FAILED", "无法安全读取邮件正文，请检查邮箱连接。", status=503) from exc
        try:
            try:
                if _uidvalidity(mailbox) != str(row["uidvalidity"]):
                    raise MailSendError("MAIL_BODY_UIDVALIDITY_CHANGED", "邮箱文件夹身份已变化，请重新同步邮件。", status=409)
                if _message_size(mailbox, str(row["imap_uid"])) > MAX_RAW_BODY_BYTES:
                    raise MailSendError("MAIL_BODY_TOO_LARGE", "邮件正文超出安全读取限制。", status=413)
                raw, _metadata = _fetch_payload(mailbox, str(row["imap_uid"]), "(BODY.PEEK[])")
                body_text, source = safe_message_text(raw)
            except MailSendError:
                raise
            except (RuntimeError, UnicodeError, ValueError) as exc:
                raise MailSendError("MAIL_BODY_READ_FAILED", "邮件正文读取失败，请重新同步后再试。", status=503) from exc
        finally:
            try:
                mailbox.logout()
            except Exception:
                pass
        return {
            "mail_message_id": identifier,
            "subject": row["subject"],
            "rfc_message_id": row["rfc_message_id"],
            "in_reply_to": row["in_reply_to"],
            "reference_ids": row["reference_ids"],
            "body_text": body_text,
            "body_source": source,
            "attachments_omitted": True,
            "persisted": False,
        }

    def reconcile_sent_attempts(self, mail_account_id: object) -> dict[str, int]:
        return reconcile_sent_attempts(self._factory_provider(), mail_account_id)


def reconcile_sent_attempts(factory, mail_account_id: object) -> dict[str, int]:
    account_id = str(mail_account_id or "").strip()
    if not account_id:
        raise MailSendError("MAIL_ACCOUNT_REQUIRED", "请选择邮箱账户。")
    counts = {"reconciled": 0, "ambiguous": 0, "unmatched": 0, "pending": 0}
    with factory.write_transaction() as connection:
        attempts = connection.execute(
                "SELECT attempt_id,rfc_message_id,outcome,reconciliation_status FROM mail_send_attempts "
                "WHERE mail_account_id=? AND reconciliation_status IN ('pending','unmatched','ambiguous')",
                (account_id,),
        ).fetchall()
        for attempt in attempts:
            if attempt["outcome"] not in {"accepted", "unknown"}:
                counts["pending"] += 1
                continue
            matches = connection.execute(
                    "SELECT o.observation_id FROM mail_messages m "
                    "JOIN mail_message_observations o ON o.mail_message_id=m.mail_message_id "
                    "JOIN mailbox_sync_states s ON s.mailbox_id=o.mailbox_id "
                    "WHERE m.mail_account_id=? AND s.role='sent' AND m.rfc_message_id=? ORDER BY o.observation_id",
                    (account_id, attempt["rfc_message_id"]),
            ).fetchall()
            if len(matches) == 1:
                status, observation_id = "reconciled", matches[0]["observation_id"]
            elif len(matches) > 1:
                status, observation_id = "ambiguous", None
            else:
                status, observation_id = "unmatched", None
            connection.execute(
                    "UPDATE mail_send_attempts SET reconciliation_status=?,sent_observation_id=?,updated_at=CURRENT_TIMESTAMP WHERE attempt_id=?",
                    (status, observation_id, attempt["attempt_id"]),
            )
            counts[status] += 1
    return counts
