from __future__ import annotations

"""Ephemeral, session-bound and single-use assistant confirmations."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import secrets
import threading
from typing import Any, Callable


class ConfirmationError(ValueError):
    pass


@dataclass
class ConfirmationRecord:
    token: str
    session_id: str
    intent: str
    arguments: dict[str, Any]
    arguments_hash: str
    expires_at: datetime
    trace_id: str
    used: bool = False


class AssistantConfirmationStore:
    def __init__(self, *, ttl_seconds: int = 300, now: Callable[[], datetime] | None = None) -> None:
        self.ttl_seconds = ttl_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._records: dict[str, ConfirmationRecord] = {}
        self._lock = threading.RLock()

    def create(self, session_id: str, intent: str, arguments: dict[str, Any], trace_id: str) -> ConfirmationRecord:
        token = f"confirm_{secrets.token_urlsafe(24)}"
        record = ConfirmationRecord(
            token=token,
            session_id=session_id,
            intent=intent,
            arguments=dict(arguments),
            arguments_hash=self._hash(arguments),
            expires_at=self._now() + timedelta(seconds=self.ttl_seconds),
            trace_id=trace_id,
        )
        with self._lock:
            self._records[token] = record
        return record

    def consume(self, token: object, session_id: object) -> ConfirmationRecord:
        normalized_token = str(token or "").strip()
        normalized_session = str(session_id or "").strip()
        with self._lock:
            record = self._records.get(normalized_token)
            if record is None:
                raise ConfirmationError("CONFIRMATION_MISMATCH")
            if record.used:
                raise ConfirmationError("CONFIRMATION_ALREADY_USED")
            if record.session_id != normalized_session:
                raise ConfirmationError("CONFIRMATION_MISMATCH")
            if self._now() >= record.expires_at:
                raise ConfirmationError("CONFIRMATION_EXPIRED")
            if record.arguments_hash != self._hash(record.arguments):
                raise ConfirmationError("CONFIRMATION_MISMATCH")
            record.used = True
            return record

    def discard(self, token: object, session_id: object) -> bool:
        """Invalidate one pending confirmation without executing its operation."""
        normalized_token = str(token or "").strip()
        normalized_session = str(session_id or "").strip()
        with self._lock:
            record = self._records.get(normalized_token)
            if record is None or record.used or record.session_id != normalized_session:
                return False
            record.used = True
            return True

    def discard_intent(self, intent: str) -> int:
        """Invalidate unused confirmations for one narrowly scoped operation."""
        count = 0
        with self._lock:
            for record in self._records.values():
                if record.intent == intent and not record.used:
                    record.used = True
                    count += 1
        return count

    @staticmethod
    def _hash(arguments: dict[str, Any]) -> str:
        payload = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
