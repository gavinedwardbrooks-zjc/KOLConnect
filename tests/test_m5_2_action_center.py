from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from dashboard_service import DashboardService  # noqa: E402


class _DashboardRepository:
    def __init__(self, creators, relations):
        self.creators = creators
        self.relations = relations

    def get_creators(self):
        return self.creators

    def get_creator_health_records(self):
        return self.creators

    def get_campaign_creator_records(self, _creators):
        return self.relations


def creator(creator_id: str, *, archived: bool = False, freshness=None):
    return {
        "creator_id": creator_id,
        "creator_name": creator_id,
        "platform": "TikTok",
        "archived_at": "2026-08-01T00:00:00Z" if archived else "",
        "trend": {"freshness": freshness or {"status": "fresh", "days": 0}},
    }


def relation(
    record_id: str,
    creator_id: str,
    *,
    stage: str,
    created_at: str,
    campaign_id: str = "campaign",
    note: str = "",
    archived: bool = False,
    campaign_archived: bool = False,
):
    return {
        "id": record_id,
        "creator_id": creator_id,
        "creator_name": creator_id,
        "platform": "TikTok",
        "stage": stage,
        "created_at": created_at,
        "campaign_id": campaign_id,
        "campaign": campaign_id,
        "performance_note": note,
        "archived_at": "2026-08-01T00:00:00Z" if archived else "",
        "campaign_archived_at": "2026-08-01T00:00:00Z" if campaign_archived else "",
    }


class ActionCenterTests(unittest.TestCase):
    def actions(self, creators, relations):
        return DashboardService(_DashboardRepository(creators, relations)).getActionItems()

    def test_archived_creators_never_appear_in_any_action_category(self):
        actions = self.actions(
            [
                creator("active", freshness={"status": "stale", "days": 3}),
                creator("archived", archived=True, freshness={"status": "stale", "days": 99}),
            ],
            [
                relation("pending-active", "active", stage="pending_contact", created_at="2026-08-02T00:00:00Z"),
                relation("pending-archived", "archived", stage="pending_contact", created_at="2026-08-01T00:00:00Z"),
                relation("review-archived", "archived", stage="completed", created_at="2026-08-01T00:00:00Z"),
            ],
        )
        self.assertEqual(["active"], [item["creator_id"] for item in actions["expired_creators"]])
        self.assertEqual(["active"], [item["creator_id"] for item in actions["pending_contact"]])
        self.assertEqual([], actions["incomplete_cooperations"])

    def test_rules_exclusions_campaign_id_and_stable_caps(self):
        creators = [creator(f"creator_{index}") for index in range(7)]
        creators[0]["trend"] = {"freshness": {"status": "stale", "days": 2}}
        creators[1]["trend"] = {"freshness": {"status": "stale", "days": 9}}
        relations = [
            relation(f"pending_{index}", f"creator_{index}", stage="pending_contact", created_at=f"2026-08-0{7 - index}T00:00:00Z")
            for index in range(7)
        ] + [
            relation("review-old", "creator_0", stage="completed", created_at="2026-08-01T00:00:00Z", campaign_id="campaign_review"),
            relation("review-noted", "creator_1", stage="completed", created_at="2026-08-01T00:00:00Z", note="done"),
            relation("review-campaign-archived", "creator_2", stage="completed", created_at="2026-08-01T00:00:00Z", campaign_archived=True),
            relation("review-relation-archived", "creator_3", stage="completed", created_at="2026-08-01T00:00:00Z", archived=True),
        ]
        actions = self.actions(creators, relations)
        self.assertEqual(5, len(actions["pending_contact"]))
        self.assertEqual("creator_6", actions["pending_contact"][0]["creator_id"])
        self.assertEqual(["creator_1", "creator_0"], [item["creator_id"] for item in actions["expired_creators"]])
        self.assertEqual(["review-old"], [item["cooperation_id"] for item in actions["incomplete_cooperations"]])
        self.assertEqual("campaign_review", actions["incomplete_cooperations"][0]["campaign_id"])
        self.assertLessEqual(sum(len(items) for items in actions.values()), 15)

    def test_existing_action_item_fields_are_preserved(self):
        actions = self.actions(
            [creator("creator", freshness={"status": "stale", "days": 1})],
            [relation("pending", "creator", stage="pending_contact", created_at="2026-08-01T00:00:00Z")],
        )
        self.assertEqual(
            {"expired_creators", "pending_contact", "incomplete_cooperations"},
            set(actions),
        )
        self.assertIn("creator_id", actions["expired_creators"][0])
        self.assertIn("status", actions["pending_contact"][0])

    def test_legacy_minimal_records_without_optional_action_fields_are_safe(self):
        actions = self.actions(
            [{
                "creator_id": "legacy",
                "creator_name": "Legacy Creator",
                "platform": "TikTok",
                "trend": {"freshness": {"status": "stale", "days": None}},
            }],
            [
                {
                    "id": "legacy-pending",
                    "creator_id": "legacy",
                    "creator_name": "Legacy Creator",
                    "platform": "TikTok",
                    "stage": "pending_contact",
                    "created_at": None,
                },
                {
                    "id": "legacy-review",
                    "creator_id": "legacy",
                    "creator_name": "Legacy Creator",
                    "platform": "TikTok",
                    "stage": "completed",
                    "created_at": "not-a-timestamp",
                    "performance_note": None,
                },
            ],
        )
        self.assertEqual(["legacy"], [item["creator_id"] for item in actions["expired_creators"]])
        self.assertEqual(["legacy"], [item["creator_id"] for item in actions["pending_contact"]])
        self.assertEqual("", actions["incomplete_cooperations"][0]["campaign_id"])
