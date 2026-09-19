"""Derived, read-only Mail follow-up state from authoritative SQLite facts."""

from __future__ import annotations

from datetime import datetime, timezone


RELIABLE_MATCH_STATUSES = ("matched", "matched_multi_account")
EXCLUDED_CREATOR_STATUSES = {"archived", "rejected"}


def _utc_now(now: datetime | None) -> datetime:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc)


def _parse_utc(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _utc_text(value: datetime | None) -> str | None:
    return value.isoformat().replace("+00:00", "Z") if value else None


def _fact_rows(factory) -> list[dict]:
    """Read one historical address snapshot per fact/correspondent group."""
    placeholders = ",".join("?" for _status in RELIABLE_MATCH_STATUSES)
    query = f"""
        SELECT DISTINCT
            m.mail_message_id, m.direction, m.message_at,
            a.normalized_address AS correspondent_email,
            a.matched_creator_id AS creator_id,
            a.matched_account_uid AS creator_account_uid,
            CASE
                WHEN EXISTS (
                    SELECT 1 FROM mail_message_observations o
                    JOIN mailbox_sync_states s ON s.mailbox_id = o.mailbox_id
                    WHERE o.mail_message_id = m.mail_message_id
                      AND s.history_coverage = 'partial'
                ) THEN 'partial'
                WHEN EXISTS (
                    SELECT 1 FROM mail_message_observations o
                    JOIN mailbox_sync_states s ON s.mailbox_id = o.mailbox_id
                    WHERE o.mail_message_id = m.mail_message_id
                      AND s.history_coverage = 'unknown'
                ) THEN 'unknown'
                ELSE 'bounded'
            END AS history_coverage
        FROM mail_messages m
        JOIN mail_message_addresses a ON a.mail_message_id = m.mail_message_id
        JOIN creators c ON c.creator_id = a.matched_creator_id
        WHERE m.match_status IN ({placeholders})
          AND m.matched_creator_id = a.matched_creator_id
          AND a.match_status IN ({placeholders})
          AND a.normalized_address <> ''
          AND ((m.direction = 'inbound' AND a.role = 'from')
               OR (m.direction = 'outbound' AND a.role = 'to'))
          AND lower(trim(COALESCE(c.status, ''))) NOT IN ('archived', 'rejected')
    """
    with factory.read_connection() as connection:
        return [dict(row) for row in connection.execute(query, (*RELIABLE_MATCH_STATUSES, *RELIABLE_MATCH_STATUSES))]


def _history_coverage(facts: list[dict]) -> tuple[str, bool | None]:
    coverage = {fact["history_coverage"] for fact in facts}
    if "partial" in coverage:
        return "partial", True
    if "unknown" in coverage:
        return "unknown", None
    # A bounded sync window is known bounded, not proof of lifetime completeness.
    return "bounded", None


def _derive_group(creator_id: str, correspondent_email: str, facts: list[dict], now: datetime) -> dict:
    parsed = [(fact, _parse_utc(fact["message_at"])) for fact in facts]
    reliable = [(fact, timestamp) for fact, timestamp in parsed if timestamp is not None and timestamp <= now]
    uncertain = len(reliable) != len(parsed)
    inbound_times = [timestamp for fact, timestamp in reliable if fact["direction"] == "inbound"]
    outbound_times = [timestamp for fact, timestamp in reliable if fact["direction"] == "outbound"]
    last_inbound = max(inbound_times, default=None)
    last_outbound = max(outbound_times, default=None)
    latest = max((timestamp for _fact, timestamp in reliable), default=None)
    latest_directions = {
        fact["direction"] for fact, timestamp in reliable if latest is not None and timestamp == latest
    }
    if uncertain or latest is None or len(latest_directions) != 1:
        latest_direction = "unknown"
        waiting_for = "unknown"
        last_mail = None
        days_waiting = None
    else:
        latest_direction = next(iter(latest_directions))
        waiting_for = "me" if latest_direction == "inbound" else "creator"
        last_mail = latest
        days_waiting = int((now - latest).total_seconds() // 86400)
    coverage, partial_history = _history_coverage(facts)
    account_uids = {fact["creator_account_uid"] for fact in facts if fact["creator_account_uid"]}
    return {
        "creator_id": creator_id,
        "correspondent_email": correspondent_email,
        "creator_account_uid": next(iter(account_uids)) if len(account_uids) == 1 else None,
        "waiting_for": waiting_for,
        "latest_direction": latest_direction,
        "last_inbound_at": _utc_text(last_inbound),
        "last_outbound_at": _utc_text(last_outbound),
        "last_mail_at": _utc_text(last_mail),
        "synced_inbound_count": sum(fact["direction"] == "inbound" for fact in facts),
        "synced_outbound_count": sum(fact["direction"] == "outbound" for fact in facts),
        "days_waiting": days_waiting,
        "history_coverage": coverage,
        "partial_history": partial_history,
    }


def derive_follow_up_queue(factory, *, now: datetime | None = None) -> list[dict]:
    """Return deterministic Creator/correspondent Mail state without persistence or transport I/O."""
    current = _utc_now(now)
    groups: dict[tuple[str, str], dict[str, dict]] = {}
    for fact in _fact_rows(factory):
        groups.setdefault((fact["creator_id"], fact["correspondent_email"]), {})[fact["mail_message_id"]] = fact
    queue = [_derive_group(creator_id, email, list(facts.values()), current)
             for (creator_id, email), facts in groups.items()]
    return sorted(queue, key=lambda item: (
        item["last_mail_at"] is None,
        item["last_mail_at"] or "",
        item["creator_id"],
        item["correspondent_email"],
    ))
