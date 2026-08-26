from __future__ import annotations

"""Small Feishu Bitable transport boundary for the M7 read-only replica."""

from dataclasses import dataclass
from typing import Any, Iterable

import requests


DEFAULT_BATCH_SIZE = 100
DEFAULT_PAGE_SIZE = 500


@dataclass(frozen=True)
class FeishuClientError(RuntimeError):
    code: str
    message: str
    retry_after: str = ""

    def __str__(self) -> str:
        return self.message

    def to_safe_dict(self) -> dict[str, str]:
        result = {"code": self.code, "message": self.message}
        if self.retry_after:
            result["retry_after"] = self.retry_after
        return result


class FeishuClient:
    """Perform authenticated Bitable operations without domain decisions."""

    TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"

    def __init__(
        self,
        config: dict[str, Any],
        *,
        transport: Any = requests,
        batch_size: int = DEFAULT_BATCH_SIZE,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> None:
        self._config = {key: str(value or "").strip() for key, value in config.items()}
        self._transport = transport
        self.batch_size = max(1, int(batch_size))
        self.page_size = max(1, int(page_size))
        self._access_token = ""

    def validate_configuration(self) -> None:
        required = (
            "app_id", "app_secret", "app_token", "creator_table_id", "account_table_id",
        )
        missing = [key for key in required if not self._config.get(key)]
        if missing:
            raise FeishuClientError(
                "CONFIGURATION_ERROR",
                "飞书同步配置不完整。",
            )

    def authenticate(self) -> None:
        self.validate_configuration()
        data = self._request_json(
            "POST",
            self.TOKEN_URL,
            json={
                "app_id": self._config["app_id"],
                "app_secret": self._config["app_secret"],
            },
            authenticated=False,
            timeout=10,
        )
        token = str(data.get("tenant_access_token") or "").strip()
        if not token:
            raise FeishuClientError("AUTHENTICATION_FAILED", "飞书身份验证失败。")
        self._access_token = token

    def list_fields(self, table_id: str) -> list[dict[str, Any]]:
        return self._list_paginated(
            f"{self._table_url(table_id)}/fields",
            item_key="items",
        )

    def list_records(self, table_id: str) -> list[dict[str, Any]]:
        return self._list_paginated(
            f"{self._table_url(table_id)}/records",
            item_key="items",
        )

    def batch_create(
        self, table_id: str, records: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        payload = [{"fields": dict(fields)} for fields in records]
        if not payload:
            return []
        if len(payload) > self.batch_size:
            raise ValueError("Feishu batch exceeds the configured batch size.")
        data = self._request_json(
            "POST",
            f"{self._table_url(table_id)}/records/batch_create",
            json={"records": payload},
            timeout=20,
        )
        return list((data.get("data") or {}).get("records") or [])

    def batch_update(
        self, table_id: str, records: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        payload = [
            {"record_id": str(item["record_id"]), "fields": dict(item["fields"])}
            for item in records
        ]
        if not payload:
            return []
        if len(payload) > self.batch_size:
            raise ValueError("Feishu batch exceeds the configured batch size.")
        data = self._request_json(
            "POST",
            f"{self._table_url(table_id)}/records/batch_update",
            json={"records": payload},
            timeout=20,
        )
        return list((data.get("data") or {}).get("records") or [])

    def batch_delete(self, table_id: str, record_ids: Iterable[str]) -> list[dict[str, Any]]:
        payload = [str(record_id or "").strip() for record_id in record_ids]
        if not payload or any(not record_id for record_id in payload):
            raise ValueError("Feishu record IDs must be non-empty.")
        if len(payload) != len(set(payload)):
            raise ValueError("Feishu record IDs must be unique.")
        if len(payload) > self.batch_size:
            raise ValueError("Feishu batch exceeds the configured batch size.")
        data = self._request_json(
            "POST",
            f"{self._table_url(table_id)}/records/batch_delete",
            json={"records": payload},
            timeout=20,
        )
        return list((data.get("data") or {}).get("records") or [])

    def _list_paginated(self, url: str, *, item_key: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token = ""
        while True:
            params: dict[str, Any] = {"page_size": self.page_size}
            if page_token:
                params["page_token"] = page_token
            response = self._request_json("GET", url, params=params, timeout=15)
            data = response.get("data") or {}
            items.extend(item for item in data.get(item_key) or [] if isinstance(item, dict))
            if not data.get("has_more"):
                return items
            page_token = str(data.get("page_token") or "").strip()
            if not page_token:
                raise FeishuClientError("REMOTE_ERROR", "飞书分页响应无效。")

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        authenticated: bool = True,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if authenticated and not self._access_token:
            self.authenticate()
        headers = dict(kwargs.pop("headers", {}) or {})
        if authenticated:
            headers["Authorization"] = f"Bearer {self._access_token}"
        headers.setdefault("Content-Type", "application/json")
        try:
            response = self._transport.request(method, url, headers=headers, **kwargs)
        except (requests.RequestException, OSError) as exc:
            raise FeishuClientError(
                "TRANSIENT_NETWORK_ERROR", "无法连接飞书服务。"
            ) from exc

        status = int(getattr(response, "status_code", 0) or 0)
        retry_after = str((getattr(response, "headers", {}) or {}).get("Retry-After") or "")
        if status == 401:
            raise FeishuClientError("AUTHENTICATION_FAILED", "飞书身份验证失败。")
        if status == 403:
            raise FeishuClientError("PERMISSION_DENIED", "飞书应用权限不足。")
        if status == 429:
            raise FeishuClientError("RATE_LIMITED", "飞书请求频率受限。", retry_after)
        if status == 409:
            raise FeishuClientError("REMOTE_CONFLICT", "飞书记录发生冲突。")
        if status == 404:
            raise FeishuClientError("NOT_FOUND", "飞书记录不存在。")
        if status >= 500:
            raise FeishuClientError("TRANSIENT_REMOTE_ERROR", "飞书服务暂时不可用。")
        if status >= 400:
            raise FeishuClientError("INVALID_REQUEST", "飞书拒绝了同步请求。")

        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            raise FeishuClientError("REMOTE_ERROR", "飞书返回了无效响应。") from exc
        if not isinstance(data, dict):
            raise FeishuClientError("REMOTE_ERROR", "飞书返回了无效响应。")
        if int(data.get("code") or 0) != 0:
            message = str(data.get("msg") or "").casefold()
            if "permission" in message or "forbidden" in message:
                code = "PERMISSION_DENIED"
            elif "token" in message or "auth" in message:
                code = "AUTHENTICATION_FAILED"
            elif "rate" in message or "frequency" in message:
                code = "RATE_LIMITED"
            else:
                code = "REMOTE_ERROR"
            safe_message = {
                "PERMISSION_DENIED": "飞书应用权限不足。",
                "AUTHENTICATION_FAILED": "飞书身份验证失败。",
                "RATE_LIMITED": "飞书请求频率受限。",
                "REMOTE_ERROR": "飞书请求失败。",
            }[code]
            raise FeishuClientError(code, safe_message, retry_after)
        return data

    def _table_url(self, table_id: str) -> str:
        table_id = str(table_id or "").strip()
        if not table_id:
            raise FeishuClientError("CONFIGURATION_ERROR", "飞书 Table ID 缺失。")
        return (
            "https://open.feishu.cn/open-apis/bitable/v1/apps/"
            f"{self._config['app_token']}/tables/{table_id}"
        )

    @property
    def creator_table_id(self) -> str:
        return self._config.get("creator_table_id", "")

    @property
    def account_table_id(self) -> str:
        return self._config.get("account_table_id", "")
