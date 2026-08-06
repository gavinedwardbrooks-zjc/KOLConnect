from __future__ import annotations

"""PyInstaller desktop entry point for KOL Connect."""

import errno
import os
import shutil
import socket
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.request import ProxyHandler, build_opener

from app_logging import log_error, log_event
from runtime_paths import atomic_write_json, get_app_data_dir, get_logs_dir, load_json_with_backup


HOST = "127.0.0.1"
PORT = 8765
APP_URL = f"http://{HOST}:{PORT}/"
DEFAULT_WINDOW_WIDTH = 1400
DEFAULT_WINDOW_HEIGHT = 900
MIN_WINDOW_WIDTH = 1000
MIN_WINDOW_HEIGHT = 680
WINDOW_MARGIN_WIDTH = 80
WINDOW_MARGIN_HEIGHT = 120
SERVER_START_TIMEOUT_SECONDS = 60
BACKUP_KEEP_COUNT = 10
_LOCALHOST_OPENER = build_opener(ProxyHandler({}))


def window_state_path() -> Path:
    """Keep native window preferences beside other per-user application data."""
    return get_app_data_dir() / "window_state.json"


def _screen_size() -> tuple[int, int]:
    """Return the current primary display size without adding a GUI dependency."""
    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
        except (AttributeError, OSError):
            pass
    return 1920, 1080


def _window_limits() -> tuple[int, int]:
    screen_width, screen_height = _screen_size()
    return (
        max(MIN_WINDOW_WIDTH, screen_width - WINDOW_MARGIN_WIDTH),
        max(MIN_WINDOW_HEIGHT, screen_height - WINDOW_MARGIN_HEIGHT),
    )


def _default_window_size() -> tuple[int, int]:
    max_width, max_height = _window_limits()
    return min(DEFAULT_WINDOW_WIDTH, max_width), min(DEFAULT_WINDOW_HEIGHT, max_height)


def _valid_window_size(width: object, height: object) -> tuple[int, int] | None:
    try:
        value_width = int(width)
        value_height = int(height)
    except (TypeError, ValueError):
        return None

    max_width, max_height = _window_limits()
    if not (MIN_WINDOW_WIDTH <= value_width <= max_width):
        return None
    if not (MIN_WINDOW_HEIGHT <= value_height <= max_height):
        return None
    return value_width, value_height


def load_window_size() -> tuple[int, int]:
    state, _source = load_json_with_backup(window_state_path())
    if isinstance(state, dict):
        saved_size = _valid_window_size(state.get("width"), state.get("height"))
        if saved_size:
            return saved_size
    return _default_window_size()


def _is_effectively_maximized(width: int, height: int) -> bool:
    screen_width, screen_height = _screen_size()
    return width >= screen_width - 8 and height >= screen_height - 8


def install_window_state_handlers(window: object) -> None:
    """Persist only normal, usable dimensions and never a maximized display size."""
    state = {"maximized": False}
    save_lock = threading.Lock()

    def save_current_size(window: object, *_event_args: object) -> None:
        with save_lock:
            if state["maximized"]:
                return
            try:
                width, height = int(window.width), int(window.height)
            except (AttributeError, OSError, RuntimeError):
                return
            if _is_effectively_maximized(width, height):
                return
            size = _valid_window_size(width, height)
            if size:
                atomic_write_json(window_state_path(), {"width": size[0], "height": size[1]})

    def mark_maximized(window: object, *_event_args: object) -> None:
        state["maximized"] = True

    def mark_restored(window: object, *_event_args: object) -> None:
        state["maximized"] = False
        save_current_size(window)

    window.events.resized += save_current_size
    window.events.maximized += mark_maximized
    window.events.restored += mark_restored
    window.events.closing += save_current_size


def server_is_ready() -> bool:
    try:
        with socket.create_connection((HOST, PORT), timeout=0.4):
            return True
    except OSError:
        return False


def wait_for_server(
    timeout_seconds: float = SERVER_START_TIMEOUT_SECONDS,
    startup_state: dict[str, Any] | None = None,
) -> bool:
    """Wait for the local HTTP service without inheriting system proxy settings."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if startup_state and startup_state.get("last_error") is not None:
            return False
        if server_is_ready():
            try:
                with _LOCALHOST_OPENER.open(APP_URL, timeout=1):
                    return True
            except OSError:
                pass
        time.sleep(0.2)
    return False


def _startup_error_message(exc: BaseException) -> str:
    error_number = getattr(exc, "errno", None)
    windows_error = getattr(exc, "winerror", None)
    if error_number == errno.EADDRINUSE or windows_error == 10048:
        return f"端口 {PORT} 被占用。原始错误：{exc}"
    if error_number == errno.EACCES or windows_error == 10013:
        return f"权限不足，无法启动本地服务。原始错误：{exc}"
    return f"服务启动失败：{exc}"


def _record_startup_error(server_module: ModuleType, message: str, exc: BaseException) -> None:
    log_error("Launcher", message, exc)
    try:
        server_module._record_last_error(message)
    except (AttributeError, OSError, RuntimeError, ValueError) as diagnostic_error:
        log_error("Launcher", "启动错误写入系统诊断失败", diagnostic_error)


def _run_server(server_module: ModuleType, startup_state: dict[str, Any]) -> None:
    try:
        server_module.run()
    except BaseException as exc:
        startup_state["last_error"] = exc
        message = _startup_error_message(exc)
        _record_startup_error(server_module, message, exc)
    else:
        exc = RuntimeError("本地服务线程在启动期间意外退出。")
        startup_state["last_error"] = exc
        _record_startup_error(server_module, str(exc), exc)


def backup_creator_library(workbook_path: Path) -> Path | None:
    """Create a best-effort startup backup and retain only the newest copies."""
    if not workbook_path.is_file():
        return None
    backup_dir = workbook_path.parent / "backups"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{workbook_path.stem}_{timestamp}{workbook_path.suffix}"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(workbook_path, backup_path)
        backups = sorted(
            backup_dir.glob(f"{workbook_path.stem}_*{workbook_path.suffix}"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for stale_backup in backups[BACKUP_KEEP_COUNT:]:
            stale_backup.unlink()
        log_event("Launcher", f"启动备份完成 | path={backup_path}")
        return backup_path
    except OSError as exc:
        log_error("Launcher", f"启动备份失败 | path={workbook_path}", exc)
        return None


def run_scraper_worker() -> None:
    # This flag selects the frozen executable's worker mode; scraper.py does not parse it.
    worker_args = sys.argv
    sys.argv = [argument for argument in sys.argv if argument != "--scraper-worker"]
    import scraper

    try:
        scraper.main()
    finally:
        sys.argv = worker_args


def run_desktop() -> None:
    os.environ["KOLCONNECT_DESKTOP"] = "1"
    import server

    if server_is_ready():
        exc = OSError(errno.EADDRINUSE, f"{HOST}:{PORT}")
        message = _startup_error_message(exc)
        _record_startup_error(server, message, exc)
        raise RuntimeError(message)

    startup_state: dict[str, Any] = {"last_error": None}
    thread = threading.Thread(
        target=_run_server,
        args=(server, startup_state),
        name="kolconnect-server",
        daemon=True,
    )
    thread.start()
    if not wait_for_server(startup_state=startup_state):
        startup_error = startup_state.get("last_error")
        if isinstance(startup_error, BaseException):
            raise RuntimeError(_startup_error_message(startup_error)) from startup_error
        message = f"本地服务启动超时（{SERVER_START_TIMEOUT_SECONDS} 秒），请查看日志。"
        timeout_error = TimeoutError(message)
        _record_startup_error(server, message, timeout_error)
        raise RuntimeError(message)

    workbook_path = Path(
        server.STATE.get("creator_library", {}).get("workbook_path")
        or server.DEFAULT_CREATOR_LIBRARY_WORKBOOK
    )
    backup_creator_library(workbook_path)

    import webview

    width, height = load_window_size()
    window = webview.create_window(
        "KOLConnect v0.2.0-dev.2",
        APP_URL,
        width=width,
        height=height,
        min_size=(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT),
        resizable=True,
    )
    install_window_state_handlers(window)
    webview.start()


def main() -> None:
    get_logs_dir()
    if "--scraper-worker" in sys.argv:
        run_scraper_worker()
        return
    run_desktop()


if __name__ == "__main__":
    main()
