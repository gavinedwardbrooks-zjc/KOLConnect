from __future__ import annotations

"""Fail the build when its SQLite runtime cannot safely support WAL authority."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from storage.sqlite_runtime import (  # noqa: E402
    VENDORED_WINDOWS_SQLITE_SHA256,
    require_safe_sqlite_runtime,
    vendored_runtime_digest,
)


def main() -> int:
    version = require_safe_sqlite_runtime()
    digest = vendored_runtime_digest()
    if sys.platform == "win32" and digest != VENDORED_WINDOWS_SQLITE_SHA256:
        raise SystemExit("Vendored Windows SQLite runtime digest is invalid.")
    print(f"SQLite runtime gate: PASS | version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
