from __future__ import annotations

"""Small Feishu Bitable transport boundary for the M7 read-only replica."""

from dataclasses import dataclass
import gzip
import json
from pathlib import Path
import socket
import ssl
import sys
from typing import Any, Iterable
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import zlib

import certifi
import requests


DEFAULT_BATCH_SIZE = 100
DEFAULT_PAGE_SIZE = 500
FEISHU_USER_AGENT = "KOLConnect/2.0.2"


def is_packaged_macos() -> bool:
    return sys.platform == "darwin" and bool(getattr(sys, "frozen", False))


def resolve_ca_bundle() -> str:
    """Resolve the verified CA file bundled with a frozen macOS app."""
    candidates: list[Path] = []
    meipass = str(getattr(sys, "_MEIPASS", "") or "").strip()
    if meipass:
        bundle_root = Path(meipass)
        candidates.extend((
            bundle_root / "certifi" / "cacert.pem",
            bundle_root.parent / "Resources" / "certifi" / "cacert.pem",
        ))
    executable = str(getattr(sys, "executable", "") or "").strip()
    if executable:
        executable_path = Path(executable)
        if len(executable_path.parents) >= 2:
            candidates.append(
                executable_path.parents[1] / "Resources" / "certifi" / "cacert.pem"
            )
    candidates.append(Path(certifi.where()))

    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.expanduser().resolve(strict=False))
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.is_file():
            return str(candidate)
    raise FeishuClientError(
        "TLS_CONFIGURATION_ERROR",
        "KOLConnect 无法加载安全证书资源。",
        failure_stage="tls_configuration",
        exception_class="FileNotFoundError",
        transport_reason_type="FileNotFoundError",
        transport_reason_category="CA_BUNDLE_MISSING",
        transport_reason_message="bundled CA certificate file is unavailable",
    )


def build_verified_ssl_context(ca_bundle: str) -> ssl.SSLContext:
    ca_path = Path(str(ca_bundle or "").strip())
    if not ca_path.is_file():
        raise FeishuClientError(
            "TLS_CONFIGURATION_ERROR",
            "KOLConnect 无法加载安全证书资源。",
            failure_stage="tls_configuration",
            exception_class="FileNotFoundError",
            transport_reason_type="FileNotFoundError",
            transport_reason_category="CA_BUNDLE_MISSING",
            transport_reason_message="bundled CA certificate file is unavailable",
        )
    try:
        return ssl.create_default_context(cafile=str(ca_path))
    except (OSError, ssl.SSLError) as exc:
        details = _safe_transport_reason(exc)
        raise FeishuClientError(
            "TLS_CONFIGURATION_ERROR",
            "KOLConnect 无法加载安全证书资源。",
            failure_stage="tls_configuration",
            exception_class=type(exc).__name__,
            **details,
        ) from exc


def _safe_transport_reason(exc: BaseException) -> dict[str, str | int]:
    reason: BaseException = exc
    nested = getattr(exc, "reason", None)
    if isinstance(nested, BaseException):
        reason = nested
    chain: list[BaseException] = []
    current: BaseException | None = reason
    while current is not None and current not in chain:
        chain.append(current)
        cause = current.__cause__ or current.__context__
        current = cause if isinstance(cause, BaseException) else None

    names = {type(item).__name__ for item in chain}
    diagnostic_text = " ".join(str(item).casefold() for item in chain)
    if any(isinstance(item, ssl.SSLCertVerificationError) for item in chain) or "certificate verify failed" in diagnostic_text:
        category, message = "CERTIFICATE_VERIFY_FAILED", "certificate verification failed"
    elif any(isinstance(item, socket.gaierror) for item in chain) or "NameResolutionError" in names or "name resolution" in diagnostic_text:
        category, message = "DNS_FAILURE", "host name resolution failed"
    elif any(isinstance(item, ConnectionRefusedError) for item in chain):
        category, message = "CONNECTION_REFUSED", "remote connection was refused"
    elif any(isinstance(item, (TimeoutError, socket.timeout)) for item in chain) or "ReadTimeout" in names or "ConnectTimeout" in names or "timed out" in diagnostic_text:
        category, message = "TIMEOUT", "network operation timed out"
    elif "ProxyError" in names or "proxy" in diagnostic_text:
        category, message = "PROXY_FAILURE", "proxy connection failed"
    elif any(isinstance(item, ssl.SSLError) for item in chain) or "SSLError" in names:
        category, message = "SSL_ERROR", "secure connection failed"
    elif "InvalidURL" in names or "URLRequired" in names or isinstance(reason, ValueError) or "invalid url" in diagnostic_text:
        category, message = "MALFORMED_URL", "request URL is invalid"
    elif any(isinstance(item, ConnectionError) for item in chain) or "ConnectionError" in names:
        category, message = "CONNECTION_FAILURE", "network connection failed"
    else:
        category, message = "NETWORK_ERROR", "network transport failed"

    errno = next(
        (getattr(item, "errno", None) for item in chain if getattr(item, "errno", None) is not None),
        0,
    )
    return {
        "transport_reason_type": type(reason).__name__,
        "transport_reason_category": category,
        "transport_reason_message": message,
        "transport_errno": int(errno) if isinstance(errno, int) else 0,
    }


@dataclass(frozen=True)
class FeishuClientError(RuntimeError):
    code: str
    message: str
    retry_after: str = ""
    http_status: int = 0
    api_code: int = 0
    failure_stage: str = "unknown"
    exception_class: str = ""
    response_shape: str = "unknown"
    pagination_pages: int = 0
    transport_reason_type: str = ""
    transport_reason_category: str = ""
    transport_reason_message: str = ""
    transport_errno: int = 0
    operation: str = ""
    endpoint_category: str = ""
    table_role: str = ""

    def __str__(self) -> str:
        return self.message

    def to_safe_dict(self) -> dict[str, Any]:
        safe_message = {
            "PERMISSION_DENIED": "飞书应用权限不足。",
            "AUTHENTICATION_FAILED": "飞书身份验证失败。",
            "RATE_LIMITED": "飞书请求频率受限。",
            "BASE_NOT_FOUND": "飞书 Base 不存在或应用无法访问。",
            "TABLE_NOT_FOUND": "飞书数据表不存在或应用无法访问。",
            "FIELD_NOT_FOUND": "飞书字段不存在。",
            "RECORD_NOT_FOUND": "飞书记录不存在。",
            "INVALID_RELATION_VALUE": "飞书关联字段值无效。",
            "INVALID_FIELD_VALUE": "飞书字段值无效。",
            "WRITE_CONFLICT": "飞书记录写入冲突。",
            "REMOTE_VALIDATION_ERROR": "飞书拒绝了无效的数据。",
            "TRANSIENT_NETWORK_ERROR": "无法连接飞书服务。",
            "TRANSIENT_REMOTE_ERROR": "飞书服务暂时不可用。",
        }.get(self.code, "飞书请求失败。")
        result: dict[str, Any] = {
            "code": self.code,
            "message": safe_message,
            "feishu_api_code": self.api_code,
            "failure_stage": self.failure_stage,
            "http_status": self.http_status,
        }
        if self.retry_after:
            result["retry_after"] = self.retry_after
        if self.operation:
            result["operation"] = self.operation
        if self.endpoint_category:
            result["endpoint_category"] = self.endpoint_category
        if self.table_role:
            result["table_role"] = self.table_role
        return result

    def with_operation_context(
        self, *, operation: str, endpoint_category: str, table_role: str
    ) -> "FeishuClientError":
        return FeishuClientError(
            self.code,
            self.message,
            self.retry_after,
            self.http_status,
            self.api_code,
            self.failure_stage,
            self.exception_class,
            self.response_shape,
            self.pagination_pages,
            self.transport_reason_type,
            self.transport_reason_category,
            self.transport_reason_message,
            self.transport_errno,
            operation,
            endpoint_category,
            table_role,
        )


@dataclass(frozen=True)
class FieldFetchResult:
    ok: bool
    fields: tuple[dict[str, Any], ...] = ()
    used_fallback: bool = False
    primary_error: FeishuClientError | None = None
    fallback_error: FeishuClientError | None = None
    pagination_pages: int = 0
    parser_result_shape: str = "data.items"


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
        fallback_urlopen: Any = urllib_request.urlopen,
        packaged_macos: bool | None = None,
        ca_bundle_resolver: Any = resolve_ca_bundle,
        ssl_context_builder: Any = build_verified_ssl_context,
    ) -> None:
        self._config = {key: str(value or "").strip() for key, value in config.items()}
        self._transport = transport
        self.batch_size = max(1, int(batch_size))
        self.page_size = max(1, int(page_size))
        self._access_token = ""
        self._fallback_urlopen = fallback_urlopen
        self._packaged_macos = is_packaged_macos() if packaged_macos is None else packaged_macos
        self._ca_bundle = ""
        self._fallback_ssl_context: ssl.SSLContext | None = None
        if self._packaged_macos:
            self._ca_bundle = str(ca_bundle_resolver())
            self._fallback_ssl_context = ssl_context_builder(self._ca_bundle)

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
        fields, _pages = self._list_paginated_with_pages(
            f"{self._table_url(table_id)}/fields",
            item_key="items",
            require_items=True,
        )
        return fields

    def fetch_fields(self, table_id: str) -> FieldFetchResult:
        """Fetch field metadata with one bounded, read-only compatibility fallback."""
        try:
            fields, pages = self._list_paginated_with_pages(
                f"{self._table_url(table_id)}/fields",
                item_key="items",
                require_items=True,
            )
            return FieldFetchResult(
                True, tuple(fields), pagination_pages=pages
            )
        except FeishuClientError as primary_error:
            try:
                fields, pages = self._list_fields_with_stdlib(table_id)
            except FeishuClientError as fallback_error:
                return FieldFetchResult(
                    False,
                    used_fallback=True,
                    primary_error=primary_error,
                    fallback_error=fallback_error,
                )
            return FieldFetchResult(
                True,
                tuple(fields),
                used_fallback=True,
                primary_error=primary_error,
                pagination_pages=pages,
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

    def _list_paginated(
        self, url: str, *, item_key: str, require_items: bool = False
    ) -> list[dict[str, Any]]:
        items, _pages = self._list_paginated_with_pages(
            url, item_key=item_key, require_items=require_items
        )
        return items

    def _list_paginated_with_pages(
        self, url: str, *, item_key: str, require_items: bool = False
    ) -> tuple[list[dict[str, Any]], int]:
        items: list[dict[str, Any]] = []
        page_token = ""
        seen_page_tokens: set[str] = set()
        pages = 0
        while True:
            params: dict[str, Any] = {"page_size": self.page_size}
            if page_token:
                params["page_token"] = page_token
            try:
                response = self._request_json(
                    "GET", url, params=params, timeout=15, allow_redirects=True
                )
            except FeishuClientError as exc:
                raise self._with_field_context(
                    exc, exc.failure_stage, None, pages
                ) from exc
            pages += 1
            data = response.get("data")
            if not isinstance(data, dict):
                raise self._field_error(
                    "REMOTE_ERROR", "飞书返回了无效响应。", "shape",
                    response_shape=self._shape_of(data), pagination_pages=pages,
                )
            page_items = data.get(item_key)
            if require_items and not isinstance(page_items, list):
                raise self._field_error(
                    "REMOTE_ERROR", "飞书返回了无效字段响应。", "shape",
                    response_shape=self._shape_of(page_items), pagination_pages=pages,
                )
            if require_items and any(not isinstance(item, dict) for item in page_items):
                raise self._field_error(
                    "REMOTE_ERROR", "飞书返回了无效字段响应。", "shape",
                    response_shape="data.items.non_object", pagination_pages=pages,
                )
            items.extend(item for item in page_items or [] if isinstance(item, dict))
            if not data.get("has_more"):
                return items, pages
            next_page_token = str(data.get("page_token") or "").strip()
            if not next_page_token or next_page_token in seen_page_tokens:
                raise self._field_error(
                    "REMOTE_ERROR", "飞书分页响应无效。", "pagination",
                    response_shape="data.items", pagination_pages=pages,
                )
            seen_page_tokens.add(next_page_token)
            page_token = next_page_token

    def _list_fields_with_stdlib(
        self, table_id: str
    ) -> tuple[list[dict[str, Any]], int]:
        if not self._access_token:
            self.authenticate()
        url = f"{self._table_url(table_id)}/fields"
        items: list[dict[str, Any]] = []
        page_token = ""
        seen_page_tokens: set[str] = set()
        pages = 0
        while True:
            params: dict[str, Any] = {"page_size": self.page_size}
            if page_token:
                params["page_token"] = page_token
            query_url = f"{url}?{urllib_parse.urlencode(params)}"
            request = urllib_request.Request(
                query_url,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip, deflate",
                    "User-Agent": FEISHU_USER_AGENT,
                },
                method="GET",
            )
            try:
                if self._packaged_macos:
                    response_context = self._fallback_urlopen(
                        request, timeout=15, context=self._fallback_ssl_context
                    )
                else:
                    response_context = self._fallback_urlopen(request, timeout=15)
                with response_context as response:
                    status = int(getattr(response, "status", 0) or response.getcode() or 0)
                    raw = response.read()
                    headers = getattr(response, "headers", {}) or {}
            except urllib_error.HTTPError as exc:
                error = self._http_error(
                    int(exc.code or 0),
                    str((exc.headers or {}).get("Retry-After") or ""),
                )
                raise self._with_field_context(error, "http", exc, pages) from exc
            except (urllib_error.URLError, OSError, TimeoutError) as exc:
                details = _safe_transport_reason(exc)
                raise self._field_error(
                    "TRANSIENT_NETWORK_ERROR", "无法连接飞书服务。", "transport",
                    exception_class=type(exc).__name__, pagination_pages=pages,
                    **details,
                ) from exc
            if status >= 400:
                raise self._with_field_context(
                    self._http_error(status, str(headers.get("Retry-After") or "")),
                    "http", None, pages,
                )
            pages += 1
            try:
                payload = self._decode_response_body(raw, headers)
            except (UnicodeDecodeError, ValueError, OSError, zlib.error) as exc:
                raise self._field_error(
                    "REMOTE_ERROR", "飞书返回了无效响应。", "json",
                    exception_class=type(exc).__name__, response_shape="invalid_json",
                    pagination_pages=pages,
                ) from exc
            try:
                data = self._validated_api_payload(payload, http_status=status)
            except FeishuClientError as exc:
                raise self._with_field_context(exc, "api", None, pages) from exc
            page_data = data.get("data")
            if not isinstance(page_data, dict) or not isinstance(page_data.get("items"), list):
                raise self._field_error(
                    "REMOTE_ERROR", "飞书返回了无效字段响应。", "shape",
                    response_shape=self._shape_of(page_data), pagination_pages=pages,
                )
            if any(not isinstance(item, dict) for item in page_data["items"]):
                raise self._field_error(
                    "REMOTE_ERROR", "飞书返回了无效字段响应。", "shape",
                    response_shape="data.items.non_object", pagination_pages=pages,
                )
            items.extend(item for item in page_data["items"] if isinstance(item, dict))
            if not page_data.get("has_more"):
                return items, pages
            next_page_token = str(page_data.get("page_token") or "").strip()
            if not next_page_token or next_page_token in seen_page_tokens:
                raise self._field_error(
                    "REMOTE_ERROR", "飞书分页响应无效。", "pagination",
                    response_shape="data.items", pagination_pages=pages,
                )
            seen_page_tokens.add(next_page_token)
            page_token = next_page_token

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
        headers.setdefault("Accept", "application/json")
        headers.setdefault("User-Agent", FEISHU_USER_AGENT)
        if self._packaged_macos:
            kwargs.setdefault("verify", self._ca_bundle)
        try:
            response = self._transport.request(method, url, headers=headers, **kwargs)
        except (requests.RequestException, OSError) as exc:
            details = _safe_transport_reason(exc)
            raise self._field_error(
                "TRANSIENT_NETWORK_ERROR", "无法连接飞书服务。", "transport",
                exception_class=type(exc).__name__,
                **details,
            ) from exc

        status = int(getattr(response, "status_code", 0) or 0)
        retry_after = str((getattr(response, "headers", {}) or {}).get("Retry-After") or "")
        if status >= 400:
            raise self._with_field_context(
                self._http_error(status, retry_after), "http"
            )

        try:
            data = response.json()
        except (TypeError, ValueError) as exc:
            raise self._field_error(
                "REMOTE_ERROR", "飞书返回了无效响应。", "json",
                exception_class=type(exc).__name__, response_shape="invalid_json",
            ) from exc
        try:
            return self._validated_api_payload(
                data, http_status=status, retry_after=retry_after
            )
        except FeishuClientError as exc:
            raise self._with_field_context(exc, "api") from exc

    @staticmethod
    def _validated_api_payload(
        data: Any, *, http_status: int = 0, retry_after: str = ""
    ) -> dict[str, Any]:
        if not isinstance(data, dict):
            raise FeishuClientError(
                "REMOTE_ERROR", "飞书返回了无效响应。",
                http_status=http_status, failure_stage="shape",
                response_shape=FeishuClient._shape_of(data),
            )
        api_code = int(data.get("code") or 0)
        if api_code != 0:
            message = str(data.get("msg") or "").casefold()
            if api_code == 1254302 or "permission" in message or "forbidden" in message:
                code = "PERMISSION_DENIED"
            elif api_code in {1254061, 1254064}:
                code = "INVALID_FIELD_VALUE"
            elif "token" in message or "auth" in message:
                code = "AUTHENTICATION_FAILED"
            elif "rate" in message or "frequency" in message or "too many" in message:
                code = "RATE_LIMITED"
            elif ("base" in message or "app_token" in message) and (
                "not found" in message or "not exist" in message
            ):
                code = "BASE_NOT_FOUND"
            elif "table" in message and ("not found" in message or "not exist" in message):
                code = "TABLE_NOT_FOUND"
            elif "field" in message and ("not found" in message or "not exist" in message):
                code = "FIELD_NOT_FOUND"
            elif "record" in message and ("not found" in message or "not exist" in message):
                code = "RECORD_NOT_FOUND"
            elif "relation" in message and ("invalid" in message or "illegal" in message):
                code = "INVALID_RELATION_VALUE"
            elif "field" in message and ("invalid" in message or "illegal" in message):
                code = "INVALID_FIELD_VALUE"
            elif "conflict" in message:
                code = "WRITE_CONFLICT"
            elif any(token in message for token in ("invalid", "illegal", "parameter", "validation")):
                code = "REMOTE_VALIDATION_ERROR"
            else:
                code = "REMOTE_ERROR"
            safe_message = {
                "PERMISSION_DENIED": "飞书应用权限不足。",
                "AUTHENTICATION_FAILED": "飞书身份验证失败。",
                "RATE_LIMITED": "飞书请求频率受限。",
                "BASE_NOT_FOUND": "飞书 Base 不存在或应用无法访问。",
                "TABLE_NOT_FOUND": "飞书数据表不存在或应用无法访问。",
                "FIELD_NOT_FOUND": "飞书字段不存在。",
                "RECORD_NOT_FOUND": "飞书记录不存在。",
                "INVALID_RELATION_VALUE": "飞书关联字段值无效。",
                "INVALID_FIELD_VALUE": "飞书字段值无效。",
                "WRITE_CONFLICT": "飞书记录写入冲突。",
                "REMOTE_VALIDATION_ERROR": "飞书拒绝了无效的数据。",
                "REMOTE_ERROR": "飞书请求失败。",
            }[code]
            raise FeishuClientError(
                code, safe_message, retry_after, http_status=http_status,
                api_code=api_code, failure_stage="api", response_shape="object",
            )
        return data

    @staticmethod
    def _decode_response_body(raw: bytes, headers: Any) -> Any:
        encoding = str(headers.get("Content-Encoding") or "").casefold()
        if "gzip" in encoding:
            raw = gzip.decompress(raw)
        elif "deflate" in encoding:
            raw = zlib.decompress(raw)
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _shape_of(value: Any) -> str:
        if value is None:
            return "missing"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        return type(value).__name__

    @staticmethod
    def _field_error(
        code: str,
        message: str,
        failure_stage: str,
        *,
        exception_class: str = "",
        response_shape: str = "unknown",
        pagination_pages: int = 0,
        http_status: int = 0,
        api_code: int = 0,
        transport_reason_type: str = "",
        transport_reason_category: str = "",
        transport_reason_message: str = "",
        transport_errno: int = 0,
    ) -> FeishuClientError:
        return FeishuClientError(
            code,
            message,
            http_status=http_status,
            api_code=api_code,
            failure_stage=failure_stage,
            exception_class=exception_class,
            response_shape=response_shape,
            pagination_pages=pagination_pages,
            transport_reason_type=transport_reason_type,
            transport_reason_category=transport_reason_category,
            transport_reason_message=transport_reason_message,
            transport_errno=transport_errno,
        )

    @staticmethod
    def _with_field_context(
        error: FeishuClientError,
        failure_stage: str,
        exception: BaseException | None = None,
        pagination_pages: int | None = None,
    ) -> FeishuClientError:
        return FeishuClientError(
            error.code,
            error.message,
            error.retry_after,
            error.http_status,
            error.api_code,
            error.failure_stage if error.failure_stage != "unknown" else failure_stage,
            error.exception_class or (type(exception).__name__ if exception else ""),
            error.response_shape,
            error.pagination_pages if pagination_pages is None else pagination_pages,
            error.transport_reason_type,
            error.transport_reason_category,
            error.transport_reason_message,
            error.transport_errno,
            error.operation,
            error.endpoint_category,
            error.table_role,
        )

    @staticmethod
    def _http_error(status: int, retry_after: str = "") -> FeishuClientError:
        if status == 401:
            return FeishuClientError("AUTHENTICATION_FAILED", "飞书身份验证失败。", http_status=status)
        if status == 403:
            return FeishuClientError("PERMISSION_DENIED", "飞书应用权限不足。", http_status=status)
        if status == 429:
            return FeishuClientError("RATE_LIMITED", "飞书请求频率受限。", retry_after, status)
        if status == 409:
            return FeishuClientError("REMOTE_CONFLICT", "飞书记录发生冲突。", http_status=status)
        if status == 404:
            return FeishuClientError("NOT_FOUND", "飞书记录不存在。", http_status=status)
        if status >= 500:
            return FeishuClientError("TRANSIENT_REMOTE_ERROR", "飞书服务暂时不可用。", http_status=status)
        return FeishuClientError("INVALID_REQUEST", "飞书拒绝了同步请求。", http_status=status)

    def _table_url(self, table_id: str) -> str:
        table_id = str(table_id or "").strip()
        app_token = self._config.get("app_token", "")
        if not table_id or not app_token:
            raise FeishuClientError("CONFIGURATION_ERROR", "飞书 Table ID 缺失。")
        url = (
            "https://open.feishu.cn/open-apis/bitable/v1/apps/"
            f"{urllib_parse.quote(app_token, safe='')}/tables/"
            f"{urllib_parse.quote(table_id, safe='')}"
        )
        parsed = urllib_parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "open.feishu.cn":
            raise FeishuClientError(
                "CONFIGURATION_ERROR", "飞书请求地址无效。",
                failure_stage="url", exception_class="ValueError",
                transport_reason_type="ValueError",
                transport_reason_category="MALFORMED_URL",
                transport_reason_message="request URL is invalid",
            )
        return url

    @property
    def creator_table_id(self) -> str:
        return self._config.get("creator_table_id", "")

    @property
    def account_table_id(self) -> str:
        return self._config.get("account_table_id", "")
