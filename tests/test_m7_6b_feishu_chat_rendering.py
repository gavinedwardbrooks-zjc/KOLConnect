from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.assistant_confirmation_store import (  # noqa: E402
    AssistantConfirmationStore,
    ConfirmationError,
)
from services.assistant_intent_router import AssistantIntent  # noqa: E402
from services.assistant_provider import (  # noqa: E402
    DeterministicAssistantProvider,
    MockAssistantProvider,
)
from services.assistant_service import AssistantService  # noqa: E402
from services.feishu_chat_message_adapter import FeishuChatMessage  # noqa: E402
from services.feishu_chat_service import FeishuChatService  # noqa: E402


def chat_message(
    identity: str,
    text: str,
    *,
    chat_id: str = "chat-a",
    sender_id: str = "user-a",
    chat_type: str = "p2p",
    message_type: str = "text",
    mentioned_bot: bool = True,
) -> FeishuChatMessage:
    return FeishuChatMessage(
        event_id=f"event-{identity}",
        message_id=f"message-{identity}",
        chat_id=chat_id,
        sender_id=sender_id,
        chat_type=chat_type,
        message_type=message_type,
        text=text,
        mentioned_bot=mentioned_bot,
    )


class ResponseAssistant:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.confirmations = AssistantConfirmationStore()
        self.calls = 0

    def message(self, _text, _session_id, _trace_id):
        self.calls += 1
        return self.response


class FeishuChatRenderingTests(unittest.TestCase):
    def render(self, response: dict, *, identity: str = "render") -> tuple[str, list[str]]:
        events: list[str] = []
        chat = FeishuChatService(
            ResponseAssistant(response),
            trace_id_provider=lambda: "trace_render",
            event_logger=events.append,
        )
        outcome = chat.handle(chat_message(identity, "query"))
        return "\n".join(outcome.replies), events

    def test_campaign_members_include_selected_multi_accounts_once(self):
        response = {
            "ok": True,
            "intent": "get_campaign_detail",
            "requires_confirmation": False,
            "trace_id": "trace_campaign",
            "reply": "已从 KOLConnect 获取结果。",
            "data": {
                "campaign": {
                    "campaign_id": "campaign-father-day",
                    "name": "father day",
                    "product_name": "BLOCK BLAST!",
                    "status": "running",
                    "platforms": ["TikTok", "YouTube"],
                },
                "campaign_creators": [
                    {
                        "id": "relation-a",
                        "creator_id": "creator-a",
                        "creator_name": "INSA",
                        "account_ids": ["account-tiktok", "account-youtube"],
                        "execution_accounts": [
                            {"platform": "TikTok", "username": "insa011_"},
                            {"platform": "YouTube", "username": "insa011"},
                        ],
                    },
                    {
                        "id": "relation-b",
                        "creator_id": "creator-b",
                        "creator_name": "Creator B",
                        "account_id": "account-instagram",
                        "execution_accounts": [
                            {"platform": "Instagram", "username": "creator_b"},
                        ],
                    },
                    {
                        "id": "relation-c",
                        "creator_id": "creator-c",
                        "creator_name": "Creator C",
                        "account_platform": "YouTube",
                        "account_url": "https://youtube.com/@creator-c",
                        "execution_accounts": [],
                    },
                ],
            },
        }
        rendered, _events = self.render(response)
        self.assertIn("father day", rendered)
        self.assertIn("BLOCK BLAST!", rendered)
        self.assertIn("共 3 位达人", rendered)
        self.assertEqual(1, rendered.count("1. INSA"))
        self.assertIn("TikTok @insa011_", rendered)
        self.assertIn("YouTube @insa011", rendered)
        self.assertIn("Creator B", rendered)
        self.assertIn("Creator C", rendered)
        self.assertNotEqual("已从 KOLConnect 获取结果。", rendered)

    def test_real_campaign_phrase_flows_through_assistant_and_renderer(self):
        assistant = AssistantService(
            DeterministicAssistantProvider(),
            {
                "list_campaigns": lambda _arguments: [{
                    "campaign_id": "campaign-father-day", "name": "father day",
                }],
                "get_campaign_detail": lambda _campaign_id: {
                    "campaign": {"campaign_id": "campaign-father-day", "name": "father day"},
                    "campaign_creators": [{
                        "id": "relation-a", "creator_id": "creator-a",
                        "creator_name": "INSA",
                        "execution_accounts": [{"platform": "TikTok", "username": "insa011_"}],
                    }],
                },
            },
        )
        chat = FeishuChatService(assistant, trace_id_provider=lambda: "trace_phrase")
        outcome = chat.handle(chat_message(
            "campaign-phrase", "father day Campaign 有哪些达人？"
        ))
        rendered = "\n".join(outcome.replies)
        self.assertIn("father day", rendered)
        self.assertIn("INSA", rendered)
        self.assertIn("TikTok @insa011_", rendered)
        self.assertNotIn("已从 KOLConnect 获取结果", rendered)

    def test_creator_renderers_preserve_real_detail_and_missing_values(self):
        search, _events = self.render({
            "ok": True,
            "intent": "search_creators",
            "data": {
                "creators": [{
                    "name": "INSA", "platform": "TikTok",
                    "followers": 627600, "country": None,
                }],
                "total": 1,
                "remaining": 0,
            },
        }, identity="search")
        detail, _events = self.render({
            "ok": True,
            "intent": "get_creator_detail",
            "data": {
                "record": {"creator_name": "INSA", "country": "", "language": None},
                "accounts": [
                    {"platform": "TikTok", "username": "insa011_", "followers": 627600},
                    {"platform": "YouTube", "username": "insa011", "followers": 1140000},
                ],
            },
        }, identity="detail")
        self.assertIn("627.6K", search)
        self.assertIn("TikTok insa011_", detail)
        self.assertIn("粉丝：627.6K", detail)
        self.assertIn("YouTube insa011", detail)
        self.assertIn("粉丝：1.14M", detail)
        self.assertIn("地区：--", detail)
        self.assertIn("语言：--", detail)

        empty, _events = self.render({
            "ok": True,
            "intent": "search_creators",
            "data": {"creators": [], "total": 0, "remaining": 0},
        }, identity="empty")
        self.assertEqual("找到 0 位符合条件的达人。", empty)

    def test_campaign_list_task_daily_and_dry_run_are_specific(self):
        cases = (
            ({
                "ok": True, "intent": "list_campaigns",
                "data": {"campaigns": [{"name": "father day", "status": "running"}], "total": 1},
            }, ("father day", "running")),
            ({
                "ok": True, "intent": "get_task_status",
                "data": {"task": {"id": "task-a", "status": "completed"}, "progress": {"completed": 4, "failed": 0}},
            }, ("task-a", "completed", "成功：4", "失败：0")),
            ({
                "ok": True, "intent": "daily_summary",
                "data": {"creator_total": 3, "active_campaign_count": 1, "tasks": {"running": 2}},
            }, ("达人总数：3", "活跃 Campaign：1", "运行中 2")),
            ({
                "ok": True, "intent": "feishu_sync_dry_run",
                "data": {
                    "creator_create_count": 4, "creator_update_count": 0,
                    "account_create_count": 6, "account_update_count": 0,
                    "relation_add_count": 6, "relation_update_count": 4,
                    "relation_remove_count": 0, "conflict_count": 0,
                },
            }, ("新增：4", "新增：6", "建立：6", "更新：4", "冲突：0", "未执行写入")),
        )
        for index, (response, expected) in enumerate(cases):
            with self.subTest(intent=response["intent"]):
                rendered, _events = self.render(response, identity=f"specific-{index}")
                for text in expected:
                    self.assertIn(text, rendered)
                self.assertNotEqual("已从 KOLConnect 获取结果。", rendered)

    def test_unsupported_shape_returns_trace_reference_and_safe_log(self):
        rendered, events = self.render({
            "ok": True,
            "intent": "get_campaign_detail",
            "data": ["app_secret=must-not-log"],
        }, identity="unsupported")
        self.assertIn("暂时无法展示结果", rendered)
        self.assertIn("trace_render", rendered)
        self.assertTrue(any("UNSUPPORTED_RESULT_SHAPE" in event for event in events))
        self.assertNotIn("must-not-log", "\n".join(events))

    def test_renderer_projects_only_safe_campaign_fields(self):
        rendered, _events = self.render({
            "ok": True,
            "intent": "get_campaign_detail",
            "data": {
                "campaign": {"name": "safe", "notes": "private campaign note"},
                "campaign_creators": [{
                    "creator_id": "creator-a", "creator_name": "Creator A",
                    "email": "private@example.com", "whatsapp": "secret-phone",
                    "cost": 999, "execution_accounts": [],
                }],
            },
        }, identity="privacy")
        self.assertIn("safe", rendered)
        self.assertIn("Creator A", rendered)
        for private in ("private campaign note", "private@example.com", "secret-phone", "999"):
            self.assertNotIn(private, rendered)


class FeishuChatConfirmationSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
        self.calls: list[str] = []
        self.store = AssistantConfirmationStore(now=lambda: self.now[0])
        self.assistant = AssistantService(
            MockAssistantProvider(AssistantIntent("feishu_full_sync", {})),
            {
                "feishu_sync_dry_run": lambda: {
                    "creator_create_count": 1,
                    "account_create_count": 2,
                    "relation_add_count": 2,
                    "conflict_count": 0,
                },
                "feishu_full_sync": lambda: self.calls.append("full_sync") or {"status": "success"},
            },
            confirmation_store=self.store,
        )
        self.chat = FeishuChatService(
            self.assistant,
            trace_id_provider=lambda: "trace_confirm",
        )

    def test_cancel_clears_pending_and_confirm_after_cancel_never_executes(self):
        preview = self.chat.handle(chat_message("preview", "同步到飞书"))
        self.assertIn("回复“确认”", preview.replies[0])
        canceled = self.chat.handle(chat_message("cancel", "取消"))
        after_cancel = self.chat.handle(chat_message("after-cancel", "确认"))
        self.assertIn("已取消", canceled.replies[0])
        self.assertIn("不会执行", canceled.replies[0])
        self.assertIn("没有可确认", after_cancel.replies[0])
        self.assertEqual([], self.calls)

    def test_expired_replayed_and_wrong_session_confirmations_are_blocked(self):
        self.chat.handle(chat_message("preview-expired", "同步到飞书"))
        self.now[0] += timedelta(minutes=6)
        expired = self.chat.handle(chat_message("expired", "确认"))
        self.assertIn("失效", expired.replies[0])
        self.assertEqual([], self.calls)

        self.chat.handle(chat_message("preview-session", "同步到飞书"))
        wrong = self.chat.handle(chat_message("wrong", "确认", chat_id="chat-b"))
        self.assertIn("没有可确认", wrong.replies[0])
        confirmed = self.chat.handle(chat_message("right", "确认"))
        replay = self.chat.handle(chat_message("replay", "确认"))
        self.assertIn("success", confirmed.replies[0])
        self.assertIn("没有可确认", replay.replies[0])
        self.assertEqual(["full_sync"], self.calls)

    def test_new_preview_invalidates_old_confirmation(self):
        self.chat.handle(chat_message("preview-one", "同步到飞书"))
        old_token = next(iter(self.store._records))
        self.chat.handle(chat_message("preview-two", "同步到飞书"))
        with self.assertRaisesRegex(ConfirmationError, "CONFIRMATION_ALREADY_USED"):
            self.store.consume(old_token, "feishu:direct:chat-a")
        self.assertEqual([], self.calls)

    def test_duplicate_event_non_text_and_group_session_safety_are_preserved(self):
        image = self.chat.handle(chat_message("image", "", message_type="image"))
        self.assertEqual("目前我先支持文字消息。", image.replies[0])

        message = chat_message("dedupe", "同步到飞书")
        first = self.chat.handle(message)
        duplicate = self.chat.handle(message)
        self.assertFalse(first.ignored)
        self.assertTrue(duplicate.ignored)

        group_preview = self.chat.handle(chat_message(
            "group-preview", "同步到飞书", chat_id="group-a",
            sender_id="user-a", chat_type="group",
        ))
        group_wrong = self.chat.handle(chat_message(
            "group-wrong", "确认", chat_id="group-a",
            sender_id="user-b", chat_type="group",
        ))
        self.assertIn("回复“确认”", group_preview.replies[0])
        self.assertIn("没有可确认", group_wrong.replies[0])
        self.assertEqual([], self.calls)


if __name__ == "__main__":
    unittest.main()
