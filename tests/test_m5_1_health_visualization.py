from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from dashboard_service import DashboardService  # noqa: E402


class _Repository:
    def __init__(self, creators: list[dict]) -> None:
        self.creators = creators

    def get_creators(self):
        return self.creators

    def get_creator_health_records(self):
        return self.creators


def creator(creator_id: str, *, stale: bool = False, decline: bool = False) -> dict:
    changes = {
        "followers": {
            "status": "available",
            "direction": "decline" if decline else "growth",
            "delta": 1,
        }
    } if decline else {}
    return {
        "creator_id": creator_id,
        "creator_name": creator_id,
        "trend": {
            "freshness": {"status": "stale" if stale else "fresh", "days": 1},
            "changes": changes,
        },
    }


class HealthVisualizationTests(unittest.TestCase):
    def summary(self, creators: list[dict]) -> dict:
        return DashboardService(_Repository(creators)).getHealthSummary()

    def test_normal_creator_health_calculation(self):
        summary = self.summary([
            creator("healthy_one"),
            creator("healthy_two"),
            creator("healthy_three"),
            creator("falling", decline=True),
            creator("expired", stale=True),
        ])
        self.assertEqual(
            {"score": 60, "healthy": 3, "warning": 1, "critical": 1, "total": 5},
            summary,
        )

    def test_falling_and_expired_overlap_is_counted_once_as_critical(self):
        summary = self.summary([
            creator("expired_one", stale=True),
            creator("overlap", stale=True, decline=True), creator("falling_one", decline=True),
            creator("falling_two", decline=True),
            creator("healthy_one"), creator("healthy_two"), creator("healthy_three"),
            creator("healthy_four"), creator("healthy_five"), creator("healthy_six"),
        ])
        self.assertEqual(2, summary["critical"])
        self.assertEqual(2, summary["warning"])
        self.assertEqual(6, summary["healthy"])
        self.assertEqual(10, summary["total"])
        self.assertEqual(60, summary["score"])

    def test_empty_active_creator_set_has_no_score(self):
        self.assertEqual(
            {"score": None, "healthy": 0, "warning": 0, "critical": 0, "total": 0},
            self.summary([]),
        )

    def test_score_is_rounded_from_healthy_share(self):
        summary = self.summary([
            creator("healthy_one"), creator("healthy_two"), creator("falling", decline=True),
        ])
        self.assertEqual(67, summary["score"])

    def test_existing_creator_health_contract_is_preserved(self):
        service = DashboardService(_Repository([creator("expired", stale=True)]))
        health = service.getCreatorHealth()
        self.assertEqual(
            {"rising_creators", "falling_creators", "expired_creators"},
            set(health),
        )
        self.assertEqual("expired", health["expired_creators"][0]["creator_id"])
        self.assertEqual(1, service.getHealthSummary()["critical"])


if __name__ == "__main__":
    unittest.main()
