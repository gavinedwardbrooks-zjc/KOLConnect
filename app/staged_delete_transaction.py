from __future__ import annotations

"""Recoverable local-file primitives for a future Creator hard delete."""

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from excel_workbook_store import ExcelWorkbookStore
from runtime_paths import atomic_write_json
from local_storage_lock import (
    LOCAL_STORAGE_MUTATION_LOCK,
    SharedStorageLockTimeout,
    shared_storage_lock,
)


PHASES = frozenset({
    "PREPARED", "STAGING", "STAGED", "MUTATING", "COMMITTED",
    "CLEANUP_PENDING", "CLEANED", "ROLLED_BACK",
})
PRECOMMIT_PHASES = frozenset({"PREPARED", "STAGING", "STAGED", "MUTATING"})
ALLOWED_TRANSITIONS = {
    "PREPARED": frozenset({"STAGING", "STAGED", "ROLLED_BACK"}),
    "STAGING": frozenset({"STAGING", "STAGED", "ROLLED_BACK"}),
    "STAGED": frozenset({"MUTATING", "COMMITTED", "ROLLED_BACK"}),
    "MUTATING": frozenset({"COMMITTED", "ROLLED_BACK"}),
    "COMMITTED": frozenset({"CLEANUP_PENDING", "CLEANED"}),
    "CLEANUP_PENDING": frozenset({"CLEANUP_PENDING", "CLEANED"}),
    "CLEANED": frozenset(),
    "ROLLED_BACK": frozenset(),
}
LOCAL_DELETE_LOCK = LOCAL_STORAGE_MUTATION_LOCK
TRANSACTION_ID_PATTERN = re.compile(r"^delete_[A-Za-z0-9_-]+$")


class StagedDeleteTransaction:
    """Stage local paths and exact backups; never decides what business data to delete."""

    def __init__(
        self,
        runtime_data_dir: Path,
        creator_id: str,
        *,
        transaction_id: str | None = None,
    ) -> None:
        self.runtime_data_dir = Path(runtime_data_dir)
        self.transaction_id = transaction_id or f"delete_{uuid.uuid4().hex}"
        if not TRANSACTION_ID_PATTERN.fullmatch(self.transaction_id):
            raise ValueError("Delete transaction ID is invalid.")
        self.root = self.runtime_data_dir / "delete_transactions" / self.transaction_id
        self.manifest_path = self.root / "manifest.json"
        self.creator_id = str(creator_id or "").strip()

    def prepare(self) -> dict[str, Any]:
        with shared_storage_lock():
            if not self.creator_id:
                raise ValueError("Creator ID is required.")
            self.root.mkdir(parents=True, exist_ok=False)
            manifest = {
                "transaction_id": self.transaction_id,
                "phase": "PREPARED",
                "created_at": self._now(),
                "creator_id": self.creator_id,
                "workbook_backup": "",
                "json_backups": [],
                "quarantine_moves": [],
                "commit_marker": False,
            }
            self._write_manifest(manifest)
            return manifest

    def transition(self, phase: str) -> dict[str, Any]:
        if phase not in PHASES:
            raise ValueError("Invalid transaction phase.")
        with shared_storage_lock():
            manifest = self.load_manifest()
            if phase not in ALLOWED_TRANSITIONS[manifest["phase"]]:
                raise ValueError("Invalid transaction phase transition.")
            manifest["phase"] = phase
            if phase in {"COMMITTED", "CLEANUP_PENDING", "CLEANED"}:
                manifest["commit_marker"] = True
            self._write_manifest(manifest)
            return manifest

    def backup_workbook(self, store: ExcelWorkbookStore) -> Path:
        with shared_storage_lock():
            manifest = self.load_manifest()
            if manifest["phase"] not in {"PREPARED", "STAGING"}:
                raise RuntimeError("Workbook backup is not allowed in this phase.")
            if manifest.get("workbook_backup"):
                raise RuntimeError("Workbook backup already exists for this transaction.")
            backup = self.root / "backups" / "workbook.xlsx"
            store.create_transaction_backup(backup)
            manifest["workbook_backup"] = str(backup)
            manifest["workbook_target"] = str(store.workbook_path)
            self._write_manifest(manifest)
            return backup

    def backup_json(self, path: Path, *, label: str) -> Path:
        path = Path(path)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", label):
            raise ValueError("JSON backup label is invalid.")
        with shared_storage_lock():
            data = self._load_json(path)
            backup = self.root / "backups" / f"{label}.json"
            manifest = self.load_manifest()
            if manifest["phase"] not in {"PREPARED", "STAGING"}:
                raise RuntimeError("JSON backup is not allowed in this phase.")
            if backup.exists() or any(
                item.get("original") == str(path)
                for item in manifest["json_backups"]
            ):
                raise RuntimeError("JSON backup already exists for this transaction.")
            atomic_write_json(backup, data)
            manifest["json_backups"].append({
                "original": str(path),
                "backup": str(backup),
            })
            self._write_manifest(manifest)
            return backup

    def write_json(self, path: Path, data: Any) -> None:
        with shared_storage_lock():
            if self.load_manifest()["phase"] != "MUTATING":
                raise RuntimeError("JSON mutation is not allowed in this phase.")
            atomic_write_json(Path(path), data)

    def stage_path(self, path: Path) -> Path:
        path = Path(path)
        with shared_storage_lock():
            manifest = self.load_manifest()
            if manifest["phase"] not in {"PREPARED", "STAGING"}:
                raise RuntimeError("Artifact staging is not allowed in this phase.")
            if path.is_symlink() or not path.exists():
                raise ValueError("Artifact path is missing or unsafe.")
            quarantine = path.parent / ".kolconnect_delete_quarantine" / self.transaction_id / path.name
            quarantine.parent.mkdir(parents=True, exist_ok=True)
            if not self._same_volume(path, quarantine.parent):
                raise ValueError("Quarantine must be on the same volume.")
            if quarantine.exists():
                raise ValueError("Quarantine target already exists.")
            move = {
                "original": str(path),
                "quarantine": str(quarantine),
                "state": "planned",
            }
            manifest["phase"] = "STAGING"
            manifest["quarantine_moves"].append(move)
            self._write_manifest(manifest)
            os.replace(path, quarantine)
            move["state"] = "staged"
            self._write_manifest(manifest)
            return quarantine

    def rollback(self) -> dict[str, Any]:
        with shared_storage_lock():
            manifest = self.load_manifest()
            if manifest.get("commit_marker"):
                raise RuntimeError("Committed transaction cannot be rolled back.")
            for item in reversed(manifest.get("json_backups", [])):
                original = Path(item["original"])
                data = self._load_json(Path(item["backup"]))
                atomic_write_json(original, data)
            for item in reversed(manifest.get("quarantine_moves", [])):
                original = Path(item["original"])
                quarantine = Path(item["quarantine"])
                if not quarantine.exists():
                    continue
                if original.exists():
                    raise RuntimeError("Rollback destination is occupied.")
                original.parent.mkdir(parents=True, exist_ok=True)
                os.replace(quarantine, original)
            workbook_backup = str(manifest.get("workbook_backup") or "")
            workbook_target = str(manifest.get("workbook_target") or "")
            if workbook_backup and workbook_target:
                ExcelWorkbookStore(Path(workbook_target)).restore_transaction_backup(
                    Path(workbook_backup)
                )
            manifest["phase"] = "ROLLED_BACK"
            self._write_manifest(manifest)
            return manifest

    def finalize_cleanup(self) -> dict[str, Any]:
        with shared_storage_lock():
            manifest = self.load_manifest()
            if not manifest.get("commit_marker"):
                raise RuntimeError("Cleanup requires a committed transaction.")
            try:
                for item in manifest.get("quarantine_moves", []):
                    self._remove_path(Path(item["quarantine"]))
            except Exception:
                manifest["phase"] = "CLEANUP_PENDING"
                self._write_manifest(manifest)
                return manifest
            manifest["phase"] = "CLEANED"
            self._write_manifest(manifest)
            return manifest

    def recover(self) -> dict[str, Any]:
        with shared_storage_lock():
            manifest = self.load_manifest()
            phase = manifest["phase"]
            if phase in PRECOMMIT_PHASES:
                return self.rollback()
            if phase in {"COMMITTED", "CLEANUP_PENDING"}:
                return self.finalize_cleanup()
            return manifest

    def preflight(
        self,
        plan: dict[str, Any],
        *,
        workbook_path: Path,
        artifact_paths: Iterable[Path] = (),
        json_paths: Iterable[Path] = (),
    ) -> dict[str, Any]:
        reasons: list[str] = []
        try:
            with shared_storage_lock(timeout=0):
                pass
        except SharedStorageLockTimeout:
            reasons.append("LOCAL_MUTATION_LOCK_UNAVAILABLE")
        if plan.get("blocked"):
            reasons.append("DELETE_PLAN_BLOCKED")
        if any(not str(item.get("stable_id") or "") for item in plan.get("delete_locators", [])):
            reasons.append("INEXACT_DELETE_LOCATOR")
        workbook_path = Path(workbook_path)
        if not workbook_path.is_file() or not os.access(workbook_path.parent, os.W_OK):
            reasons.append("WORKBOOK_BACKUP_UNAVAILABLE")
        transaction_parent = self.runtime_data_dir / "delete_transactions"
        transaction_parent.mkdir(parents=True, exist_ok=True)
        if not os.access(transaction_parent, os.W_OK):
            reasons.append("MANIFEST_DESTINATION_UNWRITABLE")
        for path in artifact_paths:
            path = Path(path)
            if path.is_symlink() or not path.exists() or not os.access(path.parent, os.W_OK):
                reasons.append("ARTIFACT_STAGING_UNAVAILABLE")
        for path in json_paths:
            path = Path(path)
            if not path.is_file() or not os.access(path.parent, os.W_OK):
                reasons.append("JSON_BACKUP_UNAVAILABLE")
        return {"status": "READY" if not reasons else "BLOCKED", "reasons": sorted(set(reasons))}

    def load_manifest(self) -> dict[str, Any]:
        manifest = self._load_json(self.manifest_path)
        if (
            not isinstance(manifest, dict)
            or manifest.get("transaction_id") != self.transaction_id
            or manifest.get("phase") not in PHASES
            or not isinstance(manifest.get("json_backups"), list)
            or not isinstance(manifest.get("quarantine_moves"), list)
        ):
            raise RuntimeError("Delete transaction manifest is invalid.")
        return manifest

    def _write_manifest(self, manifest: dict[str, Any]) -> None:
        atomic_write_json(self.manifest_path, manifest)

    @staticmethod
    def _load_json(path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("Transaction JSON cannot be read safely.") from exc

    @staticmethod
    def _remove_path(path: Path) -> None:
        if not path.exists():
            return
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()

    @staticmethod
    def _same_volume(source: Path, destination_parent: Path) -> bool:
        return os.stat(source).st_dev == os.stat(destination_parent).st_dev

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def recover_pending_delete_transactions(runtime_data_dir: Path) -> list[dict[str, Any]]:
    """Recover durable local transactions without coupling recovery to server startup."""
    with shared_storage_lock():
        transactions_root = Path(runtime_data_dir) / "delete_transactions"
        if not transactions_root.is_dir():
            return []
        recovered: list[dict[str, Any]] = []
        for root in sorted(transactions_root.iterdir(), key=lambda item: item.name):
            manifest_path = root / "manifest.json"
            if not root.is_dir() or not manifest_path.is_file():
                continue
            try:
                manifest = StagedDeleteTransaction._load_json(manifest_path)
                transaction = StagedDeleteTransaction(
                    runtime_data_dir,
                    str(manifest.get("creator_id") or ""),
                    transaction_id=root.name,
                )
                recovered.append(transaction.recover())
            except (RuntimeError, ValueError, OSError):
                recovered.append({
                    "transaction_id": root.name,
                    "phase": "RECOVERY_BLOCKED",
                })
        return recovered
