from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .instance_lock import StudioInstanceLockError, WorkspaceInstanceLock
from .quick_create import (
    QUICK_CREATE_SCHEMA_VERSION,
    QuickCreateError,
    QuickCreateQcNonPass,
    load_quick_create_request,
    run_quick_create,
)
from .secrets import PROVIDERS, SecretStorageUnavailable, SecretStore
from .service import StudioService
from .test_video import TestVideoError, run_test_video


_DEFAULT_VOICE = "Microsoft Haruka Desktop"
_MAX_OUTPUT_BYTES = 16 * 1024
_MAX_OUTPUT_DEPTH = 5
_MAX_OUTPUT_ITEMS = 64
_MAX_OUTPUT_STRING = 1024
_SAFE_CODE_RE = re.compile(r"^[a-z0-9_.-]{1,128}$")
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")
# A close failure means a daemon worker may still touch the workspace.  Keep
# the OS lock object reachable until process exit instead of letting Python
# finalization release it while that old work is still draining.
_RETAINED_INSTANCE_LOCKS: list[WorkspaceInstanceLock] = []


class _CliOperationError(RuntimeError):
    """An internal, non-sensitive Studio CLI operation error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _non_negative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _positive_int(value: str) -> int:
    parsed = _non_negative_int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def _pronunciation(value: str) -> dict[str, str]:
    source, separator, target = value.partition("=")
    if not separator or not source or not target:
        raise argparse.ArgumentTypeError("must use SOURCE=TARGET")
    return {"source": source, "target": target}


def _bounded_output(value: Any, *, depth: int = 0) -> Any:
    """Keep worker summaries JSON-safe and bounded before writing stdout."""

    if depth >= _MAX_OUTPUT_DEPTH:
        return "[truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_OUTPUT_STRING]
    if isinstance(value, Path):
        return str(value)[:_MAX_OUTPUT_STRING]
    if isinstance(value, Mapping):
        bounded: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_OUTPUT_ITEMS:
                bounded["_truncated"] = True
                break
            bounded[str(key)[:128]] = _bounded_output(item, depth=depth + 1)
        return bounded
    if isinstance(value, (list, tuple)):
        bounded_items = [
            _bounded_output(item, depth=depth + 1)
            for item in value[:_MAX_OUTPUT_ITEMS]
        ]
        if len(value) > _MAX_OUTPUT_ITEMS:
            bounded_items.append("[truncated]")
        return bounded_items
    return str(value)[:_MAX_OUTPUT_STRING]


def _write_bounded_json(value: Any, *, stream: Any | None = None) -> None:
    if stream is None:
        stream = sys.stdout
    bounded = _bounded_output(value)
    try:
        encoded = json.dumps(bounded, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        encoded = json.dumps({"status": "succeeded"}, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_OUTPUT_BYTES:
        encoded = json.dumps(
            {"status": "succeeded", "truncated": True}, separators=(",", ":")
        )
    print(encoded, file=stream)


def _safe_error_code(value: Any, default: str = "test_video_failed") -> str:
    if isinstance(value, str) and _SAFE_CODE_RE.fullmatch(value):
        return value
    return default


def _test_video_error_message(code: str) -> str:
    """Return a stable message; never echo exception/path/provider text."""

    if code.startswith("invalid") or "validation" in code:
        return "The test-video request was rejected."
    if code.startswith("qc") or "technical" in code:
        return "The test-video quality check failed."
    if "stage" in code or "narration" in code or "timeline" in code:
        return "The test-video stage failed."
    return "The test-video operation failed."


def _write_test_video_error(code: str, *, stream: Any | None = None) -> None:
    if stream is None:
        stream = sys.stderr
    safe_code = _safe_error_code(code)
    print(
        json.dumps(
            {
                "error": {
                    "code": safe_code,
                    "message": _test_video_error_message(safe_code),
                }
            },
            separators=(",", ":"),
        ),
        file=stream,
    )


def _quick_create_error_message(code: str) -> str:
    """Return fixed operator text without reflecting request or job data."""

    if code == "workspace_in_use":
        return "The Studio workspace is already in use."
    if code == "quick_create_timeout":
        return "The Quick Create job did not reach a terminal state in time."
    if code == "technical_qc_failed":
        return "The Quick Create technical quality check did not pass."
    if code == "announcement_recipe_conflict":
        return "The Quick Create recipe revision changed before it was saved."
    if code.startswith("invalid") or code.startswith("quick_create_input"):
        return "The Quick Create request was rejected."
    return "The Quick Create operation failed."


def _safe_quick_create_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    identifier_keys = (
        "production_id",
        "recipe_id",
        "recipe_version_id",
        "job_id",
        "run_id",
        "revision_id",
    )
    for key in identifier_keys:
        item = value.get(key)
        if isinstance(item, str) and _SAFE_IDENTIFIER_RE.fullmatch(item):
            result[key] = item
    request_key = value.get("request_key")
    if isinstance(request_key, str) and re.fullmatch(r"[0-9A-F]{64}", request_key):
        result["request_key"] = request_key
    recipe_revision = value.get("recipe_revision")
    if (
        isinstance(recipe_revision, int)
        and not isinstance(recipe_revision, bool)
        and recipe_revision >= 1
    ):
        result["recipe_revision"] = recipe_revision
    for key in ("recipe_deduplicated", "job_deduplicated"):
        item = value.get(key)
        if isinstance(item, bool):
            result[key] = item
    status = value.get("status")
    if status in {"queued", "running", "succeeded", "failed", "interrupted"}:
        result["status"] = status
    return result


def _write_quick_create_error(
    code: str,
    *,
    context: Any = None,
    stream: Any | None = None,
) -> None:
    if stream is None:
        stream = sys.stderr
    safe_code = _safe_error_code(code, "quick_create_failed")
    document = {
        "schema_version": QUICK_CREATE_SCHEMA_VERSION,
        **_safe_quick_create_context(context),
        "error": {
            "code": safe_code,
            "message": _quick_create_error_message(safe_code),
        },
    }
    print(
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        file=stream,
    )


def _is_technical_qc_failure(value: Any) -> bool:
    if isinstance(value, Mapping):
        verdict = value.get("technical_verdict")
        if verdict == "fail":
            return True
        for key in ("qc", "result", "summary"):
            if _is_technical_qc_failure(value.get(key)):
                return True
    elif isinstance(value, (list, tuple)):
        return any(_is_technical_qc_failure(item) for item in value)
    return False


def _default_workspace() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage MiniMaxH3 Studio local settings")
    parser.add_argument("--workspace", type=Path, default=_default_workspace())
    commands = parser.add_subparsers(dest="command", required=True)
    secret = commands.add_parser("secret", help="Manage DPAPI-protected provider credentials")
    secret_commands = secret.add_subparsers(dest="secret_command", required=True)
    set_command = secret_commands.add_parser("set", help="Read and store a credential without echo")
    set_command.add_argument("provider", choices=sorted(PROVIDERS))
    delete_command = secret_commands.add_parser("delete", help="Delete a stored provider credential")
    delete_command.add_argument("provider", choices=sorted(PROVIDERS))
    status_command = secret_commands.add_parser("status", help="Show configured flags only")
    status_command.add_argument("provider", choices=sorted(PROVIDERS), nargs="?")

    test_video = commands.add_parser(
        "test-video", help="Render and technically verify a bounded local test video"
    )
    test_video.add_argument("--production-id", required=True)
    test_video.add_argument("--video-artifact-id", required=True)
    test_video.add_argument("--segment", action="append", required=True, dest="segments")
    test_video.add_argument("--voice", default=_DEFAULT_VOICE)
    test_video.add_argument("--rate", type=int, default=0)
    test_video.add_argument(
        "--pronunciation", action="append", type=_pronunciation, default=[]
    )
    test_video.add_argument("--start-ms", type=_non_negative_int, default=0)
    # A duration is intentionally explicit.  The CLI must not infer one from
    # an artifact record; the timeline worker validates the real media.
    test_video.add_argument("--end-ms", type=_non_negative_int, required=True)
    test_video.add_argument("--variant", choices=("captioned", "clean"), default="captioned")
    test_video.add_argument("--timeout-seconds", type=_positive_int, default=600)

    quick_create = commands.add_parser(
        "quick-create",
        help="Save and execute one versioned Quick Create JSON request",
    )
    quick_create.add_argument("request_file", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "test-video":
        return _run_test_video_command(args)
    if args.command == "quick-create":
        return _run_quick_create_command(args)

    return _run_secret_command(args)


def _run_secret_command(args: argparse.Namespace) -> int:
    try:
        workspace = args.workspace.resolve(strict=True)
        store = SecretStore(workspace)
        if args.secret_command == "set":
            value = getpass.getpass(f"{args.provider} credential: ")
            store.set(args.provider, value)
            print(json.dumps({"id": args.provider, "configured": True}))
            return 0
        if args.secret_command == "delete":
            removed = store.delete(args.provider)
            print(json.dumps({"id": args.provider, "configured": False, "removed": removed}))
            return 0
        statuses = store.statuses()
        if args.provider:
            statuses = [item for item in statuses if item["id"] == args.provider]
        print(json.dumps({"providers": statuses}, separators=(",", ":")))
        return 0
    except (OSError, ValueError, SecretStorageUnavailable) as exc:
        # The credential itself is never interpolated into an error.
        print(f"Studio secret operation failed: {type(exc).__name__}", file=sys.stderr)
        return 2


def _test_video_request(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "production_id": args.production_id,
        "video_artifact_id": args.video_artifact_id,
        "segments": [{"text": segment} for segment in args.segments],
        "voice": args.voice,
        "rate": args.rate,
        "pronunciations": list(args.pronunciation),
        "start_ms": args.start_ms,
        "end_ms": args.end_ms,
        "variant": args.variant,
        "timeout_seconds": args.timeout_seconds,
    }


def _refresh_index_or_raise(service: StudioService, timeout_seconds: float) -> None:
    refresh_job = service.refresh_index()
    if not isinstance(refresh_job, Mapping) or not isinstance(
        refresh_job.get("id"), str
    ):
        raise _CliOperationError("index_refresh_failed")
    completed = service.jobs.wait(refresh_job["id"], timeout=timeout_seconds)
    if not isinstance(completed, Mapping):
        raise _CliOperationError("index_refresh_timeout")
    if completed.get("status") in {"queued", "running"}:
        raise _CliOperationError("index_refresh_timeout")
    if completed.get("status") != "succeeded":
        raise _CliOperationError("index_refresh_failed")


def _run_test_video_command(args: argparse.Namespace) -> int:
    lock: WorkspaceInstanceLock | None = None
    service: StudioService | None = None
    exit_code = 2
    pending_result: dict[str, Any] | None = None
    try:
        # Resolve before acquiring the lock so a missing or non-directory
        # workspace is handled without creating any state outside it.
        workspace = args.workspace.resolve(strict=True)
        try:
            lock = WorkspaceInstanceLock(workspace)
        except StudioInstanceLockError:
            print(
                "Studio test-video could not start: workspace is already in use.",
                file=sys.stderr,
            )
        else:
            service = StudioService(workspace)
            _refresh_index_or_raise(service, args.timeout_seconds)
            result = run_test_video(service, _test_video_request(args))
            if _is_technical_qc_failure(result):
                _write_test_video_error("technical_qc_failed")
                exit_code = 3
            else:
                # Defer stdout until service shutdown proves that every old
                # worker is gone and the workspace lock can be released.
                pending_result = dict(result)
                exit_code = 0
    except TestVideoError as exc:
        code = _safe_error_code(getattr(exc, "error_code", None))
        _write_test_video_error(code)
        if code in {"technical_qc_failed", "technical_verdict_fail", "qc_technical_fail"}:
            exit_code = 3
        else:
            exit_code = 2
    except _CliOperationError as exc:
        _write_test_video_error(exc.code)
        exit_code = 2
    except (OSError, ValueError, TypeError, KeyError):
        # Do not interpolate exception text: it can contain a user path,
        # provider response, or another secret-bearing value.
        _write_test_video_error("test_video_failed")
        exit_code = 2
    except Exception:
        _write_test_video_error("test_video_failed")
        exit_code = 2
    except KeyboardInterrupt:
        _write_test_video_error("process_interrupted")
        exit_code = 130
    finally:
        service_closed = service is None
        if service is not None:
            try:
                service.close()
            except Exception:
                service_closed = False
            else:
                service_closed = True
        if lock is not None:
            if service_closed:
                try:
                    lock.close()
                except Exception:
                    _RETAINED_INSTANCE_LOCKS.append(lock)
                    service_closed = False
            else:
                _RETAINED_INSTANCE_LOCKS.append(lock)
        if not service_closed:
            if exit_code == 0:
                _write_test_video_error("process_interrupted")
            if exit_code != 130:
                exit_code = 2
            pending_result = None
    if exit_code == 0 and pending_result is not None:
        _write_bounded_json(pending_result)
    return exit_code


def _run_quick_create_command(args: argparse.Namespace) -> int:
    lock: WorkspaceInstanceLock | None = None
    service: StudioService | None = None
    exit_code = 2
    pending_result: dict[str, Any] | None = None
    pending_error: tuple[str, dict[str, Any]] | None = None
    try:
        workspace = args.workspace.resolve(strict=True)
        request = load_quick_create_request(args.request_file)
        deadline = time.monotonic() + request["timeout_seconds"]
        try:
            lock = WorkspaceInstanceLock(workspace)
        except StudioInstanceLockError:
            pending_error = ("workspace_in_use", {})
        else:
            service = StudioService(workspace)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _CliOperationError("index_refresh_timeout")
            _refresh_index_or_raise(service, remaining)
            pending_result = run_quick_create(
                service,
                request,
                deadline=deadline,
            )
            exit_code = 0
    except QuickCreateQcNonPass as exc:
        pending_error = (exc.code, exc.context)
        exit_code = 3
    except QuickCreateError as exc:
        pending_error = (exc.code, exc.context)
        exit_code = 2
    except _CliOperationError as exc:
        pending_error = (exc.code, {})
        exit_code = 2
    except (OSError, ValueError, TypeError, KeyError):
        pending_error = ("quick_create_failed", {})
        exit_code = 2
    except Exception:
        # Service and worker exceptions can contain local paths, recipe text,
        # or provider diagnostics.  Never reflect them into the CLI stream.
        pending_error = ("quick_create_failed", {})
        exit_code = 2
    except KeyboardInterrupt:
        pending_error = ("process_interrupted", {})
        exit_code = 130
    finally:
        service_closed = service is None
        if service is not None:
            try:
                service.close()
            except Exception:
                service_closed = False
            else:
                service_closed = True
        if lock is not None:
            if service_closed:
                try:
                    lock.close()
                except Exception:
                    _RETAINED_INSTANCE_LOCKS.append(lock)
                    service_closed = False
            else:
                _RETAINED_INSTANCE_LOCKS.append(lock)
        if not service_closed:
            pending_result = None
            pending_error = ("process_interrupted", {})
            if exit_code != 130:
                exit_code = 2

    if exit_code == 0 and pending_result is not None:
        _write_bounded_json(pending_result)
    elif pending_error is not None:
        _write_quick_create_error(
            pending_error[0],
            context=pending_error[1],
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
