from __future__ import annotations

"""Fail-closed control-plane contracts for the local ComfyUI video adapter.

Only a prompt, a seed, and one allowlisted workflow preset may cross the
public boundary.  Paths, endpoint selection, model records, the workflow
graph, output policy, and media tools are internal inputs resolved by the
Studio service.
"""

import hashlib
import re
import uuid
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .security import canonical_json


COMFYUI_SCHEMA_VERSION = 1
COMFYUI_IMPLEMENTATION_VERSION = "comfyui-official-q4-v3"
COMFYUI_PROVIDER = "comfyui"
COMFYUI_TIMING_SOURCE = "ffprobe"
COMFYUI_WORKFLOW_PRESET = "minimax_h3_t2v_official_q4_v1"
COMFYUI_WORKFLOW_RELATIVE_PATH = (
    "workflows/api/minimax_h3_t2v_official_q4_v1.json"
)
COMFYUI_WORKFLOW_FILE_BYTES = 3_319
COMFYUI_WORKFLOW_FILE_SHA256 = (
    "A071849B9C7F6C400D05FADA227360BEEFE27F371C26A941FF9D3C9002D5A390"
)
COMFYUI_WORKFLOW_GRAPH_SHA256 = (
    "17870B5C5922DA39AAACFEDE8424725E853AF3EC269359AE4D79AC5B6D019E90"
)

RUNTIME_FILE_SPECS: dict[str, dict[str, Any]] = {
    "runtime_lock": {
        "relative_path": "runtime-lock.json",
        "bytes": 936,
        "sha256": "E782BB90EDB2BF937C0FBC122C2F79D9CB6E53183D9047737C4FA13B52A8EDC6",
    },
    "requirements_lock": {
        "relative_path": "requirements-local-lock.txt",
        "bytes": 1_892,
        "sha256": "187A5E5291FC68707C124E11D8A1E0A19C47A5857828C863294FDAAEFD9FED27",
    },
}

RUNTIME_REPOSITORY_SPECS: dict[str, dict[str, str]] = {
    "comfyui": {
        "relative_path": "runtime/ComfyUI",
        "revision": "2a68ce33b4c9ea6ee4283e618a74560cefb32694",
    },
    "comfyui_gguf": {
        "relative_path": "runtime/ComfyUI/custom_nodes/ComfyUI-GGUF",
        "revision": "6ea2651e7df66d7585f6ffee804b20e92fb38b8a",
    },
    "minimax_h3_turbo": {
        "relative_path": "runtime/ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-Turbo",
        "revision": "55fee864dd7b2976b1c4ce3c3d5f7968f181409f",
    },
}

MAX_PROMPT_CHARS = 50_000
MAX_SEED = 2**63 - 1
MAX_CACHE_KEY_CHARS = 256
MAX_DURATION_MS = 30 * 60 * 1000

OUTPUT_POLICY: dict[str, Any] = {
    "policy_version": "minimax-h3-official-q4-portrait-5s-h264-v1",
    "container": "mp4",
    "video_codec": "h264",
    "pixel_format": "yuv420p",
    "width": 480,
    "height": 864,
    "frame_rate": 24,
    "expected_frames": 124,
    "expected_duration_ms": 5167,
    "duration_tolerance_ms": 250,
    "audio_codec": "aac",
    "audio_sample_rate": 32000,
    "audio_channels": 2,
    "save_encoding": "re-encode",
    "crf": 18,
}

# These identities are pinned by the repository's model-manifest.json.  The
# adapter verifies each exact allowlisted workspace path and byte size before
# submission and carries the already-audited manifest digest as provenance.
# Re-hashing roughly 40 GB on every queue operation is intentionally avoided.
MODEL_SPECS: dict[str, dict[str, Any]] = {
    "diffusion_model": {
        "name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors",
        "relative_path": (
            "runtime/ComfyUI/models/diffusion_models/"
            "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
        ),
        "bytes": 20_970_379_616,
        "sha256": "E889202C41DAFB67B10D67B97F0D8541508036A6090AF23425A5C2615D03C47A",
    },
    "text_encoder": {
        "name": "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf",
        "relative_path": (
            "runtime/ComfyUI/models/text_encoders/"
            "qwen3vl-32B-MiniMax-H3-Q4_K_M.gguf"
        ),
        "bytes": 14_576_977_888,
        "sha256": "1BF75E038C5895B97B6EA16CC1E3D32076254B06EC3DF10657650D86DC82279E",
    },
    "video_vae": {
        "name": "minimax_h3_video_vae_fp16.safetensors",
        "relative_path": (
            "runtime/ComfyUI/models/vae/minimax_h3_video_vae_fp16.safetensors"
        ),
        "bytes": 5_207_808_496,
        "sha256": "7C1F131492E7EDDACAAC9069A61B81BDD39DE5CC96561E677C5EAB1CDCE5E522",
    },
    "audio_vae": {
        "name": "minimax_h3_audio_vae_fp32.safetensors",
        "relative_path": (
            "runtime/ComfyUI/models/vae/minimax_h3_audio_vae_fp32.safetensors"
        ),
        "bytes": 605_254_808,
        "sha256": "8E505D95DD1561D47ABD43D4238FD40D9BB1AE9E147ED0A4CBA778D76AE4DB48",
    },
}

_PUBLIC_KEYS = {"workflow_preset", "prompt", "seed"}
_MODEL_RECORD_KEYS = {"path", "bytes", "sha256"}
_WORKFLOW_RECORD_KEYS = {"path", "bytes", "sha256", "graph_sha256"}
_TOOL_IDENTITY_KEYS = {"path", "version", "sha256"}
_RUNTIME_IDENTITY_KEYS = {"runtime_lock", "requirements_lock", "repositories"}
_RUNTIME_FILE_KEYS = {"path", "bytes", "sha256"}
_RUNTIME_REPOSITORY_KEYS = {"path", "revision", "tracked_clean"}
_SHA256_RE = re.compile(r"^[0-9A-Fa-f]{64}$")
_GIT_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,256}$")
_CONTROL_CHARS = frozenset(chr(value) for value in range(32)) - {"\n", "\r", "\t"}


class ComfyUIError(RuntimeError):
    """A bounded error that is safe to persist at the Studio job boundary."""

    error_code = "comfyui_failed"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.error_code = code
        self.public_message = message


class ComfyUIValidationError(ValueError):
    """Raised when a public or internal ComfyUI contract is malformed."""

    def __init__(self, message: str, *, code: str = "invalid_comfyui_request"):
        super().__init__(message)
        self.code = code


class ComfyUISubmissionUnknown(ComfyUIError):
    def __init__(self) -> None:
        super().__init__(
            "The ComfyUI submission state is unknown; automatic resubmission is blocked.",
            code="comfyui_submission_unknown",
        )


class ComfyUIProviderError(ComfyUIError):
    pass


class ComfyUIMediaError(ComfyUIError):
    pass


def _strict_sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ComfyUIValidationError(f"{label} is invalid")
    return value.upper()


def _strict_positive_int(value: Any, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ComfyUIValidationError(f"{label} must be a positive integer")
    return value


def _path_has_allowlisted_suffix(value: str, expected: str) -> bool:
    supplied_parts = PurePosixPath(value).parts
    expected_parts = PurePosixPath(expected).parts
    return (
        ".." not in supplied_parts
        and len(supplied_parts) >= len(expected_parts)
        and supplied_parts[-len(expected_parts) :] == expected_parts
    )


def validate_comfyui_payload(body: Any) -> dict[str, Any]:
    """Validate the exact public request for the one allowlisted preset."""

    if not isinstance(body, dict) or any(not isinstance(key, str) for key in body):
        raise ComfyUIValidationError("request body must be an object")
    if set(body) != _PUBLIC_KEYS:
        raise ComfyUIValidationError(
            "request body must contain only workflow_preset, prompt, and seed"
        )
    if body.get("workflow_preset") != COMFYUI_WORKFLOW_PRESET:
        raise ComfyUIValidationError("workflow_preset is not allowlisted")
    prompt = body.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_PROMPT_CHARS:
        raise ComfyUIValidationError("prompt is invalid")
    if any(character in _CONTROL_CHARS or ord(character) == 127 for character in prompt):
        raise ComfyUIValidationError("prompt contains unsupported control characters")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in prompt):
        raise ComfyUIValidationError("prompt contains invalid Unicode")
    try:
        encoded = prompt.encode("utf-8")
    except UnicodeEncodeError as exc:  # defensive for alternate Python builds
        raise ComfyUIValidationError("prompt contains invalid Unicode") from exc
    if len(encoded) > MAX_PROMPT_CHARS * 4:
        raise ComfyUIValidationError("prompt is too large")
    seed = body.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= MAX_SEED:
        raise ComfyUIValidationError("seed is out of range")
    return {
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt": prompt,
        "seed": seed,
    }


def normalize_workflow_record(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _WORKFLOW_RECORD_KEYS:
        raise ComfyUIValidationError("workflow provenance is invalid")
    path = value.get("path")
    if not isinstance(path, (str, Path)) or not str(path) or len(str(path)) > 1024:
        raise ComfyUIValidationError("workflow provenance path is invalid")
    normalized_path = str(path).replace("\\", "/")
    if not _path_has_allowlisted_suffix(
        normalized_path, COMFYUI_WORKFLOW_RELATIVE_PATH
    ):
        raise ComfyUIValidationError("workflow provenance path is not allowlisted")
    normalized = {
        "path": normalized_path,
        "bytes": _strict_positive_int(value.get("bytes"), label="workflow bytes"),
        "sha256": _strict_sha256(value.get("sha256"), label="workflow sha256"),
        "graph_sha256": _strict_sha256(
            value.get("graph_sha256"), label="workflow graph sha256"
        ),
    }
    if (
        normalized["bytes"] != COMFYUI_WORKFLOW_FILE_BYTES
        or normalized["sha256"] != COMFYUI_WORKFLOW_FILE_SHA256
        or normalized["graph_sha256"] != COMFYUI_WORKFLOW_GRAPH_SHA256
    ):
        raise ComfyUIValidationError("workflow identity is not allowlisted")
    return normalized


def normalize_model_records(value: Any) -> dict[str, dict[str, Any]]:
    """Validate the four pinned model records used by the workflow."""

    if not isinstance(value, Mapping) or set(value) != set(MODEL_SPECS):
        raise ComfyUIValidationError("model provenance must contain four pinned roles")
    normalized: dict[str, dict[str, Any]] = {}
    for role, spec in MODEL_SPECS.items():
        raw = value.get(role)
        if not isinstance(raw, Mapping):
            raise ComfyUIValidationError(f"model provenance for {role} is invalid")
        raw_keys = set(raw)
        if raw_keys != _MODEL_RECORD_KEYS and raw_keys != _MODEL_RECORD_KEYS | {"name"}:
            raise ComfyUIValidationError(f"model provenance for {role} is invalid")
        if "name" in raw and raw.get("name") != spec["name"]:
            raise ComfyUIValidationError(f"model name for {role} is invalid")
        path = raw.get("path")
        if not isinstance(path, (str, Path)) or not str(path) or len(str(path)) > 1024:
            raise ComfyUIValidationError(f"model path for {role} is invalid")
        normalized_path = str(path).replace("\\", "/")
        if not _path_has_allowlisted_suffix(
            normalized_path, str(spec["relative_path"]).replace("\\", "/")
        ):
            raise ComfyUIValidationError(f"model path for {role} is not allowlisted")
        size = _strict_positive_int(raw.get("bytes"), label=f"model bytes for {role}")
        digest = _strict_sha256(raw.get("sha256"), label=f"model sha256 for {role}")
        if size != spec["bytes"] or digest != spec["sha256"]:
            raise ComfyUIValidationError(f"model identity for {role} is not allowlisted")
        normalized[role] = {
            "name": spec["name"],
            "path": normalized_path,
            "bytes": size,
            "sha256": digest,
        }
    return normalized


def normalize_tool_identity(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != _TOOL_IDENTITY_KEYS:
        raise ComfyUIValidationError("ffprobe identity is invalid")
    path = value.get("path")
    version = value.get("version")
    if not isinstance(path, str) or not path or len(path) > 1024:
        raise ComfyUIValidationError("ffprobe identity path is invalid")
    if not isinstance(version, str) or not version or len(version) > 512:
        raise ComfyUIValidationError("ffprobe identity version is invalid")
    return {
        "path": path,
        "version": version,
        "sha256": _strict_sha256(value.get("sha256"), label="ffprobe identity sha256"),
    }


def normalize_runtime_identity(value: Any) -> dict[str, Any]:
    """Validate the locked local runtime used to execute the API graph."""

    if not isinstance(value, Mapping) or set(value) != _RUNTIME_IDENTITY_KEYS:
        raise ComfyUIValidationError("runtime identity is invalid")
    result: dict[str, Any] = {}
    for role, spec in RUNTIME_FILE_SPECS.items():
        raw = value.get(role)
        if not isinstance(raw, Mapping) or set(raw) != _RUNTIME_FILE_KEYS:
            raise ComfyUIValidationError(f"runtime identity for {role} is invalid")
        path = raw.get("path")
        if not isinstance(path, (str, Path)) or not str(path) or len(str(path)) > 1024:
            raise ComfyUIValidationError(f"runtime path for {role} is invalid")
        normalized_path = str(path).replace("\\", "/")
        if not _path_has_allowlisted_suffix(normalized_path, spec["relative_path"]):
            raise ComfyUIValidationError(f"runtime path for {role} is not allowlisted")
        record = {
            "path": normalized_path,
            "bytes": _strict_positive_int(raw.get("bytes"), label=f"runtime bytes for {role}"),
            "sha256": _strict_sha256(raw.get("sha256"), label=f"runtime sha256 for {role}"),
        }
        if record["bytes"] != spec["bytes"] or record["sha256"] != spec["sha256"]:
            raise ComfyUIValidationError(f"runtime identity for {role} is not allowlisted")
        result[role] = record

    raw_repositories = value.get("repositories")
    if not isinstance(raw_repositories, Mapping) or set(raw_repositories) != set(
        RUNTIME_REPOSITORY_SPECS
    ):
        raise ComfyUIValidationError("runtime repository identity is invalid")
    repositories: dict[str, dict[str, Any]] = {}
    for role, spec in RUNTIME_REPOSITORY_SPECS.items():
        raw = raw_repositories.get(role)
        if not isinstance(raw, Mapping) or set(raw) != _RUNTIME_REPOSITORY_KEYS:
            raise ComfyUIValidationError(
                f"runtime repository identity for {role} is invalid"
            )
        path = raw.get("path")
        revision = raw.get("revision")
        if not isinstance(path, (str, Path)) or not str(path) or len(str(path)) > 1024:
            raise ComfyUIValidationError(f"runtime repository path for {role} is invalid")
        normalized_path = str(path).replace("\\", "/")
        if not _path_has_allowlisted_suffix(normalized_path, spec["relative_path"]):
            raise ComfyUIValidationError(
                f"runtime repository path for {role} is not allowlisted"
            )
        if (
            not isinstance(revision, str)
            or not _GIT_REVISION_RE.fullmatch(revision)
            or revision != spec["revision"]
            or raw.get("tracked_clean") is not True
        ):
            raise ComfyUIValidationError(
                f"runtime repository identity for {role} is not allowlisted"
            )
        repositories[role] = {
            "path": normalized_path,
            "revision": revision,
            "tracked_clean": True,
        }
    result["repositories"] = repositories
    return result


def comfyui_payload_digest(payload: Mapping[str, Any]) -> str:
    normalized = validate_comfyui_payload(dict(payload))
    return hashlib.sha256(canonical_json(normalized).encode("utf-8")).hexdigest().upper()


def comfyui_resume_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return the normalized full request for private restart persistence.

    Unlike :func:`comfyui_audit_payload`, this contains the prompt text and
    must not be returned by public result/event endpoints.
    """

    return validate_comfyui_payload(dict(payload))


def comfyui_cache_key(
    payload: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any],
    models: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
    ffprobe_identity: Mapping[str, Any],
) -> str:
    """Build the content identity from prompt, graph, models, policy, and tool."""

    normalized_payload = validate_comfyui_payload(dict(payload))
    normalized_workflow = normalize_workflow_record(workflow)
    normalized_models = normalize_model_records(models)
    normalized_runtime = normalize_runtime_identity(runtime_identity)
    identity = {
        "schema_version": COMFYUI_SCHEMA_VERSION,
        "implementation_version": COMFYUI_IMPLEMENTATION_VERSION,
        "provider": COMFYUI_PROVIDER,
        "payload": normalized_payload,
        "workflow": {
            key: normalized_workflow[key]
            for key in ("bytes", "sha256", "graph_sha256")
        },
        # Paths are deliberately excluded from cache identity.  The pinned
        # role, filename, bytes, and digest survive workspace relocation.
        "models": {
            role: {
                key: record[key]
                for key in ("name", "bytes", "sha256")
            }
            for role, record in normalized_models.items()
        },
        "runtime_identity": {
            "runtime_lock": {
                key: normalized_runtime["runtime_lock"][key]
                for key in ("bytes", "sha256")
            },
            "requirements_lock": {
                key: normalized_runtime["requirements_lock"][key]
                for key in ("bytes", "sha256")
            },
            "repositories": {
                role: {
                    "revision": record["revision"],
                    "tracked_clean": record["tracked_clean"],
                }
                for role, record in normalized_runtime["repositories"].items()
            },
        },
        "output_policy": OUTPUT_POLICY,
        "ffprobe_identity": normalize_tool_identity(ffprobe_identity),
    }
    return hashlib.sha256(canonical_json(identity).encode("utf-8")).hexdigest().upper()


def comfyui_audit_payload(
    payload: Mapping[str, Any],
    *,
    workflow: Mapping[str, Any],
    models: Mapping[str, Any],
    runtime_identity: Mapping[str, Any],
    cache_key: str | None = None,
) -> dict[str, Any]:
    """Return provenance without returning the submitted prompt text."""

    normalized = validate_comfyui_payload(dict(payload))
    workflow_record = normalize_workflow_record(workflow)
    model_records = normalize_model_records(models)
    normalized_runtime = normalize_runtime_identity(runtime_identity)
    result: dict[str, Any] = {
        "provider": COMFYUI_PROVIDER,
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt_chars": len(normalized["prompt"]),
        "prompt_sha256": hashlib.sha256(normalized["prompt"].encode("utf-8")).hexdigest().upper(),
        "seed": normalized["seed"],
        "seed_decimal": str(normalized["seed"]),
        "workflow": workflow_record,
        "models": model_records,
        "runtime_identity": normalized_runtime,
        "output_policy": dict(OUTPUT_POLICY),
    }
    if cache_key is not None:
        if not isinstance(cache_key, str) or not _CACHE_KEY_RE.fullmatch(cache_key):
            raise ComfyUIValidationError("cache_key is invalid")
        result["cache_key"] = cache_key.upper()
    return result


def _prompt_id(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 64:
        raise ComfyUIError(
            "The ComfyUI worker returned invalid task metadata.",
            code="invalid_worker_result",
        )
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ComfyUIError(
            "The ComfyUI worker returned invalid task metadata.",
            code="invalid_worker_result",
        ) from exc
    canonical = str(parsed)
    if value.casefold() != canonical:
        raise ComfyUIError(
            "The ComfyUI worker returned invalid task metadata.",
            code="invalid_worker_result",
        )
    return canonical


def comfyui_public_result(
    raw: Any,
    *,
    expected_cache_key: str,
    expected_prompt_sha256: str,
    expected_seed: int,
    artifacts: list[dict[str, Any]],
    cache_hit: bool,
) -> dict[str, Any]:
    """Validate allowlisted worker metadata before database persistence."""

    if not isinstance(raw, dict):
        raise ComfyUIError(
            "The ComfyUI worker returned an invalid result.", code="invalid_worker_result"
        )
    if (
        raw.get("provider") != COMFYUI_PROVIDER
        or raw.get("timing_source") != COMFYUI_TIMING_SOURCE
        or raw.get("workflow_preset") != COMFYUI_WORKFLOW_PRESET
    ):
        raise ComfyUIError(
            "The ComfyUI worker returned invalid metadata.", code="invalid_worker_result"
        )
    returned_key = raw.get("cache_key")
    if (
        not isinstance(expected_cache_key, str)
        or not _CACHE_KEY_RE.fullmatch(expected_cache_key)
        or returned_key != expected_cache_key
    ):
        raise ComfyUIError(
            "The ComfyUI worker returned invalid cache metadata.", code="invalid_worker_result"
        )
    if not isinstance(raw.get("cache_hit"), bool) or raw["cache_hit"] is not cache_hit:
        raise ComfyUIError(
            "The ComfyUI worker returned invalid cache metadata.", code="invalid_worker_result"
        )
    duration_ms = raw.get("duration_ms")
    if (
        isinstance(duration_ms, bool)
        or not isinstance(duration_ms, int)
        or duration_ms <= 0
        or duration_ms > MAX_DURATION_MS
        or abs(duration_ms - OUTPUT_POLICY["expected_duration_ms"])
        > OUTPUT_POLICY["duration_tolerance_ms"]
    ):
        raise ComfyUIError(
            "The ComfyUI worker returned invalid timing.", code="invalid_worker_result"
        )
    prompt_id = _prompt_id(raw.get("provider_task_id"))
    if raw.get("prompt_id") != prompt_id:
        raise ComfyUIError(
            "The ComfyUI worker returned inconsistent task metadata.",
            code="invalid_worker_result",
        )
    try:
        prompt_sha256 = _strict_sha256(raw.get("prompt_sha256"), label="prompt sha256")
        expected_prompt_digest = _strict_sha256(
            expected_prompt_sha256, label="expected prompt sha256"
        )
    except ComfyUIValidationError as exc:
        raise ComfyUIError(
            "The ComfyUI worker returned invalid prompt provenance.",
            code="invalid_worker_result",
        ) from exc
    if prompt_sha256 != expected_prompt_digest:
        raise ComfyUIError(
            "The ComfyUI worker returned mismatched prompt provenance.",
            code="invalid_worker_result",
        )
    seed = raw.get("seed")
    if (
        isinstance(seed, bool)
        or not isinstance(seed, int)
        or not 0 <= seed <= MAX_SEED
        or isinstance(expected_seed, bool)
        or not isinstance(expected_seed, int)
        or not 0 <= expected_seed <= MAX_SEED
        or seed != expected_seed
    ):
        raise ComfyUIError(
            "The ComfyUI worker returned invalid seed metadata.",
            code="invalid_worker_result",
        )
    if (
        "actual_cost" not in raw
        or isinstance(raw.get("actual_cost"), bool)
        or raw.get("actual_cost") != 0
    ):
        raise ComfyUIError(
            "The ComfyUI worker returned invalid cost metadata.", code="invalid_worker_result"
        )
    return {
        "artifacts": artifacts,
        "duration_ms": duration_ms,
        "cache_key": returned_key,
        "request_cache_key": expected_cache_key,
        "cache_hit": cache_hit,
        "provider": COMFYUI_PROVIDER,
        "provider_task_id": prompt_id,
        "prompt_id": prompt_id,
        "actual_cost": 0,
        "timing_source": COMFYUI_TIMING_SOURCE,
        "workflow_preset": COMFYUI_WORKFLOW_PRESET,
        "prompt_sha256": prompt_sha256,
        "seed": seed,
        "seed_decimal": str(seed),
        "output_policy": dict(OUTPUT_POLICY),
        "cost": {"amount": "0.00", "currency": "USD", "source": "local"},
    }


def safe_comfyui_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, ComfyUIError):
        return str(exc.error_code)[:128], str(exc.public_message)[:1000]
    if isinstance(exc, ComfyUIValidationError):
        return str(exc.code)[:128], str(exc)[:1000]
    return "comfyui_failed", "The local ComfyUI job failed."


# Discoverable compatibility names for service wiring.
validate_payload = validate_comfyui_payload
cache_key = comfyui_cache_key
audit_payload = comfyui_audit_payload
public_result = comfyui_public_result


__all__ = [
    "COMFYUI_IMPLEMENTATION_VERSION",
    "COMFYUI_PROVIDER",
    "COMFYUI_SCHEMA_VERSION",
    "COMFYUI_TIMING_SOURCE",
    "COMFYUI_WORKFLOW_PRESET",
    "COMFYUI_WORKFLOW_RELATIVE_PATH",
    "COMFYUI_WORKFLOW_FILE_BYTES",
    "COMFYUI_WORKFLOW_FILE_SHA256",
    "COMFYUI_WORKFLOW_GRAPH_SHA256",
    "MODEL_SPECS",
    "OUTPUT_POLICY",
    "RUNTIME_FILE_SPECS",
    "RUNTIME_REPOSITORY_SPECS",
    "ComfyUIError",
    "ComfyUIMediaError",
    "ComfyUIProviderError",
    "ComfyUISubmissionUnknown",
    "ComfyUIValidationError",
    "comfyui_audit_payload",
    "comfyui_cache_key",
    "comfyui_payload_digest",
    "comfyui_public_result",
    "comfyui_resume_payload",
    "normalize_model_records",
    "normalize_runtime_identity",
    "normalize_tool_identity",
    "normalize_workflow_record",
    "safe_comfyui_error",
    "validate_comfyui_payload",
]
