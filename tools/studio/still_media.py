"""Shared, database-free verification boundary for still image producers."""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

from .security import SecurityError, workspace_path

MAX_BYTES = 24 * 1024 * 1024
MAX_PIXELS = 16_000_000


class StillLibraryError(ValueError):
    def __init__(self, message: str, *, conflict: bool = False):
        super().__init__(message)
        self.code = "still_library_conflict" if conflict else "invalid_still_library_request"
        self.status = 409 if conflict else 422


def still_path(workspace: Path, relative: str | Path, *, exists: bool = True) -> Path:
    candidate = workspace / relative
    current = candidate
    while current != workspace:
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise SecurityError("linked still image paths are not allowed")
        if current.parent == current:
            raise SecurityError("invalid still path")
        current = current.parent
    return workspace_path(workspace, candidate, must_exist=exists)


def read_still_png(workspace: Path, relative: str | Path, expected: str | None = None):
    from PIL import Image

    path = still_path(workspace, relative)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise StillLibraryError("PNGが存在しないか、24 MiBを超えています。")
    with path.open("rb") as handle:
        data = handle.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise StillLibraryError("有効なPNGではありません。")
    digest = hashlib.sha256(data).hexdigest()
    if expected and digest.lower() != expected.lower():
        raise StillLibraryError("画像が登録時から変更されています。再取り込みしてください。", conflict=True)
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            if width * height > MAX_PIXELS or max(width, height) > 12000 or getattr(image, "n_frames", 1) != 1:
                raise StillLibraryError("PNGは静止画・1600万画素・一辺12000px以下にしてください。")
            image.load()
    except StillLibraryError:
        raise
    except Exception as exc:
        raise StillLibraryError("PNGのデコードに失敗しました。") from exc
    return data, {"sha256": digest, "width": width, "height": height, "bytes": len(data)}
