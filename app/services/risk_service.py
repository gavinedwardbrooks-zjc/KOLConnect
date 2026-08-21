from __future__ import annotations

"""Business rules for missing publishing data and data-risk cards."""

import json
from datetime import date, datetime, timezone
from typing import Any, Protocol


class RiskSourcePort(Protocol):
    def read_risk_source(self) -> dict[str, list[dict[str, Any]]]: ...


class RiskService:
    def __init__(self, repository: RiskSourcePort) -> None:
        self.repository = repository

    @staticmethod
    def _text(value: object) -> str:
        return str(value or "").strip()

    @classmethod
    def _links_empty(cls, value: object) -> bool:
        if isinstance(value, (list, tuple)):
            return not any(cls._text(item) for item in value)
        text = cls._text(value)
        if not text:
            return True
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                return False
            return isinstance(parsed, list) and not any(cls._text(item) for item in parsed)
        return False

    @classmethod
    def _date(cls, value: object) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = cls._text(value)
        if not text:
            return None
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None

    @classmethod
    def _usable_email(cls, value: object) -> bool:
        text = cls._text(value)
        return bool(text and text != "未抓取到")

    @classmethod
    def _missing_publish_links(
        cls,
        source: dict[str, list[dict[str, Any]]],
        *,
        campaign_id: str = "",
        today: date,
    ) -> list[dict[str, str]]:
        campaigns = {
            cls._text(row.get("campaign_id")): row
            for row in source.get("campaigns", [])
            if cls._text(row.get("campaign_id"))
        }
        creators = {
            cls._text(row.get("creator_id")): row
            for row in source.get("creators", [])
            if cls._text(row.get("creator_id"))
        }
        records: list[dict[str, str]] = []
        for relation in source.get("campaign_creators", []):
            relation_campaign_id = cls._text(relation.get("campaign_id"))
            if campaign_id and relation_campaign_id != campaign_id:
                continue
            if cls._text(relation.get("stage")) != "completed":
                continue
            if not cls._links_empty(relation.get("publish_links")):
                continue
            publish_date = cls._text(relation.get("publish_date"))
            parsed_date = cls._date(publish_date)
            campaign = campaigns.get(relation_campaign_id, {})
            creator_id = cls._text(relation.get("creator_id"))
            creator = creators.get(creator_id, {})
            records.append({
                "campaign_id": relation_campaign_id,
                "campaign_name": cls._text(campaign.get("name")),
                "creator_id": creator_id,
                "creator_name": cls._text(creator.get("name")),
                "stage": "completed",
                "publish_links": "",
                "publish_date": publish_date,
                "risk_level": "high" if parsed_date is not None and parsed_date < today else "low",
            })
        records.sort(
            key=lambda row: (
                0 if row["risk_level"] == "high" else 1,
                row["publish_date"] or "9999-12-31",
                row["campaign_id"],
                row["creator_id"],
            )
        )
        return records

    def get_missing_publish_links(
        self, campaign_id: str, *, today: date | None = None
    ) -> list[dict[str, str]]:
        campaign_id = self._text(campaign_id)
        if not campaign_id:
            raise ValueError("Campaign ID 不能为空。")
        source = self.repository.read_risk_source()
        if not any(
            self._text(row.get("campaign_id")) == campaign_id
            for row in source.get("campaigns", [])
        ):
            raise ValueError("Campaign 不存在。")
        return self._missing_publish_links(
            source,
            campaign_id=campaign_id,
            today=today or datetime.now(timezone.utc).date(),
        )

    def get_risks(self, *, today: date | None = None) -> dict[str, Any]:
        source = self.repository.read_risk_source()
        effective_today = today or datetime.now(timezone.utc).date()
        cards: list[dict[str, Any]] = [
            {"risk_type": "missing_publish_links", **record}
            for record in self._missing_publish_links(source, today=effective_today)
        ]

        accounts_by_creator: dict[str, list[dict[str, Any]]] = {}
        for account in source.get("creator_accounts", []):
            creator_id = self._text(account.get("creator_id"))
            if creator_id:
                accounts_by_creator.setdefault(creator_id, []).append(account)
        for creator in source.get("creators", []):
            creator_id = self._text(creator.get("creator_id"))
            if not creator_id or self._text(creator.get("archived_at")):
                continue
            emails = [creator.get("email")]
            emails.extend(
                account.get("account_email")
                for account in accounts_by_creator.get(creator_id, [])
            )
            if not any(self._usable_email(email) for email in emails):
                cards.append({
                    "risk_type": "missing_creator_email",
                    "risk_level": "medium",
                    "creator_id": creator_id,
                    "creator_name": self._text(creator.get("name")),
                })

        for campaign in source.get("campaigns", []):
            campaign_id = self._text(campaign.get("campaign_id"))
            if not campaign_id or self._text(campaign.get("archived_at")):
                continue
            missing_fields = [
                field
                for field in ("product_id", "start_date")
                if not self._text(campaign.get(field))
            ]
            if missing_fields:
                cards.append({
                    "risk_type": "incomplete_campaign_data",
                    "risk_level": "medium",
                    "campaign_id": campaign_id,
                    "campaign_name": self._text(campaign.get("name")),
                    "missing_fields": missing_fields,
                })

        priority = {"high": 0, "medium": 1, "low": 2}
        cards.sort(
            key=lambda card: (
                priority.get(str(card.get("risk_level")), 3),
                str(card.get("risk_type") or ""),
                str(card.get("campaign_id") or ""),
                str(card.get("creator_id") or ""),
            )
        )
        summary = {"high": 0, "medium": 0, "low": 0}
        for card in cards:
            level = str(card.get("risk_level") or "")
            if level in summary:
                summary[level] += 1
        return {"summary": summary, "cards": cards}
