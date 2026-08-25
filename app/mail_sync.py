from __future__ import annotations

import imaplib
import json
import re
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import Message
from email.policy import default
from email.utils import parsedate_to_datetime, parseaddr
from html import unescape
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from runtime_paths import (
    atomic_write_json,
    get_app_data_dir,
    json_backup_path,
    load_json_with_backup,
)
from feishu_relation import relation_record_ids

DATA_DIR = get_app_data_dir()
MAIL_MESSAGES_FILE = DATA_DIR / "mail_messages.json"
MAX_MESSAGES_PER_ACCOUNT = 20
MAX_CACHED_MESSAGES = 5000
MAIL_CACHE_RETENTION_DAYS = 180

CRM_FIELD_STAGE = "合作阶段"
CRM_FIELD_LAST_CONTACT_AT = "最近联系时间"

CRM_STAGE_NOT_CONTACTED = "未联系"
CRM_STAGE_CONTACTED = "已联系"
CRM_STAGE_FOLLOWING = "跟进中"

# Four-table mail matching reads account emails, then resolves the linked creator.
FOUR_TABLE_ACCOUNT_FIELD_UID = "账号唯一ID"
FOUR_TABLE_ACCOUNT_FIELD_EMAIL = "账号邮箱"
FOUR_TABLE_ACCOUNT_FIELD_PLATFORM = "平台"
FOUR_TABLE_ACCOUNT_FIELD_CREATOR = "达人"
FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS = "归属状态"
FOUR_TABLE_CREATOR_FIELD_ID = "达人ID"
FOUR_TABLE_CREATOR_FIELD_NAME = "达人名称"
FOUR_TABLE_CREATOR_FIELD_STAGE = "合作阶段"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clone_default_store() -> dict:
    return {
        "version": 1,
        "updated_at": "",
        "accounts": {},
        "messages": [],
    }


def normalize_mail_message(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "id": str(raw.get("id") or ""),
        "account_key": str(raw.get("account_key") or ""),
        "account_name": str(raw.get("account_name") or ""),
        "imap_uid": str(raw.get("imap_uid") or ""),
        "message_id": str(raw.get("message_id") or ""),
        "from_email": str(raw.get("from_email") or "").strip().lower(),
        "from_name": str(raw.get("from_name") or ""),
        "to_email": str(raw.get("to_email") or "").strip().lower(),
        "subject": str(raw.get("subject") or ""),
        "snippet": str(raw.get("snippet") or ""),
        "received_at": str(raw.get("received_at") or ""),
        "is_unread": bool(raw.get("is_unread")),
        "matched_creator_uid": str(raw.get("matched_creator_uid") or ""),
        "matched_creator_id": str(raw.get("matched_creator_id") or ""),
        "matched_creator_email": str(raw.get("matched_creator_email") or "").strip().lower(),
        "matched_creator_name": str(raw.get("matched_creator_name") or ""),
        "matched_platform": str(raw.get("matched_platform") or ""),
        "matched_stage": str(raw.get("matched_stage") or ""),
        "matched_account_uid": str(raw.get("matched_account_uid") or ""),
        "matched_account_record_id": str(raw.get("matched_account_record_id") or ""),
        "matched_creator_record_id": str(raw.get("matched_creator_record_id") or ""),
        "match_status": str(raw.get("match_status") or "unmatched"),
        "reply_status": str(raw.get("reply_status") or "unmatched"),
        "synced_at": str(raw.get("synced_at") or ""),
        "crm_synced": bool(raw.get("crm_synced")),
        "crm_synced_at": str(raw.get("crm_synced_at") or ""),
        "crm_sync_status": str(raw.get("crm_sync_status") or "pending"),
        "crm_sync_error": str(raw.get("crm_sync_error") or ""),
        "crm_sync_record_id": str(raw.get("crm_sync_record_id") or ""),
        "crm_sync_action": str(raw.get("crm_sync_action") or ""),
        "sync_target": str(raw.get("sync_target") or ""),
    }


def load_mail_messages() -> dict:
    data, source_path = load_json_with_backup(MAIL_MESSAGES_FILE)
    if data is None:
        if MAIL_MESSAGES_FILE.exists() or json_backup_path(MAIL_MESSAGES_FILE).exists():
            print("邮件缓存损坏且无法恢复，已使用空缓存。")
        return clone_default_store()
    if source_path == json_backup_path(MAIL_MESSAGES_FILE):
        print("邮件缓存损坏，已从 mail_messages.json.bak 恢复。")
    store = clone_default_store()
    if isinstance(data, dict):
        store["version"] = int(data.get("version") or 1)
        store["updated_at"] = str(data.get("updated_at") or "")
        store["accounts"] = data.get("accounts") if isinstance(data.get("accounts"), dict) else {}
        raw_messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        store["messages"] = [normalize_mail_message(item) for item in raw_messages if isinstance(item, dict)]
    return store


def _message_datetime(message: dict) -> datetime | None:
    value = str(message.get("received_at") or message.get("synced_at") or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _is_prunable_message(message: dict) -> bool:
    protected_statuses = {"unmatched", "ambiguous", "unassigned_account", "failed", "pending"}
    if str(message.get("match_status") or "").strip() in protected_statuses:
        return False
    if str(message.get("reply_status") or "").strip() in protected_statuses:
        return False
    if not message.get("crm_synced"):
        return False
    if str(message.get("crm_sync_status") or "").strip() != "synced":
        return False
    if str(message.get("crm_sync_error") or "").strip():
        return False
    return True


def prune_mail_messages(messages: list[dict], now: datetime | None = None) -> tuple[list[dict], int]:
    """Prune only successfully handled mail while preserving unresolved records."""
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAIL_CACHE_RETENTION_DAYS)
    normalized = [normalize_mail_message(item) for item in messages if isinstance(item, dict)]
    retained: list[dict] = []
    removed = 0
    for message in normalized:
        timestamp = _message_datetime(message)
        if _is_prunable_message(message) and timestamp is not None and timestamp < cutoff:
            removed += 1
            continue
        retained.append(message)

    if len(retained) <= MAX_CACHED_MESSAGES:
        return retained, removed

    candidates = sorted(
        (
            (index, _message_datetime(message))
            for index, message in enumerate(retained)
            if _is_prunable_message(message) and _message_datetime(message) is not None
        ),
        key=lambda item: item[1],
    )
    remove_indexes = {index for index, _timestamp in candidates[: max(0, len(retained) - MAX_CACHED_MESSAGES)]}
    if remove_indexes:
        retained = [message for index, message in enumerate(retained) if index not in remove_indexes]
        removed += len(remove_indexes)
    return retained, removed


def save_mail_messages(data: dict) -> None:
    payload = clone_default_store()
    payload.update(
        {
            "version": int(data.get("version") or 1),
            "updated_at": str(data.get("updated_at") or utc_now_iso()),
            "accounts": data.get("accounts") if isinstance(data.get("accounts"), dict) else {},
            "messages": [normalize_mail_message(item) for item in data.get("messages", []) if isinstance(item, dict)],
        }
    )
    payload["messages"], _removed_count = prune_mail_messages(payload["messages"])
    atomic_write_json(MAIL_MESSAGES_FILE, payload)


def build_account_key(account: dict) -> str:
    provider = str(account.get("provider") or "custom").strip().lower() or "custom"
    identity = str(account.get("email") or account.get("username") or "").strip().lower()
    return f"{provider}::{identity}"


def build_message_id(account_key: str, imap_uid: str) -> str:
    return f"{account_key}::{imap_uid}"


def post_json(url: str, payload: dict, headers: dict[str, str] | None = None, timeout: int = 15) -> dict:
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=request_headers, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(url: str, params: dict | None = None, headers: dict[str, str] | None = None, timeout: int = 15) -> dict:
    final_url = f"{url}?{urlencode(params)}" if params else url
    request = Request(final_url, headers=headers or {}, method="GET")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def decode_mime_value(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return str(value).strip()


def to_iso_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return ""


def iso_to_epoch_ms(value: str | None) -> int | None:
    if not value:
        return None
    try:
        normalized = str(value).strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def get_message_body_text(msg: Message) -> str:
    if msg.is_multipart():
        text_parts: list[str] = []
        html_parts: list[str] = []
        for part in msg.walk():
            disposition = (part.get_content_disposition() or "").lower()
            if disposition == "attachment":
                continue
            content_type = (part.get_content_type() or "").lower()
            if content_type == "text/plain":
                try:
                    text_parts.append(part.get_content().strip())
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(payload.decode(charset, errors="replace").strip())
            elif content_type == "text/html":
                try:
                    html_parts.append(part.get_content())
                except Exception:
                    payload = part.get_payload(decode=True) or b""
                    charset = part.get_content_charset() or "utf-8"
                    html_parts.append(payload.decode(charset, errors="replace"))
        if text_parts:
            return "\n".join(part for part in text_parts if part).strip()
        if html_parts:
            return html_to_text("\n".join(html_parts))
        return ""

    content_type = (msg.get_content_type() or "").lower()
    if content_type == "text/html":
        try:
            return html_to_text(msg.get_content())
        except Exception:
            payload = msg.get_payload(decode=True) or b""
            charset = msg.get_content_charset() or "utf-8"
            return html_to_text(payload.decode(charset, errors="replace"))
    try:
        return str(msg.get_content() or "").strip()
    except Exception:
        payload = msg.get_payload(decode=True) or b""
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace").strip()


def build_snippet(text: str, max_length: int = 240) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= max_length:
        return compact
    return compact[: max_length - 1].rstrip() + "…"


def parse_email_message(account_key: str, account: dict, imap_uid: str, raw_bytes: bytes, flags: list[str]) -> dict:
    msg = message_from_bytes(raw_bytes, policy=default)
    from_name, from_email = parseaddr(str(msg.get("From") or ""))
    _, to_email = parseaddr(str(msg.get("To") or ""))
    body_text = get_message_body_text(msg)
    return {
        "id": build_message_id(account_key, imap_uid),
        "account_key": account_key,
        "account_name": str(account.get("name") or "").strip(),
        "imap_uid": str(imap_uid or "").strip(),
        "message_id": decode_mime_value(msg.get("Message-ID")),
        "from_email": from_email.strip().lower(),
        "from_name": decode_mime_value(from_name),
        "to_email": to_email.strip().lower(),
        "subject": decode_mime_value(msg.get("Subject")),
        "snippet": build_snippet(body_text),
        "received_at": to_iso_datetime(msg.get("Date")),
        "is_unread": "\\Seen" not in (flags or []),
        "matched_creator_uid": "",
        "matched_creator_id": "",
        "matched_creator_email": "",
        "matched_creator_name": "",
        "matched_platform": "",
        "matched_stage": "",
        "matched_account_uid": "",
        "matched_account_record_id": "",
        "matched_creator_record_id": "",
        "match_status": "unmatched",
        "reply_status": "unmatched",
        "synced_at": utc_now_iso(),
        "crm_synced": False,
        "crm_synced_at": "",
        "crm_sync_status": "pending",
        "crm_sync_error": "",
        "crm_sync_record_id": "",
        "crm_sync_action": "",
        "sync_target": "",
    }


def _split_email_candidates(value: object) -> list[str]:
    """Normalize text or list-based Feishu email values for exact lookup only."""
    values = value if isinstance(value, list) else [value]
    emails: list[str] = []
    for raw in values:
        for candidate in re.split(r"[,，;；\n]+", str(raw or "")):
            email = candidate.strip().lower()
            if email and email not in emails:
                emails.append(email)
    return emails


def _relation_record_ids(value: object) -> list[str]:
    """Read Feishu relation values without inferring records from display text."""
    return relation_record_ids(value)


def _four_table_access_token(config: dict) -> str:
    token_data = post_json(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        {"app_id": config["app_id"], "app_secret": config["app_secret"]},
        timeout=10,
    )
    access_token = str(token_data.get("tenant_access_token") or "").strip()
    if not access_token:
        raise RuntimeError(f"Feishu token 获取失败: {token_data}")
    return access_token


def fetch_four_table_records(config: dict, table_id: str, headers: dict[str, str]) -> list[dict]:
    """Read every record in one configured four-table CRM table."""
    list_url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{config['app_token']}/tables/{table_id}/records"
    page_token = ""
    records: list[dict] = []
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        data = get_json(list_url, params=params, headers=headers, timeout=15)
        if data.get("code") != 0:
            raise RuntimeError(f"Feishu four-table read failed: {data}")
        payload = data.get("data") or {}
        records.extend(payload.get("items") or [])
        if not payload.get("has_more"):
            break
        page_token = str(payload.get("page_token") or "").strip()
        if not page_token:
            break
    return records


def fetch_four_table_match_records(config: dict) -> tuple[list[dict], list[dict]]:
    """Read account and creator tables for mailbox matching without writing Feishu."""
    required = ("app_id", "app_secret", "app_token", "creator_table_id", "account_table_id")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"四表飞书配置不完整: {', '.join(missing)}")
    headers = {"Authorization": f"Bearer {_four_table_access_token(config)}"}
    account_records = fetch_four_table_records(config, config["account_table_id"], headers)
    creator_records = fetch_four_table_records(config, config["creator_table_id"], headers)
    return account_records, creator_records


def build_four_table_email_index(account_records: list[dict]) -> dict[str, list[dict]]:
    """Build exact email -> account-record candidates from the creator account table."""
    index: dict[str, list[dict]] = {}
    for item in account_records:
        fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
        record_id = str(item.get("record_id") or "").strip()
        if not record_id:
            continue
        entry = {
            "record_id": record_id,
            "account_uid": str(fields.get(FOUR_TABLE_ACCOUNT_FIELD_UID) or "").strip(),
            "platform": str(fields.get(FOUR_TABLE_ACCOUNT_FIELD_PLATFORM) or "").strip(),
            "creator_record_ids": _relation_record_ids(fields.get(FOUR_TABLE_ACCOUNT_FIELD_CREATOR)),
            "ownership_status": str(fields.get(FOUR_TABLE_ACCOUNT_FIELD_OWNERSHIP_STATUS) or "").strip(),
        }
        for email in _split_email_candidates(fields.get(FOUR_TABLE_ACCOUNT_FIELD_EMAIL)):
            index.setdefault(email, []).append(entry)
    return index


def _clear_four_table_match(item: dict, match_status: str) -> dict:
    item["matched_creator_uid"] = ""  # Preserve the historical cache field without using it for four-table matching.
    item["matched_creator_id"] = ""
    item["matched_creator_email"] = ""
    item["matched_creator_name"] = ""
    item["matched_platform"] = ""
    item["matched_stage"] = ""
    item["matched_account_uid"] = ""
    item["matched_account_record_id"] = ""
    item["matched_creator_record_id"] = ""
    item["match_status"] = match_status
    item["reply_status"] = "unmatched"
    return item


def match_messages_to_four_tables(messages: list[dict], account_records: list[dict], creator_records: list[dict]) -> list[dict]:
    """Match sender email to account email, then resolve exactly one linked creator."""
    account_index = build_four_table_email_index(account_records)
    creators_by_record_id = {
        str(item.get("record_id") or "").strip(): item.get("fields") or {}
        for item in creator_records
        if str(item.get("record_id") or "").strip()
    }
    matched_messages: list[dict] = []

    for message in messages:
        item = normalize_mail_message(message)
        sender = str(item.get("from_email") or "").strip().lower()
        candidates = account_index.get(sender, [])
        if not candidates:
            matched_messages.append(_clear_four_table_match(item, "unmatched"))
            continue

        resolved: list[tuple[dict, str, dict]] = []
        has_unassigned_candidate = False
        for account in candidates:
            creator_ids = account["creator_record_ids"]
            if account["ownership_status"] != "已归属" or len(creator_ids) != 1:
                has_unassigned_candidate = True
                continue
            creator_record_id = creator_ids[0]
            creator_fields = creators_by_record_id.get(creator_record_id)
            if creator_fields is None:
                has_unassigned_candidate = True
                continue
            resolved.append((account, creator_record_id, creator_fields))

        if not resolved:
            matched_messages.append(_clear_four_table_match(item, "unassigned_account"))
            continue

        creator_record_ids = {creator_record_id for _account, creator_record_id, _fields in resolved}
        if has_unassigned_candidate or len(creator_record_ids) != 1:
            matched_messages.append(_clear_four_table_match(item, "ambiguous"))
            continue

        creator_record_id = next(iter(creator_record_ids))
        account, _creator_record_id, creator_fields = resolved[0]
        match_status = "matched" if len(resolved) == 1 else "matched_multi_account"
        item["matched_creator_uid"] = ""
        item["matched_creator_id"] = str(creator_fields.get(FOUR_TABLE_CREATOR_FIELD_ID) or "").strip()
        item["matched_creator_email"] = sender
        item["matched_creator_name"] = str(creator_fields.get(FOUR_TABLE_CREATOR_FIELD_NAME) or "").strip()
        item["matched_platform"] = ", ".join(sorted({entry[0]["platform"] for entry in resolved if entry[0]["platform"]}))
        item["matched_stage"] = str(creator_fields.get(FOUR_TABLE_CREATOR_FIELD_STAGE) or "").strip()
        item["matched_account_uid"] = account["account_uid"]
        item["matched_account_record_id"] = account["record_id"]
        item["matched_creator_record_id"] = creator_record_id
        item["match_status"] = match_status
        item["reply_status"] = "matched"
        matched_messages.append(item)
    return matched_messages


def sync_one_mail_account(account: dict, options: dict, existing_data: dict) -> dict:
    account_key = build_account_key(account)
    host = str(account.get("imap_host") or "").strip()
    username = str(account.get("username") or "").strip()
    password = str(account.get("password") or "")
    port = int(str(account.get("imap_port") or "993").strip() or "993")
    if not host or not username or not password:
        raise RuntimeError("IMAP 配置不完整。")

    limit = min(int(options.get("limit_per_account") or MAX_MESSAGES_PER_ACCOUNT), MAX_MESSAGES_PER_ACCOUNT)
    mailbox = None
    result = {
        "account_key": account_key,
        "account_name": str(account.get("name") or "").strip(),
        "fetched": 0,
        "new": 0,
        "messages": [],
        "errors": [],
    }
    existing_ids = {str(item.get("id") or "") for item in existing_data.get("messages", []) if isinstance(item, dict)}
    try:
        mailbox = imaplib.IMAP4_SSL(host, port, timeout=15) if port == 993 else imaplib.IMAP4(host, port, timeout=15)
        if port != 993 and hasattr(mailbox, "starttls"):
            mailbox.starttls()
        mailbox.login(username, password)
        mailbox.select("INBOX", readonly=True)
        status, search_data = mailbox.uid("search", None, "ALL")
        if status != "OK":
            raise RuntimeError("IMAP 检索失败。")
        uid_list = [item.decode("utf-8", errors="ignore") for item in (search_data[0] or b"").split() if item]
        target_uids = uid_list[-limit:]
        result["fetched"] = len(target_uids)
        for uid in reversed(target_uids):
            fetch_status, fetch_data = mailbox.uid("fetch", uid, "(RFC822 FLAGS)")
            if fetch_status != "OK" or not fetch_data:
                continue
            raw_message = b""
            flags: list[str] = []
            for item in fetch_data:
                if not item:
                    continue
                if isinstance(item, tuple):
                    meta = item[0].decode("utf-8", errors="ignore") if isinstance(item[0], bytes) else str(item[0])
                    match = re.search(r"FLAGS \((.*?)\)", meta)
                    if match:
                        flags = [flag.strip() for flag in match.group(1).split() if flag.strip()]
                    raw_message = item[1] or b""
            if not raw_message:
                continue
            message = parse_email_message(account_key, account, uid, raw_message, flags)
            if message["id"] in existing_ids:
                continue
            existing_ids.add(message["id"])
            result["messages"].append(message)
            result["new"] += 1
        return result
    finally:
        if mailbox is not None:
            try:
                mailbox.logout()
            except Exception:
                pass


def sync_enabled_mail_accounts(accounts: list[dict], options: dict | None = None) -> dict:
    options = options or {}
    store = load_mail_messages()
    enabled_accounts = [item for item in accounts if isinstance(item, dict) and item.get("enabled")]
    summary = {
        "updated_at": utc_now_iso(),
        "accounts_checked": 0,
        "messages_fetched": 0,
        "messages_new": 0,
        "matched_messages": 0,
        "messages_total": len(store.get("messages", [])),
        "errors": [],
    }

    for account in enabled_accounts:
        summary["accounts_checked"] += 1
        account_key = build_account_key(account)
        try:
            result = sync_one_mail_account(account, options, store)
            summary["messages_fetched"] += int(result.get("fetched") or 0)
            summary["messages_new"] += int(result.get("new") or 0)
            if result.get("messages"):
                store["messages"].extend(result["messages"])
            previous_account = store.get("accounts", {}).get(account_key, {})
            store["accounts"][account_key] = {
                "account_key": account_key,
                "account_name": str(account.get("name") or "").strip(),
                "email": str(account.get("email") or "").strip(),
                "last_sync_at": summary["updated_at"],
                "last_uid": result["messages"][0]["imap_uid"] if result.get("messages") else str(previous_account.get("last_uid") or ""),
                "last_message_id": result["messages"][0]["message_id"] if result.get("messages") else str(previous_account.get("last_message_id") or ""),
                "last_result": {
                    "fetched": int(result.get("fetched") or 0),
                    "new": int(result.get("new") or 0),
                    "matched": 0,
                    "errors": result.get("errors") or [],
                },
            }
        except Exception as exc:
            error_item = {
                "account_key": account_key,
                "account_name": str(account.get("name") or "").strip(),
                "error": str(exc),
            }
            summary["errors"].append(error_item)
            previous_account = store.get("accounts", {}).get(account_key, {})
            store["accounts"][account_key] = {
                "account_key": account_key,
                "account_name": str(account.get("name") or "").strip(),
                "email": str(account.get("email") or "").strip(),
                "last_sync_at": summary["updated_at"],
                "last_uid": str(previous_account.get("last_uid") or ""),
                "last_message_id": str(previous_account.get("last_message_id") or ""),
                "last_result": {
                    "fetched": 0,
                    "new": 0,
                    "matched": 0,
                    "errors": [str(exc)],
                },
            }

    four_table_config = options.get("four_table_config") if isinstance(options.get("four_table_config"), dict) else None
    if not four_table_config:
        raise RuntimeError("缺少四表飞书配置，无法执行邮件匹配。")
    try:
        account_records, creator_records = fetch_four_table_match_records(four_table_config)
        store["messages"] = match_messages_to_four_tables(store.get("messages", []), account_records, creator_records)
    except Exception as exc:
        summary["errors"].append({"account_key": "four_tables", "account_name": "四表匹配", "error": str(exc)})

    store["messages"] = sorted(
        [normalize_mail_message(item) for item in store.get("messages", []) if isinstance(item, dict)],
        key=lambda item: str(item.get("received_at") or item.get("synced_at") or ""),
        reverse=True,
    )
    store["updated_at"] = summary["updated_at"]
    summary["messages_total"] = len(store["messages"])
    summary["matched_messages"] = sum(
        1 for item in store["messages"] if isinstance(item, dict) and item.get("reply_status") == "matched"
    )
    accounts_map = store.get("accounts", {})
    if isinstance(accounts_map, dict):
        for account_key, account_state in accounts_map.items():
            if not isinstance(account_state, dict):
                continue
            matched_for_account = sum(
                1
                for item in store["messages"]
                if isinstance(item, dict) and item.get("account_key") == account_key and item.get("reply_status") == "matched"
            )
            last_result = account_state.get("last_result") if isinstance(account_state.get("last_result"), dict) else {}
            last_result["matched"] = matched_for_account
            account_state["last_result"] = last_result
    save_mail_messages(store)
    return summary


def build_creator_reply_update_fields(current_stage: str, received_at: str) -> tuple[dict[str, object], str]:
    """Build the only two creator-table fields the manual reply sync may update."""
    update_fields: dict[str, object] = {}
    stage_updated = False
    contact_time_updated = False

    if str(current_stage or "").strip() in {"", CRM_STAGE_NOT_CONTACTED, CRM_STAGE_CONTACTED}:
        update_fields[FOUR_TABLE_CREATOR_FIELD_STAGE] = CRM_STAGE_FOLLOWING
        stage_updated = True

    contact_time_ms = iso_to_epoch_ms(received_at)
    if contact_time_ms is not None:
        update_fields[CRM_FIELD_LAST_CONTACT_AT] = contact_time_ms
        contact_time_updated = True

    if stage_updated and contact_time_updated:
        return update_fields, "updated"
    if contact_time_updated:
        return update_fields, "time_only"
    if stage_updated:
        return update_fields, "updated"
    return update_fields, "skipped"


def sync_creator_replies(config: dict) -> dict:
    """Manually sync cached four-table reply matches to their linked creator records."""
    store = load_mail_messages()
    messages = [normalize_mail_message(item) for item in store.get("messages", []) if isinstance(item, dict)]
    syncable_statuses = {"matched", "matched_multi_account"}
    pending_messages = [
        item
        for item in messages
        if (
            item.get("reply_status") == "matched"
            and item.get("match_status") in syncable_statuses
            and str(item.get("matched_creator_record_id") or "").strip()
            and (str(item.get("sync_target") or "") != "creator_table" or not item.get("crm_synced"))
        )
    ]
    summary = {
        "updated_at": utc_now_iso(),
        "updated": 0,
        "time_only": 0,
        "skipped": 0,
        "failed": 0,
        "processed_messages": len(pending_messages),
        "errors": [],
    }

    if not pending_messages:
        store["updated_at"] = summary["updated_at"]
        save_mail_messages(store)
        return summary

    required = ("app_id", "app_secret", "app_token", "creator_table_id")
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"四表飞书配置不完整：缺少 {', '.join(missing)}")
    access_token = _four_table_access_token(config)
    headers = {"Authorization": f"Bearer {access_token}"}
    creator_records = fetch_four_table_records(config, config["creator_table_id"], headers)
    creators_by_record_id = {
        str(item.get("record_id") or "").strip(): item.get("fields") or {}
        for item in creator_records
        if str(item.get("record_id") or "").strip()
    }
    update_url = (
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{config['app_token']}"
        f"/tables/{config['creator_table_id']}/records/batch_update"
    )
    grouped: dict[str, list[dict]] = {}
    for item in pending_messages:
        grouped.setdefault(str(item["matched_creator_record_id"]).strip(), []).append(item)
    message_map = {item["id"]: item for item in messages}

    def mark_group(
        group: list[dict],
        *,
        synced: bool,
        status: str,
        error: str = "",
        record_id: str = "",
        action: str = "",
    ) -> None:
        synced_at = summary["updated_at"] if synced else ""
        for message in group:
            current = message_map.get(message["id"])
            if not current:
                continue
            current["crm_synced"] = synced
            current["crm_synced_at"] = synced_at
            current["crm_sync_status"] = status
            current["crm_sync_error"] = error
            current["crm_sync_record_id"] = record_id
            current["crm_sync_action"] = action
            current["sync_target"] = "creator_table"

    for creator_record_id, group in grouped.items():
        creator_fields = creators_by_record_id.get(creator_record_id)
        if creator_fields is None:
            error_text = f"达人表中未找到 record_id：{creator_record_id}"
            summary["failed"] += 1
            summary["errors"].append({"creator_record_id": creator_record_id, "error": error_text})
            mark_group(group, synced=False, status="failed", error=error_text, record_id=creator_record_id)
            continue

        latest_message = max(group, key=lambda item: str(item.get("received_at") or item.get("synced_at") or ""))
        update_fields, action = build_creator_reply_update_fields(
            str(creator_fields.get(FOUR_TABLE_CREATOR_FIELD_STAGE) or ""),
            str(latest_message.get("received_at") or latest_message.get("synced_at") or ""),
        )
        if not update_fields:
            summary["skipped"] += 1
            mark_group(group, synced=True, status="synced", record_id=creator_record_id, action="skipped")
            continue

        response = post_json(
            update_url,
            {"records": [{"record_id": creator_record_id, "fields": update_fields}]},
            headers=headers,
            timeout=15,
        )
        if response.get("code") == 0:
            summary[action] += 1
            mark_group(group, synced=True, status="synced", record_id=creator_record_id, action=action)
            continue

        error_text = json.dumps(
            {
                "code": response.get("code"),
                "msg": response.get("msg"),
                "error": response.get("error"),
                "data": response.get("data"),
                "record_id": creator_record_id,
            },
            ensure_ascii=False,
        )
        summary["failed"] += 1
        summary["errors"].append({"creator_record_id": creator_record_id, "error": error_text})
        mark_group(group, synced=False, status="failed", error=error_text, record_id=creator_record_id)

    store["messages"] = sorted(
        [normalize_mail_message(item) for item in message_map.values()],
        key=lambda item: str(item.get("received_at") or item.get("synced_at") or ""),
        reverse=True,
    )
    store["updated_at"] = summary["updated_at"]
    save_mail_messages(store)
    return summary
