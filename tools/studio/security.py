from __future__ import annotations

import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SENSITIVE_KEY_RE = re.compile(
    r"(?:api[_-]?key|authorization|bearer|cookie|credential|password|private[_-]?key|secret|session|token|sig(?:nature)?|signed[_-]?url|sas)",
    re.IGNORECASE,
)
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_BASIC_AUTH_RE = re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/=]{8,}")
_AUTHORIZATION_HEADER_RE = re.compile(
    r"(?im)^(\s*(?:proxy-)?authorization\s*:\s*)[^\r\n]*"
)
_COOKIE_HEADER_RE = re.compile(r"(?im)^(\s*(?:set-)?cookie\s*:\s*)[^\r\n]*")
_COMMON_KEY_RE = re.compile(
    r"(?i)\b(?:sk|key|token|secret)-[A-Za-z0-9_-]{8,}"
)
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_ -]?key|authorization|cookie|credential|password|secret|session|token|sig(?:nature)?|signed[_ -]?url|sas)"
    r"(\s*[:=]\s*)(?![\"'])([^\s,;]+)"
)
_QUOTED_ASSIGNMENT_RE = re.compile(
    r"(?i)([\"'](?:api[_-]?key|authorization|bearer|cookie|credential|password|private[_-]?key|secret|session|token|sig(?:nature)?|signed[_-]?url|sas)[\"']\s*:\s*)"
    r"([\"'])([^\"'\r\n]*)([\"'])"
)
_QUOTED_VALUE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_ -]?key|authorization|cookie|credential|password|private[_ -]?key|secret|session|token|sig(?:nature)?|signed[_ -]?url|sas)"
    r"(\s*[:=]\s*)([\"'])([^\r\n]*)\3"
)
_GENERIC_QUOTED_ASSIGNMENT_RE = re.compile(
    r"(?im)^(\s*(?:(?:export|set)\s+)?(?:\$env:|\$)?)([A-Za-z_][A-Za-z0-9_.-]*)(\s*[:=]\s*)"
    r"([\"'])([^\r\n]*)\4"
)
_GENERIC_UNQUOTED_ASSIGNMENT_RE = re.compile(
    r"(?im)^(\s*(?:(?:export|set)\s+)?(?:\$env:|\$)?)([A-Za-z_][A-Za-z0-9_.-]*)(\s*[:=]\s*)"
    r"(?![\"'])([^\s#;,]+)"
)
_UNSAFE_STRUCTURED_TEXT_SUFFIXES = {
    ".cfg",
    ".conf",
    ".csv",
    ".htm",
    ".html",
    ".ini",
    ".svg",
    ".toml",
    ".tsv",
    ".xml",
    ".xhtml",
    ".yaml",
    ".yml",
}
_SAFE_REDACTABLE_TEXT_SUFFIXES = {
    ".ass",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".srt",
    ".txt",
    ".vtt",
}


class SecurityError(ValueError):
    """Raised when an input attempts to leave the workspace boundary."""


class UnsafeTextArtifactError(SecurityError):
    """Raised when a text format cannot be safely redacted for external exposure."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate_identifier(value: str, *, label: str = "identifier") -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise SecurityError(f"invalid {label}")
    return value


def workspace_path(workspace: Path, candidate: str | Path, *, must_exist: bool = False) -> Path:
    root = workspace.resolve(strict=True)
    supplied = Path(candidate)
    joined = supplied if supplied.is_absolute() else root / supplied
    resolved = joined.resolve(strict=must_exist)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SecurityError("path is outside the workspace") from exc
    return resolved


def relative_workspace_path(workspace: Path, path: Path) -> str:
    resolved = workspace_path(workspace, path, must_exist=True)
    return resolved.relative_to(workspace.resolve(strict=True)).as_posix()


def stable_id(prefix: str, value: str, *, length: int = 32) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"


def redact_text(value: str) -> str:
    def sensitive_assignment_key(key: str) -> bool:
        normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
        exact = {
            "api_key",
            "authorization",
            "cookie",
            "credential",
            "key",
            "password",
            "private_key",
            "proxy_authorization",
            "sas",
            "secret",
            "session",
            "signature",
            "signed_url",
            "token",
        }
        suffixes = tuple(f"_{item}" for item in exact)
        return normalized in exact or normalized.endswith(suffixes)

    value = _GENERIC_QUOTED_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}{match.group(3)}"
            f"{match.group(4)}[REDACTED]{match.group(4)}"
            if sensitive_assignment_key(match.group(2))
            else match.group(0)
        ),
        value,
    )
    value = _GENERIC_UNQUOTED_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}{match.group(3)}[REDACTED]"
            if sensitive_assignment_key(match.group(2))
            else match.group(0)
        ),
        value,
    )
    value = _BEARER_RE.sub("Bearer [REDACTED]", value)
    value = _BASIC_AUTH_RE.sub("Basic [REDACTED]", value)
    value = _AUTHORIZATION_HEADER_RE.sub(
        lambda match: f"{match.group(1)}[REDACTED]", value
    )
    value = _COOKIE_HEADER_RE.sub(lambda match: f"{match.group(1)}[REDACTED]", value)
    value = _COMMON_KEY_RE.sub("[REDACTED]", value)
    value = _QUOTED_ASSIGNMENT_RE.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}",
        value,
    )
    value = _QUOTED_VALUE_ASSIGNMENT_RE.sub(
        lambda match: (
            f"{match.group(1)}{match.group(2)}{match.group(3)}"
            f"[REDACTED]{match.group(3)}"
        ),
        value,
    )
    value = _ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]", value)
    return value


def sanitize_for_storage(value: Any, *, _sensitive_parent: bool = False) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return "[REDACTED]" if _sensitive_parent else redact_text(value)
    if isinstance(value, list):
        return [sanitize_for_storage(item, _sensitive_parent=_sensitive_parent) for item in value]
    if isinstance(value, tuple):
        return [sanitize_for_storage(item, _sensitive_parent=_sensitive_parent) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            key = str(raw_key)
            sensitive = bool(_SENSITIVE_KEY_RE.search(key))
            result[key] = sanitize_for_storage(item, _sensitive_parent=sensitive)
        return result
    return redact_text(str(value))


_SENSITIVE_DIRECTORY_NAMES = {
    ".credentials",
    ".git",
    ".hg",
    ".secrets",
    ".svn",
    "credential",
    "credentials",
    "secret",
    "secrets",
}
_SENSITIVE_FILE_NAMES = {
    ".env",
    ".netrc",
    ".npmrc",
    ".pypirc",
    "credentials.json",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
_SENSITIVE_FILE_SUFFIXES = {".dpapi", ".key", ".p12", ".pem", ".pfx"}
_SENSITIVE_CONFIG_SUFFIXES = {".env", ".netrc", ".npmrc", ".pypirc"}


def unsafe_structured_text_suffix(suffix: str) -> bool:
    return suffix.casefold() in _UNSAFE_STRUCTURED_TEXT_SUFFIXES


def sensitive_artifact_path(candidate: str | Path) -> bool:
    """Return True for credential-bearing paths that Studio must never index/export."""
    path = Path(candidate)
    parts = [part.casefold() for part in path.parts]
    if any(part in _SENSITIVE_DIRECTORY_NAMES for part in parts):
        return True
    name = path.name.casefold()
    return bool(
        name in _SENSITIVE_FILE_NAMES
        or name.startswith(".env.")
        or name.startswith(".npmrc.")
        or name.startswith(".pypirc.")
        or path.suffix.casefold() in _SENSITIVE_CONFIG_SUFFIXES
        or path.suffix.casefold() in _SENSITIVE_FILE_SUFFIXES
    )


def redact_artifact_text(value: str, *, suffix: str = "") -> str:
    """Redact structured and unstructured text before browser/export exposure."""
    normalized_suffix = suffix.casefold()
    if normalized_suffix and normalized_suffix not in _SAFE_REDACTABLE_TEXT_SUFFIXES:
        raise UnsafeTextArtifactError(
            "this text format has no trusted Studio redaction path"
        )
    if normalized_suffix == ".json":
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise UnsafeTextArtifactError("invalid JSON cannot be safely exposed") from exc
        else:
            return json.dumps(
                sanitize_for_storage(parsed),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ) + ("\n" if value.endswith(("\n", "\r")) else "")
    if normalized_suffix == ".jsonl":
        trailing_newline = value.endswith(("\n", "\r"))
        lines: list[str] = []
        for line in value.splitlines():
            if not line.strip():
                lines.append("")
                continue
            try:
                parsed = json.loads(line)
            except (TypeError, json.JSONDecodeError) as exc:
                raise UnsafeTextArtifactError("invalid JSONL cannot be safely exposed") from exc
            else:
                lines.append(canonical_json(sanitize_for_storage(parsed)))
        return "\n".join(lines) + ("\n" if trailing_newline else "")
    return redact_text(value)


def tokens_equal(expected: str, supplied: str | None) -> bool:
    if not supplied:
        return False
    return hmac.compare_digest(expected.encode("utf-8"), supplied.encode("utf-8"))
