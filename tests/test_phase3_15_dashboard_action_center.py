from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from services.campaign_execution_service import CampaignExecutionService
from services.dashboard_response_cache import DashboardResponseCache
from repository_factory import RepositoryFactory
from storage.sqlite_workbook_store import SQLiteWorkbookStore
from test_support.runtime_sandbox import test_runtime_sandbox


class ActionCenterA1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.sandbox = test_runtime_sandbox("action_center_a1")
        runtime = self.sandbox.__enter__()
        self.store = SQLiteWorkbookStore.initialize_empty(runtime.root / "action-center.db")
        self.today = date(2026, 10, 10)
        self.service = CampaignExecutionService(
            lambda: self.store.factory, today_provider=lambda: self.today
        )
        self.cache = DashboardResponseCache(local_date_provider=lambda: self.today)
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO products(product_id,name) VALUES ('product','Product')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name,status) VALUES ('campaign','product','Campaign','running')")
            connection.execute("INSERT INTO creators(creator_id,name) VALUES ('creator','Creator')")
            connection.execute("INSERT INTO campaign_creators(id,campaign_id,creator_id,stage) VALUES ('base','campaign','creator','executing')")

    def tearDown(self) -> None:
        self.sandbox.__exit__(None, None, None)

    def add_relation(self, relation_id: str, *, stage: str = "executing", action: str | None = None,
                     due: str | None = None, decision: int = 0, archived: str | None = None,
                     campaign: str = "campaign", creator: str = "creator") -> None:
        with self.store.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO campaign_creators(id,campaign_id,creator_id,stage,next_action,due_date,need_my_decision,archived_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (relation_id, campaign, creator, stage, action, due, decision, archived),
            )

    def items(self) -> list[dict]:
        return self.service.action_center()["items"]

    def cached_items(self) -> list[dict]:
        return self.cache.get_response(
            self.store, lambda: {"action_center": self.service.action_center()}
        )["action_center"]["items"]

    def test_due_actions_require_text_and_today_or_earlier(self) -> None:
        self.add_relation("overdue", action="Send brief", due="2026-10-08")
        self.add_relation("today", action="Approve quote", due="2026-10-10")
        self.add_relation("future", action="Future task", due="2026-10-11")
        self.add_relation("blank", action="  ", due="2026-10-09")
        self.add_relation("no-date", action="No date")
        self.add_relation("invalid-date", action="Bad legacy date", due="not-a-date")
        self.assertEqual(["overdue", "today"], [item["campaign_creator_id"] for item in self.items()])
        self.assertEqual(["overdue", "due_today"], [item["priority"] for item in self.items()])

    def test_decision_without_due_and_due_decision_deduplicate(self) -> None:
        self.add_relation("decision", decision=1)
        self.add_relation("both", action="Review proposal", due="2026-10-10", decision=1)
        self.add_relation("undated-decision", action="Schedule proposal review", decision=1)
        self.add_relation("future-decision", action="Review later", due="2026-10-11", decision=1)
        rows = {item["campaign_creator_id"]: item for item in self.items()}
        self.assertEqual({"decision", "both"}, set(rows))
        self.assertEqual("need_my_decision", rows["decision"]["type"])
        self.assertIsNone(rows["decision"]["due_date"])
        self.assertEqual("due_action", rows["both"]["type"])
        self.assertTrue(rows["both"]["need_my_decision"])

    def test_due_action_and_content_review_remain_independent(self) -> None:
        self.add_relation("both", action="Review proposal", due="2026-10-10", decision=1)
        submission = self.service.create_submission("both", {"content_type": "script"})
        rows = self.items()
        self.assertEqual(["due_action", "content_review"], [row["type"] for row in rows])
        self.assertEqual(submission["submission_id"], rows[1]["submission_id"])

    def test_terminal_relations_are_excluded_including_historical_cancelled(self) -> None:
        for stage in ("completed", "rejected", "cancelled"):
            self.add_relation(stage, stage=stage, action="Old task", due="2026-10-01", decision=1)
        self.assertEqual([], self.items())

    def test_relation_creator_campaign_archive_and_completed_campaign_are_excluded(self) -> None:
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name,archived_at) VALUES ('archived-creator','Old','2026-01-01')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name,status,archived_at) VALUES ('archived-campaign','product','Old','running','2026-01-01')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name,status) VALUES ('completed-campaign','product','Done','completed')")
        self.add_relation("archived-relation", action="Old", due="2026-10-01", archived="2026-01-01")
        self.add_relation("archived-creator-relation", action="Old", due="2026-10-01", creator="archived-creator")
        self.add_relation("archived-campaign-relation", decision=1, campaign="archived-campaign")
        self.add_relation("completed-campaign-relation", decision=1, campaign="completed-campaign")
        self.assertEqual([], self.items())

    def test_pending_submissions_are_distinct_and_nonpending_excluded(self) -> None:
        first = self.service.create_submission("base", {"content_type": "script"})
        second = self.service.create_submission("base", {"content_type": "copy"})
        third = self.service.create_submission("base", {"content_type": "other"})
        self.service.review_submission(third["submission_id"], {"review_status": "approved"})
        rows = self.items()
        self.assertEqual({first["submission_id"], second["submission_id"]}, {row["submission_id"] for row in rows})
        self.assertTrue(all(row["type"] == "content_review" for row in rows))
        self.assertTrue(all(row["campaign_creator_id"] == "base" for row in rows))

    def test_pending_review_obeys_same_terminal_and_archive_filters(self) -> None:
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO creators(creator_id,name,archived_at) VALUES ('old-creator','Old','2026-01-01')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name,status,archived_at) VALUES ('old-campaign','product','Old','running','2026-01-01')")
            connection.execute("INSERT INTO campaigns(campaign_id,product_id,name,status) VALUES ('done-campaign','product','Done','completed')")
        cases = [
            ("terminal", {"stage": "completed"}),
            ("rejected", {"stage": "rejected"}),
            ("cancelled", {"stage": "cancelled"}),
            ("archived", {"archived": "2026-01-01"}),
            ("old-creator", {"creator": "old-creator"}),
            ("old-campaign", {"campaign": "old-campaign"}),
            ("done-campaign", {"campaign": "done-campaign"}),
        ]
        for relation_id, options in cases:
            self.add_relation(relation_id, **options)
            self.service.create_submission(relation_id, {"content_type": "script"})
        self.assertEqual([], self.items())

    def test_global_order_is_deterministic_and_submission_identity_is_stable(self) -> None:
        self.add_relation("late-overdue", action="A", due="2026-10-09")
        self.add_relation("early-overdue", action="B", due="2026-10-01")
        self.add_relation("today", action="C", due="2026-10-10")
        self.add_relation("decision", decision=1)
        first = self.service.create_submission("base", {"content_type": "script"})
        second = self.service.create_submission("base", {"content_type": "copy"})
        expected = ["early-overdue", "late-overdue", "today", "decision"]
        rows = self.items()
        self.assertEqual(expected, [row["campaign_creator_id"] for row in rows[:4]])
        self.assertEqual(sorted([first["submission_id"], second["submission_id"]]),
                         [row["submission_id"] for row in rows[4:]])
        self.assertEqual(rows, self.items())

    def test_cache_rebuilds_after_execution_and_review_writes(self) -> None:
        self.assertEqual([], self.cached_items())
        self.service.update_execution("base", {"next_action": "Send draft", "due_date": "2026-10-10"})
        self.assertEqual(["due_action"], [row["type"] for row in self.cached_items()])
        self.service.update_execution("base", {"need_my_decision": True})
        self.assertTrue(self.cached_items()[0]["need_my_decision"])
        submission = self.service.create_submission("base", {"content_type": "script"})
        self.assertEqual(2, len(self.cached_items()))
        self.service.review_submission(submission["submission_id"], {"review_status": "approved"})
        self.assertEqual(["due_action"], [row["type"] for row in self.cached_items()])
        self.service.update_execution("base", {"next_action": "", "due_date": None, "need_my_decision": False})
        self.assertEqual([], self.cached_items())

    def test_local_day_rollover_rebuilds_cached_projection(self) -> None:
        self.add_relation("tomorrow", action="Call", due="2026-10-11")
        self.assertEqual([], self.cached_items())
        self.today = date(2026, 10, 11)
        self.assertEqual(["tomorrow"], [row["campaign_creator_id"] for row in self.cached_items()])

    def test_existing_dashboard_response_refreshes_after_execution_and_review(self) -> None:
        import server

        factory = RepositoryFactory(self.store)
        cache = DashboardResponseCache(local_date_provider=lambda: self.today)
        with (
            mock.patch.object(server, "get_creator_repository", return_value=factory.creator()),
            mock.patch.object(server, "get_active_repository_factory", return_value=factory),
            mock.patch.object(server, "DASHBOARD_RESPONSE_CACHE", cache),
        ):
            initial = server.get_dashboard_data()
            self.assertEqual([], initial["action_center"]["items"])
            self.assertIn("pending_contact", initial["action_items"])
            self.service.update_execution("base", {"next_action": "Review", "due_date": "2026-10-10"})
            self.assertEqual("due_action", server.get_dashboard_data()["action_center"]["items"][0]["type"])
            submission = self.service.create_submission("base", {"content_type": "script"})
            self.assertEqual(2, len(server.get_dashboard_data()["action_center"]["items"]))
            self.service.review_submission(submission["submission_id"], {"review_status": "approved"})
            self.assertEqual(1, len(server.get_dashboard_data()["action_center"]["items"]))

    def test_mail_facts_do_not_create_action_center_items(self) -> None:
        with self.store.factory.write_transaction() as connection:
            connection.execute("INSERT INTO mail_accounts(mail_account_id,identity_key,created_at) VALUES ('mail','mail-key','2026-10-01')")
            connection.execute(
                "INSERT INTO mail_messages(mail_message_id,mail_account_id,direction,observed_at,match_status,matched_creator_id) "
                "VALUES ('message','mail','inbound','2026-10-10','matched','creator')"
            )
        self.assertEqual([], self.items())


if __name__ == "__main__":
    unittest.main()
