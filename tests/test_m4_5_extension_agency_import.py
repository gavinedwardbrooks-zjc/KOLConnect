from __future__ import annotations

import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

import app_logging  # noqa: E402

with (
    mock.patch.object(app_logging, "log_event"),
    mock.patch.object(app_logging, "log_error"),
):
    import server  # noqa: E402

from creator_repository import CreatorRepository  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


class FakeAgencyPort:
    def __init__(self, agency_ids: set[str]) -> None:
        self.agency_ids = agency_ids

    def get_agency(self, agency_id: str) -> dict:
        if agency_id not in self.agency_ids:
            raise ValueError("关联的 Agency 不存在。")
        return {"agency_id": agency_id, "name": agency_id}


class ExtensionAgencyImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = test_artifact_path("m4_5_test", uuid.uuid4().hex)
        self.root.mkdir()
        self.repository = CreatorRepository(self.root / "Creator_Library.xlsx")
        self.agency_port = FakeAgencyPort({"agency_one", "agency_two"})
        self.service = CreatorService(
            lambda: self.repository,
            lambda: None,
            agency_port_provider=lambda: self.agency_port,
        )
        self.log_patcher = mock.patch("creator_repository.log_event")
        self.log_patcher.start()

    def tearDown(self) -> None:
        self.log_patcher.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    @staticmethod
    def payload(profile_url: str, agency_id: str = "") -> dict:
        return {
            "creator": {
                "creator_name": "Creator",
                "platform": "TikTok",
                "profile_url": profile_url,
                "agency_id": agency_id,
            },
            "content_category": "Gaming",
        }

    def analysis(self, profile_url: str, agency_id: str, task_id: str) -> dict:
        payload = self.payload(profile_url, agency_id)
        return server._extension_analysis_payload(
            payload,
            {"id": task_id},
            f"TikTok|{profile_url}",
        )

    def test_selected_agency_is_accepted_and_persisted(self) -> None:
        analysis = self.analysis(
            "https://www.tiktok.com/@agency-selected",
            "agency_one",
            "task_20260817T000001Z_aaaaaaaa",
        )
        self.assertEqual("agency_one", analysis["creator"]["agency_id"])
        saved = self.service.import_creator_from_extension(
            analysis, compensation_task_id="task_20260817T000001Z_aaaaaaaa"
        )
        detail = self.repository.getCreatorDetail(saved["creator_id"])
        self.assertEqual("agency_one", detail["record"]["agency_id"])

    def test_empty_agency_is_allowed_and_existing_policy_is_preserved(self) -> None:
        profile_url = "https://www.tiktok.com/@agency-existing"
        first = self.service.import_creator_from_extension(
            self.analysis(profile_url, "agency_one", "task_20260817T000002Z_bbbbbbbb"),
            compensation_task_id="task_20260817T000002Z_bbbbbbbb",
        )
        self.service.import_creator_from_extension(
            self.analysis(profile_url, "", "task_20260817T000003Z_cccccccc"),
            compensation_task_id="task_20260817T000003Z_cccccccc",
        )
        self.assertEqual(
            "agency_one",
            self.repository.getCreatorDetail(first["creator_id"])["record"]["agency_id"],
        )
        self.service.import_creator_from_extension(
            self.analysis(profile_url, "agency_two", "task_20260817T000004Z_dddddddd"),
            compensation_task_id="task_20260817T000004Z_dddddddd",
        )
        self.assertEqual(
            "agency_two",
            self.repository.getCreatorDetail(first["creator_id"])["record"]["agency_id"],
        )

    def test_unknown_agency_is_rejected_before_repository_write(self) -> None:
        analysis = self.analysis(
            "https://www.tiktok.com/@agency-unknown",
            "agency_missing",
            "task_20260817T000005Z_eeeeeeee",
        )
        with self.assertRaisesRegex(ValueError, "Agency 不存在"):
            self.service.import_creator_from_extension(
                analysis, compensation_task_id="task_20260817T000005Z_eeeeeeee"
            )
        self.assertEqual([], self.repository.getCreators(include_archived=True))


if __name__ == "__main__":
    unittest.main()
