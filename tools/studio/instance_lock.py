from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
from typing import BinaryIO

from .security import workspace_path


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

        lock_directory = workspace_path(resolved, "outputs/studio")
        lock_directory.mkdir(parents=True, exist_ok=True)
        # Resolve again after creation.  A pre-existing link that redirects
        # the lock outside the workspace must fail closed before a handle is
        # opened, otherwise two processes could lock different files.
        lock_directory = workspace_path(resolved, lock_directory, must_exist=True)
        self.path = workspace_path(
            resolved, lock_directory / "studio.instance.lock"
        )

        if os.name == "nt":
            self._acquire_windows(self.path)
        else:
            self._acquire_posix(self.path)

    def _acquire_windows(self, lock_path: Path) -> None:
        from ctypes import wintypes

        class Overlapped(ctypes.Structure):
            _fields_ = [
                ("Internal", ctypes.c_size_t),
                ("InternalHigh", ctypes.c_size_t),
                ("Offset", wintypes.DWORD),
                ("OffsetHigh", wintypes.DWORD),
                ("hEvent", wintypes.HANDLE),
            ]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create_file.restype = wintypes.HANDLE
        lock_file = kernel32.LockFileEx
        lock_file.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(Overlapped),
        ]
        lock_file.restype = wintypes.BOOL
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = [wintypes.HANDLE]
        close_handle.restype = wintypes.BOOL

        generic_read = 0x80000000
        generic_write = 0x40000000
        file_share_read = 0x00000001
        file_share_write = 0x00000002
        open_always = 4
        file_attribute_normal = 0x00000080
        invalid_handle_value = wintypes.HANDLE(-1).value
        lockfile_fail_immediately = 0x00000001
        lockfile_exclusive_lock = 0x00000002
        error_lock_violation = 33

        # The lock lives in the workspace rather than the Windows Local\
        # object namespace.  Byte-range locks are enforced by the filesystem
        # across login/RDP/service sessions.  FILE_SHARE_DELETE is omitted so
        # the path cannot be replaced while this process owns the lock.
        handle = create_file(
            str(lock_path),
            generic_read | generic_write,
            file_share_read | file_share_write,
            None,
            open_always,
            file_attribute_normal,
            None,
        )
        if handle == invalid_handle_value:
            raise ctypes.WinError(ctypes.get_last_error())
        overlapped = Overlapped()
        if not lock_file(
            handle,
            lockfile_fail_immediately | lockfile_exclusive_lock,
            0,
            1,
            0,
            ctypes.byref(overlapped),
        ):
            error = ctypes.get_last_error()
            close_handle(handle)
            if error == error_lock_violation:
                raise StudioInstanceLockError(
                    "another Studio server is already using this workspace"
                )
            raise ctypes.WinError(error)
        self._handle = int(handle)

    def _acquire_posix(self, lock_path: Path) -> None:
        import fcntl

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

            class Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_size_t),
                    ("InternalHigh", ctypes.c_size_t),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            unlock_file = kernel32.UnlockFileEx
            unlock_file.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(Overlapped),
            ]
            unlock_file.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = [wintypes.HANDLE]
            close_handle.restype = wintypes.BOOL
            handle = wintypes.HANDLE(self._handle)
            # Closing the handle also releases the byte-range lock.  Attempt
            # the explicit unlock first for deterministic same-process
            # reacquisition, then close regardless of the unlock result.
            overlapped = Overlapped()
            unlock_file(handle, 0, 1, 0, ctypes.byref(overlapped))
            close_handle(handle)
            self._handle = None
        if self._file is not None:
            self._file.close()
            self._file = None

    def __enter__(self) -> "WorkspaceInstanceLock":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
