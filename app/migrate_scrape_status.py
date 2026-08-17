from __future__ import annotations

"""One-time, non-destructive migration for task scrape-status normalization."""

import argparse
import csv
import hashlib
import json
import os
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import scraper
from local_storage_lock import shared_storage_lock


STATUS_FIELDS = {scraper.FIELD_SCRAPE_STATUS, scraper.FIELD_STATUS_REASON}


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="", errors="strict") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"CSV has no header: {path}")
        return list(reader.fieldnames), [dict(row) for row in reader]


def _business_digest(fieldnames: list[str], rows: list[dict[str, str]]) -> str:
    protected_fields = [field for field in fieldnames if field not in STATUS_FIELDS]
    payload = [[str(row.get(field) or "") for field in protected_fields] for row in rows]
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _migrated_fieldnames(fieldnames: list[str]) -> list[str]:
    if scraper.FIELD_STATUS_REASON in fieldnames:
        return list(fieldnames)
    updated = list(fieldnames)
    try:
        index = updated.index(scraper.FIELD_SCRAPE_STATUS) + 1
    except ValueError:
        index = len(updated)
    updated.insert(index, scraper.FIELD_STATUS_REASON)
    return updated


def reclassify_rows(
    fieldnames: list[str], rows: list[dict[str, str]]
) -> tuple[list[str], list[dict[str, str]], dict]:
    updated_fieldnames = _migrated_fieldnames(fieldnames)
    before_counts = Counter(str(row.get(scraper.FIELD_SCRAPE_STATUS) or "") for row in rows)
    updated_rows: list[dict[str, str]] = []
    changed = 0

    for row in rows:
        migrated = dict(row)
        result = scraper.row_to_result(row)
        status = str(result.get("scrape_status") or "failed")
        reason = str(result.get("status_reason") or "")
        if status != str(row.get(scraper.FIELD_SCRAPE_STATUS) or "") or reason != str(
            row.get(scraper.FIELD_STATUS_REASON) or ""
        ):
            changed += 1
        migrated[scraper.FIELD_SCRAPE_STATUS] = status
        migrated[scraper.FIELD_STATUS_REASON] = reason
        updated_rows.append(migrated)

    before_digest = _business_digest(fieldnames, rows)
    after_digest = _business_digest(updated_fieldnames, updated_rows)
    if before_digest != after_digest:
        raise RuntimeError("Protected task fields changed during status migration.")

    return updated_fieldnames, updated_rows, {
        "rows": len(rows),
        "changed_rows": changed,
        "before": dict(sorted(before_counts.items())),
        "after": dict(sorted(Counter(row[scraper.FIELD_SCRAPE_STATUS] for row in updated_rows).items())),
        "protected_fields_sha256": after_digest,
    }


def _write_csv_atomic(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with shared_storage_lock():
        temp_path = path.with_suffix(f"{path.suffix}.phase4_1.tmp")
        try:
            with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            temp_path.unlink(missing_ok=True)


def migrate_task(task_dir: Path, *, apply: bool = False) -> dict:
    task_dir = task_dir.resolve()
    files = [path for path in (task_dir / "results.csv", task_dir / "progress.csv") if path.is_file()]
    if not files:
        raise ValueError(f"No task result CSV found: {task_dir}")

    timestamp = _utc_stamp()
    backup_dir = task_dir / f"phase4_1_backup_{timestamp}"
    report = {"task_dir": str(task_dir), "applied": apply, "backup_dir": "", "files": {}}
    staged: list[tuple[Path, list[str], list[dict[str, str]]]] = []

    for path in files:
        fieldnames, rows = _read_csv(path)
        updated_fieldnames, updated_rows, summary = reclassify_rows(fieldnames, rows)
        report["files"][path.name] = summary
        staged.append((path, updated_fieldnames, updated_rows))

    if apply:
        with shared_storage_lock():
            backup_dir.mkdir(parents=False, exist_ok=False)
            for path, _fieldnames, _rows in staged:
                shutil.copy2(path, backup_dir / path.name)
            report["backup_dir"] = str(backup_dir)
            try:
                for path, fieldnames, rows in staged:
                    _write_csv_atomic(path, fieldnames, rows)
            except Exception:
                for path, _fieldnames, _rows in staged:
                    backup_path = backup_dir / path.name
                    if backup_path.is_file():
                        shutil.copy2(backup_path, path)
                raise

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize KOLConnect task scrape statuses.")
    parser.add_argument("task_dirs", nargs="+", type=Path, help="One or more task directories.")
    parser.add_argument("--apply", action="store_true", help="Write changes after creating backups.")
    args = parser.parse_args()

    reports = [migrate_task(task_dir, apply=args.apply) for task_dir in args.task_dirs]
    print(json.dumps({"tasks": reports}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
