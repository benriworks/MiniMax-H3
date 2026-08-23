from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
from typing import BinaryIO


class StudioInstanceLockError(RuntimeError):
    """Raised when another Studio server already owns the workspace."""


class WorkspaceInstanceLock:
    """Process-lifetime, workspace-scoped single-instance lock."""

    def __init__(self, workspace: Path):
        resolved = workspace.resolve(strict=True)
        identity = hashlib.sha256(str(resolved).casefold().encode("utf-8")).hexdigest()[:32]
        self.name = f"MiniMaxH3Studio-{identity}"
        self._handle: int | None = None
        self._file: BinaryIO | None = None

        if os.name == "nt":
            self._acquire_windows()
        else:
            self._acquire_posix(resolved)

    def _acquire_windows(self) -> None:
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_mutex = kernel32.CreateMutexW
        create_mutex.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        create_mutex.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        handle = create_mutex(None, False, f"Local\\{self.name}")
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
            close_handle(handle)
            raise StudioInstanceLockError(
                "another Studio server is already using this workspace"
            )
        self._handle = int(handle)

    def _acquire_posix(self, workspace: Path) -> None:
        import fcntl

        lock_path = workspace / "outputs" / "studio" / "studio.instance.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+b")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise StudioInstanceLockError(
                "another Studio server is already using this workspace"
            ) from exc
        self._file = handle

    def close(self) -> None:
        if self._handle is not None:
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            close_handle(wintypes.HANDLE(self._handle))
            self._handle = None
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> "WorkspaceInstanceLock":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
