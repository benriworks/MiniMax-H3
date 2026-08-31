from __future__ import annotations

"""Closed request contracts for the non-destructive production library."""

import hashlib
import re
from typing import Any

from .production_intake import validate_production_id, validate_production_title
from .security import canonical_json


PRODUCTION_LIBRARY_SCHEMA_VERSION = 1
PRODUCTION_LIBRARY_OPERATION_ID_RE = re.compile(
    r"^production_library_op_[0-9a-f]{32}$"
)


class ProductionLibraryValidationError(ValueError):
    """A bounded, public-safe library request failure."""

    def __init__(self, message: str, *, code: str = "invalid_production_library_request"):
        super().__init__(message)
        self.code = code


def _error(message: str, code: str) -> ProductionLibraryValidationError:
    return ProductionLibraryValidationError(message, code=code)


def validate_library_operation_id(value: Any) -> str:
    if (
        not isinstance(value, str)
        or PRODUCTION_LIBRARY_OPERATION_ID_RE.fullmatch(value) is None
    ):
        raise _error(
            "operation_id must match production_library_op_ followed by 32 lowercase hexadecimal characters",
            "invalid_production_library_operation_id",
        )
    return value


def _exact_payload(value: Any, required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != required:
        raise _error(
            "production library request fields do not match the closed schema",
            "invalid_production_library_request",
        )
    if (
        isinstance(value.get("schema_version"), bool)
        or value.get("schema_version") != PRODUCTION_LIBRARY_SCHEMA_VERSION
    ):
        raise _error(
            "production library schema_version is not supported",
            "unsupported_production_library_schema",
        )
    return value


def validate_production_rename_payload(value: Any) -> dict[str, Any]:
    body = _exact_payload(
        value,
        {"schema_version", "operation_id", "expected_title", "title"},
    )
    expected_title = validate_production_title(body["expected_title"])
    title = validate_production_title(body["title"])
    if title == expected_title:
        raise _error("title must change", "production_library_no_change")
    return {
        "schema_version": PRODUCTION_LIBRARY_SCHEMA_VERSION,
        "operation_id": validate_library_operation_id(body["operation_id"]),
        "expected_title": expected_title,
        "title": title,
    }


def validate_production_archive_payload(value: Any) -> dict[str, Any]:
    body = _exact_payload(
        value,
        {"schema_version", "operation_id", "expected_archived", "archived"},
    )
    if not isinstance(body["expected_archived"], bool) or not isinstance(
        body["archived"], bool
    ):
        raise _error(
            "archived and expected_archived must be booleans",
            "invalid_production_library_archive_state",
        )
    if body["archived"] == body["expected_archived"]:
        raise _error("archive state must change", "production_library_no_change")
    return {
        "schema_version": PRODUCTION_LIBRARY_SCHEMA_VERSION,
        "operation_id": validate_library_operation_id(body["operation_id"]),
        "expected_archived": body["expected_archived"],
        "archived": body["archived"],
    }


def validate_production_duplicate_payload(value: Any) -> dict[str, Any]:
    body = _exact_payload(
        value,
        {
            "schema_version",
            "operation_id",
            "production_id",
            "title",
            "include_imports",
        },
    )
    if not isinstance(body["include_imports"], bool):
        raise _error(
            "include_imports must be a boolean",
            "invalid_production_library_duplicate_request",
        )
    return {
        "schema_version": PRODUCTION_LIBRARY_SCHEMA_VERSION,
        "operation_id": validate_library_operation_id(body["operation_id"]),
        "production_id": validate_production_id(body["production_id"]),
        "title": validate_production_title(body["title"]),
        "include_imports": body["include_imports"],
    }


def production_library_request_digest(action: str, body: dict[str, Any]) -> str:
    if action not in {"rename", "archive", "duplicate"}:
        raise ValueError("unsupported production library action")
    return hashlib.sha256(
        canonical_json({"action": action, "request": body}).encode("utf-8")
    ).hexdigest()


__all__ = [
    "PRODUCTION_LIBRARY_OPERATION_ID_RE",
    "PRODUCTION_LIBRARY_SCHEMA_VERSION",
    "ProductionLibraryValidationError",
    "production_library_request_digest",
    "validate_library_operation_id",
    "validate_production_archive_payload",
    "validate_production_duplicate_payload",
    "validate_production_rename_payload",
]
