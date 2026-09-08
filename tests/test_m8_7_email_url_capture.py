from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper  # noqa: E402
import creator_repository  # noqa: E402
from http_handlers import creator_handler  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from services.email_url_capture_service import EmailURLCaptureService  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class FakeCreatorService:
    def __init__(self, accounts: list[dict] | None = None) -> None:
        self.accounts = list(accounts or [])
        self.saved: list[dict] = []

    def get_creator_accounts(self) -> list[dict]:
        return [dict(account) for account in self.accounts]

    def import_url_email_capture(self, task_id: str, record: dict, *, imported_at: str) -> dict:
        is_new_creator = not any(
            str(account.get("account_uid") or "") == str(record.get("account_uid") or "")
            for account in self.accounts
        )
        self.saved.append({"task_id": task_id, "record": record, "imported_at": imported_at})
        if is_new_creator:
            self.accounts.append({
                "account_uid": record["account_uid"],
                "platform": record["platform"],
                "profile_url": record["profile_url"],
                "username": "",
                "account_email": record["email"],
            })
        return {
            "created_creators": int(is_new_creator),
            "created_accounts": int(is_new_creator),
            "updated_accounts": int(not is_new_creator),
            "creator_ids": ["creator-new" if is_new_creator else "creator-existing"],
            "account_ids": ["account-1"],
        }


def capture_result(*, email: str = "creator@example.test", name: str = "Creator", status: str = "success") -> dict:
    return {
        "name": name,
        "emails": [email] if email else [],
        "scrape_status": status,
        "latest_publish_date": "",
        "last_scrape_time": "2026-08-31T00:00:00Z",
    }


class EmailURLCaptureServiceTests(unittest.TestCase):
    def make_service(self, accounts=None, result=None):
        self.calls: list[tuple[str, str]] = []
        creator_service = FakeCreatorService(accounts)

        def profile_capture(platform: str, profile_url: str) -> dict:
            self.calls.append((platform, profile_url))
            if isinstance(result, Exception):
                raise result
            return result or capture_result()

        return creator_service, EmailURLCaptureService(
            creator_service,
            profile_capture=profile_capture,
            task_id_factory=lambda: "task_20260831T000000Z_deadbeef",
            now_provider=lambda: "2026-08-31T00:00:00Z",
        )

    def test_supported_tiktok_instagram_and_youtube_profiles_capture_email(self):
        for raw_url, platform, profile in (
            ("https://m.tiktok.com/@alice/?source=share", "TikTok", "https://www.tiktok.com/@alice"),
            ("https://instagram.com/alice/?utm=source", "Instagram", "https://www.instagram.com/alice/"),
            ("https://youtube.com/@alice/?feature=share", "YouTube", "https://www.youtube.com/@alice"),
        ):
            with self.subTest(raw_url=raw_url):
                creator_service, service = self.make_service()
                response = service.capture(raw_url)

                self.assertEqual("created", response["status"])
                self.assertEqual([(platform, profile)], self.calls)
                self.assertEqual(1, len(creator_service.saved))
                self.assertEqual(profile, creator_service.saved[0]["record"]["profile_url"])

    def test_existing_account_and_url_variants_reuse_same_account_uid(self):
        account = {
            "account_uid": "tiktok-alice",
            "platform": "TikTok",
            "username": "alice",
            "profile_url": "https://www.tiktok.com/@alice",
            "account_email": "old@example.test",
        }
        creator_service, service = self.make_service([account])

        first = service.capture("https://www.tiktok.com/@alice/?lang=en")
        second = service.capture("https://m.tiktok.com/@alice/")

        self.assertEqual("updated", first["status"])
        self.assertEqual("updated", second["status"])
        self.assertEqual("tiktok-alice", creator_service.saved[0]["record"]["account_uid"])
        self.assertEqual("tiktok-alice", creator_service.saved[1]["record"]["account_uid"])
        self.assertEqual(2, len(creator_service.saved))

    def test_new_profile_repeated_capture_creates_one_account_then_updates_it(self):
        creator_service, service = self.make_service()

        first = service.capture("https://www.instagram.com/new_creator/")
        second = service.capture("https://instagram.com/new_creator/?utm_source=share")

        self.assertEqual("created", first["status"])
        self.assertEqual("updated", second["status"])
        self.assertEqual(1, len(creator_service.accounts))
        self.assertEqual(
            creator_service.saved[0]["record"]["account_uid"], creator_service.saved[1]["record"]["account_uid"]
        )

    def test_video_with_deterministic_profile_uses_same_account_and_partial_video_fails_closed(self):
        account = {
            "account_uid": "tiktok-alice",
            "platform": "TikTok",
            "username": "alice",
            "profile_url": "https://www.tiktok.com/@alice",
        }
        creator_service, service = self.make_service([account])

        resolved = service.capture("https://www.tiktok.com/@alice/video/123456")
        partial = service.capture("https://www.youtube.com/watch?v=video_123")

        self.assertEqual("updated", resolved["status"])
        self.assertEqual("tiktok-alice", creator_service.saved[0]["record"]["account_uid"])
        self.assertEqual("profile_identity_unresolved", partial["status"])
        self.assertEqual("profile_identity_unresolved", partial["reason_code"])
        self.assertEqual(1, len(creator_service.saved))
        self.assertEqual(1, len(self.calls))

    def test_malformed_unsupported_and_ambiguous_urls_do_not_capture_or_mutate(self):
        accounts = [
            {"account_uid": "one", "platform": "Instagram", "username": "alice"},
            {"account_uid": "two", "platform": "Instagram", "username": "alice"},
        ]
        creator_service, service = self.make_service(accounts)

        for raw_url in ("not-a-url", "https://example.test/alice", "https://www.instagram.com/alice/"):
            with self.subTest(raw_url=raw_url):
                response = service.capture(raw_url)
                self.assertIn(response["status"], {"profile_identity_unresolved", "ambiguous_account"})

        self.assertEqual([], self.calls)
        self.assertEqual([], creator_service.saved)

    def test_missing_email_fetch_failure_and_login_required_are_non_destructive(self):
        existing = [{
            "account_uid": "instagram-alice",
            "platform": "Instagram",
            "username": "alice",
            "profile_url": "https://www.instagram.com/alice/",
            "account_email": "valid@example.test",
        }]
        for result, expected in (
            (capture_result(email=""), "email_not_found"),
            (RuntimeError("network failure"), "capture_failed"),
            (capture_result(email="", status="login_required"), "login_required"),
        ):
            with self.subTest(expected=expected):
                creator_service, service = self.make_service(existing, result)
                response = service.capture("https://www.instagram.com/alice/")
                self.assertEqual(expected, response["status"])
                self.assertEqual([], creator_service.saved)

    def test_multi_account_creator_and_cross_platform_same_username_remain_isolated(self):
        accounts = [
            {"account_uid": "creator-a-tiktok", "platform": "TikTok", "username": "alice"},
            {"account_uid": "creator-a-youtube", "platform": "YouTube", "username": "alice"},
        ]
        creator_service, service = self.make_service(accounts)

        tiktok = service.capture("https://www.tiktok.com/@alice")
        youtube = service.capture("https://www.youtube.com/@alice")

        self.assertEqual("creator-a-tiktok", tiktok["account_uid"])
        self.assertEqual("creator-a-youtube", youtube["account_uid"])
        self.assertEqual(["creator-a-tiktok", "creator-a-youtube"], [
            analysis["record"]["account_uid"] for analysis in creator_service.saved
        ])


class EmailURLCaptureBoundaryTests(unittest.TestCase):
    def test_m8_7_profile_capture_never_uses_external_site_fallback(self):
        page = "<html><body><a href='https://external.example/contact'>contact</a></body></html>"
        with (
            patch.object(scraper, "load_page_source_with_context", return_value=(page, "requests")),
            patch.object(scraper, "scrape_external_link_emails") as external,
        ):
            result = scraper.capture_profile_email("Instagram", "https://www.instagram.com/alice/")

        self.assertEqual([], result["emails"])
        external.assert_not_called()
        self.assertEqual("", result["external_link"])

    def test_legacy_profile_capture_keeps_its_external_fallback_default(self):
        page = "<html><body>no email</body></html>"
        with (
            patch.object(scraper, "load_page_source_with_context", return_value=(page, "requests")),
            patch.object(scraper, "scrape_external_link_emails", return_value={
                "email": "legacy@example.test", "link": "https://external.example", "source": "https://external.example", "status": "found",
            }) as external,
        ):
            result = scraper.scrape_tiktok("https://www.tiktok.com/@alice", session=object())

        external.assert_called_once()
        self.assertEqual(["legacy@example.test"], result["emails"])

    def test_creator_library_api_exposes_controlled_capture_result(self):
        class CaptureService:
            def capture(self, raw_url):
                self.url = raw_url
                return {"status": "profile_identity_unresolved", "reason_code": "profile_identity_unresolved"}

        class Handler:
            def __init__(self):
                self.response = None

            def _json(self, payload, status=200):
                self.response = (payload, status)

        capture = CaptureService()
        handler = Handler()
        context = {
            "services": {
                "creator": object(),
                "agency": object(),
                "creator_delete_impact": object(),
                "creator_hard_delete": object(),
                "email_url_capture": capture,
            },
            "config": {"legacy_cooperation_pattern": __import__("re").compile("$^")},
        }
        request = {
            "method": "POST",
            "path": "/api/creator-library/email-capture",
            "query": {},
            "get_payload": lambda: {"url": "https://www.youtube.com/watch?v=video_123"},
        }

        self.assertTrue(creator_handler.handle(handler, request, context))
        self.assertEqual("https://www.youtube.com/watch?v=video_123", capture.url)
        self.assertEqual(
            ({"ok": True, "status": "profile_identity_unresolved", "reason_code": "profile_identity_unresolved"}, 200),
            handler.response,
        )


class EmailURLCapturePersistenceTests(unittest.TestCase):
    def test_existing_account_email_update_preserves_creator_videos_and_primary_identity(self):
        profile_url = "https://www.tiktok.com/@alice"
        account_uid = scraper.build_creator_uid({"platform": "TikTok", "url": profile_url})
        original_analysis = {
            "schema_version": "1.0",
            "analysis_id": "analysis_task_20260830T000000Z_aaaaaaaa",
            "task_id": "task_20260830T000000Z_aaaaaaaa",
            "account_uid": account_uid,
            "imported_at": "2026-08-30T00:00:00Z",
            "source": "chrome_extension",
            "creator": {
                "creator_name": "Alice",
                "platform": "TikTok",
                "profile_url": profile_url,
                "email": "old@example.test",
            },
            "video_analysis": {},
            "videos": [{"video_url": "https://www.tiktok.com/@alice/video/123", "views": 100}],
            "creator_insight": {"level": "insufficient", "risks": [], "recommendation": ""},
        }
        with test_runtime_sandbox("m8_7_email_capture") as runtime, patch.object(creator_repository, "log_event"):
            repository = creator_repository.CreatorRepository(runtime.workbook_path)
            saved = repository.saveCreator(original_analysis)
            creator_service = CreatorService(lambda: repository, lambda: None)
            capture_service = EmailURLCaptureService(
                creator_service,
                profile_capture=lambda _platform, _url: capture_result(email="new@example.test"),
                task_id_factory=lambda: "task_20260831T000000Z_deadbeef",
                now_provider=lambda: "2026-08-31T00:00:00Z",
            )

            response = capture_service.capture("https://m.tiktok.com/@alice/?lang=en")
            detail = repository.getCreatorDetail(saved["creator_id"])

        self.assertEqual("updated", response["status"])
        self.assertEqual(1, len(detail["accounts"]))
        self.assertEqual("new@example.test", detail["accounts"][0]["account_email"])
        self.assertEqual("TikTok", detail["record"]["platform"])
        self.assertEqual(profile_url, detail["record"]["profile_url"])
        self.assertEqual(1, len(detail["analysis"]["videos"]))


if __name__ == "__main__":
    unittest.main()
