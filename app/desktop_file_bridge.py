from __future__ import annotations

"""Narrow pywebview bridge for user-confirmed XLSX saves only."""

import base64
import binascii
import re
import sys
from collections.abc import Sequence
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
            return {
                "saved": False,
                "canceled": False,
                "error_code": "FILE_DIALOG_UNAVAILABLE",
                "error": "无法打开保存对话框。",
            }
        if not selected:
            return {"saved": False, "canceled": True, "path": None}

        try:
            target = _resolve_save_target(_first_dialog_path(selected), filename)
        except (TypeError, ValueError):
            return {
                "saved": False,
                "canceled": False,
                "error_code": "FILE_SELECTION_INVALID",
                "error": "请选择有效的 XLSX 保存位置。",
            }
        if _is_inside_application_bundle(target):
            return {
                "saved": False,
                "canceled": False,
                "error_code": "FILE_DESTINATION_READ_ONLY",
                "error": "请选择应用程序外的保存位置。",
            }
        if not target.parent.is_dir():
            return {
                "saved": False,
                "canceled": False,
                "error_code": "FILE_DESTINATION_UNAVAILABLE",
                "error": "保存位置不可用。",
            }
        if target.exists():
            return {
                "saved": False,
                "canceled": False,
                "error_code": "FILE_ALREADY_EXISTS",
                "error": "目标文件已存在，请选择其他文件名。",
            }
        try:
            with open(target, "wb") as handle:
                handle.write(payload)
        except OSError:
            return {
                "saved": False,
                "canceled": False,
                "error_code": "FILE_WRITE_FAILED",
                "error": "文件保存失败。",
            }
        return {"saved": True, "canceled": False, "path": str(target)}

    def open_xlsx(self) -> dict[str, object]:
        """Read one user-selected XLSX without exposing its local path to JavaScript."""
        if self._window is None:
            return {
                "selected": False,
                "canceled": False,
                "error_code": "FILE_DIALOG_UNAVAILABLE",
                "error": "桌面文件选择窗口不可用。",
            }
        try:
            selected = self._window.create_file_dialog(
                self._webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("Excel files (*.xlsx)",),
            )
        except (AttributeError, OSError, RuntimeError):
            return {
                "selected": False,
                "canceled": False,
                "error_code": "FILE_DIALOG_UNAVAILABLE",
                "error": "无法打开文件选择窗口。",
            }
        if not selected:
            return {"selected": False, "canceled": True}
        try:
            source = Path(_first_dialog_path(selected)).expanduser()
        except (TypeError, ValueError):
            return {
                "selected": False,
                "canceled": False,
                "error_code": "FILE_SELECTION_INVALID",
                "error": "请选择有效的 XLSX 文件。",
            }
        if source.suffix.lower() != ".xlsx" or not source.is_file():
            return {
                "selected": False,
                "canceled": False,
                "error_code": "INVALID_FILE",
                "error": "请选择有效的 XLSX 文件。",
            }
        try:
            payload = source.read_bytes()
        except OSError:
            return {
                "selected": False,
                "canceled": False,
                "error_code": "IMPORT_UPLOAD_FAILED",
                "error": "无法读取所选 XLSX 文件。",
            }
        if not payload:
            return {
                "selected": False,
                "canceled": False,
                "error_code": "INVALID_FILE",
                "error": "所选 XLSX 文件为空。",
            }
        return {
            "selected": True,
            "canceled": False,
            "filename": source.name,
            "payload": base64.b64encode(payload).decode("ascii"),
        }


def _safe_xlsx_filename(value: object) -> str:
    candidate = str(value or "").replace("\\", "/").rsplit("/", 1)[-1]
    candidate = _INVALID_FILENAME_CHARS.sub("_", candidate).strip(". ")
    if not candidate:
        candidate = "KOLConnect_Export"
    return f"{Path(candidate).stem or 'KOLConnect_Export'}.xlsx"


def _resolve_save_target(selected_path: object, suggested_filename: str) -> Path:
    """Turn a native Save dialog selection into a real non-empty XLSX filename."""
    selected = Path(str(selected_path or "")).expanduser()
    if not str(selected_path or "").strip():
        raise ValueError("missing selection")
    if selected.is_dir() or not selected.name:
        return selected / suggested_filename
    return selected if selected.suffix.lower() == ".xlsx" else selected.with_suffix(".xlsx")


def _first_dialog_path(selection: object) -> str:
    """Normalize pywebview's platform-specific dialog return shape."""
    if isinstance(selection, (str, Path)):
        value = str(selection).strip()
    elif isinstance(selection, Sequence) and selection:
        value = str(selection[0] or "").strip()
    else:
        value = ""
    if not value:
        raise ValueError("missing selection")
    return value


def _is_inside_application_bundle(target: Path) -> bool:
    """A packaged macOS app must not use its read-only bundle as export storage."""
    if not getattr(sys, "frozen", False):
        return False
    executable = Path(sys.executable).resolve()
    app_bundle = next((parent for parent in executable.parents if parent.suffix == ".app"), None)
    try:
        return app_bundle is not None and target.resolve().is_relative_to(app_bundle)
    except OSError:
        return False


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
