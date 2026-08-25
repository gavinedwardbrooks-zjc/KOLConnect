from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import importlib
import importlib.metadata
import inspect
import threading
import time
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from services.assistant_confirmation_store import AssistantConfirmationStore, ConfirmationError  # noqa: E402
from services.assistant_provider import AssistantIntent, MockAssistantProvider  # noqa: E402
from services.assistant_service import AssistantService  # noqa: E402
from services.feishu_chat_message_adapter import FeishuChatMessage, FeishuChatMessageAdapter  # noqa: E402
from services.feishu_chat_service import FeishuChatService, ProcessedEventCache  # noqa: E402
from services.feishu_chat_transport import (  # noqa: E402
    FEISHU_CHAT_CONNECT_TIMEOUT_SECONDS,
    FeishuChatTransport,
    FeishuChatTransportError,
)
from http_handlers import feishu_chat_handler  # noqa: E402


def message(
    identity: str,
    text: str,
    *,
    chat_id: str = "chat-a",
    sender_id: str = "user-a",
    chat_type: str = "p2p",
    mentioned_bot: bool = False,
    message_type: str = "text",
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


class StubAssistant:
    def __init__(self) -> None:
        self.confirmations = AssistantConfirmationStore()
        self.messages: list[tuple[str, str, str]] = []
        self.confirm_calls: list[tuple[str, str]] = []
        self.executions = 0

    def message(self, text: str, session_id: str, trace_id: str):
        self.messages.append((text, session_id, trace_id))
        if text == "write":
            record = self.confirmations.create(session_id, "create_capture_task", {}, trace_id)
            return {
                "ok": True,
                "intent": "create_capture_task",
                "reply": "准备执行写操作。",
                "requires_confirmation": True,
                "confirmation_token": record.token,
                "data": {},
            }
        return {
            "ok": True,
            "intent": "daily_summary",
            "reply": "读取完成。",
            "requires_confirmation": False,
            "data": {},
        }

    def confirm(self, token: str, confirm: bool, session_id: str, trace_id: str):
        self.confirm_calls.append((token, session_id))
        try:
            self.confirmations.consume(token, session_id)
        except ConfirmationError as exc:
            return {"ok": False, "error": {"code": str(exc), "message": "确认无效。"}}
        self.executions += 1
        return {
            "ok": True,
            "intent": "create_capture_task",
            "reply": "已执行。",
            "requires_confirmation": False,
            "data": {},
        }


class FeishuMessageAdapterTests(unittest.TestCase):
    def test_raw_v2_text_event_uses_stable_identity_and_session(self):
        normalized = FeishuChatMessageAdapter.normalize({
            "header": {"event_id": "event-1"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou-user"}},
                "message": {
                    "message_id": "om-message",
                    "chat_id": "oc-chat",
                    "chat_type": "p2p",
                    "message_type": "text",
                    "content": '{"text":"find creators"}',
                },
            },
        })
        self.assertIsNotNone(normalized)
        self.assertEqual("find creators", normalized.text)
        self.assertEqual("feishu:direct:oc-chat", normalized.session_id)

    def test_raw_group_event_does_not_guess_that_any_mention_is_the_bot(self):
        normalized = FeishuChatMessageAdapter.normalize({
            "header": {"event_id": "event-2"},
            "event": {
                "sender": {"sender_id": {"open_id": "ou-user"}},
                "message": {
                    "message_id": "om-message-2",
                    "chat_id": "oc-group",
                    "chat_type": "group",
                    "message_type": "text",
                    "content": '{"text":"hello"}',
                    "mentions": [{"id": {"user_id": "someone-else"}}],
                },
            },
        })
        self.assertFalse(normalized.mentioned_bot)
        self.assertEqual("feishu:group:oc-group:ou-user", normalized.session_id)

    def test_malformed_event_is_rejected(self):
        self.assertIsNone(FeishuChatMessageAdapter.normalize({"event": {"message": {}}}))

    def test_only_official_policy_admitted_sdk_group_can_supply_trusted_mention(self):
        class SdkMessage:
            raw = {"header": {"event_id": "event-sdk"}}
            message_id = "message-sdk"
            chat_id = "group-sdk"
            sender_id = "user-sdk"
            chat_type = "group"
            raw_content_type = "text"
            content_text = "hello"
            mentioned_bot = False

        untrusted = FeishuChatMessageAdapter.normalize(SdkMessage())
        trusted = FeishuChatMessageAdapter.normalize(SdkMessage(), trusted_group_mention=True)
        self.assertFalse(untrusted.mentioned_bot)
        self.assertTrue(trusted.mentioned_bot)


class FeishuChatServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assistant = StubAssistant()
        self.counter = 0
        self.service = FeishuChatService(self.assistant, trace_id_provider=self._trace)

    def _trace(self) -> str:
        self.counter += 1
        return f"trace-{self.counter}"

    def test_direct_and_mentioned_group_messages_delegate_with_isolated_sessions(self):
        direct = self.service.handle(message("direct", "read"))
        group = self.service.handle(message(
            "group", "read", chat_id="group-a", sender_id="user-b",
            chat_type="group", mentioned_bot=True,
        ))
        self.assertIn("今日概览", direct.replies[0])
        self.assertIn("今日概览", group.replies[0])
        self.assertEqual("feishu:direct:chat-a", self.assistant.messages[0][1])
        self.assertEqual("feishu:group:group-a:user-b", self.assistant.messages[1][1])

    def test_group_without_bot_mention_is_ignored(self):
        outcome = self.service.handle(message("group", "read", chat_type="group"))
        self.assertTrue(outcome.ignored)
        self.assertEqual([], self.assistant.messages)

    def test_duplicate_event_and_unsupported_type_do_not_execute_tools(self):
        first = self.service.handle(message("same", "read"))
        duplicate = self.service.handle(message("same", "read"))
        unsupported = self.service.handle(message("image", "", message_type="image"))
        self.assertFalse(first.ignored)
        self.assertTrue(duplicate.ignored)
        self.assertIn("支持文字", unsupported.replies[0])
        self.assertEqual(1, len(self.assistant.messages))

    def test_same_message_id_with_different_event_id_is_deduplicated(self):
        first = message("first", "read")
        replay = FeishuChatMessage(
            event_id="event-redelivery",
            message_id=first.message_id,
            chat_id=first.chat_id,
            sender_id=first.sender_id,
            chat_type=first.chat_type,
            message_type=first.message_type,
            text=first.text,
            mentioned_bot=first.mentioned_bot,
        )
        self.assertFalse(self.service.handle(first).ignored)
        self.assertTrue(self.service.handle(replay).ignored)
        self.assertEqual(1, len(self.assistant.messages))

    def test_confirmation_is_same_session_single_use_and_cancel_is_non_mutating(self):
        preview = self.service.handle(message("preview", "write"))
        self.assertIn("回复“确认”", preview.replies[0])
        wrong_session = self.service.handle(message("wrong", "确认", chat_id="chat-b"))
        self.assertIn("没有可确认", wrong_session.replies[0])
        confirmed = self.service.handle(message("confirm", "确认"))
        replay = self.service.handle(message("replay", "确认"))
        self.assertEqual("已执行。", confirmed.replies[0])
        self.assertIn("没有可确认", replay.replies[0])
        self.assertEqual(1, self.assistant.executions)

        self.service.handle(message("preview-2", "write"))
        canceled = self.service.handle(message("cancel", "取消"))
        after_cancel = self.service.handle(message("confirm-after-cancel", "确认"))
        self.assertIn("不会执行", canceled.replies[0])
        self.assertIn("没有可确认", after_cancel.replies[0])
        self.assertEqual(1, self.assistant.executions)

    def test_new_preview_invalidates_previous_token(self):
        self.service.handle(message("preview-a", "write"))
        old_token = next(iter(self.assistant.confirmations._records))
        self.service.handle(message("preview-b", "write"))
        with self.assertRaisesRegex(ConfirmationError, "CONFIRMATION_ALREADY_USED"):
            self.assistant.confirmations.consume(old_token, "feishu:direct:chat-a")

    def test_expired_confirmation_cannot_execute(self):
        self.service.handle(message("expiring-preview", "write"))
        token = next(iter(self.assistant.confirmations._records))
        self.assistant.confirmations._records[token].expires_at = (
            datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        result = self.service.handle(message("expired-confirm", "确认"))
        self.assertIn("确认无效", result.replies[0])
        self.assertEqual(0, self.assistant.executions)

    def test_full_sync_uses_real_assistant_preview_and_confirmation_contract(self):
        calls = []
        service = AssistantService(
            MockAssistantProvider(AssistantIntent("feishu_full_sync", {})),
            {
                "feishu_sync_dry_run": lambda: {
                    "creator_create_count": 1,
                    "account_create_count": 2,
                    "relation_add_count": 2,
                    "conflict_count": 0,
                },
                "feishu_full_sync": lambda: calls.append("full") or {"status": "success"},
            },
        )
        chat = FeishuChatService(service, trace_id_provider=lambda: "trace-safe")
        preview = chat.handle(message("full-preview", "sync"))
        self.assertIn("Creator", preview.replies[0])
        self.assertIn("新增：1", preview.replies[0])
        self.assertEqual([], calls)
        chat.handle(message("full-confirm", "确认"))
        self.assertEqual(["full"], calls)

    def test_processed_event_cache_is_bounded_and_expires(self):
        now = [0.0]
        cache = ProcessedEventCache(ttl_seconds=10, max_size=2, clock=lambda: now[0])
        self.assertFalse(cache.duplicate("a"))
        self.assertTrue(cache.duplicate("a"))
        self.assertFalse(cache.duplicate("b"))
        self.assertFalse(cache.duplicate("c"))
        self.assertNotIn("a", cache._items)
        now[0] = 11
        self.assertFalse(cache.duplicate("c"))

    def test_assistant_failure_returns_safe_message_without_exception_details(self):
        class FailingAssistant(StubAssistant):
            def message(self, text, session_id, trace_id):
                raise RuntimeError("app_secret=do-not-leak")

        chat = FeishuChatService(FailingAssistant(), trace_id_provider=lambda: "trace-safe")
        result = chat.handle(message("failure", "read"))
        self.assertIn("稍后再试", result.replies[0])
        self.assertNotIn("secret", result.replies[0])

    def test_long_responses_are_split_without_silent_truncation(self):
        text = "x" * (FeishuChatService.MAX_TEXT_CHARS + 10)
        chunks = FeishuChatService._chunks(text)
        self.assertEqual(2, len(chunks))
        self.assertTrue(chunks[0].startswith("[1/2]"))
        self.assertTrue(chunks[1].startswith("[2/2]"))
        self.assertEqual(text, "".join(chunk.split("\n", 1)[1] for chunk in chunks))

    def test_chat_layer_has_no_direct_storage_bitable_or_generic_io_boundary(self):
        sources = "\n".join(
            (ROOT / "app" / "services" / name).read_text(encoding="utf-8")
            for name in (
                "feishu_chat_message_adapter.py",
                "feishu_chat_service.py",
                "feishu_chat_transport.py",
            )
        ).casefold()
        for forbidden in (
            "excel_workbook_store", "creator_repository", "feishu_client",
            "openpyxl", "subprocess", "os.system", "requests.",
        ):
            self.assertNotIn(forbidden, sources)


class FakeConnection:
    def __init__(self, event=None, *, failure: Exception | None = None) -> None:
        self.event = event
        self.failure = failure
        self.connected = threading.Event()
        self.sent = []
        self.sent_event = threading.Event()

    def run(self, on_message, stop_event, on_state):
        if self.failure:
            raise self.failure
        on_state("connected")
        self.connected.set()
        if self.event:
            on_message(self.event)
        stop_event.wait(2)

    def send(self, chat_id, message_id, text):
        self.sent.append((chat_id, message_id, text))
        self.sent_event.set()

    def request_stop(self):
        pass


class ControlledConnection:
    def __init__(self, *, late_ready: bool = False, failure: Exception | None = None) -> None:
        self.late_ready = late_ready
        self.failure = failure
        self.started = threading.Event()
        self.stopped = threading.Event()
        self.finished = threading.Event()

    def run(self, _on_message, stop_event, on_state):
        self.started.set()
        if self.failure is not None:
            raise self.failure
        stop_event.wait(2)
        if self.late_ready:
            on_state("connected")
        self.finished.set()

    def send(self, _chat_id, _message_id, _text):
        raise AssertionError("send must not run during connection lifecycle tests")

    def request_stop(self):
        self.stopped.set()


class FeishuChatTransportTests(unittest.TestCase):
    def test_disabled_and_missing_credentials_do_not_start_thread(self):
        transport = FeishuChatTransport(
            lambda: {}, lambda: StubAssistant(), trace_id_provider=lambda: "trace"
        )
        try:
            status = transport.start()
            self.assertEqual("error", status["state"])
            self.assertEqual("FEISHU_CHAT_INVALID_CREDENTIALS", status["last_error_code"])
            self.assertIsNone(transport._thread)
        finally:
            transport.close()

    def test_connecting_is_bounded_and_timeout_releases_attempt(self):
        connection = ControlledConnection()
        events = []
        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=lambda _id, _secret: connection,
            connect_timeout_seconds=0.05,
            event_logger=events.append,
        )
        try:
            self.assertEqual("connecting", transport.start()["state"])
            self.assertTrue(connection.started.wait(1))
            deadline = time.monotonic() + 1
            while transport.status()["state"] != "error" and time.monotonic() < deadline:
                time.sleep(0.01)
            status = transport.status()
            self.assertEqual("error", status["state"])
            self.assertEqual("FEISHU_CHAT_CONNECT_TIMEOUT", status["last_error_code"])
            self.assertTrue(connection.stopped.wait(1))
            self.assertTrue(any("CONNECT_TIMEOUT" in event for event in events))
        finally:
            transport.close()

    def test_stop_while_connecting_is_disabled_and_late_ready_is_ignored(self):
        connection = ControlledConnection(late_ready=True)
        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=lambda _id, _secret: connection,
            connect_timeout_seconds=1,
        )
        try:
            transport.start()
            self.assertTrue(connection.started.wait(1))
            self.assertEqual("disabled", transport.stop(timeout=0.5)["state"])
            self.assertTrue(connection.finished.wait(1))
            self.assertEqual("disabled", transport.status()["state"])
            self.assertFalse(transport.status()["bot_enabled"])
        finally:
            transport.close()

    def test_retry_after_timeout_can_connect(self):
        first = ControlledConnection()
        second = FakeConnection()
        connections = iter((first, second))
        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=lambda _id, _secret: next(connections),
            connect_timeout_seconds=0.05,
        )
        try:
            transport.start()
            deadline = time.monotonic() + 1
            while transport.status()["state"] != "error" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual("FEISHU_CHAT_CONNECT_TIMEOUT", transport.status()["last_error_code"])
            self.assertEqual("connecting", transport.start()["state"])
            self.assertTrue(second.connected.wait(1))
            self.assertEqual("connected", transport.status()["state"])
        finally:
            transport.close()

    def test_synchronous_factory_and_asynchronous_network_errors_are_classified(self):
        cases = (
            (lambda _id, _secret: (_ for _ in ()).throw(RuntimeError("invalid credentials")),
             "FEISHU_CHAT_INVALID_CREDENTIALS"),
            (lambda _id, _secret: ControlledConnection(failure=OSError("network unreachable")),
             "FEISHU_CHAT_NETWORK_ERROR"),
        )
        for factory, expected in cases:
            with self.subTest(expected=expected):
                transport = FeishuChatTransport(
                    lambda: {"app_id": "id", "app_secret": "secret"},
                    lambda: StubAssistant(),
                    trace_id_provider=lambda: "trace",
                    connection_factory=factory,
                    connect_timeout_seconds=1,
                )
                try:
                    transport.start()
                    deadline = time.monotonic() + 1
                    while transport.status()["state"] != "error" and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertEqual(expected, transport.status()["last_error_code"])
                finally:
                    transport.close()

    def test_close_during_connecting_is_bounded_and_leaves_no_live_worker(self):
        connection = ControlledConnection()
        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=lambda _id, _secret: connection,
            connect_timeout_seconds=1,
        )
        transport.start()
        self.assertTrue(connection.started.wait(1))
        started = time.monotonic()
        transport.close()
        self.assertLess(time.monotonic() - started, 1)
        self.assertTrue(connection.finished.wait(1))
        self.assertIsNone(transport._thread)

    def test_production_connection_deadline_is_twenty_seconds(self):
        self.assertEqual(20.0, FEISHU_CHAT_CONNECT_TIMEOUT_SECONDS)


class FeishuChatHandlerAndPackagingTests(unittest.TestCase):
    def test_installed_official_sdk_matches_runtime_contract_without_network(self):
        from lark_oapi.channel import Events, FeishuChannel, PolicyConfig, SendResult

        self.assertEqual("1.7.2", importlib.metadata.version("lark-oapi"))
        self.assertEqual("message", Events.MESSAGE)
        self.assertEqual("reconnecting", Events.RECONNECTING)
        self.assertEqual("reconnected", Events.RECONNECTED)
        self.assertTrue(inspect.iscoroutinefunction(FeishuChannel.connect_until_ready))
        self.assertTrue(inspect.iscoroutinefunction(FeishuChannel.send))
        self.assertTrue(inspect.iscoroutinefunction(FeishuChannel.disconnect))
        self.assertTrue(hasattr(FeishuChannel, "stop"))
        self.assertIn("success", inspect.signature(SendResult).parameters)
        self.assertIsNotNone(importlib.import_module(
            "lark_oapi.api.im.v1.model.p2_im_message_receive_v1"
        ))
        channel = FeishuChannel(
            app_id="cli_contract_test",
            app_secret="not-a-real-secret",
            policy=PolicyConfig(require_mention=True),
        )
        self.assertTrue(callable(channel.on("message", lambda _message: None)))

    def test_enable_disable_and_status_persist_explicit_preference(self):
        class Handler:
            def _ok(self, **payload):
                self.payload = payload

        class Transport:
            def status(self): return {"state": "disabled", "bot_enabled": False}
            def start(self): return {"state": "connecting", "bot_enabled": True}
            def stop(self): return {"state": "disabled", "bot_enabled": False}
            def local_test(self): return {"ok": True, "state": "disabled"}

        state = {"feishu": {"chat_enabled": False}}
        saves = []
        context = {
            "services": {"feishu_chat": Transport()},
            "state": {"get": lambda: state, "save": lambda: saves.append(True)},
        }
        handler = Handler()
        self.assertTrue(feishu_chat_handler.handle(
            handler, {"method": "POST", "path": "/api/feishu-chat/enable"}, context
        ))
        self.assertTrue(state["feishu"]["chat_enabled"])
        self.assertEqual("connecting", handler.payload["state"])
        self.assertTrue(feishu_chat_handler.handle(
            handler, {"method": "POST", "path": "/api/feishu-chat/disable"}, context
        ))
        self.assertFalse(state["feishu"]["chat_enabled"])
        self.assertEqual(2, len(saves))

    def test_connection_error_reaches_status_endpoint_without_secret_details(self):
        class Handler:
            def _ok(self, **payload):
                self.payload = payload

        class Transport:
            def status(self):
                return {
                    "state": "error",
                    "bot_enabled": False,
                    "last_error_code": "FEISHU_CHAT_CONNECT_TIMEOUT",
                }

        handler = Handler()
        handled = feishu_chat_handler.handle(
            handler,
            {"method": "GET", "path": "/api/feishu-chat/status"},
            {
                "services": {"feishu_chat": Transport()},
                "state": {"get": lambda: {"feishu": {}}},
            },
        )
        self.assertTrue(handled)
        self.assertEqual("error", handler.payload["state"])
        self.assertEqual("FEISHU_CHAT_CONNECT_TIMEOUT", handler.payload["last_error_code"])
        self.assertNotIn("secret", str(handler.payload).casefold())

    def test_packaging_collects_official_sdk_on_all_platforms(self):
        requirements = (ROOT / "packaging" / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("lark-oapi==1.7.2", requirements)
        for name in ("KOLConnect.spec", "KOLConnect_mac.spec", "KOLConnect_mac_intel.spec"):
            source = (ROOT / "packaging" / "spec" / name).read_text(encoding="utf-8")
            self.assertIn("lark_oapi", source, name)

    def test_server_owns_optional_transport_lifecycle(self):
        source = (ROOT / "app" / "server.py").read_text(encoding="utf-8-sig")
        self.assertIn('"chat_enabled": False', source)
        self.assertIn("chat_transport.start()", source)
        self.assertIn("chat_transport.close()", source)
        self.assertIn("feishu_chat_handler", source)

    def test_official_connection_freezes_group_mention_policy(self):
        source = (ROOT / "app" / "services" / "feishu_chat_transport.py").read_text(encoding="utf-8")
        self.assertIn("PolicyConfig(require_mention=True)", source)
        self.assertIn('self._channel.on("reconnecting"', source)
        self.assertIn('self._channel.on("reconnected"', source)
        self.assertIn("def reconnecting(_event=None)", source)
        self.assertIn("def reconnected(_event=None)", source)
        self.assertNotIn("async def reconnecting", source)

    def test_actionable_connection_errors_are_classified(self):
        classify = FeishuChatTransport._classify_error
        self.assertEqual("FEISHU_CHAT_EVENT_CONFIGURATION_ERROR", classify(RuntimeError("bot capability disabled")))
        self.assertEqual("FEISHU_CHAT_EVENT_CONFIGURATION_ERROR", classify(RuntimeError("event permission denied")))
        self.assertEqual("FEISHU_CHAT_PERMISSION_DENIED", classify(PermissionError("forbidden")))
        self.assertEqual("FEISHU_CHAT_INVALID_CREDENTIALS", classify(RuntimeError("invalid credentials")))
        self.assertEqual("FEISHU_CHAT_NETWORK_ERROR", classify(OSError("websocket connection failed")))
        self.assertEqual("FEISHU_CHAT_SDK_ERROR", classify(RuntimeError("unexpected sdk state")))

    def test_connection_start_message_reply_and_clean_stop(self):
        raw = {
            "header": {"event_id": "event-live"},
            "event": {
                "sender": {"sender_id": {"open_id": "user-live"}},
                "message": {
                    "message_id": "message-live", "chat_id": "chat-live",
                    "chat_type": "p2p", "message_type": "text",
                    "content": '{"text":"read"}',
                },
            },
        }
        connection = FakeConnection(raw)
        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=lambda _id, _secret: connection,
        )
        try:
            self.assertEqual("connecting", transport.start()["state"])
            self.assertTrue(connection.connected.wait(1))
            self.assertTrue(connection.sent_event.wait(1))
            self.assertEqual("connected", transport.status()["state"])
            self.assertIn("今日概览", connection.sent[0][2])
            self.assertEqual("disabled", transport.stop()["state"])
        finally:
            transport.close()

    def test_connection_error_is_sanitized_and_local_test_does_not_connect(self):
        connection = FakeConnection(failure=PermissionError("permission denied with secret"))
        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=lambda _id, _secret: connection,
        )
        try:
            local = transport.local_test()
            self.assertTrue(local["ok"])
            self.assertFalse(connection.connected.is_set())
            transport.start()
            deadline = time.monotonic() + 1
            while transport.status()["state"] != "error" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual("FEISHU_CHAT_PERMISSION_DENIED", transport.status()["last_error_code"])
            self.assertNotIn("secret", str(transport.status()))
        finally:
            transport.close()

    def test_missing_sdk_is_a_nonfatal_local_test_result(self):
        def unavailable(_app_id, _app_secret):
            raise FeishuChatTransportError("SDK_NOT_AVAILABLE", "not installed")

        transport = FeishuChatTransport(
            lambda: {"app_id": "id", "app_secret": "secret"},
            lambda: StubAssistant(),
            trace_id_provider=lambda: "trace",
            connection_factory=unavailable,
        )
        try:
            self.assertEqual("SDK_NOT_AVAILABLE", transport.local_test()["error_code"])
        finally:
            transport.close()


if __name__ == "__main__":
    unittest.main()
