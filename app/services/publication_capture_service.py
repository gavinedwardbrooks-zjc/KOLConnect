from __future__ import annotations

"""Secure bridge from an explicit browser capture to append-only publication facts."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
import re
from math import isfinite
from typing import Any, Callable
from uuid import uuid4

from domain.creator_url_resolver import CreatorURLResolver
from local_storage_lock import shared_storage_lock


CONTRACT_VERSION = "publication-capture-v1"
CAPTURE_TTL_SECONDS = 600
PLATFORMS = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube"}
STATUSES = {"success", "partial", "insufficient", "failed"}
CONFIDENCE = {"low", "medium", "high"}
METRICS = ("views", "likes", "comments", "shares")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


class PublicationCaptureError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class PublicationCaptureService:
    def __init__(
        self,
        campaign_creator_repository: Callable[[], Any],
        creator_repository: Callable[[], Any],
        attempt_repository: Callable[[], Any],
        observation_repository: Callable[[], Any],
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._campaign_creators = campaign_creator_repository
        self._creators = creator_repository
        self._attempts = attempt_repository
        self._observations = observation_repository
        self._now = now

    @staticmethod
    def _publication(relation: dict[str, object], publication_id: str) -> dict[str, object]:
        for publication in relation.get("publications", []):
            if isinstance(publication, dict) and str(publication.get("publication_id") or "") == publication_id:
                return publication
        raise PublicationCaptureError("PUBLICATION_NOT_FOUND", "实际发布内容不存在或不属于该合作关系。", status=404)

    def _resolve(self, campaign_creator_id: object, publication_id: object) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        relation_id = str(campaign_creator_id or "").strip()
        normalized_publication_id = str(publication_id or "").strip()
        if not relation_id or not normalized_publication_id:
            raise PublicationCaptureError("CAPTURE_IDENTITY_REQUIRED", "缺少合作关系或发布内容身份。")
        try:
            relation = self._campaign_creators().getCampaignCreator(relation_id)
        except (RuntimeError, ValueError) as exc:
            raise PublicationCaptureError("CAMPAIGN_CREATOR_NOT_FOUND", "合作关系不存在。", status=404) from exc
        publication = self._publication(relation, normalized_publication_id)
        resolved = CreatorURLResolver.resolve_syntax(publication.get("actual_publish_url"))
        if resolved.get("input_type") != "content" or not resolved.get("video_id"):
            raise PublicationCaptureError("PUBLICATION_URL_UNSUPPORTED", "发布链接不是受支持的单条视频链接。")
        platform = str(resolved.get("platform") or "")
        stored_platform = str(publication.get("platform") or "").strip()
        stored_video_id = str(publication.get("video_id") or "").strip()
        if stored_platform and stored_platform.casefold() != platform.casefold():
            raise PublicationCaptureError("PUBLICATION_PLATFORM_MISMATCH", "发布平台身份不一致。")
        if stored_video_id and stored_video_id != str(resolved["video_id"]):
            raise PublicationCaptureError("PUBLICATION_VIDEO_MISMATCH", "发布视频身份不一致。")
        account_uid = str(publication.get("actual_account_uid") or "").strip()
        if not account_uid:
            raise PublicationCaptureError("PUBLICATION_ACCOUNT_REQUIRED", "请先为发布内容选择实际发布账号。")
        accounts = self._creators().getCreatorAccounts(str(relation.get("creator_id") or ""))
        account = next((item for item in accounts if str(item.get("account_uid") or "") == account_uid), None)
        if account is None or str(account.get("platform") or "").casefold() != platform.casefold():
            raise PublicationCaptureError("PUBLICATION_ACCOUNT_MISMATCH", "实际发布账号与 Creator 或平台不一致。")
        username = str(resolved.get("username") or "").lstrip("@").casefold()
        account_username = str(account.get("username") or "").lstrip("@").casefold()
        if username and account_username and username != account_username:
            raise PublicationCaptureError("PUBLICATION_ACCOUNT_MISMATCH", "视频 URL 的账号与实际发布账号不一致。")
        return relation, publication, resolved

    def create_request(self, campaign_creator_id: object, publication_id: object) -> dict[str, object]:
        relation, publication, resolved = self._resolve(campaign_creator_id, publication_id)
        now = self._now()
        token = secrets.token_urlsafe(32)
        request_id = f"capture_{uuid4().hex}"
        operation_id = f"browser_capture_{uuid4().hex}"
        attempt = self._attempts().create({
            "request_id": request_id,
            "publication_id": str(publication.get("publication_id") or publication_id),
            "campaign_creator_id": str(relation.get("id") or campaign_creator_id),
            "refresh_operation_id": operation_id,
            "platform": str(resolved["platform"]),
            "video_id": str(resolved["video_id"]),
            "canonical_url": str(resolved["canonical_url"]),
            "capability_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "started_at": _timestamp(now),
            "expires_at": _timestamp(now + timedelta(seconds=CAPTURE_TTL_SECONDS)),
            "capture_status": "pending",
            "collector_version": "",
            "contract_version": CONTRACT_VERSION,
            "safe_error_code": "",
            "completeness": "none",
            "field_provenance": "{}",
            "observation_id": None,
            "submission_count": 0,
        })
        return {
            **attempt,
            "capture_code": f"{request_id}.{token}",
            "expires_in": CAPTURE_TTL_SECONDS,
        }

    @staticmethod
    def _field_state(payload: dict[str, object], name: str) -> tuple[int | None, dict[str, object]]:
        raw = payload.get(name)
        state = raw if isinstance(raw, dict) else {"value": raw}
        value = state.get("value")
        if value in (None, ""):
            return None, {
                "source": str(state.get("source") or "missing"),
                "confidence": str(state.get("confidence") or "low"),
                "missing_reason": str(state.get("missing_reason") or "not_exposed"),
            }
        if isinstance(value, bool):
            raise PublicationCaptureError("INVALID_METRIC", f"{name} 指标无效。")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise PublicationCaptureError("INVALID_METRIC", f"{name} 指标无效。") from exc
        if number < 0 or float(value) != number:
            raise PublicationCaptureError("INVALID_METRIC", f"{name} 指标无效。")
        confidence = str(state.get("confidence") or "").lower()
        source = str(state.get("source") or "").strip()
        if confidence not in CONFIDENCE or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", source):
            raise PublicationCaptureError("METRIC_PROVENANCE_REQUIRED", f"{name} 缺少来源或置信度。")
        return number, {"source": source, "confidence": confidence, "missing_reason": ""}

    def submit_result(self, payload: dict[str, object]) -> dict[str, object]:
        # Serialize expiry polling with the observation/attempt write pair.
        with shared_storage_lock():
            return self._submit_result_locked(payload)

    def _submit_result_locked(self, payload: dict[str, object]) -> dict[str, object]:
        request_id = str(payload.get("request_id") or "").strip()
        token = str(payload.get("capability_token") or "")
        attempt = self._attempts().get_with_secret(request_id) if request_id else None
        if attempt is None or not token:
            raise PublicationCaptureError("CAPTURE_CAPABILITY_INVALID", "采集授权无效。", status=403)
        supplied = hashlib.sha256(token.encode("utf-8")).hexdigest()
        if not hmac.compare_digest(str(attempt.get("capability_hash") or ""), supplied):
            raise PublicationCaptureError("CAPTURE_CAPABILITY_INVALID", "采集授权无效。", status=403)
        if str(payload.get("contract_version") or "") != CONTRACT_VERSION:
            raise PublicationCaptureError("CAPTURE_CONTRACT_UNSUPPORTED", "采集协议版本不受支持。")
        if int(attempt.get("submission_count") or 0) > 0:
            observation_id = str(attempt.get("observation_id") or "")
            return {"attempt": self._attempts().get(request_id), "observation": self._observations().get(observation_id) if observation_id else None, "replayed": True}
        now = self._now()
        if now >= _parse_timestamp(attempt["expires_at"]):
            completed = self._attempts().complete(
                request_id, capture_status="expired", completed_at=_timestamp(now), collector_version="",
                safe_error_code="CAPTURE_REQUEST_EXPIRED", completeness="none", field_provenance={}, observation_id=None,
            )
            return {"attempt": completed, "observation": None, "replayed": False}
        relation, publication, resolved = self._resolve(attempt["campaign_creator_id"], attempt["publication_id"])
        page = CreatorURLResolver.resolve_syntax(payload.get("page_url"))
        expected = (str(attempt["platform"]).casefold(), str(attempt["video_id"]))
        actual = (str(page.get("platform") or "").casefold(), str(page.get("video_id") or ""))
        claimed = (str(payload.get("platform") or "").casefold(), str(payload.get("video_id") or ""))
        if page.get("input_type") != "content" or actual != expected or claimed != expected:
            raise PublicationCaptureError("CAPTURE_TARGET_MISMATCH", "当前页面不是此次授权的目标视频。", status=403)
        if str(resolved.get("video_id")) != expected[1] or str(publication.get("publication_id")) != str(attempt["publication_id"]):
            raise PublicationCaptureError("CAPTURE_TARGET_STALE", "发布内容身份已变化，请重新发起采集。", status=409)
        status = str(payload.get("capture_status") or "").lower()
        if status not in STATUSES:
            raise PublicationCaptureError("CAPTURE_STATUS_INVALID", "采集状态无效。")
        metrics_payload = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        values: dict[str, int | None] = {}
        provenance: dict[str, object] = {}
        for name in METRICS:
            values[name], provenance[name] = self._field_state(metrics_payload, name)
        available = [name for name, value in values.items() if value is not None]
        if status in {"success", "partial"} and not available:
            status = "insufficient"
        elif available and status in {"insufficient", "failed"}:
            status = "partial"
        completeness = "complete" if len(available) == len(METRICS) else ("partial" if available else "none")
        observation = None
        if available:
            confidence_order = {"low": 0, "medium": 1, "high": 2}
            aggregate_confidence = min((str(provenance[name]["confidence"]) for name in available), key=confidence_order.get)
            views, likes, comments = values["views"], values["likes"], values["comments"]
            engagement = None
            if views is not None and views > 0 and likes is not None and comments is not None:
                engagement = round((likes + comments) / views * 100, 2)
                if not isfinite(engagement):
                    engagement = None
            observation, _ = self._observations().append({
                "observation_id": f"observation_{uuid4().hex}",
                "publication_id": str(attempt["publication_id"]),
                "refresh_operation_id": str(attempt["refresh_operation_id"]),
                "observed_at": _timestamp(now),
                **values,
                "engagement_rate": engagement,
                "source": "browser_capture",
                "confidence": aggregate_confidence,
            })
        raw_error = str(payload.get("safe_error_code") or "NO_RELIABLE_METRICS")
        safe_error = "" if available else (raw_error if re.fullmatch(r"[A-Z0-9_]{1,80}", raw_error) else "CAPTURE_FAILED")
        completed = self._attempts().complete(
            request_id, capture_status=status, completed_at=_timestamp(now),
            collector_version=str(payload.get("collector_version") or "")[:40], safe_error_code=safe_error,
            completeness=completeness, field_provenance=provenance,
            observation_id=str(observation.get("observation_id")) if observation else None,
        )
        return {"attempt": completed, "observation": observation, "replayed": False}

    def get_request(self, request_id: object) -> dict[str, object]:
        with shared_storage_lock():
            attempt = self._attempts().get(str(request_id or "").strip())
            if attempt is None:
                raise PublicationCaptureError("CAPTURE_REQUEST_NOT_FOUND", "采集任务不存在。", status=404)
            if attempt.get("capture_status") == "pending" and self._now() >= _parse_timestamp(attempt["expires_at"]):
                attempt = self._attempts().complete(
                    str(attempt["request_id"]), capture_status="expired", completed_at=_timestamp(self._now()),
                    collector_version="", safe_error_code="CAPTURE_REQUEST_EXPIRED", completeness="none",
                    field_provenance={}, observation_id=None,
                )
            observation = self._observations().get(str(attempt["observation_id"])) if attempt.get("observation_id") else None
            return {"attempt": attempt, "observation": observation}
