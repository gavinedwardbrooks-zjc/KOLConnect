from __future__ import annotations

"""Privacy-minimal conversion between Feishu events and Assistant messages."""

from dataclasses import dataclass
import json
from typing import Any


@dataclass(frozen=True)
class FeishuChatMessage:
    event_id: str
    message_id: str
    chat_id: str
    sender_id: str
    chat_type: str
    message_type: str
    text: str
    mentioned_bot: bool

    @property
    def session_id(self) -> str:
        if self.chat_type == "p2p":
            return f"feishu:direct:{self.chat_id or self.sender_id}"
        return f"feishu:group:{self.chat_id}:{self.sender_id}"


class FeishuChatMessageAdapter:
    """Accept sanitized SDK objects or raw v2 event dictionaries."""

    @classmethod
    def normalize(
        cls,
        value: Any,
        *,
        trusted_group_mention: bool = False,
    ) -> FeishuChatMessage | None:
        if isinstance(value, dict):
            return cls._from_dict(value)
        return cls._from_sdk_message(value, trusted_group_mention=trusted_group_mention)

    @classmethod
    def _from_sdk_message(
        cls,
        message: Any,
        *,
        trusted_group_mention: bool,
    ) -> FeishuChatMessage | None:
        if message is None:
            return None
        raw = getattr(message, "raw", None)
        raw = raw if isinstance(raw, dict) else {}
        header = raw.get("header") if isinstance(raw.get("header"), dict) else {}
        message_id = cls._text(getattr(message, "message_id", None) or getattr(message, "id", None))
        chat_id = cls._text(getattr(message, "chat_id", None))
        sender_id = cls._text(getattr(message, "sender_id", None))
        chat_type = cls._chat_type(getattr(message, "chat_type", None))
        message_type = cls._text(getattr(message, "raw_content_type", None) or "text").casefold()
        text = cls._text(getattr(message, "content_text", None))
        event_id = cls._text(header.get("event_id")) or message_id
        if not event_id or not message_id or not chat_id or not sender_id:
            return None
        return FeishuChatMessage(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            chat_type=chat_type,
            message_type=message_type,
            text=text,
            mentioned_bot=(
                bool(getattr(message, "mentioned_bot", False))
                or (trusted_group_mention and chat_type != "p2p")
            ),
        )

    @classmethod
    def _from_dict(cls, payload: dict[str, Any]) -> FeishuChatMessage | None:
        header = payload.get("header") if isinstance(payload.get("header"), dict) else {}
        event = payload.get("event") if isinstance(payload.get("event"), dict) else payload
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        sender = event.get("sender") if isinstance(event.get("sender"), dict) else {}
        sender_ids = sender.get("sender_id") if isinstance(sender.get("sender_id"), dict) else {}
        message_id = cls._text(message.get("message_id"))
        chat_id = cls._text(message.get("chat_id"))
        sender_id = cls._text(sender_ids.get("open_id") or sender.get("open_id"))
        event_id = cls._text(header.get("event_id")) or message_id
        message_type = cls._text(message.get("message_type") or "text").casefold()
        text = cls._content_text(message.get("content"), message_type)
        # A generic mention cannot prove the bot was addressed. The official SDK
        # adapter or a trusted test/event wrapper must identify the bot explicitly.
        mentioned_bot = bool(message.get("mentioned_bot"))
        if not event_id or not message_id or not chat_id or not sender_id:
            return None
        return FeishuChatMessage(
            event_id=event_id,
            message_id=message_id,
            chat_id=chat_id,
            sender_id=sender_id,
            chat_type=cls._chat_type(message.get("chat_type")),
            message_type=message_type,
            text=text,
            mentioned_bot=mentioned_bot,
        )

    @staticmethod
    def _content_text(content: Any, message_type: str) -> str:
        if message_type != "text":
            return ""
        if isinstance(content, str):
            try:
                decoded = json.loads(content)
            except (TypeError, ValueError):
                return content.strip()
            return str(decoded.get("text") or "").strip() if isinstance(decoded, dict) else ""
        return str((content or {}).get("text") or "").strip() if isinstance(content, dict) else ""

    @staticmethod
    def _chat_type(value: Any) -> str:
        return "p2p" if str(value or "").casefold() in {"p2p", "direct"} else "group"

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
