from __future__ import annotations

"""Deterministic URL identity resolution for supported creator platforms.

This module deliberately parses URLs only.  It never fetches a page or creates
local records, so callers can reuse it before deciding what workflow to run.
"""

from collections.abc import Callable, Iterable, Mapping
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit


_PLATFORM_LABELS = {
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "youtube": "YouTube",
}
_IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")
_VIDEO_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


def _empty_result(raw_url: object) -> dict[str, object]:
    return {
        "input": str(raw_url or "").strip(),
        "resolution_status": "invalid",
        "reason_code": "malformed_url",
        "platform": None,
        "input_type": None,
        "video_id": None,
        "username": None,
        "canonical_profile_url": None,
        "canonical_url": None,
        "platform_account_id": None,
        "account_uid": None,
        "account_match_status": "not_requested",
        "account_match_priority": None,
    }


class CreatorURLResolver:
    """Resolve deterministic creator/content URL identity without network I/O.

    ``account_rows_provider`` may return existing CreatorAccount read rows.  It
    is intentionally optional so syntactic URL parsing remains independent of
    storage and can be used by imports and task preparation.
    """

    def __init__(
        self,
        account_rows_provider: Callable[[], Iterable[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._account_rows_provider = account_rows_provider

    @classmethod
    def from_repository(cls, repository: object) -> "CreatorURLResolver":
        """Create a read-only resolver backed by the repository account view."""
        getter = getattr(repository, "getCreatorAccounts", None)
        if not callable(getter):
            raise TypeError("repository must provide getCreatorAccounts()")
        return cls(lambda: getter())

    def resolve(
        self,
        raw_url: object,
        *,
        account_rows: Iterable[Mapping[str, Any]] | None = None,
    ) -> dict[str, object]:
        result = self.resolve_syntax(raw_url)
        rows = account_rows
        if rows is None and self._account_rows_provider is not None:
            rows = self._account_rows_provider()
        if rows is not None:
            self._attach_account_match(result, rows)
        return result

    @classmethod
    def resolve_syntax(cls, raw_url: object) -> dict[str, object]:
        text = str(raw_url or "").strip()
        result = _empty_result(text)
        if not text:
            result["reason_code"] = "blank_input"
            return result

        parsed = urlsplit(text)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
            return result

        host = parsed.hostname.lower().rstrip(".")
        path = [part for part in parsed.path.split("/") if part]
        if host in {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}:
            return cls._parse_tiktok(text, host, path)
        if host in {"instagram.com", "www.instagram.com", "m.instagram.com"}:
            return cls._parse_instagram(text, path)
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}:
            return cls._parse_youtube(text, host, path, parse_qs(parsed.query))

        result["resolution_status"] = "unsupported"
        result["reason_code"] = "unsupported_platform"
        return result

    @classmethod
    def _base(cls, raw_url: str, platform_key: str) -> dict[str, object]:
        result = _empty_result(raw_url)
        result.update(
            {
                "resolution_status": "unsupported",
                "reason_code": "unsupported_url_form",
                "platform": _PLATFORM_LABELS[platform_key],
            }
        )
        return result

    @classmethod
    def _profile_result(
        cls,
        raw_url: str,
        platform_key: str,
        username: str,
        canonical_profile_url: str,
        *,
        platform_account_id: str | None = None,
    ) -> dict[str, object]:
        result = cls._base(raw_url, platform_key)
        result.update(
            {
                "resolution_status": "resolved",
                "reason_code": None,
                "input_type": "profile",
                "username": username or None,
                "canonical_profile_url": canonical_profile_url,
                "canonical_url": canonical_profile_url,
                "platform_account_id": platform_account_id,
            }
        )
        return result

    @classmethod
    def _content_result(
        cls,
        raw_url: str,
        platform_key: str,
        video_id: str,
        canonical_url: str,
        *,
        username: str | None = None,
        canonical_profile_url: str | None = None,
    ) -> dict[str, object]:
        result = cls._base(raw_url, platform_key)
        result.update(
            {
                "resolution_status": "resolved" if canonical_profile_url else "partial",
                "reason_code": None if canonical_profile_url else "profile_identity_unresolved",
                "input_type": "content",
                "video_id": video_id,
                "username": username,
                "canonical_profile_url": canonical_profile_url,
                "canonical_url": canonical_url,
            }
        )
        return result

    @classmethod
    def _parse_tiktok(cls, raw_url: str, host: str, parts: list[str]) -> dict[str, object]:
        result = cls._base(raw_url, "tiktok")
        if host in {"vm.tiktok.com", "vt.tiktok.com"}:
            return result
        if not parts:
            return result
        handle = (
            parts[0]
            if parts[0].startswith("@") and len(parts[0]) > 1 and _IDENTIFIER.fullmatch(parts[0][1:])
            else ""
        )
        username = handle[1:]
        if handle and len(parts) == 1:
            return cls._profile_result(raw_url, "tiktok", username, f"https://www.tiktok.com/{handle}")
        if len(parts) >= 3 and handle and parts[1].lower() == "video" and parts[2].isdigit():
            return cls._content_result(
                raw_url,
                "tiktok",
                parts[2],
                f"https://www.tiktok.com/{handle}/video/{parts[2]}",
                username=username,
                canonical_profile_url=f"https://www.tiktok.com/{handle}",
            )
        if len(parts) >= 2 and parts[0].lower() == "video" and parts[1].isdigit():
            return cls._content_result(raw_url, "tiktok", parts[1], f"https://www.tiktok.com/video/{parts[1]}")
        return result

    @classmethod
    def _parse_instagram(cls, raw_url: str, parts: list[str]) -> dict[str, object]:
        result = cls._base(raw_url, "instagram")
        if not parts:
            return result
        first = parts[0]
        reserved = {"reel", "reels", "p", "stories", "tv", "explore", "accounts", "directory"}
        if (
            first.lower() in {"p", "reel", "reels", "tv"}
            and len(parts) >= 2
            and _VIDEO_IDENTIFIER.fullmatch(parts[1])
        ):
            return cls._content_result(
                raw_url,
                "instagram",
                parts[1],
                f"https://www.instagram.com/{first.lower()}/{parts[1]}/",
            )
        if first.lower() in reserved or first.startswith("_") or not _IDENTIFIER.fullmatch(first):
            return result
        return cls._profile_result(raw_url, "instagram", first, f"https://www.instagram.com/{first}/")

    @classmethod
    def _parse_youtube(
        cls,
        raw_url: str,
        host: str,
        parts: list[str],
        query: Mapping[str, list[str]],
    ) -> dict[str, object]:
        result = cls._base(raw_url, "youtube")
        if host == "youtu.be":
            if len(parts) == 1 and _VIDEO_IDENTIFIER.fullmatch(parts[0]):
                return cls._content_result(
                    raw_url, "youtube", parts[0], f"https://www.youtube.com/watch?v={parts[0]}"
                )
            return result
        if not parts:
            return result
        first = parts[0]
        if first == "watch":
            video_id = (query.get("v") or [""])[0]
            if _VIDEO_IDENTIFIER.fullmatch(video_id):
                return cls._content_result(
                    raw_url, "youtube", video_id, f"https://www.youtube.com/watch?v={video_id}"
                )
            return result
        if first.lower() == "shorts" and len(parts) >= 2 and _VIDEO_IDENTIFIER.fullmatch(parts[1]):
            return cls._content_result(
                raw_url, "youtube", parts[1], f"https://www.youtube.com/shorts/{parts[1]}"
            )
        if (
            first.startswith("@")
            and len(first) > 1
            and _IDENTIFIER.fullmatch(first[1:])
            and (len(parts) == 1 or parts[1].lower() == "shorts")
        ):
            return cls._profile_result(raw_url, "youtube", first[1:], f"https://www.youtube.com/{first}")
        if first.lower() in {"channel", "c", "user"} and len(parts) >= 2 and _IDENTIFIER.fullmatch(parts[1]):
            canonical = f"https://www.youtube.com/{first.lower()}/{parts[1]}"
            return cls._profile_result(
                raw_url,
                "youtube",
                parts[1],
                canonical,
                platform_account_id=parts[1] if first.lower() == "channel" else None,
            )
        return result

    @classmethod
    def _attach_account_match(
        cls,
        result: dict[str, object],
        account_rows: Iterable[Mapping[str, Any]],
    ) -> None:
        platform = str(result.get("platform") or "").casefold()
        if not platform or not result.get("canonical_profile_url") and not result.get("username") and not result.get("platform_account_id"):
            result["account_match_status"] = "not_applicable"
            return
        candidates = [
            dict(row) for row in account_rows
            if str(row.get("account_uid") or "").strip()
            and str(row.get("platform") or "").casefold() == platform
        ]
        native_id = str(result.get("platform_account_id") or "").casefold()
        profile_url = str(result.get("canonical_profile_url") or "")
        username = str(result.get("username") or "").casefold()
        for priority, matcher in (
            ("platform_account_id", lambda row: native_id and str(row.get("platform_account_id") or "").casefold() == native_id),
            ("canonical_profile_url", lambda row: profile_url and cls.resolve_syntax(row.get("profile_url")).get("canonical_profile_url") == profile_url),
            ("username", lambda row: username and str(row.get("username") or "").casefold() == username),
        ):
            matched = [row for row in candidates if matcher(row)]
            if len(matched) == 1:
                result["account_uid"] = str(matched[0]["account_uid"])
                result["account_match_status"] = "matched"
                result["account_match_priority"] = priority
                return
            if len(matched) > 1:
                result["account_match_status"] = "ambiguous"
                result["account_match_priority"] = priority
                return
        result["account_match_status"] = "no_match"


def normalize_creator_url(raw_url: object) -> dict[str, object]:
    """Convenience entry point for callers that only need syntactic resolution."""
    return CreatorURLResolver().resolve(raw_url)
