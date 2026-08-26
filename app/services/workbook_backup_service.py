from __future__ import annotations

"""Manual backup orchestration for the active Creator Library workbook."""

import errno
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from excel_workbook_store import ExcelWorkbookStore
from local_storage_lock import SharedStorageLockTimeout


class WorkbookBackupError(RuntimeError):
    pass


class WorkbookBackupNotFoundError(WorkbookBackupError):
    pass


class WorkbookBackupService:
    """Create one validated backup without accepting filesystem input from callers."""

    def __init__(
        self,
        workbook_path_provider: Callable[[], Path],
        *,
        store_provider: Callable[[], Any] | None = None,
        now_provider: Callable[[], datetime] | None = None,
        token_provider: Callable[[], str] | None = None,
        retention: int = 10,
    ) -> None:
        self._workbook_path_provider = workbook_path_provider
        self._store_provider = store_provider
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._token_provider = token_provider or (lambda: uuid.uuid4().hex[:8])
        self._retention = retention

    def create_backup(self) -> dict[str, object]:
        store = self._store_provider() if self._store_provider else None
        workbook_path = Path(
            store.workbook_path if store is not None else self._workbook_path_provider()
        ).expanduser()
        if not workbook_path.is_file():
            raise WorkbookBackupNotFoundError("达人库 Excel 文件不存在，无法创建备份。")

        created_at = self._now_provider().astimezone(timezone.utc)
        timestamp = created_at.strftime("%Y%m%d_%H%M%S_%f")
        token = self._safe_token(self._token_provider())
        sqlite_authority = bool(getattr(store, "is_sqlite_authority", False))
        prefix = "kolconnect_manual" if sqlite_authority else workbook_path.stem
        filename = f"{prefix}_{timestamp}_{token}{workbook_path.suffix}"
        backup_dir = (
            workbook_path.parent.parent / "backups" / "database"
            if sqlite_authority
            else workbook_path.parent / "backups"
        )
        backup_path = backup_dir / filename

        try:
            (store or ExcelWorkbookStore(workbook_path)).create_transaction_backup(
                backup_path
            )
            self._apply_retention(backup_dir, prefix, workbook_path.suffix)
        except SharedStorageLockTimeout as exc:
            raise WorkbookBackupError("达人库正在被其他操作使用，请稍后重试备份。") from exc
        except PermissionError as exc:
            raise WorkbookBackupError("无法写入备份目录，请检查目录权限。") from exc
        except OSError as exc:
            message = (
                "磁盘空间不足，无法创建达人库备份。"
                if exc.errno == errno.ENOSPC
                else "创建达人库备份失败，请检查文件和磁盘状态。"
            )
            raise WorkbookBackupError(message) from exc

        return {
            "filename": filename,
            "created_at": created_at.isoformat().replace("+00:00", "Z"),
            "size": backup_path.stat().st_size,
        }

    @staticmethod
    def _safe_token(value: object) -> str:
        token = "".join(character for character in str(value) if character.isalnum())
        return token[:16] or uuid.uuid4().hex[:8]

    def _apply_retention(self, directory: Path, prefix: str, suffix: str) -> None:
        managed = sorted(
            directory.glob(f"{prefix}_*{suffix}"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for expired in managed[self._retention :]:
            expired.unlink()
