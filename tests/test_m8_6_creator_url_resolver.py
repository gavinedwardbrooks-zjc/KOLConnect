from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper  # noqa: E402
from domain.creator_url_resolver import CreatorURLResolver  # noqa: E402


class CreatorURLResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.resolver = CreatorURLResolver()

    def test_tiktok_profile_and_video_canonicalize_without_network(self) -> None:
        profile = self.resolver.resolve("https://m.tiktok.com/@Alice/?utm_source=test#fragment")
        video = self.resolver.resolve("https://www.tiktok.com/@Alice/video/123456?lang=en")

        self.assertEqual("TikTok", profile["platform"])
        self.assertEqual("profile", profile["input_type"])
        self.assertEqual("Alice", profile["username"])
        self.assertEqual("https://www.tiktok.com/@Alice", profile["canonical_profile_url"])
        self.assertEqual("content", video["input_type"])
        self.assertEqual("123456", video["video_id"])
        self.assertEqual("https://www.tiktok.com/@Alice", video["canonical_profile_url"])

    def test_tiktok_short_link_and_malformed_url_fail_safely(self) -> None:
        short = self.resolver.resolve("https://vm.tiktok.com/abc123/")
        malformed = self.resolver.resolve("https://www.tiktok.com/@alice%20bad")

        self.assertEqual("unsupported", short["resolution_status"])
        self.assertEqual("unsupported_url_form", short["reason_code"])
        self.assertEqual("unsupported", malformed["resolution_status"])
        self.assertEqual("unsupported_url_form", malformed["reason_code"])

    def test_instagram_profile_post_and_reel_preserve_partial_identity(self) -> None:
        profile = self.resolver.resolve("https://instagram.com/alice/?utm_campaign=x")
        post = self.resolver.resolve("https://www.instagram.com/p/POST_123/?utm_source=x")
        reel = self.resolver.resolve("https://www.instagram.com/reel/REEL_456/")

        self.assertEqual("https://www.instagram.com/alice/", profile["canonical_profile_url"])
        self.assertEqual("POST_123", post["video_id"])
        self.assertEqual("partial", post["resolution_status"])
        self.assertIsNone(post["username"])
        self.assertEqual("REEL_456", reel["video_id"])

    def test_instagram_unsupported_forms_and_unknown_hosts_are_explicit(self) -> None:
        unsupported = self.resolver.resolve("https://www.instagram.com/explore/")
        malformed = self.resolver.resolve("https://www.instagram.com/alice%20bad/")
        unknown = self.resolver.resolve("https://example.com/alice")

        self.assertEqual("unsupported_url_form", unsupported["reason_code"])
        self.assertEqual("unsupported_url_form", malformed["reason_code"])
        self.assertEqual("unsupported_platform", unknown["reason_code"])

    def test_youtube_profiles_videos_shorts_and_short_links(self) -> None:
        handle = self.resolver.resolve("https://youtube.com/@Alice/?feature=share")
        channel = self.resolver.resolve("https://www.youtube.com/channel/UC123/")
        video = self.resolver.resolve("https://www.youtube.com/watch?v=video_123&utm_source=x")
        short = self.resolver.resolve("https://youtu.be/video_123?t=1")
        shorts = self.resolver.resolve("https://www.youtube.com/shorts/short_456?feature=share")

        self.assertEqual("https://www.youtube.com/@Alice", handle["canonical_profile_url"])
        self.assertEqual("UC123", channel["platform_account_id"])
        self.assertEqual("video_123", video["video_id"])
        self.assertEqual("https://www.youtube.com/watch?v=video_123", short["canonical_url"])
        self.assertEqual("short_456", shorts["video_id"])
        self.assertEqual("partial", shorts["resolution_status"])

    def test_youtube_unsupported_and_blank_inputs_are_explicit(self) -> None:
        unsupported = self.resolver.resolve("https://www.youtube.com/feed/subscriptions")
        malformed = self.resolver.resolve("https://www.youtube.com/watch?v=video%20bad")
        blank = self.resolver.resolve(" ")

        self.assertEqual("unsupported_url_form", unsupported["reason_code"])
        self.assertEqual("unsupported_url_form", malformed["reason_code"])
        self.assertEqual("blank_input", blank["reason_code"])

    def test_equivalent_variants_are_idempotent(self) -> None:
        first = self.resolver.resolve("https://www.tiktok.com/@alice/?lang=en")
        second = self.resolver.resolve(first["canonical_url"])

        self.assertEqual(first["canonical_url"], second["canonical_url"])
        self.assertEqual(first["canonical_profile_url"], second["canonical_profile_url"])

    def test_existing_account_matching_uses_strong_identity_then_username(self) -> None:
        accounts = [
            {
                "account_uid": "tiktok|alice",
                "platform": "TikTok",
                "username": "alice",
                "profile_url": "https://www.tiktok.com/@alice",
            },
            {
                "account_uid": "youtube|alice",
                "platform": "YouTube",
                "username": "alice",
                "profile_url": "https://www.youtube.com/@alice",
            },
        ]

        resolved = self.resolver.resolve("https://www.tiktok.com/@alice/video/123", account_rows=accounts)
        self.assertEqual("tiktok|alice", resolved["account_uid"])
        self.assertEqual("canonical_profile_url", resolved["account_match_priority"])

    def test_ambiguous_and_unknown_accounts_fail_closed_without_mutation(self) -> None:
        accounts = [
            {"account_uid": "one", "platform": "Instagram", "username": "alice"},
            {"account_uid": "two", "platform": "Instagram", "username": "alice"},
        ]
        snapshot = [dict(row) for row in accounts]

        ambiguous = self.resolver.resolve("https://www.instagram.com/alice/", account_rows=accounts)
        unknown = self.resolver.resolve("https://www.instagram.com/bob/", account_rows=accounts)

        self.assertEqual("ambiguous", ambiguous["account_match_status"])
        self.assertIsNone(ambiguous["account_uid"])
        self.assertEqual("no_match", unknown["account_match_status"])
        self.assertEqual(snapshot, accounts)

    def test_content_with_no_profile_identity_never_guesses_an_account(self) -> None:
        result = self.resolver.resolve(
            "https://www.youtube.com/watch?v=video_123",
            account_rows=[{"account_uid": "youtube|alice", "platform": "YouTube", "username": "alice"}],
        )

        self.assertEqual("partial", result["resolution_status"])
        self.assertEqual("not_applicable", result["account_match_status"])
        self.assertIsNone(result["account_uid"])

    def test_repository_provider_is_read_only_and_uses_existing_account_rows(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls = 0

            def getCreatorAccounts(self):
                self.calls += 1
                return [
                    {
                        "account_uid": "youtube|channel",
                        "platform": "YouTube",
                        "platform_account_id": "UC123",
                        "profile_url": "https://www.youtube.com/channel/UC123",
                    }
                ]

        repository = Repository()
        result = CreatorURLResolver.from_repository(repository).resolve(
            "https://www.youtube.com/channel/UC123/"
        )

        self.assertEqual(1, repository.calls)
        self.assertEqual("youtube|channel", result["account_uid"])
        self.assertEqual("platform_account_id", result["account_match_priority"])

    def test_legacy_profile_normalizer_is_a_compatibility_adapter(self) -> None:
        video = scraper.normalize_link_record("https://www.tiktok.com/@alice/video/1001?lang=en")
        reel = scraper.normalize_link_record("https://www.instagram.com/reel/REEL_456/")

        self.assertTrue(video["valid"])
        self.assertEqual("https://www.tiktok.com/@alice", video["normalized_url"])
        self.assertFalse(reel["valid"])


if __name__ == "__main__":
    unittest.main()
