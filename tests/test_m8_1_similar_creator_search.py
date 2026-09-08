from __future__ import annotations

import copy
import re
import socket
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import http_handlers.creator_handler as creator_handler
from services.similar_creator_search_service import SimilarCreatorSearchService


def creator(creator_id: str, name: str, **values):
    return {
        "creator_id": creator_id,
        "name": name,
        "tags": "",
        "country": "",
        "language": "",
        "content_category": "",
        "archived_at": "",
        **values,
    }


def account(creator_id: str, account_uid: str, platform: str, **values):
    return {
        "creator_id": creator_id,
        "account_uid": account_uid,
        "platform": platform,
        "followers": "",
        **values,
    }


def relation(creator_id: str, **values):
    return {
        "creator_id": creator_id,
        "archived_at": "",
        "quote_currency": "",
        "quote_unit_amount": "",
        "quote_quantity": "",
        "quote_unit": "",
        "creator_quote": "",
        "views": "",
        "likes": "",
        "comments": "",
        **values,
    }


class FakeRepository:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def getSimilarCreatorSourceData(self):
        self.calls += 1
        return copy.deepcopy(self.data)


class SimilarCreatorSearchTests(unittest.TestCase):
    def service(self, *, creators, accounts=(), snapshots=(), relations=()):
        repository = FakeRepository({
            "creators": list(creators),
            "accounts": list(accounts),
            "snapshots": list(snapshots),
            "campaign_creators": list(relations),
        })
        return SimilarCreatorSearchService(lambda: repository), repository

    @staticmethod
    def candidate(result, creator_id):
        return next(row for row in result["candidates"] if row["creator_id"] == creator_id)

    def test_user_tags_are_authoritative_and_ai_tags_are_supplemental(self):
        service, repository = self.service(
            creators=[
                creator("source", "Source", tags="Gaming, Brazil", content_category="Gaming"),
                creator("user", "User", tags="gaming, comedy", content_category="Comedy"),
                creator("ai", "AI", tags="", content_category="Gaming"),
                creator("none", "None", tags="", content_category=""),
            ]
        )

        result = service.find_similar("source")

        self.assertEqual(1, repository.calls)
        self.assertNotIn("source", {row["creator_id"] for row in result["candidates"]})
        self.assertEqual(["Gaming"], self.candidate(result, "user")["evidence"]["user_tags"])
        self.assertEqual([], self.candidate(result, "user")["evidence"]["ai_tags"])
        self.assertEqual([], self.candidate(result, "ai")["evidence"]["user_tags"])
        self.assertEqual(["category:Gaming"], self.candidate(result, "ai")["evidence"]["ai_tags"])
        self.assertNotIn("none", {row["creator_id"] for row in result["candidates"]})

    def test_platform_and_followers_remain_account_scoped_without_duplicate_creators(self):
        service, _ = self.service(
            creators=[creator("source", "Source"), creator("candidate", "Candidate")],
            accounts=[
                account("source", "source_tt", "TikTok", followers="100K"),
                account("source", "source_ig", "Instagram", followers="500K"),
                account("candidate", "candidate_tt", "TikTok", followers="150K"),
                account("candidate", "candidate_ig", "Instagram", followers="2M"),
            ],
        )

        result = service.find_similar("source")

        self.assertEqual(["candidate"], [row["creator_id"] for row in result["candidates"]])
        evidence = result["candidates"][0]["evidence"]
        self.assertEqual(2, len(evidence["platform_accounts"]))
        self.assertEqual(
            [{
                "platform": "TikTok",
                "source_account_uid": "source_tt",
                "candidate_account_uid": "candidate_tt",
                "follower_proximity": True,
            }],
            evidence["follower_accounts"],
        )
        self.assertNotIn("source_ig", [row["source_account_uid"] for row in evidence["follower_accounts"]])

    def test_country_language_content_and_missing_values_have_no_inferred_match(self):
        service, _ = self.service(
            creators=[
                creator("source", "Source", country="Brazil", language="Portuguese", content_category="Gaming"),
                creator("match", "Match", country="Brasil", language="portuguese", content_category="gaming"),
                creator("missing", "Missing", country="", language="", content_category=""),
            ]
        )

        result = service.find_similar("source")

        evidence = self.candidate(result, "match")["evidence"]
        self.assertEqual("BR", evidence["country"])
        self.assertEqual("Portuguese", evidence["language"])
        self.assertEqual(["Gaming"], evidence["content_category"])
        self.assertNotIn("missing", {row["creator_id"] for row in result["candidates"]})

    def test_quote_requires_same_currency_and_pricing_contract_without_fx(self):
        base = [creator("source", "Source"), creator("usd", "USD"), creator("brl", "BRL"), creator("unit", "Unit")]
        relations = [
            relation("source", quote_currency="USD", quote_unit_amount=100, quote_quantity=2, quote_unit="video", creator_quote=200),
            relation("usd", quote_currency="USD", quote_unit_amount=80, quote_quantity=2, quote_unit="video", creator_quote=160),
            relation("brl", quote_currency="BRL", quote_unit_amount=500, quote_quantity=2, quote_unit="video", creator_quote=1000),
            relation("unit", quote_currency="USD", quote_unit_amount=200, quote_quantity=1, quote_unit="post", creator_quote=200),
        ]
        service, _ = self.service(
            creators=base,
            relations=relations,
        )

        result = service.find_similar("source")

        self.assertTrue(self.candidate(result, "usd")["evidence"]["quote"]["comparable"])
        source_rows = [row for row in relations if row["creator_id"] == "source"]
        brl_rows = [row for row in relations if row["creator_id"] == "brl"]
        unit_rows = [row for row in relations if row["creator_id"] == "unit"]
        self.assertFalse(service._quote_evidence(source_rows, brl_rows)["comparable"])
        self.assertFalse(service._quote_evidence(source_rows, unit_rows)["comparable"])
        self.assertNotIn("brl", {row["creator_id"] for row in result["candidates"]})
        self.assertNotIn("unit", {row["creator_id"] for row in result["candidates"]})
        self.assertEqual("USD", self.candidate(result, "usd")["evidence"]["quote"]["source_contracts"][0]["currency"])
        self.assertEqual([], service._quote_records([
            relation("broken", quote_currency="USD", quote_unit_amount=100, quote_quantity=2, quote_unit="video", creator_quote=999),
            relation("bad_currency", quote_currency="US Dollars", creator_quote=200),
        ]))

    def test_recorded_engagement_requires_complete_non_missing_metrics(self):
        service, _ = self.service(
            creators=[creator("source", "Source"), creator("valid", "Valid"), creator("missing", "Missing")],
            relations=[
                relation("source", views=1000, likes=100, comments=20),
                relation("valid", views=2000, likes=200, comments=40),
                relation("missing", views="", likes=0, comments=0),
            ],
        )

        result = service.find_similar("source")

        self.assertTrue(self.candidate(result, "valid")["evidence"]["engagement"]["available"])
        self.assertNotIn("missing", {row["creator_id"] for row in result["candidates"]})

    def test_limit_ordering_unknown_source_and_local_only_contract(self):
        service, _ = self.service(
            creators=[
                creator("source", "Source", tags="tag"),
                creator("b", "Beta", tags="tag"),
                creator("a", "Alpha", tags="tag"),
            ]
        )
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            result = service.find_similar("source", limit=1)
        self.assertEqual(2, result["total"])
        self.assertEqual(["a"], [row["creator_id"] for row in result["candidates"]])
        with self.assertRaisesRegex(ValueError, "未找到"):
            service.find_similar("missing")
        with self.assertRaisesRegex(ValueError, "limit"):
            service.find_similar("source", limit=0)


class SimilarCreatorApiTests(unittest.TestCase):
    def test_api_returns_candidates_and_unknown_source_is_not_found(self):
        class Search:
            def find_scored(self, creator_id, *, limit, include_ai=False):
                if creator_id == "missing":
                    raise ValueError("未找到达人记录。")
                return {"source_creator_id": creator_id, "candidates": [], "total": 0, "limit": limit}

        class Handler:
            def __init__(self):
                self.response = None

            def _json(self, payload, status=200):
                self.response = (status, payload)

            def _error(self, message, status=400):
                self.response = (status, {"ok": False, "error": message})

        context = {
            "services": {
                "creator": object(), "agency": object(), "creator_delete_impact": object(),
                "creator_hard_delete": object(), "similar_creator_search": Search(),
            },
            "config": {"legacy_cooperation_pattern": re.compile(r"$^")},
        }
        handler = Handler()
        self.assertTrue(creator_handler.handle(handler, {
            "method": "GET", "path": "/api/creator-library/source/similar", "query": {"limit": ["5"]},
        }, context))
        self.assertEqual((200, {"ok": True, "source_creator_id": "source", "candidates": [], "total": 0, "limit": 5}), handler.response)
        self.assertTrue(creator_handler.handle(handler, {
            "method": "GET", "path": "/api/creator-library/missing/similar", "query": {},
        }, context))
        self.assertEqual(404, handler.response[0])
