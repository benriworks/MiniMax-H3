from __future__ import annotations

from typing import Any


JOB_CONTROL_SCHEMA_VERSION = 1


class JobControlValidationError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_job_control_request"):
        super().__init__(message)
        self.code = code


def validate_job_cancel_payload(body: Any) -> dict[str, int]:
    """Validate the closed, versioned operator-cancellation request.

    Cancellation intentionally accepts no force flag, timeout, provider ID, or
    process selector.  The authenticated operator names exactly one durable Job
    in the URL and the service resolves all subordinate ownership from SQLite.
    """

    if not isinstance(body, dict) or set(body) != {"schema_version"}:
        raise JobControlValidationError(
            "Job cancellation requires only schema_version."
        )
    schema_version = body.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != JOB_CONTROL_SCHEMA_VERSION
    ):
        raise JobControlValidationError(
            "Job cancellation schema_version is not supported.",
            code="unsupported_job_control_schema",
        )
    return {"schema_version": JOB_CONTROL_SCHEMA_VERSION}
