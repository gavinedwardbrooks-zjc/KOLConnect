from __future__ import annotations

"""Strict extraction of Feishu Bitable relation record IDs."""

from typing import Any


def relation_record_ids(value: Any) -> list[str]:
    """Return explicit record IDs only, preserving first-seen order."""
    result: list[str] = []

    def add(candidate: Any) -> None:
        record_id = str(candidate or "").strip()
        if record_id and record_id not in result:
            result.append(record_id)

    def visit(item: Any) -> None:
        if isinstance(item, list):
            for nested in item:
                visit(nested)
            return
        if not isinstance(item, dict):
            return
        add(item.get("record_id"))
        record_ids = item.get("record_ids")
        if isinstance(record_ids, list):
            for record_id in record_ids:
                add(record_id)
        for key in ("records", "value", "values"):
            nested = item.get(key)
            if isinstance(nested, (dict, list)):
                visit(nested)

    visit(value)
    return result
