from __future__ import annotations

"""PyInstaller desktop entry point for KOL Connect."""

import os
import socket
import sys
import threading
import time
from pathlib import Path
from urllib.request import urlopen

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


def wait_for_server(timeout_seconds: float = 15) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if server_is_ready():
            try:
                with urlopen(APP_URL, timeout=1):
                    return True
            except OSError:
                pass
        time.sleep(0.2)
    return False


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
    if not server_is_ready():
        import server

        thread = threading.Thread(target=server.run, name="kolconnect-server", daemon=True)
        thread.start()
        if not wait_for_server():
            raise RuntimeError("本地服务启动超时，请查看日志。")

    import webview

    width, height = load_window_size()
    window = webview.create_window(
        "KOLConnect v0.2.0-dev.1",
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
