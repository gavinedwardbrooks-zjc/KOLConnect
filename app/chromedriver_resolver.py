from __future__ import annotations

"""Resolve a ChromeDriver compatible with the locally installed Chrome."""

import logging
import os
import sys
from pathlib import Path

try:
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:  # Frozen/source startup reports this through the normal browser error path.
    ChromeDriverManager = None


log = logging.getLogger(__name__)

RESOLUTION_ERROR_MESSAGE = (
    "ChromeDriver 自动匹配失败。请检查 Chrome 是否正确安装、网络连接、"
    "Chrome 版本，以及 Driver 下载/cache 状态。"
)


class ChromeDriverResolutionError(RuntimeError):
    """A user-readable ChromeDriver resolution failure."""


def resolve_chromedriver() -> Path:
    """Return webdriver-manager's compatible cached or downloaded driver path."""
    if ChromeDriverManager is None:
        raise ChromeDriverResolutionError(
            f"{RESOLUTION_ERROR_MESSAGE} webdriver-manager 未安装。"
        )

    try:
        resolved = ChromeDriverManager().install()
    except Exception as exc:
        log.warning("ChromeDriver resolver failure: %s", exc)
        raise ChromeDriverResolutionError(RESOLUTION_ERROR_MESSAGE) from exc

    driver_path = Path(str(resolved or "")).expanduser()
    if not resolved or not driver_path.is_file():
        log.warning("ChromeDriver resolver returned an invalid path: %s", driver_path)
        raise ChromeDriverResolutionError(
            f"{RESOLUTION_ERROR_MESSAGE} 下载或缓存中的 Driver 文件不可用。"
        )

    if sys.platform != "win32" and not os.access(driver_path, os.X_OK):
        log.warning("Resolved ChromeDriver is not executable: %s", driver_path)
        raise ChromeDriverResolutionError(
            f"{RESOLUTION_ERROR_MESSAGE} Driver 文件没有执行权限。"
        )

    return driver_path
