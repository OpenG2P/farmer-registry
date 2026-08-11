"""Pure parsing/selection helpers for the cr_read_and_approve flow.

Kept separate from cr_read_and_approve_locustfile.py so the business logic
of paging through search results and picking out change_request_ids can be
read (and tested) independently of the actual HTTP calls.
"""
from __future__ import annotations

from typing import Any, Optional


def response_payload(response_json: dict) -> Any:
    return (response_json or {}).get("response_body", {}).get("response_payload")


def response_status(response_json: dict) -> Optional[str]:
    return (response_json or {}).get("response_header", {}).get("response_status")


def response_error_code(response_json: dict) -> Optional[str]:
    return (response_json or {}).get("response_header", {}).get("response_error_code")


def total_pages(search_response_json: dict) -> int:
    pagination = (search_response_json or {}).get("response_body", {}).get("pagination_response") or {}
    return pagination.get("number_of_pages") or 1


def approval_blocked(sequence_check_response_json: dict) -> bool:
    """True if check_change_request_sequence says an earlier, still-unapproved
    change request exists on the same internal_record_id — approving this one
    out of order would be wrong, so it should be skipped.
    """
    payload = response_payload(sequence_check_response_json) or {}
    return bool(payload.get("approval_decision_blocked"))


def pending_change_requests(search_response_json: dict) -> list[dict]:
    """Full result dicts (change_request_id, section_id, etc.) on this page
    whose approval_status is PENDING.

    search_in_change_request has no register/status scoping in its
    request_payload (it's empty — pagination_request.search_text is the only
    input), so every change request on the page comes back regardless of
    status; only PENDING ones should actually go through approve_change_request,
    so they're picked out here the same way pending_submission_ids does for
    intake_read_and_approve.
    """
    results = response_payload(search_response_json) or []
    return [
        result
        for result in results
        if result.get("approval_status") == "PENDING" and result.get("change_request_id")
    ]
