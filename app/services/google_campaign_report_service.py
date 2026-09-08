from __future__ import annotations

"""Assemble one deterministic Campaign report from M8.5 analytics."""

import json
from typing import Any


WORKSHEET_NAMES = ("Campaign Summary", "Publications", "Performance History")


def _cell(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return str(value)


def _json_cell(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class GoogleCampaignReportService:
    def __init__(self, campaign_repository, campaign_creator_repository, analytics_service) -> None:
        self._campaign_repository = campaign_repository
        self._campaign_creator_repository = campaign_creator_repository
        self._analytics_service = analytics_service

    def assemble(self, campaign_id: str) -> dict[str, Any]:
        campaign = self._campaign_repository.getCampaign(campaign_id)
        analytics = self._analytics_service.get_campaign_performance(campaign_id)
        relations = self._campaign_creator_repository.getCampaignCreators(
            campaign_id=campaign_id, include_archived=False
        )
        relations_by_id = {str(item.get("id") or ""): item for item in relations}
        publication_rows = []
        history_rows = []
        for publication in sorted(
            analytics.get("publications") or [], key=lambda item: str(item.get("publication_id") or "")
        ):
            relation = relations_by_id.get(str(publication.get("campaign_creator_id") or ""), {})
            publication_id = str(publication.get("publication_id") or "")
            relation_publications = {
                str(item.get("publication_id") or ""): item
                for item in relation.get("publications") or [] if isinstance(item, dict)
            }
            source_record = relation_publications.get(publication_id, {})
            series = sorted(
                publication.get("series") or [],
                key=lambda item: (str(item.get("observed_at") or ""), str(item.get("observation_id") or "")),
            )
            latest = series[-1] if series else {}
            planned_accounts = [
                str(item.get("account_uid") or "")
                for item in relation.get("execution_accounts") or []
                if str(item.get("account_uid") or "")
            ]
            publication_rows.append([
                campaign_id,
                publication.get("campaign_creator_id"),
                publication.get("creator_id"),
                publication_id,
                publication.get("platform"),
                publication.get("video_id"),
                publication.get("publication_url"),
                _json_cell(planned_accounts),
                publication.get("actual_account_uid"),
                _json_cell(relation.get("planned_publish_dates") or []),
                publication.get("published_at"),
                latest.get("views"), latest.get("likes"), latest.get("comments"),
                latest.get("shares"), latest.get("engagement_rate"),
                latest.get("observed_at"), source_record.get("source"),
                latest.get("source"), latest.get("confidence"),
            ])
            for observation in series:
                history_rows.append([
                    observation.get("observation_id"), publication_id, campaign_id,
                    publication.get("campaign_creator_id"), publication.get("creator_id"),
                    observation.get("observed_at"), observation.get("views"),
                    observation.get("likes"), observation.get("comments"),
                    observation.get("shares"), observation.get("engagement_rate"),
                    observation.get("source"), observation.get("confidence"),
                ])

        summary_rows = self._summary_rows(campaign, analytics)
        return {
            "campaign_id": campaign_id,
            "worksheets": [
                self._worksheet("Campaign Summary", ("field", "value", "coverage"), summary_rows),
                self._worksheet("Publications", (
                    "campaign_id", "campaign_creator_id", "creator_id", "publication_id",
                    "platform", "video_id", "canonical_url", "planned_account_uids",
                    "actual_account_uid", "planned_dates", "published_at", "latest_views",
                    "latest_likes", "latest_comments", "latest_shares", "latest_engagement_rate",
                    "latest_observed_at", "publication_source", "observation_source", "confidence",
                ), publication_rows),
                self._worksheet("Performance History", (
                    "observation_id", "publication_id", "campaign_id", "campaign_creator_id",
                    "creator_id", "observed_at", "views", "likes", "comments", "shares",
                    "engagement_rate", "observation_source", "confidence",
                ), history_rows),
            ],
        }

    def sync(self, campaign_id: str, client, spreadsheet: object) -> dict[str, Any]:
        report = self.assemble(campaign_id)
        return client.sync_managed_worksheets(spreadsheet, report["worksheets"])

    @staticmethod
    def _worksheet(title: str, headers: tuple[str, ...], rows: list[list[object]]) -> dict[str, Any]:
        return {
            "title": title,
            "schema_version": "1",
            "headers": list(headers),
            "rows": [[_cell(value) for value in row] for row in rows],
        }

    @staticmethod
    def _summary_rows(campaign: dict[str, Any], analytics: dict[str, Any]) -> list[list[object]]:
        totals = analytics.get("totals") or {}
        rows = [
            ["campaign_id", campaign.get("campaign_id"), ""],
            ["campaign_name", campaign.get("name"), ""],
            ["publication_count", analytics.get("publication_count"), ""],
        ]
        for metric in ("views", "likes", "comments"):
            item = totals.get(metric) or {}
            coverage = f"{item.get('valid_count', 0)}/{item.get('total_publications', 0)}"
            rows.append([f"total_{metric}", item.get("total"), coverage])
        rows.extend([
            ["average_er", analytics.get("average_er"), f"{analytics.get('valid_er_count', 0)}/{analytics.get('total_publications', 0)}"],
            ["top_creator", _json_cell(analytics.get("top_creator")) if analytics.get("top_creator") else "", ""],
            ["top_video", _json_cell(analytics.get("top_video")) if analytics.get("top_video") else "", ""],
            ["highest_er", _json_cell(analytics.get("highest_er")) if analytics.get("highest_er") else "", ""],
            ["fastest_growing", _json_cell(analytics.get("fastest_growing")) if analytics.get("fastest_growing") else "", ""],
            ["total_quote_by_currency", _json_cell(analytics.get("total_quote_by_currency") or {}), ""],
            ["total_cost_by_currency", _json_cell(analytics.get("total_cost_by_currency") or {}), ""],
            ["efficiency_by_currency", _json_cell(analytics.get("efficiency_by_currency") or {}), ""],
            ["roi", analytics.get("roi"), analytics.get("roi_reason") or ""],
            ["latest_observed_at", analytics.get("latest_observed_at"), ""],
        ])
        return rows
