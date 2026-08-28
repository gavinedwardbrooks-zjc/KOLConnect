from __future__ import annotations

"""Workspace-local runtime isolation for the Python test process."""

from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import uuid
from typing import Iterator


ROOT = Path(__file__).resolve().parents[2]
SANDBOX_ROOT = ROOT / ".test_runtime"
_ENV_KEYS = (
    "HOME",
    "APPDATA",
    "LOCALAPPDATA",
    "XDG_DATA_HOME",
    "TEMP",
    "TMP",
    "TMPDIR",
)
CLEANUP_WARNINGS: list[str] = []
_ACTIVE_RUNTIME_ROOTS: list[Path] = []
_FORBIDDEN_ROOT_ARTIFACT_PREFIXES = (
    ".d4_",
    ".m3_",
    ".m4_",
    ".m5_",
    ".m6_",
    ".m7_",
    ".pre_m8_",
)


def _resolve_production_app_data() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return (base / "KOLConnect").resolve()


# Capture this before a process sandbox changes APPDATA. Nested contexts must keep
# comparing against the user's original production location.
_PRODUCTION_APP_DATA = _resolve_production_app_data()


@dataclass(frozen=True)
class TestRuntime:
    root: Path
    home: Path
    appdata: Path
    local_appdata: Path
    temp: Path
    data_root: Path
    lock_root: Path
    backup_root: Path
    settings_path: Path
    workbook_path: Path


def production_app_data_path() -> Path:
    return _PRODUCTION_APP_DATA


def test_artifact_path(*parts: str) -> Path:
    """Return a workspace-local test path beneath the single sandbox root."""
    artifact_root = (
        _ACTIVE_RUNTIME_ROOTS[-1] / "artifacts"
        if _ACTIVE_RUNTIME_ROOTS
        else SANDBOX_ROOT / "standalone"
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    path = artifact_root.joinpath(*parts).resolve()
    if path != artifact_root.resolve() and artifact_root.resolve() not in path.parents:
        raise ValueError("Test artifact path must stay inside .test_runtime.")
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_artifact_directory(*parts: str) -> Path:
    """Return an existing directory under the single test sandbox root."""
    path = test_artifact_path(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def forbidden_root_test_artifacts() -> list[Path]:
    """List legacy root-level test artifacts without deleting user data."""
    if not ROOT.is_dir():
        return []
    return sorted(
        path
        for path in ROOT.iterdir()
        if path.is_dir() and path.name.startswith(_FORBIDDEN_ROOT_ARTIFACT_PREFIXES)
    )


def assert_not_production_runtime(path: Path) -> None:
    resolved = Path(path).resolve()
    production = production_app_data_path()
    if resolved == production or production in resolved.parents:
        raise AssertionError(f"TEST_RUNTIME_POINTS_TO_PRODUCTION_DATA: {resolved}")


def assert_not_production_workbook(path: Path) -> None:
    resolved = Path(path).resolve()
    production_workbook = production_app_data_path() / "Creator_Library.xlsx"
    if resolved == production_workbook:
        raise AssertionError(f"TEST_RUNTIME_POINTS_TO_PRODUCTION_WORKBOOK: {resolved}")


def _materialize_runtime(root: Path) -> TestRuntime:
    root = root.resolve()
    home = root / "home"
    appdata = root / "appdata"
    local_appdata = root / "localappdata"
    temp = root / "temp"
    if sys.platform == "darwin":
        data_root = home / "Library" / "Application Support" / "KOLConnect"
    else:
        data_root = appdata / "KOLConnect"
    lock_root = data_root / "locks"
    backup_root = data_root / "backups"
    settings_path = data_root / "settings.json"
    workbook_path = data_root / "Creator_Library.xlsx"
    assert_not_production_runtime(data_root)
    assert_not_production_workbook(workbook_path)
    for path in (home, appdata, local_appdata, temp, data_root, lock_root, backup_root):
        path.mkdir(parents=True, exist_ok=True)
    return TestRuntime(
        root=root,
        home=home,
        appdata=appdata,
        local_appdata=local_appdata,
        temp=temp,
        data_root=data_root,
        lock_root=lock_root,
        backup_root=backup_root,
        settings_path=settings_path,
        workbook_path=workbook_path,
    )


def _safe_mkdtemp(suffix=None, prefix=None, dir=None) -> str:
    """Create test directories without tempfile's restrictive Windows ACL mode."""
    suffix = "" if suffix is None else suffix
    prefix = "kolconnect_test_" if prefix is None else prefix
    parent = Path(tempfile.gettempdir() if dir is None else dir)
    parent.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = parent / f"{prefix}{secrets.token_hex(8)}{suffix}"
        try:
            candidate.mkdir()
            return str(candidate)
        except FileExistsError:
            continue
    raise FileExistsError("Unable to allocate a unique test temporary directory")


@contextmanager
def test_runtime_sandbox(
    prefix: str = "case", *, cleanup: bool = True
) -> Iterator[TestRuntime]:
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    root = (SANDBOX_ROOT / f"{prefix}_{uuid.uuid4().hex}").resolve()
    runtime = _materialize_runtime(root)
    previous_env = {key: os.environ.get(key) for key in _ENV_KEYS}
    previous_tempdir = tempfile.tempdir
    previous_mkdtemp = tempfile.mkdtemp
    _ACTIVE_RUNTIME_ROOTS.append(root)
    try:
        os.environ.update(
            {
                "HOME": str(runtime.home),
                "APPDATA": str(runtime.appdata),
                "LOCALAPPDATA": str(runtime.local_appdata),
                "XDG_DATA_HOME": str(runtime.appdata),
                "TEMP": str(runtime.temp),
                "TMP": str(runtime.temp),
                "TMPDIR": str(runtime.temp),
            }
        )
        tempfile.tempdir = str(runtime.temp)
        tempfile.mkdtemp = _safe_mkdtemp
        yield runtime
    finally:
        _ACTIVE_RUNTIME_ROOTS.pop()
        tempfile.mkdtemp = previous_mkdtemp
        tempfile.tempdir = previous_tempdir
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if cleanup and os.environ.get("KOLCONNECT_TEST_KEEP_RUNTIME") != "1":
            try:
                shutil.rmtree(root)
            except PermissionError as exc:
                # Product assertions have completed. The canonical runner reports
                # retained directories as environment cleanup warnings.
                CLEANUP_WARNINGS.append(f"{root}: {exc}")


@contextmanager
def isolated_runtime(prefix: str = "case"):
    """Backward-compatible context that yields the sandbox root path."""
    with test_runtime_sandbox(prefix) as runtime:
        yield runtime.root
