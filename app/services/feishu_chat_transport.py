from __future__ import annotations

"""Optional official-SDK long connection for the KOLConnect Assistant."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import threading
from typing import Any, Callable, Protocol

from services.feishu_chat_message_adapter import FeishuChatMessageAdapter
from services.feishu_chat_service import FeishuChatService


FEISHU_CHAT_CONNECT_TIMEOUT_SECONDS = 20.0
FEISHU_CHAT_STOP_TIMEOUT_SECONDS = 5.0


class FeishuChatTransportError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class Connection(Protocol):
    def run(
        self,
        on_message: Callable[[Any], None],
        stop_event: threading.Event,
        on_state: Callable[[str], None],
    ) -> None: ...

    def send(self, chat_id: str, message_id: str, text: str) -> None: ...

    def request_stop(self) -> None: ...


@dataclass
class FeishuChatStatus:
    state: str = "disabled"
    transport: str = "long_connection"
    bot_enabled: bool = False
    last_connected_at: str = ""
    last_error_code: str = ""
    connecting_started_at: str = ""


@dataclass(frozen=True)
class OfficialInbound:
    payload: Any
    group_mention_policy_enforced: bool = True


class OfficialLarkConnection:
    """Lazy lark-oapi Channel adapter; importing it never affects disabled startup."""

    def __init__(self, app_id: str, app_secret: str) -> None:
        try:
            from lark_oapi.channel import FeishuChannel, PolicyConfig
        except ImportError as exc:
            raise FeishuChatTransportError(
                "SDK_NOT_AVAILABLE", "飞书官方 SDK 未安装或未打包。"
            ) from exc
        self._channel = FeishuChannel(
            app_id=app_id,
            app_secret=app_secret,
            policy=PolicyConfig(require_mention=True),
        )
        self._loop: asyncio.AbstractEventLoop | None = None

    def run(self, on_message, stop_event, on_state) -> None:
        asyncio.run(self._run(on_message, stop_event, on_state))

    async def _run(self, on_message, stop_event, on_state) -> None:
        self._loop = asyncio.get_running_loop()
        if stop_event.is_set():
            return

        async def receive(message) -> None:
            # Return to the SDK quickly; Assistant work runs outside event dispatch.
            on_message(OfficialInbound(message))

        def reconnecting(_event=None) -> None:
            on_state("connecting")

        def reconnected(_event=None) -> None:
            on_state("connected")

        self._channel.on("message", receive)
        self._channel.on("reconnecting", reconnecting)
        self._channel.on("reconnected", reconnected)
        # The application-level watchdog owns the deadline. SDK 1.7.2 calls
        # its synchronous stop() from its timeout coroutine, which can delay
        # propagating the timeout while the WebSocket worker is still starting.
        await self._channel.connect_until_ready(timeout=None)
        if stop_event.is_set() or not self._channel.is_ready:
            return
        on_state("connected")
        try:
            while not stop_event.is_set():
                await asyncio.sleep(0.2)
        finally:
            await self._channel.disconnect()

    def send(self, chat_id: str, message_id: str, text: str) -> None:
        if self._loop is None or self._loop.is_closed():
            raise FeishuChatTransportError("LONG_CONNECTION_FAILED", "飞书长连接不可用。")
        future = asyncio.run_coroutine_threadsafe(
            self._channel.send(
                chat_id,
                {"text": text},
                {"reply_to": message_id},
            ),
            self._loop,
        )
        result = future.result(timeout=20)
        if getattr(result, "success", True) is False or getattr(result, "error", None):
            raise FeishuChatTransportError("BOT_PERMISSION_MISSING", "机器人无法发送消息。")

    def request_stop(self) -> None:
        self._channel.stop(join_timeout=2.0)


class FeishuChatTransport:
    def __init__(
        self,
        config_provider: Callable[[], dict[str, Any]],
        assistant_provider: Callable[[], Any],
        *,
        trace_id_provider: Callable[[], str],
        connection_factory: Callable[[str, str], Connection] | None = None,
        event_logger: Callable[[str], None] | None = None,
        error_logger: Callable[[str, BaseException], None] | None = None,
        connect_timeout_seconds: float = FEISHU_CHAT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._config_provider = config_provider
        self._assistant_provider = assistant_provider
        self._trace_id_provider = trace_id_provider
        self._connection_factory = connection_factory or OfficialLarkConnection
        self._event_logger = event_logger or (lambda _message: None)
        self._error_logger = error_logger or (lambda _message, _exc: None)
        self._connect_timeout_seconds = connect_timeout_seconds
        self._status = FeishuChatStatus()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._connect_timer: threading.Timer | None = None
        self._attempt_generation = 0
        self._connection: Connection | None = None
        self._chat_service: FeishuChatService | None = None
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="feishu-assistant")
        self._executor_closed = False
        self._pending_slots = threading.BoundedSemaphore(16)
        self._lock = threading.RLock()

    def start(self) -> dict[str, Any]:
        config = self._config_provider()
        app_id = str(config.get("app_id") or "").strip()
        app_secret = str(config.get("app_secret") or "").strip()
        if not app_id or not app_secret:
            return self._set_error("FEISHU_CHAT_INVALID_CREDENTIALS")
        with self._lock:
            if self._thread and self._thread.is_alive():
                if self._status.state in {"connecting", "connected"}:
                    return asdict(self._status)
                stale_thread = self._thread
            else:
                stale_thread = None
        if stale_thread is not None:
            self._stop_attempt(stale_thread, timeout=FEISHU_CHAT_STOP_TIMEOUT_SECONDS)

        with self._lock:
            self._attempt_generation += 1
            generation = self._attempt_generation
            self._stop_event = threading.Event()
            stop_event = self._stop_event
            self._status = FeishuChatStatus(
                state="connecting",
                bot_enabled=True,
                connecting_started_at=self._utc_now(),
            )
            timer = threading.Timer(
                self._connect_timeout_seconds,
                self._connection_timed_out,
                args=(generation, stop_event),
            )
            timer.daemon = True
            self._connect_timer = timer
            self._thread = threading.Thread(
                target=self._run,
                args=(generation, stop_event, app_id, app_secret),
                name="feishu-chat-long-connection",
                daemon=True,
            )
            timer.start()
            self._thread.start()
        self._event_logger("feishu_chat lifecycle=SDK_START transport=long_connection")
        self._event_logger("feishu_chat lifecycle=CONNECTING transport=long_connection")
        return self.status()

    def stop(self, timeout: float = FEISHU_CHAT_STOP_TIMEOUT_SECONDS) -> dict[str, Any]:
        with self._lock:
            self._attempt_generation += 1
            thread = self._thread
            connection = self._connection
            timer = self._connect_timer
            self._stop_event.set()
            if timer is not None:
                timer.cancel()
                self._connect_timer = None
        self._request_connection_stop(connection)
        self._join_thread(thread, timeout)
        with self._lock:
            self._thread = None
            self._connection = None
            self._status.state = "disabled"
            self._status.bot_enabled = False
            self._status.connecting_started_at = ""
        self._event_logger("feishu_chat lifecycle=STOPPED transport=long_connection")
        return self.status()

    def close(self) -> None:
        with self._lock:
            if self._executor_closed:
                return
            self._executor_closed = True
        self.stop()
        self._executor.shutdown(wait=True, cancel_futures=True)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    def local_test(self) -> dict[str, Any]:
        config = self._config_provider()
        if not str(config.get("app_id") or "").strip() or not str(config.get("app_secret") or "").strip():
            return {"ok": False, "error_code": "FEISHU_CHAT_INVALID_CREDENTIALS", **self.status()}
        try:
            connection = self._connection_factory(
                str(config["app_id"]).strip(), str(config["app_secret"]).strip()
            )
        except FeishuChatTransportError as exc:
            return {"ok": False, "error_code": exc.code, **self.status()}
        del connection
        return {
            "ok": True,
            "configuration_ok": True,
            "sdk_available": True,
            "network_tested": self.status()["state"] == "connected",
            **self.status(),
        }

    def _run(
        self,
        generation: int,
        stop_event: threading.Event,
        app_id: str,
        app_secret: str,
    ) -> None:
        try:
            if stop_event.is_set():
                return
            connection = self._connection_factory(app_id, app_secret)
            chat_service = FeishuChatService(
                self._assistant_provider(),
                trace_id_provider=self._trace_id_provider,
                event_logger=self._event_logger,
            )
            with self._lock:
                if generation != self._attempt_generation or stop_event.is_set():
                    self._request_connection_stop(connection)
                    return
                self._connection = connection
                self._chat_service = chat_service
            connection.run(
                lambda message: self._queue_receive(generation, stop_event, message),
                stop_event,
                lambda state: self._state_changed(generation, stop_event, state),
            )
            if not stop_event.is_set():
                self._set_error("FEISHU_CHAT_SDK_ERROR", generation=generation)
        except FeishuChatTransportError as exc:
            code = self._normalize_error_code(exc.code)
            self._set_error(code, generation=generation)
            self._log_safe_error("Feishu Chat connection failed", code)
        except Exception as exc:
            code = self._classify_error(exc)
            self._set_error(code, generation=generation)
            self._log_safe_error("Feishu Chat connection failed", code)
        finally:
            self._event_logger("feishu_chat lifecycle=DISCONNECTED transport=long_connection")
            with self._lock:
                if generation == self._attempt_generation:
                    if self._connect_timer is not None:
                        self._connect_timer.cancel()
                        self._connect_timer = None
                    self._connection = None
                    if self._thread is threading.current_thread():
                        self._thread = None

    def _receive(
        self,
        generation: int,
        stop_event: threading.Event,
        raw_message: Any,
    ) -> None:
        trusted_group_mention = isinstance(raw_message, OfficialInbound)
        payload = raw_message.payload if trusted_group_mention else raw_message
        message = FeishuChatMessageAdapter.normalize(
            payload,
            trusted_group_mention=trusted_group_mention,
        )
        if message is None:
            self._event_logger("feishu_chat malformed_event=true")
            return
        with self._lock:
            if generation != self._attempt_generation or stop_event.is_set():
                return
            service = self._chat_service
            connection = self._connection
        if service is None or connection is None:
            return
        try:
            outcome = service.handle(message)
            if outcome.ignored:
                return
            for reply in outcome.replies:
                connection.send(message.chat_id, message.message_id, reply)
        except Exception:
            self._log_safe_error("Feishu Chat message processing failed", "FEISHU_CHAT_SDK_ERROR")

    def _queue_receive(
        self,
        generation: int,
        stop_event: threading.Event,
        raw_message: Any,
    ) -> None:
        with self._lock:
            stale = generation != self._attempt_generation
        if stale or stop_event.is_set():
            return
        if not self._pending_slots.acquire(blocking=False):
            self._event_logger("feishu_chat queue_full=true")
            return
        try:
            self._executor.submit(
                self._receive_with_release,
                generation,
                stop_event,
                raw_message,
            )
        except RuntimeError:
            self._pending_slots.release()

    def _receive_with_release(
        self,
        generation: int,
        stop_event: threading.Event,
        raw_message: Any,
    ) -> None:
        try:
            self._receive(generation, stop_event, raw_message)
        finally:
            self._pending_slots.release()

    def _state_changed(
        self,
        generation: int,
        stop_event: threading.Event,
        state: str,
    ) -> None:
        with self._lock:
            if generation != self._attempt_generation or stop_event.is_set():
                return
            self._status.state = state
            self._status.bot_enabled = True
            if state == "connected":
                self._status.last_connected_at = self._utc_now()
                self._status.last_error_code = ""
                self._status.connecting_started_at = ""
                if self._connect_timer is not None:
                    self._connect_timer.cancel()
                    self._connect_timer = None
            elif state == "connecting" and self._connect_timer is None:
                self._status.connecting_started_at = self._utc_now()
                timer = threading.Timer(
                    self._connect_timeout_seconds,
                    self._connection_timed_out,
                    args=(generation, stop_event),
                )
                timer.daemon = True
                self._connect_timer = timer
                timer.start()
        lifecycle = "CONNECTED" if state == "connected" else "RECONNECTING"
        self._event_logger(f"feishu_chat lifecycle={lifecycle} transport=long_connection")

    def _set_error(self, code: str, *, generation: int | None = None) -> dict[str, Any]:
        with self._lock:
            if generation is not None and generation != self._attempt_generation:
                return asdict(self._status)
            self._status.state = "error"
            self._status.bot_enabled = False
            self._status.last_error_code = code
            self._status.connecting_started_at = ""
            if self._connect_timer is not None:
                self._connect_timer.cancel()
                self._connect_timer = None
        self._event_logger(
            f"feishu_chat lifecycle=CONNECT_ERROR code={code} transport=long_connection"
        )
        return self.status()

    def _connection_timed_out(
        self,
        generation: int,
        stop_event: threading.Event,
    ) -> None:
        with self._lock:
            if (
                generation != self._attempt_generation
                or stop_event.is_set()
                or self._status.state != "connecting"
            ):
                return
            connection = self._connection
            stop_event.set()
        self._set_error("FEISHU_CHAT_CONNECT_TIMEOUT", generation=generation)
        self._event_logger("feishu_chat lifecycle=CONNECT_TIMEOUT transport=long_connection")
        self._request_connection_stop(connection)

    def _stop_attempt(self, thread: threading.Thread, *, timeout: float) -> None:
        with self._lock:
            connection = self._connection
            self._stop_event.set()
            if self._connect_timer is not None:
                self._connect_timer.cancel()
                self._connect_timer = None
            self._attempt_generation += 1
        self._request_connection_stop(connection)
        self._join_thread(thread, timeout)
        with self._lock:
            if self._thread is thread:
                self._thread = None
            if self._connection is connection:
                self._connection = None

    def _request_connection_stop(self, connection: Connection | None) -> None:
        request_stop = getattr(connection, "request_stop", None)
        if not callable(request_stop):
            return

        def stop_connection() -> None:
            try:
                request_stop()
            except Exception:
                self._log_safe_error("Feishu Chat stop failed", "FEISHU_CHAT_SDK_ERROR")

        threading.Thread(
            target=stop_connection,
            name="feishu-chat-stop",
            daemon=True,
        ).start()

    @staticmethod
    def _join_thread(thread: threading.Thread | None, timeout: float) -> None:
        if thread and thread is not threading.current_thread():
            thread.join(timeout=max(0.0, timeout))

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _log_safe_error(self, message: str, code: str) -> None:
        self._error_logger(message, FeishuChatTransportError(code, code))

    @staticmethod
    def _normalize_error_code(code: str) -> str:
        aliases = {
            "INVALID_APP_CREDENTIALS": "FEISHU_CHAT_INVALID_CREDENTIALS",
            "BOT_PERMISSION_MISSING": "FEISHU_CHAT_PERMISSION_DENIED",
            "EVENT_PERMISSION_MISSING": "FEISHU_CHAT_EVENT_CONFIGURATION_ERROR",
            "LONG_CONNECTION_FAILED": "FEISHU_CHAT_SDK_ERROR",
        }
        return aliases.get(code, code if code.startswith("FEISHU_CHAT_") else "FEISHU_CHAT_SDK_ERROR")

    @staticmethod
    def _classify_error(exc: BaseException) -> str:
        message = str(exc).casefold()
        if "bot capability" in message or "bot not enabled" in message:
            return "FEISHU_CHAT_EVENT_CONFIGURATION_ERROR"
        if "event" in message or "subscription" in message:
            return "FEISHU_CHAT_EVENT_CONFIGURATION_ERROR"
        if "forbidden" in message or "permission" in message:
            return "FEISHU_CHAT_PERMISSION_DENIED"
        if "credential" in message or "auth" in message or "secret" in message:
            return "FEISHU_CHAT_INVALID_CREDENTIALS"
        if any(term in message for term in (
            "network", "dns", "socket", "websocket", "connection", "ssl", "timed out", "timeout",
        )):
            return "FEISHU_CHAT_NETWORK_ERROR"
        return "FEISHU_CHAT_SDK_ERROR"
