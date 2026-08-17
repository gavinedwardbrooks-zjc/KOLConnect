from __future__ import annotations

"""Cross-process serialization for mutations of KOLConnect local stores."""

import contextlib
import errno
import os
import threading
import time
from pathlib import Path
from typing import Iterator


DEFAULT_SHARED_STORAGE_LOCK_TIMEOUT = 20.0
SHARED_STORAGE_LOCK_POLL_INTERVAL = 0.05
SHARED_STORAGE_LOCK_FILENAME = "shared_storage.lock"


class SharedStorageLockTimeout(TimeoutError):
    pass


LOCAL_STORAGE_MUTATION_LOCK = threading.RLock()
_THREAD_STATE = threading.local()


def get_shared_storage_lock_path() -> Path:
    """Resolve one persistent lock carrier shared by every app process."""
    from runtime_paths import get_app_data_dir

    return get_app_data_dir() / "locks" / SHARED_STORAGE_LOCK_FILENAME


def _is_lock_contention_error(exc: OSError, *, platform: str | None = None) -> bool:
    platform = platform or os.name
    if platform == "nt":
        return (
            exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}
            or getattr(exc, "winerror", None) in {32, 33}
        )
    return exc.errno in {errno.EACCES, errno.EAGAIN}


def _open_lock_carrier(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if os.fstat(fd).st_size < 1:
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, b"\0")
            os.fsync(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        return fd
    except Exception:
        os.close(fd)
        raise


def _try_lock_windows(fd: int) -> None:
    import msvcrt

    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)


def _unlock_windows(fd: int) -> None:
    import msvcrt

    os.lseek(fd, 0, os.SEEK_SET)
    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def _try_lock_posix(fd: int) -> None:
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_posix(fd: int) -> None:
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


def _acquire_os_lock(path: Path, timeout: float) -> int:
    fd = _open_lock_carrier(path)
    deadline = time.monotonic() + timeout
    lock_once = _try_lock_windows if os.name == "nt" else _try_lock_posix
    try:
        while True:
            try:
                lock_once(fd)
                return fd
            except OSError as exc:
                if not _is_lock_contention_error(exc):
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise SharedStorageLockTimeout(
                        "Timed out waiting for the shared storage mutation lock."
                    ) from exc
                time.sleep(min(SHARED_STORAGE_LOCK_POLL_INTERVAL, remaining))
    except Exception:
        os.close(fd)
        raise


def _release_os_lock(fd: int) -> None:
    unlock = _unlock_windows if os.name == "nt" else _unlock_posix
    try:
        unlock(fd)
    finally:
        os.close(fd)


@contextlib.contextmanager
def shared_storage_lock(
    *, timeout: float = DEFAULT_SHARED_STORAGE_LOCK_TIMEOUT
) -> Iterator[None]:
    """Acquire the process-local and OS-backed shared mutation lock reentrantly."""
    timeout = float(timeout)
    if timeout < 0:
        raise ValueError("Shared storage lock timeout must be non-negative.")
    deadline = time.monotonic() + timeout
    if not LOCAL_STORAGE_MUTATION_LOCK.acquire(timeout=timeout):
        raise SharedStorageLockTimeout(
            "Timed out waiting for the process-local storage mutation lock."
        )
    entered = False
    try:
        pid = os.getpid()
        if getattr(_THREAD_STATE, "pid", pid) != pid:
            _THREAD_STATE.depth = 0
            _THREAD_STATE.fd = None
        _THREAD_STATE.pid = pid
        depth = int(getattr(_THREAD_STATE, "depth", 0))
        if depth == 0:
            remaining = max(0.0, deadline - time.monotonic())
            _THREAD_STATE.fd = _acquire_os_lock(
                get_shared_storage_lock_path(), remaining
            )
        _THREAD_STATE.depth = depth + 1
        entered = True
        yield
    finally:
        try:
            if entered:
                depth = int(getattr(_THREAD_STATE, "depth", 1)) - 1
                _THREAD_STATE.depth = depth
                if depth == 0:
                    fd = _THREAD_STATE.fd
                    _THREAD_STATE.fd = None
                    if fd is not None:
                        _release_os_lock(fd)
        finally:
            LOCAL_STORAGE_MUTATION_LOCK.release()


def shared_storage_lock_held() -> bool:
    return (
        getattr(_THREAD_STATE, "pid", None) == os.getpid()
        and int(getattr(_THREAD_STATE, "depth", 0)) > 0
    )


def _reset_after_fork() -> None:
    global LOCAL_STORAGE_MUTATION_LOCK, _THREAD_STATE
    inherited_fd = getattr(_THREAD_STATE, "fd", None)
    if inherited_fd is not None:
        try:
            os.close(inherited_fd)
        except OSError:
            pass
    LOCAL_STORAGE_MUTATION_LOCK = threading.RLock()
    _THREAD_STATE = threading.local()


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_after_fork)
