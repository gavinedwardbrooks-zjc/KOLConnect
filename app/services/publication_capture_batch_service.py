from __future__ import annotations

"""Bounded, user-authorized queue for one-click Campaign publication capture."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import secrets
from typing import Any, Callable
from uuid import uuid4

from local_storage_lock import shared_storage_lock
from services.publication_capture_service import PublicationCaptureError


BATCH_TTL_SECONDS = 2 * 60 * 60
CLAIM_TTL_SECONDS = 2 * 60
ITEM_LEASE_SECONDS = 90
FINAL_ITEM_STATUSES = {"success", "partial", "insufficient", "failed", "skipped", "cancelled"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse(value: object) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PublicationCaptureBatchService:
    def __init__(
        self,
        campaign_repository: Callable[[], Any],
        campaign_creator_repository: Callable[[], Any],
        batch_repository: Callable[[], Any],
        capture_service: Callable[[], Any],
        *,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._campaigns = campaign_repository
        self._relations = campaign_creator_repository
        self._batches = batch_repository
        self._capture = capture_service
        self._now = now

    def create(self, campaign_id: object) -> dict[str, object]:
        normalized = str(campaign_id or "").strip()
        if not normalized:
            raise PublicationCaptureError("CAMPAIGN_REQUIRED", "缺少 Campaign 身份。")
        try:
            self._campaigns().getCampaign(normalized)
        except (RuntimeError, ValueError) as exc:
            raise PublicationCaptureError("CAMPAIGN_NOT_FOUND", "Campaign 不存在。", status=404) from exc
        existing = self._batches().active_for_campaign(normalized)
        if existing:
            raise PublicationCaptureError("BATCH_ALREADY_ACTIVE", "当前 Campaign 已有未完成的一键采集任务。", status=409)

        now = self._now()
        batch_id = f"publication_batch_{uuid4().hex}"
        claim_token = secrets.token_urlsafe(32)
        items: list[dict[str, object]] = []
        seen_videos: dict[tuple[str, str], str] = {}
        position = 0
        for relation in reversed(self._relations().getCampaignCreators(campaign_id=normalized)):
            relation_id = str(relation.get("id") or "")
            for publication in relation.get("publications", []):
                if not isinstance(publication, dict):
                    continue
                publication_id = str(publication.get("publication_id") or "").strip()
                if not publication_id:
                    continue
                position += 1
                status, error = "pending", ""
                platform = video_id = canonical_url = ""
                try:
                    _, _, resolved = self._capture()._resolve(relation_id, publication_id)
                    platform = str(resolved.get("platform") or "")
                    video_id = str(resolved.get("video_id") or "")
                    canonical_url = str(resolved.get("canonical_url") or "")
                except PublicationCaptureError as exc:
                    status, error = "skipped", exc.code
                duplicate_of = None
                identity = (platform.casefold(), video_id)
                if status == "pending" and identity in seen_videos:
                    status, error, duplicate_of = "skipped", "DUPLICATE_VIDEO_IN_BATCH", seen_videos[identity]
                item_id = f"batch_item_{uuid4().hex}"
                if status == "pending":
                    seen_videos[identity] = item_id
                items.append({
                    "item_id": item_id, "batch_run_id": batch_id, "publication_id": publication_id,
                    "campaign_creator_id": relation_id, "position": position, "platform": platform,
                    "video_id": video_id, "canonical_url": canonical_url, "status": status,
                    "safe_error_code": error, "duplicate_of_item_id": duplicate_of,
                    "created_at": _stamp(now), "updated_at": _stamp(now),
                })
        if not items:
            raise PublicationCaptureError("BATCH_NO_PUBLICATIONS", "当前 Campaign 没有可检查的 Publication。")
        manifest = [{key: item.get(key) for key in (
            "publication_id", "campaign_creator_id", "platform", "video_id", "canonical_url", "status"
        )} for item in items]
        self._batches().create({
            "batch_run_id": batch_id, "campaign_id": normalized, "status": "pending_claim",
            "claim_token_hash": _digest(claim_token),
            "manifest_hash": _digest(json.dumps(manifest, sort_keys=True, separators=(",", ":"))),
            "created_at": _stamp(now), "updated_at": _stamp(now), "safe_error_code": "",
        }, items)
        return {**self.status(batch_id), "claim_token": claim_token}

    def _verify_executor(self, batch_id: object, token: object, origin: object) -> dict[str, object]:
        run = self._batches().get_secret(str(batch_id or "").strip())
        supplied = str(token or "")
        normalized_origin = str(origin or "").strip().lower()
        if not run or not supplied or not normalized_origin.startswith("chrome-extension://"):
            raise PublicationCaptureError("BATCH_EXECUTOR_UNAUTHORIZED", "批量采集执行器未授权。", status=403)
        if not hmac.compare_digest(str(run.get("executor_token_hash") or ""), _digest(supplied)):
            raise PublicationCaptureError("BATCH_EXECUTOR_UNAUTHORIZED", "批量采集执行器未授权。", status=403)
        if not hmac.compare_digest(str(run.get("executor_origin_hash") or ""), _digest(normalized_origin)):
            raise PublicationCaptureError("BATCH_EXECUTOR_ORIGIN_MISMATCH", "批量采集执行器身份不匹配。", status=403)
        if self._now() >= _parse(run.get("executor_expires_at")):
            self._batches().set_status(str(run["batch_run_id"]), "interrupted", _stamp(self._now()))
            raise PublicationCaptureError("BATCH_EXECUTOR_EXPIRED", "批量采集授权已过期，请在 KOLConnect 中继续任务。", status=403)
        return run

    def claim(self, batch_id: object, claim_token: object, origin: object) -> dict[str, object]:
        normalized_id = str(batch_id or "").strip()
        run = self._batches().get_secret(normalized_id)
        token = str(claim_token or "")
        normalized_origin = str(origin or "").strip().lower()
        if not run or not token or not normalized_origin.startswith("chrome-extension://"):
            raise PublicationCaptureError("BATCH_CLAIM_INVALID", "批量采集领取凭据无效。", status=403)
        if run.get("status") != "pending_claim" or self._now() >= _parse(run.get("updated_at")) + timedelta(seconds=CLAIM_TTL_SECONDS):
            if run.get("status") == "pending_claim":
                self._batches().set_status(
                    normalized_id, "interrupted", _stamp(self._now()), safe_error_code="BATCH_CLAIM_EXPIRED",
                )
            raise PublicationCaptureError("BATCH_CLAIM_EXPIRED", "批量采集领取链接已失效，请返回 KOLConnect 继续任务。", status=403)
        if not hmac.compare_digest(str(run.get("claim_token_hash") or ""), _digest(token)):
            raise PublicationCaptureError("BATCH_CLAIM_INVALID", "批量采集领取凭据无效。", status=403)
        executor_token = secrets.token_urlsafe(32)
        now = self._now()
        try:
            self._batches().bind_executor(
                normalized_id, claim_consumed_at=_stamp(now), origin_hash=_digest(normalized_origin),
                token_hash=_digest(executor_token), expires_at=_stamp(now + timedelta(seconds=BATCH_TTL_SECONDS)),
                updated_at=_stamp(now),
            )
        except ValueError as exc:
            raise PublicationCaptureError(
                "BATCH_CLAIM_ALREADY_USED", "批量采集领取凭据已使用或已失效。", status=409
            ) from exc
        return {"batch": self.status(normalized_id), "executor_token": executor_token}

    def next_item(self, batch_id: object, executor_token: object, origin: object) -> dict[str, object]:
        run = self._verify_executor(batch_id, executor_token, origin)
        if run.get("status") != "running":
            return {"state": str(run.get("status") or "interrupted"), "item": None}
        item = self._batches().next_pending(str(run["batch_run_id"]))
        if item is None:
            self._batches().finish_if_exhausted(str(run["batch_run_id"]), _stamp(self._now()))
            current = self.status(str(run["batch_run_id"]))
            return {"state": str(current["batch"].get("status") or "completed"), "item": None}
        request = self._capture().create_request(item["campaign_creator_id"], item["publication_id"])
        now = self._now()
        leased = self._batches().lease_item(
            str(item["item_id"]), request_id=str(request["request_id"]), opened_at=_stamp(now),
            lease_expires_at=_stamp(now + timedelta(seconds=ITEM_LEASE_SECONDS)), updated_at=_stamp(now),
        )
        return {"state": "opening", "item": {**leased, "capture_code": request["capture_code"]}}

    def complete_from_attempt(self, attempt: dict[str, object]) -> None:
        request_id = str(attempt.get("request_id") or "")
        item = self._batches().item_for_request(request_id)
        if not item:
            return
        run = self._batches().get_secret(str(item["batch_run_id"]))
        if not run or run.get("status") == "cancelled":
            raise PublicationCaptureError("BATCH_CANCELLED", "批量采集任务已取消。", status=409)
        status = str(attempt.get("capture_status") or "failed")
        self._batches().complete_item(
            request_id, status=status if status in FINAL_ITEM_STATUSES else "failed",
            safe_error_code=str(attempt.get("safe_error_code") or ""), completed_at=_stamp(self._now()),
        )

    def authorize_submission(self, request_id: object) -> None:
        item = self._batches().item_for_request(str(request_id or ""))
        if not item:
            return
        run = self._batches().get_secret(str(item["batch_run_id"]))
        if not run or run.get("status") != "running" or item.get("status") not in {"opening", "collecting"}:
            raise PublicationCaptureError("BATCH_NOT_RUNNING", "批量采集任务当前未运行。", status=409)

    def executor_state(
        self, batch_id: object, executor_token: object, origin: object, request_id: object,
    ) -> dict[str, object]:
        run = self._verify_executor(batch_id, executor_token, origin)
        item = self._batches().item_for_request(str(request_id or ""))
        can_continue = bool(
            item and str(item.get("batch_run_id")) == str(run.get("batch_run_id"))
            and run.get("status") == "running" and item.get("status") in {"opening", "collecting"}
        )
        return {"state": str(run.get("status") or "interrupted"), "continue_current": can_continue}

    def submit_result(self, payload: dict[str, object]) -> dict[str, object]:
        # Serialize cancellation with authorization and both durable result writes.
        with shared_storage_lock():
            item = self._batches().item_for_request(str(payload.get("request_id") or ""))
            if item and item.get("status") in {"success", "partial", "insufficient", "failed"}:
                return self._capture().submit_result(payload)
            self.authorize_submission(payload.get("request_id"))
            result = self._capture().submit_result(payload)
            self.complete_from_attempt(result.get("attempt") or {})
            return result

    def pause(self, batch_id: object) -> dict[str, object]:
        run = self._batches().get_secret(str(batch_id or ""))
        if not run or run.get("status") not in {"pending_claim", "running"}:
            raise PublicationCaptureError("BATCH_NOT_PAUSABLE", "当前批量任务不能暂停。", status=409)
        self._batches().set_status(str(run["batch_run_id"]), "paused", _stamp(self._now()))
        return self.status(str(run["batch_run_id"]))

    def cancel(self, batch_id: object) -> dict[str, object]:
        run = self._batches().get_secret(str(batch_id or ""))
        if not run or run.get("status") in {"completed", "cancelled"}:
            raise PublicationCaptureError("BATCH_NOT_CANCELLABLE", "当前批量任务不能取消。", status=409)
        self._batches().set_status(str(run["batch_run_id"]), "cancelled", _stamp(self._now()))
        return self.status(str(run["batch_run_id"]))

    def interrupt(self, batch_id: object, safe_error_code: str) -> dict[str, object]:
        normalized = str(batch_id or "")
        run = self._batches().get_secret(normalized)
        if run and run.get("status") not in {"completed", "cancelled"}:
            self._batches().set_status(
                normalized, "interrupted", _stamp(self._now()), safe_error_code=safe_error_code,
            )
        return self.status(normalized)

    def resume(self, batch_id: object) -> dict[str, object]:
        normalized = str(batch_id or "")
        run = self._batches().get_secret(normalized)
        if not run or run.get("status") not in {"paused", "interrupted"}:
            raise PublicationCaptureError("BATCH_NOT_RESUMABLE", "当前批量任务不能继续。", status=409)
        token = secrets.token_urlsafe(32)
        self._batches().rotate_claim(normalized, _digest(token), _stamp(self._now()))
        return {**self.status(normalized), "claim_token": token}

    def retry(self, batch_id: object, item_id: object) -> dict[str, object]:
        try:
            self._batches().retry_item(str(batch_id or ""), str(item_id or ""), _stamp(self._now()))
        except ValueError as exc:
            raise PublicationCaptureError("BATCH_ITEM_NOT_RETRYABLE", "该视频当前不能重试。", status=409) from exc
        return self.status(str(batch_id or ""))

    def status(self, batch_id: object) -> dict[str, object]:
        normalized = str(batch_id or "").strip()
        secret = self._batches().get_secret(normalized)
        if secret and secret.get("status") == "pending_claim" and self._now() >= _parse(secret.get("updated_at")) + timedelta(seconds=CLAIM_TTL_SECONDS):
            self._batches().set_status(
                normalized, "interrupted", _stamp(self._now()), safe_error_code="BATCH_CLAIM_EXPIRED",
            )
        self._batches().interrupt_stale(normalized, _stamp(self._now()))
        run = self._batches().get(normalized)
        if not run:
            raise PublicationCaptureError("BATCH_NOT_FOUND", "批量采集任务不存在。", status=404)
        items = self._batches().items(normalized)
        counts: dict[str, int] = {}
        for item in items:
            key = str(item.get("status") or "")
            counts[key] = counts.get(key, 0) + 1
        sanitized = [{key: item.get(key) for key in (
            "item_id", "publication_id", "campaign_creator_id", "position", "platform", "video_id",
            "canonical_url", "status", "safe_error_code", "attempt_count", "opened_at", "completed_at"
        )} for item in items]
        return {"batch": run, "items": sanitized, "counts": counts, "total": len(items)}

    def active_for_campaign(self, campaign_id: object) -> dict[str, object] | None:
        run = self._batches().active_for_campaign(str(campaign_id or "").strip())
        return self.status(str(run["batch_run_id"])) if run else None
