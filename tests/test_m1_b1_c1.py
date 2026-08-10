from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))


def close_app_logger() -> None:
    app_logging = sys.modules.get("app_logging")
    if app_logging is None:
        return
    logger = app_logging.logging.getLogger(app_logging.LOGGER_NAME)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    app_logging._CONFIGURED = False


def reload_server():
    close_app_logger()
    for module_name in (
        "server",
        "runtime_paths",
        "mail_sync",
        "task_manager",
        "dashboard_repository",
        "dashboard_service",
        "app_logging",
        "creator_repository",
    ):
        sys.modules.pop(module_name, None)
    return importlib.import_module("server")


class PluginContractAndEmailRecheckTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = mock.patch.dict(
            os.environ,
            {
                "APPDATA": self.temp_dir.name,
                "HOME": self.temp_dir.name,
                "XDG_DATA_HOME": self.temp_dir.name,
            },
        )
        self.env_patch.start()
        self.server = reload_server()

    def tearDown(self) -> None:
        close_app_logger()
        self.env_patch.stop()
        self.temp_dir.cleanup()

    def _analysis(
        self,
        task_id: str,
        *,
        platform: str,
        profile_url: str,
        email: str = "",
        creator_id: str = "",
    ) -> dict:
        account_uid = self.server.scraper_module.build_creator_uid(
            {"platform": platform, "url": profile_url}
        )
        return {
            "schema_version": "1.0",
            "analysis_id": f"analysis_{task_id}",
            "creator_id": creator_id,
            "task_id": task_id,
            "account_uid": account_uid,
            "imported_at": "2026-08-07T00:00:00Z",
            "source": "test",
            "creator": {
                "creator_name": "Shared Creator",
                "platform": platform,
                "profile_url": profile_url,
                "followers": "100",
                "email": email,
            },
            "content_category": "Gaming",
            "videos": [],
            "video_analysis": {},
            "creator_insight": {},
        }

    def _prepare_recheck(self):
        repository = self.server.get_creator_repository()
        first = repository.saveCreator(
            self._analysis(
                "task_20260807T000001Z_aaaaaaaa",
                platform="TikTok",
                profile_url="https://www.tiktok.com/@sharedcreator",
            )
        )
        repository.saveCreator(
            self._analysis(
                "task_20260807T000002Z_bbbbbbbb",
                platform="YouTube",
                profile_url="https://www.youtube.com/@sharedcreator",
                email="youtube@creator-mail.com",
                creator_id=first["creator_id"],
            )
        )
        scan = self.server.create_email_recheck_task()
        self.assertEqual(1, scan["created_count"])
        return repository, scan["task"], first["creator_id"], first["account_uid"]

    def _write_recheck_email(self, task: dict, email: str) -> None:
        _task, paths = self.server.task_manager.load_task(self.server.TASKS_DIR, task["id"])
        _fields, rows = self.server._read_task_csv(paths["results"])
        self.assertEqual(1, len(rows))
        rows[0][self.server.scraper_module.FIELD_NAME] = "Shared Creator"
        rows[0][self.server.scraper_module.FIELD_EMAIL] = email
        rows[0][self.server.scraper_module.FIELD_STATUS] = "完成"
        rows[0][self.server.scraper_module.FIELD_SCRAPE_STATUS] = (
            "success" if email else "partial_success"
        )
        self.server.task_manager.atomic_write_files(
            {
                paths["results"]: self.server._csv_content(
                    self.server.scraper_module.OUTPUT_FIELDS, rows
                )
            }
        )
        self.server.task_manager.update_task(
            self.server.TASKS_DIR,
            task["id"],
            status="completed",
            finished_at="2026-08-07T01:00:00Z",
        )

    def _creator_row(self, repository, creator_id: str) -> dict:
        workbook = repository._load_workbook()
        try:
            return repository._creator_row(workbook["Creators"], creator_id)
        finally:
            workbook.close()

    def test_extension_payload_persists_crm_fields_and_task_contract(self) -> None:
        result = self.server.import_extension_capture(
            {
                "task_name": "Extension contract",
                "creator": {
                    "creator_name": "Maria",
                    "platform": "TikTok",
                    "profile_url": "https://www.tiktok.com/@maria",
                    "followers": "1000",
                    "email": "  maria@example.com  ",
                    "country": "  Brazil  ",
                    "content_category": "  Beauty  ",
                },
                "whatsapp": "  +5511999999999  ",
                "language": "  Portuguese  ",
                "content_category": "  Lifestyle  ",
            }
        )

        task, paths = self.server.task_manager.load_task(self.server.TASKS_DIR, result["task"]["id"])
        self.assertEqual(
            {
                "country": "Brazil",
                "language": "Portuguese",
                "content_category": "Lifestyle",
            },
            task["extension_crm"],
        )
        _fields, rows = self.server._read_task_csv(paths["results"])
        mapped = self.server._task_rows_for_creator_library(task, rows)[0]
        self.assertEqual("Brazil", mapped["country"])
        self.assertEqual("Portuguese", mapped["language"])
        self.assertEqual("Lifestyle", mapped["content_category"])

        repository = self.server.get_creator_repository()
        creator = self._creator_row(repository, result["analysis_id"])
        account = next(
            item for item in repository.getCreatorAccounts("")
            if item["account_uid"] == result["account_uid"]
        )
        self.assertEqual("maria@example.com", creator["email"])
        self.assertEqual("+5511999999999", creator["whatsapp"])
        self.assertEqual("Brazil", creator["country"])
        self.assertEqual("Portuguese", creator["language"])
        self.assertEqual("Lifestyle", creator["content_category"])
        self.assertEqual("maria@example.com", account["account_email"])

    def test_regular_scrape_import_behavior_is_unchanged(self) -> None:
        repository = self.server.get_creator_repository()
        summary = repository.importTaskResults(
            "task_20260807T010001Z_cccccccc",
            [
                {
                    "account_uid": "instagram|https://www.instagram.com/ordinary",
                    "platform": "Instagram",
                    "profile_url": "https://www.instagram.com/ordinary",
                    "creator_name": "Ordinary",
                    "email": "ordinary@example.com",
                    "scrape_status": "success",
                }
            ],
            source="系统抓取",
            imported_at="2026-08-07T01:00:01Z",
        )
        self.assertEqual(1, summary["created_creators"])
        self.assertEqual(1, summary["created_accounts"])
        self.assertEqual("ordinary@example.com", repository.getCreatorAccounts("")[0]["account_email"])

    def test_email_recheck_uses_local_accounts_without_feishu(self) -> None:
        with mock.patch.object(
            self.server,
            "get_four_table_feishu_config",
            side_effect=AssertionError("Feishu must not be read"),
        ):
            _repository, task, _creator_id, _account_uid = self._prepare_recheck()
        self.assertEqual("local_account_empty_email", task["email_recheck_source"])
        self.assertEqual(1, task["valid_count"])

    def test_email_recheck_updates_only_the_matching_account_uid(self) -> None:
        repository, task, creator_id, target_uid = self._prepare_recheck()
        self._write_recheck_email(task, "new@creator-mail.com")

        result = self.server.import_task_results_to_creator_library(task["id"])
        accounts = {row["account_uid"]: row for row in repository.getCreatorAccounts("")}
        creator = self._creator_row(repository, creator_id)

        self.assertEqual("success", result["status"])
        self.assertEqual("new@creator-mail.com", creator["email"])
        self.assertEqual("new@creator-mail.com", accounts[target_uid]["account_email"])
        youtube_uid = "youtube|https://www.youtube.com/@sharedcreator"
        self.assertEqual("youtube@creator-mail.com", accounts[youtube_uid]["account_email"])

    def test_empty_recheck_email_does_not_clear_existing_email(self) -> None:
        repository, task, creator_id, target_uid = self._prepare_recheck()
        self._write_recheck_email(task, "new@creator-mail.com")
        self.server.import_task_results_to_creator_library(task["id"])
        self._write_recheck_email(task, "")

        self.server.import_task_results_to_creator_library(task["id"])
        accounts = {row["account_uid"]: row for row in repository.getCreatorAccounts("")}
        creator = self._creator_row(repository, creator_id)
        self.assertEqual("new@creator-mail.com", creator["email"])
        self.assertEqual("new@creator-mail.com", accounts[target_uid]["account_email"])

    def test_repeated_email_recheck_import_is_idempotent(self) -> None:
        repository, task, creator_id, target_uid = self._prepare_recheck()
        self._write_recheck_email(task, "stable@creator-mail.com")

        first = self.server.import_task_results_to_creator_library(task["id"])
        second = self.server.import_task_results_to_creator_library(task["id"])
        accounts = {row["account_uid"]: row for row in repository.getCreatorAccounts("")}

        self.assertEqual("success", first["status"])
        self.assertEqual("success", second["status"])
        self.assertEqual(1, len(repository.getCreators()))
        self.assertEqual(2, len(accounts))
        self.assertEqual("stable@creator-mail.com", accounts[target_uid]["account_email"])
        self.assertEqual(3, len(repository.getCreatorSnapshots(creator_id)))


if __name__ == "__main__":
    unittest.main()
