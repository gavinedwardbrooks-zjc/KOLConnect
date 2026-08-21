from __future__ import annotations

"""Task workflow facade over narrow task and creator ports."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from ports.creator_port import (
    CreatorImportResult,
    CreatorImportSummary,
    CreatorPort,
    ExternalAgencyContactCommand,
    FourTableSyncCommand,
    FourTableSyncResult,
    ManualTaskPreparationCommand,
    ManualTaskProtectionCommand,
    ImportTaskResultsCommand,
    PreparedFourTableSync,
    TaskResultImportCommand,
    TaskResultUpdateCommand,
)
from ports.task_port import (
    EmailRecheckTaskCommand,
    EmailRecheckTaskItem,
    ManualTaskCreateCommand,
    ManualTaskInitializationCommand,
    RetryFailedResultsCommand,
    ScrapeTaskCreateCommand,
    TaskLinksUpdateCommand,
    TaskPort,
    TaskResultImportLinkage,
    TaskSyncStatusUpdate,
    TaskFinalizationDocuments,
    TaskRuntimeSnapshot,
    TaskRuntimeDocuments,
    TaskSummaryDocuments,
    RuntimeProgressUpdate,
)
from repositories.task_repository import TaskCsvDocument, TaskRepository
from services.task_result_mapper import (
    map_task_rows_for_creator_library,
    task_data_source,
)


TaskPortProvider = Callable[[], TaskPort]
CreatorPortProvider = Callable[[], CreatorPort]
TaskRepositoryProvider = Callable[[], TaskRepository]
ImportErrorLogger = Callable[[str, Exception], None]
ContactErrorLogger = Callable[[str, Exception], None]
FinalizationErrorLogger = Callable[[str, Exception], None]
SyncErrorLogger = Callable[[str, Exception], None]


@dataclass(frozen=True)
class TaskLifecyclePlan:
    runtime_action: str = ""
    profile: str = ""
    response: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BackgroundFinalizationResult:
    status: str
    sync_status: str
    last_error: str = ""
    import_result: dict[str, object] = field(default_factory=dict)


class TaskReviewError(ValueError):
    """Stable API-safe failure for a result-review transition."""

    def __init__(
        self, code: str, *, status: int = 400, details: dict[str, object] | None = None
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.details = dict(details or {})

    def to_response(self) -> dict[str, object]:
        return {"ok": False, "error": self.code, **self.details}


class TaskService:
    """Resolve operation-scoped dependencies for Task domain workflows."""

    def __init__(
        self,
        get_task_port: TaskPortProvider,
        get_creator_port: CreatorPortProvider,
        get_task_repository: TaskRepositoryProvider,
        import_error_logger: ImportErrorLogger | None = None,
        contact_error_logger: ContactErrorLogger | None = None,
        finalization_error_logger: FinalizationErrorLogger | None = None,
        sync_error_logger: SyncErrorLogger | None = None,
    ) -> None:
        self._get_task_port = get_task_port
        self._get_creator_port = get_creator_port
        self._get_task_repository = get_task_repository
        self._import_error_logger = import_error_logger or (lambda _task_id, _exc: None)
        self._contact_error_logger = contact_error_logger or (
            lambda _record_id, _exc: None
        )
        self._finalization_error_logger = finalization_error_logger or (
            lambda _task_id, _exc: None
        )
        self._sync_error_logger = sync_error_logger or (lambda _task_id, _exc: None)

    def get_tasks(self) -> dict[str, object]:
        return self._get_task_port().get_tasks().to_response()

    def get_task_details(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().get_task_details(task_id).to_response()

    def get_task_metadata(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().get_task(task_id).to_response()

    # These lifecycle operations are intentionally named transitions, rather than
    # exposing the legacy task-manager's generic metadata/file primitives.
    def get_runtime_task_snapshot(self, task_id: str) -> TaskRuntimeSnapshot:
        return self._get_task_port().get_runtime_task_snapshot(task_id)

    def get_runtime_documents(self, task_id: str) -> TaskRuntimeDocuments:
        return self._get_task_port().get_runtime_documents(task_id)

    def get_task_summary_documents(self, task_id: str) -> TaskSummaryDocuments:
        return self._get_task_port().get_task_summary_documents(task_id)

    def list_recovery_candidates(self) -> tuple[TaskRuntimeSnapshot, ...]:
        return self._get_task_port().list_recovery_candidates()

    def recover_stopping_task(self, task_id: str, *, finished_at: str) -> dict[str, object]:
        return self._get_task_port().recover_stopping_task(task_id, finished_at=finished_at).to_response()

    def mark_task_interrupted(self, task_id: str, *, interrupted_at: str, reason: str) -> dict[str, object]:
        return self._get_task_port().mark_task_interrupted(task_id, interrupted_at=interrupted_at, reason=reason).to_response()

    def start_runtime_task(self, task_id: str, **kwargs: object) -> dict[str, object]:
        return self._get_task_port().start_runtime_task(task_id, **kwargs).to_response()  # type: ignore[arg-type]

    def mark_runtime_worker_running(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().mark_runtime_worker_running(task_id).to_response()

    def persist_runtime_progress(self, task_id: str, update: RuntimeProgressUpdate) -> dict[str, object]:
        return self._get_task_port().persist_runtime_progress(task_id, update).to_response()

    def mark_runtime_paused(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().mark_runtime_paused(task_id).to_response()

    def mark_runtime_resumed(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().mark_runtime_resumed(task_id).to_response()

    def request_runtime_stop(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().request_runtime_stop(task_id).to_response()

    def mark_runtime_finalizing(self, task_id: str, *, metadata_changes: dict[str, object]) -> dict[str, object]:
        return self._get_task_port().mark_runtime_finalizing(task_id, metadata_changes=metadata_changes).to_response()

    def complete_runtime_task(self, task_id: str, *, finished_at: str, metadata_changes: dict[str, object]) -> dict[str, object]:
        return self._get_task_port().complete_runtime_task(task_id, finished_at=finished_at, metadata_changes=metadata_changes).to_response()

    def fail_runtime_task(self, task_id: str, *, finished_at: str, error: str, metadata_changes: dict[str, object]) -> dict[str, object]:
        return self._get_task_port().fail_runtime_task(task_id, finished_at=finished_at, error=error, metadata_changes=metadata_changes).to_response()

    def get_task_finalization_documents(self, task_id: str) -> TaskFinalizationDocuments:
        return self._get_task_port().get_task_documents(task_id)

    def finalize_task_documents(self, task_id: str, documents: TaskFinalizationDocuments) -> dict[str, object]:
        return self._get_task_port().finalize_task_documents(task_id, documents).to_response()

    def get_task_results(self, task_id: str) -> dict[str, object]:
        return self._get_task_port().get_task_results(task_id).to_response()

    def get_task_creator_analysis(self, task_id: str) -> dict[str, object]:
        task = self._get_task_port().get_task(task_id)
        if not task.creator_analysis_id:
            return {"available": False}
        analysis = self._get_creator_port().get_creator_analysis(
            task.creator_analysis_id
        )
        return {
            "available": True,
            "analysis": dict(analysis.analysis),
            "recovered_from_backup": False,
        }

    def get_scrape_status(self) -> dict[str, object]:
        return self._get_task_port().get_scrape_status().to_response()

    def create_manual_task(
        self, payload: dict[str, object], *, defer_library_import: bool = True
    ) -> dict[str, object]:
        creator_port = self._get_creator_port()
        prepared = creator_port.prepare_manual_task(
            ManualTaskPreparationCommand(payload=payload)
        )
        platform_summary = {
            "TikTok": int(prepared.platform == "TikTok"),
            "Instagram": int(prepared.platform == "Instagram"),
            "YouTube": int(prepared.platform == "YouTube"),
        }
        task_port = self._get_task_port()
        created = task_port.create_manual_task(
            ManualTaskCreateCommand(
                normalized_url=prepared.profile_url,
                task_name=prepared.task_name,
                platform=prepared.platform,
                platform_summary=platform_summary,
                defer_library_import=defer_library_import,
            )
        )
        local_source_contact_id = ""
        if prepared.source_contact_record_id:
            try:
                contact = creator_port.upsert_external_agency_contact(
                    ExternalAgencyContactCommand(
                        external_record_id=prepared.source_contact_record_id,
                        name=prepared.source_contact_name,
                        whatsapp=prepared.source_contact_whatsapp,
                    )
                )
                local_source_contact_id = contact.contact_id
            except (OSError, RuntimeError, ValueError) as exc:
                self._contact_error_logger(prepared.source_contact_record_id, exc)
        initialized = task_port.initialize_manual_task(
            created.task.task_id,
            ManualTaskInitializationCommand(
                creator_name=prepared.creator_name,
                platform=prepared.platform,
                profile_url=prepared.profile_url,
                follower_count=prepared.follower_count,
                email=prepared.email,
                whatsapp=prepared.whatsapp,
                note=prepared.note,
                source_contact_record_id=prepared.source_contact_record_id,
                source_contact_name=prepared.source_contact_name,
                local_source_contact_id=local_source_contact_id,
            ),
        )
        if prepared.protected_values:
            creator_port.commit_manual_task_protection(
                ManualTaskProtectionCommand(
                    task_id=created.task.task_id,
                    account_uid=initialized.account_uid,
                    values=prepared.protected_values,
                    updated_at=initialized.modified_at,
                )
            )
        return {
            "task": initialized.task.to_response(),
            "account_uid": initialized.account_uid,
            "creator_library_import": None,
        }

    def create_scrape_task(
        self,
        *,
        normalized_links: list[str],
        invalid_links: list[str],
        input_count: int,
        name: object,
        target_platform: object,
        platforms: list[str],
        platform_summary: dict[str, int],
        filtered_links: list[dict[str, object]],
    ) -> dict[str, object]:
        created = self._get_task_port().create_scrape_task(
            ScrapeTaskCreateCommand(
                normalized_links=tuple(normalized_links),
                invalid_links=tuple(invalid_links),
                input_count=input_count,
                name=str(name or ""),
                target_platform=str(target_platform or "全部"),
                platforms=tuple(platforms),
                platform_summary=dict(platform_summary),
                filtered_links=tuple(dict(item) for item in filtered_links),
            )
        )
        return created.task.to_response()

    def open_task_results(self, task_id: str) -> None:
        self._get_task_port().open_task_results(task_id)

    def create_email_recheck_task(self) -> dict[str, object]:
        scan = self._get_creator_port().get_email_recheck_candidates()
        if not scan.candidates:
            return {
                "task": None,
                "scanned_accounts": scan.scanned_accounts,
                "created_count": 0,
                "skipped_count": len(scan.skipped),
                "skipped": list(scan.skipped),
                "duplicate_uids": list(scan.duplicate_uids),
            }

        platform_counts = {"TikTok": 0, "Instagram": 0, "YouTube": 0}
        items: list[EmailRecheckTaskItem] = []
        for candidate in scan.candidates:
            platform_counts[candidate.platform] += 1
            items.append(
                EmailRecheckTaskItem(
                    account_uid=candidate.account_uid,
                    platform=candidate.platform,
                    profile_url=candidate.profile_url,
                    username=candidate.username,
                )
            )
        created = self._get_task_port().create_email_recheck_task(
            EmailRecheckTaskCommand(
                items=tuple(items),
                name=f"缺失邮箱补全-{datetime.now().strftime('%Y%m%d')}",
                platform_summary=platform_counts,
                skipped_count=len(scan.skipped),
            )
        )
        return {
            "task": created.task.to_response(),
            "scanned_accounts": scan.scanned_accounts,
            "created_count": len(items),
            "skipped_count": len(scan.skipped),
            "skipped": list(scan.skipped),
            "duplicate_uids": list(scan.duplicate_uids),
        }

    def delete_task(self, task_id: str) -> dict[str, object]:
        if self._task_is_running(task_id):
            raise RuntimeError("任务正在运行，不能删除。")
        self._get_task_port().delete_task(task_id)
        return {"task_id": task_id, "deleted": True}

    def rename_task(self, task_id: str, name: object) -> dict[str, object]:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("任务名称不能为空。")
        if len(normalized_name) > 100:
            raise ValueError("任务名称不能超过100个字符。")
        return self._get_task_port().rename_task(
            task_id, normalized_name
        ).to_response()

    def update_task_links(
        self,
        task_id: str,
        action: object,
        index: object = None,
        url: object = None,
    ) -> dict[str, object]:
        if self._task_is_running(task_id):
            raise RuntimeError("任务正在运行，不能修改链接。")
        command = TaskLinksUpdateCommand(
            action=str(action or "").strip(),
            index=index,
            url=str(url or "").strip(),
        )
        return self._get_task_port().update_task_links(
            task_id, command
        ).to_response()

    def retry_failed_results(
        self, task_id: str, account_uids: list[object] | None = None
    ) -> dict[str, object]:
        requested = tuple(
            str(value or "").strip()
            for value in (account_uids or [])
            if str(value or "").strip()
        )
        command = RetryFailedResultsCommand(account_uids=requested)
        return self._get_task_port().retry_failed_results(
            task_id, command
        ).to_response()

    def resume_task(
        self,
        task_id: str,
        *,
        runtime_running: bool,
        runtime_task_id: str,
    ) -> TaskLifecyclePlan:
        task = self._get_task_port().resume_task(task_id)
        if runtime_running:
            if runtime_task_id != task_id:
                raise RuntimeError("已有任务正在运行。")
            return TaskLifecyclePlan(runtime_action="resume")
        if task.status not in {
            "paused",
            "interrupted",
            "stopped",
            "created",
            "failed",
        }:
            raise RuntimeError("当前任务不需要恢复。")
        return TaskLifecyclePlan(profile=task.profile)

    def stop_task(
        self, task_id: str, *, runtime_active: bool
    ) -> TaskLifecyclePlan:
        task = self._get_task_port().get_task(task_id)
        if task.status == "finalizing":
            raise RuntimeError("任务已经完成抓取，正在处理中。")
        if runtime_active:
            return TaskLifecyclePlan(runtime_action="stop")
        if task.status not in {"paused", "interrupted", "running", "stopping"}:
            raise RuntimeError("当前任务无需停止。")
        self._get_task_port().stop_task(task_id)
        return TaskLifecyclePlan(
            response={"task_id": task_id, "status": "stopped"}
        )

    def update_task_results(
        self, task_id: str, account_uid: object, fields: object
    ) -> dict[str, object]:
        status = self._get_task_port().get_scrape_status().to_response()
        if bool(status.get("running")) and status.get("task_id") == task_id:
            raise RuntimeError("任务正在运行，暂不能审核结果。")
        normalized_uid = str(account_uid or "").strip()
        if not normalized_uid:
            raise ValueError("缺少账号唯一ID。")

        repository = self._get_task_repository()
        creator_port = self._get_creator_port()
        now = self._utc_now()
        with repository.operation_lock():
            task = repository.get_task(task_id)
            results = repository.read_results_document(task_id)
            progress = repository.read_progress_document(task_id)
            prepared = creator_port.prepare_task_result_update(
                TaskResultUpdateCommand(
                    task_id=task_id,
                    account_uid=normalized_uid,
                    fields=fields if isinstance(fields, dict) else {},
                    task_type=str(task.get("task_type") or "scrape"),
                    updated_at=now,
                    result_fieldnames=results.fieldnames,
                    result_rows=results.rows,
                    progress_fieldnames=progress.fieldnames,
                    progress_rows=progress.rows,
                )
            )
            modifications = repository.read_modifications(task_id)
            modifications.append(
                {
                    "account_uid": normalized_uid,
                    "modified_fields": dict(prepared.modified_fields),
                    "status": "pending_sync",
                    "time": now,
                }
            )
            task = repository.write_review_update(
                task_id,
                results=TaskCsvDocument(
                    prepared.result_fieldnames, prepared.result_rows
                ),
                progress=TaskCsvDocument(
                    prepared.progress_fieldnames, prepared.progress_rows
                ),
                modifications=modifications,
                metadata_changes={
                    "modified_count": len(modifications),
                    "last_modified_time": now,
                },
            )

        creator_port.commit_task_result_protection(task_id, prepared)
        library_import = None
        if str(task.get("status") or "") in {"completed", "manual_created"}:
            try:
                import_result = creator_port.import_task_results(
                    TaskResultImportCommand(
                        task_id=task_id,
                        task=task,
                        rows=prepared.result_rows,
                        allowed_statuses=("completed", "manual_created"),
                    )
                )
                if not isinstance(import_result, CreatorImportResult):
                    raise RuntimeError("Creator 导入结果无效。")
                if import_result.imported_at:
                    self._get_task_port().attach_task_result_import(
                        task_id,
                        TaskResultImportLinkage(
                            imported_at=import_result.imported_at,
                            creator_ids=import_result.creator_ids,
                            account_ids=import_result.account_ids,
                            summary=dict(import_result.summary or {}),
                        ),
                    )
                library_import = dict(import_result.response)
            except (OSError, RuntimeError, ValueError) as exc:
                self._import_error_logger(task_id, exc)
                library_import = {"status": "failed", "error": str(exc)}

        return {
            "task_id": task_id,
            "account_uid": normalized_uid,
            "modified_fields": dict(prepared.modified_fields),
            "data_status": prepared.data_status,
            "modified_at": now,
            "creator_library_import": library_import,
        }

    def reject_task_result(
        self,
        task_id: str,
        account_uid: object,
        rejection_reason: object = None,
    ) -> dict[str, object]:
        """Persist a pending-to-rejected transition without changing task data."""
        normalized_uid = str(account_uid or "").strip()
        if not normalized_uid:
            raise TaskReviewError("REVIEW_ACCOUNT_UID_REQUIRED")

        repository = self._get_task_repository()
        normalized_reason = str(rejection_reason or "").strip()
        with repository.operation_lock():
            try:
                repository.get_task(task_id)
            except ValueError as exc:
                raise TaskReviewError("TASK_NOT_FOUND", status=404) from exc

            results = self._get_task_port().get_task_results(task_id).to_response()
            record = next(
                (
                    item
                    for item in results.get("records", [])
                    if str(item.get("account_uid") or "") == normalized_uid
                ),
                None,
            )
            if record is None:
                raise TaskReviewError("REVIEW_RESULT_NOT_FOUND", status=404)
            if not bool(record.get("review_eligible")):
                raise TaskReviewError("REVIEW_RESULT_NOT_ELIGIBLE", status=409)
            if record.get("review_state") == "approved":
                raise TaskReviewError("REVIEW_TRANSITION_CONFLICT", status=409)

            review_state = repository.read_review_state(task_id)
            rows = dict(review_state["rows"])
            existing = rows.get(normalized_uid)
            existing = dict(existing) if isinstance(existing, dict) else {}
            if record.get("review_state") == "rejected":
                if not normalized_reason:
                    return self._review_response(task_id, normalized_uid)
                reviewed_at = str(existing.get("reviewed_at") or record.get("reviewed_at") or "")
            else:
                reviewed_at = self._utc_now()

            rows[normalized_uid] = {
                "review_state": "rejected",
                "reviewed_at": reviewed_at,
                "rejection_reason": normalized_reason or str(
                    existing.get("rejection_reason") or ""
                ),
            }
            try:
                repository.write_task_documents(
                    task_id,
                    results=repository.read_results_document(task_id),
                    progress=repository.read_progress_document(task_id),
                    modifications=repository.read_modifications(task_id),
                    metadata_changes={},
                    review_state={"version": review_state["version"], "rows": rows},
                )
            except (OSError, RuntimeError) as exc:
                raise TaskReviewError("REVIEW_PERSISTENCE_FAILED", status=500) from exc

        return self._review_response(task_id, normalized_uid)

    def approve_task_result(self, task_id: str, account_uid: object) -> dict[str, object]:
        """Approve one eligible result and complete existing Creator import work."""
        normalized_uid, repository, _record = self._review_target(task_id, account_uid)
        with repository.operation_lock():
            _current_uid, _current_repository, record = self._review_target(
                task_id, normalized_uid
            )
            if record.get("review_state") == "rejected":
                raise TaskReviewError("REVIEW_TRANSITION_CONFLICT", status=409)
            if record.get("review_state") != "approved":
                self._persist_review_state(
                    repository,
                    task_id,
                    normalized_uid,
                    "approved",
                    reviewed_at=self._utc_now(),
                )
        return self._complete_review_creator_mutation(task_id, normalized_uid)

    def edit_approve_task_result(
        self, task_id: str, account_uid: object, fields: object
    ) -> dict[str, object]:
        """Atomically persist supported edits and approval before Creator mutation."""
        if not isinstance(fields, dict) or not fields:
            raise TaskReviewError("REVIEW_FIELDS_REQUIRED")
        normalized_uid, repository, _record = self._review_target(task_id, account_uid)
        creator_port = self._get_creator_port()
        with repository.operation_lock():
            _current_uid, _current_repository, record = self._review_target(
                task_id, normalized_uid
            )
            task = repository.get_task(task_id)
            if record.get("review_state") == "rejected":
                raise TaskReviewError("REVIEW_TRANSITION_CONFLICT", status=409)
            if record.get("review_state") == "approved":
                raise TaskReviewError("REVIEW_TRANSITION_CONFLICT", status=409)
            now = str(record.get("reviewed_at") or self._utc_now())
            results = repository.read_results_document(task_id)
            progress = repository.read_progress_document(task_id)
            try:
                prepared = creator_port.prepare_task_result_update(
                    TaskResultUpdateCommand(
                        task_id=task_id,
                        account_uid=normalized_uid,
                        fields=fields,
                        task_type=str(task.get("task_type") or "scrape"),
                        updated_at=now,
                        result_fieldnames=results.fieldnames,
                        result_rows=results.rows,
                        progress_fieldnames=progress.fieldnames,
                        progress_rows=progress.rows,
                    )
                )
            except ValueError as exc:
                raise TaskReviewError("REVIEW_FIELDS_INVALID") from exc
            modifications = repository.read_modifications(task_id)
            modifications.append(
                {
                    "account_uid": normalized_uid,
                    "modified_fields": dict(prepared.modified_fields),
                    "status": "pending_sync",
                    "time": now,
                }
            )
            review_state = repository.read_review_state(task_id)
            rows = dict(review_state["rows"])
            rows[normalized_uid] = {
                "review_state": "approved",
                "reviewed_at": now,
                "rejection_reason": "",
            }
            try:
                repository.write_task_documents(
                    task_id,
                    results=TaskCsvDocument(prepared.result_fieldnames, prepared.result_rows),
                    progress=TaskCsvDocument(prepared.progress_fieldnames, prepared.progress_rows),
                    modifications=modifications,
                    metadata_changes={
                        "modified_count": len(modifications),
                        "last_modified_time": now,
                    },
                    review_state={"version": review_state["version"], "rows": rows},
                )
            except (OSError, RuntimeError) as exc:
                raise TaskReviewError("REVIEW_PERSISTENCE_FAILED", status=500) from exc

        try:
            creator_port.commit_task_result_protection(task_id, prepared)
        except (OSError, RuntimeError, ValueError) as exc:
            raise self._review_partial_failure(task_id, normalized_uid, exc) from exc
        return self._complete_review_creator_mutation(task_id, normalized_uid)

    def _review_target(
        self, task_id: str, account_uid: object
    ) -> tuple[str, TaskRepository, dict[str, object]]:
        normalized_uid = str(account_uid or "").strip()
        if not normalized_uid:
            raise TaskReviewError("REVIEW_ACCOUNT_UID_REQUIRED")
        repository = self._get_task_repository()
        try:
            repository.get_task(task_id)
        except ValueError as exc:
            raise TaskReviewError("TASK_NOT_FOUND", status=404) from exc
        results = self._get_task_port().get_task_results(task_id).to_response()
        record = next(
            (
                item
                for item in results.get("records", [])
                if str(item.get("account_uid") or "") == normalized_uid
            ),
            None,
        )
        if record is None:
            raise TaskReviewError("REVIEW_RESULT_NOT_FOUND", status=404)
        if not bool(record.get("review_eligible")):
            raise TaskReviewError("REVIEW_RESULT_NOT_ELIGIBLE", status=409)
        return normalized_uid, repository, dict(record)

    def _persist_review_state(
        self,
        repository: TaskRepository,
        task_id: str,
        account_uid: str,
        state: str,
        *,
        reviewed_at: str,
    ) -> None:
        review_state = repository.read_review_state(task_id)
        rows = dict(review_state["rows"])
        rows[account_uid] = {
            "review_state": state,
            "reviewed_at": reviewed_at,
            "rejection_reason": "",
        }
        try:
            repository.write_task_documents(
                task_id,
                results=repository.read_results_document(task_id),
                progress=repository.read_progress_document(task_id),
                modifications=repository.read_modifications(task_id),
                metadata_changes={},
                review_state={"version": review_state["version"], "rows": rows},
            )
        except (OSError, RuntimeError) as exc:
            raise TaskReviewError("REVIEW_PERSISTENCE_FAILED", status=500) from exc

    def _complete_review_creator_mutation(
        self, task_id: str, account_uid: str
    ) -> dict[str, object]:
        repository = self._get_task_repository()
        task = repository.get_task(task_id)
        library_import = None
        if str(task.get("status") or "") in {"completed", "manual_created"}:
            if str(task.get("creator_library_imported_at") or ""):
                return {
                    **self._review_response(task_id, account_uid),
                    "creator_library_import": {"status": "already_imported"},
                }
            try:
                import_result = self._get_creator_port().import_task_results(
                    TaskResultImportCommand(
                        task_id=task_id,
                        task=task,
                        rows=repository.read_results_document(task_id).rows,
                        allowed_statuses=("completed", "manual_created"),
                    )
                )
                if not isinstance(import_result, CreatorImportResult):
                    raise RuntimeError("Creator 导入结果无效。")
                if import_result.imported_at:
                    self._get_task_port().attach_task_result_import(
                        task_id,
                        TaskResultImportLinkage(
                            imported_at=import_result.imported_at,
                            creator_ids=import_result.creator_ids,
                            account_ids=import_result.account_ids,
                            summary=dict(import_result.summary or {}),
                        ),
                    )
                library_import = dict(import_result.response)
            except (OSError, RuntimeError, ValueError) as exc:
                raise self._review_partial_failure(task_id, account_uid, exc) from exc
        return {**self._review_response(task_id, account_uid), "creator_library_import": library_import}

    def _review_partial_failure(
        self, task_id: str, account_uid: str, exc: Exception
    ) -> TaskReviewError:
        return TaskReviewError(
            "REVIEW_CREATOR_MUTATION_FAILED",
            status=502,
            details={"review": self._review_response(task_id, account_uid)},
        )

    def _review_response(self, task_id: str, account_uid: str) -> dict[str, object]:
        results = self._get_task_port().get_task_results(task_id).to_response()
        record = next(
            (
                item
                for item in results.get("records", [])
                if str(item.get("account_uid") or "") == account_uid
            ),
            None,
        )
        if record is None:
            raise TaskReviewError("REVIEW_RESULT_NOT_FOUND", status=404)
        return {
            "account_uid": account_uid,
            "review_state": record["review_state"],
            "reviewed_at": record["reviewed_at"],
            "rejection_reason": record["rejection_reason"],
            "review_total": results["review_total"],
            "reviewed_count": results["reviewed_count"],
            "pending_count": results["pending_count"],
        }

    def sync_four_tables(self, task_id: str) -> dict[str, object]:
        repository = self._get_task_repository()
        task = repository.get_task(task_id)
        task_status = str(task.get("status") or "").strip()
        if task_status == "running":
            raise RuntimeError("任务抓取中，请稍候")
        if task_status == "finalizing":
            raise RuntimeError("任务入库收尾中，请稍候")
        rows = repository.read_results_document(task_id).rows
        creator_port = self._get_creator_port()
        prepared = creator_port.prepare_four_table_sync(
            FourTableSyncCommand(task_id=task_id, task=task, rows=rows)
        )
        empty_summary = {
            "created_creators": 0,
            "created_accounts": 0,
            "updated_accounts": 0,
            "updated_creators": 0,
            "skipped": 0,
            "errors": 0,
        }
        synced_at = self._utc_now()
        if not prepared.results and not prepared.validation_errors:
            sync_summary = {
                **empty_summary,
                "success_records": prepared.success_records,
                "partial_records": prepared.partial_records,
                "skipped_abnormal": prepared.skipped_abnormal,
                "skipped_invalid": 0,
            }
            return self._persist_sync_result(
                task_id,
                prepared,
                status="success",
                synced_at=synced_at,
                summary=sync_summary,
                errors=(),
                sync_log=None,
            )
        if prepared.validation_errors and not prepared.results:
            return self._persist_sync_result(
                task_id,
                prepared,
                status="failed",
                synced_at=synced_at,
                summary=empty_summary,
                errors=prepared.validation_errors,
                sync_log=None,
            )

        sync_log: tuple[dict[str, object], ...] = ()
        try:
            result = creator_port.execute_four_table_sync(prepared)
            if not isinstance(result, FourTableSyncResult):
                raise RuntimeError("Creator 四表同步结果无效。")
            sync_errors = result.errors
            sync_summary = {
                "created_creators": result.created_creators,
                "created_accounts": result.created_accounts,
                "updated_accounts": result.updated_accounts,
                "updated_creators": result.updated_creators,
                "skipped": result.skipped,
                "errors": len(sync_errors),
                "success_records": prepared.success_records,
                "partial_records": prepared.partial_records,
                "skipped_abnormal": prepared.skipped_abnormal,
                "skipped_invalid": len(prepared.validation_errors),
            }
            sync_status = "success" if not sync_errors else "failed"
            sync_log = tuple(dict(item) for item in result.sync_logs)
        except Exception as exc:
            self._sync_error_logger(task_id, exc)
            sync_errors = (str(exc),)
            sync_summary = {
                **empty_summary,
                "errors": 1,
                "success_records": prepared.success_records,
                "partial_records": prepared.partial_records,
                "skipped_abnormal": prepared.skipped_abnormal,
                "skipped_invalid": len(prepared.validation_errors),
            }
            sync_status = "failed"
        return self._persist_sync_result(
            task_id,
            prepared,
            status=sync_status,
            synced_at=synced_at,
            summary=sync_summary,
            errors=sync_errors,
            sync_log=sync_log,
        )

    def _persist_sync_result(
        self,
        task_id: str,
        prepared: PreparedFourTableSync,
        *,
        status: str,
        synced_at: str,
        summary: dict[str, object],
        errors: tuple[str, ...],
        sync_log: tuple[dict[str, object], ...] | None,
    ) -> dict[str, object]:
        self._get_task_port().update_sync_status(
            task_id,
            TaskSyncStatusUpdate(
                status=status,
                synced_at=synced_at,
                data_source=prepared.data_source if sync_log is not None else "",
                summary=summary,
                errors=errors,
                warnings=prepared.warnings,
                skipped=prepared.skipped,
                sync_log=sync_log,
            ),
        )
        return {
            "task_id": task_id,
            "record_count": prepared.record_count,
            "sync_status": status,
            "sync_summary": summary,
            "sync_errors": list(errors),
            "sync_warnings": list(prepared.warnings),
            "sync_skipped": list(prepared.skipped),
        }

    def import_task_results_to_creator_library(
        self,
        task_id: str,
        *,
        allowed_task_statuses: set[str] | None = None,
    ) -> dict[str, object]:
        repository = self._get_task_repository()
        task = repository.get_task(task_id)
        if not bool(task.get("creator_library_import_eligible")):
            return {
                "status": "skipped",
                "reason": "historical_task_requires_manual_import",
            }
        if (
            str(task.get("task_type") or "scrape") == "email_recheck"
            and not str(task.get("email_recheck_source") or "").strip()
        ):
            return {"status": "skipped", "reason": "email_recheck_task"}
        allowed_statuses = allowed_task_statuses or {"completed"}
        if str(task.get("status") or "") not in allowed_statuses:
            return {"status": "skipped", "reason": "task_not_completed"}
        if not repository.results_exist(task_id):
            return {"status": "skipped", "reason": "results_missing"}
        rows = repository.read_results_document(task_id).rows
        items = map_task_rows_for_creator_library(task, rows)
        summary = self._get_creator_port().import_task_results(
            ImportTaskResultsCommand(
                task_id=task_id,
                items=items,
                source=task_data_source(task),
                imported_at=str(
                    task.get("finished_at")
                    or task.get("created_at")
                    or self._utc_now()
                ),
            )
        )
        if not isinstance(summary, CreatorImportSummary):
            raise RuntimeError("Creator 导入结果无效。")
        imported_at = self._utc_now()
        public_summary = {
            "input_records": summary.input_records,
            "created_creators": summary.created_creators,
            "created_accounts": summary.created_accounts,
            "updated_accounts": summary.updated_accounts,
            "duplicate_records": summary.duplicate_records,
            "skipped_failed": summary.skipped_failed,
            "skipped_invalid": summary.skipped_invalid,
        }
        self._get_task_port().attach_task_result_import(
            task_id,
            TaskResultImportLinkage(
                imported_at=imported_at,
                creator_ids=summary.creator_ids,
                account_ids=summary.account_ids,
                summary=public_summary,
            ),
        )
        return {
            "status": "success",
            **public_summary,
            "creator_ids": list(summary.creator_ids),
            "account_ids": list(summary.account_ids),
        }

    def finalize_background_task(
        self, task_id: str
    ) -> BackgroundFinalizationResult:
        repository = self._get_task_repository()
        task = repository.get_task(task_id)
        if str(task.get("status") or "") == "completed":
            return BackgroundFinalizationResult(
                status="completed",
                sync_status=str(task.get("sync_status") or "not_requested"),
            )
        try:
            import_result = self.import_task_results_to_creator_library(
                task_id, allowed_task_statuses={"finalizing"}
            )
        except Exception as exc:
            self._finalization_error_logger(task_id, exc)
            last_error = f"Creator Library 入库失败：{exc}"
            repository.update_task(
                task_id,
                creator_library_import_error=str(exc),
                status="failed",
                finished_at=self._utc_now(),
                last_error=last_error,
                sync_status="not_started",
            )
            return BackgroundFinalizationResult(
                status="failed",
                sync_status="not_started",
                last_error=last_error,
            )
        repository.update_task(
            task_id,
            status="completed",
            finished_at=self._utc_now(),
            last_error="",
            sync_status="not_requested",
        )
        return BackgroundFinalizationResult(
            status="completed",
            sync_status="not_requested",
            import_result=import_result,
        )

    def _task_is_running(self, task_id: str) -> bool:
        status = self._get_task_port().get_scrape_status().to_response()
        return bool(status.get("running")) and status.get("task_id") == task_id

    @staticmethod
    def _utc_now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
