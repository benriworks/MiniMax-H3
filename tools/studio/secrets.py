from __future__ import annotations

import ctypes
import os
import platform
import tempfile
from ctypes import wintypes
from pathlib import Path

from .security import SecurityError, validate_identifier, workspace_path


PROVIDERS: dict[str, tuple[str, ...]] = {
    "minimax": ("MINIMAX_API_KEY",),
    "elevenlabs": ("ELEVENLABS_API_KEY",),
    "azure_speech": ("AZURE_SPEECH_KEY",),
    "openai": ("OPENAI_API_KEY",),
}


class SecretStorageUnavailable(RuntimeError):
    pass


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]


def dpapi_available() -> bool:
    return platform.system() == "Windows" and hasattr(ctypes, "windll")


def _blob(data: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(data)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(data), pointer), buffer


def _local_free(pointer: ctypes.POINTER(ctypes.c_ubyte)) -> None:
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    kernel32.LocalFree(ctypes.cast(pointer, ctypes.c_void_p))


def _protect(data: bytes) -> bytes:
    if not dpapi_available():
        raise SecretStorageUnavailable("Windows DPAPI is unavailable")
    input_blob, input_buffer = _blob(data)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    if not crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        "MiniMaxH3 Studio provider credential",
        None,
        None,
        None,
        0x1,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        _local_free(output_blob.pbData)
        del input_buffer


def _unprotect(data: bytes) -> bytes:
    if not dpapi_available():
        raise SecretStorageUnavailable("Windows DPAPI is unavailable")
    input_blob, input_buffer = _blob(data)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        wintypes.LPVOID,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    if not crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        0x1,
        ctypes.byref(output_blob),
    ):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        _local_free(output_blob.pbData)
        del input_buffer


class SecretStore:
    """Stores provider credentials with Windows user-scoped DPAPI.

    There is deliberately no plaintext file fallback. Environment variables and
    a workspace ``.env`` file are detected for compatibility, but their values
    are never returned by status APIs or copied into SQLite.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve(strict=True)
        self.directory = workspace_path(self.workspace, "outputs/studio/secrets")

    def _provider(self, provider: str) -> str:
        validate_identifier(provider, label="provider")
        if provider not in PROVIDERS:
            raise ValueError("unknown provider")
        return provider

    def _path(self, provider: str) -> Path:
        provider = self._provider(provider)
        return workspace_path(self.workspace, self.directory / f"{provider}.dpapi")

    def set(self, provider: str, value: str) -> None:
        provider = self._provider(provider)
        clean = value.strip()
        if not clean or "\x00" in clean or "\n" in clean or "\r" in clean:
            raise ValueError("credential must be a non-empty single line")
        encrypted = _protect(clean.encode("utf-8"))
        self.directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.directory, delete=False) as temporary:
            temporary.write(encrypted)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, self._path(provider))

    def get(self, provider: str) -> str | None:
        path = self._path(provider)
        if not path.is_file():
            return None
        decrypted = _unprotect(path.read_bytes())
        try:
            value = decrypted.decode("utf-8")
            return value if value else None
        finally:
            decrypted = b""

    def delete(self, provider: str) -> bool:
        path = self._path(provider)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _dotenv_has_value(self, variable_names: tuple[str, ...]) -> bool:
        try:
            dotenv = workspace_path(self.workspace, ".env")
        except SecurityError:
            return False
        if not dotenv.is_file() or dotenv.stat().st_size > 1024 * 1024:
            return False
        wanted = set(variable_names)
        try:
            with dotenv.open("r", encoding="utf-8-sig", errors="replace") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    name, raw_value = stripped.split("=", 1)
                    if name.strip() in wanted and raw_value.strip().strip("\"'"):
                        return True
        except OSError:
            return False
        return False

    def configured(self, provider: str) -> bool:
        provider = self._provider(provider)
        variables = PROVIDERS[provider]
        if any(os.environ.get(name, "").strip() for name in variables):
            return True
        if self._dotenv_has_value(variables):
            return True
        try:
            return bool(self.get(provider))
        except (OSError, ValueError, UnicodeError, SecretStorageUnavailable):
            return False

    def statuses(self) -> list[dict[str, object]]:
        return [
            {"id": provider, "configured": self.configured(provider)}
            for provider in PROVIDERS
        ]
