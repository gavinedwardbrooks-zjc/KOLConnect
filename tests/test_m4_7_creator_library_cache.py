from __future__ import annotations

import os
import shutil
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import creator_repository  # noqa: E402
from local_storage_lock import shared_storage_lock  # noqa: E402
from services.agency_service import AgencyService  # noqa: E402
from services.creator_hard_delete_service import CreatorHardDeleteService  # noqa: E402
from services.creator_library_cache import CreatorLibraryCache  # noqa: E402
from services.creator_service import CreatorService  # noqa: E402


class FakeAgencyPort:
    def save_agency(self, payload):
        return dict(payload)

    def save_contact(self, payload):
        return dict(payload)

    def upsert_external_contact(self, external_record_id, **kwargs):
        return {"external_record_id": external_record_id, **kwargs}


class CreatorLibraryCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ROOT / f".m4_7_cache_test_{uuid.uuid4().hex}"
        self.root.mkdir()
        self.workbook_path = self.root / "Creator_Library.xlsx"
        self.lock_patcher = mock.patch(
            "local_storage_lock.get_shared_storage_lock_path",
            return_value=self.root / "locks" / "shared_storage.lock",
        )
        self.lock_patcher.start()
        self.log_patcher = mock.patch.object(creator_repository, "log_event")
        self.log_patcher.start()
        self.repository = creator_repository.CreatorRepository(self.workbook_path)
        self.repository.getCreators()
        self._seed_creators()
        self.cache = CreatorLibraryCache()
        self.service = CreatorService(
            lambda: self.repository,
            lambda: None,
            creator_library_cache_provider=lambda: self.cache,
        )

    def tearDown(self) -> None:
        self.log_patcher.stop()
        self.lock_patcher.stop()
        shutil.rmtree(self.root, ignore_errors=True)

    def _seed_creators(self) -> None:
        workbook = load_workbook(self.workbook_path)
        creators = workbook["Creators"]
        creator_headers = [str(cell.value or "") for cell in creators[1]]
        agencies = workbook["Agencies"]
        agency_headers = [str(cell.value or "") for cell in agencies[1]]
        agencies.append(
            [
                {"agency_id": "agency_one", "name": "Agency One"}.get(header, "")
                for header in agency_headers
            ]
        )
        rows = [
            {
                "creator_id": "creator_one",
                "name": "Alice",
                "platform": "TikTok",
                "profile_url": "https://example.com/alice",
                "country": "Brazil",
                "language": "Portuguese",
                "content_category": "Gaming",
                "followers": "20K",
                "tags": "priority, gaming",
                "status": "discovered",
                "agency_id": "agency_one",
                "created_at": "2026-08-01T00:00:00Z",
                "updated_at": "2026-08-02T00:00:00Z",
            },
            {
                "creator_id": "creator_two",
                "name": "Bella",
                "platform": "Instagram",
                "profile_url": "https://example.com/bella",
                "country": "USA",
                "language": "English",
                "content_category": "Lifestyle",
                "followers": "10K",
                "tags": "lifestyle",
                "status": "contacted",
                "created_at": "2026-08-03T00:00:00Z",
                "updated_at": "2026-08-04T00:00:00Z",
            },
            {
                "creator_id": "creator_archived",
                "name": "Archived",
                "platform": "YouTube",
                "profile_url": "https://example.com/archived",
                "country": "USA",
                "language": "English",
                "content_category": "Gaming",
                "followers": "30K",
                "status": "completed",
                "archived_at": "2026-08-05T00:00:00Z",
                "created_at": "2026-08-05T00:00:00Z",
                "updated_at": "2026-08-05T00:00:00Z",
            },
        ]
        for values in rows:
            creators.append([values.get(header, "") for header in creator_headers])
        workbook.save(self.workbook_path)
        workbook.close()

    def test_cache_hit_loads_and_builds_once(self) -> None:
        with (
            mock.patch.object(
                self.repository.store,
                "_open_now",
                wraps=self.repository.store._open_now,
            ) as open_now,
            mock.patch.object(
                self.repository,
                "getCreatorLibrarySnapshot",
                wraps=self.repository.getCreatorLibrarySnapshot,
            ) as build,
        ):
            first = self.service.get_creator_library(page_size=12)
            second = self.service.get_creator_library(page_size=12, page=1)
        self.assertEqual(first, second)
        self.assertEqual(1, open_now.call_count)
        self.assertEqual(1, build.call_count)

    def test_successful_creator_write_invalidates_and_reloads(self) -> None:
        with mock.patch.object(
            self.repository,
            "getCreatorLibrarySnapshot",
            wraps=self.repository.getCreatorLibrarySnapshot,
        ) as build:
            self.service.get_creator_library(page_size=12)
            self.service.update_creator_profile(
                "creator_one", {"creator_name": "Alice Updated"}
            )
            result = self.service.get_creator_library(page_size=12)
        self.assertEqual(2, build.call_count)
        self.assertEqual(
            "Alice Updated",
            next(
                row["creator_name"]
                for row in result["creators"]
                if row["creator_id"] == "creator_one"
            ),
        )

    def test_failed_creator_write_does_not_invalidate(self) -> None:
        self.service.get_creator_library(page_size=12)
        with mock.patch.object(self.cache, "invalidate") as invalidate:
            with self.assertRaises(ValueError):
                self.service.update_creator_profile("missing", {"creator_name": "No"})
        invalidate.assert_not_called()

    def test_external_workbook_mtime_change_rebuilds(self) -> None:
        with mock.patch.object(
            self.repository,
            "getCreatorLibrarySnapshot",
            wraps=self.repository.getCreatorLibrarySnapshot,
        ) as build:
            self.service.get_creator_library(page_size=12)
            current = self.workbook_path.stat()
            os.utime(
                self.workbook_path,
                ns=(current.st_atime_ns, current.st_mtime_ns + 1_000_000_000),
            )
            self.service.get_creator_library(page_size=12)
        self.assertEqual(2, build.call_count)

    def test_returned_data_cannot_mutate_cached_snapshot(self) -> None:
        first = self.service.get_creator_library(page_size=12)
        first["creators"][0]["creator_name"] = "Polluted"
        first["creators"][0]["trend"]["changes"]["followers"] = "Polluted"
        first["creators"].append({"creator_id": "injected"})
        first["filter_options"]["country"].append("Injected")

        second = self.service.get_creator_library(page_size=12)
        self.assertNotIn("Polluted", {row["creator_name"] for row in second["creators"]})
        self.assertNotIn("injected", {row["creator_id"] for row in second["creators"]})
        self.assertNotIn("Injected", second["filter_options"]["country"])

    def test_query_contract_and_read_only_detail_lookup_are_unchanged(self) -> None:
        filtered = self.service.get_creator_library(
            page_size=12,
            sort="followers",
            order="desc",
            filters={
                "search": "alice",
                "platform": "TikTok",
                "country": "Brazil",
                "language": "Portuguese",
                "content_category": "Gaming",
                "agency_id": "agency_one",
                "tag": "priority",
                "status": "discovered",
            },
        )
        self.assertEqual(1, filtered["total"])
        self.assertEqual("creator_one", filtered["creators"][0]["creator_id"])
        self.assertEqual(filtered["creators"], filtered["records"])
        self.assertIn("agency_one", filtered["filter_options"]["agency_id"])

        active = self.service.get_creator_library(page_size=12)
        archived = self.service.get_creator_library(
            page_size=12,
            include_archived=True,
            filters={"status": "archived"},
        )
        self.assertEqual(2, active["total"])
        self.assertEqual(["creator_archived"], [row["creator_id"] for row in archived["creators"]])
        self.assertEqual(
            "creator_one",
            self.service.get_creator_detail("creator_one")["record"]["creator_id"],
        )

    def test_concurrent_cold_read_loads_and_builds_once(self) -> None:
        readers = 6
        barrier = threading.Barrier(readers)
        results = []
        errors = []
        build_count = 0
        build_count_lock = threading.Lock()
        original_loader = self.repository.getCreatorLibrarySnapshot

        def slow_loader():
            nonlocal build_count
            with build_count_lock:
                build_count += 1
            time.sleep(0.05)
            return original_loader()

        def read() -> None:
            try:
                barrier.wait(timeout=2)
                results.append(
                    self.cache.get_snapshot(self.workbook_path, slow_loader)
                )
            except BaseException as exc:
                errors.append(exc)

        with mock.patch.object(
            self.repository.store,
            "_open_now",
            wraps=self.repository.store._open_now,
        ) as open_now:
            threads = [threading.Thread(target=read) for _ in range(readers)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=3)

        self.assertEqual([], errors)
        self.assertEqual(readers, len(results))
        self.assertEqual(1, open_now.call_count)
        self.assertEqual(1, build_count)
        self.assertTrue(all(result == results[0] for result in results))

    def test_cold_load_uses_mutation_compatible_lock_order(self) -> None:
        storage_held = threading.Event()
        reader_started = threading.Event()
        invalidated = threading.Event()
        reader_finished = threading.Event()

        def writer() -> None:
            with shared_storage_lock(timeout=2):
                storage_held.set()
                reader_started.wait(timeout=1)
                time.sleep(0.05)
                self.cache.invalidate()
                invalidated.set()

        def reader() -> None:
            storage_held.wait(timeout=1)
            reader_started.set()
            self.cache.get_snapshot(
                self.workbook_path,
                self.repository.getCreatorLibrarySnapshot,
            )
            reader_finished.set()

        writer_thread = threading.Thread(target=writer, daemon=True)
        reader_thread = threading.Thread(target=reader, daemon=True)
        writer_thread.start()
        reader_thread.start()
        writer_thread.join(timeout=2)
        reader_thread.join(timeout=2)

        self.assertTrue(invalidated.is_set())
        self.assertTrue(reader_finished.is_set())

    def test_agency_writes_invalidate_after_success(self) -> None:
        cache = mock.Mock()
        service = AgencyService(
            lambda: FakeAgencyPort(),
            lambda: self.repository,
            lambda: cache,
        )
        service.save_agency({"agency_id": "a"})
        service.save_agency_contact({"contact_id": "c"})
        service.upsert_external_contact("external", name="Name")
        self.assertEqual(3, cache.invalidate.call_count)

    def test_agency_options_reuse_creator_snapshot(self) -> None:
        agency_service = AgencyService(
            lambda: FakeAgencyPort(),
            lambda: self.repository,
            lambda: self.cache,
        )
        with mock.patch.object(
            self.repository.store,
            "_open_now",
            wraps=self.repository.store._open_now,
        ) as open_now:
            agencies = agency_service.get_agencies()["agencies"]
            creators = self.service.get_creator_library(page_size=12)
        self.assertEqual(1, open_now.call_count)
        self.assertEqual("agency_one", agencies[0]["agency_id"])
        self.assertEqual(1, agencies[0]["creator_count"])
        self.assertEqual(2, creators["total"])

    def test_committed_hard_delete_invalidates(self) -> None:
        invalidator = mock.Mock()
        service = CreatorHardDeleteService(
            lambda: None,
            lambda: None,
            lambda: self.root,
            lock_timeout=2,
            creator_library_cache_invalidator=invalidator,
        )
        with mock.patch.object(
            service,
            "_delete_locked",
            return_value={"creator_id": "creator_one", "deleted": True},
        ):
            result = service.delete_creator(
                "creator_one", confirm=True, preview_fingerprint="fingerprint"
            )
        self.assertTrue(result["deleted"])
        invalidator.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
