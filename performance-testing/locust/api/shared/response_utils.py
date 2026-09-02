from __future__ import annotations

from typing import Any


def safe_json(response) -> dict[str, Any]:
    """Best-effort JSON parse of a Locust/requests response; empty dict on failure."""
    try:
        return response.json()
    except ValueError:
        return {}


# HTTP 200 + envelope ERROR that still means the API handled the request
# correctly. Locust should count latency as success, not a performance failure.
_EXPECTED_BUSINESS_ERROR_MARKERS = (
    "There are earlier pending change requests for this record",
    "AWE-007",
)


def is_expected_business_error(header: dict[str, Any] | None) -> bool:
    """True for known domain rejections (sequence check, already-decided task)."""
    if not header:
        return False
    code = str(header.get("response_error_code") or "")
    message = str(header.get("response_error_message") or "")
    combined = f"{code}: {message}"
    return any(marker in combined for marker in _EXPECTED_BUSINESS_ERROR_MARKERS)
