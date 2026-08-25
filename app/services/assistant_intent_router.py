from __future__ import annotations

"""Strict allowlist and argument validation for assistant intents."""

from dataclasses import dataclass
from typing import Any

from services.assistant_provider import AssistantIntent


READ_INTENTS = {
    "search_creators",
    "get_creator_detail",
    "list_campaigns",
    "get_campaign_detail",
    "get_task_status",
    "feishu_sync_dry_run",
    "daily_summary",
}
WRITE_INTENTS = {"create_capture_task", "feishu_full_sync"}
DEFERRED_INTENTS = {"add_creator_to_campaign"}
SUPPORTED_INTENTS = READ_INTENTS | WRITE_INTENTS | DEFERRED_INTENTS

_FIELDS = {
    "search_creators": {
        "country", "platform", "language", "content_category", "followers_min",
        "followers_max", "include_archived", "limit", "search",
    },
    "get_creator_detail": {"creator_id", "query", "platform"},
    "list_campaigns": {"status", "limit"},
    "get_campaign_detail": {"campaign_id", "name"},
    "get_task_status": {"task_id"},
    "feishu_sync_dry_run": set(),
    "daily_summary": set(),
    "create_capture_task": {"url", "platform", "name"},
    "feishu_full_sync": {"preview"},
    "add_creator_to_campaign": {"creator_id", "campaign_id", "account_ids"},
}


class AssistantRoutingError(ValueError):
    def __init__(self, code: str, message: str = "", data: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.message = message or code
        self.data = data


@dataclass(frozen=True)
class ValidatedIntent:
    intent: str
    arguments: dict[str, Any]
    requires_confirmation: bool


class AssistantIntentRouter:
    def validate(self, parsed: AssistantIntent) -> ValidatedIntent:
        intent = str(parsed.intent or "").strip()
        if intent not in SUPPORTED_INTENTS:
            raise AssistantRoutingError("UNSUPPORTED_ASSISTANT_INTENT", "暂不支持该操作。")
        supplied = dict(parsed.arguments or {})
        unknown = set(supplied) - _FIELDS[intent]
        if unknown:
            raise AssistantRoutingError("ASSISTANT_PARSE_FAILED", "助手参数包含不支持的字段。")
        arguments = {key: value for key, value in supplied.items() if value is not None}
        self._required(intent, arguments)
        if intent == "search_creators":
            limit = int(arguments.get("limit") or 10)
            if limit < 1 or limit > 50:
                raise AssistantRoutingError("ASSISTANT_PARSE_FAILED", "结果数量必须在 1 到 50 之间。")
            arguments["limit"] = limit
        return ValidatedIntent(intent, arguments, intent in WRITE_INTENTS)

    @staticmethod
    def _required(intent: str, arguments: dict[str, Any]) -> None:
        required_any = {
            "get_creator_detail": ("creator_id", "query"),
            "get_campaign_detail": ("campaign_id", "name"),
        }
        required = {
            "get_task_status": ("task_id",),
            "create_capture_task": ("url",),
        }
        if intent in required_any and not any(str(arguments.get(key) or "").strip() for key in required_any[intent]):
            raise AssistantRoutingError("MISSING_REQUIRED_ARGUMENT", "缺少必要的查询标识。")
        for key in required.get(intent, ()):
            if not str(arguments.get(key) or "").strip():
                raise AssistantRoutingError("MISSING_REQUIRED_ARGUMENT", f"缺少参数：{key}")
