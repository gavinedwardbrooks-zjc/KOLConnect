from __future__ import annotations

"""Shared Excel access helpers for the local KOLConnect data repositories."""

import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from excel_workbook_store import ExcelWorkbookStore


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ExcelDataRepository:
    """Shared row helpers backed by an injected Excel workbook store."""

    def __init__(self, workbook_path: Path | ExcelWorkbookStore) -> None:
        self.store = (
            workbook_path
            if isinstance(workbook_path, ExcelWorkbookStore)
            else ExcelWorkbookStore(workbook_path)
        )
        self.workbook_path = self.store.workbook_path

    @contextmanager
    def workbook(self, *, write: bool = False) -> Iterator[Any]:
        with self.store.workbook(write=write) as workbook:
            yield workbook

    @staticmethod
    def rows(sheet) -> list[dict[str, Any]]:
        headers = [str(cell.value or "") for cell in sheet[1]]
        records: list[dict[str, Any]] = []
        for values in sheet.iter_rows(min_row=2, values_only=True):
            record = {
                headers[index]: "" if values[index] is None else values[index]
                for index in range(min(len(headers), len(values)))
                if headers[index]
            }
            if any(value not in (None, "") for value in record.values()):
                records.append(record)
        return records

    @classmethod
    def row_by_key(cls, sheet, key: str, value: object) -> dict[str, Any]:
        expected = str(value or "")
        return next(
            (row for row in cls.rows(sheet) if str(row.get(key) or "") == expected),
            {},
        )

    @staticmethod
    def upsert_row(sheet, key: str, key_value: str, values: dict[str, Any]) -> None:
        headers = [str(cell.value or "") for cell in sheet[1]]
        key_index = headers.index(key) + 1
        row_index = next(
            (
                index
                for index in range(2, sheet.max_row + 1)
                if str(sheet.cell(index, key_index).value or "") == key_value
            ),
            sheet.max_row + 1,
        )
        for column, header in enumerate(headers, start=1):
            if header in values:
                sheet.cell(row_index, column, values[header])

    @staticmethod
    def delete_row(sheet, key: str, key_value: str) -> bool:
        headers = [str(cell.value or "") for cell in sheet[1]]
        key_index = headers.index(key) + 1
        for row_index in range(2, sheet.max_row + 1):
            if str(sheet.cell(row_index, key_index).value or "") == key_value:
                sheet.delete_rows(row_index, 1)
                return True
        return False

    @staticmethod
    def require_text(value: object, label: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError(f"{label}不能为空。")
        return text

    @staticmethod
    def optional_number(value: object, label: str, *, integer: bool = False) -> int | float | str:
        raw = str(value if value is not None else "").strip()
        if not raw:
            return ""
        try:
            number = float(raw.replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"{label}必须是数字。") from exc
        if number < 0:
            raise ValueError(f"{label}不能为负数。")
        if integer:
            if not number.is_integer():
                raise ValueError(f"{label}必须是整数。")
            return int(number)
        return number

    @staticmethod
    def publish_links_value(value: object) -> str:
        if value in (None, ""):
            return ""
        if isinstance(value, list):
            links = [str(item or "").strip() for item in value if str(item or "").strip()]
            return json.dumps(links, ensure_ascii=False)
        text = str(value).strip()
        if not text:
            return ""
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("发布链接格式无效。") from exc
            if not isinstance(parsed, list):
                raise ValueError("发布链接必须是链接列表。")
            links = [str(item or "").strip() for item in parsed if str(item or "").strip()]
            return json.dumps(links, ensure_ascii=False)
        links = [item.strip() for item in re.split(r"[\r\n,]+", text) if item.strip()]
        return json.dumps(links, ensure_ascii=False)
