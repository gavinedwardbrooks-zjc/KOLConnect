from __future__ import annotations

import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import creator_repository
import migrate_scrape_status
import scraper


class ScrapeStatusModelTests(unittest.TestCase):
    URL = "https://www.tiktok.com/@status-model"

    def classify(self, access_status: str = "success", **fields) -> str:
        return scraper.finalize_scrape_status(
            access_status,
            platform=fields.get("platform", "TikTok"),
            profile_url=fields.get("profile_url", self.URL),
            name=fields.get("name", ""),
            emails=fields.get("emails", []),
            follower_count=fields.get("follower_count", ""),
            whatsapp=fields.get("whatsapp", ""),
            has_video_data=fields.get("has_video_data", False),
        )

    def test_complete_identity_and_enhanced_data_is_success(self) -> None:
        self.assertEqual("success", self.classify(name="Creator", emails=["creator@unit.test"]))

    def test_warning_with_name_and_email_is_partial_success(self) -> None:
        access_status, reason = scraper.detect_scrape_access(
            "TikTok", "<html><body>Try again</body></html>", "browser"
        )
        self.assertEqual("platform_error", access_status)
        self.assertIn("warning_text_detected", reason)
        self.assertEqual(
            "partial_success",
            self.classify(access_status, name="Creator", emails=["creator@unit.test"]),
        )

    def test_name_without_enhanced_data_is_partial_success(self) -> None:
        self.assertEqual("partial_success", self.classify(name="Creator"))

    def test_missing_identity_is_failed(self) -> None:
        self.assertEqual("failed", self.classify())

    def test_status_reason_survives_csv_round_trip(self) -> None:
        result = scraper.build_result(
            url=self.URL,
            platform="TikTok",
            name="Creator",
            emails=["creator@unit.test"],
            scrape_status="partial_success",
            status_reason="warning_text_detected:try again",
        )
        restored = scraper.row_to_result(scraper.result_to_row(result))
        self.assertEqual("partial_success", restored["scrape_status"])
        self.assertIn("warning_text_detected", restored["status_reason"])

    def test_legacy_896_abnormal_rows_reclassify_without_business_changes(self) -> None:
        rows = []
        for index in range(874):
            rows.append(
                scraper.result_to_row(
                    scraper.build_result(
                        url=f"https://www.tiktok.com/@usable-{index}",
                        platform="TikTok",
                        name=f"Creator {index}",
                        emails=[f"creator{index}@unit.test"],
                        scrape_status="platform_error",
                    )
                )
            )
        rows.append(
            scraper.result_to_row(
                scraper.build_result(
                    url="https://www.tiktok.com/@empty-warning",
                    platform="TikTok",
                    scrape_status="platform_error",
                )
            )
        )
        for index in range(21):
            rows.append(
                scraper.result_to_row(
                    scraper.build_result(
                        url=f"https://www.tiktok.com/@missing-{index}",
                        platform="TikTok",
                        scrape_status="missing_data",
                    )
                )
            )

        fieldnames, migrated, summary = migrate_scrape_status.reclassify_rows(
            list(scraper.OUTPUT_FIELDS), rows
        )
        self.assertIn(scraper.FIELD_STATUS_REASON, fieldnames)
        self.assertEqual(896, summary["rows"])
        self.assertEqual({"failed": 22, "partial_success": 874}, summary["after"])
        self.assertEqual(
            Counter({"partial_success": 874, "failed": 22}),
            Counter(row[scraper.FIELD_SCRAPE_STATUS] for row in migrated),
        )
        for before, after in zip(rows, migrated, strict=True):
            for field in scraper.OUTPUT_FIELDS:
                if field not in {scraper.FIELD_SCRAPE_STATUS, scraper.FIELD_STATUS_REASON}:
                    self.assertEqual(before.get(field, ""), after.get(field, ""))

    def test_partial_success_can_enter_creator_library(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temp_dir, mock.patch.object(
            creator_repository, "log_event"
        ):
            repository = creator_repository.CreatorRepository(Path(temp_dir) / "Creator_Library.xlsx")
            summary = repository.importTaskResults(
                "task_20260806T120000Z_1234abcd",
                [
                    {
                        "account_uid": f"tiktok|{self.URL}",
                        "platform": "TikTok",
                        "profile_url": self.URL,
                        "creator_name": "Creator",
                        "email": "creator@unit.test",
                        "scrape_status": "partial_success",
                    }
                ],
                source="系统抓取",
            )
            self.assertEqual(1, summary["created_creators"])
            self.assertEqual(1, summary["created_accounts"])
            self.assertEqual(0, summary["skipped_failed"])


if __name__ == "__main__":
    unittest.main()
