from __future__ import annotations

"""Normalization helpers for actual campaign publications."""

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit


def normalize_publication_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("实际发布链接不能为空。")
    parsed = urlsplit(text)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        raise ValueError("实际发布链接必须是有效的 HTTP/HTTPS URL。")
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def publication_platform(url: object) -> str:
    host = urlsplit(str(url or "")).netloc.lower()
    if "tiktok.com" in host:
        return "TikTok"
    if "instagram.com" in host:
        return "Instagram"
    if "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    return ""


def normalize_utc_timestamp(value: object, label: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if "T" not in text:
        raise ValueError(f"{label}必须是包含时间的 ISO 8601 时间戳。")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label}必须是有效的 ISO 8601 时间戳。") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def platforms_compatible(account_platform: object, url_platform: object) -> bool:
    left = str(account_platform or "").strip().lower()
    right = str(url_platform or "").strip().lower()
    return not left or not right or left == right
