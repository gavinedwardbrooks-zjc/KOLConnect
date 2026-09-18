"""Inbox observations and local Creator matches; no mailbox or Feishu authority is inferred."""

from __future__ import annotations

import hashlib
import imaplib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.policy import default
from email.utils import getaddresses, parsedate_to_datetime


LOOKBACK_DAYS = 30
MAX_FIRST_SYNC_MESSAGES = 200
HEADER_FETCH = "(BODY.PEEK[HEADER.FIELDS (DATE MESSAGE-ID IN-REPLY-TO REFERENCES FROM TO CC SUBJECT)] INTERNALDATE)"
MATCH_STATUSES = {"matched", "matched_multi_account", "unmatched", "ambiguous", "unassigned_account"}
SENT_FALLBACK_NAMES = {"sent", "sent mail", "sent items", "inbox.sent"}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def mail_account_identity(account: dict) -> tuple[str, str]:
    """Display/secret changes retain identity; changing the mailbox endpoint starts a new identity."""
    email = str(account.get("email") or "").strip().lower()
    username = str(account.get("username") or "").strip().lower()
    host = str(account.get("imap_host") or "").strip().lower()
    port = int(account.get("imap_port") or 993)
    if not email and not username:
        raise ValueError("Mail account has no stable email or username.")
    key = json.dumps([email, username, host, port], separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return f"mail_account_{digest[:32]}", key


def normalize_address(value: object) -> str:
    parsed = getaddresses([str(value or "")])
    return parsed[0][1].strip().lower() if len(parsed) == 1 else ""


def _addresses(message, field: str) -> list[tuple[str, str]]:
    result = []
    for _name, address in getaddresses(message.get_all(field, [])):
        original = address.strip()
        if original:
            result.append((original, original.lower()))
    return result


def _message_date(value: object) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(str(value or ""))
        if parsed is None:
            return None
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _iso(value: datetime | None) -> str | None:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z") if value else None


def _uidvalidity(mailbox) -> str:
    status, values = mailbox.response("UIDVALIDITY")
    raw = next((part for part in (values or []) if part), None) if status == "UIDVALIDITY" else None
    value = raw.decode("ascii", errors="ignore") if isinstance(raw, bytes) else str(raw or "")
    if not value.isdigit() or int(value) < 1:
        raise RuntimeError("IMAP UIDVALIDITY is unavailable; Inbox facts were not advanced.")
    return value


def _fetch_payload(mailbox, uid: str, query: str) -> tuple[bytes, str]:
    status, response = mailbox.uid("fetch", uid, query)
    if status != "OK" or not response:
        raise RuntimeError("IMAP fetch failed; cursor was not advanced.")
    for item in response:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
            metadata = item[0].decode("ascii", errors="replace") if isinstance(item[0], bytes) else str(item[0])
            return item[1], metadata
    raise RuntimeError("IMAP fetch returned no message data; cursor was not advanced.")


def _internal_date(metadata: str) -> datetime | None:
    match = re.search(r'INTERNALDATE\s+"([^"]+)"', metadata, re.IGNORECASE)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%d-%b-%Y %H:%M:%S %z").astimezone(timezone.utc)
    except ValueError:
        return None


def _account_matches(connection, address: str) -> list[dict]:
    if not address:
        return []
    rows = connection.execute(
        "SELECT a.account_uid,a.creator_id,c.creator_id AS owner_id FROM creator_accounts a "
        "LEFT JOIN creators c ON c.creator_id=a.creator_id "
        "WHERE lower(trim(a.account_email))=?", (address,)
    ).fetchall()
    return [dict(row) for row in rows]


def _match_addresses(connection, addresses: list[str]) -> tuple[str, str | None, str | None, str | None]:
    """Match address evidence conservatively and retain no guessed ownership."""
    matches = [(address, row) for address in addresses for row in _account_matches(connection, address)]
    if not matches:
        return "unmatched", None, None, None
    if any(not row["owner_id"] for _address, row in matches):
        return "unassigned_account", None, None, None
    owners = {row["creator_id"] for _address, row in matches}
    if len(owners) != 1:
        return "ambiguous", None, None, None
    account_uids = {row["account_uid"] for _address, row in matches}
    creator_id = next(iter(owners))
    matched_address = matches[0][0]
    return (
        "matched" if len(account_uids) == 1 else "matched_multi_account",
        creator_id,
        next(iter(account_uids)) if len(account_uids) == 1 else None,
        matched_address,
    )


def _match_inbound(connection, sender: str, own_addresses: set[str]) -> tuple[str, str | None, str | None, str | None]:
    if not sender or sender in own_addresses:
        return "unmatched", None, None, sender or None
    status, creator_id, account_uid, correspondent = _match_addresses(connection, [sender])
    return status, creator_id, account_uid, correspondent or sender


def _match_outbound(connection, to_addresses: list[str], cc_addresses: list[str]) -> tuple[str, str | None, str | None, str | None]:
    """Only To can establish ownership; CC can invalidate an otherwise unique To match."""
    to_status, creator_id, account_uid, correspondent = _match_addresses(connection, to_addresses)
    if to_status in {"ambiguous", "unassigned_account"}:
        return to_status, None, None, None
    if to_status == "unmatched":
        return "unmatched", None, None, to_addresses[0] if len(to_addresses) == 1 else None
    cc_status, cc_creator_id, _cc_account_uid, _cc_correspondent = _match_addresses(connection, cc_addresses)
    if cc_status in {"ambiguous", "unassigned_account"} or (cc_creator_id and cc_creator_id != creator_id):
        return "ambiguous", None, None, None
    return to_status, creator_id, account_uid, correspondent


def _mailbox_name_from_list_item(item: object) -> tuple[str, str] | None:
    raw = item.decode("utf-8", errors="replace") if isinstance(item, bytes) else str(item or "")
    # IMAP LIST commonly returns: (\\HasNoChildren \\Sent) "/" "Sent Mail".
    match = re.match(r"\s*(\([^)]*\))\s+(?:NIL|\"[^\"]*\"|[^\s]+)\s+(.*)\s*$", raw)
    if not match:
        return None
    flags, mailbox = match.groups()
    mailbox = mailbox.strip()
    if mailbox.startswith('"') and mailbox.endswith('"'):
        mailbox = mailbox[1:-1].replace('\\"', '"')
    return flags.lower(), mailbox


def discover_sent_mailbox(mailbox) -> str:
    """Return one authoritative Sent mailbox or fail closed on absence/ambiguity."""
    status, items = mailbox.list()
    if status != "OK":
        raise RuntimeError("IMAP Sent mailbox discovery failed.")
    parsed = [item for item in (_mailbox_name_from_list_item(value) for value in (items or [])) if item]
    special_use = [name for flags, name in parsed if "\\sent" in flags]
    if len(special_use) == 1:
        return special_use[0]
    if len(special_use) > 1:
        raise RuntimeError("IMAP Sent mailbox discovery is ambiguous.")
    conventional = [name for _flags, name in parsed if name.strip().lower() in SENT_FALLBACK_NAMES]
    if len(conventional) == 1:
        return conventional[0]
    if len(conventional) > 1:
        raise RuntimeError("IMAP Sent mailbox discovery is ambiguous.")
    raise RuntimeError("IMAP Sent mailbox was not found.")


def _match_sender(connection, address: str) -> tuple[str, str | None, str | None]:
    """Gate 2 compatibility wrapper for exact inbound sender matching."""
    status, creator_id, account_uid, _correspondent = _match_addresses(connection, [address])
    return status, creator_id, account_uid


def _persist_observation(factory, account_id: str, mailbox_id: str, uidvalidity: str,
                         uid: str, raw: bytes, observed_at: str, own_addresses: set[str],
                         direction: str) -> tuple[bool, dict]:
    message = message_from_bytes(raw, policy=default)
    addresses = {role: _addresses(message, role.title()) for role in ("from", "to", "cc")}
    sender = addresses["from"][0][1] if len(addresses["from"]) == 1 else ""
    to_addresses = [address for address, _normalized in addresses["to"]]
    cc_addresses = [address for address, _normalized in addresses["cc"]]
    with factory.write_transaction() as connection:
        existing = connection.execute(
            "SELECT mail_message_id FROM mail_message_observations WHERE mailbox_id=? AND uidvalidity=? AND imap_uid=?",
            (mailbox_id, uidvalidity, uid),
        ).fetchone()
        if existing:
            return False, {"mail_message_id": existing[0]}
        if direction == "inbound":
            match, creator_id, account_uid, correspondent = _match_inbound(connection, sender, own_addresses)
        elif direction == "outbound":
            match, creator_id, account_uid, correspondent = _match_outbound(connection, to_addresses, cc_addresses)
        else:
            match, creator_id, account_uid, correspondent = "unmatched", None, None, None
        fact_id = f"mail_{uuid.uuid4().hex}"
        date = _iso(_message_date(message.get("Date")))
        references = message.get("References")
        connection.execute(
            "INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,rfc_message_id,in_reply_to,reference_ids,subject,message_at,observed_at,correspondent_email,match_status,matched_creator_id,matched_account_uid) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (fact_id, account_id, direction, message.get("Message-ID"), message.get("In-Reply-To"),
             references, str(message.get("Subject")) if message.get("Subject") is not None else None,
             date, observed_at, correspondent, match, creator_id, account_uid),
        )
        connection.execute(
            "INSERT INTO mail_message_observations(observation_id,mail_message_id,mailbox_id,uidvalidity,imap_uid,observed_at) VALUES (?,?,?,?,?,?)",
            (f"observation_{uuid.uuid4().hex}", fact_id, mailbox_id, uidvalidity, uid, observed_at),
        )
        for role, items in addresses.items():
            for position, (original, normalized) in enumerate(items):
                connection.execute(
                    "INSERT INTO mail_message_addresses(mail_message_id,role,position,original_address,normalized_address,match_status,matched_creator_id,matched_account_uid) VALUES (?,?,?,?,?,?,?,?)",
                    (fact_id, role, position, original, normalized, match if role == "from" else "unmatched",
                     creator_id if role == "from" else None, account_uid if role == "from" else None),
                )
    return True, {"mail_message_id": fact_id, "match_status": match, "matched_creator_id": creator_id,
                  "matched_account_uid": account_uid, "from_email": sender, "received_at": date or "",
                  "direction": direction}


def _sync_mailbox(account: dict, factory, *, folder_name: str, role: str, direction: str,
                  imap_factory=None, now: datetime | None = None) -> dict:
    """Persist one mailbox generation without reconciling away historical observations."""
    account_id, identity_key = mail_account_identity(account)
    own_addresses = {normalize_address(account.get(key)) for key in ("email", "username")}
    own_addresses.discard("")
    host, username, password = (str(account.get(key) or "") for key in ("imap_host", "username", "password"))
    if not host or not username or not password:
        raise ValueError("IMAP configuration is incomplete.")
    port = int(account.get("imap_port") or 993)
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    observed_at = _iso(now)
    mailbox_id = f"mailbox_{hashlib.sha256((account_id + ':' + folder_name).encode()).hexdigest()[:32]}"
    with factory.write_transaction() as connection:
        connection.execute("INSERT OR IGNORE INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES (?,?,?)",
                           (account_id, identity_key, observed_at))
        connection.execute("INSERT OR IGNORE INTO mailbox_sync_states(mailbox_id,mail_account_id,folder_name,role) VALUES (?,?,?,?)",
                           (mailbox_id, account_id, folder_name, role))
    with factory.read_connection() as connection:
        state = connection.execute("SELECT * FROM mailbox_sync_states WHERE mailbox_id=?", (mailbox_id,)).fetchone()
        previous = dict(state)
    constructor = imap_factory or (imaplib.IMAP4_SSL if port == 993 else imaplib.IMAP4)
    mailbox = constructor(host, port, timeout=15)
    try:
        if port != 993:
            mailbox.starttls()
        mailbox.login(username, password)
        select_status, _ = mailbox.select(folder_name, readonly=True)
        if select_status != "OK":
            raise RuntimeError(f"IMAP {role} mailbox selection failed.")
        validity = _uidvalidity(mailbox)
        first = not previous["first_sync_completed_at"] or previous["uidvalidity"] != validity
        cutoff = now - timedelta(days=LOOKBACK_DAYS)
        if first:
            search_status, search_data = mailbox.uid("search", None, "SINCE", cutoff.strftime("%d-%b-%Y"))
        else:
            search_status, search_data = mailbox.uid("search", None, "UID", f"{int(previous['high_water_uid'] or 0) + 1}:*")
        if search_status != "OK":
            raise RuntimeError(f"IMAP {role} UID search failed.")
        uids = [part.decode("ascii") for part in (search_data[0] or b"").split() if part.isdigit()]
        if not first:
            uids = [uid for uid in uids if int(uid) > int(previous["high_water_uid"] or 0)]
        if first:
            candidates = []
            for uid in uids:
                _header, metadata = _fetch_payload(mailbox, uid, HEADER_FETCH)
                internal_date = _internal_date(metadata)
                if internal_date is None:
                    raise RuntimeError("IMAP INTERNALDATE is unavailable; first-sync cursor was not advanced.")
                if internal_date >= cutoff:
                    candidates.append((internal_date, int(uid), uid))
            candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
            selected = [item[2] for item in candidates[:MAX_FIRST_SYNC_MESSAGES]]
            coverage = "partial" if len(candidates) > MAX_FIRST_SYNC_MESSAGES else "bounded"
        else:
            selected = sorted(set(uids), key=int)
            coverage = previous["history_coverage"]
        fresh = []
        for uid in selected:
            raw, _metadata = _fetch_payload(mailbox, uid, "(BODY.PEEK[])")
            created, fact = _persist_observation(
                factory, account_id, mailbox_id, validity, uid, raw, observed_at, own_addresses, direction
            )
            if created:
                fresh.append({"uid": uid, **fact, "raw": raw})
        # A first-sync cap is a deliberate history boundary: scanned older UIDs
        # must not be interpreted as pending backfill on the next incremental sync.
        high_water = max([int(uid) for uid in uids], default=0) if first else max(
            [int(previous["high_water_uid"] or 0), *(int(uid) for uid in uids)])
        with factory.write_transaction() as connection:
            connection.execute(
                "UPDATE mailbox_sync_states SET uidvalidity=?,high_water_uid=?,first_sync_completed_at=COALESCE(first_sync_completed_at,?),history_coverage=?,last_sync_at=? WHERE mailbox_id=?",
                (validity, high_water, observed_at, coverage, observed_at, mailbox_id),
            )
        return {"mail_account_id": account_id, "mailbox_id": mailbox_id, "uidvalidity": validity,
                "fetched": len(selected), "new": len(fresh), "messages": fresh,
                "history_coverage": coverage, "high_water_uid": high_water, "folder_name": folder_name,
                "role": role}
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass


def sync_inbox(account: dict, factory, *, imap_factory=None, now: datetime | None = None) -> dict:
    """Persist authoritative Inbox observations; JSON projection remains caller-owned."""
    return _sync_mailbox(
        account, factory, folder_name="INBOX", role="inbox", direction="inbound",
        imap_factory=imap_factory, now=now,
    )


def sync_sent(account: dict, factory, *, imap_factory=None, now: datetime | None = None) -> dict:
    """Discover and persist authoritative Sent observations without provider-specific APIs."""
    account_id, _identity_key = mail_account_identity(account)
    host, username, password = (str(account.get(key) or "") for key in ("imap_host", "username", "password"))
    if not host or not username or not password:
        raise ValueError("IMAP configuration is incomplete.")
    port = int(account.get("imap_port") or 993)
    constructor = imap_factory or (imaplib.IMAP4_SSL if port == 993 else imaplib.IMAP4)
    mailbox = constructor(host, port, timeout=15)
    try:
        if port != 993:
            mailbox.starttls()
        mailbox.login(username, password)
        folder_name = discover_sent_mailbox(mailbox)
    finally:
        try:
            mailbox.logout()
        except Exception:
            pass
    # Discovery uses one short-lived connection. The synchronized connection still
    # reads actual UIDVALIDITY and treats the discovered folder as account-scoped.
    return _sync_mailbox(
        account, factory, folder_name=folder_name, role="sent", direction="outbound",
        imap_factory=imap_factory, now=now,
    )


def rfc_correlation(factory, *, in_reply_to: object = None, references: object = None) -> dict:
    """Read-only RFC evidence lookup; correlation never merges Mail facts."""
    candidates = []
    if in_reply_to:
        candidates.append(str(in_reply_to).strip())
    if references:
        candidates.extend(token for token in str(references).split() if token)
    candidates = list(dict.fromkeys(candidate for candidate in candidates if candidate))
    if not candidates:
        return {"status": "none", "mail_message_ids": []}
    placeholders = ",".join("?" for _candidate in candidates)
    with factory.read_connection() as connection:
        rows = connection.execute(
            f"SELECT mail_message_id FROM mail_messages WHERE rfc_message_id IN ({placeholders}) ORDER BY mail_message_id",
            candidates,
        ).fetchall()
    ids = [str(row[0]) for row in rows]
    return {"status": "correlated" if len(ids) == 1 else "ambiguous" if len(ids) > 1 else "unmatched",
            "mail_message_ids": ids}


def inbox_fact_projection(factory, mail_account_id: str) -> list[dict]:
    """Header-only recovery for the legacy Inbox display cache; never reads message bodies."""
    with factory.read_connection() as connection:
        rows = connection.execute(
            "SELECT m.mail_message_id,m.subject,m.message_at,m.observed_at,m.correspondent_email,"
            "m.match_status,m.matched_creator_id,m.matched_account_uid,o.imap_uid,"
            "(SELECT normalized_address FROM mail_message_addresses a WHERE a.mail_message_id=m.mail_message_id "
            "AND a.role='to' ORDER BY a.position LIMIT 1) AS to_email "
            "FROM mail_messages m JOIN mail_message_observations o ON o.mail_message_id=m.mail_message_id "
            "WHERE m.mail_account_id=? AND o.mailbox_id IN "
            "(SELECT mailbox_id FROM mailbox_sync_states WHERE role='inbox') "
            "ORDER BY m.observed_at DESC",
            (mail_account_id,),
        ).fetchall()
    return [dict(row) for row in rows]
