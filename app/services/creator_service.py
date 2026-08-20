from __future__ import annotations

"""Creator workflows over request-aware repository and port providers."""

import re
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

import creator_data_compat as scraper_module
from creator_batch_import import (
    CreatorBatchImportError,
    build_creator_import_template,
    parse_creator_import_workbook,
)
from creator_library_export import build_creator_export_workbook
from ports.agency_port import AgencyPort
from ports.creator_port import (
    CreatorImportItem,
    CreatorImportResult,
    CreatorImportSummary,
    EmailRecheckCandidate,
    EmailRecheckCandidateScan,
    ExternalAgencyContact,
    ExternalAgencyContactCommand,
    FourTableSyncCommand,
    FourTableSyncResult,
    ImportTaskResultsCommand,
    ManualTaskPreparationCommand,
    ManualTaskProtectionCommand,
    PreparedFourTableSync,
    PreparedTaskResultUpdate,
    PreparedManualTask,
    TaskResultImportCommand,
    TaskResultUpdateCommand,
)
from ports.task_port import TaskPort
from local_storage_lock import shared_storage_lock


REVIEW_FIELD_WHATSAPP = "WhatsApp"
REVIEW_FIELD_NOTE = "备注"
REVIEW_FIELD_DATA_STATUS = "数据状态"
REVIEW_FIELD_MODIFIED_AT = "最后修改时间"
REVIEW_CSV_FIELDS = (
    REVIEW_FIELD_WHATSAPP,
    REVIEW_FIELD_NOTE,
    REVIEW_FIELD_DATA_STATUS,
    REVIEW_FIELD_MODIFIED_AT,
)
REVIEW_EDITABLE_FIELDS = {
    scraper_module.FIELD_NAME,
    scraper_module.FIELD_EMAIL,
    scraper_module.FIELD_FOLLOWER_COUNT,
    REVIEW_FIELD_WHATSAPP,
    REVIEW_FIELD_NOTE,
}
REVIEW_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
REVIEW_WHATSAPP_PATTERN = re.compile(r"^[0-9+()\- ]+$")
PROTECTED_DATA_FIELDS = REVIEW_EDITABLE_FIELDS
DATA_PROTECTION_PRIORITY = {
    "人工维护": 50,
    "人工录入": 40,
    "审核修改": 30,
    "系统补全": 20,
    "邮箱补全": 20,
    "人工+系统补充": 20,
    "人工补充": 20,
    "系统抓取": 10,
}
BLOCKING_SCRAPE_STATUSES = {
    "missing_data",
    "failed",
    "login_required",
    "platform_error",
}


class CreatorRepositoryReader(Protocol):
    def saveCreator(self, analysis: dict[str, Any]) -> dict[str, Any]: ...

    def getCreatorsPage(self, **kwargs: Any) -> dict[str, Any]: ...

    def getCreatorLibrarySnapshot(self) -> dict[str, Any]: ...

    def getCreatorsPageFromSnapshot(
        self, snapshot: dict[str, Any], **kwargs: Any
    ) -> dict[str, Any]: ...

    def getCreatorDetail(self, creator_id: str) -> dict[str, Any]: ...

    def getCreatorTrend(self, creator_id: str) -> dict[str, Any]: ...

    def getCreatorSnapshots(self, creator_id: str) -> list[dict[str, Any]]: ...

    def getCreatorAccounts(self, creator_id: str = "") -> list[dict[str, Any]]: ...

    def getExistingCreatorAccountUids(self, account_uids: set[str]) -> set[str]: ...

    def createCreatorsBatch(self, records: list[dict[str, Any]]) -> dict[str, int]: ...

    def updateCreator(
        self,
        creator_id: str,
        payload: dict[str, Any],
        *,
        agency_port: AgencyPort | None = None,
    ) -> dict[str, Any]: ...

    def updateCreatorStatus(self, creator_id: str, status: object) -> dict[str, Any]: ...

    def updateCreatorRelations(
        self,
        creator_id: str,
        payload: dict[str, Any],
        *,
        agency_port: AgencyPort | None = None,
    ) -> dict[str, Any]: ...

    def importTaskResults(
        self,
        task_id: str,
        records: list[dict[str, Any]],
        *,
        source: str,
        imported_at: str,
    ) -> dict[str, Any]: ...

    def upsertExternalAgencyContact(
        self,
        external_record_id: str,
        *,
        name: str,
        whatsapp: str = "",
        source: str = "feishu_compat",
    ) -> dict[str, Any]: ...


RepositoryProvider = Callable[[], CreatorRepositoryReader]
TaskPortProvider = Callable[[], TaskPort]
AgencyPortProvider = Callable[[], AgencyPort]
DataProtectionLoader = Callable[[], dict]
DataProtectionSaver = Callable[[dict], None]
SourceContactResolver = Callable[[object], dict | None]
FourTableConfigProvider = Callable[[], dict]
CreatorLibraryCacheProvider = Callable[[], Any]


class CreatorService:
    """Resolve a repository per operation instead of retaining scoped state."""

    def __init__(
        self,
        repository_provider: RepositoryProvider,
        task_port_provider: TaskPortProvider,
        data_protection_loader: DataProtectionLoader | None = None,
        data_protection_saver: DataProtectionSaver | None = None,
        source_contact_resolver: SourceContactResolver | None = None,
        four_table_config_provider: FourTableConfigProvider | None = None,
        agency_port_provider: AgencyPortProvider | None = None,
        creator_library_cache_provider: CreatorLibraryCacheProvider | None = None,
    ) -> None:
        self._repository_provider = repository_provider
        self._task_port_provider = task_port_provider
        self._data_protection_loader = data_protection_loader or (lambda: {})
        self._data_protection_saver = data_protection_saver or (lambda _data: None)
        self._source_contact_resolver = source_contact_resolver or (lambda _value: None)
        self._four_table_config_provider = four_table_config_provider or (lambda: {})
        self._agency_port_provider = agency_port_provider
        self._creator_library_cache_provider = creator_library_cache_provider

    def _invalidate_creator_library_cache(self) -> None:
        if self._creator_library_cache_provider is not None:
            self._creator_library_cache_provider().invalidate()

    def prepare_four_table_sync(
        self, command: FourTableSyncCommand
    ) -> PreparedFourTableSync:
        task = dict(command.task)
        rows = [dict(row) for row in command.rows]
        email_recheck_only = task.get("task_type") == "email_recheck"
        results: list[dict[str, Any]] = []
        validation_errors: list[str] = []
        skipped_records: list[str] = []
        success_records = 0
        partial_records = 0
        skipped_abnormal = 0
        for index, row in enumerate(rows, start=1):
            result = scraper_module.row_to_result(row)
            account_uid = scraper_module.build_creator_uid(result) or f"第 {index} 条"
            scrape_status = str(result.get("scrape_status") or "success").strip()
            if scrape_status not in {"success", "partial_success"}:
                skipped_abnormal += 1
                skipped_records.append(
                    f"{account_uid}：抓取状态为 {scrape_status}，已跳过。"
                )
                continue
            row_results, row_errors = self._validate_four_table_sync_rows([row])
            if email_recheck_only:
                row_errors = [
                    error for error in row_errors if "抓取状态为" in error
                ]
            if row_errors:
                validation_errors.extend(row_errors)
                skipped_records.extend(row_errors)
                continue
            results.extend(row_results)
            if scrape_status == "partial_success":
                partial_records += 1
            else:
                success_records += 1
        warnings = self._partial_scrape_warnings(rows)
        if not rows:
            validation_errors.append("当前任务没有可同步的抓取结果。")
        return PreparedFourTableSync(
            task_id=command.task_id,
            record_count=len(rows),
            results=tuple(results),
            validation_errors=tuple(validation_errors),
            warnings=tuple(warnings),
            skipped=tuple(skipped_records),
            success_records=success_records,
            partial_records=partial_records,
            skipped_abnormal=skipped_abnormal,
            email_recheck_only=email_recheck_only,
            data_source=self._task_data_source(task),
            email_source=self._task_email_source(task),
            source_contact_record_id=(
                str(task.get("source_contact_record_id") or "").strip()
                if task.get("task_type") == "manual"
                else ""
            ),
        )

    def execute_four_table_sync(
        self, prepared: PreparedFourTableSync
    ) -> FourTableSyncResult:
        data_protection = self._data_protection_loader()
        results = [dict(result) for result in prepared.results]
        summary = scraper_module.push_to_feishu_four_tables(
            results,
            self._four_table_config_provider(),
            email_recheck_only=prepared.email_recheck_only,
            data_source=prepared.data_source,
            email_source=prepared.email_source,
            data_protection=data_protection,
            source_contact_record_id=prepared.source_contact_record_id,
        )
        sync_logs = tuple(
            dict(item)
            for item in summary.get("sync_logs", [])
            if isinstance(item, dict)
        )
        result_by_uid = {
            scraper_module.build_creator_uid(result): result
            for result in results
            if scraper_module.build_creator_uid(result)
        }
        with shared_storage_lock():
            current_protection = self._data_protection_loader()
            protection_changed = False
            now = self._utc_now()
            for entry in sync_logs:
                if (
                    scraper_module.FOUR_TABLE_ACCOUNT_FIELD_EMAIL
                    not in entry.get("updated_fields", [])
                ):
                    continue
                account_uid = str(entry.get("account_uid") or "")
                result = result_by_uid.get(account_uid) or {}
                email = str(result.get("email_display") or "")
                if email and email != scraper_module.NO_EMAIL:
                    protection_changed = self.merge_data_protection(
                        current_protection,
                        account_uid,
                        {scraper_module.FIELD_EMAIL: email},
                        prepared.data_source,
                        prepared.task_id,
                        str(entry.get("updated_at") or now),
                    ) or protection_changed
            if protection_changed:
                self._data_protection_saver(current_protection)
        return FourTableSyncResult(
            created_creators=int(summary.get("created_creators") or 0),
            created_accounts=int(summary.get("created_accounts") or 0),
            updated_accounts=int(summary.get("updated_accounts") or 0),
            updated_creators=int(summary.get("updated_creators") or 0),
            skipped=int(summary.get("skipped") or 0),
            errors=tuple(str(item) for item in summary.get("errors", [])),
            sync_logs=sync_logs,
        )

    def prepare_manual_task(
        self, command: ManualTaskPreparationCommand
    ) -> PreparedManualTask:
        payload = dict(command.payload)
        profile_url = str(payload.get("profile_url") or "").strip()
        if not profile_url:
            raise ValueError("主页链接不能为空。")

        normalized = scraper_module.normalize_link_record(profile_url)
        if not normalized.get("valid"):
            raise ValueError(str(normalized.get("reason") or "主页链接无效。"))
        platform_by_key = {
            "tiktok": "TikTok",
            "instagram": "Instagram",
            "youtube": "YouTube",
        }
        normalized_platform = platform_by_key.get(
            str(normalized.get("platform") or "").lower(), ""
        )
        selected_platform = str(payload.get("platform") or "").strip()
        if selected_platform not in {"TikTok", "Instagram", "YouTube"}:
            raise ValueError("请选择平台。")
        if selected_platform != normalized_platform:
            raise ValueError(f"主页链接属于 {normalized_platform}，请确认所选平台。")

        name = str(payload.get("name") or "").strip()
        email = str(payload.get("email") or "").strip()
        whatsapp = str(payload.get("whatsapp") or "").strip()
        note = str(payload.get("note") or "")
        source_contact = self._source_contact_resolver(
            payload.get("source_contact_record_id")
        )
        raw_followers = str(payload.get("follower_count") or "").strip()
        follower_count = scraper_module.normalize_follower_count(raw_followers)
        if raw_followers and not follower_count:
            raise ValueError("粉丝数格式错误，请填写如 10K、1.2M 或 100000。")
        if email:
            self.validate_task_result_updates(
                {scraper_module.FIELD_NAME: name or "未命名"},
                {scraper_module.FIELD_EMAIL: email},
            )
        if whatsapp:
            self.validate_task_result_updates(
                {scraper_module.FIELD_NAME: name or "未命名"},
                {REVIEW_FIELD_WHATSAPP: whatsapp},
            )
        if follower_count:
            self.validate_task_result_updates(
                {scraper_module.FIELD_NAME: name or "未命名"},
                {scraper_module.FIELD_FOLLOWER_COUNT: follower_count},
            )
        protected_values = {
            field: value
            for field, value in {
                scraper_module.FIELD_NAME: name,
                scraper_module.FIELD_EMAIL: email,
                scraper_module.FIELD_FOLLOWER_COUNT: follower_count,
                REVIEW_FIELD_WHATSAPP: whatsapp,
                REVIEW_FIELD_NOTE: note,
            }.items()
            if value
        }
        return PreparedManualTask(
            task_name=str(payload.get("task_name") or ""),
            creator_name=name,
            platform=selected_platform,
            profile_url=str(normalized.get("normalized_url") or "").strip(),
            follower_count=follower_count,
            email=email,
            whatsapp=whatsapp,
            note=note,
            source_contact_record_id=str(
                (source_contact or {}).get("record_id") or ""
            ),
            source_contact_name=str((source_contact or {}).get("name") or ""),
            source_contact_whatsapp=str(
                (source_contact or {}).get("whatsapp") or ""
            ),
            protected_values=protected_values,
        )

    def commit_manual_task_protection(
        self, command: ManualTaskProtectionCommand
    ) -> None:
        with shared_storage_lock():
            protection = self._data_protection_loader()
            if self.merge_data_protection(
                protection,
                command.account_uid,
                dict(command.values),
                "人工录入",
                command.task_id,
                command.updated_at,
            ):
                self._data_protection_saver(protection)

    def upsert_external_agency_contact(
        self, contact: ExternalAgencyContactCommand
    ) -> ExternalAgencyContact:
        if self._agency_port_provider is None:
            # Compatibility for existing injected CreatorRepository test doubles.
            saved = self._repository_provider().upsertExternalAgencyContact(
                contact.external_record_id,
                name=contact.name,
                whatsapp=contact.whatsapp,
                source=contact.source,
            )
        else:
            saved = self._agency_port_provider().upsert_external_contact(
                contact.external_record_id,
                name=contact.name,
                whatsapp=contact.whatsapp,
                source=contact.source,
            )
        self._invalidate_creator_library_cache()
        return ExternalAgencyContact(
            contact_id=str(saved.get("contact_id") or ""),
            external_record_id=str(saved.get("external_record_id") or ""),
            name=str(saved.get("name") or ""),
            agency_id=str(saved.get("agency_id") or ""),
            whatsapp=str(saved.get("whatsapp") or ""),
            source=str(saved.get("source") or ""),
            created_at=str(saved.get("created_at") or ""),
            updated_at=str(saved.get("updated_at") or ""),
        )

    def get_creator_library(
        self,
        *,
        include_archived: bool = False,
        page: int = 1,
        page_size: int = 24,
        sort: str = "created_at",
        order: str = "desc",
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        repository = self._repository_provider()
        query = {
            "include_archived": include_archived,
            "page": page,
            "page_size": page_size,
            "sort": sort,
            "order": order,
            "filters": filters,
        }
        if self._creator_library_cache_provider is None:
            result = repository.getCreatorsPage(**query)
        else:
            result = repository.getCreatorsPageFromSnapshot(
                self._get_creator_library_snapshot(repository), **query
            )
        # Preserve the legacy records alias while clients migrate to creators.
        return {**result, "records": result["creators"]}

    def import_creator_batch(self, payload: bytes) -> dict[str, int]:
        parsed_rows = parse_creator_import_workbook(payload)
        repository = self._repository_provider()
        prepared: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for parsed in parsed_rows:
            values = parsed.values
            platform_value = str(values.get("platform") or "").strip()
            profile_url = str(values.get("profile_url") or "").strip()
            if not platform_value:
                errors.append(self._batch_row_error(parsed.excel_row, "MISSING_REQUIRED_FIELD", "platform"))
            if not profile_url:
                errors.append(self._batch_row_error(parsed.excel_row, "MISSING_REQUIRED_FIELD", "profile_url"))
            if not platform_value or not profile_url:
                continue

            platform = self._canonical_platform(platform_value)
            if not platform:
                errors.append(self._batch_row_error(parsed.excel_row, "INVALID_PLATFORM", "platform"))
                continue
            normalized = scraper_module.normalize_link_record(profile_url)
            normalized_url = str(normalized.get("normalized_url") or "").strip()
            normalized_platform = self._canonical_platform(normalized.get("platform"))
            if not normalized.get("valid") or not normalized_url or normalized_platform != platform:
                errors.append(self._batch_row_error(parsed.excel_row, "INVALID_PROFILE_URL", "profile_url"))
                continue
            account_uid = scraper_module.build_creator_uid(
                {"platform": platform, "url": normalized_url}
            )
            if not account_uid:
                errors.append(self._batch_row_error(parsed.excel_row, "INVALID_PROFILE_URL", "profile_url"))
                continue
            prepared.append(
                {
                    **{header: str(values.get(header) or "").strip() for header in values},
                    "excel_row": parsed.excel_row,
                    "platform": platform,
                    "profile_url": normalized_url,
                    "account_uid": account_uid,
                }
            )

        rows_by_uid: dict[str, list[dict[str, Any]]] = {}
        for row in prepared:
            rows_by_uid.setdefault(row["account_uid"], []).append(row)
        duplicate_rows = {
            row["excel_row"]
            for rows in rows_by_uid.values()
            if len(rows) > 1
            for row in rows
        }
        errors.extend(
            self._batch_row_error(row_number, "DUPLICATE_IN_FILE")
            for row_number in sorted(duplicate_rows)
        )

        agency_cache: dict[str, bool] = {}
        for row in prepared:
            agency_id = str(row.get("agency_id") or "")
            if not agency_id or row["excel_row"] in duplicate_rows:
                continue
            if agency_id not in agency_cache:
                try:
                    if self._agency_port_provider is None:
                        raise ValueError("Agency boundary unavailable")
                    self._agency_port_provider().get_agency(agency_id)
                    agency_cache[agency_id] = True
                except ValueError:
                    agency_cache[agency_id] = False
            if not agency_cache[agency_id]:
                errors.append(
                    self._batch_row_error(row["excel_row"], "UNKNOWN_AGENCY", "agency_id")
                )

        existing_uids = repository.getExistingCreatorAccountUids(
            {row["account_uid"] for row in prepared}
        )
        invalid_row_numbers = {int(error["row"]) for error in errors}
        skipped_existing = sum(
            1
            for row in prepared
            if row["excel_row"] not in invalid_row_numbers
            and row["account_uid"] in existing_uids
        )
        valid_new = [
            row
            for row in prepared
            if row["excel_row"] not in invalid_row_numbers
            and row["account_uid"] not in existing_uids
        ]
        summary = {
            "total_rows": len(parsed_rows),
            "valid_new_rows": len(valid_new),
            "skipped_existing": skipped_existing,
            "invalid_rows": len(invalid_row_numbers),
        }
        if errors:
            errors.sort(key=lambda item: (int(item["row"]), str(item["code"])))
            raise CreatorBatchImportError(
                "BATCH_IMPORT_VALIDATION_FAILED", summary=summary, rows=errors
            )

        try:
            result = repository.createCreatorsBatch(valid_new)
        except Exception as exc:
            raise CreatorBatchImportError("BATCH_IMPORT_WRITE_FAILED") from exc
        self._invalidate_creator_library_cache()
        return {
            "total_rows": len(parsed_rows),
            "created": int(result.get("created") or 0),
            "skipped_existing": skipped_existing + int(result.get("skipped_existing") or 0),
        }

    def export_creators(self, creator_ids: object) -> bytes:
        """Export a complete, all-or-nothing selection from the Creator Library."""
        if not isinstance(creator_ids, list) or not creator_ids:
            raise ValueError("CREATOR_IDS_REQUIRED")
        normalized_ids = [str(creator_id or "").strip() for creator_id in creator_ids]
        if not all(normalized_ids):
            raise ValueError("CREATOR_IDS_REQUIRED")

        repository = self._repository_provider()
        snapshot = self._get_creator_library_snapshot(repository)
        index = snapshot.get("creator_id_index") if isinstance(snapshot, dict) else None
        if not isinstance(index, dict):
            raise RuntimeError("CREATOR_EXPORT_FAILED")
        missing = [creator_id for creator_id in normalized_ids if creator_id not in index]
        if missing:
            raise LookupError("CREATOR_NOT_FOUND")
        return build_creator_export_workbook([dict(index[creator_id]) for creator_id in normalized_ids])

    def _get_creator_library_snapshot(self, repository: CreatorRepositoryReader) -> dict[str, Any]:
        if self._creator_library_cache_provider is None:
            return repository.getCreatorLibrarySnapshot()
        return self._creator_library_cache_provider().get_snapshot(
            repository.workbook_path,
            repository.getCreatorLibrarySnapshot,
        )

    @staticmethod
    def get_creator_import_template() -> bytes:
        return build_creator_import_template()

    @staticmethod
    def _canonical_platform(value: object) -> str:
        return {
            "tiktok": "TikTok",
            "instagram": "Instagram",
            "youtube": "YouTube",
        }.get(str(value or "").strip().casefold(), "")

    @staticmethod
    def _batch_row_error(row: int, code: str, field: str = "") -> dict[str, Any]:
        error: dict[str, Any] = {"row": row, "status": "INVALID", "code": code}
        if field:
            error["field"] = field
        return error

    def get_creator_detail(self, creator_id: str) -> dict[str, Any]:
        return self._repository_provider().getCreatorDetail(creator_id)

    def get_creator_trend(self, creator_id: str) -> dict[str, Any]:
        return self._repository_provider().getCreatorTrend(creator_id)

    def get_creator_snapshots(self, creator_id: str) -> dict[str, Any]:
        return {
            "creator_id": creator_id,
            "snapshots": self._repository_provider().getCreatorSnapshots(creator_id),
        }

    def update_creator_profile(
        self, creator_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        agency_port = (
            self._agency_port_provider()
            if self._agency_port_provider is not None and "agency_id" in payload
            else None
        )
        repository = self._repository_provider()
        result = {
            "creator": (
                repository.updateCreator(creator_id, payload)
                if agency_port is None
                else repository.updateCreator(
                    creator_id, payload, agency_port=agency_port
                )
            )
        }
        self._invalidate_creator_library_cache()
        return result

    def update_creator_status(self, creator_id: str, status: object) -> dict[str, Any]:
        result = self._repository_provider().updateCreatorStatus(creator_id, status)
        self._invalidate_creator_library_cache()
        return result

    def update_creator_relations(
        self, creator_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        agency_port = (
            self._agency_port_provider()
            if self._agency_port_provider is not None
            else None
        )
        repository = self._repository_provider()
        result = (
            repository.updateCreatorRelations(creator_id, payload)
            if agency_port is None
            else repository.updateCreatorRelations(
                creator_id, payload, agency_port=agency_port
            )
        )
        self._invalidate_creator_library_cache()
        return result

    def import_creator_from_extension(
        self,
        analysis: dict[str, Any],
        *,
        compensation_task_id: str,
    ) -> dict[str, Any]:
        """Persist one prepared Extension analysis through the Creator boundary."""
        try:
            creator = (
                analysis.get("creator")
                if isinstance(analysis.get("creator"), dict)
                else {}
            )
            agency_id = str(creator.get("agency_id") or "").strip()
            if agency_id:
                if self._agency_port_provider is None:
                    raise ValueError("Agency boundary unavailable.")
                self._agency_port_provider().get_agency(agency_id)
            result = self._repository_provider().saveCreator(analysis)
            self._invalidate_creator_library_cache()
            return result
        except Exception:
            # Preserve the original import failure even when task cleanup also fails.
            try:
                self._task_port_provider().delete_task(compensation_task_id)
            except Exception:
                pass
            raise

    def get_creator_task(self, creator_id: str) -> dict[str, Any]:
        """Return the existing review task linked to one Creator."""
        detail = self._repository_provider().getCreatorDetail(creator_id)
        task_id = str(detail["record"].get("task_id") or "")
        task = self._task_port_provider().get_task(task_id)
        return {
            "task": task.to_response(),
            "created": False,
            "message": "已打开关联的审核任务。",
        }

    def get_email_recheck_candidates(self) -> EmailRecheckCandidateScan:
        accounts = self._repository_provider().getCreatorAccounts("")
        duplicate_uids: set[str] = set()
        seen_uids: set[str] = set()
        candidates: list[EmailRecheckCandidate] = []
        skipped: list[str] = []
        supported_platforms = {"TikTok", "Instagram", "YouTube"}
        for account in accounts:
            account_uid = str(account.get("account_uid") or "").strip()
            if not account_uid:
                skipped.append("missing_uid: 账号唯一ID为空")
                continue
            if account_uid in seen_uids:
                duplicate_uids.add(account_uid)
                skipped.append(f"duplicate_uid: {account_uid}")
                continue
            seen_uids.add(account_uid)
            account_email = str(account.get("account_email") or "").strip()
            if account_email and account_email != scraper_module.NO_EMAIL:
                continue
            platform = str(account.get("platform") or "").strip()
            profile_url = str(account.get("profile_url") or "").strip()
            if platform not in supported_platforms or not profile_url:
                skipped.append(f"{account_uid}: 平台或主页链接不完整")
                continue
            normalized = scraper_module.normalize_link_record(profile_url)
            normalized_url = str(normalized.get("normalized_url") or "")
            identity_result = scraper_module.build_result(
                url=normalized_url,
                platform=platform,
                name=str(account.get("username") or "").strip(),
            )
            if (
                not normalized.get("valid")
                or scraper_module.build_creator_uid(identity_result) != account_uid
            ):
                skipped.append(
                    f"{account_uid}: 账号唯一ID、平台或主页链接不完整/不一致"
                )
                continue
            candidates.append(
                EmailRecheckCandidate(
                    creator_id=str(account.get("creator_id") or ""),
                    account_id=str(account.get("account_id") or ""),
                    account_uid=account_uid,
                    platform=platform,
                    profile_url=normalized_url,
                    username=str(account.get("username") or "").strip(),
                    account_email=account_email,
                )
            )
        return EmailRecheckCandidateScan(
            scanned_accounts=len(accounts),
            candidates=tuple(candidates),
            skipped=tuple(skipped),
            duplicate_uids=tuple(sorted(duplicate_uids)),
        )

    def prepare_task_result_update(
        self, command: TaskResultUpdateCommand
    ) -> PreparedTaskResultUpdate:
        result_rows = [dict(row) for row in command.result_rows]
        progress_rows = [dict(row) for row in command.progress_rows]
        result_matches = [
            row for row in result_rows if self._account_uid_for_row(row) == command.account_uid
        ]
        if len(result_matches) != 1:
            raise ValueError("未找到唯一的任务结果记录。")
        if not any(
            self._account_uid_for_row(row) == command.account_uid
            for row in progress_rows
        ):
            raise ValueError("未找到对应的任务进度记录。")

        target_row = result_matches[0]
        updates = self.validate_task_result_updates(target_row, command.fields)
        modified_fields = {
            field: {"old": str(target_row.get(field) or ""), "new": value}
            for field, value in updates.items()
            if str(target_row.get(field) or "") != value
        }
        if not modified_fields:
            raise ValueError("没有检测到需要保存的修改。")

        task_result_fields = (scraper_module.FIELD_FOLLOWER_COUNT, *REVIEW_CSV_FIELDS)
        for rows in (result_rows, progress_rows):
            for row in rows:
                for field in task_result_fields:
                    row.setdefault(
                        field, "待检查" if field == REVIEW_FIELD_DATA_STATUS else ""
                    )
                if self._account_uid_for_row(row) == command.account_uid:
                    row.update(updates)
                    row[REVIEW_FIELD_DATA_STATUS] = "待同步"
                    row[REVIEW_FIELD_MODIFIED_AT] = command.updated_at

        result_fieldnames = tuple(
            dict.fromkeys((*command.result_fieldnames, *task_result_fields))
        )
        progress_fieldnames = tuple(
            dict.fromkeys((*command.progress_fieldnames, *task_result_fields))
        )
        return PreparedTaskResultUpdate(
            account_uid=command.account_uid,
            modified_fields=modified_fields,
            updated_at=command.updated_at,
            data_status="待同步",
            result_fieldnames=result_fieldnames,
            result_rows=tuple(result_rows),
            progress_fieldnames=progress_fieldnames,
            progress_rows=tuple(progress_rows),
            protection_values=updates,
            protection_source=(
                "人工录入" if command.task_type == "manual" else "审核修改"
            ),
        )

    def commit_task_result_protection(
        self, task_id: str, update: PreparedTaskResultUpdate
    ) -> None:
        with shared_storage_lock():
            protection = self._data_protection_loader()
            if self.merge_data_protection(
                protection,
                update.account_uid,
                dict(update.protection_values),
                update.protection_source,
                task_id,
                update.updated_at,
            ):
                self._data_protection_saver(protection)

    def import_task_results(
        self, command: ImportTaskResultsCommand | TaskResultImportCommand
    ) -> CreatorImportSummary | CreatorImportResult:
        if isinstance(command, ImportTaskResultsCommand):
            summary = self._repository_provider().importTaskResults(
                command.task_id,
                [self._creator_import_item_record(item) for item in command.items],
                source=command.source,
                imported_at=command.imported_at,
            )
            self._invalidate_creator_library_cache()
            return CreatorImportSummary(
                input_records=int(summary.get("input_records") or 0),
                created_creators=int(summary.get("created_creators") or 0),
                created_accounts=int(summary.get("created_accounts") or 0),
                updated_accounts=int(summary.get("updated_accounts") or 0),
                duplicate_records=int(summary.get("duplicate_records") or 0),
                skipped_failed=int(summary.get("skipped_failed") or 0),
                skipped_invalid=int(summary.get("skipped_invalid") or 0),
                creator_ids=tuple(str(value) for value in summary.get("creator_ids", [])),
                account_ids=tuple(str(value) for value in summary.get("account_ids", [])),
            )
        task = dict(command.task)
        if not bool(task.get("creator_library_import_eligible")):
            return CreatorImportResult(
                {"status": "skipped", "reason": "historical_task_requires_manual_import"}
            )
        if (
            str(task.get("task_type") or "scrape") == "email_recheck"
            and not str(task.get("email_recheck_source") or "").strip()
        ):
            return CreatorImportResult(
                {"status": "skipped", "reason": "email_recheck_task"}
            )
        if str(task.get("status") or "") not in set(command.allowed_statuses):
            return CreatorImportResult(
                {"status": "skipped", "reason": "task_not_completed"}
            )

        summary = self._repository_provider().importTaskResults(
            command.task_id,
            self._task_rows_for_creator_library(task, command.rows),
            source=self._task_data_source(task),
            imported_at=str(
                task.get("finished_at") or task.get("created_at") or self._utc_now()
            ),
        )
        self._invalidate_creator_library_cache()
        imported_at = self._utc_now()
        public_summary = {
            key: value
            for key, value in summary.items()
            if key not in {"creator_ids", "account_ids"}
        }
        return CreatorImportResult(
            response={"status": "success", **summary},
            imported_at=imported_at,
            creator_ids=tuple(str(value) for value in summary["creator_ids"]),
            account_ids=tuple(str(value) for value in summary["account_ids"]),
            summary=public_summary,
        )

    @staticmethod
    def _creator_import_item_record(item: CreatorImportItem) -> dict[str, Any]:
        return {
            field: getattr(item, field)
            for field in CreatorImportItem.__dataclass_fields__
        }

    @staticmethod
    def validate_task_result_updates(
        row: dict, fields: Any
    ) -> dict[str, str]:
        if not isinstance(fields, dict) or not fields:
            raise ValueError("缺少可保存的审核字段。")
        unknown_fields = set(fields) - REVIEW_EDITABLE_FIELDS
        if unknown_fields:
            raise ValueError(f"不允许修改字段：{', '.join(sorted(unknown_fields))}")

        final_name = str(
            fields.get(scraper_module.FIELD_NAME, row.get(scraper_module.FIELD_NAME) or "")
        ).strip()
        if not final_name:
            raise ValueError("达人名称不能为空。")
        final_email = str(
            fields.get(scraper_module.FIELD_EMAIL, row.get(scraper_module.FIELD_EMAIL) or "")
        ).strip()
        email_for_validation = "" if final_email == scraper_module.NO_EMAIL else final_email
        if email_for_validation:
            if any(char.isspace() for char in email_for_validation):
                raise ValueError("邮箱格式错误：邮箱不能包含空格。")
            for email in email_for_validation.split(","):
                if not REVIEW_EMAIL_PATTERN.fullmatch(email):
                    raise ValueError("邮箱格式错误。")
        final_whatsapp = str(
            fields.get(REVIEW_FIELD_WHATSAPP, row.get(REVIEW_FIELD_WHATSAPP) or "")
        ).strip()
        if final_whatsapp:
            if not REVIEW_WHATSAPP_PATTERN.fullmatch(final_whatsapp):
                raise ValueError("WhatsApp号码格式异常。")
            digits = re.sub(r"\D", "", final_whatsapp)
            if not 7 <= len(digits) <= 20:
                raise ValueError("WhatsApp号码格式异常。")
        raw_followers = fields.get(
            scraper_module.FIELD_FOLLOWER_COUNT,
            row.get(scraper_module.FIELD_FOLLOWER_COUNT) or "",
        )
        final_followers = scraper_module.normalize_follower_count(str(raw_followers or "").strip())
        if str(raw_followers or "").strip() and not final_followers:
            raise ValueError("粉丝数格式错误，请填写如 10K、1.2M 或 100000。")

        normalized: dict[str, str] = {}
        for field, value in (
            (scraper_module.FIELD_NAME, final_name),
            (scraper_module.FIELD_EMAIL, final_email),
            (scraper_module.FIELD_FOLLOWER_COUNT, final_followers),
            (REVIEW_FIELD_WHATSAPP, final_whatsapp),
            (REVIEW_FIELD_NOTE, str(fields.get(REVIEW_FIELD_NOTE) or "")),
        ):
            if field in fields:
                normalized[field] = value
        return normalized

    @staticmethod
    def merge_data_protection(
        protection: dict,
        account_uid: str,
        values: dict[str, str],
        source: str,
        task_id: str,
        updated_at: str,
    ) -> bool:
        if not account_uid:
            return False
        changed = False
        account_fields = protection.setdefault(account_uid, {})
        incoming_priority = DATA_PROTECTION_PRIORITY.get(source, 0)
        for field, value in values.items():
            if field not in PROTECTED_DATA_FIELDS or not str(value or "").strip():
                continue
            current = account_fields.get(field)
            current_priority = DATA_PROTECTION_PRIORITY.get(
                str((current or {}).get("source") or ""), 0
            )
            if (
                isinstance(current, dict)
                and str(current.get("value") or "").strip()
                and current_priority > incoming_priority
            ):
                continue
            account_fields[field] = {
                "value": str(value),
                "source": source,
                "task_id": task_id,
                "updated_at": updated_at,
            }
            changed = True
        return changed

    @staticmethod
    def _account_uid_for_row(row: dict) -> str:
        return scraper_module.build_creator_uid(scraper_module.row_to_result(row))

    @classmethod
    def _task_rows_for_creator_library(
        cls, task: dict, rows: tuple[Any, ...]
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        source_contact_id = str(task.get("local_source_contact_id") or "").strip()
        extension_crm = (
            task.get("extension_crm")
            if isinstance(task.get("extension_crm"), dict)
            else {}
        )
        task_type = str(task.get("task_type") or "scrape").strip()
        for raw_row in rows:
            row = dict(raw_row)
            result = scraper_module.row_to_result(row)
            profile_url = str(result.get("url") or "").strip()
            normalized = scraper_module.normalize_link_record(profile_url)
            platform = str(
                result.get("platform") or normalized.get("platform") or ""
            ).strip()
            email = str(result.get("email_display") or "").strip()
            if email == scraper_module.NO_EMAIL:
                email = ""
            records.append(
                {
                    "account_uid": scraper_module.build_creator_uid(result),
                    "platform": platform,
                    "profile_url": str(normalized.get("normalized_url") or profile_url),
                    "creator_name": str(result.get("name") or "").strip(),
                    "followers": str(result.get("follower_count") or "").strip(),
                    "email": email,
                    "whatsapp": str(result.get("whatsapp") or "").strip(),
                    "country": str(
                        result.get("country") or extension_crm.get("country") or ""
                    ).strip(),
                    "language": str(
                        result.get("language") or extension_crm.get("language") or ""
                    ).strip(),
                    "content_category": str(
                        result.get("content_category")
                        or extension_crm.get("content_category")
                        or ""
                    ).strip(),
                    "note": str(result.get("note") or ""),
                    "latest_post_date": str(
                        result.get("latest_publish_date") or ""
                    ).strip(),
                    "last_scrape_time": str(result.get("last_scrape_time") or "").strip(),
                    "data_source": cls._task_data_source(task),
                    "scrape_status": str(result.get("scrape_status") or "").strip(),
                    "source_contact_id": source_contact_id,
                    "email_recheck": task_type == "email_recheck",
                }
            )
        return records

    @staticmethod
    def _task_data_source(task: dict) -> str:
        task_type = str(task.get("task_type") or "scrape")
        if task_type == "email_recheck":
            return "系统抓取"
        if task_type == "manual":
            return "人工+系统补充" if task.get("has_system_supplement") else "人工录入"
        return "系统抓取"

    @staticmethod
    def _task_email_source(task: dict) -> str:
        task_type = str(task.get("task_type") or "scrape")
        if task_type == "email_recheck":
            return "邮箱补全"
        if task_type == "manual":
            return "人工+系统补充" if task.get("has_system_supplement") else "人工录入"
        return "系统抓取"

    @staticmethod
    def _validate_four_table_sync_rows(
        rows: list[dict]
    ) -> tuple[list[dict], list[str]]:
        results: list[dict] = []
        errors: list[str] = []
        for index, row in enumerate(rows, start=1):
            result = scraper_module.row_to_result(row)
            account_uid = scraper_module.build_creator_uid(result)
            reference = account_uid or f"第 {index} 条"
            scrape_status = str(result.get("scrape_status") or "success").strip()
            if scrape_status in BLOCKING_SCRAPE_STATUSES:
                errors.append(
                    f"{reference}：抓取状态为 {scrape_status}，请重新抓取后再同步。"
                )
            name = str(result.get("name") or "").strip()
            if not name:
                errors.append(f"{reference}：达人名称不能为空。")
            email_display = str(row.get(scraper_module.FIELD_EMAIL) or "").strip()
            if email_display and email_display != scraper_module.NO_EMAIL:
                if any(char.isspace() for char in email_display):
                    errors.append(f"{reference}：邮箱格式错误，邮箱不能包含空格。")
                else:
                    for email in email_display.split(","):
                        if not REVIEW_EMAIL_PATTERN.fullmatch(email.strip()):
                            errors.append(
                                f"{reference}：邮箱格式错误：{email.strip() or email_display}"
                            )
            whatsapp = str(row.get(REVIEW_FIELD_WHATSAPP) or "").strip()
            if whatsapp:
                digits = re.sub(r"\D", "", whatsapp)
                if (
                    not REVIEW_WHATSAPP_PATTERN.fullmatch(whatsapp)
                    or not 7 <= len(digits) <= 20
                ):
                    errors.append(f"{reference}：WhatsApp号码格式异常。")
            raw_followers = str(
                row.get(scraper_module.FIELD_FOLLOWER_COUNT) or ""
            ).strip()
            if raw_followers and not scraper_module.normalize_follower_count(
                raw_followers
            ):
                errors.append(
                    f"{reference}：粉丝数格式错误，请填写如 10K、1.2M 或 100000。"
                )
            results.append(result)
        return results, errors

    @staticmethod
    def _partial_scrape_warnings(rows: list[dict]) -> list[str]:
        warnings: list[str] = []
        for index, row in enumerate(rows, start=1):
            result = scraper_module.row_to_result(row)
            if str(result.get("scrape_status") or "success").strip() != "partial_success":
                continue
            account_uid = scraper_module.build_creator_uid(result)
            warnings.append(
                f"{account_uid or f'第 {index} 条'}：部分抓取成功，请确认数据后继续管理。"
            )
        return warnings

    @staticmethod
    def _utc_now() -> str:
        return (
            datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
