from __future__ import annotations

"""Pure localhost request checks shared by the local HTTP handler tests."""

from urllib.parse import urlparse


MUTATING_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
EXTENSION_MUTATION_PATHS = frozenset({"/api/extension/import"})
RUNTIME_SHUTDOWN_PATH = "/api/runtime/shutdown"


def allowed_host_header(host_header: object, port: int) -> bool:
    host = str(host_header or "").strip().lower()
    return host in {f"127.0.0.1:{port}", f"localhost:{port}"}


def allowed_mutation_origin(origin_header: object, path: str, port: int) -> bool:
    origin = str(origin_header or "").strip()
    if not origin:
        return True
    try:
        parsed = urlparse(origin)
        origin_port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme == "http"
        and parsed.hostname in {"127.0.0.1", "localhost"}
        and origin_port == port
        and not parsed.username
        and not parsed.password
        and not parsed.path
    ):
        return True
    return bool(
        path in EXTENSION_MUTATION_PATHS
        and parsed.scheme == "chrome-extension"
        and parsed.netloc
        and not parsed.path
    )


def browser_shutdown_allowed(path: str, browser_mode: object) -> bool:
    return path == RUNTIME_SHUTDOWN_PATH and str(browser_mode or "") == "1"
