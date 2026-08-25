from __future__ import annotations

"""Conversation safety, replay protection, and Assistant response projection."""

from collections import OrderedDict
from dataclasses import dataclass
import threading
import time
from typing import Any, Callable

from services.feishu_chat_message_adapter import FeishuChatMessage


@dataclass(frozen=True)
class FeishuChatOutcome:
    ignored: bool
    replies: tuple[str, ...] = ()
    trace_id: str = ""


class ProcessedEventCache:
    def __init__(
        self,
        *,
        ttl_seconds: float = 600,
        max_size: int = 2048,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._clock = clock or time.monotonic
        self._items: OrderedDict[str, float] = OrderedDict()
        self._lock = threading.RLock()

    def duplicate(self, identity: str) -> bool:
        return self.duplicate_any(identity)

    def duplicate_any(self, *identities: str) -> bool:
        normalized = tuple(dict.fromkeys(identity for identity in identities if identity))
        now = self._clock()
        with self._lock:
            while self._items:
                key, timestamp = next(iter(self._items.items()))
                if now - timestamp < self.ttl_seconds:
                    break
                self._items.pop(key, None)
            if any(identity in self._items for identity in normalized):
                return True
            for identity in normalized:
                self._items[identity] = now
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)
            return False


class FeishuChatService:
    MAX_TEXT_CHARS = 3500
    CONFIRM_COMMANDS = frozenset({"确认", "confirm"})
    CANCEL_COMMANDS = frozenset({"取消", "cancel"})

    def __init__(
        self,
        assistant_service: Any,
        *,
        trace_id_provider: Callable[[], str],
        event_cache: ProcessedEventCache | None = None,
        event_logger: Callable[[str], None] | None = None,
    ) -> None:
        self._assistant = assistant_service
        self._trace_id_provider = trace_id_provider
        self._events = event_cache or ProcessedEventCache()
        self._event_logger = event_logger or (lambda _message: None)
        self._pending: dict[str, str] = {}
        self._lock = threading.RLock()

    def handle(self, message: FeishuChatMessage) -> FeishuChatOutcome:
        if message.chat_type != "p2p" and not message.mentioned_bot:
            return FeishuChatOutcome(ignored=True)
        if self._events.duplicate_any(message.event_id, message.message_id):
            self._event_logger(f"feishu_chat duplicate=true event_id={message.event_id}")
            return FeishuChatOutcome(ignored=True)

        trace_id = self._trace_id_provider()
        if message.message_type != "text":
            return FeishuChatOutcome(False, ("目前我先支持文字消息。",), trace_id)
        command = message.text.strip().casefold()
        if command in self.CONFIRM_COMMANDS:
            return self._confirm(message.session_id, trace_id)
        if command in self.CANCEL_COMMANDS:
            return self._cancel(message.session_id, trace_id)

        try:
            response = self._assistant.message(message.text, message.session_id, trace_id)
        except Exception:
            self._event_logger(
                f"feishu_chat transport=feishu_chat event_id={message.event_id} "
                f"trace_id={trace_id} status=failed error=ASSISTANT_UNAVAILABLE"
            )
            return FeishuChatOutcome(
                False,
                ("暂时无法连接 KOLConnect，请稍后再试。",),
                trace_id,
            )
        if response.get("requires_confirmation"):
            token = str(response.get("confirmation_token") or "")
            with self._lock:
                previous = self._pending.get(message.session_id)
                if previous:
                    self._assistant.confirmations.discard(previous, message.session_id)
                self._pending[message.session_id] = token
        rendered = self._render(response, trace_id)
        self._event_logger(
            f"feishu_chat transport=feishu_chat event_id={message.event_id} "
            f"message_id={message.message_id} assistant_session_id={message.session_id} "
            f"trace_id={trace_id} status={'success' if response.get('ok') else 'failed'}"
        )
        return FeishuChatOutcome(False, self._chunks(rendered), trace_id)

    def _confirm(self, session_id: str, trace_id: str) -> FeishuChatOutcome:
        with self._lock:
            token = self._pending.pop(session_id, "")
        if not token:
            return FeishuChatOutcome(False, ("当前没有可确认的操作。",), trace_id)
        try:
            response = self._assistant.confirm(token, True, session_id, trace_id)
        except Exception:
            return FeishuChatOutcome(
                False,
                ("确认的操作未完成，请重新发起预览后再试。",),
                trace_id,
            )
        return FeishuChatOutcome(False, self._chunks(self._render(response, trace_id)), trace_id)

    def _cancel(self, session_id: str, trace_id: str) -> FeishuChatOutcome:
        with self._lock:
            token = self._pending.pop(session_id, "")
        if not token:
            return FeishuChatOutcome(False, ("当前没有待取消的操作。",), trace_id)
        self._assistant.confirmations.discard(token, session_id)
        return FeishuChatOutcome(False, ("已取消，本次操作不会执行。",), trace_id)

    def _render(self, response: dict[str, Any], trace_id: str) -> str:
        if not response.get("ok"):
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            return str(error.get("message") or "暂时无法连接 KOLConnect，请稍后再试。")
        intent = str(response.get("intent") or "")
        raw_data = response.get("data")
        try:
            return self._render_success(intent, raw_data, response)
        except Exception:
            self._event_logger(
                f"feishu_chat renderer intent={intent or 'unknown'} "
                f"result_type={type(raw_data).__name__} trace_id={trace_id} "
                "error=UNSUPPORTED_RESULT_SHAPE"
            )
            return f"已获取数据，但暂时无法展示结果。错误参考：{trace_id}"

    @classmethod
    def _render_success(
        cls,
        intent: str,
        raw_data: Any,
        response: dict[str, Any],
    ) -> str:
        read_intents = {
            "search_creators", "get_creator_detail", "list_campaigns",
            "get_campaign_detail", "get_task_status", "daily_summary",
            "feishu_sync_dry_run",
        }
        if intent in read_intents and not isinstance(raw_data, dict):
            raise TypeError("read result must be an object")
        data = raw_data if isinstance(raw_data, dict) else {}
        if intent == "search_creators":
            rows = data.get("creators") if isinstance(data.get("creators"), list) else []
            total = cls._integer(data.get("total"), len(rows))
            if not rows:
                return "找到 0 位符合条件的达人。"
            lines = [f"找到 {total} 位符合条件的达人："]
            for index, row in enumerate(rows[:10], 1):
                if not isinstance(row, dict):
                    raise TypeError("creator result must be an object")
                lines.extend([
                    "",
                    f"{index}. {row.get('name') or '未命名达人'}",
                    " · ".join(filter(None, [str(row.get("platform") or ""), cls._metric(row.get("followers"))])),
                    f"地区：{row.get('country') or '--'}",
                ])
            remaining = cls._integer(data.get("remaining"), max(0, total - len(rows[:10])))
            if remaining:
                lines.extend(["", f"另有 {remaining} 位达人未展开。"])
            return "\n".join(line for line in lines if line != " · ")
        if intent == "get_creator_detail":
            creator = (
                data.get("creator") if isinstance(data.get("creator"), dict)
                else data.get("record") if isinstance(data.get("record"), dict)
                else data
            )
            lines = [str(creator.get("name") or creator.get("creator_name") or "达人资料")]
            accounts = data.get("accounts") if isinstance(data.get("accounts"), list) else []
            for account in accounts:
                if not isinstance(account, dict):
                    raise TypeError("creator account must be an object")
                lines.extend([
                    "",
                    " ".join(filter(None, [str(account.get("platform") or ""), str(account.get("username") or account.get("profile_url") or "")])),
                    f"粉丝：{cls._metric(account.get('followers')) or '--'}",
                ])
            lines.extend(["", f"地区：{creator.get('country') or '--'}", f"语言：{creator.get('language') or '--'}"])
            return "\n".join(lines)
        if intent == "list_campaigns":
            campaigns = data.get("campaigns")
            if not isinstance(campaigns, list):
                raise TypeError("campaign list is missing")
            total = cls._integer(data.get("total"), len(campaigns))
            if not campaigns:
                return "找到 0 个 Campaign。"
            lines = [f"找到 {total} 个 Campaign："]
            for index, campaign in enumerate(campaigns[:10], 1):
                if not isinstance(campaign, dict):
                    raise TypeError("campaign result must be an object")
                summary = " · ".join(filter(None, [
                    str(campaign.get("status") or ""),
                    str(campaign.get("product_name") or ""),
                ]))
                lines.append(f"{index}. {campaign.get('name') or '未命名 Campaign'}{f' · {summary}' if summary else ''}")
            remaining = cls._integer(data.get("remaining"), max(0, total - len(campaigns[:10])))
            if remaining:
                lines.append(f"另有 {remaining} 个 Campaign 未展开。")
            return "\n".join(lines)
        if intent == "get_campaign_detail":
            return cls._render_campaign_detail(data)
        if intent == "get_task_status":
            task = data.get("task")
            if not isinstance(task, dict):
                raise TypeError("task result is missing")
            progress = data.get("progress") if isinstance(data.get("progress"), dict) else {}
            lines = [f"任务：{task.get('name') or task.get('id') or task.get('task_id') or '--'}"]
            lines.append(f"状态：{task.get('status') or '--'}")
            for label, keys in (
                ("成功", ("completed", "completed_links", "success_count")),
                ("失败", ("failed", "failed_links", "failure_count")),
            ):
                value = cls._first_present(progress, keys)
                if value is not None:
                    lines.append(f"{label}：{value}")
            return "\n".join(lines)
        if intent == "daily_summary":
            tasks = data.get("tasks") if isinstance(data.get("tasks"), dict) else {}
            lines = [
                "今日概览",
                f"达人总数：{cls._display(data.get('creator_total'))}",
                f"近 7 天新增达人：{cls._display(data.get('new_creators_7d'))}",
                f"活跃 Campaign：{cls._display(data.get('active_campaign_count'))}",
            ]
            if tasks:
                lines.append(
                    "任务：" + " · ".join(
                        f"{label} {tasks[key]}"
                        for label, key in (("待处理", "pending"), ("运行中", "running"), ("失败", "failed"))
                        if key in tasks
                    )
                )
            return "\n".join(line for line in lines if line != "任务：")
        if intent == "feishu_sync_dry_run":
            return cls._render_sync_preview(data, requires_confirmation=False)
        if intent in {"feishu_sync_dry_run", "feishu_full_sync"} and response.get("requires_confirmation"):
            preview = data.get("preview") if isinstance(data.get("preview"), dict) else data
            return cls._render_sync_preview(preview, requires_confirmation=True)
        text = str(response.get("reply") or "已完成。").strip()
        if response.get("requires_confirmation"):
            text += "\n\n回复“确认”执行。\n5 分钟内有效。"
        return text

    @classmethod
    def _render_campaign_detail(cls, data: dict[str, Any]) -> str:
        campaign = data.get("campaign")
        if not isinstance(campaign, dict):
            raise TypeError("campaign detail is missing")
        relations = data.get("campaign_creators")
        if not isinstance(relations, list):
            raise TypeError("campaign members are missing")
        lines = [str(campaign.get("name") or "Campaign 详情")]
        for label, value in (
            ("产品", campaign.get("product_name")),
            ("状态", campaign.get("status")),
            ("平台", " / ".join(str(item) for item in campaign.get("platforms") or [] if item) or campaign.get("platform")),
            ("地区", campaign.get("country") or campaign.get("region")),
        ):
            if value not in (None, "", []):
                lines.append(f"{label}：{value}")

        members: list[dict[str, Any]] = []
        seen: set[str] = set()
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                raise TypeError("campaign member must be an object")
            identity = str(
                relation.get("creator_id") or relation.get("id") or f"row:{index}"
            )
            if identity in seen:
                continue
            seen.add(identity)
            members.append(relation)
        lines.extend(["", f"共 {len(members)} 位达人："])
        for index, relation in enumerate(members[:10], 1):
            lines.append(f"{index}. {relation.get('creator_name') or '未命名达人'}")
            execution_accounts = relation.get("execution_accounts")
            accounts = execution_accounts if isinstance(execution_accounts, list) else []
            if not accounts and (relation.get("account_platform") or relation.get("account_url")):
                accounts = [{
                    "platform": relation.get("account_platform"),
                    "profile_url": relation.get("account_url"),
                }]
            for account in accounts:
                if not isinstance(account, dict):
                    raise TypeError("execution account must be an object")
                account_text = cls._account_label(account)
                if account_text:
                    lines.append(f"   {account_text}")
        if len(members) > 10:
            lines.extend(["", f"另有 {len(members) - 10} 位达人未展开。"])
        return "\n".join(lines)

    @classmethod
    def _render_sync_preview(
        cls,
        preview: dict[str, Any],
        *,
        requires_confirmation: bool,
    ) -> str:
        lines = ["飞书同步预检查完成"]
        for title, keys in (
            ("Creator", (("新增", "creator_create_count"), ("更新", "creator_update_count"))),
            ("Account", (("新增", "account_create_count"), ("更新", "account_update_count"))),
            ("关系", (("建立", "relation_add_count"), ("更新", "relation_update_count"), ("移除", "relation_remove_count"))),
        ):
            available = [(label, preview[key]) for label, key in keys if key in preview]
            if available:
                lines.extend(["", title, *(f"{label}：{value}" for label, value in available)])
        if "conflict_count" in preview:
            lines.extend(["", f"冲突：{preview['conflict_count']}"])
        if requires_confirmation:
            lines.extend(["", "回复“确认”执行 Full Sync。", "5 分钟内有效。"])
        else:
            lines.extend(["", "本次仅预检查，未执行写入。"])
        return "\n".join(lines)

    @staticmethod
    def _account_label(account: dict[str, Any]) -> str:
        platform = str(account.get("platform") or "").strip()
        identity = str(account.get("username") or account.get("profile_url") or "").strip()
        if identity and not identity.startswith(("http://", "https://", "@")):
            identity = f"@{identity}"
        return " ".join(filter(None, (platform, identity)))

    @staticmethod
    def _display(value: Any) -> str:
        return "--" if value in (None, "") else str(value)

    @staticmethod
    def _first_present(values: dict[str, Any], keys: tuple[str, ...]) -> Any:
        for key in keys:
            if key in values and values[key] not in (None, ""):
                return values[key]
        return None

    @staticmethod
    def _integer(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _metric(value: Any) -> str:
        if value in (None, ""):
            return ""
        try:
            number = float(value)
        except (TypeError, ValueError):
            return str(value)
        if number >= 1_000_000:
            return f"{number / 1_000_000:.2f}".rstrip("0").rstrip(".") + "M"
        if number >= 1_000:
            return f"{number / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
        return str(int(number) if number.is_integer() else number)

    @classmethod
    def _chunks(cls, text: str) -> tuple[str, ...]:
        if len(text) <= cls.MAX_TEXT_CHARS:
            return (text,)
        chunks = tuple(
            text[index:index + cls.MAX_TEXT_CHARS]
            for index in range(0, len(text), cls.MAX_TEXT_CHARS)
        )
        total = len(chunks)
        return tuple(f"[{index}/{total}]\n{chunk}" for index, chunk in enumerate(chunks, 1))
