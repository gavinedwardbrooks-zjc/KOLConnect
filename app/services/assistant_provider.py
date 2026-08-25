from __future__ import annotations

"""Small deterministic provider boundary for the M7.3 assistant."""

from dataclasses import dataclass
import re
from typing import Any, Protocol


@dataclass(frozen=True)
class AssistantIntent:
    intent: str
    arguments: dict[str, Any]
    confidence: float = 1.0


class AssistantProvider(Protocol):
    mode: str

    def interpret(self, message: str, context: dict[str, str]) -> AssistantIntent: ...


class DeterministicAssistantProvider:
    """Route a deliberately small command vocabulary without pretending to be AI."""

    mode = "deterministic"

    def interpret(self, message: str, context: dict[str, str]) -> AssistantIntent:
        text = str(message or "").strip()
        lowered = text.casefold()
        if not text:
            return AssistantIntent("", {})
        if any(term in lowered for term in (
            "删除所有", "hard delete", "clean reset", "执行 shell", "shell command",
            "直接编辑 excel", "打开 c:\\", "arbitrary file",
        )):
            return AssistantIntent("unsupported", {})
        if "飞书" in text and any(term in text for term in ("预检查", "dry run", "有什么变化")):
            return AssistantIntent("feishu_sync_dry_run", {})
        if "飞书" in text and any(term in text for term in ("同步", "full sync")):
            return AssistantIntent("feishu_full_sync", {})
        task_id = self._id(text, "task")
        if not task_id and any(term in text for term in ("刚才那个任务", "这个任务")):
            task_id = str(context.get("last_task_id") or "")
        if task_id and any(term in text for term in ("任务", "状态", "怎么样", "完成")):
            return AssistantIntent("get_task_status", {"task_id": task_id})
        url = self._url(text)
        if url and any(term in text for term in ("抓", "采集", "capture", "scrape")):
            return AssistantIntent("create_capture_task", {"url": url})
        if any(term in text for term in ("日报", "每日总结", "daily summary", "运营概览")):
            return AssistantIntent("daily_summary", {})
        campaign_id = self._id(text, "campaign")
        if campaign_id:
            return AssistantIntent("get_campaign_detail", {"campaign_id": campaign_id})
        if "campaign" in lowered or "活动" in text:
            if any(term in text for term in ("有哪些", "列表", "进行中", "最近")):
                return AssistantIntent("list_campaigns", {"status": "running" if "进行中" in text else ""})
            name = re.sub(r"(?i)campaign", "", text)
            name = re.sub(r"(有哪些达人|现在|详情|是哪些平台|计划发布日期|看看)", "", name).strip(" ？?")
            return AssistantIntent("get_campaign_detail", {"name": name})
        creator_id = self._id(text, "creator")
        if not creator_id and "这个达人" in text:
            creator_id = str(context.get("last_creator_id") or "")
        if creator_id:
            return AssistantIntent("get_creator_detail", {"creator_id": creator_id})
        if any(term in text for term in ("资料", "哪些账号", "粉丝多少", "查看达人", "看看")):
            query = re.sub(r"(看看|查看达人|达人|的资料|有哪些账号|粉丝多少|这个)", "", text).strip(" ？?")
            return AssistantIntent("get_creator_detail", {"query": query})
        if any(term in text for term in ("找", "搜索", "search")) and any(
            term in text for term in ("达人", "creator", "kol", "TikTok", "Instagram", "YouTube")
        ):
            return AssistantIntent("search_creators", self._search_arguments(text))
        return AssistantIntent("unsupported", {})

    @staticmethod
    def _id(text: str, prefix: str) -> str:
        match = re.search(rf"\b({prefix}_[0-9A-Za-z_-]+)\b", text, re.IGNORECASE)
        return match.group(1) if match else ""

    @staticmethod
    def _url(text: str) -> str:
        match = re.search(r"https?://[^\s]+", text)
        return match.group(0).rstrip("，,。)") if match else ""

    @staticmethod
    def _search_arguments(text: str) -> dict[str, Any]:
        args: dict[str, Any] = {}
        for platform in ("TikTok", "Instagram", "YouTube"):
            if platform.casefold() in text.casefold():
                args["platform"] = platform
        countries = ("巴西", "Brazil", "美国", "USA", "日本", "Japan")
        for country in countries:
            if country.casefold() in text.casefold():
                args["country"] = country
                break
        limit = re.search(r"(?:找|前|limit\s*)\s*(\d{1,3})\s*(?:个|位|条)?", text, re.IGNORECASE)
        if limit:
            args["limit"] = int(limit.group(1))
        follower_range = re.search(r"(\d+(?:\.\d+)?)\s*万\s*(?:到|[-~至])\s*(\d+(?:\.\d+)?)\s*万", text)
        if follower_range:
            args["followers_min"] = int(float(follower_range.group(1)) * 10000)
            args["followers_max"] = int(float(follower_range.group(2)) * 10000)
        category = re.search(r"(?:内容类型|类型|category)\s*(?:是|为|=)?\s*([\w\u4e00-\u9fff-]+)", text, re.IGNORECASE)
        if category:
            args["content_category"] = category.group(1)
        return args


class MockAssistantProvider:
    mode = "mock"

    def __init__(self, intent: AssistantIntent | Exception) -> None:
        self.intent = intent

    def interpret(self, message: str, context: dict[str, str]) -> AssistantIntent:
        if isinstance(self.intent, Exception):
            raise self.intent
        return self.intent
