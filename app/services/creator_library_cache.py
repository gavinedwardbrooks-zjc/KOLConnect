from __future__ import annotations

"""Thread-safe, process-local cache for the Creator Library read model."""

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from local_storage_lock import shared_storage_lock


SnapshotLoader = Callable[[], dict[str, Any]]
WorkbookFingerprint = tuple[str, int, int]


class CreatorLibraryCache:
    """Cache immutable snapshots while Excel remains the source of truth."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._entry: tuple[WorkbookFingerprint, dict[str, Any]] | None = None

    def get_snapshot(
        self,
        workbook_path: Path,
        loader: SnapshotLoader,
    ) -> dict[str, Any]:
        """Return a detached snapshot, rebuilding once when the file changed."""
        path = Path(workbook_path)
        fingerprint = self._fingerprint(path)
        entry = self._entry
        if entry is not None and entry[0] == fingerprint:
            return deepcopy(entry[1])

        # Match the mutation lock order: shared storage first, cache lock second.
        with shared_storage_lock():
            with self._lock:
                # A waiting cold reader must observe the snapshot built by the winner.
                fingerprint = self._fingerprint(path)
                entry = self._entry
                if entry is not None and entry[0] == fingerprint:
                    return deepcopy(entry[1])

                snapshot = loader()
                fingerprint = self._fingerprint(path)
                stored = deepcopy(snapshot)
                self._entry = (fingerprint, stored)
                return deepcopy(stored)

    def invalidate(self) -> None:
        with self._lock:
            self._entry = None

    @staticmethod
    def _fingerprint(path: Path) -> WorkbookFingerprint:
        resolved = str(path.resolve())
        try:
            stat = path.stat()
        except FileNotFoundError:
            return (resolved, -1, -1)
        return (resolved, stat.st_mtime_ns, stat.st_size)
