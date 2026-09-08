from __future__ import annotations

import copy
import json
from fractions import Fraction
import socket
import unittest
from unittest.mock import patch

from test_m8_1_similar_creator_search import FakeRepository, account, creator, relation
from services.creator_similarity_engine import CreatorSimilarityEngine, WEIGHTS, ratio
from services.similar_creator_search_service import SimilarCreatorSearchService
from services.similarity_explanation import explain_candidates
from http_handlers import creator_handler


def fixture():
    rows = {"creators": [], "accounts": [], "snapshots": [], "campaign_creators": []}
    for identity in ("source", "candidate"):
        rows["creators"].append(creator(identity, identity, tags="Gaming, Comedy", country="Brazil",
                                        language="Portuguese", content_category="Gaming"))
        rows["accounts"].append(account(identity, identity + "_uid", "TikTok", account_id=identity + "_account", followers=100000))
        rows["campaign_creators"].append(relation(
            identity, id=identity + "_relation", account_id=identity + "_account",
            publications=json.dumps([{"actual_account_id": identity + "_account"}]),
            quote_currency="USD", quote_unit_amount=400, quote_quantity=1, quote_unit="video",
            creator_quote=400, views=1000, likes=100, comments=20,
        ))
    return rows


def service(data=None, provider=None):
    repository = FakeRepository(data if data is not None else fixture())
    return SimilarCreatorSearchService(lambda: repository, explanation_provider=provider), repository


class SimilarityEngineTests(unittest.TestCase):
    def scored(self, data=None):
        search, _ = service(data)
        return search.find_scored("source")["candidates"][0]

    def test_complete_seven_dimensions_exact_score_and_contribution_math(self):
        row = self.scored()
        self.assertEqual(100, sum(WEIGHTS.values()))
        self.assertEqual(100, row["available_nominal_weight"])
        self.assertEqual(100, row["raw_weighted_score"])
        self.assertEqual(100, row["base_similarity_score"])
        self.assertEqual([], row["unavailable_dimensions"])
        self.assertAlmostEqual(1, sum(d["normalized_contribution"] for d in row["dimensions"].values()))
        self.assertEqual(set(WEIGHTS), {r["id"] for r in row["why_recommended"]})

    def test_missing_dimensions_remove_weights_not_score_zero(self):
        for missing_price, missing_er, denominator in ((True, False, 85), (False, True, 90), (True, True, 75)):
            with self.subTest(denominator=denominator):
                data = fixture()
                if missing_price:
                    data["campaign_creators"][1]["creator_quote"] = None
                if missing_er:
                    data["campaign_creators"][1]["comments"] = None
                row = self.scored(data)
                self.assertEqual(denominator, row["available_nominal_weight"])
                self.assertEqual(denominator, row["raw_weighted_score"])
                self.assertEqual(100, row["base_similarity_score"])
                for key in row["unavailable_dimensions"]:
                    self.assertIsNone(row["dimensions"][key]["score"])
                    self.assertIsNone(row["dimensions"][key]["normalized_contribution"])

    def test_partial_scores_exact_weighted_formula(self):
        data = fixture()
        data["creators"][1]["tags"] = "Gaming, Other"
        data["accounts"][1]["followers"] = 200000
        data["campaign_creators"][1].update(quote_unit_amount=800, creator_quote=800, comments=140)
        row = self.scored(data)
        # 30*(1/3) + 20 + 15/2 + 15/2 + 10/2 + 5 + 5 = 60.
        self.assertEqual(60, row["raw_weighted_score"])
        self.assertEqual(60, row["base_similarity_score"])
        self.assertIn("gaming", row["dimensions"]["tag"]["evidence"]["matched"])

    def test_empty_evidence_null_score_no_division_by_zero(self):
        row = CreatorSimilarityEngine().score({"creator_id": "empty", "evidence": {}})
        self.assertIsNone(row["base_similarity_score"])
        self.assertEqual(0, row["available_nominal_weight"])
        self.assertEqual(0, row["raw_weighted_score"])
        self.assertEqual(set(WEIGHTS), set(row["unavailable_dimensions"]))
        self.assertEqual([], row["why_recommended"])

    def test_tags_jaccard_no_overlap_is_valid_zero_and_ai_cannot_override(self):
        for tags, expected in (("Gaming, Comedy", 1), ("gaming, Other", 1/3), ("unrelated", 0)):
            with self.subTest(tags=tags):
                data = fixture()
                data["creators"][1]["tags"] = tags
                result = self.scored(data)["dimensions"]["tag"]
                self.assertTrue(result["available"])
                self.assertAlmostEqual(expected, result["score"])
                self.assertEqual("user_tags", result["evidence"]["source"])

    def test_ai_tags_fallback_only_when_user_pair_unavailable(self):
        data = fixture()
        data["creators"][1]["tags"] = ""
        before = copy.deepcopy(data)
        row = self.scored(data)
        self.assertEqual("ai_tags_fallback", row["dimensions"]["tag"]["evidence"]["source"])
        self.assertEqual(before, data)
        self.assertTrue(any("非人工标签" in r["text"] for r in row["why_recommended"]))

    def test_ai_tag_placeholders_are_missing_not_similarity_evidence(self):
        row = CreatorSimilarityEngine().score({
            "creator_id": "candidate",
            "evidence": {
                "ai_tag_sets": {
                    "source": ["category:unknown", "platform:--"],
                    "candidate": ["category:unknown", "platform:--"],
                },
            },
        })
        self.assertFalse(row["dimensions"]["tag"]["available"])
        self.assertIsNone(row["base_similarity_score"])

    def test_snapshot_timestamp_ties_do_not_depend_on_repository_row_order(self):
        data = fixture()
        data["accounts"][0]["followers"] = None
        data["snapshots"] = [
            {"account_uid": "source_uid", "captured_at": "2026-01-01", "followers": value}
            for value in (100000, 200000)
        ]
        first = self.scored(data)
        data["snapshots"].reverse()
        second = self.scored(data)
        self.assertEqual(first, second)
        self.assertEqual(.5, first["dimensions"]["followers"]["score"])

    def test_content_exact_partial_missing_and_no_semantic_guess(self):
        for category, expected in (("gaming", 1), ("Gaming, Comedy", .5), ("games", 0), ("", None)):
            data = fixture()
            data["creators"][1]["content_category"] = category
            self.assertEqual(expected, self.scored(data)["dimensions"]["content"]["score"])

    def test_followers_ratio_equal_close_far_missing_zero(self):
        for followers, expected in ((100000, 1), (110000, 10/11), (500000, .2), (None, None), (0, 0)):
            with self.subTest(followers=followers):
                data = fixture()
                data["accounts"][1]["followers"] = followers
                actual = self.scored(data)["dimensions"]["followers"]["score"]
                if expected is None:
                    self.assertIsNone(actual)
                else:
                    self.assertAlmostEqual(expected, actual)
        self.assertEqual(1, ratio(0, 0))

    def test_price_same_unit_different_quantity_uses_unit_rate(self):
        data = fixture()
        data["campaign_creators"][1].update(quote_quantity=2, creator_quote=800)
        price = self.scored(data)["dimensions"]["price"]
        self.assertEqual(1, price["score"])
        self.assertEqual("unit_amount", price["evidence"]["value_type"])
        self.assertEqual("400", price["evidence"]["candidate_amount"])

    def test_price_invalid_or_incompatible_is_unavailable(self):
        for change in ({"quote_currency": "BRL"}, {"quote_unit": "story"}, {"creator_quote": None},
                       {"quote_quantity": 1.5, "creator_quote": 600}, {"creator_quote": 401},
                       {"quote_currency": "?"}, {"quote_unit": "invalid"}):
            with self.subTest(change=change):
                data = fixture()
                data["campaign_creators"][1].update(change)
                result = self.scored(data)
                self.assertIsNone(result["dimensions"]["price"]["score"])
                self.assertEqual(85, result["available_nominal_weight"])

    def test_decimal_quote_validation_and_legacy_totals(self):
        for record in fixture()["campaign_creators"]:
            record.update(quote_unit_amount="0.1", quote_quantity=3, creator_quote="0.3")
            self.assertEqual("0.1", SimilarCreatorSearchService._quote_records([record])[0]["amount"])
        data = fixture()
        for row in data["campaign_creators"]:
            row.update(quote_unit="", quote_unit_amount="", quote_quantity="", creator_quote=400)
        self.assertEqual("total", self.scored(data)["dimensions"]["price"]["evidence"]["value_type"])
        data["campaign_creators"][1]["quote_currency"] = ""
        self.assertIsNone(self.scored(data)["dimensions"]["price"]["score"])

    def test_engagement_existing_analytics_formula_complete_metrics_and_actual_attribution(self):
        row = self.scored()["dimensions"]["engagement"]
        self.assertEqual(1, row["score"])
        pair = row["evidence"]["pairs"][0]
        self.assertEqual(12, pair["source_rate"])
        self.assertEqual("source_uid", pair["source_account_uid"])
        self.assertEqual("unknown", pair["freshness"])
        for change in ({"views": 0}, {"likes": None}, {"comments": "--"}, {"publications": []},
                       {"publications": [{"actual_account_id": "missing"}]},
                       {"publications": [{"actual_account_id": "candidate_account"}, {}]}):
            data = fixture()
            data["campaign_creators"][1].update(change)
            self.assertIsNone(self.scored(data)["dimensions"]["engagement"]["score"])

    def test_geography_available_subsignals_only_and_no_name_inference(self):
        for country, language, expected in (("Brazil", "Portuguese", 1), ("US", "Portuguese", .5),
                                            ("", "Portuguese", 1), ("", "", None), ("unknown", "--", None)):
            data = fixture()
            data["creators"][1].update(country=country, language=language, name="Brazil Portuguese")
            self.assertEqual(expected, self.scored(data)["dimensions"]["country_language"]["score"])

    def test_platform_different_valid_zero_and_missing_unavailable(self):
        for platform, expected in (("TikTok", 1), ("Instagram", 0), ("", None)):
            data = fixture()
            data["accounts"][1]["platform"] = platform
            row = self.scored(data)
            self.assertEqual(expected, row["dimensions"]["platform"]["score"])
            if platform != "TikTok":
                self.assertIsNone(row["dimensions"]["followers"]["score"])
                self.assertIsNone(row["dimensions"]["engagement"]["score"])

    def test_multi_account_best_pair_per_platform_and_er_uses_same_pair(self):
        data = fixture()
        data["accounts"].extend([
            account("source", "source_ig", "Instagram", followers=500000),
            account("candidate", "candidate_ig", "Instagram", followers=100000),
            account("candidate", "candidate_tt_far", "TikTok", account_id="far", followers=1000000),
        ])
        data["campaign_creators"][1]["publications"] = [{"actual_account_id": "far"}]
        row = self.scored(data)
        self.assertAlmostEqual(.6, row["dimensions"]["followers"]["score"])
        pairs = row["dimensions"]["followers"]["evidence"]["pairs"]
        self.assertEqual(["instagram", "tiktok"], [p["platform"].lower() for p in pairs])
        self.assertEqual("candidate_uid", pairs[1]["candidate_account_uid"])
        self.assertIsNone(row["dimensions"]["engagement"]["score"])
        self.assertEqual(15, row["dimensions"]["followers"]["nominal_weight"])

    def test_stable_order_score_then_weight_then_creator_id_without_prelimit(self):
        data = fixture()
        data["creators"].extend([creator("a_sparse", "zzz", tags="Gaming, Comedy"), creator("b_sparse", "aaa", tags="Gaming, Comedy")])
        search, repo = service(data)
        result = search.find_scored("source", limit=2)
        self.assertEqual(["candidate", "a_sparse"], [r["creator_id"] for r in result["candidates"]])
        self.assertEqual(3, result["total"])
        self.assertEqual(1, repo.calls)
        reversed_data = {key: list(reversed(value)) for key, value in data.items()}
        self.assertEqual(result, service(reversed_data)[0].find_scored("source", limit=2))

    def test_rank_uses_unrounded_value(self):
        rows = []
        for uid, amount in (("z", 999999), ("a", 999998)):
            rows.append({"creator_id": uid, "evidence": {"follower_pairs": [{
                "platform": "TikTok", "source_account_uid": "s", "candidate_account_uid": uid,
                "source_followers": 1000000, "candidate_followers": amount,
            }]}})
        ranked = CreatorSimilarityEngine().rank(rows)
        self.assertEqual(["z", "a"], [r["creator_id"] for r in ranked])
        self.assertEqual(ranked[0]["base_similarity_score"], ranked[1]["base_similarity_score"])

    def test_no_network_no_mutation_no_duplicate_creator(self):
        data = fixture()
        before = copy.deepcopy(data)
        search, repository = service(data)
        with patch.object(socket, "create_connection", side_effect=AssertionError("network forbidden")):
            first = search.find_scored("source")
            second = search.find_scored("source")
        self.assertEqual(first, second)
        self.assertEqual(before, repository.data)
        self.assertEqual(["candidate"], [r["creator_id"] for r in first["candidates"]])
        first["candidates"][0]["evidence"]["user_tag_sets"]["source"].clear()
        self.assertEqual(second, search.find_scored("source"))

    def test_unknown_archived_empty_and_invalid_limits(self):
        search, _ = service()
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                search.find_scored("source", limit=limit)
        with self.assertRaises(ValueError):
            search.find_scored("unknown")
        data = fixture()
        data["creators"][0]["archived_at"] = "2026-01-01"
        with self.assertRaises(ValueError):
            service(data)[0].find_scored("source")
        search, _ = service({"creators": [creator("source", "source")]})
        self.assertEqual([], search.find_scored("source")["candidates"])


class SimilarityAiTests(unittest.TestCase):
    def test_offline_provider_is_optional(self):
        search, _ = service()
        plain, requested = search.find_scored("source"), search.find_scored("source", include_ai=True)
        self.assertEqual(plain["candidates"], requested["candidates"])
        self.assertEqual("unavailable", requested["ai"]["status"])

    def test_ai_selects_only_existing_reasons_and_cannot_mutate_base(self):
        class Provider:
            def explain(self, candidates):
                self.received = copy.deepcopy(candidates)
                candidates[0]["base_similarity_score"] = -999
                return [{"creator_id": "candidate", "reason_ids": ["tag"]}]
        provider = Provider()
        search, _ = service(provider=provider)
        with patch.object(socket, "create_connection", side_effect=AssertionError("network")):
            result = search.find_scored("source", include_ai=True)
        self.assertEqual(100, result["candidates"][0]["base_similarity_score"])
        self.assertEqual(["candidate"], [r["creator_id"] for r in provider.received])
        self.assertEqual("available", result["ai"]["status"])
        self.assertEqual(result["candidates"][0]["why_recommended"][0]["text"], result["ai"]["explanations"][0]["text"])

    def test_unknown_ids_fabricated_metrics_and_provider_errors_fail_closed(self):
        rows = service()[0].find_scored("source")["candidates"]
        for response in ([{"creator_id": "invented", "reason_ids": ["tag"]}],
                         [{"creator_id": "candidate", "reason_ids": ["fake"]}],
                         [{"creator_id": "candidate", "reason_ids": ["tag"], "text": "10M followers"}], None):
            class Provider:
                def explain(self, payload):
                    if response is None:
                        raise RuntimeError("secret must not escape")
                    return response
            before = copy.deepcopy(rows)
            result = explain_candidates(rows, requested=True, provider=Provider())
            self.assertEqual("unavailable", result["status"])
            self.assertEqual(before, rows)
            self.assertNotIn("secret", json.dumps(result))

    def test_api_scored_default_optional_ai_and_query_validation(self):
        search, _ = service()
        class Handler:
            def _json(self, data, status=200): self.result = status, data
            def _error(self, error, status=400): self.result = status, {"error": error}
        context = {"services": {"creator": None, "agency": None, "creator_delete_impact": None,
                    "creator_hard_delete": None, "similar_creator_search": search}, "config": {}}
        for query, expected in (({}, 200), ({"include_ai": ["true"]}, 200),
                                ({"include_ai": ["oops"]}, 400), ({"limit": ["abc"]}, 400)):
            handler = Handler()
            creator_handler.handle(handler, {"method": "GET", "path": "/api/creator-library/source/similar", "query": query}, context)
            self.assertEqual(expected, handler.result[0])
            if expected == 200:
                self.assertEqual(100, handler.result[1]["candidates"][0]["base_similarity_score"])


class SimilaritySQLiteTests(unittest.TestCase):
    def test_real_sqlite_projection_decodes_tags_and_search_is_read_only(self):
        from test_support.runtime_sandbox import test_runtime_sandbox
        from test_pre_m8_excel_sqlite_migration import build_fixture, file_hash
        from storage.paths import SQLiteStoragePaths
        from storage.migration import ExcelToSQLiteMigrator
        from repository_factory import RepositoryFactory

        with test_runtime_sandbox("m8_2_sqlite") as runtime:
            paths = SQLiteStoragePaths.for_app_data(runtime.root / "storage_test")
            build_fixture(runtime.workbook_path)
            migrator = ExcelToSQLiteMigrator(paths)
            result = migrator.migrate(runtime.workbook_path)
            migrator.activate_synthetic(result)
            factory = RepositoryFactory.for_runtime(runtime.workbook_path, storage_paths=paths)
            workbook_hash = file_hash(runtime.workbook_path)
            revision = factory.store.business_revision()
            search = SimilarCreatorSearchService(factory.creator)
            result = search.find_scored("creator_0000")
            match = next(row for row in result["candidates"] if row["creator_id"] == "creator_0002")
            self.assertEqual(["group-0", "priority"], match["dimensions"]["tag"]["evidence"]["matched"])
            self.assertEqual(1, match["dimensions"]["tag"]["score"])
            self.assertEqual(revision, factory.store.business_revision())
            self.assertEqual(workbook_hash, file_hash(runtime.workbook_path))
