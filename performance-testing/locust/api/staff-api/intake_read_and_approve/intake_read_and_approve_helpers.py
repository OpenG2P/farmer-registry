"""Pure parsing/selection helpers for the intake read-and-approve flow.

Kept separate from intake_read_and_approve_locustfile.py so the business
logic of paging through search results and picking out pending submissions
can be read (and tested) independently of the actual HTTP calls.
"""
from __future__ import annotations

from typing import Any, Optional


def response_payload(response_json: dict) -> Any:
    return (response_json or {}).get("response_body", {}).get("response_payload")


def total_pages(search_response_json: dict) -> int:
    pagination = (search_response_json or {}).get("response_body", {}).get("pagination_response") or {}
    return pagination.get("number_of_pages") or 1


def pending_submission_ids(search_response_json: dict) -> list[str]:
    """submission_ids of submissions on this page ready to approve.

    search_in_intake_form_submissions has no server-side way to filter by
    approval_status/draft_status: pagination_request.filter_by is validated
    against the register's filter_schema and applied only to the register's
    own domain model (e.g. Farmer attributes like first_name/gender) — those
    two fields live on a different table that this filter path never
    reaches, and an unrecognized field name is silently dropped rather than
    erroring. So every submission on the page comes back regardless of
    status, and the ready-to-approve ones are picked out here instead:
    draft_status must be FINAL (still-DRAFT submissions haven't been
    finalized yet) and approval_status must be PENDING (not already
    approved/rejected).
    """
    submissions = response_payload(search_response_json) or []
    return [
        submission["submission_id"]
        for submission in submissions
        if submission.get("draft_status") == "FINAL"
        and submission.get("approval_status") == "PENDING"
        and submission.get("submission_id")
    ]


def extract_awe_request_id(submission_response_json: dict) -> Optional[str]:
    """awe_request_id off get_intake_form_submission's response -- the id
    list_tasks_for_request needs, distinct from submission_id itself."""
    payload = response_payload(submission_response_json) or {}
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
