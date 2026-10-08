from __future__ import annotations

"""Pure policy for applying observed extension data to authoritative creator state."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtensionUpdateDecision:
    creator_values: dict[str, Any]
    account_values: dict[str, Any]
    updated_fields: tuple[str, ...]
    preserved_fields: tuple[str, ...]
    warnings: tuple[dict[str, str], ...]
    preserve_current_videos: bool = True
    preserve_current_insights: bool = True


@dataclass(frozen=True)
class ExtensionSnapshotDecision:
    metrics: dict[str, Any]
    videos: tuple[dict[str, Any], ...]
    followers_observed: bool
    video_count_observed: bool
    default_insight_level: str


def has_observed_value(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _text(value: object) -> str:
    return str(value if value is not None else "").strip()


def _record_persisted_delta(
    updated: set[str],
    qualified: str,
    before: object,
    effective_after: object,
) -> None:
    if _text(before) != _text(effective_after):
        updated.add(qualified)


def field_observed(analysis: dict[str, Any], field: str, value: object) -> bool:
    observations = (
        analysis.get("field_observations")
        if isinstance(analysis.get("field_observations"), dict)
        else {}
    )
    if field in observations:
        state = observations.get(field)
        return bool(isinstance(state, dict) and state.get("observed") is True)
    if not has_observed_value(value):
        return False
    # A legacy flat zero is ambiguous until the extension supplies field state.
    return value not in (0, "0", False)


def decide_extension_update(
    analysis: dict[str, Any],
    current_creator: dict[str, Any],
    candidate_creator: dict[str, Any],
    current_account: dict[str, Any],
    candidate_account: dict[str, Any],
) -> ExtensionUpdateDecision:
    creator_values = dict(candidate_creator)
    account_values = dict(candidate_account)
    updated: set[str] = set()
    preserved: set[str] = set()
    warnings: list[dict[str, str]] = []
    creator = analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}

    creator_fill_only = {
        "name": "creator_name",
        "email": "email",
        "followers": "followers",
        "bio": "bio",
        "country": "country",
        "language": "language",
        "content_category": "content_category",
        "whatsapp": "whatsapp",
        "platform": "platform",
        "profile_url": "profile_url",
    }
    for field, observation_field in creator_fill_only.items():
        qualified = f"creator.{field}"
        old_value = current_creator.get(field)
        new_value = candidate_creator.get(field)
        source_value = (
            analysis.get("content_category")
            if field == "content_category"
            else creator.get(observation_field)
        )
        observed = field_observed(analysis, observation_field, source_value)
        if has_observed_value(old_value):
            creator_values[field] = old_value
            if observed and has_observed_value(new_value) and str(old_value) != str(new_value):
                preserved.add(qualified)
                if field == "email" and _normalized_email(old_value) != _normalized_email(new_value):
                    warnings.append({"code": "EMAIL_CONFLICT_PRESERVED", "field": qualified})
        elif observed and has_observed_value(new_value):
            creator_values[field] = new_value
            updated.add(qualified)
        else:
            creator_values[field] = old_value if old_value is not None else ""

    manual_creator_fields = (
        "status", "cooperation_stage", "owner", "note", "tags", "archived_at",
        "last_contact_time", "next_follow_up_time", "quote", "recent_product",
        "agency_id", "current_contact_id", "source_contact_id", "created_at",
        "insight_level",
    )
    for field in manual_creator_fields:
        creator_values[field] = current_creator.get(field, "")
        supplied = creator.get(field)
        if field_observed(analysis, field, supplied) and has_observed_value(supplied):
            preserved.add(f"creator.{field}")

    _record_persisted_delta(
        updated,
        "creator.updated_at",
        current_creator.get("updated_at"),
        creator_values.get("updated_at"),
    )

    for field in ("creator_id", "account_uid", "account_id", "platform", "created_at"):
        account_values[field] = current_account.get(field, account_values.get(field, ""))
    for field in ("attribution_status", "note"):
        account_values[field] = current_account.get(field, "")

    account_mutable = {
        "profile_url": creator.get("profile_url"),
        "username": creator.get("username"),
        "followers": creator.get("followers"),
        "platform_account_id": creator.get("platform_account_id"),
        "latest_post_date": creator.get("latest_post_date"),
    }
    for field, incoming in account_mutable.items():
        qualified = f"creator_account.{field}"
        if field_observed(analysis, field, incoming):
            normalized = _text(incoming)
            if _text(current_account.get(field)) != normalized:
                account_values[field] = normalized
                updated.add(qualified)
            else:
                account_values[field] = current_account.get(field, "")
        else:
            account_values[field] = current_account.get(field, "")

    incoming_email = (
        creator.get("account_email")
        if creator.get("account_email") not in (None, "")
        else creator.get("email")
    )
    email_field = "account_email" if creator.get("account_email") not in (None, "") else "email"
    existing_email = _text(current_account.get("account_email"))
    captured_email = _text(incoming_email)
    if field_observed(analysis, email_field, incoming_email) and captured_email:
        if not existing_email:
            account_values["account_email"] = captured_email
            updated.add("creator_account.account_email")
        elif _normalized_email(existing_email) != _normalized_email(captured_email):
            account_values["account_email"] = existing_email
            preserved.add("creator_account.account_email")
            warnings.append({
                "code": "EMAIL_CONFLICT_PRESERVED",
                "field": "creator_account.account_email",
            })
        else:
            account_values["account_email"] = existing_email
    else:
        account_values["account_email"] = existing_email

    for field in ("last_scrape_time", "updated_at"):
        _record_persisted_delta(
            updated,
            f"creator_account.{field}",
            current_account.get(field),
            account_values.get(field),
        )
    if has_observed_value(analysis.get("source")):
        _record_persisted_delta(
            updated,
            "creator_account.data_source",
            current_account.get("data_source"),
            account_values.get("data_source"),
        )
    if has_observed_value(analysis.get("task_id")):
        _record_persisted_delta(
            updated,
            "creator_account.source_task_id",
            current_account.get("source_task_id"),
            account_values.get("source_task_id"),
        )
    if has_observed_value(analysis.get("scrape_status")):
        _record_persisted_delta(
            updated,
            "creator_account.scrape_status",
            current_account.get("scrape_status"),
            account_values.get("scrape_status"),
        )

    preserved.update(("creator.videos", "creator.insights"))
    return ExtensionUpdateDecision(
        creator_values=creator_values,
        account_values=account_values,
        updated_fields=tuple(sorted(updated)),
        preserved_fields=tuple(sorted(preserved)),
        warnings=tuple(warnings),
    )


def decide_extension_snapshot(
    analysis: dict[str, Any], extension_action: str | None
) -> ExtensionSnapshotDecision:
    creator = analysis.get("creator") if isinstance(analysis.get("creator"), dict) else {}
    metrics = analysis.get("video_analysis") if isinstance(analysis.get("video_analysis"), dict) else {}
    videos = tuple(
        item for item in (
            analysis.get("videos") if isinstance(analysis.get("videos"), list) else []
        ) if isinstance(item, dict)
    )
    if extension_action is None:
        return ExtensionSnapshotDecision(
            metrics=metrics,
            videos=videos,
            followers_observed=True,
            video_count_observed=True,
            default_insight_level="insufficient",
        )

    content_status = str(metrics.get("capture_status") or "").strip().lower()
    failed = content_status in {
        "failed", "cancelled", "canceled", "timed_out", "timeout", "unavailable"
    }
    observed_videos = () if failed else videos
    complete = content_status in {"success", "complete", "completed"}
    return ExtensionSnapshotDecision(
        metrics={} if failed else metrics,
        videos=observed_videos,
        followers_observed=field_observed(analysis, "followers", creator.get("followers")),
        video_count_observed=bool(observed_videos) or complete,
        default_insight_level="",
    )
def _normalized_email(value: object) -> str:
    return _text(value).casefold()
