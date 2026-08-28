from __future__ import annotations

import contextlib
import os
import shutil
import sys
import threading
import time
import unittest
import uuid
from datetime import date
from pathlib import Path
from unittest import mock

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT / "tests"))

from http_handlers import campaign_handler  # noqa: E402
from creator_repository import CreatorRepository  # noqa: E402
from services.creator_hard_delete_service import CreatorHardDeleteService  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402
from services.dashboard_response_cache import (  # noqa: E402
    DashboardResponseCache,
    DashboardResponseCacheUnstableBuild,
)
from test_support.runtime_sandbox import test_artifact_path  # noqa: E402


class DashboardResponseCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = test_artifact_path("m5_1_1_cache_test", uuid.uuid4().hex)
        self.root.mkdir()
        self.workbook_path = self.root / "Creator_Library.xlsx"
        self.workbook_path.write_bytes(b"initial")
        self.today = date(2026, 8, 21)
        self.cache = DashboardResponseCache(lambda: self.today)
        self.lock_patcher = mock.patch(
            "services.dashboard_response_cache.shared_storage_lock",
            side_effect=lambda **_kwargs: contextlib.nullcontext(),
        )
        self.lock_patcher.start()

    def tearDown(self) -> None:
        self.lock_patcher.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def test_first_request_builds_once_and_second_request_hits(self) -> None:
        loader = mock.Mock(return_value={"overview": {"creator_count": 1}})
        self.assertEqual(1, self.cache.get_response(self.workbook_path, loader)["overview"]["creator_count"])
        self.assertEqual(1, self.cache.get_response(self.workbook_path, loader)["overview"]["creator_count"])
        self.assertEqual(1, loader.call_count)

    def test_returned_payload_cannot_pollute_cached_snapshot(self) -> None:
        first = self.cache.get_response(
            self.workbook_path, lambda: {"overview": {"items": ["safe"]}}
        )
        first["overview"]["items"].append("polluted")
        second = self.cache.get_response(self.workbook_path, lambda: self.fail("cache miss"))
        self.assertEqual(["safe"], second["overview"]["items"])

    def test_external_mtime_or_size_change_rebuilds(self) -> None:
        loader = mock.Mock(side_effect=[{"version": 1}, {"version": 2}])
        self.assertEqual(1, self.cache.get_response(self.workbook_path, loader)["version"])
        previous = self.workbook_path.stat()
        self.workbook_path.write_bytes(b"changed-size")
        os.utime(
            self.workbook_path,
            ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000),
        )
        self.assertEqual(2, self.cache.get_response(self.workbook_path, loader)["version"])
        self.assertEqual(2, loader.call_count)

    def test_utc_date_change_rebuilds(self) -> None:
        loader = mock.Mock(side_effect=[{"date": "first"}, {"date": "second"}])
        self.cache.get_response(self.workbook_path, loader)
        self.today = date(2026, 8, 22)
        self.assertEqual("second", self.cache.get_response(self.workbook_path, loader)["date"])
        self.assertEqual(2, loader.call_count)

    def test_concurrent_first_requests_build_once(self) -> None:
        readers = 6
        barrier = threading.Barrier(readers)
        count_lock = threading.Lock()
        build_count = 0
        results: list[dict] = []
        errors: list[BaseException] = []

        def loader() -> dict:
            nonlocal build_count
            with count_lock:
                build_count += 1
            time.sleep(0.03)
            return {"overview": {"creator_count": 3}}

        def read() -> None:
            try:
                barrier.wait(timeout=2)
                results.append(self.cache.get_response(self.workbook_path, loader))
            except BaseException as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=read) for _ in range(readers)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual([], errors)
        self.assertEqual(readers, len(results))
        self.assertEqual(1, build_count)

    def test_build_time_workbook_change_is_not_cached(self) -> None:
        self.cache.get_response(self.workbook_path, lambda: {"version": "stable"})
        self.workbook_path.write_bytes(b"external-change")
        build_number = 0

        def unstable_loader() -> dict:
            nonlocal build_number
            build_number += 1
            self.workbook_path.write_bytes(b"x" * (32 + build_number))
            return {"version": "unstable"}

        with self.assertRaises(DashboardResponseCacheUnstableBuild):
            self.cache.get_response(self.workbook_path, unstable_loader)
        self.assertEqual(3, build_number)

    def test_one_generation_change_restarts_the_complete_build(self) -> None:
        builds: list[int] = []

        def loader() -> dict:
            generation = len(builds) + 1
            builds.append(generation)
            if generation == 1:
                self.workbook_path.write_bytes(b"generation-two")
            return {
                "overview": {"generation": generation},
                "creator_health": {"generation": generation},
            }

        result = self.cache.get_response(self.workbook_path, loader)
        self.assertEqual([1, 2], builds)
        self.assertEqual(2, result["overview"]["generation"])
        self.assertEqual(2, result["creator_health"]["generation"])

    def test_atomic_replace_generation_change_retries_coherently(self) -> None:
        build_count = 0

        def loader() -> dict:
            nonlocal build_count
            build_count += 1
            if build_count == 1:
                replacement = self.root / "replacement.xlsx"
                replacement.write_bytes(b"atomic-replacement-generation")
                os.replace(replacement, self.workbook_path)
            return {"generation": build_count}

        self.assertEqual(2, self.cache.get_response(self.workbook_path, loader)["generation"])
        self.assertEqual(2, build_count)

    def test_empty_dashboard_payload_is_cacheable(self) -> None:
        loader = mock.Mock(return_value={
            "overview": {"creator_count": 0},
            "creator_health": {"rising": [], "falling": [], "expired": []},
            "action_items": {},
        })
        first = self.cache.get_response(self.workbook_path, loader)
        second = self.cache.get_response(self.workbook_path, loader)
        self.assertEqual(first, second)
        self.assertEqual(1, loader.call_count)

    def test_concurrent_writer_completion_rebuilds_from_new_generation(self) -> None:
        start_writer = threading.Event()
        writer_done = threading.Event()
        build_count = 0

        def writer() -> None:
            start_writer.wait(timeout=2)
            self.workbook_path.write_bytes(b"writer-complete-generation")
            writer_done.set()

        thread = threading.Thread(target=writer)
        thread.start()

        def loader() -> dict:
            nonlocal build_count
            build_count += 1
            snapshot = self.workbook_path.read_bytes().decode("ascii")
            if build_count == 1:
                start_writer.set()
                self.assertTrue(writer_done.wait(timeout=2))
            return {"generation": snapshot}

        result = self.cache.get_response(self.workbook_path, loader)
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual("writer-complete-generation", result["generation"])
        self.assertEqual(2, build_count)

    def test_existing_legacy_workbook_schema_write_retries_and_succeeds(self) -> None:
        legacy_path = self.root / "legacy.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Creators"
        sheet.append(["creator_id", "creator_name"])
        sheet.append(["creator-1", "Fixture Creator"])
        workbook.save(legacy_path)
        workbook.close()
        before = legacy_path.stat()
        build_count = 0

        def loader() -> dict:
            nonlocal build_count
            build_count += 1
            return {"creators": CreatorRepository(legacy_path).getCreators()}

        no_lock = lambda **_kwargs: contextlib.nullcontext()
        with (
            mock.patch("excel_workbook_store.shared_storage_lock", side_effect=no_lock),
            mock.patch("creator_repository.log_event"),
        ):
            result = self.cache.get_response(legacy_path, loader)

        after = legacy_path.stat()
        self.assertEqual(2, build_count)
        self.assertEqual(1, len(result["creators"]))
        self.assertNotEqual((before.st_mtime_ns, before.st_size), (after.st_mtime_ns, after.st_size))

    def test_generation_change_events_are_sanitized_and_bounded(self) -> None:
        events: list[str] = []
        cache = DashboardResponseCache(lambda: self.today, events.append)
        build_count = 0

        def unstable_loader() -> dict:
            nonlocal build_count
            build_count += 1
            self.workbook_path.write_bytes(b"x" * (48 + build_count))
            return {"generation": build_count}

        with self.assertRaises(DashboardResponseCacheUnstableBuild):
            cache.get_response(self.workbook_path, unstable_loader)

        self.assertEqual(3, build_count)
        self.assertEqual(3, len(events))
        self.assertIn("attempt=1/3 | action=retry", events[0])
        self.assertIn("attempt=3/3 | action=fail", events[-1])
        self.assertNotIn(str(self.workbook_path), "\n".join(events))

    def test_first_read_can_create_workbook_without_returning_dashboard_error(self) -> None:
        missing_workbook = self.root / "new" / "Creator_Library.xlsx"
        build_count = 0

        def create_workbook() -> dict:
            nonlocal build_count
            build_count += 1
            if not missing_workbook.exists():
                missing_workbook.parent.mkdir()
                missing_workbook.write_bytes(b"created")
            return {"overview": {"creator_count": 0}}

        first = self.cache.get_response(missing_workbook, create_workbook)
        self.assertEqual(0, first["overview"]["creator_count"])
        self.assertEqual(2, build_count)

        stable_loader = mock.Mock(return_value={"overview": {"creator_count": 0}})
        second = self.cache.get_response(missing_workbook, stable_loader)
        self.assertEqual(0, second["overview"]["creator_count"])
        stable_loader.assert_not_called()

    def test_shared_storage_lock_is_acquired_before_cache_build(self) -> None:
        trace: list[str] = []

        @contextlib.contextmanager
        def traced_lock(**_kwargs):
            trace.append("storage-enter")
            try:
                yield
            finally:
                trace.append("storage-exit")

        with mock.patch(
            "services.dashboard_response_cache.shared_storage_lock", traced_lock
        ):
            result = self.cache.get_response(
                self.workbook_path,
                lambda: (trace.append("loader") or {"ok": True}),
            )
        self.assertTrue(result["ok"])
        self.assertEqual(["storage-enter", "loader", "storage-exit"], trace)


class _CreatorRepository:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def updateCreator(self, _creator_id, _payload, **_kwargs):
        if self.fail:
            raise ValueError("write failed")
        return {"creator_id": "creator"}

    def updateCreatorStatus(self, _creator_id, _status):
        if self.fail:
            raise ValueError("write failed")
        return {"creator_id": "creator"}

    def updateCreatorRelations(self, _creator_id, _payload, **_kwargs):
        if self.fail:
            raise ValueError("write failed")
        return {"creator_id": "creator"}

    def saveCreator(self, _analysis):
        if self.fail:
            raise ValueError("write failed")
        return {"creator_id": "creator", "snapshot_id": "snapshot"}


class DashboardInvalidationBoundaryTests(unittest.TestCase):
    def _creator_service(self, repository: _CreatorRepository, invalidator):
        return CreatorService(
            lambda: repository,
            lambda: mock.Mock(),
            dashboard_response_cache_invalidator=invalidator,
        )

    def test_successful_creator_mutation_and_snapshot_write_invalidate(self) -> None:
        invalidate = mock.Mock()
        service = self._creator_service(_CreatorRepository(), invalidate)
        service.update_creator_profile("creator", {"creator_name": "Updated"})
        service.update_creator_status("creator", "contacted")
        service.import_creator_from_extension({"creator": {}}, compensation_task_id="task")
        self.assertEqual(3, invalidate.call_count)

    def test_agency_id_only_creator_mutation_does_not_invalidate_dashboard(self) -> None:
        invalidate = mock.Mock()
        self._creator_service(_CreatorRepository(), invalidate).update_creator_relations(
            "creator", {"agency_id": "agency"}
        )
        invalidate.assert_not_called()

    def test_failed_creator_mutation_does_not_invalidate_dashboard(self) -> None:
        invalidate = mock.Mock()
        with self.assertRaises(ValueError):
            self._creator_service(_CreatorRepository(fail=True), invalidate).update_creator_status(
                "creator", "contacted"
            )
        invalidate.assert_not_called()

    def test_successful_hard_delete_invalidates_after_locked_delete(self) -> None:
        invalidate = mock.Mock()
        service = CreatorHardDeleteService(
            lambda: mock.Mock(),
            lambda: mock.Mock(),
            lambda: ROOT,
            dashboard_response_cache_invalidator=invalidate,
        )
        with (
            mock.patch.object(service, "_delete_locked", return_value={"deleted": True}),
            mock.patch(
                "services.creator_hard_delete_service.shared_storage_lock",
                side_effect=lambda **_kwargs: contextlib.nullcontext(),
            ),
        ):
            self.assertTrue(
                service.delete_creator(
                    "creator", confirm=True, preview_fingerprint="fingerprint"
                )["deleted"]
            )
        invalidate.assert_called_once_with()

    def test_campaign_and_campaign_creator_relevant_writes_invalidate(self) -> None:
        invalidate = mock.Mock()
        campaign = mock.Mock()
        campaign.updateCampaign.return_value = {"campaign_id": "campaign"}
        campaign_creator = mock.Mock()
        campaign_creator.updateCampaignCreator.return_value = {"id": "relation"}
        context = {
            "repositories": {
                "campaign": lambda: campaign,
                "campaign_creator": lambda: campaign_creator,
            },
            "services": {"invalidate_dashboard_response_cache": invalidate},
        }
        handler = mock.Mock()
        request = {
            "method": "PATCH",
            "path": "/api/campaigns/campaign",
            "query": {},
            "get_payload": lambda: {"name": "New name"},
        }
        self.assertTrue(campaign_handler.handle(handler, request, context))
        request = {
            "method": "PATCH",
            "path": "/api/campaign-creators/relation",
            "query": {},
            "get_payload": lambda: {"cost": 100},
        }
        self.assertTrue(campaign_handler.handle(handler, request, context))
        self.assertEqual(2, invalidate.call_count)

    def test_unrelated_campaign_write_does_not_invalidate(self) -> None:
        invalidate = mock.Mock()
        campaign = mock.Mock()
        campaign.updateCampaign.return_value = {"campaign_id": "campaign"}
        context = {
            "repositories": {"campaign": lambda: campaign},
            "services": {"invalidate_dashboard_response_cache": invalidate},
        }
        handler = mock.Mock()
        request = {
            "method": "PATCH",
            "path": "/api/campaigns/campaign",
            "query": {},
            "get_payload": lambda: {"budget": 1000},
        }
        self.assertTrue(campaign_handler.handle(handler, request, context))
        invalidate.assert_not_called()
