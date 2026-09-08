from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.campaign_creator_service import CampaignCreatorService  # noqa: E402
from http_handlers import campaign_handler  # noqa: E402
from campaign_creator_repository import CampaignCreatorRepository  # noqa: E402


class _CreatorRepository:
    def __init__(self, accounts: list[dict[str, object]]) -> None:
        self.accounts = accounts

    def getCreatorAccounts(self):
        return [dict(account) for account in self.accounts]


class _CampaignCreatorRepository:
    def __init__(self, relation: dict[str, object] | None = None) -> None:
        self.relation = relation or {
            "id": "relation_1",
            "creator_id": "creator_1",
            "publications": [],
        }
        self.created: list[dict[str, object]] = []
        self.updated: list[dict[str, object]] = []

    def createCampaignCreator(self, payload):
        self.created.append(dict(payload))
        return dict(payload)

    def getCampaignCreator(self, record_id):
        if record_id != self.relation["id"]:
            raise ValueError("Campaign 达人关系不存在。")
        return dict(self.relation)

    def updateCampaignCreator(self, record_id, payload):
        if record_id != self.relation["id"]:
            raise ValueError("Campaign 达人关系不存在。")
        self.updated.append(dict(payload))
        self.relation = {**self.relation, **payload}
        return dict(self.relation)


class CampaignPublicationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.accounts = [
            {
                "account_id": "tiktok_alice",
                "account_uid": "tiktok|alice",
                "creator_id": "creator_1",
                "platform": "TikTok",
                "profile_url": "https://www.tiktok.com/@alice",
            },
            {
                "account_id": "instagram_alice",
                "account_uid": "instagram|alice",
                "creator_id": "creator_1",
                "platform": "Instagram",
                "profile_url": "https://www.instagram.com/alice/",
            },
            {
                "account_id": "tiktok_other",
                "account_uid": "tiktok|other",
                "creator_id": "creator_2",
                "platform": "TikTok",
                "profile_url": "https://www.tiktok.com/@other",
            },
        ]
        self.campaign_repository = _CampaignCreatorRepository()
        self.service = CampaignCreatorService(
            lambda: self.campaign_repository,
            lambda: None,
            lambda: _CreatorRepository(self.accounts),
        )

    def test_resolves_tiktok_content_and_never_uses_planned_account_as_actual(self) -> None:
        result = self.service.create_campaign_creator({
            "campaign_id": "campaign_1",
            "creator_id": "creator_1",
            "account_ids": ["instagram_alice"],
            "planned_publish_dates": ["2026-10-01"],
            "publications": [{
                "actual_publish_url": "https://www.tiktok.com/@alice/video/123456?lang=en",
                "actual_published_at": "",
                "source": "manual",
            }],
        })

        publication = result["publications"][0]
        self.assertEqual("https://www.tiktok.com/@alice/video/123456", publication["actual_publish_url"])
        self.assertEqual("TikTok", publication["platform"])
        self.assertEqual("123456", publication["video_id"])
        self.assertEqual("tiktok_alice", publication["actual_account_id"])
        self.assertEqual("", publication["actual_published_at"])
        self.assertNotEqual("instagram_alice", publication["actual_account_id"])

    def test_partial_content_identity_keeps_actual_account_unknown(self) -> None:
        result = self.service.create_campaign_creator({
            "campaign_id": "campaign_1",
            "creator_id": "creator_1",
            "account_ids": ["instagram_alice"],
            "publications": [
                {"actual_publish_url": "https://www.instagram.com/reel/REEL_456/"},
                {"actual_publish_url": "https://www.youtube.com/shorts/short_456"},
            ],
        })

        self.assertEqual("", result["publications"][0].get("actual_account_id", ""))
        self.assertEqual("", result["publications"][1].get("actual_account_id", ""))
        self.assertEqual("Instagram", result["publications"][0]["platform"])
        self.assertEqual("YouTube", result["publications"][1]["platform"])

    def test_cross_creator_resolved_account_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "不一致"):
            self.service.create_campaign_creator({
                "campaign_id": "campaign_1",
                "creator_id": "creator_1",
                "publications": [{
                    "actual_publish_url": "https://www.tiktok.com/@other/video/654321",
                }],
            })
        self.assertEqual([], self.campaign_repository.created)

    def test_add_and_delete_publication_preserve_multiple_records(self) -> None:
        self.campaign_repository.relation["publications"] = [
            {"publication_id": "publication_one", "actual_publish_url": "https://www.tiktok.com/@alice/video/1"}
        ]
        updated = self.service.add_publication("relation_1", {
            "actual_publish_url": "https://www.tiktok.com/@alice/video/2",
        })
        self.assertEqual(2, len(updated["publications"]))
        self.assertEqual(2, len(self.campaign_repository.updated[-1]["publications"]))

        deleted = self.service.delete_publication("relation_1", "publication_one")
        self.assertTrue(deleted["deleted"])
        self.assertEqual(1, len(self.campaign_repository.updated[-1]["publications"]))

    def test_publication_routes_use_the_existing_campaign_creator_service(self) -> None:
        class Handler:
            def _json(self, payload, status=200):
                self.payload = payload
                self.status = status

            def _ok(self, **payload):
                self.payload = {"ok": True, **payload}
                self.status = 200

            def _repository_error(self, exc):
                raise exc

        handler = Handler()
        context = {
            "repositories": {"campaign_creator": lambda: self.campaign_repository},
            "services": {"campaign_creator": self.service},
        }
        get_request = {
            "method": "GET",
            "path": "/api/campaign-creators/relation_1/publications",
            "query": {},
            "get_payload": lambda: {},
        }
        self.assertTrue(campaign_handler.handle(handler, get_request, context))
        self.assertEqual([], handler.payload["publications"])

        post_request = {
            **get_request,
            "method": "POST",
            "get_payload": lambda: {
                "actual_publish_url": "https://www.tiktok.com/@alice/video/777"
            },
        }
        self.assertTrue(campaign_handler.handle(handler, post_request, context))
        self.assertEqual(201, handler.status)
        publication = handler.payload["campaign_creator"]["publications"][0]
        self.assertEqual("https://www.tiktok.com/@alice/video/777", publication["actual_publish_url"])

        self.campaign_repository.relation["publications"][0]["publication_id"] = "publication_777"
        delete_request = {
            **get_request,
            "method": "DELETE",
            "path": "/api/campaign-creators/relation_1/publications/publication_777",
        }
        self.assertTrue(campaign_handler.handle(handler, delete_request, context))
        self.assertTrue(handler.payload["deleted"])

    def test_read_projection_keeps_unknown_actual_fields_nullable(self) -> None:
        response = CampaignCreatorRepository._campaign_creator_response(
            {
                "creator_id": "creator_1",
                "publications": [{
                    "publication_id": "publication_1",
                    "actual_publish_url": "https://www.youtube.com/shorts/short_1",
                    "actual_account_id": "",
                    "actual_published_at": "",
                }],
            },
            {"creator_1": {"creator_id": "creator_1", "name": "Creator One"}},
            {},
            {},
        )
        publication = response["publications"][0]
        self.assertIsNone(publication["actual_account_uid"])
        self.assertIsNone(publication["published_at"])
        self.assertIsNone(publication["actual_account"])


if __name__ == "__main__":
    unittest.main()
