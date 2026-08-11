"""Pure parsing/selection helpers for the register browsing flow.

Kept separate from register_locustfile.py so the business logic of parsing
search/metadata responses and choosing what to browse next can be read (and
tested) independently of the actual HTTP calls.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Optional


def response_payload(response_json: dict) -> Any:
    return (response_json or {}).get("response_body", {}).get("response_payload")


def choose_internal_record_id(search_response_json: dict) -> Optional[str]:
    results = response_payload(search_response_json) or []
    if not results:
        return None
    return random.choice(results)["internal_record_id"]


def extract_ordered_tab_ids(tabs_response_json: dict) -> list[str]:
    """tab_id list sorted ascending by tab_order, so tabs are browsed in UI order."""
    tabs = response_payload(tabs_response_json) or []
    ordered_tabs = sorted(tabs, key=lambda tab: tab["tab_order"])
    return [tab["tab_id"] for tab in ordered_tabs]


def extract_version_dates(version_dates_response_json: dict) -> list[str]:
    payload = response_payload(version_dates_response_json) or {}
    return payload.get("version_dates") or []


def total_pages(response_json: dict) -> int:
    pagination = (response_json or {}).get("response_body", {}).get("pagination_response") or {}
    return pagination.get("number_of_pages") or 1


def change_request_items(response_json: dict) -> list[dict]:
    """Every change request returned for one tab, one page. Unlike
    cr_read_and_approve's pending_change_requests, this doesn't filter by
    approval_status -- register_read is a pure browse flow, so every change
    request on the tab gets its detail read regardless of status."""
    return response_payload(response_json) or []


@dataclass
class RegisterBrowseState:
    """The record + tab picked for one browse_registers_and_view_detailed_record run."""

    register_id: str
    internal_record_id: Optional[str] = None
    tab_id: Optional[str] = None

    def has_record(self) -> bool:
        return self.internal_record_id is not None
