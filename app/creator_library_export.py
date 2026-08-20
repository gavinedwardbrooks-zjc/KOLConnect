from __future__ import annotations

"""Creator Library export workbook serialization with a deliberately small field set."""

import io
from typing import Any

from openpyxl import Workbook


CREATOR_EXPORT_HEADERS = (
    "platform",
    "profile_url",
    "name",
    "country",
    "language",
    "content_category",
    "agency_id",
    "followers",
    "insight_level",
    "status",
    "created_at",
)


def build_creator_export_workbook(records: list[dict[str, Any]]) -> bytes:
    """Serialize only the approved Creator Library fields, in their frozen order."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Creators"
    sheet.append(list(CREATOR_EXPORT_HEADERS))
    for record in records:
        sheet.append([
            str(record.get("platform") or ""),
            str(record.get("profile_url") or ""),
            str(record.get("creator_name") or ""),
            str(record.get("country") or ""),
            str(record.get("language") or ""),
            str(record.get("content_category") or ""),
            str(record.get("agency_id") or ""),
            str(record.get("followers") or ""),
            str(record.get("insight_level") or ""),
            str(record.get("status") or ""),
            str(record.get("created_at") or ""),
        ])
    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
