from __future__ import annotations

"""Safe bridge between the browser extension and existing mail/Creator authorities."""

from datetime import datetime, timezone
import hashlib
import json
import re
import threading
from typing import Any, Callable, Mapping

from services.mail_inbox_facts import mail_account_identity
from services.mail_send_service import MailSendError
from services.mail_template_service import MailTemplateError, normalize_language_tag


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$")


class ExtensionWorkspaceError(ValueError):
    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ExtensionWorkspaceService:
    """Expose bounded read/render/draft operations without exposing mail secrets."""

    def __init__(
        self,
        factory_provider: Callable[[], Any],
        creator_service_provider: Callable[[], Any],
        template_service_provider: Callable[[], Any],
        mail_send_service_provider: Callable[[], Any],
        mail_accounts_provider: Callable[[], list[dict[str, Any]]],
    ) -> None:
        self._factory_provider = factory_provider
        self._creator_service_provider = creator_service_provider
        self._template_service_provider = template_service_provider
        self._mail_send_service_provider = mail_send_service_provider
        self._mail_accounts_provider = mail_accounts_provider
        self._lock = threading.Lock()

    def options(self, *, platform: object, profile_url: object, audience_type: object, language: object) -> dict[str, Any]:
        identity = self._identity(platform, profile_url)
        normalized_audience = str(audience_type or "").strip().casefold()
        if normalized_audience not in {"kol", "koc"}:
            raise ExtensionWorkspaceError("EXTENSION_AUDIENCE_REQUIRED", "请选择 KOL 或 KOC。")
        normalized_language = normalize_language_tag(language)
        templates = self._template_service_provider().list_templates(
            draft_type="initial_outreach", language=normalized_language, audience_type=normalized_audience
        )
        return {
            "identity": identity,
            "templates": [self._safe_template(item) for item in templates],
            "mail_accounts": self._safe_mail_accounts(),
        }

    def render(self, payload: Mapping[str, object]) -> dict[str, Any]:
        values = self._validated_request(payload)
        rendered = self._template_service_provider().render(values["template_id"], values["variables"])
        if rendered["template_version"] != values["template_version"]:
            raise ExtensionWorkspaceError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新选择。", status=409)
        return {"identity": values["identity"], "template": values["template"], "rendered": rendered}

    def create_draft(self, payload: Mapping[str, object]) -> dict[str, Any]:
        values = self._validated_request(payload, require_mail_account=True)
        key = str(payload.get("idempotency_key") or "").strip()
        if not IDEMPOTENCY_PATTERN.fullmatch(key):
            raise ExtensionWorkspaceError("EXTENSION_IDEMPOTENCY_INVALID", "草稿请求标识无效。")
        fingerprint = self._fingerprint(values)
        with self._lock:
            existing = self._reservation(key)
            if existing:
                if existing["request_fingerprint"] != fingerprint:
                    raise ExtensionWorkspaceError("EXTENSION_IDEMPOTENCY_CONFLICT", "草稿请求标识已用于其他内容。", status=409)
                if existing["status"] == "completed" and existing.get("draft_id"):
                    return {"draft": self._mail_send_service_provider().get_draft(existing["draft_id"]),
                            "identity": values["identity"], "replayed": True}
                raise ExtensionWorkspaceError("EXTENSION_DRAFT_PENDING", "草稿正在创建，请稍后重试。", status=409)
            self._reserve(key, fingerprint)
            try:
                rendered = self._template_service_provider().render(values["template_id"], values["variables"])
                if rendered["template_version"] != values["template_version"]:
                    raise ExtensionWorkspaceError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新选择。", status=409)
                account = values["mail_account"]
                draft = self._mail_send_service_provider().create_draft({
                    "context_type": "initial",
                    "mail_account_id": account["mail_account_id"],
                    "from_address": account["email"],
                    "to_addresses": [values["identity"]["account_email"]],
                    "cc_addresses": [],
                    "subject": rendered["subject"],
                    "body_text": rendered["body"],
                })
                self._complete(key, draft["draft_id"])
                return {"draft": draft, "identity": values["identity"], "replayed": False}
            except Exception:
                self._release(key)
                raise

    def lookup_candidates(self, profile_urls: object) -> list[dict[str, Any]]:
        return self._creator_service_provider().lookup_extension_candidates(profile_urls)

    def _validated_request(self, payload: Mapping[str, object], *, require_mail_account: bool = False) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ExtensionWorkspaceError("EXTENSION_REQUEST_INVALID", "请求格式无效。")
        identity = self._identity(payload.get("platform"), payload.get("profile_url"))
        if identity.get("state") != "recorded" or not identity.get("account_uid"):
            raise ExtensionWorkspaceError("EXTENSION_ACCOUNT_REQUIRED", "请先将当前账号收录到 KOLConnect。", status=409)
        recipient = str(payload.get("recipient_email") or "").strip().casefold()
        authoritative_email = str(identity.get("account_email") or "").strip().casefold()
        if not authoritative_email or recipient != authoritative_email or not EMAIL_PATTERN.fullmatch(recipient):
            raise ExtensionWorkspaceError("EXTENSION_RECIPIENT_MISMATCH", "收件人与当前 CreatorAccount 不一致。", status=409)
        creator_name = str(payload.get("creator_name") or identity.get("creator_name") or "").strip()
        if not creator_name:
            raise ExtensionWorkspaceError("EXTENSION_CREATOR_NAME_REQUIRED", "达人称呼不能为空。")
        audience = str(payload.get("audience_type") or "").strip().casefold()
        if audience not in {"kol", "koc"}:
            raise ExtensionWorkspaceError("EXTENSION_AUDIENCE_REQUIRED", "请选择 KOL 或 KOC。")
        language = normalize_language_tag(payload.get("language"))
        template = self._template_service_provider().get_template(payload.get("template_id"))
        if template["draft_type"] != "initial_outreach" or template["language"] != language:
            raise ExtensionWorkspaceError("EXTENSION_TEMPLATE_MISMATCH", "模板用途或语言与当前选择不一致。", status=409)
        if template.get("audience_type", "all") not in {"all", audience}:
            raise ExtensionWorkspaceError("EXTENSION_TEMPLATE_MISMATCH", "模板不适用于当前达人分级。", status=409)
        version = payload.get("template_version")
        if not isinstance(version, int) or version != template["template_version"]:
            raise ExtensionWorkspaceError("MAIL_TEMPLATE_VERSION_CONFLICT", "模板已更新，请重新选择。", status=409)
        account = None
        account_id = str(payload.get("mail_account_id") or "").strip()
        if require_mail_account or account_id:
            account = next((item for item in self._mail_accounts() if item["mail_account_id"] == account_id), None)
            if account is None:
                raise ExtensionWorkspaceError("MAIL_ACCOUNT_REQUIRED", "请选择已启用的发送邮箱。")
        sender_name = str((account or {}).get("sender_name") or (account or {}).get("name") or "KOLConnect").strip()
        variables = {
            "creator_name": creator_name,
            "sender_name": sender_name,
            "brand_name": "KOLConnect",
            "collaboration_type": audience.upper(),
        }
        unsupported = set(template["required_variables"]) - set(variables)
        if unsupported:
            raise ExtensionWorkspaceError("EXTENSION_TEMPLATE_VARIABLES_UNAVAILABLE", "该模板需要在 Mail Workspace 中补充更多变量。", status=409)
        return {
            "identity": identity, "template": self._safe_template(template), "template_id": template["template_id"],
            "template_version": version, "language": language, "audience_type": audience,
            "variables": variables, "mail_account": account,
        }

    def _identity(self, platform: object, profile_url: object) -> dict[str, Any]:
        return self._creator_service_provider().get_extension_account_context(platform, profile_url)

    def _mail_accounts(self) -> list[dict[str, Any]]:
        result = []
        for account in self._mail_accounts_provider():
            if not account.get("enabled"):
                continue
            try:
                account_id, _identity = mail_account_identity(account)
            except (TypeError, ValueError):
                continue
            result.append({**account, "mail_account_id": account_id})
        return result

    def _safe_mail_accounts(self) -> list[dict[str, str]]:
        return [{key: str(account.get(key) or "") for key in ("mail_account_id", "name", "email", "sender_name")}
                for account in self._mail_accounts()]

    @staticmethod
    def _safe_template(template: Mapping[str, Any]) -> dict[str, Any]:
        keys = ("template_id", "template_version", "template_source", "name", "language", "tone",
                "audience_type", "subject_template", "body_template", "required_variables")
        return {key: template.get(key) for key in keys}

    @staticmethod
    def _fingerprint(values: Mapping[str, Any]) -> str:
        safe = {
            "account_uid": values["identity"]["account_uid"],
            "recipient": values["identity"]["account_email"].casefold(),
            "template_id": values["template_id"], "template_version": values["template_version"],
            "mail_account_id": values["mail_account"]["mail_account_id"], "variables": values["variables"],
        }
        return hashlib.sha256(json.dumps(safe, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def _reservation(self, key: str) -> dict[str, Any] | None:
        with self._factory_provider().read_connection() as connection:
            row = connection.execute("SELECT * FROM mail_extension_draft_requests WHERE idempotency_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def _reserve(self, key: str, fingerprint: str) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self._factory_provider().write_transaction() as connection:
            connection.execute(
                "INSERT INTO mail_extension_draft_requests(idempotency_key,request_fingerprint,status,created_at,updated_at) "
                "VALUES (?,?,'pending',?,?)", (key, fingerprint, now, now)
            )

    def _complete(self, key: str, draft_id: str) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        with self._factory_provider().write_transaction() as connection:
            connection.execute(
                "UPDATE mail_extension_draft_requests SET status='completed',draft_id=?,updated_at=? "
                "WHERE idempotency_key=? AND status='pending'", (draft_id, now, key)
            )

    def _release(self, key: str) -> None:
        with self._factory_provider().write_transaction() as connection:
            connection.execute(
                "DELETE FROM mail_extension_draft_requests WHERE idempotency_key=? AND status='pending'", (key,)
            )
