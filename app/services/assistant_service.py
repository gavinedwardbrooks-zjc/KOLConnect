from __future__ import annotations

"""Grounded, allowlisted KOLConnect assistant orchestration."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import threading
from typing import Any, Callable

from domain.normalization import normalize_country, normalize_number

from services.assistant_confirmation_store import (
    AssistantConfirmationStore,
    ConfirmationError,
)
from services.assistant_intent_router import (
    AssistantIntentRouter,
    AssistantRoutingError,
    DEFERRED_INTENTS,
    READ_INTENTS,
    SUPPORTED_INTENTS,
    WRITE_INTENTS,
)
from services.assistant_provider import AssistantProvider


Tool = Callable[..., Any]


@dataclass
class AssistantSession:
    expires_at: datetime
    last_creator_id: str = ""
    last_campaign_id: str = ""
    last_task_id: str = ""


class AssistantService:
    def __init__(
        self,
        provider: AssistantProvider,
        tools: dict[str, Tool],
        *,
        confirmation_store: AssistantConfirmationStore | None = None,
        session_ttl_seconds: int = 1800,
        now: Callable[[], datetime] | None = None,
        event_logger: Callable[[str], None] | None = None,
    ) -> None:
        self.provider = provider
        self.tools = dict(tools)
        self.router = AssistantIntentRouter()
        self.confirmations = confirmation_store or AssistantConfirmationStore()
        self.session_ttl_seconds = session_ttl_seconds
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sessions: dict[str, AssistantSession] = {}
        self._lock = threading.RLock()
        self._event_logger = event_logger or (lambda _message: None)

    def capabilities(self, trace_id: str) -> dict[str, Any]:
        return {
            "ok": True,
            "mode": self.provider.mode,
            "configured": self.provider.mode != "mock",
            "intents": [
                {
                    "intent": intent,
                    "class": (
                        "read" if intent in READ_INTENTS else
                        "write_confirmation" if intent in WRITE_INTENTS else "deferred"
                    ),
                }
                for intent in sorted(SUPPORTED_INTENTS)
            ],
            "trace_id": trace_id,
        }

    def message(self, message: object, session_id: object, trace_id: str) -> dict[str, Any]:
        try:
            session_key = self._session_id(session_id)
        except ConfirmationError:
            return self._error("MISSING_REQUIRED_ARGUMENT", "session_id 无效。", trace_id)
        session = self._session(session_key)
        text = str(message or "").strip()
        if not text:
            return self._error("MISSING_REQUIRED_ARGUMENT", "请输入问题或指令。", trace_id)
        if text.casefold() in {"确认", "confirm", "yes", "是"}:
            return self._error("CONFIRMATION_MISMATCH", "当前没有可确认的操作。", trace_id)
        try:
            parsed = self.provider.interpret(text, self._context(session))
            routed = self.router.validate(parsed)
        except AssistantRoutingError as exc:
            return self._error(exc.code, exc.message, trace_id)
        except Exception:
            return self._error("REMOTE_PROVIDER_ERROR", "助手解析暂时不可用。", trace_id)

        if routed.intent in DEFERRED_INTENTS:
            return self._error("UNSUPPORTED_ASSISTANT_INTENT", "该写操作需要明确账号选择，当前版本暂不开放。", trace_id)
        try:
            if routed.intent == "feishu_full_sync":
                preview = self._tool("feishu_sync_dry_run")()
                if self._conflict_count(preview):
                    return self._error("TOOL_CONFLICT", "飞书预检查存在冲突，已阻止同步。", trace_id, data=self._safe_sync(preview))
                arguments = {"preview": self._safe_sync(preview)}
                return self._confirmation(session_key, routed.intent, arguments, trace_id)
            if routed.requires_confirmation:
                return self._confirmation(session_key, routed.intent, routed.arguments, trace_id)
            result = self._execute_read(routed.intent, routed.arguments, session)
            self._event_logger(f"assistant intent={routed.intent} class=read status=success trace_id={trace_id}")
            return self._success(routed.intent, self._reply(routed.intent, result), result, trace_id)
        except LookupError as exc:
            return self._error(str(exc) or "NOT_FOUND", "未找到符合条件的数据。", trace_id)
        except AssistantRoutingError as exc:
            return self._error(exc.code, exc.message, trace_id, data=getattr(exc, "data", None))
        except Exception:
            return self._error("TOOL_EXECUTION_FAILED", "KOLConnect 操作未完成。", trace_id)

    def confirm(self, token: object, confirm: object, session_id: object, trace_id: str) -> dict[str, Any]:
        if confirm is not True:
            return self._error("CONFIRMATION_REQUIRED", "需要明确确认后才能执行。", trace_id)
        try:
            record = self.confirmations.consume(token, self._session_id(session_id))
        except ConfirmationError as exc:
            return self._error(str(exc), "确认已失效、已使用或不属于当前会话。", trace_id)
        try:
            if record.intent == "create_capture_task":
                result = self._tool("create_capture_task")(record.arguments)
                task_id = str((result.get("task") or {}).get("id") or result.get("task_id") or "")
                if task_id:
                    self._session(record.session_id).last_task_id = task_id
            elif record.intent == "feishu_full_sync":
                result = self._tool("feishu_full_sync")()
            else:
                return self._error("UNSUPPORTED_ASSISTANT_INTENT", "确认目标不受支持。", trace_id)
            self._event_logger(f"assistant intent={record.intent} class=write status=success confirmation=true trace_id={trace_id}")
            response = self._success(record.intent, self._reply(record.intent, result), self._privacy_safe(result), trace_id)
            response["confirmation_trace_id"] = record.trace_id
            return response
        except Exception:
            return self._error("TOOL_EXECUTION_FAILED", "确认的操作未完成。", trace_id)

    def _execute_read(self, intent: str, arguments: dict[str, Any], session: AssistantSession) -> Any:
        if intent == "search_creators":
            result = self._search(arguments)
        elif intent == "get_creator_detail":
            result = self._creator_detail(arguments)
            session.last_creator_id = str(result.get("creator_id") or result.get("record", {}).get("creator_id") or "")
        elif intent == "list_campaigns":
            result = self._bounded_campaigns(self._tool(intent)(arguments), int(arguments.get("limit") or 20))
        elif intent == "get_campaign_detail":
            result = self._campaign_detail(arguments)
            session.last_campaign_id = str(result.get("campaign_id") or result.get("campaign", {}).get("campaign_id") or "")
        elif intent == "get_task_status":
            result = self._tool(intent)(arguments["task_id"])
            session.last_task_id = str(arguments["task_id"])
        else:
            result = self._tool(intent)()
        return self._privacy_safe(result)

    def _search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        arguments = dict(arguments)
        if arguments.get("country"):
            arguments["country"] = normalize_country(arguments["country"]) or arguments["country"]
        rows = list(self._tool("search_creators")(arguments) or [])
        minimum = self._number(arguments.get("followers_min"))
        maximum = self._number(arguments.get("followers_max"))
        filtered = []
        seen_creator_ids: set[str] = set()
        for row in rows:
            creator_id = str(row.get("creator_id") or "")
            if creator_id and creator_id in seen_creator_ids:
                continue
            followers = self._number(row.get("followers"))
            if (minimum is not None or maximum is not None) and followers is None:
                continue
            if minimum is not None and followers < minimum:
                continue
            if maximum is not None and followers > maximum:
                continue
            filtered.append(self._creator_summary(row))
            if creator_id:
                seen_creator_ids.add(creator_id)
        limit = int(arguments.get("limit") or 10)
        return {"creators": filtered[:limit], "total": len(filtered), "remaining": max(0, len(filtered) - limit)}

    def _creator_detail(self, arguments: dict[str, Any]) -> dict[str, Any]:
        creator_id = str(arguments.get("creator_id") or "").strip()
        if not creator_id:
            matches = list(self._tool("search_creators")({"search": arguments.get("query"), "include_archived": True}) or [])
            exact = [row for row in matches if str(row.get("creator_name") or row.get("name") or "").casefold() == str(arguments.get("query") or "").casefold()]
            candidates = exact or matches
            if len(candidates) != 1:
                raise AssistantRoutingError(
                    "AMBIGUOUS_CREATOR" if candidates else "NOT_FOUND",
                    "达人名称不唯一，请选择具体账号。" if candidates else "未找到达人。",
                    {"candidates": [self._creator_summary(row) for row in candidates[:10]]},
                )
            creator_id = str(candidates[0].get("creator_id") or "")
        detail = dict(self._tool("get_creator_detail")(creator_id) or {})
        platform = str(arguments.get("platform") or "").casefold()
        if platform:
            accounts = [row for row in detail.get("accounts", []) if str(row.get("platform") or "").casefold() == platform]
            detail["accounts"] = accounts
        return detail

    def _campaign_detail(self, arguments: dict[str, Any]) -> dict[str, Any]:
        campaign_id = str(arguments.get("campaign_id") or "").strip()
        if not campaign_id:
            campaigns = list(self._tool("list_campaigns")({}) or [])
            name = str(arguments.get("name") or "").casefold()
            matches = [row for row in campaigns if str(row.get("name") or "").casefold() == name]
            if len(matches) != 1:
                raise AssistantRoutingError(
                    "AMBIGUOUS_CAMPAIGN" if matches else "NOT_FOUND",
                    "Campaign 名称不唯一。" if matches else "未找到 Campaign。",
                    {"candidates": self._privacy_safe(matches[:10])},
                )
            campaign_id = str(matches[0].get("campaign_id") or "")
        return dict(self._tool("get_campaign_detail")(campaign_id) or {})

    def _confirmation(self, session_id: str, intent: str, arguments: dict[str, Any], trace_id: str) -> dict[str, Any]:
        record = self.confirmations.create(session_id, intent, arguments, trace_id)
        preview = self._preview(intent, arguments)
        return {
            "ok": True,
            "reply": preview,
            "intent": intent,
            "requires_confirmation": True,
            "confirmation_token": record.token,
            "expires_at": record.expires_at.isoformat(),
            "data": self._privacy_safe(arguments),
            "trace_id": trace_id,
        }

    def _session(self, session_id: str) -> AssistantSession:
        with self._lock:
            current = self._sessions.get(session_id)
            if current is None or self._now() >= current.expires_at:
                current = AssistantSession(self._now() + timedelta(seconds=self.session_ttl_seconds))
                self._sessions[session_id] = current
            else:
                current.expires_at = self._now() + timedelta(seconds=self.session_ttl_seconds)
            return current

    @staticmethod
    def _session_id(value: object) -> str:
        session_id = str(value or "").strip()
        if not session_id or len(session_id) > 128 or not re.fullmatch(r"[A-Za-z0-9_.:-]+", session_id):
            raise ConfirmationError("CONFIRMATION_MISMATCH")
        return session_id

    def _tool(self, name: str) -> Tool:
        tool = self.tools.get(name)
        if tool is None:
            raise RuntimeError("tool unavailable")
        return tool

    @staticmethod
    def _context(session: AssistantSession) -> dict[str, str]:
        return {"last_creator_id": session.last_creator_id, "last_campaign_id": session.last_campaign_id, "last_task_id": session.last_task_id}

    @staticmethod
    def _number(value: object) -> float | None:
        number = normalize_number(value)
        return float(number) if number is not None else None

    @classmethod
    def _creator_summary(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "creator_id": str(row.get("creator_id") or ""),
            "name": str(row.get("creator_name") or row.get("name") or ""),
            "platform": str(row.get("platform") or ""),
            "username": str(row.get("username") or row.get("profile_url") or ""),
            "followers": row.get("followers") if cls._number(row.get("followers")) is not None else None,
            "country": str(row.get("country") or "") or None,
            "content_category": str(row.get("content_category") or "") or None,
        }

    @staticmethod
    def _bounded_campaigns(result: Any, limit: int) -> dict[str, Any]:
        rows = list(result or [])
        limit = min(max(limit, 1), 50)
        return {"campaigns": rows[:limit], "total": len(rows), "remaining": max(0, len(rows) - limit)}

    @staticmethod
    def _privacy_safe(value: Any) -> Any:
        blocked = {"email", "phone", "whatsapp", "note", "notes", "cost", "quote", "creator_quote", "app_secret", "token", "password", "mail_body", "path", "file_path", "workbook_path"}
        if isinstance(value, dict):
            return {key: AssistantService._privacy_safe(item) for key, item in value.items() if str(key).casefold() not in blocked}
        if isinstance(value, list):
            return [AssistantService._privacy_safe(item) for item in value]
        if isinstance(value, tuple):
            return [AssistantService._privacy_safe(item) for item in value]
        return value

    @staticmethod
    def _safe_sync(result: Any) -> dict[str, Any]:
        if not isinstance(result, dict):
            return {}
        allowed = ("status", "blocked_reason", "creator_create_count", "creator_update_count", "creator_unchanged_count", "account_create_count", "account_update_count", "account_unchanged_count", "relation_add_count", "relation_update_count", "relation_remove_count", "relation_unchanged_count", "conflict_count", "conflicts")
        return {key: result.get(key) for key in allowed if key in result}

    @staticmethod
    def _conflict_count(result: Any) -> int:
        if not isinstance(result, dict):
            return 0
        return int(result.get("conflict_count") or len(result.get("conflicts") or []))

    @staticmethod
    def _preview(intent: str, arguments: dict[str, Any]) -> str:
        if intent == "create_capture_task":
            return f"准备创建抓取任务：{arguments.get('url')}。确认创建吗？"
        return "飞书同步预检查已完成。确认按当前计划执行 Full Sync 吗？"

    @staticmethod
    def _reply(intent: str, result: Any) -> str:
        if intent == "search_creators":
            return f"找到 {result.get('total', 0)} 位符合条件的达人。"
        if intent == "create_capture_task":
            return "抓取任务已创建，尚未自动启动。"
        if intent == "feishu_full_sync":
            return f"飞书 Full Sync 返回状态：{result.get('status', 'unknown')}。"
        if intent == "feishu_sync_dry_run":
            return "飞书同步预检查已完成，未执行写入。"
        return "已从 KOLConnect 获取结果。"

    @staticmethod
    def _success(intent: str, reply: str, data: Any, trace_id: str) -> dict[str, Any]:
        return {"ok": True, "reply": reply, "intent": intent, "requires_confirmation": False, "data": data, "trace_id": trace_id}

    @staticmethod
    def _error(code: str, message: str, trace_id: str, *, data: Any = None) -> dict[str, Any]:
        result = {"ok": False, "error": {"code": code, "message": message}, "trace_id": trace_id}
        if data is not None:
            result["data"] = AssistantService._privacy_safe(data)
        return result
