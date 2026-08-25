from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
sys.path.insert(0, str(APP_DIR))

import creator_repository
import server


def append_mapping(sheet, values: dict) -> None:
    headers = [str(cell.value or "") for cell in sheet[1]]
    sheet.append([values.get(header, "") for header in headers])


class LegacyReadGuardRepository(creator_repository.CreatorRepository):
    def getCooperations(self) -> list[dict]:
        raise AssertionError("Dashboard must not read Legacy Cooperations")


class DashboardCampaignCreatorMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workbook_path = Path(self.temp_dir.name) / "Creator_Library.xlsx"
        creator_repository.CreatorRepository(self.workbook_path).getCreators()
        self._seed_workbook()

        self.patchers = [
            mock.patch.object(
                server,
                "get_creator_repository",
                side_effect=lambda: LegacyReadGuardRepository(self.workbook_path),
            ),
            mock.patch.object(server, "log_event"),
            mock.patch.object(server, "log_error"),
            mock.patch.object(server, "_record_last_error"),
        ]
        for patcher in self.patchers:
            patcher.start()

        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def _seed_workbook(self) -> None:
        workbook = load_workbook(self.workbook_path)
        try:
            for suffix in ("a", "b", "c", "d", "e"):
                creator_id = f"creator_{suffix}"
                account_id = f"account_{suffix}"
                append_mapping(workbook["Creators"], {
                    "creator_id": creator_id,
                    "name": f"Creator {suffix.upper()}",
                    "platform": "TikTok",
                    "profile_url": f"https://www.tiktok.com/@creator-{suffix}",
                    "status": "discovered",
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-01T00:00:00Z",
                })
                append_mapping(workbook["CreatorAccounts"], {
                    "account_id": account_id,
                    "creator_id": creator_id,
                    "account_uid": f"tiktok|creator-{suffix}",
                    "platform": "TikTok",
                    "username": f"creator-{suffix}",
                    "profile_url": f"https://www.tiktok.com/@creator-{suffix}",
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-01T00:00:00Z",
                })

            append_mapping(workbook["Products"], {
                "product_id": "product_one",
                "name": "Product One",
                "company_name": "Studio",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-01T00:00:00Z",
            })
            for index in range(1, 6):
                append_mapping(workbook["Campaigns"], {
                    "campaign_id": f"campaign_{index}",
                    "product_id": "product_one",
                    "name": f"Campaign {index}",
                    "status": "completed" if index >= 3 else "running",
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-01T00:00:00Z",
                })

            relations = [
                {
                    "id": "relation_pending",
                    "campaign_id": "campaign_1",
                    "creator_id": "creator_a",
                    "account_id": "account_a",
                    "stage": "pending_contact",
                },
                {
                    "id": "relation_agreed",
                    "campaign_id": "campaign_1",
                    "creator_id": "creator_b",
                    "account_id": "account_b",
                    "stage": "agreed",
                    "cost": 100,
                    "views": 1000,
                },
                {
                    "id": "relation_executing",
                    "campaign_id": "campaign_2",
                    "creator_id": "creator_a",
                    "account_id": "account_a",
                    "stage": "executing",
                    "cost": 200,
                    "views": 2000,
                },
                {
                    "id": "relation_completed_a",
                    "campaign_id": "campaign_3",
                    "creator_id": "creator_a",
                    "account_id": "account_a",
                    "stage": "completed",
                    "cost": 100,
                    "views": 5000,
                    "roi": 2,
                    "performance_note": "",
                },
                {
                    "id": "relation_completed_b",
                    "campaign_id": "campaign_4",
                    "creator_id": "creator_b",
                    "account_id": "account_b",
                    "stage": "completed",
                    "cost": 300,
                    "views": 4000,
                    "roi": 4,
                    "performance_note": "Reviewed",
                },
                {
                    "id": "relation_bad_roi",
                    "campaign_id": "campaign_5",
                    "creator_id": "creator_c",
                    "account_id": "account_c",
                    "stage": "completed",
                    "cost": 500,
                    "views": 3000,
                    "roi": "not-a-number",
                    "performance_note": "Reviewed",
                },
                {
                    "id": "relation_null_roi",
                    "campaign_id": "campaign_5",
                    "creator_id": "creator_d",
                    "account_id": "account_d",
                    "stage": "completed",
                    "cost": 200,
                    "views": 1000,
                    "roi": "",
                    "performance_note": "Reviewed",
                },
                {
                    "id": "relation_zero_cost",
                    "campaign_id": "campaign_4",
                    "creator_id": "creator_e",
                    "account_id": "account_e",
                    "stage": "completed",
                    "cost": 0,
                    "views": 500,
                    "roi": 99,
                    "performance_note": "Reviewed",
                },
                {
                    "id": "relation_rejected",
                    "campaign_id": "campaign_2",
                    "creator_id": "creator_c",
                    "account_id": "account_c",
                    "stage": "rejected",
                    "cost": 999,
                    "views": 99999,
                    "roi": 99,
                    "performance_note": "Rejected",
                },
                {
                    "id": "relation_archived",
                    "campaign_id": "campaign_3",
                    "creator_id": "creator_d",
                    "account_id": "account_d",
                    "stage": "completed",
                    "cost": 999,
                    "views": 99999,
                    "roi": 99,
                    "performance_note": "Archived",
                    "archived_at": "2026-08-02T00:00:00Z",
                },
            ]
            for relation in relations:
                append_mapping(workbook["CampaignCreators"], {
                    **relation,
                    "created_at": "2026-08-01T00:00:00Z",
                    "updated_at": "2026-08-01T00:00:00Z",
                })

            append_mapping(workbook["Cooperations"], {
                "cooperation_id": "legacy_should_be_ignored",
                "creator_id": "creator_a",
                "campaign": "Legacy Campaign",
                "price": 999999,
                "total_views": 999999,
                "roi": 999,
                "created_at": "2026-08-01T00:00:00Z",
            })
            workbook.save(self.workbook_path)
        finally:
            workbook.close()

    def get_dashboard(self) -> tuple[int, dict]:
        request = urllib.request.Request(self.base_url + "/api/dashboard", method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_dashboard_uses_campaign_creators_and_preserves_contract(self) -> None:
        status, payload = self.get_dashboard()

        self.assertEqual(200, status)
        self.assertEqual(
            {
                "ok",
                "overview",
                "creator_health",
                "health_summary",
                "cooperation_performance",
                "action_items",
                "platform_distribution",
                "creator_status_distribution",
                "creator_growth_trend",
                "trace_id",
            },
            set(payload),
        )
        self.assertRegex(payload["trace_id"], r"^trace_[0-9a-f]{32}$")
        overview = payload["overview"]
        health_summary = payload["health_summary"]
        performance = payload["cooperation_performance"]
        actions = payload["action_items"]

        self.assertEqual(1, overview["discovered_count"])
        self.assertEqual(2, overview["cooperating_count"])
        self.assertEqual(1400, overview["cooperation_spend"])
        self.assertAlmostEqual(3.5, overview["average_roi"])

        self.assertEqual(5, performance["total_campaigns"])
        self.assertEqual(1400, performance["total_cost"])
        self.assertEqual(16500, performance["total_views"])
        self.assertAlmostEqual(3.5, performance["average_roi"])
        self.assertEqual(
            ["creator_a", "creator_b", "creator_c", "creator_d", "creator_e"],
            [item["creator_id"] for item in performance["top_creators"]],
        )

        self.assertEqual(["creator_a"], [item["creator_id"] for item in actions["pending_contact"]])
        self.assertEqual(1, len(actions["incomplete_cooperations"]))
        self.assertEqual(
            "relation_completed_a",
            actions["incomplete_cooperations"][0]["cooperation_id"],
        )
        self.assertEqual(
            "missing_performance_note",
            actions["incomplete_cooperations"][0]["reason"],
        )

        for key in ("total_creators", "new_creators_7d", "discovered_count", "cooperating_count", "cooperation_spend", "average_roi"):
            self.assertIsInstance(overview[key], (int, float))
        for key in ("total_campaigns", "total_cost", "total_views", "average_roi"):
            self.assertIsInstance(performance[key], (int, float))
        self.assertEqual([{"platform": "TikTok", "count": 5}], payload["platform_distribution"])
        self.assertEqual([{"status": "discovered", "count": 5}], payload["creator_status_distribution"])
        self.assertEqual(30, len(payload["creator_growth_trend"]))
        self.assertEqual(
            health_summary["total"],
            health_summary["healthy"] + health_summary["warning"] + health_summary["critical"],
        )


if __name__ == "__main__":
    unittest.main()
