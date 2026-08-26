from __future__ import annotations

"""Measure the real C3 migration path with the deterministic Medium fixture."""

import json
from pathlib import Path
import shutil
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
SCRIPTS = ROOT / "scripts"
for path in (APP, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from benchmark_sqlite_runtime import SCALES, create_fixture
from storage.migration import ExcelToSQLiteMigrator
from storage.paths import SQLiteStoragePaths


def main() -> int:
    root = ROOT / ".pre_m8_batch3_benchmark" / "migration"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    logs = root / "logs"
    logs.mkdir()
    import app_logging
    import local_storage_lock

    app_logging.get_logs_dir = lambda: logs
    local_storage_lock.get_shared_storage_lock_path = (
        lambda: root / "locks" / "shared_storage.lock"
    )
    source_store = create_fixture(root / "source.db", SCALES["medium"])
    source = root / "medium-source.xlsx"
    source_store.export_workbook(source)
    paths = SQLiteStoragePaths.for_app_data(root / "target_appdata")
    started = time.perf_counter()
    result = ExcelToSQLiteMigrator(paths).migrate(source)
    duration = time.perf_counter() - started
    evidence = {
        "source_size_bytes": source.stat().st_size,
        "duration_seconds": round(duration, 3),
        "database_size_bytes": result.staged_database_path.stat().st_size,
        "counts": result.counts,
        "source_sha256_before": result.source_sha256_before,
        "source_sha256_after": result.source_sha256_after,
        "source_unchanged": result.source_sha256_before == result.source_sha256_after,
        "phase": "ready_for_activation",
        "activated": False,
    }
    (root / "migration-results.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
