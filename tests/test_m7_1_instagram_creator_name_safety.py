from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

import scraper


class InstagramCreatorNameSafetyTests(unittest.TestCase):
    target_url = "https://www.instagram.com/target.creator/"

    @staticmethod
    def _page(*objects: dict) -> str:
        return "".join(
            f'<script type="application/json">{json.dumps(item)}</script>'
            for item in objects
        )

    def test_target_object_wins_when_logged_in_viewer_appears_first(self) -> None:
        page = self._page(
            {"user": {"username": "logged.in.viewer", "full_name": "Gavin Viewer"}},
            {"profile": {"username": "target.creator", "full_name": "Target Creator"}},
        )
        self.assertEqual(
            "Target Creator",
            scraper.extract_creator_name("Instagram", page, self.target_url),
        )

    def test_unrelated_viewer_name_is_never_used_for_target(self) -> None:
        page = self._page({"username": "viewer", "full_name": "Gavin"})
        self.assertEqual("", scraper.extract_creator_name("Instagram", page, self.target_url))

    def test_matching_username_selects_correct_name_among_multiple_objects(self) -> None:
        page = self._page({
            "users": [
                {"username": "first", "full_name": "First Person"},
                {"username": "target.creator", "full_name": "Correct Person"},
                {"username": "last", "full_name": "Last Person"},
            ]
        })
        self.assertEqual(
            "Correct Person",
            scraper.extract_creator_name("Instagram", page, self.target_url),
        )

    def test_target_scoped_wrapped_hydration_payload_is_supported(self) -> None:
        payload = json.dumps({
            "viewer": {"username": "viewer", "full_name": "Gavin Edward Brooks"},
            "graphql": {"user": {"username": "target.creator", "full_name": "Wrapped Target"}},
        })
        page = f"<script>window.__profileData = {payload};</script>"
        self.assertEqual(
            "Wrapped Target",
            scraper.extract_creator_name("Instagram", page, self.target_url),
        )

    def test_error_pages_do_not_become_creator_names(self) -> None:
        for title in ("Access Denied", "404 Not Found", "This page isn't available"):
            with self.subTest(title=title):
                page = f"<html><title>{title}</title></html>"
                self.assertEqual(
                    "", scraper.extract_creator_name("Instagram", page, self.target_url)
                )

    def test_target_bound_meta_is_allowed_but_generic_meta_is_not(self) -> None:
        target_page = '<meta property="og:title" content="Target Creator (@target.creator) • Instagram photos">'
        generic_page = '<meta property="og:title" content="Logged In Viewer (@viewer) • Instagram photos">'
        self.assertEqual(
            "Target Creator",
            scraper.extract_creator_name("Instagram", target_page, self.target_url),
        )
        self.assertEqual(
            "", scraper.extract_creator_name("Instagram", generic_page, self.target_url)
        )

    def test_valid_profile_identity_does_not_depend_on_name(self) -> None:
        self.assertEqual("", scraper.extract_creator_name("Instagram", "<html></html>", self.target_url))
        uid = scraper.build_creator_uid({"url": self.target_url, "platform": "Instagram", "name": ""})
        self.assertTrue(uid)
        self.assertIn("instagram|", uid)

    def test_tiktok_and_youtube_name_extraction_remains_supported(self) -> None:
        self.assertEqual(
            "TikTok Creator",
            scraper.extract_creator_name("TikTok", '{"nickname":"TikTok Creator"}'),
        )
        self.assertEqual(
            "YouTube Creator",
            scraper.extract_creator_name("YouTube", '{"channelName":"YouTube Creator"}'),
        )


if __name__ == "__main__":
    unittest.main()
