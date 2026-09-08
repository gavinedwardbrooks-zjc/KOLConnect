from __future__ import annotations

"""Publication-scoped performance refresh without platform-side polling."""

from datetime import datetime, timezone
from math import isfinite
from typing import Any, Callable
from uuid import uuid4


OBSERVATION_SOURCES = {"platform_api", "browser_capture", "page_structured_data", "manual"}
OBSERVATION_CONFIDENCE = {"low", "medium", "high"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class UnavailablePublicationMetricProvider:
    """Fail-closed production provider until a reliable platform path is configured."""

    def track(self, publication: dict[str, object]) -> dict[str, object]:
        platform = str(publication.get("platform") or "").strip()
        if platform.casefold() == "tiktok":
            return {"status": "CAPTURE_UNAVAILABLE", "reason": "TIKTOK_DEFERRED"}
        if platform.casefold() not in {"instagram", "youtube"}:
            return {"status": "UNSUPPORTED_PLATFORM", "reason": "UNSUPPORTED_PLATFORM"}
        return {"status": "CAPTURE_UNAVAILABLE", "reason": "SERVER_CAPTURE_UNAVAILABLE"}


class PublicationTrackingService:
    def __init__(
        self,
        campaign_creator_repository: Callable[[], Any],
        campaign_repository: Callable[[], Any],
        observation_repository: Callable[[], Any],
        metric_provider: Any | None = None,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        self._campaign_creators = campaign_creator_repository
        self._campaigns = campaign_repository
        self._observations = observation_repository
        self._provider = metric_provider or UnavailablePublicationMetricProvider()
        self._clock = clock

    @staticmethod
    def _publication(relation: dict[str, object], publication_id: str) -> dict[str, object]:
        for publication in relation.get("publications", []):
            if isinstance(publication, dict) and str(publication.get("publication_id") or "") == publication_id:
                return dict(publication)
        raise ValueError("实际发布内容不存在或不属于该合作关系。")

    def _resolve(self, campaign_creator_id: object, publication_id: object) -> tuple[dict[str, object], dict[str, object]]:
        relation_id = str(campaign_creator_id or "").strip()
        normalized_publication_id = str(publication_id or "").strip()
        if not relation_id or not normalized_publication_id:
            raise ValueError("CampaignCreator ID 和 Publication ID 不能为空。")
        relation = self._campaign_creators().getCampaignCreator(relation_id)
        return relation, self._publication(relation, normalized_publication_id)

    @staticmethod
    def _metric(value: object, name: str) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            raise ValueError(f"{name} 指标无效。")
        number = int(value)
        if number < 0 or float(value) != number:
            raise ValueError(f"{name} 指标无效。")
        return number

    @staticmethod
    def _engagement(value: object, views: int | None, likes: int | None, comments: int | None) -> float | None:
        if value not in (None, ""):
            number = float(value)
            if not isfinite(number) or number < 0:
                raise ValueError("engagement_rate 指标无效。")
            return round(number, 2)
        if views is None or views <= 0 or likes is None or comments is None:
            return None
        return round((likes + comments) / views * 100, 2)

    def refresh_publication(
        self,
        campaign_creator_id: object,
        publication_id: object,
        *,
        refresh_operation_id: object = "",
    ) -> dict[str, object]:
        relation, publication = self._resolve(campaign_creator_id, publication_id)
        platform = str(publication.get("platform") or "").strip()
        url = str(publication.get("actual_publish_url") or "").strip()
        if not platform or not url:
            return {
                "publication_id": str(publication_id), "platform": platform,
                "status": "UNTRACKABLE_IDENTITY", "reason": "PUBLICATION_IDENTITY_INCOMPLETE",
                "observation": None,
            }
        operation_id = str(refresh_operation_id or "").strip() or f"refresh_{uuid4().hex}"
        try:
            result = self._provider.track({**publication, "campaign_creator_id": relation.get("id")})
        except Exception:
            return {
                "publication_id": str(publication_id), "platform": platform,
                "status": "NETWORK_ERROR", "reason": "METRIC_PROVIDER_FAILED", "observation": None,
            }
        status = str(result.get("status") or "METRIC_UNAVAILABLE")
        if status != "SUCCESS":
            return {
                "publication_id": str(publication_id), "platform": platform, "status": status,
                "reason": str(result.get("reason") or status), "observation": None,
            }
        metrics = result.get("metrics") if isinstance(result.get("metrics"), dict) else {}
        views = self._metric(metrics.get("views"), "views")
        likes = self._metric(metrics.get("likes"), "likes")
        comments = self._metric(metrics.get("comments"), "comments")
        shares = self._metric(metrics.get("shares"), "shares")
        if all(value is None for value in (views, likes, comments, shares)):
            return {
                "publication_id": str(publication_id), "platform": platform,
                "status": "METRIC_UNAVAILABLE", "reason": "NO_RELIABLE_METRICS", "observation": None,
            }
        source = str(result.get("source") or "").strip()
        confidence = str(result.get("confidence") or "").strip()
        if source not in OBSERVATION_SOURCES or confidence not in OBSERVATION_CONFIDENCE:
            raise ValueError("成功的指标观察必须包含 source 和 confidence。")
        observed_at = str(result.get("observed_at") or self._clock()).strip()
        observation_id = f"observation_{uuid4().hex}"
        observation, created = self._observations().append({
            "observation_id": observation_id,
            "publication_id": str(publication_id),
            "refresh_operation_id": operation_id,
            "observed_at": observed_at,
            "views": views,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "engagement_rate": self._engagement(metrics.get("engagement_rate"), views, likes, comments),
            "source": source,
            "confidence": confidence,
        })
        return {
            "publication_id": str(publication_id), "platform": platform, "status": "SUCCESS",
            "reason": "", "observation": observation, "created": created,
        }

    def latest(self, campaign_creator_id: object, publication_id: object) -> dict[str, object] | None:
        self._resolve(campaign_creator_id, publication_id)
        return self._observations().latest(str(publication_id))

    def history(self, campaign_creator_id: object, publication_id: object) -> list[dict[str, object]]:
        self._resolve(campaign_creator_id, publication_id)
        return self._observations().history(str(publication_id))

    def refresh_campaign(self, campaign_id: object, *, refresh_operation_id: object = "") -> dict[str, object]:
        normalized_campaign_id = str(campaign_id or "").strip()
        self._campaigns().getCampaign(normalized_campaign_id)
        operation_id = str(refresh_operation_id or "").strip() or f"campaign_refresh_{uuid4().hex}"
        results: list[dict[str, object]] = []
        relations = self._campaign_creators().getCampaignCreators(campaign_id=normalized_campaign_id)
        for relation in relations:
            for publication in relation.get("publications", []):
                if not isinstance(publication, dict):
                    continue
                publication_id = str(publication.get("publication_id") or "")
                try:
                    result = self.refresh_publication(
                        relation.get("id"), publication_id,
                        refresh_operation_id=f"{operation_id}:{publication_id}",
                    )
                except Exception:
                    result = {
                        "publication_id": publication_id,
                        "platform": str(publication.get("platform") or ""),
                        "status": "FAILED", "reason": "REFRESH_FAILED", "observation": None,
                    }
                results.append(result)
        succeeded = sum(result["status"] == "SUCCESS" for result in results)
        failed = len(results) - succeeded
        status = "SUCCESS" if results and not failed else ("PARTIAL" if succeeded else "FAILED")
        return {
            "campaign_id": normalized_campaign_id, "refresh_operation_id": operation_id,
            "status": status, "requested": len(results), "succeeded": succeeded,
            "failed": failed, "results": results,
        }
