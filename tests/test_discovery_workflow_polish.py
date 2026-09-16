from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper  # noqa: E402
from adapters.task_manager_adapter import TaskManagerAdapter  # noqa: E402
from repositories.task_repository import TaskRepository  # noqa: E402
from services.task_service import TaskService  # noqa: E402


class CreatorAccountsPort:
    def __init__(self, accounts: list[dict]) -> None:
        self.accounts = accounts

    def get_creator_accounts(self) -> list[dict]:
        return [dict(item) for item in self.accounts]


class DiscoveryWorkflowPolishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.repository = TaskRepository(self.tasks_dir)
        self.adapter = TaskManagerAdapter(lambda: self.tasks_dir)
        self.links = [
            "https://www.tiktok.com/@done",
            "https://www.instagram.com/pending/",
            "https://www.youtube.com/@done",
        ]
        self.accounts = [
            {
                "account_uid": scraper.build_creator_uid(
                    scraper.build_result(url=self.links[0], platform="TikTok")
                ),
                "platform": "TikTok",
                "profile_url": self.links[0],
                "username": "done",
                "account_email": "known@example.test",
            }
        ]
        self.creator_port = CreatorAccountsPort(self.accounts)
        self.service = TaskService(
            lambda: self.adapter,
            lambda: self.creator_port,
            lambda: self.repository,
        )
        self.task = self.repository.create_task(
            self.links,
            [],
            len(self.links),
            name="跨平台发现",
            platforms=["tiktok", "instagram", "youtube"],
            platform_summary={"TikTok": 1, "Instagram": 1, "YouTube": 1},
        )
        done_rows = [
            scraper.result_to_row(
                scraper.build_result(url=self.links[0], platform="TikTok")
            ),
            scraper.result_to_row(
                scraper.build_result(url=self.links[2], platform="YouTube")
            ),
        ]
        self.repository.write_progress(
            self.task["id"],
            [dict(row, **{scraper.FIELD_STATUS: "完成"}) for row in done_rows],
            scraper.PROGRESS_FIELDS,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_continue_other_platform_retains_task_links_and_run_history(self) -> None:
        first = self.service.prepare_task_run(
            self.task["id"], platforms=["tiktok"], profile="Default"
        )
        self.service.finish_task_run(self.task["id"], status="completed")
        second = self.service.prepare_task_run(
            self.task["id"], platforms=["instagram"], profile="Default"
        )

        self.assertEqual(["tiktok"], first["selected_platforms"])
        self.assertEqual(["instagram"], second["selected_platforms"])
        self.assertEqual(1, second["selected_count"])
        self.assertEqual(1, second["unfinished_count"])
        self.assertEqual(self.links, self.repository.read_links(self.task["id"]))
        self.assertEqual(2, len(self.repository.read_runs(self.task["id"])))

        failed = scraper.result_to_row(
            scraper.build_result(
                url=self.links[2], platform="YouTube", scrape_status="failed"
            )
        )
        self.repository.write_progress(
            self.task["id"],
            [dict(failed, **{scraper.FIELD_STATUS: "完成"})],
            scraper.PROGRESS_FIELDS,
        )
        self.service.prepare_task_run(
            self.task["id"], platforms=["youtube"], profile="Default"
        )
        self.assertEqual(
            [self.links[2]], self.repository.get_task(self.task["id"])["retry_requested_urls"]
        )

    def test_all_and_unfinished_original_link_contracts(self) -> None:
        failed = scraper.result_to_row(
            scraper.build_result(
                url=self.links[2], platform="YouTube", scrape_status="failed"
            )
        )
        current = self.repository.read_progress(self.task["id"])
        self.repository.write_progress(
            self.task["id"],
            [current[0], dict(failed, **{scraper.FIELD_STATUS: "完成"})],
            scraper.PROGRESS_FIELDS,
        )
        all_links = self.service.get_task_input_links(
            self.task["id"], unfinished_only=False
        )
        unfinished = self.service.get_task_input_links(
            self.task["id"], unfinished_only=True
        )

        self.assertEqual(self.links, all_links["links"])
        self.assertEqual([self.links[1], self.links[2]], unfinished["links"])

    def test_task_email_source_defaults_to_missing_accounts_and_platform_filter(self) -> None:
        preview = self.service.get_email_enrichment_candidates(
            source="task",
            task_id=self.task["id"],
            platforms=["instagram"],
            missing_only=True,
        )

        self.assertEqual(1, preview["candidate_count"])
        self.assertEqual("Instagram", preview["candidates"][0]["platform"])
        self.assertEqual(self.links[1], preview["candidates"][0]["profile_url"])
        self.assertNotIn("account_uid", preview["candidates"][0])

    def test_review_and_creator_library_sources_use_authoritative_records(self) -> None:
        instagram = scraper.result_to_row(
            scraper.build_result(
                url=self.links[1], platform="Instagram", emails=[],
                scrape_status="success",
            )
        )
        self.repository.write_results(
            self.task["id"], [instagram], scraper.OUTPUT_FIELDS
        )
        review = self.service.get_email_enrichment_candidates(
            source="review_results", task_id=self.task["id"], missing_only=True
        )
        library = self.service.get_email_enrichment_candidates(
            source="creator_library", missing_only=False
        )

        self.assertEqual(1, review["candidate_count"])
        self.assertEqual(self.links[1], review["candidates"][0]["profile_url"])
        self.assertEqual(1, library["candidate_count"])
        self.assertTrue(library["candidates"][0]["has_email"])

    def test_email_recheck_creation_rebuilds_selection_and_keeps_source_task(self) -> None:
        response = self.service.create_email_recheck_task(
            source="task",
            task_id=self.task["id"],
            platforms=["instagram"],
            missing_only=True,
        )

        created = response["task"]
        self.assertNotEqual(self.task["id"], created["id"])
        self.assertEqual("task", created["email_recheck_source"])
        self.assertEqual([self.links[1]], self.repository.read_links(created["id"]))
        self.assertEqual(self.links, self.repository.read_links(self.task["id"]))


if __name__ == "__main__":
    unittest.main()
