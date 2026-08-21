from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper  # noqa: E402
from http_handlers import task_handler  # noqa: E402


class _ResponseHandler:
    def __init__(self) -> None:
        self.payload = None

    def _ok(self, **payload) -> None:
        self.payload = payload


class M48LinkCleanerTests(unittest.TestCase):
    def test_api_preserves_source_line_numbers_and_legacy_contract(self) -> None:
        handler = _ResponseHandler()
        handled = task_handler.handle(
            handler,
            {
                "method": "POST",
                "path": "/api/normalize-links",
                "get_payload": lambda: {
                    "text": "\nhttps://www.tiktok.com/@alice?lang=en\n\nhttps://www.tiktok.com/@alice\n",
                },
            },
            {"services": {"task": object()}, "modules": {"scraper": scraper}},
        )

        self.assertTrue(handled)
        self.assertEqual([2, 4], [item["line_number"] for item in handler.payload["link_results"]])
        self.assertIn("normalized_links", handler.payload)
        self.assertIn("invalid_links", handler.payload)

    def test_every_non_empty_input_has_an_explainable_outcome(self) -> None:
        payload = scraper.build_normalize_payload(
            [
                "https://www.tiktok.com/@alice?lang=en",
                "https://www.tiktok.com/@alice",
                "not-a-url",
            ],
            [2, 4, 7],
        )

        self.assertEqual([2, 4, 7], [item["line_number"] for item in payload["link_results"]])
        self.assertEqual(
            ["normalized", "duplicate", "invalid"],
            [item["status"] for item in payload["link_results"]],
        )
        duplicate = payload["link_results"][1]
        self.assertEqual("标准化后重复", duplicate["reason"])
        self.assertEqual(2, duplicate["duplicate_of_line"])
        self.assertEqual(
            {
                "line_number",
                "original",
                "normalized",
                "platform",
                "status",
                "reason",
                "duplicate_of_line",
            },
            set(duplicate),
        )

    def test_summary_invariant_and_legacy_fields_are_preserved(self) -> None:
        payload = scraper.build_normalize_payload(
            [
                "https://www.instagram.com/alice/",
                "https://www.instagram.com/alice/?utm_source=test",
                "bad",
                "bad",
            ]
        )

        summary = payload["summary"]
        self.assertEqual(
            summary["non_empty_count"],
            summary["accepted_unique_count"]
            + summary["duplicate_count"]
            + summary["rejected_count"],
        )
        self.assertIn("normalized_links", payload)
        self.assertIn("invalid_links", payload)
        self.assertEqual(1, len(payload["normalized_links"]))
        self.assertEqual(1, len(payload["invalid_links"]), "legacy invalid links stay deduplicated")

    def test_canonical_link_is_valid_without_fabricated_normalization(self) -> None:
        payload = scraper.build_normalize_payload(["https://www.tiktok.com/@alice"])

        result = payload["link_results"][0]
        self.assertEqual("valid", result["status"])
        self.assertEqual("无需调整", result["reason"])
        self.assertIsNone(result["duplicate_of_line"])

    def test_different_content_urls_explain_normalized_duplicate(self) -> None:
        payload = scraper.build_normalize_payload(
            [
                "https://www.tiktok.com/@alice/video/1001",
                "https://www.tiktok.com/@alice/video/1002",
            ]
        )

        self.assertEqual(["normalized", "duplicate"], [item["status"] for item in payload["link_results"]])
        self.assertEqual("标准化后重复", payload["link_results"][1]["reason"])
        self.assertEqual(1, payload["link_results"][1]["duplicate_of_line"])

    def test_mixed_platforms_malformed_and_unsupported_inputs_reconcile(self) -> None:
        payload = scraper.build_normalize_payload(
            [
                "https://www.tiktok.com/@alice",
                "https://www.instagram.com/bob/",
                "https://www.youtube.com/@charlie",
                "https://example.com/person",
                "malformed",
            ]
        )

        self.assertEqual(
            {"tiktok", "instagram", "youtube"},
            {item["platform"] for item in payload["link_results"] if item["status"] != "invalid"},
        )
        self.assertEqual(5, payload["summary"]["non_empty_count"])
        self.assertEqual(3, payload["summary"]["accepted_unique_count"])
        self.assertEqual(0, payload["summary"]["duplicate_count"])
        self.assertEqual(2, payload["summary"]["rejected_count"])


if __name__ == "__main__":
    unittest.main()
