from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from domain.normalization import (  # noqa: E402
    extract_country,
    format_compact_number,
    normalize_country,
    normalize_followers,
    normalize_number,
    normalize_tags,
)
from services.creator_summary_service import CreatorSummaryService  # noqa: E402
from creator_repository import CreatorRepository  # noqa: E402


class M74NormalizationTests(unittest.TestCase):
    def test_country_aliases_share_iso_identity(self):
        for value in ("Brazil", "Brasil", "BRASIL", "brazil", "巴西", "BR", "br", "BRA"):
            self.assertEqual("BR", normalize_country(value), value)
        self.assertIsNone(normalize_country("LATAM"))
        self.assertIsNone(normalize_country("Global"))
        self.assertEqual("BR", extract_country("找 Brasil TikTok 达人"))

    def test_follower_shorthand_and_display(self):
        cases = {
            "100K": 100000, "100k": 100000, "100 K": 100000,
            "1021k": 1021000, "1M": 1000000, "1m": 1000000,
            "1.14M": 1140000, "627.6K": 627600, "42.5K": 42500,
            "1,000,000": 1000000, "1000000": 1000000, "1B": 1000000000,
        }
        for raw, expected in cases.items():
            self.assertEqual(expected, normalize_followers(raw), raw)
            self.assertEqual(float(expected), CreatorSummaryService._number(raw), raw)
        self.assertEqual("1.14M", format_compact_number(1140000))

    def test_missing_and_invalid_fail_closed(self):
        for value in (None, "", "--", "N/A", "unknown"):
            self.assertIsNone(normalize_followers(value))
        for value in ("100KK", "1MM", "abc", "NaN", "Infinity", "-100K", math.nan, math.inf):
            self.assertIsNone(normalize_number(value), repr(value))
        self.assertIsNone(normalize_followers("1.5"))

    def test_user_tag_serialization_is_stable(self):
        self.assertEqual(["priority", "Gaming"], normalize_tags("priority, Gaming,priority"))

    def test_creator_library_filters_use_canonical_semantics(self):
        records = [
            {"creator_id": "a", "country": "Brazil", "followers": "100K", "content_category": "Gaming", "platform": "TikTok", "tags": "manual"},
            {"creator_id": "b", "country": "Japan", "followers": "", "content_category": "Beauty", "platform": "Instagram", "tags": "priority"},
        ]
        for country in ("Brazil", "Brasil", "巴西", "BR"):
            result = CreatorRepository._filter_creator_records(records, {"country": country})
            self.assertEqual(["a"], [row["creator_id"] for row in result])
        for minimum in ("100k", "100K", "100000"):
            result = CreatorRepository._filter_creator_records(records, {"followers_min": minimum})
            self.assertEqual(["a"], [row["creator_id"] for row in result])
        self.assertEqual(
            ["a"],
            [row["creator_id"] for row in CreatorRepository._filter_creator_records(records, {"ai_tag": "category:Gaming"})],
        )
        self.assertEqual("manual", records[0]["tags"], "AI filtering must not overwrite user tags")


if __name__ == "__main__":
    unittest.main()
