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
    status; only PENDING ones should actually go through the AWE decision
    step, so they're picked out here the same way pending_submission_ids does
    for intake_read_and_approve.
    """
    results = response_payload(search_response_json) or []
    return [
        result
        for result in results
        if result.get("approval_status") == "PENDING" and result.get("change_request_id")
    ]


def sort_pending_oldest_first(pending: list[dict]) -> list[dict]:
    """Oldest CRs first so check_change_request_sequence does not block.

    search_in_change_request defaults to created_at DESC (newest first). For a
    given internal_record_id, approving a newer PENDING CR while an older one
    is still open returns approval_decision_blocked — so page-order processing
    skips almost everything. Sort by created_at ASC (then change_request_id)
    across the collected set before approving.
    """
    return sorted(
        pending,
        key=lambda row: (row.get("created_at") or "", row.get("change_request_id") or ""),
    )


def search_term_candidates(
    search_terms: list[str],
    start_index: int = 0,
    max_anchor_probes: int = 10,
) -> list[str]:
    """Ordered search texts to try for cr_read_and_approve.

    Farmer-seed anchors alone often miss pending CRs: cr_create edits many
    non-farmer sections whose payload search_text never contains first_name
    anchors, and a sticky random anchor may have zero pending CRs even when
    others do. Probe up to max_anchor_probes anchors (starting at
    start_index), then fall back to "" — the API builds `%<text>%`, so empty
    matches all rows with any search_text (ILIKE '%%').
    """
    terms = [term for term in search_terms if term]
    if not terms:
        return [""]
    start = start_index % len(terms)
    rotated = terms[start:] + terms[:start]
    return rotated[:max_anchor_probes] + [""]


def extract_awe_request_id(change_request_response_json: dict) -> Optional[str]:
    """awe_request_id off get_change_request's response -- the id
    list_tasks_for_request needs, distinct from change_request_id itself."""
    payload = response_payload(change_request_response_json) or {}
    return payload.get("awe_request_id")


def actionable_task(list_tasks_response_json: dict) -> Optional[dict]:
    """First open/claimed task from list_tasks_for_request's response.items --
    the one submit_task_decision should act on."""
    payload = response_payload(list_tasks_response_json) or {}
    items = payload.get("data", {}).get("items") or []
    for item in items:
        if item.get("status") in ("open", "claimed") and item.get("id"):
            return item
    return None
