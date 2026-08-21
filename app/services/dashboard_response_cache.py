from __future__ import annotations

"""Immutable, process-local cache for the complete Dashboard response."""

from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from local_storage_lock import shared_storage_lock


DashboardLoader = Callable[[], dict[str, Any]]
UtcDateProvider = Callable[[], date]


class DashboardResponseCacheUnstableBuild(RuntimeError):
    """The workbook changed while a Dashboard snapshot was being built."""


@dataclass(frozen=True)
class DashboardFingerprint:
    path: str
    mtime_ns: int
    size: int
    utc_date: str


class DashboardResponseCache:
    """Serve immutable Dashboard payloads until the workbook or UTC day changes."""

    def __init__(self, utc_date_provider: UtcDateProvider | None = None) -> None:
        self._lock = RLock()
        self._entry: tuple[DashboardFingerprint, dict[str, Any]] | None = None
        self._utc_date_provider = utc_date_provider or self._current_utc_date

    def get_response(
        self, workbook_path: Path | str, loader: DashboardLoader
    ) -> dict[str, Any]:
        path = Path(workbook_path)
        fingerprint = self._fingerprint(path)
        with self._lock:
            if self._is_current(fingerprint):
                return deepcopy(self._entry[1])  # type: ignore[index]

        # Keep the global order: shared storage lock, then the cache lock, then I/O.
        with shared_storage_lock():
            with self._lock:
                fingerprint = self._fingerprint(path)
                if self._is_current(fingerprint):
                    return deepcopy(self._entry[1])  # type: ignore[index]

                payload = loader()
                after_build = self._fingerprint(path)
                if after_build != fingerprint:
                    raise DashboardResponseCacheUnstableBuild(
                        "Dashboard workbook changed while building its response."
                    )
                self._entry = (after_build, deepcopy(payload))
                return deepcopy(payload)

    def invalidate(self) -> None:
        """Discard the snapshot after a successfully committed relevant mutation."""
        with self._lock:
            self._entry = None

    def _is_current(self, fingerprint: DashboardFingerprint) -> bool:
        return self._entry is not None and self._entry[0] == fingerprint

    def _fingerprint(self, workbook_path: Path) -> DashboardFingerprint:
        resolved = workbook_path.expanduser().resolve()
        try:
            stat = resolved.stat()
            mtime_ns = stat.st_mtime_ns
            size = stat.st_size
        except FileNotFoundError:
            mtime_ns = -1
            size = -1
        return DashboardFingerprint(
            path=str(resolved),
            mtime_ns=mtime_ns,
            size=size,
            utc_date=self._utc_date_provider().isoformat(),
        )

    @staticmethod
    def _current_utc_date() -> date:
        return datetime.now(timezone.utc).date()
