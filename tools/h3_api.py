#!/usr/bin/env python3
"""Dependency-free command line client for the MiniMax H3 Video API."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib import error, parse, request


DEFAULT_API_BASE = "https://api.minimax.io"
MODEL = "MiniMax-H3"
RESOLUTIONS = ("768P", "2K")
RATIOS = ("adaptive", "21:9", "16:9", "4:3", "1:1", "3:4", "9:16")
CONCRETE_RATIOS = RATIOS[1:]
TERMINAL_STATUSES = frozenset(("succeeded", "failed", "cancelled"))
MAX_REQUEST_BYTES = 64 * 1024 * 1024
USER_AGENT = "MiniMax-H3-stdlib-cli/1.0"

_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

_MEDIA_CONFIG: dict[str, dict[str, Any]] = {
    "image": {
        "api_type": "image_url",
        "roles": frozenset(("first_frame", "last_frame", "reference_image")),
        "max_bytes": 30 * 1024 * 1024,
        "mime_by_suffix": {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
        },
    },
    "video": {
        "api_type": "video_url",
        "roles": frozenset(("reference_video",)),
        "max_bytes": 50 * 1024 * 1024,
        # The V2 API accepts local Base64 video only as video/mp4.
        "mime_by_suffix": {".mp4": "video/mp4"},
    },
    "audio": {
        "api_type": "audio_url",
        "roles": frozenset(("reference_audio",)),
        "max_bytes": 15 * 1024 * 1024,
        "mime_by_suffix": {".wav": "audio/wav", ".mp3": "audio/mpeg"},
    },
}


class H3Error(Exception):
    """Base class for user-facing errors."""


class H3ConfigurationError(H3Error):
    """Raised when local configuration is incomplete or invalid."""


class H3ValidationError(H3Error):
    """Raised before a request when input violates the public API contract."""


class H3APIError(H3Error):
    """Raised when the MiniMax API or a download endpoint returns an error."""


class _RejectHTTPRedirects(request.HTTPRedirectHandler):
    """Keep bearer-authenticated API requests on their original URL."""

    def redirect_request(
        self,
        req: request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


class H3TaskError(H3Error):
    """Raised when an asynchronous task fails, is cancelled, or times out."""


def load_env_file(path: Path) -> None:
    """Load a small dotenv file without overriding process environment values."""

    if not path.is_file():
        return
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError as exc:
        raise H3ConfigurationError(f"cannot read environment file {path}: {exc}") from exc

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        name, separator, value = stripped.partition("=")
        name = name.strip()
        if not separator or not _ENV_NAME.fullmatch(name):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        os.environ.setdefault(name, value)


def normalize_api_base(value: str) -> str:
    base = value.strip().rstrip("/")
    parsed = parse.urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise H3ConfigurationError(
            "MINIMAX_API_BASE must be an absolute http:// or https:// URL"
        )
    if parsed.username is not None or parsed.password is not None:
        raise H3ConfigurationError("MINIMAX_API_BASE must not contain credentials")
    if parsed.query or parsed.fragment:
        raise H3ConfigurationError("MINIMAX_API_BASE must not contain a query or fragment")
    if parsed.scheme == "http" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise H3ConfigurationError(
            "MINIMAX_API_BASE must use HTTPS unless the host is localhost, 127.0.0.1, or [::1]"
        )
    return base


def _redact(text: str, secrets: Iterable[str]) -> str:
    safe = text
    for secret in secrets:
        if secret:
            safe = safe.replace(secret, "[REDACTED]")
    return safe


def _extract_error_message(body: bytes) -> str:
    if not body:
        return "empty response body"
    decoded = body.decode("utf-8", errors="replace")
    try:
        parsed_body = json.loads(decoded)
    except json.JSONDecodeError:
        return decoded[:1000]
    if isinstance(parsed_body, dict):
        nested_error = parsed_body.get("error")
        if isinstance(nested_error, dict) and nested_error.get("message"):
            return str(nested_error["message"])
        if parsed_body.get("message"):
            return str(parsed_body["message"])
    return decoded[:1000]


def _is_remote_media(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith(("https://", "http://", "mm_file://", "data:"))


def media_source_to_url(kind: str, source: str) -> str:
    """Return a remote source unchanged or encode a local media file as a Data URL."""

    if kind not in _MEDIA_CONFIG:
        raise H3ValidationError(f"unsupported media kind: {kind}")
    source = source.strip()
    if not source:
        raise H3ValidationError(f"{kind} source must not be empty")
    if _is_remote_media(source):
        return source

    path = Path(source).expanduser()
    if not path.is_file():
        raise H3ValidationError(f"local {kind} file does not exist: {path}")
    config = _MEDIA_CONFIG[kind]
    mime_type = config["mime_by_suffix"].get(path.suffix.lower())
    if mime_type is None:
        supported = ", ".join(sorted(config["mime_by_suffix"]))
        raise H3ValidationError(
            f"unsupported local {kind} extension {path.suffix or '(none)'}; "
            f"expected one of: {supported}"
        )
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise H3ValidationError(f"cannot inspect local {kind} file {path}: {exc}") from exc
    if size > config["max_bytes"]:
        limit_mb = config["max_bytes"] // (1024 * 1024)
        raise H3ValidationError(f"local {kind} file exceeds the {limit_mb} MB API limit")
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise H3ValidationError(f"cannot read local {kind} file {path}: {exc}") from exc
    return f"data:{mime_type};base64,{encoded}"


def _append_media_items(
    content: list[dict[str, Any]], kind: str, entries: Sequence[Sequence[str]]
) -> None:
    config = _MEDIA_CONFIG[kind]
    api_type = str(config["api_type"])
    for entry in entries:
        if len(entry) != 2:
            raise H3ValidationError(f"each --{kind} needs ROLE and SOURCE")
        role, source = entry
        if role not in config["roles"]:
            allowed = ", ".join(sorted(config["roles"]))
            raise H3ValidationError(f"invalid {kind} role {role!r}; expected: {allowed}")
        content.append(
            {
                "type": api_type,
                api_type: {"url": media_source_to_url(kind, source)},
                "role": role,
            }
        )


def build_generation_payload(
    *,
    prompt: str,
    resolution: str,
    duration: int,
    ratio: str | None,
    images: Sequence[Sequence[str]] = (),
    videos: Sequence[Sequence[str]] = (),
    audios: Sequence[Sequence[str]] = (),
    callback_url: str | None = None,
) -> dict[str, Any]:
    """Validate CLI input and build the official V2 generation request body."""

    if not prompt.strip():
        raise H3ValidationError("prompt must not be empty")
    if len(prompt) > 7000:
        raise H3ValidationError("prompt must be at most 7000 characters")
    if resolution not in RESOLUTIONS:
        raise H3ValidationError(f"resolution must be one of: {', '.join(RESOLUTIONS)}")
    if isinstance(duration, bool) or not isinstance(duration, int) or not 4 <= duration <= 15:
        raise H3ValidationError("duration must be an integer from 4 through 15")
    if ratio is not None and ratio not in RATIOS:
        raise H3ValidationError(f"ratio must be one of: {', '.join(RATIOS)}")

    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    _append_media_items(content, "image", images)
    _append_media_items(content, "video", videos)
    _append_media_items(content, "audio", audios)

    roles = [str(item.get("role", "")) for item in content[1:]]
    image_mode = any(role in ("first_frame", "last_frame") for role in roles)
    reference_mode = any(role.startswith("reference_") for role in roles)
    if image_mode and reference_mode:
        raise H3ValidationError(
            "first/last-frame inputs cannot be mixed with reference image/video/audio inputs"
        )
    if roles.count("first_frame") > 1 or roles.count("last_frame") > 1:
        raise H3ValidationError("at most one first_frame and one last_frame are allowed")
    if roles.count("reference_image") > 9:
        raise H3ValidationError("at most 9 reference images are allowed")
    if roles.count("reference_video") > 3:
        raise H3ValidationError("at most 3 reference videos are allowed")
    if roles.count("reference_audio") > 3:
        raise H3ValidationError("at most 3 reference audio files are allowed")
    reference_roles = [role for role in roles if role.startswith("reference_")]
    if len(reference_roles) > 12:
        raise H3ValidationError("at most 12 reference files in total are allowed")
    if "reference_audio" in roles and not any(
        role in ("reference_image", "reference_video") for role in roles
    ):
        raise H3ValidationError(
            "reference audio requires at least one reference image or video; audio-only is not allowed"
        )

    if image_mode:
        if ratio not in (None, "adaptive"):
            raise H3ValidationError(
                "first/last-frame generation derives its ratio from the image; use adaptive"
            )
        effective_ratio = "adaptive"
    elif reference_mode:
        effective_ratio = ratio or "adaptive"
    else:
        if ratio not in CONCRETE_RATIOS:
            raise H3ValidationError(
                "text-to-video requires --ratio with a concrete value (not adaptive)"
            )
        effective_ratio = ratio

    payload: dict[str, Any] = {
        "model": MODEL,
        "content": content,
        "resolution": resolution,
        "duration": duration,
        "ratio": effective_ratio,
    }
    if callback_url:
        callback = parse.urlsplit(callback_url)
        if callback.scheme not in ("http", "https") or not callback.netloc:
            raise H3ValidationError("callback URL must be an absolute http:// or https:// URL")
        payload["callback_url"] = callback_url

    encoded_size = len(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )
    if encoded_size > MAX_REQUEST_BYTES:
        raise H3ValidationError(
            "request body exceeds the 64 MB API limit; use public URLs or mm_file:// sources"
        )
    return payload


class H3Client:
    """Small urllib-based client that never sends the API key to output CDNs."""

    def __init__(self, api_key: str, api_base: str, timeout: float = 60.0) -> None:
        api_key = api_key.strip()
        if not api_key:
            raise H3ConfigurationError(
                "MINIMAX_API_KEY is not configured; copy .env.example to .env and set it"
            )
        if timeout <= 0:
            raise H3ConfigurationError("request timeout must be greater than zero")
        self._api_key = api_key
        self.api_base = normalize_api_base(api_base)
        self.timeout = timeout
        # urllib's default redirect handler can forward Authorization to a
        # redirect target. API calls use a dedicated no-redirect opener so a
        # compromised/misconfigured endpoint cannot exfiltrate the bearer key.
        self._api_opener = request.build_opener(_RejectHTTPRedirects())

    def _safe(self, text: str) -> str:
        return _redact(text, (self._api_key,))

    def _request_json(
        self, method: str, endpoint: str, payload: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "User-Agent": USER_AGENT,
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            if len(data) > MAX_REQUEST_BYTES:
                raise H3ValidationError("request body exceeds the 64 MB API limit")
            headers["Content-Type"] = "application/json"

        url = f"{self.api_base}{endpoint}"
        api_request = request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._api_opener.open(api_request, timeout=self.timeout) as response:
                body = response.read()
        except error.HTTPError as exc:
            body = exc.read()
            message = self._safe(_extract_error_message(body))
            raise H3APIError(f"MiniMax API returned HTTP {exc.code}: {message}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise H3APIError(f"MiniMax API request failed: {self._safe(str(exc))}") from exc

        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise H3APIError("MiniMax API returned an invalid JSON response") from exc
        if not isinstance(decoded, dict):
            raise H3APIError("MiniMax API returned a non-object JSON response")
        return decoded

    def submit(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        response = self._request_json("POST", "/v2/video_generation", payload)
        if not isinstance(response.get("task_id"), str) or not response["task_id"]:
            raise H3APIError("MiniMax API response did not contain a task_id")
        return response

    def status(self, task_id: str) -> dict[str, Any]:
        task_id = task_id.strip()
        if not task_id or len(task_id) > 256:
            raise H3ValidationError("task_id must be a non-empty string of at most 256 characters")
        encoded_id = parse.quote(task_id, safe="")
        return self._request_json("GET", f"/v2/query/video_generation/{encoded_id}")

    def download(self, url: str, output: Path, *, overwrite: bool = False) -> int:
        parsed_url = parse.urlsplit(url)
        if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
            raise H3APIError("task output URL is not an absolute http:// or https:// URL")
        if parsed_url.username is not None or parsed_url.password is not None:
            raise H3APIError("task output URL must not contain credentials")
        output = output.expanduser().resolve()
        if output.exists() and not overwrite:
            raise H3ValidationError(f"output already exists: {output} (use --force to replace it)")
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise H3APIError(f"cannot create output directory {output.parent}: {exc}") from exc

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{output.name}.",
                suffix=".part",
                dir=output.parent,
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                # Deliberately omit Authorization: output URLs can point to a different host.
                download_request = request.Request(
                    url,
                    headers={"Accept": "video/mp4", "User-Agent": USER_AGENT},
                    method="GET",
                )
                with request.urlopen(download_request, timeout=self.timeout) as response:
                    total = 0
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        temporary.write(chunk)
                        total += len(chunk)
            if total == 0:
                raise H3APIError("downloaded video was empty")
            os.replace(temporary_path, output)
            temporary_path = None
            return total
        except error.HTTPError as exc:
            message = self._safe(_extract_error_message(exc.read()))
            raise H3APIError(f"video download returned HTTP {exc.code}: {message}") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise H3APIError(f"video download failed: {self._safe(str(exc))}") from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass


def task_from_response(response: Mapping[str, Any]) -> dict[str, Any]:
    task = response.get("task")
    if not isinstance(task, dict):
        raise H3APIError("MiniMax API response did not contain a task object")
    status = task.get("status")
    if status not in ("queued", "running", "succeeded", "failed", "cancelled"):
        raise H3APIError(f"MiniMax API returned an unknown task status: {status!r}")
    return task


def wait_for_task(
    client: H3Client,
    task_id: str,
    *,
    interval: float = 10.0,
    timeout: float = 0.0,
    output: Path | None = None,
    overwrite: bool = False,
    on_status: Callable[[str, Mapping[str, Any]], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[dict[str, Any], int | None]:
    """Poll a task and optionally download its successful MP4 output."""

    if interval <= 0:
        raise H3ValidationError("poll interval must be greater than zero")
    if timeout < 0:
        raise H3ValidationError("wait timeout cannot be negative")
    deadline = clock() + timeout if timeout else None

    while True:
        response = client.status(task_id)
        task = task_from_response(response)
        status = str(task["status"])
        if on_status is not None:
            on_status(status, task)
        if status == "succeeded":
            downloaded_bytes = None
            if output is not None:
                content = task.get("content")
                url = content.get("url") if isinstance(content, dict) else None
                if not isinstance(url, str) or not url:
                    raise H3APIError("succeeded task did not contain a video download URL")
                downloaded_bytes = client.download(url, output, overwrite=overwrite)
            return response, downloaded_bytes
        if status in ("failed", "cancelled"):
            error_info = task.get("error")
            detail = ""
            if isinstance(error_info, dict) and error_info.get("message"):
                detail = f": {client._safe(str(error_info['message']))}"
            raise H3TaskError(f"task {status}{detail}")

        sleep_for = interval
        if deadline is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                raise H3TaskError(f"timed out waiting for task after {timeout:g} seconds")
            sleep_for = min(sleep_for, remaining)
        sleep(sleep_for)


def _add_client_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-base",
        help="override MINIMAX_API_BASE (default: https://api.minimax.io)",
    )
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=60.0,
        metavar="SECONDS",
        help="timeout for each HTTP request (default: 60)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MiniMax H3 Video API CLI (Python standard library only)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser(
        "doctor",
        aliases=("config",),
        help="check local API configuration without making a network request",
    )
    doctor.add_argument("--api-base", help="override MINIMAX_API_BASE")
    doctor.add_argument("--json", action="store_true", help="print machine-readable JSON")

    submit = subparsers.add_parser("submit", help="submit a billable video generation task")
    prompt_group = submit.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="video generation prompt")
    prompt_group.add_argument("--prompt-file", type=Path, help="read the prompt from a UTF-8 file")
    submit.add_argument("--resolution", choices=RESOLUTIONS, default="768P")
    submit.add_argument("--duration", type=int, default=5, metavar="SECONDS")
    submit.add_argument("--ratio", choices=RATIOS)
    submit.add_argument(
        "--image",
        action="append",
        nargs=2,
        default=[],
        metavar=("ROLE", "SOURCE"),
        help="image role/source: first_frame, last_frame, or reference_image",
    )
    submit.add_argument(
        "--video",
        action="append",
        nargs=2,
        default=[],
        metavar=("ROLE", "SOURCE"),
        help="reference_video role and local path/public URL/mm_file URL",
    )
    submit.add_argument(
        "--audio",
        action="append",
        nargs=2,
        default=[],
        metavar=("ROLE", "SOURCE"),
        help="reference_audio role and local path/public URL/mm_file URL",
    )
    submit.add_argument("--callback-url")
    submit.add_argument(
        "--confirm-billable",
        action="store_true",
        help="required acknowledgement that submit can incur MiniMax API charges",
    )
    submit.add_argument(
        "--wait",
        action="store_true",
        help="poll after submission and download the completed MP4",
    )
    submit.add_argument("--output", type=Path, help="MP4 path used with --wait")
    submit.add_argument("--force", action="store_true", help="replace an existing output")
    submit.add_argument("--interval", type=float, default=10.0, metavar="SECONDS")
    submit.add_argument(
        "--wait-timeout",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="overall wait timeout; 0 waits indefinitely",
    )
    _add_client_options(submit)

    status = subparsers.add_parser("status", help="query one existing task")
    status.add_argument("task_id")
    status.add_argument("--download", type=Path, metavar="MP4")
    status.add_argument("--force", action="store_true", help="replace an existing output")
    _add_client_options(status)

    wait_parser = subparsers.add_parser(
        "wait", help="poll an existing task and download its completed MP4"
    )
    wait_parser.add_argument("task_id")
    wait_parser.add_argument("--output", type=Path, help="output MP4 path")
    wait_parser.add_argument(
        "--no-download", action="store_true", help="only wait; do not download the MP4"
    )
    wait_parser.add_argument("--force", action="store_true", help="replace an existing output")
    wait_parser.add_argument("--interval", type=float, default=10.0, metavar="SECONDS")
    wait_parser.add_argument(
        "--wait-timeout",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help="overall wait timeout; 0 waits indefinitely",
    )
    _add_client_options(wait_parser)
    return parser


def _api_base_from_args(args: argparse.Namespace) -> str:
    return args.api_base or os.environ.get("MINIMAX_API_BASE", DEFAULT_API_BASE)


def _new_client(args: argparse.Namespace) -> H3Client:
    return H3Client(
        os.environ.get("MINIMAX_API_KEY", ""),
        _api_base_from_args(args),
        timeout=args.request_timeout,
    )


def _default_output(task_id: str) -> Path:
    safe_id = _SAFE_FILENAME.sub("_", task_id).strip("._") or "video"
    return Path.cwd() / f"MiniMax-H3-{safe_id}.mp4"


def _print_json(value: Mapping[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _doctor(args: argparse.Namespace) -> int:
    problems: list[str] = []
    try:
        api_base = normalize_api_base(_api_base_from_args(args))
    except H3ConfigurationError as exc:
        api_base = "invalid"
        problems.append(str(exc))
    key_configured = bool(os.environ.get("MINIMAX_API_KEY", "").strip())
    if not key_configured:
        problems.append("MINIMAX_API_KEY is not configured")
    result: dict[str, Any] = {
        "api_base": api_base,
        "api_key": "configured" if key_configured else "missing",
        "model": MODEL,
        "network_request_made": False,
        "ok": not problems,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }
    if problems:
        result["problems"] = problems
    if args.json:
        _print_json(result)
    else:
        print(f"model: {result['model']}")
        print(f"api_base: {result['api_base']}")
        print(f"api_key: {result['api_key']} (value is never displayed)")
        print(f"python: {result['python']}")
        print("network: not contacted")
        if problems:
            for problem in problems:
                print(f"problem: {problem}", file=sys.stderr)
        else:
            print("configuration: OK")
    return 0 if not problems else 2


def _read_prompt(args: argparse.Namespace) -> str:
    if args.prompt is not None:
        return args.prompt
    try:
        return args.prompt_file.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise H3ValidationError(f"cannot read prompt file {args.prompt_file}: {exc}") from exc


def _progress_printer() -> Callable[[str, Mapping[str, Any]], None]:
    previous: list[str | None] = [None]

    def report(status: str, _task: Mapping[str, Any]) -> None:
        if status != previous[0]:
            print(f"status: {status}", file=sys.stderr)
            previous[0] = status

    return report


def _submit(args: argparse.Namespace) -> int:
    if not args.confirm_billable:
        raise H3ValidationError(
            "submit can incur MiniMax API charges; rerun with --confirm-billable after reviewing the request"
        )
    if not args.wait and args.output is not None:
        raise H3ValidationError("--output requires --wait")
    payload = build_generation_payload(
        prompt=_read_prompt(args),
        resolution=args.resolution,
        duration=args.duration,
        ratio=args.ratio,
        images=args.image,
        videos=args.video,
        audios=args.audio,
        callback_url=args.callback_url,
    )
    client = _new_client(args)
    response = client.submit(payload)
    task_id = str(response["task_id"])
    if not args.wait:
        _print_json(response)
        return 0

    print(f"submitted task: {task_id}", file=sys.stderr)
    output = args.output or _default_output(task_id)
    result, downloaded_bytes = wait_for_task(
        client,
        task_id,
        interval=args.interval,
        timeout=args.wait_timeout,
        output=output,
        overwrite=args.force,
        on_status=_progress_printer(),
    )
    combined = dict(result)
    combined["downloaded_to"] = str(output.expanduser().resolve())
    combined["downloaded_bytes"] = downloaded_bytes
    _print_json(combined)
    return 0


def _status(args: argparse.Namespace) -> int:
    client = _new_client(args)
    response = client.status(args.task_id)
    task = task_from_response(response)
    result = dict(response)
    if args.download is not None:
        if task["status"] != "succeeded":
            raise H3TaskError("the task has not succeeded, so there is no MP4 to download")
        content = task.get("content")
        url = content.get("url") if isinstance(content, dict) else None
        if not isinstance(url, str) or not url:
            raise H3APIError("succeeded task did not contain a video download URL")
        downloaded_bytes = client.download(url, args.download, overwrite=args.force)
        result["downloaded_to"] = str(args.download.expanduser().resolve())
        result["downloaded_bytes"] = downloaded_bytes
    _print_json(result)
    return 0


def _wait(args: argparse.Namespace) -> int:
    client = _new_client(args)
    output = None if args.no_download else (args.output or _default_output(args.task_id))
    if args.no_download and args.output is not None:
        raise H3ValidationError("--output cannot be combined with --no-download")
    response, downloaded_bytes = wait_for_task(
        client,
        args.task_id,
        interval=args.interval,
        timeout=args.wait_timeout,
        output=output,
        overwrite=args.force,
        on_status=_progress_printer(),
    )
    result = dict(response)
    if output is not None:
        result["downloaded_to"] = str(output.expanduser().resolve())
        result["downloaded_bytes"] = downloaded_bytes
    _print_json(result)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    try:
        load_env_file(project_root / ".env")
        args = build_parser().parse_args(argv)
        if args.command in ("doctor", "config"):
            return _doctor(args)
        if args.command == "submit":
            return _submit(args)
        if args.command == "status":
            return _status(args)
        if args.command == "wait":
            return _wait(args)
        raise H3ValidationError(f"unsupported command: {args.command}")
    except H3Error as exc:
        # Errors can contain server-provided text; redact the configured key defensively.
        message = _redact(str(exc), (os.environ.get("MINIMAX_API_KEY", ""),))
        print(f"error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
