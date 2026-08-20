from __future__ import annotations

"""Narrow pywebview bridge for user-confirmed XLSX saves only."""

import base64
import binascii
import re
from pathlib import Path
from typing import Any


_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')


class DesktopFileBridge:
    """Expose a single Save As operation to the desktop WebView."""

    def __init__(self, webview_module: Any, window: Any | None = None) -> None:
        self._webview = webview_module
        self._window = window

    def bind_window(self, window: Any) -> None:
        self._window = window

    def save_xlsx(self, suggested_filename: object, base64_payload: object) -> dict[str, object]:
        """Save a validated XLSX payload only after a native Save As choice."""
        filename = _safe_xlsx_filename(suggested_filename)
        try:
            payload = _decode_xlsx_payload(base64_payload)
        except (TypeError, ValueError):
            return {"saved": False, "canceled": False, "error": "无效的 XLSX 文件内容。"}

        if self._window is None:
            return {"saved": False, "canceled": False, "error": "桌面保存窗口不可用。"}
        try:
            selected = self._window.create_file_dialog(
                self._webview.FileDialog.SAVE,
                save_filename=filename,
                file_types=("Excel files (*.xlsx)",),
            )
        except (AttributeError, OSError, RuntimeError):
            return {"saved": False, "canceled": False, "error": "无法打开保存对话框。"}
        if not selected:
            return {"saved": False, "canceled": True, "path": None}

        target = Path(str(selected[0])).with_suffix(".xlsx")
        if target.exists():
            return {"saved": False, "canceled": False, "error": "目标文件已存在，请选择其他文件名。"}
        try:
            with open(target, "wb") as handle:
                handle.write(payload)
        except OSError:
            return {"saved": False, "canceled": False, "error": "文件保存失败。"}
        return {"saved": True, "canceled": False, "path": str(target)}


def _safe_xlsx_filename(value: object) -> str:
    candidate = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    candidate = _INVALID_FILENAME_CHARS.sub("_", candidate).strip(". ")
    if not candidate:
        candidate = "KOLConnect_Export"
    return f"{Path(candidate).stem or 'KOLConnect_Export'}.xlsx"


def _decode_xlsx_payload(value: object) -> bytes:
    if not isinstance(value, str) or not value:
        raise ValueError("missing payload")
    try:
        payload = base64.b64decode(value.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("invalid base64") from exc
    if not payload:
        raise ValueError("empty payload")
    return payload
