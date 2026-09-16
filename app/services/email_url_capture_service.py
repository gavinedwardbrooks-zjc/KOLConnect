from __future__ import annotations

"""Safe Creator email capture from resolver-approved profile URLs."""

from datetime import datetime, timezone
import uuid
from typing import Any, Callable, Protocol

import scraper as scraper_module
from domain.creator_url_resolver import CreatorURLResolver


_BLOCKING_CAPTURE_STATUSES = frozenset({"failed", "login_required", "platform_error"})


class CreatorEmailCapturePort(Protocol):
    def get_creator_accounts(self) -> list[dict[str, Any]]: ...

    def import_url_email_capture(
        self,
        task_id: str,
        record: dict[str, Any],
        *,
        imported_at: str,
    ) -> dict[str, Any]: ...


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _new_capture_task_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"task_{timestamp}_{uuid.uuid4().hex[:8]}"


class EmailURLCaptureService:
    """Run M8.7 URL capture without creating a second URL parser or write model."""

    def __init__(
        self,
        creator_service: CreatorEmailCapturePort,
        *,
        profile_capture: Callable[[str, str], dict[str, Any]] = scraper_module.capture_profile_email,
        task_id_factory: Callable[[], str] = _new_capture_task_id,
        now_provider: Callable[[], str] = _utc_now,
    ) -> None:
        self._creator_service = creator_service
        self._profile_capture = profile_capture
        self._task_id_factory = task_id_factory
        self._now_provider = now_provider

    def capture(self, raw_url: object) -> dict[str, Any]:
        accounts = self._creator_service.get_creator_accounts()
        resolution = CreatorURLResolver(lambda: accounts).resolve(raw_url)
        resolution_status = str(resolution.get("resolution_status") or "invalid")
        match_status = str(resolution.get("account_match_status") or "")
        canonical_profile_url = str(resolution.get("canonical_profile_url") or "").strip()

        if resolution_status != "resolved" or not canonical_profile_url:
            return self._result("profile_identity_unresolved", resolution)
        if match_status == "ambiguous":
            return self._result("ambiguous_account", resolution)

        platform = str(resolution.get("platform") or "")
        try:
            captured = self._profile_capture(platform, canonical_profile_url)
        except Exception:
            # Fetch/capture failures are intentionally non-destructive and sanitized.
            return self._result("capture_failed", resolution)

        scrape_status = str(captured.get("scrape_status") or "").strip().lower()
        if scrape_status in _BLOCKING_CAPTURE_STATUSES:
            return self._result(scrape_status, resolution)

        emails = scraper_module.clean_email_candidates(captured.get("emails") or [])
        if not emails:
            return self._result("email_not_found", resolution)

        account_uid = str(resolution.get("account_uid") or "").strip()
        if not account_uid:
            account_uid = scraper_module.build_creator_uid(
                {"platform": platform, "url": canonical_profile_url}
            )
        existing_account = next(
            (
                account for account in accounts
                if str(account.get("account_uid") or "").strip() == account_uid
            ),
            {},
        )
        existing_email = str(existing_account.get("account_email") or "").strip()
        email_source = str(captured.get("email_source") or "").strip()
        if existing_email and existing_email != scraper_module.NO_EMAIL:
            if existing_email.casefold() == emails[0].casefold():
                return self._result(
                    "unchanged", resolution, account_uid=account_uid,
                    email=existing_email, email_source=email_source,
                )
            return self._result(
                "email_conflict", resolution, account_uid=account_uid,
                email=emails[0], email_source=email_source,
            )
        task_id = self._task_id_factory()
        imported_at = self._now_provider()
        record = {
            "account_uid": account_uid,
            "creator_name": str(captured.get("name") or "").strip(),
            "platform": platform,
            "profile_url": canonical_profile_url,
            "email": emails[0],
            "email_source": email_source,
            "latest_post_date": str(captured.get("latest_publish_date") or "").strip(),
            "last_scrape_time": str(captured.get("last_scrape_time") or imported_at),
            "data_source": "m8_7_profile_email_capture",
            "scrape_status": scrape_status or "success",
            # This marks a verified non-empty email as a recheck update while
            # preserving the repository's non-destructive empty-email behavior.
            "email_recheck": True,
            "content_category": "",
        }
        saved = self._creator_service.import_url_email_capture(
            task_id, record, imported_at=imported_at
        )
        created = bool(saved.get("created_creators") or saved.get("created_accounts"))
        return self._result(
            "created" if created else "updated",
            resolution,
            creator_id=str((saved.get("creator_ids") or [""])[0] or ""),
            account_uid=account_uid,
            email=emails[0],
            email_source=email_source,
        )

    @staticmethod
    def _result(status: str, resolution: dict[str, Any], **extra: Any) -> dict[str, Any]:
        return {
            "status": status,
            "reason_code": resolution.get("reason_code"),
            "resolution": resolution,
            **extra,
        }
