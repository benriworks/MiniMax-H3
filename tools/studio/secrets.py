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
    # A single-line JSON object containing client_id, client_secret and
    # refresh_token.  It is resolved only inside the YouTube adapter; status
    # APIs expose the configured flag and never the JSON or its fields.
    "youtube": ("YOUTUBE_OAUTH_CREDENTIAL_JSON",),
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


def protect_private_data(
    data: bytes,
    *,
    description: str = "MiniMaxH3 Studio private local data",
) -> bytes:
    """Protect one bounded private payload for the current Windows user.

    The returned bytes are DPAPI ciphertext.  Callers may persist the
    ciphertext, but must never place the plaintext in jobs, events, logs, or
    public API responses.
    """

    if not dpapi_available():
        raise SecretStorageUnavailable("Windows DPAPI is unavailable")
    if not isinstance(data, bytes) or not data or len(data) > 512 * 1024:
        raise ValueError("private data must contain 1 to 524288 bytes")
    if (
        not isinstance(description, str)
        or not description
        or len(description) > 128
        or "\x00" in description
    ):
        raise ValueError("private data description is invalid")
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
        description,
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


def unprotect_private_data(data: bytes) -> bytes:
    """Decrypt one bounded current-user DPAPI payload in process memory."""

    if not dpapi_available():
        raise SecretStorageUnavailable("Windows DPAPI is unavailable")
    if not isinstance(data, bytes) or not data or len(data) > 1024 * 1024:
        raise ValueError("protected private data is invalid")
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

    There is deliberately no plaintext file written by Studio. Environment
    variables and a workspace ``.env`` file are accepted as compatibility
    inputs, but their values are only resolved inside a provider worker and are
    never returned by status APIs or copied into SQLite.
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
        encrypted = protect_private_data(
            clean.encode("utf-8"),
            description="MiniMaxH3 Studio provider credential",
        )
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
        decrypted = unprotect_private_data(path.read_bytes())
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

    def _dotenv_value(self, variable_names: tuple[str, ...]) -> str | None:
        try:
            dotenv = workspace_path(self.workspace, ".env")
        except SecurityError:
            return None
        if not dotenv.is_file() or dotenv.stat().st_size > 1024 * 1024:
            return None
        wanted = set(variable_names)
        try:
            with dotenv.open("r", encoding="utf-8-sig", errors="replace") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or "=" not in stripped:
                        continue
                    name, raw_value = stripped.split("=", 1)
                    if name.strip() not in wanted:
                        continue
                    value = raw_value.strip()
                    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                        value = value[1:-1]
                    if value and "\x00" not in value and "\r" not in value and "\n" not in value:
                        return value
        except OSError:
            return None
        return None

    def resolve(self, provider: str) -> str | None:
        """Resolve a credential for an in-process provider adapter only.

        The lookup order is process environment, workspace ``.env``, then the
        user-scoped DPAPI store. Callers must not persist or include the return
        value in exceptions, job payloads, events, or audit artifacts.
        """

        provider = self._provider(provider)
        for variable in PROVIDERS[provider]:
            value = os.environ.get(variable, "").strip()
            if value and "\x00" not in value and "\r" not in value and "\n" not in value:
                return value
        dotenv_value = self._dotenv_value(PROVIDERS[provider])
        if dotenv_value is not None:
            return dotenv_value
        try:
            return self.get(provider)
        except (OSError, ValueError, UnicodeError, SecretStorageUnavailable):
            return None

    def configured(self, provider: str) -> bool:
        provider = self._provider(provider)
        return bool(self.resolve(provider))

    def statuses(self) -> list[dict[str, object]]:
        return [
            {"id": provider, "configured": self.configured(provider)}
            for provider in PROVIDERS
        ]
