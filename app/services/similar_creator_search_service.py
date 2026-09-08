from __future__ import annotations

"""Deterministic, local-only Creator candidate discovery for M8.1."""

from collections import defaultdict
from decimal import Decimal
import json
from typing import Any, Callable, Protocol

from domain.normalization import (
    normalize_country,
    normalize_followers,
    normalize_number,
    normalize_tags,
)
from domain.money import currency_code, optional_decimal, positive_quantity, quote_unit


class SimilarCreatorReader(Protocol):
    def getSimilarCreatorSourceData(self) -> dict[str, list[dict[str, Any]]]: ...


class SimilarCreatorSearchService:
    """Reuse local candidate evidence for unscored and M8.2 scored responses."""

    def __init__(self, repository_provider: Callable[[], SimilarCreatorReader], *, explanation_provider=None, historical_performance_provider=None) -> None:
        self._repository_provider = repository_provider
        self._explanation_provider = explanation_provider
        self._historical_performance_provider = historical_performance_provider

    def find_similar(self, creator_id: str, *, limit: int = 30) -> dict[str, Any]:
        if not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间。")
        result = self._discover(creator_id)
        result["candidates"] = result["candidates"][:limit]
        return result

    def find_scored(self, creator_id: str, *, limit: int = 30, include_ai: bool = False) -> dict[str, Any]:
        from services.creator_similarity_engine import CreatorSimilarityEngine
        from services.similarity_explanation import explain_candidates

        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit 必须在 1 到 100 之间。")
        result = self._discover(creator_id)
        # Rank the whole discovered set before applying the presentation limit.
        result["candidates"] = CreatorSimilarityEngine().rank(result["candidates"])[:limit]
        if self._historical_performance_provider is not None:
            try:
                histories = self._historical_performance_provider(
                    [candidate["creator_id"] for candidate in result["candidates"]]
                )
            except RuntimeError:
                histories = {}
            for candidate in result["candidates"]:
                history = histories.get(candidate["creator_id"])
                if history is None:
                    continue
                candidate["historical_performance_summary"] = history
                candidate["historical_performance_evidence"] = {
                    "source": "publication_performance_observations",
                    "cooperation_count": history.get("cooperation_count", 0),
                    "publication_count": history.get("publication_count", 0),
                    "average_latest_views": history.get("average_latest_views"),
                    "average_latest_er": history.get("average_latest_er"),
                }
        result["ai"] = explain_candidates(result["candidates"], requested=include_ai, provider=self._explanation_provider)
        return result

    def _discover(self, creator_id: str) -> dict[str, Any]:

        source_data = self._repository_provider().getSimilarCreatorSourceData()
        creators = {
            str(row.get("creator_id") or "").strip(): dict(row)
            for row in source_data.get("creators", [])
            if str(row.get("creator_id") or "").strip()
        }
        source_id = str(creator_id or "").strip()
        source_creator = creators.get(source_id)
        if source_creator is None:
            raise ValueError("未找到达人记录。")
        if self._is_archived(source_creator):
            raise ValueError("已归档达人不能用于相似达人搜索。")

        accounts = self._group(source_data.get("accounts", []), "creator_id")
        snapshots = self._latest_snapshots(source_data.get("snapshots", []))
        relations = self._group([
            row for row in source_data.get("campaign_creators", []) if not self._is_archived(row)
        ], "creator_id")
        candidates: list[dict[str, Any]] = []
        for candidate_id, candidate in creators.items():
            if candidate_id == source_id or self._is_archived(candidate):
                continue
            evidence = self._evidence(source_creator, candidate, accounts, snapshots, relations)
            if evidence["matched_dimensions"]:
                candidates.append({
                    "creator_id": candidate_id,
                    "creator_name": str(candidate.get("name") or ""),
                    "evidence": evidence,
                })

        candidates.sort(key=lambda row: (
            -len(row["evidence"]["matched_dimensions"]),
            str(row["creator_name"]).casefold(),
            row["creator_id"],
        ))
        return {
            "source_creator_id": source_id,
            "candidates": candidates,
            "total": len(candidates),
        }

    @staticmethod
    def _is_archived(row: dict[str, Any]) -> bool:
        return bool(str(row.get("archived_at") or "").strip())

    @staticmethod
    def _group(rows: list[dict[str, Any]], field: str) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            value = str(row.get(field) or "").strip()
            if value:
                result[value].append(dict(row))
        return result

    @staticmethod
    def _latest_snapshots(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            account_uid = str(row.get("account_uid") or "").strip()
            def order(item):
                return (str(item.get("captured_at") or ""), json.dumps(item, sort_keys=True, default=str))

            # Equal capture timestamps must not make scoring depend on row order.
            if account_uid and (account_uid not in latest or order(row) > order(latest[account_uid])):
                latest[account_uid] = dict(row)
        return latest

    def _evidence(self, source, candidate, accounts, snapshots, relations) -> dict[str, Any]:
        source_id = str(source.get("creator_id") or "")
        candidate_id = str(candidate.get("creator_id") or "")
        source_accounts = accounts.get(source_id, [])
        candidate_accounts = accounts.get(candidate_id, [])
        source_user_tags = self._user_tags(source.get("tags"))
        candidate_user_tags = self._user_tags(candidate.get("tags"))
        user_tags = self._tag_overlap(source_user_tags, candidate_user_tags)
        source_ai_tags = self._ai_tags(source, source_accounts)
        candidate_ai_tags = self._ai_tags(candidate, candidate_accounts)
        ai_tags = self._tag_overlap(
            source_ai_tags,
            candidate_ai_tags,
        )
        follower_pairs = self._platform_matches(source_accounts, candidate_accounts, snapshots)
        platform_accounts = [
            {key: value for key, value in row.items() if key not in {"source_followers", "candidate_followers"}}
            for row in follower_pairs
        ]
        follower_accounts = [row for row in platform_accounts if row["follower_proximity"] is True]
        source_country = normalize_country(source.get("country"))
        candidate_country = normalize_country(candidate.get("country"))
        country = source_country if source_country and source_country == candidate_country else None
        source_language = str(source.get("language") or "").strip()
        candidate_language = str(candidate.get("language") or "").strip()
        language = source_language if source_language and source_language.casefold() == candidate_language.casefold() else None
        source_content = normalize_tags(source.get("content_category"))
        candidate_content = normalize_tags(candidate.get("content_category"))
        content_category = self._tag_overlap(source_content, candidate_content)
        quote = self._quote_evidence(relations.get(source_id, []), relations.get(candidate_id, []))
        engagement = self._engagement_evidence(
            relations.get(source_id, []),
            relations.get(candidate_id, []),
            source_accounts,
            candidate_accounts,
        )

        matched_dimensions = [
            dimension
            for dimension, matched in (
                ("user_tags", bool(user_tags)),
                ("ai_tags", bool(ai_tags)),
                ("platform", bool(platform_accounts)),
                ("followers", bool(follower_accounts)),
                ("country", country is not None),
                ("language", language is not None),
                ("content_category", bool(content_category)),
                ("quote", quote["comparable"]),
                ("engagement", engagement["available"]),
            )
            if matched
        ]
        return {
            "matched_dimensions": matched_dimensions,
            "user_tags": user_tags,
            "ai_tags": ai_tags,
            "user_tag_sets": {"source": source_user_tags, "candidate": candidate_user_tags},
            "ai_tag_sets": {"source": source_ai_tags, "candidate": candidate_ai_tags},
            "platform_accounts": platform_accounts,
            "follower_pairs": follower_pairs,
            "platforms": {
                "source": sorted({str(row.get("platform") or "").strip() for row in source_accounts if str(row.get("platform") or "").strip()}, key=str.casefold),
                "candidate": sorted({str(row.get("platform") or "").strip() for row in candidate_accounts if str(row.get("platform") or "").strip()}, key=str.casefold),
            },
            "follower_accounts": follower_accounts,
            "country": country,
            "language": language,
            "country_language": {
                "source_country": source_country,
                "candidate_country": candidate_country,
                "source_language": source_language or None,
                "candidate_language": candidate_language or None,
            },
            "content_category": content_category,
            "content_category_sets": {"source": source_content, "candidate": candidate_content},
            "quote": quote,
            "engagement": engagement,
        }

    @staticmethod
    def _user_tags(value):
        # SQLite's workbook projection serializes creator_tags as a JSON list;
        # legacy imports can still carry comma-separated text.
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                value = json.loads(value)
            except ValueError:
                return []
            if not isinstance(value, list) or any(not isinstance(tag, str) for tag in value):
                return []
        return normalize_tags(value)

    @staticmethod
    def _tag_overlap(left: object, right: object) -> list[str]:
        left_tags = normalize_tags(left)
        right_keys = {tag.casefold() for tag in normalize_tags(right)}
        return [tag for tag in left_tags if tag.casefold() in right_keys]

    @staticmethod
    def _ai_tags(creator: dict[str, Any], accounts: list[dict[str, Any]]) -> list[str]:
        values = []
        category = str(creator.get("content_category") or "").strip()
        if category:
            values.append(f"category:{category}")
        values.extend(
            f"platform:{row.get('platform')}" for row in accounts
            if str(row.get("platform") or "").strip()
        )
        return normalize_tags(values)

    @staticmethod
    def _country_match(left: object, right: object) -> str | None:
        left_country = normalize_country(left)
        right_country = normalize_country(right)
        return left_country if left_country and left_country == right_country else None

    @staticmethod
    def _text_match(left: object, right: object) -> str | None:
        left_value = str(left or "").strip()
        right_value = str(right or "").strip()
        return left_value if left_value and left_value.casefold() == right_value.casefold() else None

    @staticmethod
    def _platform_matches(source_accounts, candidate_accounts, snapshots) -> list[dict[str, Any]]:
        matches = []
        for source_account in source_accounts:
            platform = str(source_account.get("platform") or "").strip()
            if platform.casefold() in {"", "--", "unknown", "none", "n/a", "unavailable"}:
                continue
            for candidate_account in candidate_accounts:
                candidate_platform = str(candidate_account.get("platform") or "").strip()
                if platform.casefold() != candidate_platform.casefold():
                    continue
                source_followers = SimilarCreatorSearchService._account_followers(source_account, snapshots)
                candidate_followers = SimilarCreatorSearchService._account_followers(candidate_account, snapshots)
                matches.append({
                    "platform": platform,
                    "source_account_uid": str(source_account.get("account_uid") or ""),
                    "candidate_account_uid": str(candidate_account.get("account_uid") or ""),
                    "source_followers": source_followers,
                    "candidate_followers": candidate_followers,
                    "follower_proximity": SimilarCreatorSearchService._followers_close(source_followers, candidate_followers),
                })
        return matches

    @staticmethod
    def _account_followers(account: dict[str, Any], snapshots: dict[str, dict[str, Any]]) -> int | None:
        account_value = normalize_followers(account.get("followers"))
        if account_value is not None:
            return account_value
        snapshot = snapshots.get(str(account.get("account_uid") or ""), {})
        return normalize_followers(snapshot.get("followers"))

    @staticmethod
    def _followers_close(left: int | None, right: int | None) -> bool | None:
        """Use a simple two-times candidate band; missing and zero are not inferred."""
        if left is None or right is None or left <= 0 or right <= 0:
            return None
        return max(left, right) <= min(left, right) * 2

    @staticmethod
    def _quote_evidence(source_rows, candidate_rows) -> dict[str, Any]:
        source_values = SimilarCreatorSearchService._quote_records(source_rows)
        candidate_values = SimilarCreatorSearchService._quote_records(candidate_rows)
        comparable = any(
            source["currency"] == candidate["currency"]
            and source["pricing_unit"] == candidate["pricing_unit"]
            for source in source_values
            for candidate in candidate_values
        )
        return {
            "available": bool(source_values and candidate_values),
            "comparable": comparable,
            "reason": "same_currency_and_pricing_unit" if comparable else "unavailable_or_not_comparable",
            "source_contracts": [dict(row) for row in source_values],
            "candidate_contracts": [dict(row) for row in candidate_values],
        }

    @staticmethod
    def _quote_records(rows) -> list[dict[str, Any]]:
        records = []
        for row in rows:
            try:
                currency = currency_code(row.get("quote_currency"), "quote", required=True)
                total = optional_decimal(row.get("creator_quote"), "quote")
                unit_amount = optional_decimal(row.get("quote_unit_amount"), "quote")
                quantity = positive_quantity(row.get("quote_quantity"))
                pricing_unit = quote_unit(row.get("quote_unit"))
            except ValueError:
                continue
            if total is not None and not pricing_unit and unit_amount is None and quantity == "":
                records.append({
                    "currency": currency,
                    "pricing_unit": "legacy_total",
                    "amount": str(total),
                    "value_type": "total",
                })
            elif (
                total is not None
                and unit_amount is not None
                and isinstance(quantity, int)
                and quantity > 0
                and pricing_unit
                and total == unit_amount * Decimal(quantity)
            ):
                records.append({
                    "currency": currency,
                    "pricing_unit": pricing_unit,
                    "amount": str(unit_amount),
                    "value_type": "unit_amount",
                })
        return records

    @staticmethod
    def _engagement_evidence(source_rows, candidate_rows, source_accounts, candidate_accounts) -> dict[str, Any]:
        source_rates = SimilarCreatorSearchService._engagement_records(source_rows, source_accounts)
        candidate_rates = SimilarCreatorSearchService._engagement_records(candidate_rows, candidate_accounts)
        return {
            # Preserve the M8.1 broad discovery signal. Scoring requires the
            # separately attributed records below, never this availability flag.
            "available": all(any(
                normalize_number(row.get("views")) is not None
                and normalize_number(row.get("views")) > 0
                and normalize_number(row.get("likes")) is not None
                and normalize_number(row.get("comments")) is not None
                for row in rows
            ) for rows in (source_rows, candidate_rows)),
            "source": "recorded_campaign_creator_metrics",
            "source_records": source_rates,
            "candidate_records": candidate_rates,
        }

    @staticmethod
    def _engagement_records(rows, accounts) -> list[dict[str, Any]]:
        account_by_id = {
            str(row.get("account_id") or "").strip(): row
            for row in accounts
            if str(row.get("account_id") or "").strip()
        }
        records = []
        for row in rows:
            # Planned execution accounts do not prove actual metric attribution.
            publications = row.get("publications")
            if isinstance(publications, str):
                try:
                    publications = json.loads(publications)
                except ValueError:
                    publications = None
            if not isinstance(publications, list) or not publications or any(
                not isinstance(item, dict) or not item.get("actual_account_id") for item in publications
            ):
                continue
            account_ids = sorted({str(item["actual_account_id"]) for item in publications})
            if len(account_ids) != 1 or account_ids[0] not in account_by_id:
                continue
            views = normalize_number(row.get("views"))
            likes = normalize_number(row.get("likes"))
            comments = normalize_number(row.get("comments"))
            if views is not None and views > 0 and likes is not None and comments is not None:
                account = account_by_id[account_ids[0]]
                records.append({
                    "account_uid": str(account.get("account_uid") or ""),
                    "platform": str(account.get("platform") or "").strip(),
                    "rate": (float(likes) + float(comments)) / float(views) * 100,
                    "views": views, "likes": likes, "comments": comments,
                    "relation_id": str(row.get("id") or ""),
                    "record_updated_at": row.get("updated_at") or None,
                    "measured_at": None,
                    "freshness": "unknown",
                    "source": "campaign_creator_recorded_metrics",
                })
        return records
