from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))

import app_logging  # noqa: E402

with (
    mock.patch.object(app_logging, "log_event"),
    mock.patch.object(app_logging, "log_error"),
):
    import server  # noqa: E402

from adapters.task_manager_adapter import TaskManagerAdapter  # noqa: E402
from http_handlers import creator_handler  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from storage.connection import SQLiteConnectionFactory  # noqa: E402
from storage.schema import apply_schema_migrations  # noqa: E402
from storage.sqlite_creator_repository import SQLiteCreatorRepository  # noqa: E402
from storage.sqlite_workbook_store import SQLiteWorkbookStore  # noqa: E402
from test_support.runtime_sandbox import test_runtime_sandbox  # noqa: E402


class _Handler:
    def __init__(self) -> None:
        self.status = 0
        self.payload: dict = {}

    def _json(self, payload: dict, status: int = 200) -> None:
        self.status = status
        self.payload = payload

    def _error(self, message: str, status: int = 400) -> None:
        self.status = status
        self.payload = {"ok": False, "error": message}


class PluginV1Gate2BFieldProtectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_context = test_runtime_sandbox("plugin_v1_gate2b")
        self.runtime = self.runtime_context.__enter__()
        self.database = self.runtime.root / "data" / "kolconnect.db"
        self.factory = SQLiteConnectionFactory(self.database)
        with self.factory.read_connection() as connection:
            apply_schema_migrations(connection, migration_reference="plugin_v1_gate2b")
        self.repository = SQLiteCreatorRepository(SQLiteWorkbookStore(self.database))
        self.task_port = TaskManagerAdapter(lambda: self.runtime.root / "tasks")
        self.service = CreatorService(lambda: self.repository, lambda: self.task_port)
        self.patchers = [
            mock.patch.object(server, "get_creator_service", return_value=self.service),
            mock.patch.object(server, "get_task_port", return_value=self.task_port),
            mock.patch(
                "local_storage_lock.get_shared_storage_lock_path",
                return_value=self.runtime.root / "locks" / "shared_storage.lock",
            ),
            mock.patch("creator_repository.log_event"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.runtime_context.__exit__(None, None, None)

    @staticmethod
    def field(value, *, source: str = "dom", confidence: str = "high", missing_reason=None):
        return {
            "value": value,
            "source": source,
            "confidence": confidence,
            "missing_reason": missing_reason,
        }

    def payload(self, *, fields: dict | None = None, videos=None, video_analysis=None) -> dict:
        creator = {
            "creator_name": "Gate 2B Creator",
            "platform": "TikTok",
            "profile_url": "https://www.tiktok.com/@gate2bcreator",
            "followers": "100",
        }
        if fields is not None:
            creator["fields"] = fields
            for key, state in fields.items():
                if isinstance(state, dict) and "value" in state:
                    creator[key] = state["value"]
        return {
            "task_name": "Gate 2B protected update",
            "creator": creator,
            "videos": [] if videos is None else videos,
            "video_analysis": {} if video_analysis is None else video_analysis,
            "creator_insight": {},
        }

    def call(self, payload: dict, action: str) -> _Handler:
        handler = _Handler()
        context = {
            "services": {
                "creator": self.service,
                "agency": object(),
                "creator_delete_impact": object(),
                "creator_hard_delete": object(),
                "import_extension_capture": server.import_extension_capture,
                "record_diagnostic": mock.Mock(),
                "utc_now": lambda: "2026-10-05T00:00:00Z",
            },
            "config": {
                "legacy_cooperation_pattern": re.compile(r"$a"),
                "legacy_cooperation_read_only_message": "read only",
            },
            "logging": {"event": mock.Mock()},
        }
        creator_handler.handle(
            handler,
            {
                "method": "POST",
                "path": "/api/extension/import",
                "query": {},
                "get_payload": lambda: {**payload, "action": action},
            },
            context,
        )
        return handler

    def add_creator(self) -> dict:
        response = self.call(self.payload(), "ADD")
        self.assertEqual(201, response.status)
        return response.payload

    def row(self, table: str, where: str, value: object) -> dict:
        with self.factory.read_connection() as connection:
            result = connection.execute(
                f"SELECT * FROM {table} WHERE {where}=?", (value,)
            ).fetchone()
            return dict(result) if result else {}

    def task_count(self) -> int:
        task_root = self.runtime.root / "tasks"
        return sum(path.is_dir() for path in task_root.iterdir()) if task_root.exists() else 0

    def business_revision(self) -> int:
        return self.repository.store.business_revision()

    def snapshot_count(self) -> int:
        with self.factory.read_connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM creator_snapshots").fetchone()[0])

    def test_update_protects_creator_manual_fields_and_current_views(self) -> None:
        added = self.add_creator()
        creator_id = added["analysis_id"]
        account_uid = added["account_uid"]
        original_snapshot = self.row("creator_snapshots", "snapshot_id", added["snapshot_id"])
        original_account = self.row("creator_accounts", "account_uid", account_uid)
        with self.factory.write_transaction() as connection:
            connection.execute(
                """UPDATE creators SET name='Curated Name', followers=500, email='creator@old.test',
                   bio='curated bio', country='BR', language='pt-BR', content_category='Beauty',
                   agency_id='agency_manual', whatsapp='+5511999999999', status='cooperating',
                   cooperation_stage='contracted', owner='Alice', note='keep note', archived_at='keep',
                   last_contact_time='2026-01-01', next_follow_up_time='2026-01-10', quote=1200,
                   insight_level='high', current_contact_id='contact_current',
                   source_contact_id='contact_source' WHERE creator_id=?""",
                (creator_id,),
            )
            connection.execute(
                "UPDATE creator_accounts SET followers=500, account_email='account@old.test', "
                "attribution_status='manual', note='account note' WHERE account_uid=?",
                (account_uid,),
            )
            connection.execute(
                "INSERT INTO creator_tags(creator_id, position, tag) VALUES (?, 0, 'priority')",
                (creator_id,),
            )
            connection.execute(
                "INSERT INTO videos(creator_id, video_url, views) VALUES (?, 'https://video/old', 99)",
                (creator_id,),
            )
            connection.execute(
                "UPDATE insights SET average_views=111, median_views=101, stability=0.8, "
                "risks='[\"old\"]', recommendation='keep insight' WHERE creator_id=?",
                (creator_id,),
            )
        before_update_creator = self.row("creators", "creator_id", creator_id)
        before_update_account = self.row("creator_accounts", "account_uid", account_uid)

        fields = {
            "creator_name": self.field("Captured Name"),
            "followers": self.field(0),
            "email": self.field("creator@new.test"),
            "account_email": self.field("account@new.test"),
            "bio": self.field("captured bio"),
            "country": self.field("US"),
            "language": self.field("en"),
            "content_category": self.field("Gaming"),
            "agency_id": self.field("agency_other"),
            "whatsapp": self.field("+15551234567"),
            "username": self.field("newhandle"),
        }
        response = self.call(
            self.payload(
                fields=fields,
                videos=[{"video_url": "https://video/new", "views": 5}],
                video_analysis={"capture_status": "partial_success", "average_views": 5},
            ),
            "UPDATE",
        )
        self.assertEqual(200, response.status, response.payload)
        self.assertEqual(
            [
                {"code": "EMAIL_CONFLICT_PRESERVED", "field": "creator.email"},
                {"code": "EMAIL_CONFLICT_PRESERVED", "field": "creator_account.account_email"},
            ],
            response.payload["warnings"],
        )
        self.assertFalse(any("@" in str(item) for item in response.payload["warnings"]))
        self.assertNotIn(
            "@",
            str({
                "updated_fields": response.payload["updated_fields"],
                "preserved_fields": response.payload["preserved_fields"],
                "warnings": response.payload["warnings"],
            }),
        )
        self.assertEqual(
            {
                "creator.agency_id",
                "creator.bio",
                "creator.content_category",
                "creator.country",
                "creator.email",
                "creator.followers",
                "creator.insights",
                "creator.language",
                "creator.name",
                "creator.videos",
                "creator.whatsapp",
                "creator_account.account_email",
            },
            set(response.payload["preserved_fields"]),
        )

        creator = self.row("creators", "creator_id", creator_id)
        for field, expected in {
            "name": "Curated Name", "followers": 500, "email": "creator@old.test",
            "bio": "curated bio", "country": "BR", "language": "pt-BR",
            "content_category": "Beauty", "agency_id": "agency_manual",
            "whatsapp": "+5511999999999", "status": "cooperating",
            "cooperation_stage": "contracted", "owner": "Alice", "note": "keep note",
            "archived_at": "keep", "last_contact_time": "2026-01-01",
            "next_follow_up_time": "2026-01-10", "quote": 1200.0,
            "insight_level": "high",
            "current_contact_id": "contact_current", "source_contact_id": "contact_source",
        }.items():
            self.assertEqual(expected, creator[field], field)
        account = self.row("creator_accounts", "account_uid", account_uid)
        expected_updated = {
            "creator_account.followers",
            "creator_account.source_task_id",
            "creator_account.username",
        }
        for qualified, before_value, after_value in (
            ("creator.updated_at", before_update_creator["updated_at"], creator["updated_at"]),
            (
                "creator_account.last_scrape_time",
                before_update_account["last_scrape_time"],
                account["last_scrape_time"],
            ),
            (
                "creator_account.updated_at",
                before_update_account["updated_at"],
                account["updated_at"],
            ),
        ):
            if before_value != after_value:
                expected_updated.add(qualified)
        self.assertEqual(expected_updated, set(response.payload["updated_fields"]))
        self.assertEqual(
            len(response.payload["updated_fields"]),
            len(set(response.payload["updated_fields"])),
        )
        self.assertEqual(creator_id, account["creator_id"])
        self.assertEqual(0, account["followers"])
        self.assertEqual("newhandle", account["username"])
        self.assertEqual("account@old.test", account["account_email"])
        self.assertEqual("manual", account["attribution_status"])
        self.assertEqual("account note", account["note"])
        self.assertEqual(original_account["created_at"], account["created_at"])
        self.assertEqual("chrome_extension", account["data_source"])
        self.assertNotIn("creator_account.data_source", response.payload["updated_fields"])
        self.assertEqual(response.payload["task"]["id"], account["source_task_id"])
        self.assertEqual(account["last_scrape_time"], account["updated_at"])
        self.assertEqual("https://video/old", self.row("videos", "creator_id", creator_id)["video_url"])
        insight = self.row("insights", "creator_id", creator_id)
        self.assertEqual(111.0, insight["average_views"])
        self.assertEqual("keep insight", insight["recommendation"])
        with self.factory.read_connection() as connection:
            self.assertEqual(
                ["priority"],
                [row[0] for row in connection.execute(
                    "SELECT tag FROM creator_tags WHERE creator_id=? ORDER BY position", (creator_id,)
                )],
            )
            snapshot = dict(connection.execute(
                "SELECT * FROM creator_snapshots WHERE snapshot_id=?", (response.payload["snapshot_id"],)
            ).fetchone())
            snapshot_videos = connection.execute(
                "SELECT video_url FROM video_snapshots WHERE snapshot_id=?", (response.payload["snapshot_id"],)
            ).fetchall()
        self.assertEqual(0, snapshot["followers"])
        self.assertEqual(1, snapshot["video_count"])
        self.assertEqual(5.0, snapshot["average_views"])
        self.assertIsNone(snapshot["median_views"])
        self.assertIsNone(snapshot["insight_level"])
        self.assertEqual(["https://video/new"], [row[0] for row in snapshot_videos])
        self.assertEqual(
            original_snapshot,
            self.row("creator_snapshots", "snapshot_id", added["snapshot_id"]),
        )

    def test_operational_metadata_reports_only_persisted_state_changes(self) -> None:
        added = self.add_creator()
        creator_id = added["analysis_id"]
        account_uid = added["account_uid"]
        with self.factory.write_transaction() as connection:
            connection.execute(
                "UPDATE creator_accounts SET data_source='legacy_import', scrape_status='success' "
                "WHERE account_uid=?",
                (account_uid,),
            )

        source_change = self.call(self.payload(), "UPDATE")
        self.assertEqual(200, source_change.status)
        self.assertEqual(
            1,
            source_change.payload["updated_fields"].count("creator_account.data_source"),
        )
        self.assertNotIn("creator_account.scrape_status", source_change.payload["updated_fields"])
        self.assertEqual(
            "chrome_extension",
            self.row("creator_accounts", "account_uid", account_uid)["data_source"],
        )

        metadata_columns = {
            "creator.updated_at": ("creators", "updated_at"),
            "creator_account.last_scrape_time": ("creator_accounts", "last_scrape_time"),
            "creator_account.updated_at": ("creator_accounts", "updated_at"),
            "creator_account.source_task_id": ("creator_accounts", "source_task_id"),
            "creator_account.data_source": ("creator_accounts", "data_source"),
            "creator_account.scrape_status": ("creator_accounts", "scrape_status"),
        }

        def metadata_state() -> dict[str, object]:
            creator = self.row("creators", "creator_id", creator_id)
            account = self.row("creator_accounts", "account_uid", account_uid)
            rows = {"creators": creator, "creator_accounts": account}
            return {
                qualified: rows[table][column]
                for qualified, (table, column) in metadata_columns.items()
            }

        def direct_update(
            task_id: str,
            scrape_status: str,
            *,
            account_timestamp: str,
            creator_timestamp: str,
        ) -> dict:
            analysis = server._extension_analysis_payload(
                self.payload(),
                {"id": task_id},
                account_uid,
            )
            analysis["imported_at"] = account_timestamp
            analysis["scrape_status"] = scrape_status
            clock_globals = self.repository._creator_values.__globals__
            with mock.patch.dict(
                clock_globals,
                {"_utc_now": mock.Mock(return_value=creator_timestamp)},
            ):
                return self.repository.saveCreator(analysis, extension_action="UPDATE")

        same_timestamp = "2026-10-07T01:01:01Z"
        same_task_id = "task_20261007T010101Z_11111111"
        with self.factory.write_transaction() as connection:
            connection.execute(
                "UPDATE creators SET updated_at=? WHERE creator_id=?",
                (same_timestamp, creator_id),
            )
            connection.execute(
                "UPDATE creator_accounts SET last_scrape_time=?, updated_at=?, "
                "source_task_id=?, scrape_status='success' WHERE account_uid=?",
                (same_timestamp, same_timestamp, same_task_id, account_uid),
            )

        before_same = metadata_state()
        same_status = direct_update(
            same_task_id,
            "success",
            account_timestamp=same_timestamp,
            creator_timestamp=same_timestamp,
        )
        after_same = metadata_state()
        self.assertEqual(before_same, after_same)
        self.assertEqual([], same_status["updated_fields"])
        self.assertEqual(len(same_status["updated_fields"]), len(set(same_status["updated_fields"])))
        self.assertEqual(len(same_status["preserved_fields"]), len(set(same_status["preserved_fields"])))

        changed_timestamp = "2026-10-07T01:01:02Z"
        before_changed = metadata_state()
        changed_status = direct_update(
            "task_20261007T010102Z_22222222",
            "failed",
            account_timestamp=changed_timestamp,
            creator_timestamp=changed_timestamp,
        )
        after_changed = metadata_state()
        actual_changed = {
            qualified
            for qualified in metadata_columns
            if before_changed[qualified] != after_changed[qualified]
        }
        self.assertEqual(
            {
                "creator.updated_at",
                "creator_account.last_scrape_time",
                "creator_account.scrape_status",
                "creator_account.source_task_id",
                "creator_account.updated_at",
            },
            set(changed_status["updated_fields"]),
        )
        self.assertEqual(actual_changed, set(changed_status["updated_fields"]))
        for qualified in actual_changed:
            self.assertEqual(1, changed_status["updated_fields"].count(qualified))
        account = self.row("creator_accounts", "account_uid", account_uid)
        self.assertEqual("failed", account["scrape_status"])
        self.assertEqual("chrome_extension", account["data_source"])

    def test_missing_null_empty_marker_and_ambiguous_zero_preserve_followers(self) -> None:
        added = self.add_creator()
        creator_id = added["analysis_id"]
        account_uid = added["account_uid"]
        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE creators SET followers=321 WHERE creator_id=?", (creator_id,))
            connection.execute("UPDATE creator_accounts SET followers=321 WHERE account_uid=?", (account_uid,))

        cases = (
            None,
            {"followers": self.field(None)},
            {"followers": self.field("")},
            {"followers": self.field(None, confidence="missing", missing_reason="field_absent")},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                payload = self.payload(fields={} if fields is None else fields)
                if fields is None:
                    payload["creator"].pop("followers", None)
                response = self.call(payload, "UPDATE")
                self.assertEqual(200, response.status)
                self.assertNotIn("creator.followers", response.payload["updated_fields"])
                self.assertNotIn("creator_account.followers", response.payload["updated_fields"])
                self.assertEqual(321, self.row("creators", "creator_id", creator_id)["followers"])
                self.assertEqual(321, self.row("creator_accounts", "account_uid", account_uid)["followers"])

        legacy_zero = self.payload()
        legacy_zero["creator"]["followers"] = 0
        response = self.call(legacy_zero, "UPDATE")
        self.assertEqual(200, response.status)
        self.assertNotIn("creator.followers", response.payload["updated_fields"])
        self.assertNotIn("creator_account.followers", response.payload["updated_fields"])
        self.assertEqual(321, self.row("creator_accounts", "account_uid", account_uid)["followers"])

    def test_empty_values_fill_from_observed_capture_and_same_email_is_idempotent(self) -> None:
        added = self.add_creator()
        creator_id = added["analysis_id"]
        account_uid = added["account_uid"]
        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE creators SET followers=NULL, email=NULL, bio=NULL WHERE creator_id=?", (creator_id,))
            connection.execute("UPDATE creator_accounts SET followers=NULL, account_email=NULL WHERE account_uid=?", (account_uid,))
        fields = {
            "followers": self.field(42),
            "email": self.field("Creator@Example.test"),
            "account_email": self.field("Creator@Example.test"),
            "bio": self.field("observed bio"),
        }
        first = self.call(self.payload(fields=fields), "UPDATE")
        self.assertEqual(200, first.status)
        self.assertEqual([], first.payload["warnings"])
        creator = self.row("creators", "creator_id", creator_id)
        account = self.row("creator_accounts", "account_uid", account_uid)
        self.assertEqual(42, creator["followers"])
        self.assertEqual(42, account["followers"])
        self.assertEqual("Creator@Example.test", creator["email"])
        self.assertEqual("Creator@Example.test", account["account_email"])
        self.assertEqual("observed bio", creator["bio"])

        with self.factory.write_transaction() as connection:
            connection.execute("UPDATE creators SET followers=NULL WHERE creator_id=?", (creator_id,))
        zero_fields = dict(fields)
        zero_fields["followers"] = self.field(0)
        zero = self.call(self.payload(fields=zero_fields), "UPDATE")
        self.assertEqual(200, zero.status)
        self.assertIn("creator.followers", zero.payload["updated_fields"])
        self.assertIn("creator_account.followers", zero.payload["updated_fields"])
        self.assertEqual(0, self.row("creators", "creator_id", creator_id)["followers"])
        self.assertEqual(0, self.row("creator_accounts", "account_uid", account_uid)["followers"])

        fields["email"] = self.field(" creator@example.TEST ")
        fields["account_email"] = self.field("creator@example.test")
        second = self.call(self.payload(fields=fields), "UPDATE")
        self.assertEqual(200, second.status)
        self.assertEqual([], second.payload["warnings"])
        self.assertEqual("Creator@Example.test", self.row("creators", "creator_id", creator_id)["email"])

    def test_update_content_failure_states_preserve_current_video_and_insight(self) -> None:
        added = self.add_creator()
        creator_id = added["analysis_id"]
        with self.factory.write_transaction() as connection:
            connection.execute(
                "INSERT INTO videos(creator_id, video_url, views) VALUES (?, 'https://video/keep', 7)",
                (creator_id,),
            )
            connection.execute(
                "UPDATE insights SET average_views=77, recommendation='keep' WHERE creator_id=?",
                (creator_id,),
            )
        for status in ("failed", "cancelled", "timed_out", "unavailable", ""):
            with self.subTest(status=status):
                response = self.call(
                    self.payload(
                        videos=[{"video_url": "https://video/stale", "views": 999}]
                        if status == "failed"
                        else [],
                        video_analysis={"capture_status": status} if status else {},
                    ),
                    "UPDATE",
                )
                self.assertEqual(200, response.status)
                self.assertEqual("https://video/keep", self.row("videos", "creator_id", creator_id)["video_url"])
                self.assertEqual(77.0, self.row("insights", "creator_id", creator_id)["average_views"])
                snapshot = self.row("creator_snapshots", "snapshot_id", response.payload["snapshot_id"])
                self.assertIsNone(snapshot["video_count"])
                self.assertIsNone(snapshot["insight_level"])
                with self.factory.read_connection() as connection:
                    self.assertEqual(
                        0,
                        connection.execute(
                            "SELECT COUNT(*) FROM video_snapshots WHERE snapshot_id=?",
                            (response.payload["snapshot_id"],),
                        ).fetchone()[0],
                    )

        partial_empty = self.call(
            self.payload(video_analysis={"capture_status": "partial_success"}),
            "UPDATE",
        )
        self.assertEqual(200, partial_empty.status)
        self.assertIsNone(
            self.row("creator_snapshots", "snapshot_id", partial_empty.payload["snapshot_id"])["video_count"]
        )

    def test_add_initializes_observed_content_but_missing_snapshot_values_stay_missing(self) -> None:
        observed = self.call(
            self.payload(
                videos=[{"video_url": "https://video/observed", "views": 0}],
                video_analysis={"capture_status": "success", "average_views": 0},
            ),
            "ADD",
        )
        self.assertEqual(201, observed.status)
        self.assertEqual("https://video/observed", self.row("videos", "creator_id", observed.payload["analysis_id"])["video_url"])
        snapshot = self.row("creator_snapshots", "snapshot_id", observed.payload["snapshot_id"])
        self.assertEqual(1, snapshot["video_count"])
        self.assertEqual(0.0, snapshot["average_views"])
        self.assertIsNone(snapshot["insight_level"])

    def test_success_warning_and_failure_cardinality_are_exact(self) -> None:
        before_add = (self.task_count(), self.business_revision(), self.snapshot_count())
        added = self.add_creator()
        after_add = (self.task_count(), self.business_revision(), self.snapshot_count())
        self.assertEqual((1, 1, 1), tuple(after - before for before, after in zip(before_add, after_add)))

        before_update = (self.task_count(), self.business_revision(), self.snapshot_count())
        update = self.call(
            self.payload(fields={"username": self.field("cardinality-update")}),
            "UPDATE",
        )
        self.assertEqual(200, update.status)
        after_update = (self.task_count(), self.business_revision(), self.snapshot_count())
        self.assertEqual((1, 1, 1), tuple(after - before for before, after in zip(before_update, after_update)))

        with self.factory.write_transaction() as connection:
            connection.execute(
                "UPDATE creators SET email='creator@existing.test' WHERE creator_id=?",
                (added["analysis_id"],),
            )
            connection.execute(
                "UPDATE creator_accounts SET account_email='account@existing.test' WHERE account_uid=?",
                (added["account_uid"],),
            )
        before_warning = (self.task_count(), self.business_revision(), self.snapshot_count())
        warning = self.call(
            self.payload(fields={
                "email": self.field("creator@captured.test"),
                "account_email": self.field("account@captured.test"),
            }),
            "UPDATE",
        )
        self.assertEqual(200, warning.status)
        self.assertEqual(2, len(warning.payload["warnings"]))
        self.assertNotIn("creator.email", warning.payload["updated_fields"])
        self.assertNotIn("creator_account.account_email", warning.payload["updated_fields"])
        after_warning = (self.task_count(), self.business_revision(), self.snapshot_count())
        self.assertEqual((1, 1, 1), tuple(after - before for before, after in zip(before_warning, after_warning)))

        before_failure = (self.task_count(), self.business_revision(), self.snapshot_count())
        duplicate = self.call(self.payload(), "ADD")
        self.assertEqual(409, duplicate.status)
        after_failure = (self.task_count(), self.business_revision(), self.snapshot_count())
        self.assertEqual((0, 0, 0), tuple(after - before for before, after in zip(before_failure, after_failure)))

        before_invalid = (self.task_count(), self.business_revision(), self.snapshot_count())
        invalid = self.call(self.payload(), "UPSERT")
        self.assertEqual(422, invalid.status)
        after_invalid = (self.task_count(), self.business_revision(), self.snapshot_count())
        self.assertEqual((0, 0, 0), tuple(after - before for before, after in zip(before_invalid, after_invalid)))

    def test_rejected_update_adds_no_snapshot_task_or_revision(self) -> None:
        before = (self.task_count(), self.business_revision(), self.snapshot_count())
        response = self.call(self.payload(), "UPDATE")
        self.assertEqual(404, response.status)
        after = (self.task_count(), self.business_revision(), self.snapshot_count())
        self.assertEqual((0, 0, 0), tuple(end - start for start, end in zip(before, after)))


if __name__ == "__main__":
    unittest.main()
