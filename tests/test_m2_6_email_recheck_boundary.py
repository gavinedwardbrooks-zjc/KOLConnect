from __future__ import annotations

import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import scraper
from adapters.task_manager_adapter import TaskManagerAdapter
from ports.creator_port import EmailRecheckCandidate, EmailRecheckCandidateScan
from repositories.task_repository import TaskRepository
from services.creator_service import CreatorService
from services.task_service import TaskService


class CreatorAccountsRepository:
    def __init__(self, accounts: list[dict]) -> None:
        self.accounts = accounts

    def getCreatorAccounts(self, creator_id: str = "") -> list[dict]:
        return list(self.accounts)


class EmailCandidatePort:
    def __init__(self, scan: EmailRecheckCandidateScan) -> None:
        self.scan = scan
        self.calls = 0

    def get_email_recheck_candidates(self) -> EmailRecheckCandidateScan:
        self.calls += 1
        return self.scan


class EmailRecheckBoundaryTests(unittest.TestCase):
    @staticmethod
    def _uid(url: str, platform: str) -> str:
        return scraper.build_creator_uid(
            scraper.build_result(url=url, platform=platform)
        )

    def test_creator_service_preserves_candidate_filter_and_dedup_order(self):
        valid_url = "https://www.tiktok.com/@candidate"
        valid_uid = self._uid(valid_url, "TikTok")
        accounts = [
            {"account_uid": "", "platform": "TikTok", "profile_url": valid_url},
            {
                "creator_id": "creator-1",
                "account_id": "account-1",
                "account_uid": valid_uid,
                "platform": "TikTok",
                "profile_url": valid_url,
                "username": "candidate",
                "account_email": "",
            },
            {
                "account_uid": valid_uid,
                "platform": "TikTok",
                "profile_url": valid_url,
                "account_email": "already@example.test",
            },
            {
                "account_uid": "youtube|https://www.youtube.com/@has-email",
                "platform": "YouTube",
                "profile_url": "https://www.youtube.com/@has-email",
                "account_email": "has@example.test",
            },
            {
                "account_uid": "other|profile",
                "platform": "Other",
                "profile_url": "profile",
                "account_email": "",
            },
            {
                "account_uid": "tiktok|mismatch",
                "platform": "TikTok",
                "profile_url": "https://www.tiktok.com/@different",
                "account_email": "",
            },
        ]
        service = CreatorService(
            lambda: CreatorAccountsRepository(accounts), lambda: None
        )

        scan = service.get_email_recheck_candidates()

        self.assertEqual(scan.scanned_accounts, 6)
        self.assertEqual(len(scan.candidates), 1)
        self.assertEqual(scan.candidates[0].account_uid, valid_uid)
        self.assertEqual(scan.duplicate_uids, (valid_uid,))
        self.assertEqual(
            scan.skipped,
            (
                "missing_uid: 账号唯一ID为空",
                f"duplicate_uid: {valid_uid}",
                "other|profile: 平台或主页链接不完整",
                "tiktok|mismatch: 账号唯一ID、平台或主页链接不完整/不一致",
            ),
        )

    def test_no_candidates_preserves_response_and_creates_no_task(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_dir = Path(temp_dir) / "tasks"
            creator_port = EmailCandidatePort(
                EmailRecheckCandidateScan(scanned_accounts=2, candidates=())
            )
            service = TaskService(
                lambda: TaskManagerAdapter(lambda: tasks_dir),
                lambda: creator_port,
                lambda: TaskRepository(tasks_dir),
            )

            response = service.create_email_recheck_task()

            self.assertEqual(
                response,
                {
                    "task": None,
                    "scanned_accounts": 2,
                    "created_count": 0,
                    "skipped_count": 0,
                    "skipped": [],
                    "duplicate_uids": [],
                },
            )
            self.assertFalse(tasks_dir.exists())

    def test_task_service_creates_compatible_email_recheck_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tasks_dir = Path(temp_dir) / "tasks"
            profile_url = "https://www.instagram.com/candidate/"
            uid = self._uid(profile_url, "Instagram")
            creator_port = EmailCandidatePort(
                EmailRecheckCandidateScan(
                    scanned_accounts=3,
                    candidates=(
                        EmailRecheckCandidate(
                            creator_id="creator-1",
                            account_id="account-1",
                            account_uid=uid,
                            platform="Instagram",
                            profile_url=profile_url,
                            username="candidate",
                        ),
                    ),
                    skipped=("missing_uid: 账号唯一ID为空",),
                )
            )
            repository = TaskRepository(tasks_dir)
            task_port = TaskManagerAdapter(lambda: tasks_dir)
            service = TaskService(
                lambda: task_port, lambda: creator_port, lambda: repository
            )

            response = service.create_email_recheck_task()
            task = response["task"]
            stored = repository.get_task(task["id"])

            self.assertEqual(response["scanned_accounts"], 3)
            self.assertEqual(response["created_count"], 1)
            self.assertEqual(response["skipped_count"], 1)
            self.assertEqual(stored["status"], "email_recheck_created")
            self.assertEqual(
                stored["email_recheck_source"], "local_account_empty_email"
            )
            self.assertEqual(stored["scan_skipped_count"], 1)
            self.assertEqual(repository.read_links(task["id"]), [profile_url])
            self.assertEqual(
                repository.read_results_document(task["id"]).fieldnames,
                tuple(scraper.OUTPUT_FIELDS),
            )
            self.assertEqual(
                repository.read_progress_document(task["id"]).fieldnames,
                tuple(scraper.PROGRESS_FIELDS),
            )
            self.assertEqual(repository.read_modifications(task["id"]), [])
            metadata = json.loads(
                (tasks_dir / task["id"] / "task.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata, stored)

    def test_task_service_has_no_forbidden_email_recheck_dependencies(self):
        source = (APP_DIR / "services" / "task_service.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertTrue(
            {"server", "http_handlers", "task_manager", "scraper"}.isdisjoint(
                imported
            )
        )


if __name__ == "__main__":
    unittest.main()
