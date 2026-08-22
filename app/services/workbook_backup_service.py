from __future__ import annotations

"""Manual backup orchestration for the active Creator Library workbook."""

import errno
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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
        now_provider: Callable[[], datetime] | None = None,
        token_provider: Callable[[], str] | None = None,
    ) -> None:
        self._workbook_path_provider = workbook_path_provider
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._token_provider = token_provider or (lambda: uuid.uuid4().hex[:8])

    def create_backup(self) -> dict[str, object]:
        workbook_path = Path(self._workbook_path_provider()).expanduser()
        if not workbook_path.is_file():
            raise WorkbookBackupNotFoundError("达人库 Excel 文件不存在，无法创建备份。")

        created_at = self._now_provider().astimezone(timezone.utc)
        timestamp = created_at.strftime("%Y%m%d_%H%M%S_%f")
        token = self._safe_token(self._token_provider())
        filename = f"{workbook_path.stem}_{timestamp}_{token}{workbook_path.suffix}"
        backup_path = workbook_path.parent / "backups" / filename

        try:
            ExcelWorkbookStore(workbook_path).create_transaction_backup(backup_path)
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
