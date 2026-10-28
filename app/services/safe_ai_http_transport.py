from __future__ import annotations

"""HTTPS transport for user-approved AI endpoints with SSRF-safe DNS pinning."""

import http.client
import ipaddress
import json
import socket
import ssl
from typing import Any, Callable
from urllib.parse import urlparse

import requests


MAX_RESPONSE_BYTES = 1_000_000


def _public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return bool(address.is_global) and not any((
        address.is_private,
        address.is_loopback,
        address.is_link_local,
        address.is_multicast,
        address.is_reserved,
        address.is_unspecified,
    ))


def resolve_public_endpoint(
    hostname: str,
    port: int,
    *,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> str:
    """Resolve once and reject the whole result if any address is non-public."""
    try:
        records = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise requests.ConnectionError("AI endpoint DNS resolution failed.") from exc
    addresses = list(dict.fromkeys(str(record[4][0]) for record in records if record[4]))
    if not addresses or any(not _public_ip(address) for address in addresses):
        raise requests.ConnectionError("AI endpoint did not resolve exclusively to public addresses.")
    return addresses[0]


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, hostname: str, port: int, pinned_ip: str, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(hostname, port=port, timeout=timeout, context=context)
        self._pinned_ip = pinned_ip

    def connect(self) -> None:
        raw = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(raw, server_hostname=self.host)


class SafeHTTPResponse:
    def __init__(self, status: int, content: bytes) -> None:
        self.status_code = status
        self.content = content

    def json(self) -> Any:
        return json.loads(self.content.decode("utf-8"))


class SafePinnedHTTPSession:
    """A minimal requests-like session that never re-resolves an approved host."""

    def __init__(
        self,
        *,
        resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
        ssl_context: ssl.SSLContext | None = None,
        connection_factory: Callable[..., http.client.HTTPSConnection] = _PinnedHTTPSConnection,
    ) -> None:
        self._resolver = resolver
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._connection_factory = connection_factory

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
        allow_redirects: bool,
    ) -> SafeHTTPResponse:
        if allow_redirects:
            raise requests.ConnectionError("AI endpoint redirects must remain disabled.")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.port not in (None, 443):
            raise requests.ConnectionError("AI endpoint is not a supported HTTPS endpoint.")
        pinned_ip = resolve_public_endpoint(parsed.hostname, parsed.port or 443, resolver=self._resolver)
        connection = self._connection_factory(
            parsed.hostname,
            parsed.port or 443,
            pinned_ip,
            float(timeout),
            self._ssl_context,
        )
        body = json_module_dumps(json)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        try:
            connection.request("POST", path, body=body, headers=headers)
            response = connection.getresponse()
            content = response.read(MAX_RESPONSE_BYTES + 1)
            return SafeHTTPResponse(int(response.status), content)
        except (socket.timeout, TimeoutError) as exc:
            raise requests.Timeout("AI endpoint request timed out.") from exc
        except requests.RequestException:
            raise
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise requests.ConnectionError("AI endpoint connection failed.") from exc
        finally:
            connection.close()


def json_module_dumps(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
