from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

DEFAULT_PAGINATION_REQUEST = {
    "current_page": 1,
    "page_size": 20,
    "sort_by": "",
    "filter_by": "",
    "search_text": "",
}


def build_g2p_request(
    request_payload: dict[str, Any],
    pagination_request: dict[str, Any] | None = None,
    sender_app_mnemonic: str = "Registry Staff Portal Load Test",
    sender_app_url: str = "",
) -> dict[str, Any]:
    """Build the full G2P request envelope expected by the staff portal controllers."""
    effective_pagination = dict(DEFAULT_PAGINATION_REQUEST)
    if pagination_request:
        effective_pagination.update(pagination_request)

    request_header = {
        "sender_app_mnemonic": sender_app_mnemonic,
        "sender_app_url": sender_app_url,
        "request_id": str(uuid4()),
        "request_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    return {
        "request_header": request_header,
        "request_body": {
            "pagination_request": effective_pagination,
            "request_payload": request_payload,
        },
    }
