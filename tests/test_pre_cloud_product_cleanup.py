from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
for path in (APP_DIR, ROOT / "tests"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import scraper
from adapters.task_manager_adapter import TaskManagerAdapter
from repository_factory import RepositoryFactory
from repositories.task_repository import TaskRepository
from services.creator_service import CreatorService
from services.task_result_mapper import map_task_rows_for_creator_library
from services.task_service import TaskService
from storage.migration import ExcelToSQLiteMigrator
from storage.paths import SQLiteStoragePaths
from test_pre_m8_excel_sqlite_migration import build_fixture


class PreCloudProductCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tasks_dir = Path(self.temp_dir.name) / "tasks"
        self.repository = TaskRepository(self.tasks_dir)
        self.adapter = TaskManagerAdapter(lambda: self.tasks_dir)
        self.service = TaskService(
            lambda: self.adapter,
            lambda: object(),
            lambda: self.repository,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_scrape_identity_is_account_scoped_and_does_not_claim_creator_name(self):
        result = scraper.build_result(
            url="https://www.tiktok.com/@account_label",
            platform="TikTok",
            # Scrapers deliberately do not promote page metadata to this
            # person-level field.
            name="",
            account_name="account_label",
        )
        item = map_task_rows_for_creator_library(
            {"task_type": "scrape"}, (scraper.result_to_row(result),)
        )[0]

        self.assertEqual(result["account_name"], "account_label")
        self.assertEqual(item.creator_name, "")
        self.assertEqual(scraper.account_name_from_url(result["url"], "TikTok"), "account_label")

    def test_manual_task_metadata_remains_the_explicit_person_name_source(self):
        result = scraper.build_result(
            url="https://www.instagram.com/account_label/",
            platform="Instagram",
            account_name="account_label",
        )
        item = map_task_rows_for_creator_library(
            {"task_type": "manual", "manual_creator_name": "Explicit Person"},
            (scraper.result_to_row(result),),
        )[0]

        self.assertEqual(item.creator_name, "Explicit Person")

    def test_results_csv_omits_runtime_diagnostics_and_result_read_merges_them(self):
        task = self.repository.create_task(
            ["https://www.instagram.com/example/"], [], 1,
            platform_summary={"Instagram": 1},
        )
        result = scraper.build_result(
            url="https://www.instagram.com/example/",
            platform="Instagram",
            account_name="example",
            scrape_status="failed",
            status_reason="network_timeout",
            last_scrape_time="2026-09-11T00:00:00Z",
            retry_count=2,
        )
        result_row = scraper.result_to_row(result)
        progress_row = dict(result_row, **{scraper.FIELD_STATUS: "失败"})
        self.repository.write_results(
            task["id"], [result_row], scraper.OUTPUT_FIELDS
        )
        self.repository.write_progress(
            task["id"], [progress_row], scraper.PROGRESS_FIELDS
        )

        stored = self.repository.read_results(task["id"])[0]
        self.assertNotIn(scraper.FIELD_SCRAPE_STATUS, stored)
        self.assertNotIn(scraper.FIELD_STATUS_REASON, stored)
        self.assertNotIn(scraper.FIELD_NAME, stored)
        response = self.adapter.get_task_results(task["id"]).to_response()
        record = response["records"][0]
        self.assertEqual(record["scrape_status"], "failed")
        self.assertIn("network_timeout", record["status_reason"])
        self.assertEqual(record["retry_count"], "2")

    def test_legacy_task_name_column_remains_readable(self):
        task = self.repository.create_task(
            ["https://www.youtube.com/@legacy_account"], [], 1,
            platform_summary={"YouTube": 1},
        )
        result = scraper.build_result(
            url="https://www.youtube.com/@legacy_account",
            platform="YouTube",
            name="Historical display name",
        )
        legacy_row = scraper.result_to_row(result)
        self.repository.write_results(task["id"], [legacy_row], list(legacy_row))
        self.repository.write_progress(task["id"], [legacy_row], list(legacy_row))

        record = self.adapter.get_task_results(task["id"]).to_response()["records"][0]

        self.assertEqual(record[scraper.FIELD_NAME], "Historical display name")

    def test_latest_publication_date_only_uses_target_account_non_pinned_items(self):
        items = [
            {"account_name": "target", "published_at": "2026-09-01T12:00:00Z"},
            {"account_name": "target", "published_at": "2026-09-10T12:00:00Z", "is_pinned": True},
            {"account_name": "other", "published_at": "2026-09-11T12:00:00Z"},
            {"account_name": "target", "published_at": "not-a-timestamp"},
            {"account_name": "target", "published_at": "2026-09-03T12:00:00Z"},
        ]
        self.assertEqual(
            scraper.latest_publication_date_from_content(
                items, target_account_name="target"
            ),
            "2026-09-03",
        )
        self.assertEqual(
            scraper.latest_publication_date_from_content(
                [{"account_name": "target", "published_at": "invalid"}],
                target_account_name="target",
            ),
            "",
        )
        self.assertEqual(scraper.extract_latest_publish_date("2026-09-11"), "")

    def test_platform_task_runs_reuse_one_input_list_and_persist_run_history(self):
        links = [
            "https://www.tiktok.com/@creator",
            "https://www.instagram.com/creator/",
            "https://www.youtube.com/@creator",
        ]
        task = self.repository.create_task(
            links, [], len(links),
            platforms=["tiktok", "instagram", "youtube"],
            platform_summary={"TikTok": 1, "Instagram": 1, "YouTube": 1},
        )

        first = self.service.prepare_task_run(
            task["id"], platforms=["tiktok"], profile="Default"
        )
        self.assertEqual(first["selected_platforms"], ["tiktok"])
        self.assertEqual(first["selected_count"], 1)
        self.assertEqual(self.repository.read_links(task["id"]), links)
        self.assertTrue((self.tasks_dir / task["id"] / "links.csv").exists())
        self.repository.write_progress(
            task["id"],
            [{scraper.FIELD_URL: links[0], scraper.FIELD_STATUS: "完成"}],
            [scraper.FIELD_URL, scraper.FIELD_STATUS],
        )
        self.service.finish_task_run(task["id"], status="success")

        second = self.service.prepare_task_run(
            task["id"], platforms=["instagram"], profile="Default"
        )
        runs = self.repository.read_runs(task["id"])
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0]["status"], "success")
        self.assertEqual(runs[0]["selected_platforms"], ["tiktok"])
        self.assertEqual(second["selected_platforms"], ["instagram"])
        self.assertEqual(second["unfinished_count"], 1)

    def test_direct_whatsapp_edit_persists_to_the_sqlite_creator_authority(self):
        root = Path(self.temp_dir.name) / "sqlite_runtime"
        root.mkdir()
        workbook = root / "legacy.xlsx"
        build_fixture(workbook)
        paths = SQLiteStoragePaths.for_app_data(root / "appdata")
        with patch(
            "local_storage_lock.get_shared_storage_lock_path",
            return_value=root / "locks" / "shared_storage.lock",
        ):
            migration = ExcelToSQLiteMigrator(paths).migrate(workbook)
            ExcelToSQLiteMigrator(paths).activate_synthetic(migration)
            repository = RepositoryFactory.for_runtime(
                workbook,
                storage_paths=paths,
                tasks_dir=root / "tasks",
                data_protection_file=root / "data_protection.json",
            ).creator()
            repository.updateCreator("creator_0000", {"whatsapp": "+5511999999999"})
            detail = repository.getCreatorDetail("creator_0000")

        self.assertEqual(detail["record"]["whatsapp"], "+5511999999999")

    def test_post_import_task_edit_converges_into_sqlite_creator_authority(self):
        root = Path(self.temp_dir.name) / "task_sqlite_runtime"
        root.mkdir()
        workbook = root / "legacy.xlsx"
        build_fixture(workbook)
        paths = SQLiteStoragePaths.for_app_data(root / "appdata")
        with patch(
            "local_storage_lock.get_shared_storage_lock_path",
            return_value=root / "locks" / "shared_storage.lock",
        ):
            migration = ExcelToSQLiteMigrator(paths).migrate(workbook)
            ExcelToSQLiteMigrator(paths).activate_synthetic(migration)
            creator_repository = RepositoryFactory.for_runtime(
                workbook,
                storage_paths=paths,
                tasks_dir=root / "tasks",
                data_protection_file=root / "data_protection.json",
            ).creator()
            task_repository = TaskRepository(root / "tasks")
            task_port = TaskManagerAdapter(lambda: root / "tasks")
            creator_service = CreatorService(
                lambda: creator_repository,
                lambda: task_port,
                lambda: {},
                lambda _value: None,
            )
            task_service = TaskService(
                lambda: task_port,
                lambda: creator_service,
                lambda: task_repository,
            )
            url = "https://www.instagram.com/post_import_account/"
            task = task_repository.create_task([url], [], 1)
            task = task_repository.update_task(
                task["id"],
                status="completed",
                creator_library_import_eligible=True,
            )
            result = scraper.build_result(
                url=url,
                platform="Instagram",
                account_name="post_import_account",
                emails=["before@example.test"],
            )
            row = scraper.result_to_row(result)
            progress = dict(row)
            progress[scraper.FIELD_STATUS] = "完成"
            progress[scraper.FIELD_SCRAPE_STATUS] = "success"
            task_repository.write_results(task["id"], [row], scraper.OUTPUT_FIELDS)
            task_repository.write_progress(task["id"], [progress], scraper.PROGRESS_FIELDS)

            imported = task_service.import_task_results_to_creator_library(task["id"])
            creator_id = imported["creator_ids"][0]
            task_service.update_task_results(
                task["id"],
                scraper.build_creator_uid(result),
                {scraper.FIELD_EMAIL: "after@example.test"},
            )
            detail = creator_repository.getCreatorDetail(creator_id)

        self.assertEqual(detail["accounts"][0]["account_email"], "after@example.test")


if __name__ == "__main__":
    unittest.main()
