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


class CreatorLibraryPaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workbook_path = Path(self.temp_dir.name) / "Creator_Library.xlsx"
        self.repository = creator_repository.CreatorRepository(self.workbook_path)
        self.repository.getCreators()
        self._seed_creators()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _seed_creators(self) -> None:
        names = [
            "Zoe", "Alice", "Bella", "张三", "李四", "王五", "Diego", "Emma",
            "Felix", "Grace", "Hugo", "Ivy", "Jack", "Kira", "Liam",
        ]
        platforms = ["YouTube", "Instagram", "TikTok"]
        followers = [
            "1K", "20万", "1.2M", "950", "8K", "2M", "15K", "3K",
            "40K", "700", "5万", "9K", "100K", "12K", "6K",
        ]
        workbook = load_workbook(self.workbook_path)
        sheet = workbook["Creators"]
        headers = [str(cell.value or "") for cell in sheet[1]]
        for index, name in enumerate(names):
            values = {
                "creator_id": f"creator_{index:02d}",
                "name": name,
                "platform": platforms[index % len(platforms)],
                "profile_url": f"https://example.com/{index}",
                "country": "Brazil" if index < 2 else "USA",
                "language": "English",
                "content_category": "Gaming" if index % 2 == 0 else "Lifestyle",
                "tags": "priority, gaming" if index % 2 == 0 else "lifestyle",
                "followers": followers[index],
                "status": "discovered",
                "created_at": f"2026-07-{index + 1:02d}T00:00:00Z",
                "updated_at": f"2026-08-{15 - index:02d}T00:00:00Z",
            }
            sheet.append([values.get(header, "") for header in headers])
        workbook.save(self.workbook_path)
        workbook.close()

    def test_pages_are_bounded_and_do_not_overlap(self) -> None:
        first = self.repository.getCreatorsPage(page=1, page_size=12)
        second = self.repository.getCreatorsPage(page=2, page_size=12)
        self.assertEqual(15, first["total"])
        self.assertEqual(2, first["pages"])
        self.assertEqual(12, len(first["creators"]))
        self.assertEqual(3, len(second["creators"]))
        first_ids = {record["creator_id"] for record in first["creators"]}
        second_ids = {record["creator_id"] for record in second["creators"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_supported_sort_orders(self) -> None:
        created = self.repository.getCreatorsPage(
            page=1, page_size=24, sort="created_at", order="desc",
        )["creators"]
        self.assertEqual("creator_14", created[0]["creator_id"])

        updated = self.repository.getCreatorsPage(
            page=1, page_size=24, sort="updated_at", order="desc",
        )["creators"]
        self.assertEqual("creator_00", updated[0]["creator_id"])

        followers = self.repository.getCreatorsPage(
            page=1, page_size=24, sort="followers", order="desc",
        )["creators"]
        self.assertEqual("2M", followers[0]["followers"])
        self.assertEqual("1.2M", followers[1]["followers"])
        self.assertEqual("20万", followers[2]["followers"])

        platforms = self.repository.getCreatorsPage(
            page=1, page_size=24, sort="platform", order="asc",
        )["creators"]
        platform_groups = [record["platform"] for record in platforms]
        self.assertEqual(
            sorted(platform_groups, key={"Instagram": 0, "TikTok": 1, "YouTube": 2}.get),
            platform_groups,
        )

    def test_creator_name_uses_english_and_chinese_phonetic_order(self) -> None:
        records = self.repository.getCreatorsPage(
            page=1, page_size=24, sort="creator_name", order="asc",
        )["creators"]
        names = [record["creator_name"] for record in records]
        self.assertLess(names.index("Alice"), names.index("Bella"))
        self.assertLess(names.index("Bella"), names.index("Zoe"))
        self.assertLess(names.index("李四"), names.index("王五"))
        self.assertLess(names.index("王五"), names.index("张三"))

    def test_api_returns_compatible_pagination_contract(self) -> None:
        patchers = [
            mock.patch.object(server, "get_creator_repository", return_value=self.repository),
            mock.patch.object(server, "log_event"),
            mock.patch.object(server, "log_error"),
            mock.patch.object(server, "_record_last_error"),
        ]
        for patcher in patchers:
            patcher.start()
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = (
                f"http://127.0.0.1:{httpd.server_port}/api/creator-library"
                "?page=2&page_size=12&sort=followers&order=desc"
            )
            with urllib.request.urlopen(url) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(15, payload["total"])
            self.assertEqual(2, payload["page"])
            self.assertEqual(12, payload["page_size"])
            self.assertEqual(2, payload["pages"])
            self.assertEqual(payload["creators"], payload["records"])
            self.assertLessEqual(len(payload["creators"]), payload["page_size"])

            with urllib.request.urlopen(
                f"http://127.0.0.1:{httpd.server_port}/api/creator-library"
                "?page=1&page_size=12&country=Brazil"
            ) as response:
                filtered = json.loads(response.read().decode("utf-8"))
            self.assertEqual(2, filtered["total"])
            self.assertEqual({"Brazil"}, {item["country"] for item in filtered["creators"]})
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=2)
            for patcher in reversed(patchers):
                patcher.stop()

    def test_invalid_page_size_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "page_size"):
            self.repository.getCreatorsPage(page=1, page_size=30)

    def test_filters_apply_before_pagination_and_report_filtered_total(self) -> None:
        unfiltered = self.repository.getCreatorsPage(
            page=1, page_size=12, sort="created_at", order="desc",
        )
        self.assertNotIn("Brazil", {record["country"] for record in unfiltered["creators"]})

        filtered = self.repository.getCreatorsPage(
            page=1,
            page_size=12,
            sort="created_at",
            order="desc",
            filters={"country": "Brazil"},
        )
        self.assertEqual(2, filtered["total"])
        self.assertEqual(1, filtered["pages"])
        self.assertEqual({"Brazil"}, {record["country"] for record in filtered["creators"]})

    def test_filter_sort_and_second_page_are_composable(self) -> None:
        sorted_filtered = self.repository.getCreatorsPage(
            page=1,
            page_size=12,
            sort="followers",
            order="desc",
            filters={"country": "USA", "content_category": "Gaming"},
        )
        values = [
            self.repository._metric_sort_value(record["followers"])
            for record in sorted_filtered["creators"]
        ]
        self.assertEqual(sorted(values, reverse=True), values)

        second_page = self.repository.getCreatorsPage(
            page=2,
            page_size=12,
            sort="created_at",
            order="desc",
            filters={"language": "English"},
        )
        self.assertEqual(15, second_page["total"])
        self.assertEqual(3, len(second_page["creators"]))
        self.assertEqual({"creator_02", "creator_01", "creator_00"}, {
            record["creator_id"] for record in second_page["creators"]
        })

    def test_api_filters_and_keeps_global_filter_options(self) -> None:
        result = self.repository.getCreatorsPage(
            page=1,
            page_size=12,
            filters={"country": "Brazil", "tag": "priority"},
        )
        self.assertEqual(1, result["total"])
        self.assertIn("Brazil", result["filter_options"]["country"])
        self.assertIn("USA", result["filter_options"]["country"])


if __name__ == "__main__":
    unittest.main()
