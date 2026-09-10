from __future__ import annotations

"""Explicit, local-only Claude window capture using the installed FFmpeg WGC engine.

Window handles, executable paths and selection capabilities live only in this
controller's memory. Inspection never captures pixels. A claim is single use;
the HTTP caller must reconcile its durable Job rather than retry an uncertain
submission. This module does not control Claude or start its process.
"""

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import struct
import threading
import time
from typing import Any

from . import assembly
from . import windows_capture_worker as native
from .security import canonical_json, workspace_path
from .windows_capture import WindowsCaptureError


PROVIDER = "local_claude_window_capture"
IMPLEMENTATION_VERSION = "claude-window-wgc-silent-v1"
MIN_DURATION_MS = 15_000
MAX_DURATION_MS = 30_000
SELECTION_TTL_SECONDS = 60
WIDTH, HEIGHT, FPS = 1920, 1080, 24
_CLAUDE_PACKAGE_FAMILY = "Claude_pzs8sxrjxfjjc"
_CLAUDE_APPLICATION_ID = _CLAUDE_PACKAGE_FAMILY + "!Claude"
_CLAUDE_WINDOW_CLASS = "Chrome_WidgetWin_1"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")
_DIGEST = re.compile(r"^[0-9A-Fa-f]{64}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_MAX_BYTES = 300 * 1024 * 1024
_FILES = {
    "claude-capture.mp4": ("video", "video/mp4"),
    "first-frame.png": ("image", "image/png"),
    "last-frame.png": ("image", "image/png"),
    "capture-report.json": ("document", "application/json"),
    "ffprobe.json": ("document", "application/json"),
    "manifest.json": ("document", "application/json"),
}


class ClaudeCaptureError(WindowsCaptureError):
    error_code = "claude_capture_failed"


def _fail(code: str, message: str) -> None:
    raise ClaudeCaptureError(message, code=code)


def selection_token_digest(token: str) -> str:
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        _fail("invalid_claude_capture_request", "The window selection is invalid.")
    return hashlib.sha256(b"claude-window-selection-v1\0" + token.encode("ascii")).hexdigest().upper()


def validate_capture_request(body: Any) -> dict[str, Any]:
    if not isinstance(body, dict) or set(body) != {"selection_token", "duration_ms", "confirm_capture"}:
        _fail("invalid_claude_capture_request", "Only the selected window, duration and explicit confirmation are accepted.")
    selection_token_digest(body.get("selection_token"))
    duration = body.get("duration_ms")
    if isinstance(duration, bool) or not isinstance(duration, int) or not MIN_DURATION_MS <= duration <= MAX_DURATION_MS:
        _fail("invalid_claude_capture_request", "Capture duration must be 15000 to 30000 milliseconds.")
    if body.get("confirm_capture") is not True:
        _fail("claude_capture_confirmation_required", "Confirm this silent window capture before starting.")
    return dict(body)


def _session(value: str) -> str:
    if not isinstance(value, str) or not _DIGEST.fullmatch(value):
        _fail("claude_capture_selection_invalid", "An authenticated Studio session is required.")
    return value.upper()


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _capture_root(capture_root: Path, workspace: Path) -> Path:
    supplied = Path(capture_root)
    lexical = supplied if supplied.is_absolute() else workspace / supplied
    if native._has_symlink_component(workspace, lexical):
        _fail("invalid_claude_capture_output", "Capture directories must not contain links or junctions.")
    target = workspace_path(workspace, lexical)
    parts = target.relative_to(workspace).parts
    if len(parts) != 5 or parts[:3] != ("outputs", "studio", "claude-captures") or not all(_ID.fullmatch(part) for part in parts[3:]):
        _fail("invalid_claude_capture_output", "Capture requires an exact production/request output directory.")
    return target


def cleanup_capture_root(capture_root: Path, *, workspace: str | Path) -> None:
    """Remove only this request's known outputs/partials; unknown contents block.

    Used by the service after transaction failure or interrupted-Job recovery.
    Never pass a workspace, captures root or production directory here.
    """
    root = Path(workspace).resolve(strict=True)
    target = _capture_root(capture_root, root)
    candidates = [target] if target.exists() else []
    pattern = re.compile(r"^\." + re.escape(target.name) + r"\.[0-9a-f]{32}\.partial$")
    if target.parent.exists():
        candidates += [path for path in target.parent.iterdir() if pattern.fullmatch(path.name)]
    allowed = set(_FILES) | {f".{name}.partial" for name in _FILES if name.endswith(".json")}
    # Validate the entire set before deleting any file. No recursive deletion.
    for directory in candidates:
        if native._has_symlink_component(root, directory) or not directory.is_dir():
            _fail("claude_capture_cleanup_failed", "Capture cleanup encountered a changed directory.")
        if any(path.name not in allowed or not path.is_file() or native._has_symlink_component(root, path) for path in directory.iterdir()):
            _fail("claude_capture_cleanup_failed", "Capture cleanup found unknown files; nothing was removed.")
    for directory in candidates:
        for path in directory.iterdir():
            path.unlink()
        directory.rmdir()


def _runtime_directory(workspace: Path) -> Path:
    """Keep graphics-driver cwd caches outside the exact six-file media bundle.

    Some drivers create a relative NVIDIA Corporation/umdlogs directory when
    the deliberately minimal subprocess environment omits LOCALAPPDATA. The
    dedicated local cache is retained, never published as an artifact and never
    included in media cleanup. Every media input/output remains an absolute path.
    """
    lexical = workspace / "outputs" / "studio" / "runtime" / "claude-window-capture"
    if native._has_symlink_component(workspace, lexical):
        _fail("invalid_claude_capture_output", "Capture runtime directories must not contain links or junctions.")
    directory = workspace_path(workspace, lexical)
    directory.mkdir(parents=True, exist_ok=True)
    if not directory.is_dir() or native._has_symlink_component(workspace, directory):
        _fail("invalid_claude_capture_output", "The capture runtime directory changed.")
    return directory


@dataclass(frozen=True, repr=False)
class _Window:
    hwnd: int
    pid: int
    process_started: int
    process_path: str
    window_class: str
    width: int
    height: int
    package_family: str = ""
    package_full_name: str = ""
    application_id: str = ""
    package_root: str = ""

    def digest(self) -> str:
        return hashlib.sha256(canonical_json(self.__dict__).encode("utf-8")).hexdigest().upper()


def _official_package_binding(process_path: str, family: str, full_name: str, application_id: str, package_root: str) -> bool:
    """Only the observed official MSIX family; unpackaged installs are unsupported."""
    if family != _CLAUDE_PACKAGE_FAMILY or application_id != _CLAUDE_APPLICATION_ID:
        return False
    if not re.fullmatch(r"Claude_\d+(?:\.\d+){3}_(?:x64|arm64|x86|neutral)__pzs8sxrjxfjjc", full_name):
        return False
    executable, root = PureWindowsPath(process_path), PureWindowsPath(package_root)
    if not executable.is_absolute() or not root.is_absolute() or executable.name.casefold() != "claude.exe" or ".." in executable.parts or ".." in root.parts:
        return False
    try:
        return bool(executable.relative_to(root).parts)
    except ValueError:
        return False


@dataclass(frozen=True, repr=False)
class ClaudeCaptureClaim:
    capture_id: str
    selection_digest: str
    duration_ms: int
    _window: _Window
    _expires: float


@dataclass(frozen=True, repr=False)
class ClaudeStillClaim:
    capture_id: str
    selection_digest: str
    _window: _Window
    _expires: float


class _Win32:
    """No window title, UI text, pixels, audio or accessibility content is read."""

    executable_name = "claude.exe"
    window_class = _CLAUDE_WINDOW_CLASS
    package_binding = staticmethod(_official_package_binding)

    def __init__(self) -> None:
        if os.name != "nt":
            _fail("claude_capture_unavailable", "Windows is required.")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        u, k = self.user, self.kernel
        for name in ("IsWindow", "IsWindowVisible", "IsIconic"):
            getattr(u, name).argtypes = [wintypes.HWND]
            getattr(u, name).restype = wintypes.BOOL
        u.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
        u.GetAncestor.restype = wintypes.HWND
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.GetWindowThreadProcessId.restype = wintypes.DWORD
        u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetClientRect.restype = wintypes.BOOL
        u.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetClassNameW.restype = ctypes.c_int
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.OpenProcess.restype = wintypes.HANDLE
        k.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        k.QueryFullProcessImageNameW.restype = wintypes.BOOL
        k.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k.GetProcessTimes.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.CloseHandle.restype = wintypes.BOOL
        for name in ("GetPackageFamilyName", "GetPackageFullName", "GetApplicationUserModelId"):
            call = getattr(k, name)
            call.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
            call.restype = wintypes.LONG
        k.GetPackagePathByFullName.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
        k.GetPackagePathByFullName.restype = wintypes.LONG
        self.dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.dwm.DwmGetWindowAttribute.restype = ctypes.c_long

    @staticmethod
    def _package_text(call: Any, argument: Any) -> str:
        size = wintypes.UINT()
        if call(argument, ctypes.byref(size), None) != 122 or not 1 <= size.value <= 32768:
            return ""
        buffer = ctypes.create_unicode_buffer(size.value)
        if call(argument, ctypes.byref(size), buffer) != 0:
            return ""
        return buffer.value

    def snapshot(self, hwnd: int) -> _Window | None:
        if not hwnd or not self.user.IsWindow(hwnd) or not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):
            return None
        if int(self.user.GetAncestor(hwnd, 2) or 0) != hwnd:
            return None
        cloaked = wintypes.DWORD()
        if self.dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0 or cloaked.value:
            return None
        pid = wintypes.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            return None
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            path = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(path))
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
                return None
            process_path = os.path.normcase(os.path.abspath(path.value))
            if Path(process_path).name.casefold() != self.executable_name:
                return None
            family = self._package_text(self.kernel.GetPackageFamilyName, handle)
            full_name = self._package_text(self.kernel.GetPackageFullName, handle)
            application_id = self._package_text(self.kernel.GetApplicationUserModelId, handle)
            package_root = self._package_text(self.kernel.GetPackagePathByFullName, full_name) if full_name else ""
            if not self.package_binding(process_path, family, full_name, application_id, package_root):
                return None
            created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
            if not self.kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
                return None
            started = (created.dwHighDateTime << 32) | created.dwLowDateTime
        finally:
            self.kernel.CloseHandle(handle)
        rect = wintypes.RECT()
        class_name = ctypes.create_unicode_buffer(256)
        if not self.user.GetClientRect(hwnd, ctypes.byref(rect)) or not self.user.GetClassNameW(hwnd, class_name, len(class_name)):
            return None
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if class_name.value != self.window_class or not (100 <= width <= 16384 and 100 <= height <= 16384):
            return None
        return _Window(hwnd, pid.value, started, process_path, class_name.value, width, height, family, full_name, application_id, os.path.normcase(package_root))

    def windows(self) -> list[_Window]:
        found: list[_Window] = []
        failed = False
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd: int, _data: int) -> bool:
            nonlocal failed
            try:
                item = self.snapshot(int(hwnd))
                if item is not None:
                    found.append(item)
                return True
            except Exception:
                failed = True
                return False
        callback_ref = callback_type(callback)
        self.user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self.user.EnumWindows.restype = wintypes.BOOL
        if not self.user.EnumWindows(callback_ref, 0) or failed:
            _fail("claude_capture_unavailable", "Window enumeration is unavailable.")
        return sorted(found, key=lambda item: (item.pid, item.hwnd))[:16]

    def guard(self, window: _Window) -> _WindowGuard:
        return _WindowGuard(self, window)


class _WindowGuard:
    """Latch destroy/hide/minimize/move/resize even between polling ticks."""

    def __init__(self, system: _Win32, window: _Window):
        self.system, self.window = system, window
        self.hooks: list[int] = []
        self.invalid = False
        self.checks = 0

    def __enter__(self) -> _WindowGuard:
        u = self.system.user
        callback_type = ctypes.WINFUNCTYPE(None, wintypes.HANDLE, wintypes.DWORD, wintypes.HWND, wintypes.LONG, wintypes.LONG, wintypes.DWORD, wintypes.DWORD)
        def callback(_hook: int, event: int, hwnd: int, object_id: int, _child: int, _thread: int, _time: int) -> None:
            if int(hwnd or 0) == self.window.hwnd and (event == 0x16 or (object_id == 0 and event in {0x8001, 0x8003, 0x800B})):
                self.invalid = True
        self.callback = callback_type(callback)
        u.SetWinEventHook.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.HMODULE, callback_type, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD]
        u.SetWinEventHook.restype = wintypes.HANDLE
        u.UnhookWinEvent.argtypes = [wintypes.HANDLE]
        u.UnhookWinEvent.restype = wintypes.BOOL
        u.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        u.PeekMessageW.restype = wintypes.BOOL
        u.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
        u.DispatchMessageW.restype = wintypes.LPARAM
        try:
            for first, last in ((0x16, 0x16), (0x8001, 0x800B)):
                hook = u.SetWinEventHook(first, last, None, self.callback, self.window.pid, 0, 0)
                if not hook:
                    _fail("claude_capture_guard_unavailable", "Window state monitoring is unavailable.")
                self.hooks.append(int(hook))
            self.check()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def check(self) -> None:
        message = wintypes.MSG()
        while self.system.user.PeekMessageW(ctypes.byref(message), None, 0, 0, 1):
            self.system.user.TranslateMessage(ctypes.byref(message))
            self.system.user.DispatchMessageW(ctypes.byref(message))
        self.checks += 1
        if self.invalid or self.system.snapshot(self.window.hwnd) != self.window:
            _fail("claude_capture_target_changed", "The selected window changed, closed, became hidden or was minimized. Nothing will be published.")

    def __exit__(self, *_args: Any) -> None:
        for hook in self.hooks:
            self.system.user.UnhookWinEvent(hook)
        self.hooks.clear()


class _GuardedCancel:
    def __init__(self, parent: Any, guard: Any):
        self.parent, self.guard = parent, guard

    def raise_if_cancelled(self) -> None:
        assembly._raise_if_cancelled(self.parent)
        self.guard.check()

    def register_process(self, process: Any) -> None:
        assembly._register_process(self.parent, process)

    def unregister_process(self, process: Any) -> None:
        assembly._unregister_process(self.parent, process)


def _command(ffmpeg: str, window: _Window, duration_ms: int, output: Path) -> list[str]:
    # No caller-controlled filter, selector, URL or path enters the public API.
    if not isinstance(window.hwnd, int) or window.hwnd <= 0:
        _fail("claude_capture_selection_invalid", "The selected window is invalid.")
    graph = (
        f"gfxcapture=hwnd={window.hwnd}:capture_cursor=0:display_border=1:max_framerate={FPS}:output_fmt=bgra,"
        f"hwdownload,format=bgra,scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps={FPS},setpts=PTS-STARTPTS[v]"
    )
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe",
            "-filter_complex", graph, "-map", "[v]", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
            "-frames:v", str((duration_ms * FPS + 999) // 1000), "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p", "-threads", "2", "-movflags", "+faststart", str(output)]


def _still_command(ffmpeg: str, window: _Window, output: Path) -> list[str]:
    if not isinstance(window.hwnd, int) or window.hwnd <= 0:
        _fail("claude_capture_selection_invalid", "The selected window is invalid.")
    graph = (f"gfxcapture=hwnd={window.hwnd}:capture_cursor=0:display_border=1:max_framerate=1:output_fmt=bgra,"
             "hwdownload,format=bgra,format=rgb24[v]")
    return [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-n", "-protocol_whitelist", "file,pipe",
            "-filter_complex", graph, "-map", "[v]", "-an", "-sn", "-dn", "-map_metadata", "-1",
            "-frames:v", "1", "-c:v", "png", "-pix_fmt", "rgb24", "-threads", "1", "-f", "image2", "-update", "1", str(output)]


def _validate_probe(probe: Any, expected_ms: int) -> dict[str, Any]:
    if not isinstance(probe, dict) or not isinstance(probe.get("streams"), list) or len(probe["streams"]) != 1:
        _fail("invalid_claude_capture_media", "The capture must have exactly one video stream and no audio.")
    video = probe["streams"][0]
    expected_frames = (expected_ms * FPS + 999) // 1000
    expected_frame_duration_ms = expected_frames * 1000 / FPS
    try:
        duration = float(probe["format"]["duration"])
        stream_duration = float(video["duration"])
        start = float(video["start_time"])
        frames = int(video["nb_read_frames"])
        numerator, denominator = (int(item) for item in video["avg_frame_rate"].split("/"))
        valid = (video["codec_type"] == "video" and video["codec_name"] == "h264" and video["pix_fmt"] == "yuv420p"
                 and video["width"] == WIDTH and video["height"] == HEIGHT and denominator > 0 and numerator / denominator == FPS
                 and math.isfinite(duration) and math.isfinite(stream_duration) and math.isfinite(start)
                 and abs(start) <= 0.000001 and frames == expected_frames
                 # FFprobe prints durations to six decimals; allow only that
                 # rounding error, never a missing final frame or short source.
                 and -0.001 <= duration * 1000 - expected_ms < 1000 / FPS + 0.001
                 and -0.001 <= stream_duration * 1000 - expected_ms < 1000 / FPS + 0.001
                 and abs(duration * 1000 - expected_frame_duration_ms) <= 0.001
                 and abs(stream_duration * 1000 - expected_frame_duration_ms) <= 0.001)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        valid = False
    if not valid:
        _fail("invalid_claude_capture_media", "The silent capture failed duration, frame or format validation.")
    return {"duration_ms": round(duration * 1000), "frame_count": frames, "video_dimensions": {"width": WIDTH, "height": HEIGHT}, "frame_rate": FPS, "audio_streams": 0}


def _validate_frame(path: Path) -> None:
    native._validate_png(path)
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[12:16] != b"IHDR" or struct.unpack(">II", header[16:24]) != (WIDTH, HEIGHT):
        _fail("invalid_claude_capture_media", "The capture preview has invalid dimensions.")


class ClaudeCaptureController:
    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace).resolve(strict=True)
        self._lock = threading.Lock()
        self._active = threading.Lock()
        self._selections: dict[str, tuple[_Window, float, str]] = {}
        self._claims: dict[str, ClaudeCaptureClaim] = {}
        self._still_claims: dict[str, ClaudeStillClaim] = {}
        self._tools: dict[str, Any] | None = None

    def _system(self) -> _Win32:
        return _Win32()

    def _resolve_tools(self) -> dict[str, Any]:
        if os.name != "nt":
            _fail("claude_capture_unavailable", "Windows is required.")
        result: dict[str, Any] = {}
        for name in ("ffmpeg", "ffprobe"):
            path = Path(assembly._find_tool(name)).resolve(strict=True)
            code, output, _ = native._run_contained_process([str(path), "-hide_banner", "-version"], cwd=self.workspace, timeout=10, label="claude-capability", cancel_event=None)
            if code or not output:
                _fail("claude_capture_unavailable", "The local media tools are unavailable.")
            result[name] = str(path)
            result[name + "_sha256"] = _sha(path)
        code, output, _ = native._run_contained_process([result["ffmpeg"], "-hide_banner", "-h", "filter=gfxcapture"], cwd=self.workspace, timeout=10, label="claude-capability", cancel_event=None)
        if code or not all(value in output for value in (b"gfxcapture", b"hwnd", b"capture_cursor", b"max_framerate")):
            _fail("claude_capture_unavailable", "This FFmpeg build does not expose WGC window capture.")
        return result

    def inspect(self, *, session_binding: str) -> dict[str, Any]:
        session = _session(session_binding)
        try:
            tools = self._resolve_tools()
            windows = self._system().windows()
        except (RuntimeError, OSError, ValueError):
            return {"schema_version": 1, "provider": PROVIDER, "available": False, "reason": "claude_capture_unavailable", "actual_capture_performed": False, "selections": []}
        now = time.monotonic()
        selections = []
        with self._lock:
            self._tools = tools
            self._claims = {key: claim for key, claim in self._claims.items() if claim._expires > now}
            self._still_claims = {key: claim for key, claim in self._still_claims.items() if claim._expires > now}
            self._selections = {key: item for key, item in self._selections.items() if item[1] > now and item[2] != session}
            if len(self._selections) > 256:
                self._selections.clear()
            for index, window in enumerate(windows):
                token = secrets.token_urlsafe(32)
                self._selections[selection_token_digest(token)] = (window, now + SELECTION_TTL_SECONDS, session)
                selections.append({"selection_token": token, "label": f"Claude {index + 1}", "width": window.width, "height": window.height, "available": True, "expires_in_seconds": SELECTION_TTL_SECONDS})
        return {"schema_version": 1, "provider": PROVIDER, "available": bool(selections), "reason": None if selections else "claude_window_not_available", "actual_capture_performed": False, "selections": selections}

    def claim(self, body: Any, *, session_binding: str) -> ClaudeCaptureClaim:
        payload = validate_capture_request(body)
        session = _session(session_binding)
        digest = selection_token_digest(payload["selection_token"])
        with self._lock:
            item = self._selections.get(digest)
            if item is None or item[1] <= time.monotonic() or item[2] != session:
                _fail("claude_capture_selection_invalid", "Select the window again; the selection expired or was already used.")
            del self._selections[digest]
            claim = ClaudeCaptureClaim(secrets.token_hex(16), digest, payload["duration_ms"], item[0], item[1])
            self._claims[claim.capture_id] = claim
        return claim

    def claim_still(self, body: Any, *, session_binding: str) -> ClaudeStillClaim:
        if not isinstance(body, dict) or set(body) != {"selection_token", "confirm_capture"} or body["confirm_capture"] is not True:
            _fail("invalid_claude_capture_request", "Select and explicitly confirm one still image.")
        digest = selection_token_digest(body["selection_token"])
        session = _session(session_binding)
        with self._lock:
            item = self._selections.get(digest)
            if item is None or item[1] <= time.monotonic() or item[2] != session:
                _fail("claude_capture_selection_invalid", "Select the window again; the selection expired or was used.")
            if item[0].width * item[0].height > 16_000_000 or max(item[0].width, item[0].height) > 12000:
                _fail("invalid_claude_capture_media", "The selected window is too large for a still image.")
            del self._selections[digest]
            claim = ClaudeStillClaim(secrets.token_hex(16), digest, item[0], item[1])
            self._still_claims[claim.capture_id] = claim
        return claim

    def discard_still(self, claim: ClaudeStillClaim) -> None:
        with self._lock:
            self._still_claims.pop(claim.capture_id, None)

    def capture_still(self, claim: ClaudeStillClaim, *, output: Path, cancel_event: Any = None) -> dict[str, Any]:
        """Exactly one native-resolution PNG. No video, audio, crop or fallback."""
        with self._lock:
            if not isinstance(claim, ClaudeStillClaim) or self._still_claims.pop(claim.capture_id, None) is not claim:
                _fail("claude_capture_selection_invalid", "This still claim was not issued here or has been used.")
            tools = dict(self._tools or {})
        if claim._expires <= time.monotonic():
            _fail("claude_capture_selection_invalid", "The selection expired before capture started.")
        if not self._active.acquire(blocking=False):
            _fail("claude_capture_busy", "A Claude capture is already running.")
        owned: Path | None = None
        try:
            output = Path(output)
            if native._has_symlink_component(self.workspace, output):
                _fail("invalid_claude_capture_output", "Linked image paths are not allowed.")
            target = workspace_path(self.workspace, output)
            parts = target.relative_to(self.workspace).parts
            if len(parts) != 5 or parts[:3] != ("outputs", "studio", "stills") or not re.fullmatch(r"still_[a-f0-9]{32}", parts[3]) or parts[4] != "image.png" or target.exists() or not target.parent.is_dir():
                _fail("invalid_claude_capture_output", "A new dedicated still-image output is required.")
            if "ffmpeg" not in tools or _sha(Path(tools["ffmpeg"])) != tools.get("ffmpeg_sha256"):
                _fail("claude_capture_tool_changed", "Inspect again; the capture engine changed.")
            runtime = _runtime_directory(self.workspace)
            system = self._system()
            started = datetime.now(timezone.utc).isoformat()
            with system.guard(claim._window) as guard:
                guarded = _GuardedCancel(cancel_event, guard)
                guarded.raise_if_cancelled()
                owned = target
                code, _, _ = native._run_contained_process(_still_command(tools["ffmpeg"], claim._window, target), cwd=runtime, timeout=20, label="claude-still", cancel_event=guarded)
                guarded.raise_if_cancelled()
                if code:
                    _fail("claude_capture_failed", "The selected window could not be captured. No fallback was attempted.")
                # Reuse library bounds and full Pillow decode; keep original bytes.
                from .still_media import read_still_png
                _, media = read_still_png(self.workspace, target.relative_to(self.workspace))
                guarded.raise_if_cancelled()
                checks = guard.checks
            return {"schema_version": 1, "mode": "still", "engine": "ffmpeg_gfxcapture_wgc", "target": "selected_claude_window",
                    "target_binding_sha256": claim._window.digest(), "selection_digest": claim.selection_digest,
                    "source_dimensions": {"width": claim._window.width, "height": claim._window.height}, "source_dimension_units": "win32_client_coordinates",
                    "media": media, "window_guard_checks": checks, "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(),
                    "actual_capture_performed": True, "audio_capture_performed": False, "video_capture_performed": False,
                    "resized": False, "content_quality_verified": False, "public_release_ready": False,
                    "tool_sha256": tools["ffmpeg_sha256"], "target_identity_policy": "claude-official-msix-family-v1"}
        except BaseException:
            # Only the exact newly-owned file; no recursive or broad cleanup.
            if owned is not None and owned.exists():
                if native._has_symlink_component(self.workspace, owned) or not owned.is_file():
                    _fail("claude_capture_cleanup_failed", "The private still output changed; cleanup was stopped.")
                owned.unlink()
            raise
        finally:
            self._active.release()

    def capture(self, claim: ClaudeCaptureClaim, *, capture_root: Path, cancel_event: Any = None) -> dict[str, Any]:
        with self._lock:
            if not isinstance(claim, ClaudeCaptureClaim) or self._claims.pop(claim.capture_id, None) is not claim:
                _fail("claude_capture_selection_invalid", "This capture claim was not issued here or has already been used.")
            tools = dict(self._tools or {})
        if claim._expires <= time.monotonic():
            _fail("claude_capture_selection_invalid", "The capture selection expired before recording started.")
        if not self._active.acquire(blocking=False):
            _fail("claude_capture_busy", "A Claude window capture is already running.")
        partial: Path | None = None
        published: Path | None = None
        try:
            assembly._raise_if_cancelled(cancel_event)
            for name in ("ffmpeg", "ffprobe"):
                if name not in tools or _sha(Path(tools[name])) != tools.get(name + "_sha256"):
                    _fail("claude_capture_tool_changed", "The capture tools changed; inspect again before recording.")
            target = _capture_root(capture_root, self.workspace)
            if target.exists():
                _fail("invalid_claude_capture_output", "Capture requires a new, dedicated local output directory.")
            runtime_directory = _runtime_directory(self.workspace)
            target.parent.mkdir(parents=True, exist_ok=True)
            partial = target.with_name(f".{target.name}.{claim.capture_id}.partial")
            partial.mkdir(exist_ok=False)
            video = partial / "claude-capture.mp4"
            system = self._system()
            started = datetime.now(timezone.utc).isoformat()
            with system.guard(claim._window) as guard:
                guarded_cancel = _GuardedCancel(cancel_event, guard)
                guarded_cancel.raise_if_cancelled()
                code, _stdout, _stderr = native._run_contained_process(_command(tools["ffmpeg"], claim._window, claim.duration_ms, video), cwd=runtime_directory, timeout=claim.duration_ms / 1000 + 20, label="claude-window", cancel_event=guarded_cancel)
                guard.check()
                if code:
                    _fail("claude_capture_failed", "WGC could not record the selected window. No fallback capture was attempted.")
                guard_checks = guard.checks
            if not video.is_file() or not 0 < video.stat().st_size <= _MAX_BYTES:
                _fail("invalid_claude_capture_media", "The capture output is missing or too large.")
            probe_args = [tools["ffprobe"], "-v", "error", "-protocol_whitelist", "file,pipe", "-count_frames", "-show_entries", "stream=codec_type,codec_name,pix_fmt,width,height,start_time,duration,avg_frame_rate,nb_read_frames:format=duration", "-of", "json", str(video)]
            code, stdout, _ = native._run_contained_process(probe_args, cwd=runtime_directory, timeout=30, label="claude-probe", cancel_event=cancel_event)
            try:
                probe = json.loads(stdout) if code == 0 else None
            except (ValueError, UnicodeError):
                probe = None
            measured = _validate_probe(probe, claim.duration_ms)
            code, _, _ = native._run_contained_process([tools["ffmpeg"], "-v", "error", "-xerror", "-nostdin", "-protocol_whitelist", "file,pipe", "-i", str(video), "-map", "0:v:0", "-f", "null", "-"], cwd=runtime_directory, timeout=45, label="claude-decode", cancel_event=cancel_event)
            if code:
                _fail("invalid_claude_capture_media", "The recorded video failed full decoding.")
            for name, frame in (("first-frame.png", 0), ("last-frame.png", measured["frame_count"] - 1)):
                code, _, _ = native._run_contained_process([tools["ffmpeg"], "-v", "error", "-nostdin", "-y", "-protocol_whitelist", "file,pipe", "-i", str(video), "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1", "-update", "1", str(partial / name)], cwd=runtime_directory, timeout=30, label="claude-frame", cancel_event=cancel_event)
                if code:
                    _fail("invalid_claude_capture_media", "Capture preview extraction failed.")
                _validate_frame(partial / name)
            if system.snapshot(claim._window.hwnd) != claim._window:
                _fail("claude_capture_target_changed", "The selected window changed before capture verification completed.")
            report = {"schema_version": 1, "implementation_version": IMPLEMENTATION_VERSION, "provider": PROVIDER, "capture_id": claim.capture_id,
                      "selection_digest": claim.selection_digest, "target_binding_sha256": claim._window.digest(), "target": "selected_claude_window",
                      "source_dimensions": {"width": claim._window.width, "height": claim._window.height}, "source_dimension_units": "win32_client_coordinates", "requested_duration_ms": claim.duration_ms,
                      "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat(), "audio_mode": "none", "audio_capture_performed": False,
                      "actual_capture_performed": True, "window_guard_checks": guard_checks, "structural_video_verified": True, "full_decode_verified": True,
                      "content_quality_verified": False, "public_release_ready": False, "network_access": False,
                      "engine": "ffmpeg_gfxcapture_wgc", "target_identity_policy": "claude-official-msix-family-v1", "tool_identity": {key: value for key, value in tools.items() if key.endswith("_sha256")}, **measured}
            report["runtime_directory_policy"] = "isolated_local_driver_cache_v1"
            native._write_json(partial / "capture-report.json", report)
            native._write_json(partial / "ffprobe.json", probe)
            files = [{"name": name, "kind": kind, "media_type": mime, "bytes": (partial / name).stat().st_size, "sha256": _sha(partial / name)} for name, (kind, mime) in _FILES.items() if name != "manifest.json"]
            manifest = {"schema_version": 1, "capture_id": claim.capture_id, "implementation_version": IMPLEMENTATION_VERSION, "report": report, "artifacts": files}
            manifest["manifest_sha256"] = hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest().upper()
            native._write_json(partial / "manifest.json", manifest)
            assembly._raise_if_cancelled(cancel_event)
            if native._has_symlink_component(self.workspace, target) or target.exists():
                _fail("invalid_claude_capture_output", "The output destination changed during recording.")
            os.rename(partial, target)
            partial, published = None, target
            artifacts = [{"name": name, "kind": kind, "mime": mime, "media_type": mime, "path": str(target / name), "rel_path": (target / name).relative_to(self.workspace).as_posix(), "bytes": (target / name).stat().st_size, "sha256": _sha(target / name)} for name, (kind, mime) in _FILES.items()]
            assembly._raise_if_cancelled(cancel_event)
            return {**report, "artifacts": artifacts}
        except BaseException:
            if partial is not None or published is not None:
                cleanup_capture_root(target, workspace=self.workspace)
            raise
        finally:
            self._active.release()


__all__ = ["ClaudeCaptureController", "ClaudeCaptureClaim", "ClaudeStillClaim", "ClaudeCaptureError", "PROVIDER", "cleanup_capture_root", "selection_token_digest", "validate_capture_request"]
