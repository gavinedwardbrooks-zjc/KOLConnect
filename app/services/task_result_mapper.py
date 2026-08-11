from __future__ import annotations

"""Convert raw task result rows into neutral Creator import DTOs."""

from typing import Mapping

import creator_data_compat as scraper_module
from ports.creator_port import CreatorImportItem


def task_data_source(task: Mapping[str, object]) -> str:
    task_type = str(task.get("task_type") or "scrape")
    if task_type == "email_recheck":
        return "系统抓取"
    if task_type == "manual":
        return "人工+系统补充" if task.get("has_system_supplement") else "人工录入"
    return "系统抓取"


def map_task_rows_for_creator_library(
    task: Mapping[str, object], rows: tuple[Mapping[str, object], ...]
) -> tuple[CreatorImportItem, ...]:
    source_contact_id = str(task.get("local_source_contact_id") or "").strip()
    extension_crm = (
        task.get("extension_crm")
        if isinstance(task.get("extension_crm"), dict)
        else {}
    )
    task_type = str(task.get("task_type") or "scrape").strip()
    items: list[CreatorImportItem] = []
    for raw_row in rows:
        result = scraper_module.row_to_result(dict(raw_row))
        profile_url = str(result.get("url") or "").strip()
        normalized = scraper_module.normalize_link_record(profile_url)
        platform = str(
            result.get("platform") or normalized.get("platform") or ""
        ).strip()
        email = str(result.get("email_display") or "").strip()
        if email == scraper_module.NO_EMAIL:
            email = ""
        items.append(
            CreatorImportItem(
                account_uid=scraper_module.build_creator_uid(result),
                platform=platform,
                profile_url=str(normalized.get("normalized_url") or profile_url),
                creator_name=str(result.get("name") or "").strip(),
                followers=str(result.get("follower_count") or "").strip(),
                email=email,
                whatsapp=str(result.get("whatsapp") or "").strip(),
                country=str(
                    result.get("country") or extension_crm.get("country") or ""
                ).strip(),
                language=str(
                    result.get("language") or extension_crm.get("language") or ""
                ).strip(),
                content_category=str(
                    result.get("content_category")
                    or extension_crm.get("content_category")
                    or ""
                ).strip(),
                note=str(result.get("note") or ""),
                latest_post_date=str(
                    result.get("latest_publish_date") or ""
                ).strip(),
                last_scrape_time=str(result.get("last_scrape_time") or "").strip(),
                data_source=task_data_source(task),
                scrape_status=str(result.get("scrape_status") or "").strip(),
                source_contact_id=source_contact_id,
                email_recheck=task_type == "email_recheck",
            )
        )
    return tuple(items)
